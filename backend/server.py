from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import asyncio, os, re
from cryptography.fernet import Fernet

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

RESOURCE_PATHS = {"interfaces": "/interface", "addresses": "/ip/address", "firewall": "/ip/firewall/filter", "routes": "/ip/route", "logs": "/log", "ppp-profiles": "/ppp/profile", "ppp-secrets": "/ppp/secret", "system-clock": "/system/clock"}
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

def safe_name(value: str) -> str: return re.sub(r"[^A-Za-z0-9_-]+", "_", value)
def credential_box() -> Fernet:
    key = os.environ.get("CREDENTIALS_FERNET_KEY")
    if not key: raise HTTPException(503, "CREDENTIALS_FERNET_KEY is not configured")
    return Fernet(key.encode())

async def router_doc(router_id: str) -> dict[str, Any]:
    doc = await db.routers.find_one({"id": router_id}, {"_id": 0, "password": 0})
    if not doc: raise HTTPException(404, "Router not found in managed inventory")
    return doc

def ros_call(router: dict, path: str, command: str = "print", params: dict | None = None):
    try:
        import routeros_api
        password = credential_box().decrypt(router["password_enc"].encode()).decode()
        pool = routeros_api.RouterOsApiPool(router["host"], username=router["username"], password=password, port=router.get("port", 8728), use_ssl=router.get("port", 8728) == 8729, plaintext_login=router.get("port", 8728) != 8729, socket_timeout=10)
        try: return pool.get_api().get_resource(path).call(command, params or {})
        finally: pool.disconnect()
    except ImportError: raise RuntimeError("RouterOS client is not installed")

@api.get("/")
async def root(): return {"message": "NetPulse API online"}
@api.get("/monitoring/overview")
async def overview(): return DEMO
@api.get("/health")
async def health():
    try: await db.command("ping"); state = "connected"
    except Exception: state = "unavailable"
    return {"ok": True, "database": state, "timestamp": datetime.now(timezone.utc).isoformat()}

@api.post("/routers")
async def create_router(item: RouterCreate):
    # Live credentials are accepted only by the server and never returned to the browser.
    doc = item.model_dump(); password = doc.pop("password"); doc["password_enc"] = credential_box().encrypt(password.encode()).decode(); doc["created_at"] = datetime.now(timezone.utc).isoformat(); doc["status"] = "pending"
    await db.routers.insert_one(doc)
    return {"ok": True, "message": "Router queued for secure connection test"}

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
    except Exception as exc: raise HTTPException(502, f"RouterOS read failed: {sanitize_error(exc, router)}")
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
    except Exception as exc: raise HTTPException(502, f"RouterOS action failed: {sanitize_error(exc, router)}")

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

app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])

@app.on_event("shutdown")
async def shutdown(): client.close()