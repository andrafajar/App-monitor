"""Real RouterOS SSH terminal bridged to the browser over a WebSocket (xterm.js on the frontend)."""
import asyncio, json, socket
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from core import db, level_of

ssh_router = APIRouter(prefix="/api")
RED = "\r\n\x1b[31m{}\x1b[0m\r\n"


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


@ssh_router.websocket("/routers/{router_id}/ssh")
async def ssh_terminal(websocket: WebSocket, router_id: str, token: str = Query(""), cols: int = Query(110, ge=20, le=500), rows: int = Query(30, ge=5, le=200)):
    await websocket.accept()
    user, router, error = await _authorize(token, router_id)
    if error:
        await websocket.send_text(RED.format(error)); await websocket.close(); return
    from server import ros_credentials, user_secret
    try: username, password = ros_credentials(router, user, await user_secret(user["user_id"]))
    except Exception:
        await websocket.send_text(RED.format("Set your own MikroTik credentials in My settings before opening a shared router")); await websocket.close(); return
    port = int(router.get("ssh_port") or 22)
    await websocket.send_text(f"\x1b[36mConnecting to {router['host']}:{port} as {username}…\x1b[0m\r\n")
    try: client, chan = await asyncio.to_thread(_open_shell, router["host"], port, username, password, cols, rows)
    except Exception as exc:
        await websocket.send_text(RED.format(f"SSH connection failed ({type(exc).__name__}): {str(exc)[:160]}"))
        await websocket.send_text("\x1b[33mCheck that /ip service ssh is enabled, the SSH port is correct and your MikroTik user has the ssh policy.\x1b[0m\r\n")
        await websocket.close(); return

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
    except (WebSocketDisconnect, RuntimeError): pass
    except Exception: pass
    finally:
        task.cancel()
        for close in (chan.close, client.close):
            try: close()
            except Exception: pass
        try: await websocket.close()
        except Exception: pass
