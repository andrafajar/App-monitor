"""Vendor-agnostic monitoring: ICMP ping + SNMP v2c polling with 30-day retention (driven by platform crons)."""
import asyncio, inspect
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from core import db, credential_box
from auth import require, current_workspace

monitor_router = APIRouter(prefix="/api")
now = lambda: datetime.now(timezone.utc)
DEVICE_TYPES = ("mikrotik", "huawei", "juniper", "cisco", "other")
VENDOR_LABELS = {"mikrotik": "MikroTik", "huawei": "Huawei", "juniper": "Juniper", "cisco": "Cisco", "other": "Other"}
RETENTION_DAYS = 30
SYS_OIDS = {"descr": "1.3.6.1.2.1.1.1.0", "uptime": "1.3.6.1.2.1.1.3.0", "name": "1.3.6.1.2.1.1.5.0"}
WALK_OIDS = {"name": "1.3.6.1.2.1.2.2.1.2", "status": "1.3.6.1.2.1.2.2.1.8", "alias": "1.3.6.1.2.1.31.1.1.1.18",
             "in64": "1.3.6.1.2.1.31.1.1.1.6", "out64": "1.3.6.1.2.1.31.1.1.1.10",
             "in32": "1.3.6.1.2.1.2.2.1.10", "out32": "1.3.6.1.2.1.2.2.1.16"}
CPU_OID = "1.3.6.1.2.1.25.3.3.1.2"  # hrProcessorLoad — MikroTik, Cisco IOS-XE, Huawei VRP and Junos all answer this
ETHER_HINTS = ("ether", "gigabit", "ge-", "xe-", "et-", "fastethernet", "gi", "te", "sfp", "eth")


class SnmpIn(BaseModel):
    enabled: bool = True
    community: str | None = Field(default=None, max_length=64)
    port: int = Field(161, ge=1, le=65535)


# ---------- SNMP v2c ----------
def community_of(device: dict) -> str | None:
    enc = device.get("snmp_community_enc")
    if not enc: return None
    try: return credential_box().decrypt(enc.encode()).decode()
    except Exception: return None


async def _target(host: str, port: int):
    from pysnmp.hlapi.v3arch.asyncio import UdpTransportTarget
    maker = getattr(UdpTransportTarget, "create", None)
    if maker:
        made = maker((host, port), timeout=2, retries=1)
        return await made if inspect.isawaitable(made) else made
    return UdpTransportTarget((host, port), timeout=2, retries=1)


async def snmp_get(host: str, port: int, community: str, oids: dict[str, str]) -> dict[str, str]:
    from pysnmp.hlapi.v3arch.asyncio import ContextData, CommunityData, ObjectIdentity, ObjectType, SnmpEngine, get_cmd
    keys = list(oids)
    error, status, _, var_binds = await get_cmd(SnmpEngine(), CommunityData(community, mpModel=1), await _target(host, port), ContextData(),
                                                *[ObjectType(ObjectIdentity(oids[k])) for k in keys])
    if error: raise RuntimeError(str(error))
    if status: raise RuntimeError(f"SNMP error status {status.prettyPrint()}")
    return {k: str(vb[1].prettyPrint()) for k, vb in zip(keys, var_binds)}


async def snmp_walk(host: str, port: int, community: str, root: str) -> dict[str, str]:
    from pysnmp.hlapi.v3arch.asyncio import ContextData, CommunityData, ObjectIdentity, ObjectType, SnmpEngine, bulk_walk_cmd
    out: dict[str, str] = {}
    async for error, status, _, var_binds in bulk_walk_cmd(SnmpEngine(), CommunityData(community, mpModel=1), await _target(host, port), ContextData(),
                                                           0, 25, ObjectType(ObjectIdentity(root)), lexicographicMode=False):
        if error: raise RuntimeError(str(error))
        if status: raise RuntimeError(f"SNMP error status {status.prettyPrint()}")
        for oid, value in var_binds:
            text = str(oid)
            if not text.startswith(root): return out
            out[text[len(root) + 1:]] = value.prettyPrint()
    return out


def as_int(value: str | None) -> int:
    try: return int(str(value).strip())
    except (TypeError, ValueError): return 0


def rate_mbps(prev: int, cur: int, seconds: float) -> float | None:
    if seconds <= 1 or seconds > 900 or cur < prev: return None
    return round((cur - prev) * 8 / seconds / 1e6, 3)


