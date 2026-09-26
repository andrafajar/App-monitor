"""Live traffic sampling, scheduled backups and the automatic alarm engine (driven by platform crons)."""
import asyncio, hmac, os, re, uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from core import db
from auth import require, current_workspace

engine_router = APIRouter(prefix="/api")
now = lambda: datetime.now(timezone.utc)
PHYSICAL_PREFIXES = ("ether", "wlan", "wifi", "sfp", "lte", "wireless", "vlan", "bridge")
# Only real ports count towards totals — bridges/VLANs carry the same packets and would double count.
UPLINK_PREFIXES = ("ether", "wlan", "wifi", "sfp", "lte", "wireless")
is_uplink = lambda kind: any(kind.startswith(p) for p in UPLINK_PREFIXES)
ALARM_DEFAULTS = {"enabled": True, "cpu_threshold": 80, "notify_unreachable": True, "notify_interface": True, "throttle_minutes": 60}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class AlarmSettingsIn(BaseModel):
    enabled: bool = True
    cpu_threshold: int = Field(80, ge=20, le=100)
    notify_unreachable: bool = True
    notify_interface: bool = True
    throttle_minutes: int = Field(60, ge=5, le=1440)


class ScheduleIn(BaseModel):
    frequency: str = Field(pattern="^(daily|weekly)$")
    hour: int = Field(ge=0, le=23)
    minute: int = Field(0, ge=0, le=59)
    weekday: int = Field(0, ge=0, le=6)
    enabled: bool = True
    keep: int = Field(10, ge=1, le=100)


class AlarmInterfacesIn(BaseModel):
    mode: str = Field("all", pattern="^(all|ethernet|selected|off)$")
    interfaces: list[str] = Field(default_factory=list, max_length=200)


ETHERNET_PREFIXES = ("ether", "sfp", "combo", "qsfp")


def watched_interfaces(rows: list[dict], router: dict) -> dict[str, bool]:
    """Map interface name -> running, honouring this router's alarm watch mode."""
    mode = router.get("alarm_iface_mode") or "all"
    chosen = set(router.get("alarm_ifaces") or [])
    if mode == "off": return {}
    out = {}
    for row in rows:
        name = row.get("name")
        if not name or row.get("disabled") == "true": continue
        kind = (row.get("type") or "").lower()
        if mode == "ethernet" and not kind.startswith(ETHERNET_PREFIXES): continue
        if mode == "selected" and name not in chosen: continue
        out[name] = row.get("running") == "true"
    return out


# ---------- live interface traffic ----------
def sample_interfaces(router: dict, user_id: str, creds: tuple[str, str]) -> dict[str, dict[str, Any]]:
    from server import ros_call
    out: dict[str, dict[str, Any]] = {}
    for row in ros_call(router, user_id, creds, "/interface"):
        name = row.get("name"); kind = (row.get("type") or "").lower()
        if not name or not any(kind.startswith(p) for p in PHYSICAL_PREFIXES): continue
        out[name] = {"rx": int(row.get("rx-byte") or 0), "tx": int(row.get("tx-byte") or 0), "type": kind,
                     "running": row.get("running"), "disabled": row.get("disabled"), "comment": row.get("comment", "")}
    return out


def bps(prev: int, cur: int, dt: float) -> float | None:
    if dt <= 0.5 or dt > 900 or cur < prev: return None
    return (cur - prev) * 8 / dt


def totals(ifaces: dict) -> tuple[int, int]:
    uplinks = [v for v in ifaces.values() if is_uplink(v["type"])]
    return sum(v["rx"] for v in uplinks), sum(v["tx"] for v in uplinks)


async def store_sample(router_id: str, ifaces: dict, ts: float) -> dict | None:
    prev = await db.traffic_state.find_one({"router_id": router_id}, {"_id": 0})
    rx, tx = totals(ifaces)
    await db.traffic_state.update_one({"router_id": router_id}, {"$set": {"router_id": router_id, "ts": ts, "rx": rx, "tx": tx, "ifaces": ifaces}}, upsert=True)
    return prev


