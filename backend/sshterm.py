"""Real RouterOS shell in the browser: SSH (paramiko) or Telnet, bridged over a WebSocket to xterm.js."""
import asyncio, json, socket
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from core import db, level_of

ssh_router = APIRouter(prefix="/api")
RED = "\r\n\x1b[31m{}\x1b[0m\r\n"
CTRL = "\x00{}"  # control frames for the browser client (shell state), never printed to the terminal
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
OPT_ECHO, OPT_SGA = 1, 3


async def _authorize(token: str, router_id: str):
    from auth import _user_by_token, enrich_user
    doc = await _user_by_token(token) if token else None
    if not doc or doc.get("disabled"): return None, None, "Authentication failed — sign in again"
    user = await enrich_user(doc)
    if level_of(user, "routers") < 1: return None, None, "Your role has no access to routers"
    router = await db.routers.find_one({"id": router_id}, {"_id": 0})
    if not router: return None, None, "Router not found"
    if not user.get("is_super_admin") and (router.get("workspace_id") not in user["workspace_ids"] or router.get("group_id") not in user["effective_group_ids"]):
        return None, None, "You do not have access to this router"
    return user, router, None


# ---------- SSH ----------
def _open_shell(host: str, port: int, username: str, password: str, cols: int, rows: int):
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username=username, password=password, look_for_keys=False, allow_agent=False, timeout=12, banner_timeout=12, auth_timeout=12)
    chan = client.invoke_shell(term="vt100", width=cols, height=rows)
    chan.settimeout(0.2)
    return client, chan


def _read(chan) -> bytes | None:
    try: return chan.recv(8192)
    except socket.timeout: return b""
    except Exception: return None


async def run_ssh(websocket: WebSocket, router: dict, port: int, username: str, password: str, cols: int, rows: int):
    try: client, chan = await asyncio.to_thread(_open_shell, router["host"], port, username, password, cols, rows)
    except Exception as exc:
        await websocket.send_text(RED.format(f"SSH connection failed ({type(exc).__name__}): {str(exc)[:160]}"))
        await websocket.send_text("\x1b[33mEnable /ip service ssh on the router, check the SSH port in Edit router, or switch to Terminal (Telnet).\x1b[0m\r\n")
        await websocket.send_text(CTRL.format(json.dumps({"type": "failed"})))
        return
    await websocket.send_text(CTRL.format(json.dumps({"type": "ready"})))

    async def pump_out():
        while True:
            data = await asyncio.to_thread(_read, chan)
            if data is None: break
            if data: await websocket.send_bytes(data)
            elif chan.exit_status_ready() and not chan.recv_ready(): break
        try: await websocket.send_text("\r\n\x1b[33mSession closed by the router.\x1b[0m\r\n")
        except Exception: pass

    task = asyncio.create_task(pump_out())
    try:
        while True:
            message = await websocket.receive_text()
            if message.startswith("\x00"):
                payload = json.loads(message[1:])
                if payload.get("type") == "resize": chan.resize_pty(width=int(payload["cols"]), height=int(payload["rows"]))
                continue
            await asyncio.to_thread(chan.send, message)
    except (WebSocketDisconnect, RuntimeError, Exception): pass
    finally:
        task.cancel()
        for close in (chan.close, client.close):
            try: close()
            except Exception: pass


# ---------- Telnet ----------
def strip_telnet(data: bytes) -> tuple[bytes, bytes]:
    """Split raw telnet bytes into terminal output and the option negotiation we must answer."""
    out, reply, i = bytearray(), bytearray(), 0
    while i < len(data):
        if data[i] != IAC: out.append(data[i]); i += 1; continue
        if i + 1 >= len(data): break
        cmd = data[i + 1]
        if cmd == IAC: out.append(IAC); i += 2; continue
        if cmd == SB:
            end = data.find(bytes([IAC, SE]), i)
            i = end + 2 if end != -1 else len(data)
            continue
        if cmd in (WILL, WONT, DO, DONT):
            if i + 2 >= len(data): break
            opt = data[i + 2]
            if cmd == WILL: reply += bytes([IAC, DO if opt in (OPT_ECHO, OPT_SGA) else DONT, opt])
            elif cmd == WONT: reply += bytes([IAC, DONT, opt])
            elif cmd == DO: reply += bytes([IAC, WILL if opt == OPT_SGA else WONT, opt])
            else: reply += bytes([IAC, WONT, opt])
            i += 3
            continue
        i += 2
    return bytes(out), bytes(reply)


async def run_telnet(websocket: WebSocket, router: dict, port: int, username: str, password: str):
    try: reader, writer = await asyncio.wait_for(asyncio.open_connection(router["host"], port), timeout=12)
    except Exception as exc:
        await websocket.send_text(RED.format(f"Telnet connection failed ({type(exc).__name__}): {str(exc)[:160]}"))
        await websocket.send_text("\x1b[33mEnable /ip service telnet on the router or check the Telnet port in Edit router.\x1b[0m\r\n")
        await websocket.send_text(CTRL.format(json.dumps({"type": "failed"})))
        return
    await websocket.send_text(CTRL.format(json.dumps({"type": "ready"})))
    state = {"user": False, "pass": False, "tail": ""}

    async def pump_out():
        while True:
            data = await reader.read(4096)
            if not data: break
            clean, reply = strip_telnet(data)
            if reply:
                writer.write(reply); await writer.drain()
            if not clean: continue
            await websocket.send_bytes(clean)
            state["tail"] = (state["tail"] + clean.decode("utf-8", "ignore")).lower()[-160:]
            if not state["user"] and "login:" in state["tail"]:
                writer.write(f"{username}\r\n".encode()); await writer.drain(); state["user"] = True; state["tail"] = ""
            elif state["user"] and not state["pass"] and "password:" in state["tail"]:
                writer.write(f"{password}\r\n".encode()); await writer.drain(); state["pass"] = True; state["tail"] = ""
        try: await websocket.send_text("\r\n\x1b[33mSession closed by the router.\x1b[0m\r\n")
        except Exception: pass

    task = asyncio.create_task(pump_out())
    try:
        while True:
            message = await websocket.receive_text()
            if message.startswith("\x00"): continue
            writer.write(message.encode()); await writer.drain()
    except (WebSocketDisconnect, RuntimeError, Exception): pass
    finally:
        task.cancel()
        try: writer.close()
        except Exception: pass


@ssh_router.websocket("/routers/{router_id}/ssh")
async def shell_terminal(websocket: WebSocket, router_id: str, token: str = Query(""), proto: str = Query("ssh", pattern="^(ssh|telnet)$"),
                         cols: int = Query(110, ge=20, le=500), rows: int = Query(30, ge=5, le=200)):
    await websocket.accept()
    user, router, error = await _authorize(token, router_id)
    if error:
        await websocket.send_text(RED.format(error)); await websocket.close(); return
    from server import ros_credentials, user_secret
    try: username, password = ros_credentials(router, user, await user_secret(user["user_id"]))
    except Exception:
        await websocket.send_text(RED.format("Set your own MikroTik credentials in My settings before opening a shared router")); await websocket.close(); return
    port = int(router.get("telnet_port") or 23) if proto == "telnet" else int(router.get("ssh_port") or 22)
    await websocket.send_text(f"\x1b[36m{proto.upper()} → {router['host']}:{port} as {username}…\x1b[0m\r\n")
    if proto == "telnet": await run_telnet(websocket, router, port, username, password)
    else: await run_ssh(websocket, router, port, username, password, cols, rows)
    try: await websocket.close()
    except Exception: pass