def iface_kind(name: str) -> str:
    low = name.lower()
    return "ether" if any(low.startswith(h) or h in low for h in ETHER_HINTS) else "other"


def pretty_uptime(ticks: str) -> str:
    seconds = as_int(str(ticks).split(".")[0]) // 100
    if seconds <= 0: return str(ticks)[:40]
    d, rest = divmod(seconds, 86400); h, rest = divmod(rest, 3600); m = rest // 60
    return (f"{d}d " if d else "") + f"{h}h {m}m"


async def poll_snmp(device: dict) -> dict:
    """One SNMP v2c sweep: system info, CPU load and per-interface status/throughput."""
    community = community_of(device)
    if not device.get("snmp_enabled") or not community: return {"error": "SNMP is not configured for this device"}
    host, port = device["host"], int(device.get("snmp_port") or 161)
    try:
        system = await snmp_get(host, port, community, SYS_OIDS)
        names = await snmp_walk(host, port, community, WALK_OIDS["name"])
        status = await snmp_walk(host, port, community, WALK_OIDS["status"])
        inbound = await snmp_walk(host, port, community, WALK_OIDS["in64"]) or await snmp_walk(host, port, community, WALK_OIDS["in32"])
        outbound = await snmp_walk(host, port, community, WALK_OIDS["out64"]) or await snmp_walk(host, port, community, WALK_OIDS["out32"])
        cpu_rows = await snmp_walk(host, port, community, CPU_OID)
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {str(exc)[:140]}", "polled_at": now().isoformat()}
        await db.snmp_state.update_one({"device_id": device["id"]}, {"$set": {"device_id": device["id"], **result}}, upsert=True)
        return result

    loads = [as_int(v) for v in cpu_rows.values() if as_int(v) >= 0]
    cpu = int(round(sum(loads) / len(loads))) if loads else 0
    prev = await db.snmp_state.find_one({"device_id": device["id"]}, {"_id": 0}) or {}
    prev_counters = prev.get("counters") or {}
    stamp = now(); elapsed = stamp.timestamp() - float(prev.get("ts") or 0)
    interfaces, counters = [], {}
    for index, name in sorted(names.items(), key=lambda kv: as_int(kv[0])):
        rx, tx = as_int(inbound.get(index)), as_int(outbound.get(index))
        counters[index] = {"rx": rx, "tx": tx}
        before = prev_counters.get(index) or {}
        interfaces.append({"index": index, "name": name, "status": "up" if status.get(index) == "up" or as_int(status.get(index)) == 1 else "down",
                           "rx_mbps": rate_mbps(before.get("rx", 0), rx, elapsed) if before else None,
                           "tx_mbps": rate_mbps(before.get("tx", 0), tx, elapsed) if before else None,
                           "rx_total": rx, "tx_total": tx})
    state = {"device_id": device["id"], "ts": stamp.timestamp(), "polled_at": stamp.isoformat(), "counters": counters,
             "sysname": system.get("name", ""), "sysdescr": system.get("descr", "")[:160], "uptime": pretty_uptime(system.get("uptime", "")),
             "cpu": cpu, "interfaces": interfaces, "error": None}
    await db.snmp_state.update_one({"device_id": device["id"]}, {"$set": state}, upsert=True)
    return {k: v for k, v in state.items() if k != "counters"}


# ---------- ICMP ----------
async def tcp_reachable(host: str) -> dict:
    """Last-resort reachability when ICMP sockets are unavailable: touch the common management ports."""
    async def touch(port: int) -> bool:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2)
            writer.close()
            return True
        except Exception: return False
    for port in (22, 23, 161, 443, 80, 8728):
        if await touch(port): return {"alive": True, "rtt_ms": None, "loss": 0, "method": f"tcp/{port}"}
    return {"alive": False, "rtt_ms": None, "loss": 100, "method": "tcp"}


async def ping_device(host: str) -> dict:
    from icmplib import async_ping
    for privileged in (False, True):  # unprivileged ICMP datagram sockets first — containers rarely hold CAP_NET_RAW
        try:
            result = await async_ping(host, count=2, interval=0.3, timeout=1, privileged=privileged)
            return {"alive": result.is_alive, "rtt_ms": round(result.avg_rtt, 2) if result.is_alive else None, "loss": round(result.packet_loss * 100), "method": "icmp"}
        except Exception: continue
    return await tcp_reachable(host)