@engine_router.get("/monitoring/traffic")
async def live_traffic(request: Request, user: dict = Depends(require("overview", "read"))):
    from server import router_filter, ros_credentials, user_secret
    ws = await current_workspace(request, user)
    routers = await db.routers.find(router_filter(user, ws), {"_id": 0}).to_list(200)
    secret = await user_secret(user["user_id"])
    stamp = now(); ts = stamp.timestamp()

    async def one(doc):
        try: creds = ros_credentials(doc, user, secret)
        except HTTPException: return {"id": doc["id"], "name": doc["name"], "state": "no-credentials"}
        try: ifaces = await asyncio.to_thread(sample_interfaces, doc, user["user_id"], creds)
        except Exception: return {"id": doc["id"], "name": doc["name"], "state": "unreachable"}
        prev = await store_sample(doc["id"], ifaces, ts)
        rx, tx = totals(ifaces)
        dt = ts - (prev or {}).get("ts", 0)
        if prev and dt >= 3:
            inbound, outbound = bps(prev.get("rx", 0), rx, dt), bps(prev.get("tx", 0), tx, dt)
            if inbound is not None and outbound is not None:
                await db.traffic_state.update_one({"router_id": doc["id"]}, {"$set": {"last_in": inbound, "last_out": outbound}})
        elif prev:  # another sampler just refreshed the counters — reuse the last good rate
            inbound, outbound = prev.get("last_in"), prev.get("last_out")
        else:
            inbound = outbound = None
        ready = inbound is not None and outbound is not None
        return {"id": doc["id"], "name": doc["name"], "state": "ready" if ready else "warming-up",
                "inbound": round((inbound or 0) / 1e6, 2), "outbound": round((outbound or 0) / 1e6, 2), "interfaces": len(ifaces)}

    results = [r for r in await asyncio.gather(*[one(d) for d in routers]) if r]
    ready = [r for r in results if r["state"] == "ready"]
    if ready:
        await db.traffic_series.insert_one({"workspace_id": ws, "ts": stamp.isoformat(),
                                            "inbound": round(sum(r["inbound"] for r in ready), 2), "outbound": round(sum(r["outbound"] for r in ready), 2)})
        await db.traffic_series.delete_many({"workspace_id": ws, "ts": {"$lt": (stamp - timedelta(hours=3)).isoformat()}})
    rows = await db.traffic_series.find({"workspace_id": ws}, {"_id": 0}).sort("ts", -1).to_list(60)
    series = [{"time": datetime.fromisoformat(r["ts"]).strftime("%H:%M:%S"), "inbound": r["inbound"], "outbound": r["outbound"]} for r in reversed(rows)]
    return {"series": series, "per_router": results, "sampled_at": stamp.isoformat(), "live": bool(ready),
            "totals": {"inbound": round(sum(r["inbound"] for r in ready), 2), "outbound": round(sum(r["outbound"] for r in ready), 2)}}


@engine_router.get("/routers/{router_id}/traffic")
async def router_traffic(router_id: str, request: Request, user: dict = Depends(require("routers", "read"))):
    from server import ros_credentials, ros_http_error, user_secret, visible_router
    router = await visible_router(router_id, request, user)
    creds = ros_credentials(router, user, await user_secret(user["user_id"]))
    stamp = now(); ts = stamp.timestamp()
    try: ifaces = await asyncio.to_thread(sample_interfaces, router, user["user_id"], creds)
    except Exception as exc: raise ros_http_error(exc, router, "read")
    prev = await store_sample(router_id, ifaces, ts)
    dt = ts - (prev or {}).get("ts", 0); old = (prev or {}).get("ifaces") or {}
    items = []
    for name, cur in sorted(ifaces.items()):
        before = old.get(name)
        rx = bps(before["rx"], cur["rx"], dt) if before else None
        tx = bps(before["tx"], cur["tx"], dt) if before else None
        items.append({"name": name, "type": cur["type"], "running": cur["running"], "disabled": cur["disabled"], "comment": cur["comment"],
                      "rx_mbps": round((rx or 0) / 1e6, 3), "tx_mbps": round((tx or 0) / 1e6, 3), "ready": rx is not None,
                      "uplink": is_uplink(cur["type"]), "rx_total": cur["rx"], "tx_total": cur["tx"]})
    uplinks = [i for i in items if i["uplink"]]
    return {"router_id": router_id, "sampled_at": stamp.isoformat(), "interval": round(dt, 1) if prev else 0, "items": items,
            "totals": {"rx_mbps": round(sum(i["rx_mbps"] for i in uplinks), 2), "tx_mbps": round(sum(i["tx_mbps"] for i in uplinks), 2)}}


