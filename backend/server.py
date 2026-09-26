from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import asyncio, os, re, html, secrets, threading, time
from cryptography.fernet import Fernet
import httpx

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="NetPulse MikroTik Control Plane")
api = APIRouter(prefix="/api")

DEMO = {"routers": [
    {"id":"r-01","name":"HQ Core Router","host":"10.10.0.1","group":"Head Office","status":"online","cpu":28,"memory":42,"uptime":"21d 04h 18m","interfaces":14,"traffic":"842 Mbps","version":"7.14.3","color":"cyan"},
    {"id":"r-02","name":"East Branch","host":"10.21.0.1","group":"Region East","status":"online","cpu":64,"memory":71,"uptime":"8d 12h 09m","interfaces":8,"traffic":"318 Mbps","version":"7.13.5","color":"green"},
    {"id":"r-03","name":"Warehouse Gateway","host":"10.30.0.1","group":"Operations","status":"warning","cpu":83,"memory":77,"uptime":"3d 07h 44m","interfaces":11,"traffic":"1.24 Gbps","version":"7.12.1","color":"amber"},
    {"id":"r-04","name":"Partner PT ABC","host":"172.16.20.1","group":"Partner · PT ABC","status":"offline","cpu":0,"memory":0,"uptime":"—","interfaces":6,"traffic":"—","version":"7.11.2","color":"red"}],
    "groups": ["All routers", "Head Office", "Region East", "Operations", "Partner · PT ABC"],
    "traffic": [{"time":f"{i+8:02d}:00","inbound":v+12,"outbound":max(8,v-3)} for i,v in enumerate([0,28,21,44,36,58,45,66,52,73,62,81])]}

RESOURCE_PATHS = {
    "interfaces": "/interface",
    "addresses": "/ip/address", "arp": "/ip/arp",
    "dhcp-server": "/ip/dhcp-server", "dhcp-leases": "/ip/dhcp-server/lease",
    "firewall": "/ip/firewall/filter", "routes": "/ip/route",
    "ppp-profiles": "/ppp/profile", "ppp-secrets": "/ppp/secret",
    "queues": "/queue/simple",
    "wireless-registration": "/interface/wireless/registration-table",
    "logs": "/log",
    "system-clock": "/system/clock", "system-resource": "/system/resource",
    "system-identity": "/system/identity", "system-health": "/system/health",
}
PPP_SECRET_SENSITIVE = ("password", "caller-id", "last-caller-id")
REDACTED_PLACEHOLDER = "••••••"
ACTION_MAP = {"interface-disable": ("/interface", "set", "disabled", "yes"), "interface-enable": ("/interface", "set", "disabled", "no"), "firewall-disable": ("/ip/firewall/filter", "set", "disabled", "yes"), "firewall-enable": ("/ip/firewall/filter", "set", "disabled", "no")}

class RouterCreate(BaseModel):
    name: str = Field(min_length=2); host: str; port: int = Field(8728, ge=1, le=65535); username: str; password: str
    group: str = "Unassigned"; telegram_chat_id: str | None = None
class ActionRequest(BaseModel):
    item_id: str = Field(pattern=r"^\*[A-Za-z0-9]+$")
class ScheduleRequest(BaseModel):
    frequency: str = Field(pattern="^(daily|weekly|monthly)$"); hour: int = Field(ge=0, le=23); minute: int = Field(ge=0, le=59)
class TelegramConfigIn(BaseModel):
    bot_token: str = Field(min_length=20, max_length=200, pattern=r"^\d+:[A-Za-z0-9_\-]+$")
    chat_id: str = Field(min_length=1, max_length=40, pattern=r"^-?\d+$")
    enabled: bool = True
class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
class AlarmDispatch(BaseModel):
    kind: str = Field(pattern="^(cpu-threshold|interface-status|router-unreachable|test)$")
    group: str = Field(min_length=1); router_name: str = Field(min_length=1); detail: str = Field(default="", max_length=280)