# ---------- scan (cron: every minute) ----------
async def ensure_indexes():
    await db.device_metrics.create_index("created_at", expireAfterSeconds=RETENTION_DAYS * 86400)
    await db.device_metrics.create_index([("device_id", 1), ("created_at", -1)])


async def monitor_device(device: dict, settings: dict) -> list[str]:
    from engine import recently_fired, watched_interfaces
    from server import deliver_alarm
    vendor = device.get("device_type") or "mikrotik"
    fired: list[str] = []
    ping = await ping_device(device["host"])
    snmp = await poll_snmp(device) if device.get("snmp_enabled") else {}
    update = {"ping_ms": ping.get("rtt_ms"), "ping_loss": ping.get("loss"), "reachable": ping["alive"], "last_ping_at": now().isoformat()}
    if vendor != "mikrotik":  # MikroTik health comes from the RouterOS API scan; other vendors rely on ping + SNMP
        update["status"] = "online" if ping["alive"] else "offline"
        if not snmp.get("error") and snmp:
            update.update({"cpu": snmp.get("cpu", 0), "uptime": snmp.get("uptime", "—"), "version": (snmp.get("sysdescr") or "—")[:60],
                           "interfaces": len(snmp.get("interfaces") or [])})
    await db.routers.update_one({"id": device["id"]}, {"$set": update})
    await db.device_metrics.insert_one({"device_id": device["id"], "workspace_id": device.get("workspace_id"), "created_at": now(),
                                        "ping_ms": ping.get("rtt_ms"), "loss": ping.get("loss"), "cpu": snmp.get("cpu"),
                                        "rx_mbps": round(sum(i["rx_mbps"] or 0 for i in snmp.get("interfaces") or []), 2) if snmp.get("interfaces") else None,
                                        "tx_mbps": round(sum(i["tx_mbps"] or 0 for i in snmp.get("interfaces") or []), 2) if snmp.get("interfaces") else None})
    if not settings.get("enabled"): return fired
    if vendor != "mikrotik" and not ping["alive"] and settings.get("notify_unreachable"):
        if not await recently_fired(device["id"], "router-unreachable", settings["throttle_minutes"]):
            await deliver_alarm(device, "router-unreachable", f"{VENDOR_LABELS.get(vendor, vendor)} device {device['host']} does not answer ICMP ping (100% loss)")
            fired.append("router-unreachable")
        return fired
    if vendor != "mikrotik" and settings.get("notify_interface") and snmp.get("interfaces"):
        rows = [{"name": i["name"], "type": iface_kind(i["name"]), "running": "true" if i["status"] == "up" else "false"} for i in snmp["interfaces"]]
        current = watched_interfaces(rows, device)
        if current:
            snapshot = await db.interface_state.find_one({"router_id": device["id"]}, {"_id": 0})
            await db.interface_state.update_one({"router_id": device["id"]}, {"$set": {"router_id": device["id"], "state": current, "updated_at": now().isoformat()}}, upsert=True)
            before = (snapshot or {}).get("state") or {}
            changes = [f"{name} is {'up' if up else 'down'}" for name, up in current.items() if name in before and before[name] != up]
            if changes and not await recently_fired(device["id"], "interface-status", max(5, settings["throttle_minutes"] // 4)):
                await deliver_alarm(device, "interface-status", ", ".join(changes[:6]) + " (SNMP)")
                fired.append("interface-status")
    return fired


async def purge_history() -> dict:
    cutoff = now() - timedelta(days=RETENTION_DAYS)
    metrics = await db.device_metrics.delete_many({"created_at": {"$lt": cutoff}})
    logs = await db.syslog_events.delete_many({"created_at": {"$lt": cutoff.isoformat()}})
    alarms = await db.alarm_log.delete_many({"created_at": {"$lt": cutoff.isoformat()}})
    return {"metrics": metrics.deleted_count, "syslog": logs.deleted_count, "alarms": alarms.deleted_count}


async def scan_monitor() -> dict:
    from engine import alarm_settings
    devices = await db.routers.find({}, {"_id": 0}).to_list(500)
    cache: dict[str, dict] = {}
    fired: list[str] = []
    for device in devices:
        ws = device.get("workspace_id")
        if ws not in cache: cache[ws] = await alarm_settings(ws)
        try: fired.extend(f"{device['name']}:{k}" for k in await monitor_device(device, cache[ws]))
        except Exception as exc: fired.append(f"{device['name']}:monitor-error({type(exc).__name__})")
    return {"devices": len(devices), "alarms": fired, "retention": await purge_history()}


# ---------- API ----------
async def visible_device(device_id: str, request: Request, user: dict) -> dict:
    from server import visible_router
    return await visible_router(device_id, request, user)


def snmp_public(device: dict) -> dict:
    return {"enabled": bool(device.get("snmp_enabled")), "port": int(device.get("snmp_port") or 161),
            "configured": bool(device.get("snmp_community_enc")), "version": "2c"}


@monitor_router.get("/devices/{device_id}/snmp")
async def get_snmp(device_id: str, request: Request, user: dict = Depends(require("routers", "read"))):
    device = await visible_device(device_id, request, user)
    state = await db.snmp_state.find_one({"device_id": device_id}, {"_id": 0, "counters": 0}) or {}
    return {"device_id": device_id, "device_type": device.get("device_type") or "mikrotik", "config": snmp_public(device),
            "ping": {"ms": device.get("ping_ms"), "loss": device.get("ping_loss"), "at": device.get("last_ping_at")}, "snmp": state}


@monitor_router.put("/devices/{device_id}/snmp")
async def put_snmp(device_id: str, body: SnmpIn, request: Request, user: dict = Depends(require("routers", "write"))):
    from server import audit
    device = await visible_device(device_id, request, user)
    update = {"snmp_enabled": body.enabled, "snmp_port": body.port}
    if body.community: update["snmp_community_enc"] = credential_box().encrypt(body.community.encode()).decode()
    if body.enabled and not body.community and not device.get("snmp_community_enc"): raise HTTPException(422, "A community string is required to enable SNMP")
    await db.routers.update_one({"id": device_id}, {"$set": update})
    await audit(user, "device.snmp", device_id, f"{'enabled' if body.enabled else 'disabled'} v2c udp/{body.port}")
    return {"ok": True, "config": snmp_public({**device, **update})}


@monitor_router.post("/devices/{device_id}/snmp/scan")
async def scan_snmp(device_id: str, request: Request, user: dict = Depends(require("routers", "read"))):
    device = await visible_device(device_id, request, user)
    ping = await ping_device(device["host"])
    snmp = await poll_snmp(device)
    await db.routers.update_one({"id": device_id}, {"$set": {"ping_ms": ping.get("rtt_ms"), "ping_loss": ping.get("loss"), "reachable": ping["alive"], "last_ping_at": now().isoformat()}})
    return {"ok": not snmp.get("error"), "ping": ping, "snmp": snmp}


@monitor_router.get("/devices/{device_id}/metrics")
async def device_metrics(device_id: str, request: Request, user: dict = Depends(require("routers", "read"))):
    await visible_device(device_id, request, user)
    rows = await db.device_metrics.find({"device_id": device_id}, {"_id": 0}).sort("created_at", -1).to_list(120)
    return {"items": [{**r, "created_at": r["created_at"].isoformat() if isinstance(r.get("created_at"), datetime) else r.get("created_at")} for r in reversed(rows)],
            "retention_days": RETENTION_DAYS}


@monitor_router.get("/monitor/status")
async def monitor_status(request: Request, user: dict = Depends(require("overview", "read"))):
    from server import router_filter
    ws = await current_workspace(request, user)
    devices = await db.routers.find(router_filter(user, ws), {"_id": 0}).to_list(500)
    states = {s["device_id"]: s for s in await db.snmp_state.find({}, {"_id": 0, "counters": 0}).to_list(500)}
    return {"retention_days": RETENTION_DAYS, "items": [{
        "id": d["id"], "name": d["name"], "device_type": d.get("device_type") or "mikrotik", "status": d.get("status", "pending"),
        "ping_ms": d.get("ping_ms"), "ping_loss": d.get("ping_loss"), "snmp_enabled": bool(d.get("snmp_enabled")),
        "snmp_error": (states.get(d["id"]) or {}).get("error"), "snmp_interfaces": len((states.get(d["id"]) or {}).get("interfaces") or []),
        "cpu": d.get("cpu", 0), "last_ping_at": d.get("last_ping_at")} for d in devices]}


@monitor_router.post("/cron/monitor-scan")
async def cron_monitor_scan(payload: dict | None = Body(default=None), authorization: str | None = Header(default=None), x_webhook_id: str | None = Header(default=None)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    from engine import cron_ack
    return await cron_ack("monitor-scan", payload, authorization, x_webhook_id, scan_monitor)