# ---------- alarm settings ----------
async def alarm_settings(ws: str) -> dict:
    doc = await db.alarm_settings.find_one({"workspace_id": ws}, {"_id": 0}) or {}
    return {**ALARM_DEFAULTS, **{k: v for k, v in doc.items() if k in ALARM_DEFAULTS}}


@engine_router.get("/alarms/settings")
async def get_alarm_settings(request: Request, user: dict = Depends(require("alarms", "read"))):
    ws = await current_workspace(request, user)
    doc = await db.alarm_settings.find_one({"workspace_id": ws}, {"_id": 0}) or {}
    return {"settings": await alarm_settings(ws), "last_scan_at": doc.get("last_scan_at"), "last_scan_result": doc.get("last_scan_result")}


@engine_router.put("/alarms/settings")
async def put_alarm_settings(body: AlarmSettingsIn, request: Request, user: dict = Depends(require("alarms", "write"))):
    ws = await current_workspace(request, user)
    await db.alarm_settings.update_one({"workspace_id": ws}, {"$set": {**body.model_dump(), "workspace_id": ws, "updated_at": now().isoformat(), "updated_by": user["email"]}}, upsert=True)
    return {"ok": True, "settings": body.model_dump()}


@engine_router.get("/routers/{router_id}/alarm-interfaces")
async def get_alarm_interfaces(router_id: str, request: Request, user: dict = Depends(require("alarms", "read"))):
    from server import ros_call, ros_credentials, user_secret, visible_router
    router = await visible_router(router_id, request, user)
    available, error = [], None
    try:
        creds = ros_credentials(router, user, await user_secret(user["user_id"]))
        rows = await asyncio.to_thread(ros_call, router, user["user_id"], creds, "/interface")
        available = [{"name": r.get("name"), "type": (r.get("type") or "").lower(), "running": r.get("running") == "true"} for r in rows if r.get("name")]
    except Exception as exc: error = f"{type(exc).__name__}"
    watching = watched_interfaces([{"name": a["name"], "type": a["type"], "running": "true" if a["running"] else "false"} for a in available], router)
    return {"mode": router.get("alarm_iface_mode") or "all", "interfaces": router.get("alarm_ifaces") or [], "available": available, "watching": sorted(watching), "error": error}


@engine_router.put("/routers/{router_id}/alarm-interfaces")
async def put_alarm_interfaces(router_id: str, body: AlarmInterfacesIn, request: Request, user: dict = Depends(require("alarms", "write"))):
    from server import audit, visible_router
    await visible_router(router_id, request, user)
    if body.mode == "selected" and not body.interfaces: raise HTTPException(422, "Pick at least one interface to watch")
    await db.routers.update_one({"id": router_id}, {"$set": {"alarm_iface_mode": body.mode, "alarm_ifaces": body.interfaces if body.mode == "selected" else []}})
    await db.interface_state.delete_one({"router_id": router_id})
    await audit(user, "alarm.interfaces", router_id, f"{body.mode}: {', '.join(body.interfaces[:8]) or 'auto'}")
    return {"ok": True, "mode": body.mode, "interfaces": body.interfaces if body.mode == "selected" else []}


# ---------- reachability check (helps diagnose blocked SSH/Telnet ports) ----------
_OUTBOUND_IP: dict[str, Any] = {}