def safe_name(value: str) -> str: return re.sub(r"[^A-Za-z0-9_-]+", "_", value)
def credential_box() -> Fernet:
    key = os.environ.get("CREDENTIALS_FERNET_KEY")
    if not key: raise HTTPException(503, "CREDENTIALS_FERNET_KEY is not configured")
    return Fernet(key.encode())

async def router_doc(router_id: str) -> dict[str, Any]:
    doc = await db.routers.find_one({"id": router_id}, {"_id": 0, "password": 0})
    if not doc: raise HTTPException(404, "Router not found in managed inventory")
    return doc

_ROS_POOLS: dict[str, dict[str, Any]] = {}
_ROS_LOCK = threading.Lock()

def _new_pool(router: dict):
    import routeros_api
    password = credential_box().decrypt(router["password_enc"].encode()).decode()
    port = router.get("port", 8728)
    pool = routeros_api.RouterOsApiPool(router["host"], username=router["username"], password=password, port=port, use_ssl=port == 8729, plaintext_login=port != 8729)
    pool.socket_timeout = 8
    return pool

def _drop_pool(router_id: str):
    with _ROS_LOCK:
        entry = _ROS_POOLS.pop(router_id, None)
    if entry:
        try: entry["pool"].disconnect()
        except Exception: pass

def _get_pool_entry(router: dict):
    rid = router["id"]
    with _ROS_LOCK:
        entry = _ROS_POOLS.get(rid)
        if entry: return entry
    try:
        import routeros_api  # noqa: F401
    except ImportError:
        raise RuntimeError("RouterOS client is not installed")
    pool = _new_pool(router)
    api_client = pool.get_api()
    entry = {"pool": pool, "api": api_client, "connected_at": time.time(), "last_used": time.time()}
    with _ROS_LOCK: _ROS_POOLS[rid] = entry
    return entry

def ros_call(router: dict, path: str, command: str = "print", params: dict | None = None):
    last_exc: Exception | None = None
    for attempt in (1, 2):
        try:
            entry = _get_pool_entry(router)
            result = entry["api"].get_resource(path).call(command, params or {})
            entry["last_used"] = time.time()
            return result
        except Exception as exc:
            last_exc = exc
            _drop_pool(router["id"])
    raise last_exc if last_exc else RuntimeError("RouterOS call failed")

def probe_router(router: dict) -> dict[str, Any]:
    """Attempt a lightweight /system/resource print. Returns dict with status + optional metrics."""
    try:
        rows = ros_call(router, "/system/resource")
        row = rows[0] if rows else {}
        free = int(row.get("free-memory", 0) or 0); total = int(row.get("total-memory", 0) or 0)
        memory_pct = int(round((total - free) * 100 / total)) if total else 0
        return {"status": "online", "cpu": int(row.get("cpu-load", 0) or 0), "memory": memory_pct, "uptime": row.get("uptime", "—"), "version": row.get("version", "—")}
    except Exception as exc:
        return {"status": "offline", "error": sanitize_error(exc, router)}

MANAGED_PUBLIC_FIELDS = ("id", "name", "host", "port", "group", "status", "cpu", "memory", "uptime", "version", "traffic", "interfaces", "color", "created_at", "last_probed_at")

def sanitize_router(doc: dict) -> dict:
    return {k: doc[k] for k in MANAGED_PUBLIC_FIELDS if k in doc}

@api.get("/")
async def root(): return {"message": "NetPulse API online"}

@api.get("/monitoring/overview")
async def overview():
    managed = await db.routers.find({}, {"_id": 0}).to_list(500)
    managed_public = []
    for m in managed:
        row = sanitize_router(m)
        row.setdefault("status", "managed"); row.setdefault("cpu", 0); row.setdefault("memory", 0)
        row.setdefault("uptime", "—"); row.setdefault("interfaces", 0); row.setdefault("traffic", "—")
        row.setdefault("version", "—"); row.setdefault("color", "cyan")
        managed_public.append(row)
    groups = list(DEMO["groups"])
    custom = [g["name"] for g in await db.groups.find({}, {"_id": 0, "name": 1}).to_list(200)]
    for name in [*custom, *[m.get("group") for m in managed_public]]:
        if name and name not in groups: groups.append(name)
    return {"routers": [*DEMO["routers"], *managed_public], "groups": groups, "custom_groups": custom, "traffic": DEMO["traffic"]}