async def outbound_ip() -> str:
    if _OUTBOUND_IP.get("value") and (now().timestamp() - _OUTBOUND_IP["at"]) < 3600: return _OUTBOUND_IP["value"]
    import httpx
    try:
        async with httpx.AsyncClient(timeout=6) as http:
            value = (await http.get("https://api.ipify.org")).text.strip()
    except Exception: value = "unknown"
    _OUTBOUND_IP.update({"value": value, "at": now().timestamp()})
    return value


async def probe_port(host: str, port: int) -> str:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
        writer.close()
        return "open"
    except asyncio.TimeoutError: return "filtered"
    except ConnectionRefusedError: return "refused"
    except Exception as exc: return f"error:{type(exc).__name__}"


@engine_router.get("/routers/{router_id}/port-check")
async def port_check(router_id: str, request: Request, user: dict = Depends(require("routers", "read"))):
    from server import visible_router
    router = await visible_router(router_id, request, user)
    targets = {"api": int(router.get("port") or 8728), "ssh": int(router.get("ssh_port") or 22), "telnet": int(router.get("telnet_port") or 23), "winbox": 8291}
    results = await asyncio.gather(*[probe_port(router["host"], p) for p in targets.values()])
    return {"host": router["host"], "from_ip": await outbound_ip(),
            "ports": [{"service": name, "port": port, "state": state} for (name, port), state in zip(targets.items(), results)]}


# ---------- backup schedules ----------
def next_run(freq: str, hour: int, minute: int, weekday: int, base: datetime | None = None) -> datetime:
    base = base or now()
    cand = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if freq == "weekly":
        cand += timedelta(days=(weekday - cand.weekday()) % 7)
        if cand <= base: cand += timedelta(days=7)
    elif cand <= base:
        cand += timedelta(days=1)
    return cand


def schedule_public(doc: dict) -> dict:
    return {k: doc.get(k) for k in ("router_id", "frequency", "hour", "minute", "weekday", "enabled", "keep", "next_run_at", "last_run_at", "last_status", "created_by_email")}


@engine_router.get("/routers/{router_id}/backup-schedule")
async def get_schedule(router_id: str, request: Request, user: dict = Depends(require("backups", "read"))):
    from server import visible_router
    await visible_router(router_id, request, user)
    doc = await db.backup_schedules.find_one({"router_id": router_id}, {"_id": 0})
    return {"schedule": schedule_public(doc) if doc else None}


@engine_router.post("/routers/{router_id}/backup-schedule")
async def save_schedule(router_id: str, body: ScheduleIn, request: Request, user: dict = Depends(require("backups", "write"))):
    from server import audit, visible_router
    router = await visible_router(router_id, request, user)
    if not (user.get("is_super_admin") or router.get("created_by") == user["user_id"]):
        raise HTTPException(403, "Only the router owner or a Super Admin can schedule backups (they run with the stored router credentials)")
    doc = {**body.model_dump(), "router_id": router_id, "workspace_id": router["workspace_id"], "created_by": user["user_id"], "created_by_email": user["email"],
           "next_run_at": next_run(body.frequency, body.hour, body.minute, body.weekday).isoformat(), "updated_at": now().isoformat()}
    await db.backup_schedules.update_one({"router_id": router_id}, {"$set": doc}, upsert=True)
    await audit(user, "backup.schedule", router_id, f"{body.frequency} {body.hour:02d}:{body.minute:02d} UTC")
    return {"ok": True, "schedule": schedule_public(doc)}


@engine_router.delete("/routers/{router_id}/backup-schedule")
async def delete_schedule(router_id: str, request: Request, user: dict = Depends(require("backups", "write"))):
    from server import visible_router
    await visible_router(router_id, request, user)
    r = await db.backup_schedules.delete_one({"router_id": router_id})
    if r.deleted_count == 0: raise HTTPException(404, "No schedule for this router")
    return {"ok": True, "router_id": router_id}


async def run_scheduled_backup(schedule: dict) -> str:
    from server import build_rsc, stored_creds
    from storage import put_object, APP_NAME
    router = await db.routers.find_one({"id": schedule["router_id"]}, {"_id": 0})
    if not router:
        await db.backup_schedules.delete_one({"router_id": schedule["router_id"]})
        return "router-removed"
    stamp = now()
    try:
        text, sections = await asyncio.to_thread(build_rsc, router, "scheduler", stored_creds(router))
        if not sections: raise RuntimeError("no sections could be read")
        path = f"{APP_NAME}/backups/{router['workspace_id']}/{router['id']}/{uuid.uuid4().hex}.rsc"
        result = await asyncio.to_thread(put_object, path, text.encode(), "text/plain")
        filename = f"{re.sub(r'[^A-Za-z0-9_-]+', '_', router['name'])}_{stamp.strftime('%Y%m%d-%H%M%S')}_scheduled.rsc"
        await db.backups.insert_one({"id": f"bk-{uuid.uuid4().hex[:8]}", "router_id": router["id"], "router_name": router["name"], "workspace_id": router["workspace_id"],
                                     "filename": filename, "storage_path": result["path"], "size": result.get("size", len(text)), "sections": sections, "kind": "rsc",
                                     "scheduled": True, "created_by": schedule.get("created_by"), "created_by_email": "scheduler", "is_deleted": False, "created_at": stamp.isoformat()})
        keep = int(schedule.get("keep", 10))
        old = await db.backups.find({"router_id": router["id"], "scheduled": True, "is_deleted": False}, {"_id": 0, "id": 1}).sort("created_at", -1).to_list(200)
        for extra in old[keep:]:
            await db.backups.update_one({"id": extra["id"]}, {"$set": {"is_deleted": True, "deleted_at": stamp.isoformat()}})
        status = f"ok · {len(sections)} sections"
    except Exception as exc:
        status = f"failed · {type(exc).__name__}: {str(exc)[:90]}"
    await db.backup_schedules.update_one({"router_id": schedule["router_id"]}, {"$set": {
        "last_run_at": stamp.isoformat(), "last_status": status,
        "next_run_at": next_run(schedule["frequency"], schedule["hour"], schedule.get("minute", 0), schedule.get("weekday", 0), stamp).isoformat()}})
    return status


async def scan_backups() -> dict:
    due = await db.backup_schedules.find({"enabled": True, "next_run_at": {"$lte": now().isoformat()}}, {"_id": 0}).to_list(100)
    results = [await run_scheduled_backup(s) for s in due]
    return {"due": len(due), "results": results}


# ---------- automatic alarm engine ----------
async def recently_fired(router_id: str, kind: str, minutes: int) -> bool:
    cutoff = (now() - timedelta(minutes=minutes)).isoformat()
    return bool(await db.alarm_log.find_one({"router_id": router_id, "kind": kind, "created_at": {"$gt": cutoff}}))