@api.post("/groups")
async def create_group(item: GroupCreate):
    name = item.name.strip()
    existing = await db.groups.find_one({"name": name})
    if existing or name in DEMO["groups"]: raise HTTPException(409, "Group already exists")
    await db.groups.insert_one({"name": name, "created_at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "group": name}

@api.delete("/groups/{name}")
async def delete_group(name: str):
    if name in DEMO["groups"]: raise HTTPException(400, "Built-in groups cannot be removed")
    if await db.routers.count_documents({"group": name}) > 0: raise HTTPException(409, "Move or remove routers from this group first")
    result = await db.groups.delete_one({"name": name})
    if result.deleted_count == 0: raise HTTPException(404, "Group not found")
    await db.telegram_configs.delete_many({"group": name})
    return {"ok": True, "group": name}

@api.get("/routers")
async def list_routers():
    docs = await db.routers.find({}, {"_id": 0}).to_list(500)
    return {"items": [sanitize_router(d) for d in docs]}

@api.post("/monitoring/probe-all")
async def probe_all():
    docs = await db.routers.find({}).to_list(500)
    async def one(doc):
        probe = await asyncio.to_thread(probe_router, doc)
        await db.routers.update_one({"id": doc["id"]}, {"$set": {**{k: v for k, v in probe.items() if k != "error"}, "last_probed_at": datetime.now(timezone.utc).isoformat()}})
        return {"id": doc["id"], "status": probe.get("status")}
    results = await asyncio.gather(*[one(d) for d in docs], return_exceptions=True)
    return {"ok": True, "count": len(docs), "results": [r for r in results if not isinstance(r, Exception)]}

@api.get("/health")
async def health():
    try: await db.command("ping"); state = "connected"
    except Exception: state = "unavailable"
    return {"ok": True, "database": state, "timestamp": datetime.now(timezone.utc).isoformat()}

@api.post("/routers")
async def create_router(item: RouterCreate):
    # Live credentials are accepted only by the server and never returned to the browser.
    doc = item.model_dump(); password = doc.pop("password")
    doc["id"] = f"mr-{secrets.token_hex(4)}"
    doc["password_enc"] = credential_box().encrypt(password.encode()).decode()
    doc["created_at"] = datetime.now(timezone.utc).isoformat(); doc["status"] = "pending"
    probe = await asyncio.to_thread(probe_router, doc)
    doc.update({k: v for k, v in probe.items() if k != "error"})
    doc["last_probed_at"] = datetime.now(timezone.utc).isoformat()
    await db.routers.insert_one(doc)
    return {"ok": True, "message": "Router onboarded", "router": sanitize_router(doc), "probe": {"status": probe.get("status"), "error": probe.get("error")}}

@api.post("/routers/{router_id}/test-connection")
async def test_connection(router_id: str):
    router = await router_doc(router_id)
    probe = await asyncio.to_thread(probe_router, router)
    update = {k: v for k, v in probe.items() if k != "error"}
    update["last_probed_at"] = datetime.now(timezone.utc).isoformat()
    await db.routers.update_one({"id": router_id}, {"$set": update})
    return {"ok": True, "status": probe.get("status"), "error": probe.get("error"), "cpu": probe.get("cpu"), "uptime": probe.get("uptime"), "version": probe.get("version")}

@api.post("/routers/{router_id}/disconnect")
async def disconnect_router(router_id: str):
    await router_doc(router_id)
    await asyncio.to_thread(_drop_pool, router_id)
    return {"ok": True, "id": router_id, "connected": False}

@api.get("/routers/{router_id}/connection")
async def connection_state(router_id: str):
    await router_doc(router_id)
    with _ROS_LOCK: entry = _ROS_POOLS.get(router_id)
    if not entry: return {"connected": False}
    return {"connected": True, "connected_at": entry["connected_at"], "last_used": entry["last_used"]}

@api.delete("/routers/{router_id}")
async def delete_router(router_id: str):
    result = await db.routers.delete_one({"id": router_id})
    if result.deleted_count == 0: raise HTTPException(404, "Router not found in managed inventory")
    await asyncio.to_thread(_drop_pool, router_id)
    return {"ok": True, "id": router_id}

def sanitize_error(exc: Exception, router: dict) -> str:
    msg = str(exc)[:180]
    for value in (router.get("host"), router.get("username")):
        if value: msg = msg.replace(value, "[redacted]")
    return msg

@api.get("/routers/{router_id}/resources/{resource}")
async def read_resource(router_id: str, resource: str, reveal: bool = Query(False)):
    if resource not in RESOURCE_PATHS: raise HTTPException(400, "Resource is not allow-listed")
    router = await router_doc(router_id)
    try:
        items = await asyncio.to_thread(ros_call, router, RESOURCE_PATHS[resource])
    except Exception as exc: raise HTTPException(424, f"RouterOS read failed: {sanitize_error(exc, router)}")
    redacted = False
    if resource == "ppp-secrets" and not reveal:
        items = [{**row, **{field: REDACTED_PLACEHOLDER for field in PPP_SECRET_SENSITIVE if field in row}} for row in items]
        redacted = True
    return {"resource": resource, "items": items, "redacted": redacted}

@api.post("/routers/{router_id}/actions/{action}")
async def execute_action(router_id: str, action: str, request: ActionRequest):
    if action == "reboot": raise HTTPException(403, "Reboot requires an authenticated Super Admin confirmation")
    if action not in ACTION_MAP: raise HTTPException(400, "Action is not allow-listed")
    router = await router_doc(router_id); path, command, key, value = ACTION_MAP[action]
    try:
        result = await asyncio.to_thread(ros_call, router, path, command, {".id": request.item_id, key: value})
        await db.audit_log.insert_one({"router_id": router_id, "action": action, "item_id": request.item_id, "created_at": datetime.now(timezone.utc).isoformat()})
        return {"ok": True, "action": action, "result": result}
    except Exception as exc: raise HTTPException(424, f"RouterOS action failed: {sanitize_error(exc, router)}")

@api.get("/routers/{router_id}/backups")
async def backup_history(router_id: str):
    rows = await db.backup_history.find({"router_id": router_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
    allowed = ("router_id", "group", "created_at", "status", "binary_size", "text_size", "binary_name", "text_name")
    return {"items": [{key: row[key] for key in allowed if key in row} for row in rows]}

@api.post("/routers/{router_id}/backup-now")
async def backup_now(router_id: str):
    try:
        await router_doc(router_id)
    except HTTPException as exc:
        if exc.status_code != 404: raise
    return {"ok": False, "status": "configuration_required", "message": "Set managed router credentials, BACKUP_ROOT, BACKUP_ENCRYPTION_KEY, and SMTP settings before enabling backup execution"}

@api.post("/routers/{router_id}/backup-schedule")
async def save_schedule(router_id: str, schedule: ScheduleRequest):
    await router_doc(router_id)
    await db.backup_schedules.update_one({"router_id": router_id}, {"$set": {**schedule.model_dump(), "router_id": router_id}}, upsert=True)
    return {"ok": True, "schedule": schedule.model_dump()}

ALARM_LABELS = {"cpu-threshold": ("🔥", "CPU threshold exceeded"), "interface-status": ("📡", "Interface status changed"), "router-unreachable": ("🚨", "Router unreachable"), "test": ("✅", "NetPulse test alert")}

def mask_token(token: str) -> str:
    if not token or len(token) < 12: return "••••••"
    return f"{token[:5]}••••{token[-4:]}"

async def telegram_group_doc(group: str) -> dict[str, Any]:
    doc = await db.telegram_configs.find_one({"group": group}, {"_id": 0})
    if not doc: raise HTTPException(404, "Telegram is not configured for this group")
    return doc

async def telegram_send(bot_token: str, chat_id: str, text: str) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Telegram unreachable: {type(exc).__name__}")
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"ok": False, "description": "non-json response"}
    if not data.get("ok"):
        detail = data.get("description", "Telegram send failed")[:200]
        raise HTTPException(response.status_code if response.status_code >= 400 else 502, f"Telegram: {detail}")
    return data

def format_alarm(kind: str, router_name: str, detail: str) -> str:
    emoji, label = ALARM_LABELS.get(kind, ("🔔", "Alarm"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [f"{emoji} <b>{html.escape(label)}</b>", f"<b>Router:</b> {html.escape(router_name)}"]
    if detail: parts.append(f"<b>Detail:</b> {html.escape(detail)}")
    parts.append(f"<i>{now}</i>")
    return "\n".join(parts)

@api.get("/notifications/telegram")
async def list_telegram_configs():
    rows = await db.telegram_configs.find({}, {"_id": 0}).to_list(200)
    return {"items": [{"group": r["group"], "chat_id": r.get("chat_id", ""), "enabled": bool(r.get("enabled", False)), "token_hint": r.get("token_hint", "••••••"), "updated_at": r.get("updated_at")} for r in rows]}

@api.put("/notifications/telegram/{group}")
async def upsert_telegram_config(group: str, config: TelegramConfigIn):
    if not group.strip(): raise HTTPException(400, "Group name is required")
    token_enc = credential_box().encrypt(config.bot_token.encode()).decode()
    now = datetime.now(timezone.utc).isoformat()
    await db.telegram_configs.update_one({"group": group}, {"$set": {"group": group, "token_enc": token_enc, "token_hint": mask_token(config.bot_token), "chat_id": config.chat_id, "enabled": config.enabled, "updated_at": now}}, upsert=True)
    return {"ok": True, "group": group, "token_hint": mask_token(config.bot_token), "enabled": config.enabled}

@api.delete("/notifications/telegram/{group}")
async def delete_telegram_config(group: str):
    result = await db.telegram_configs.delete_one({"group": group})
    if result.deleted_count == 0: raise HTTPException(404, "Telegram is not configured for this group")
    return {"ok": True, "group": group}

@api.post("/notifications/telegram/{group}/test")
async def test_telegram_config(group: str):
    doc = await telegram_group_doc(group)
    token = credential_box().decrypt(doc["token_enc"].encode()).decode()
    text = format_alarm("test", "NetPulse control plane", f"Telegram delivery verified for group {group}")
    result = await telegram_send(token, doc["chat_id"], text)
    return {"ok": True, "message_id": result.get("result", {}).get("message_id")}

@api.post("/alarms/dispatch")
async def dispatch_alarm(alarm: AlarmDispatch):
    doc = await telegram_group_doc(alarm.group)
    if not doc.get("enabled", False): raise HTTPException(409, "Telegram delivery is disabled for this group")
    token = credential_box().decrypt(doc["token_enc"].encode()).decode()
    text = format_alarm(alarm.kind, alarm.router_name, alarm.detail)
    result = await telegram_send(token, doc["chat_id"], text)
    await db.alarm_log.insert_one({"group": alarm.group, "router_name": alarm.router_name, "kind": alarm.kind, "detail": alarm.detail, "created_at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "message_id": result.get("result", {}).get("message_id")}

app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])

@app.on_event("shutdown")
async def shutdown():
    with _ROS_LOCK:
        for entry in _ROS_POOLS.values():
            try: entry["pool"].disconnect()
            except Exception: pass
        _ROS_POOLS.clear()
    client.close()