async def scan_router(router: dict, settings: dict) -> list[str]:
    from server import deliver_alarm, probe_router, ros_call, stored_creds
    fired: list[str] = []
    creds = stored_creds(router)
    probe = await asyncio.to_thread(probe_router, router, creds, "scheduler")
    previous = router.get("status")
    await db.routers.update_one({"id": router["id"]}, {"$set": {**{k: v for k, v in probe.items() if k != "error"}, "last_probed_at": now().isoformat()}})
    if probe["status"] != "online":
        if settings["notify_unreachable"] and (previous != "offline" or not await recently_fired(router["id"], "router-unreachable", settings["throttle_minutes"])):
            await deliver_alarm(router, "router-unreachable", f"RouterOS API on {router['host']} did not answer: {probe.get('error', 'connection failed')[:120]}")
            fired.append("router-unreachable")
        return fired
    if probe.get("cpu", 0) >= settings["cpu_threshold"] and not await recently_fired(router["id"], "cpu-threshold", settings["throttle_minutes"]):
        await deliver_alarm(router, "cpu-threshold", f"CPU load {probe['cpu']}% is at or above the {settings['cpu_threshold']}% threshold (memory {probe.get('memory', 0)}%)")
        fired.append("cpu-threshold")
    if settings["notify_interface"]:
        try: rows = await asyncio.to_thread(ros_call, router, "scheduler", creds, "/interface")
        except Exception: return fired
        current = watched_interfaces(rows, router)
        if not current: return fired
        snapshot = await db.interface_state.find_one({"router_id": router["id"]}, {"_id": 0})
        await db.interface_state.update_one({"router_id": router["id"]}, {"$set": {"router_id": router["id"], "state": current, "updated_at": now().isoformat()}}, upsert=True)
        previous_state = (snapshot or {}).get("state") or {}
        changes = [f"{name} is {'up' if up else 'down'}" for name, up in current.items() if name in previous_state and previous_state[name] != up]
        if changes and not await recently_fired(router["id"], "interface-status", max(5, settings["throttle_minutes"] // 4)):
            await deliver_alarm(router, "interface-status", ", ".join(changes[:6]))
            fired.append("interface-status")
    return fired


async def scan_alarms() -> dict:
    routers = await db.routers.find({"password_enc": {"$exists": True}}, {"_id": 0}).to_list(500)
    cache: dict[str, dict] = {}
    checked = 0; fired: list[str] = []
    for router in routers:
        ws = router.get("workspace_id")
        if ws not in cache: cache[ws] = await alarm_settings(ws)
        settings = cache[ws]
        if not settings["enabled"]: continue
        checked += 1
        try: fired.extend(f"{router['name']}:{k}" for k in await scan_router(router, settings))
        except Exception as exc: fired.append(f"{router['name']}:scan-error({type(exc).__name__})")
    stamp = now().isoformat()
    for ws in cache:
        await db.alarm_settings.update_one({"workspace_id": ws}, {"$set": {"workspace_id": ws, "last_scan_at": stamp, "last_scan_result": f"{checked} routers checked · {len(fired)} alarms"}}, upsert=True)
    return {"routers_checked": checked, "alarms": fired}


# ---------- cron webhooks ----------
def verify_cron(authorization: str | None):
    secret = os.environ.get("WEBHOOK_CRON_SECRET")
    if not secret: raise HTTPException(503, "WEBHOOK_CRON_SECRET is not configured")
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401, "Unauthorized")
    if not hmac.compare_digest(authorization[7:], secret): raise HTTPException(401, "Unauthorized")


_CRON_TASKS: set = set()


async def cron_ack(name: str, payload: dict | None, authorization: str | None, x_webhook_id: str | None, worker):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    verify_cron(authorization)
    run_id = x_webhook_id or (payload or {}).get("run_id") or uuid.uuid4().hex
    existing = await db.cron_runs.find_one({"run_id": run_id})
    if existing: return {"ok": True, "duplicate": True, "run_id": run_id}
    await db.cron_runs.insert_one({"run_id": run_id, "job": name, "accepted_at": now().isoformat()})

    async def job():
        try: result = await worker()
        except Exception as exc: result = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        await db.cron_runs.update_one({"run_id": run_id}, {"$set": {"finished_at": now().isoformat(), "result": result}})
    task = asyncio.create_task(job())
    _CRON_TASKS.add(task)
    task.add_done_callback(_CRON_TASKS.discard)
    return {"ok": True, "accepted": True, "job": name, "run_id": run_id}


@engine_router.post("/cron/alarm-scan")
async def cron_alarm_scan(payload: dict | None = Body(default=None), authorization: str | None = Header(default=None), x_webhook_id: str | None = Header(default=None)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    return await cron_ack("alarm-scan", payload, authorization, x_webhook_id, scan_alarms)


@engine_router.post("/cron/backup-scan")
async def cron_backup_scan(payload: dict | None = Body(default=None), authorization: str | None = Header(default=None), x_webhook_id: str | None = Header(default=None)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    return await cron_ack("backup-scan", payload, authorization, x_webhook_id, scan_backups)


@engine_router.get("/cron/runs")
async def cron_runs(user: dict = Depends(require("audit", "read"))):
    return {"items": await db.cron_runs.find({}, {"_id": 0}).sort("accepted_at", -1).to_list(30)}
