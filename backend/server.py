from core import db, credential_box, MODULES, level_of, DEFAULT_WORKSPACE_ID
from auth import auth_router, get_current_user, require, current_workspace, seed_auth
from admin import admin_router, groups_for
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any
import asyncio, os, re, html, secrets, threading, time, uuid
import httpx

app = FastAPI(title="NetPulse MikroTik Control Plane")
api = APIRouter(prefix="/api")

LEGACY_GROUP_NAMES = ["Head Office", "Region East", "Operations", "Partner · PT ABC"]

RESOURCE_PATHS = {
    "interfaces": "/interface",
    "bridge": "/interface/bridge", "bridge-ports": "/interface/bridge/port", "vlan": "/interface/vlan",
    "wireless": "/interface/wireless", "wireless-security": "/interface/wireless/security-profiles",
    "addresses": "/ip/address", "arp": "/ip/arp", "ip-pools": "/ip/pool",
    "dhcp-server": "/ip/dhcp-server", "dhcp-leases": "/ip/dhcp-server/lease",
    "firewall": "/ip/firewall/filter", "nat": "/ip/firewall/nat", "routes": "/ip/route",
    "routing-tables": "/routing/table", "vrf": "/ip/vrf",
    "ospf-instances": "/routing/ospf/instance", "ospf-areas": "/routing/ospf/area",
    "ospf-interfaces": "/routing/ospf/interface-template", "ospf-neighbors": "/routing/ospf/neighbor",
    "bgp-connections": "/routing/bgp/connection", "bgp-sessions": "/routing/bgp/session",
    "routing-filters": "/routing/filter/rule", "routing-bfd": "/routing/bfd/session",
    "hotspot-servers": "/ip/hotspot", "hotspot-profiles": "/ip/hotspot/profile",
    "hotspot-users": "/ip/hotspot/user", "hotspot-user-profiles": "/ip/hotspot/user/profile", "hotspot-active": "/ip/hotspot/active",
    "ppp-profiles": "/ppp/profile", "ppp-secrets": "/ppp/secret",
    "queues": "/queue/simple",
    "wireless-registration": "/interface/wireless/registration-table",
    "logs": "/log",
    "system-clock": "/system/clock", "system-resource": "/system/resource",
    "system-identity": "/system/identity", "system-health": "/system/health",
}
# Which RouterOS commands the UI may issue per resource (writes gated by the ros_config privilege).
WRITE_COMMANDS = {
    "interfaces": {"set"}, "addresses": {"add", "set", "remove"}, "arp": {"add", "set", "remove"},
    "bridge": {"add", "set", "remove"}, "bridge-ports": {"add", "set", "remove"}, "vlan": {"add", "set", "remove"},
    "wireless": {"set"}, "wireless-security": {"add", "set", "remove"},
    "ip-pools": {"add", "set", "remove"},
    "dhcp-server": {"add", "set", "remove"}, "dhcp-leases": {"add", "set", "remove"},
    "firewall": {"add", "set", "remove"}, "nat": {"add", "set", "remove"}, "routes": {"add", "set", "remove"},
    "routing-tables": {"add", "set", "remove"}, "vrf": {"add", "set", "remove"},
    "ospf-instances": {"add", "set", "remove"}, "ospf-areas": {"add", "set", "remove"},
    "ospf-interfaces": {"add", "set", "remove"}, "bgp-connections": {"add", "set", "remove"},
    "routing-filters": {"add", "set", "remove"},
    "hotspot-servers": {"add", "set", "remove"}, "hotspot-profiles": {"add", "set", "remove"},
    "hotspot-users": {"add", "set", "remove"}, "hotspot-user-profiles": {"add", "set", "remove"}, "hotspot-active": {"remove"},
    "ppp-profiles": {"add", "set", "remove"}, "ppp-secrets": {"add", "set", "remove"}, "queues": {"add", "set", "remove"},
    "system-clock": {"set"}, "system-identity": {"set"},
}
PPP_SECRET_SENSITIVE = ("password", "caller-id", "last-caller-id")
SENSITIVE_FIELDS = {"ppp-secrets": PPP_SECRET_SENSITIVE, "hotspot-users": ("password",), "wireless-security": ("wpa-pre-shared-key", "wpa2-pre-shared-key", "eap-methods")}
REDACTED_PLACEHOLDER = "••••••"
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,40}$")


class RouterCreate(BaseModel):
    name: str = Field(min_length=2); host: str; port: int = Field(8728, ge=1, le=65535)
    username: str = Field("", max_length=64); password: str = Field("", max_length=128)
    device_type: str = Field("mikrotik", pattern="^(mikrotik|huawei|juniper|cisco|other)$")
    use_ssl: bool = False
    snmp_enabled: bool = False; snmp_community: str = Field("", max_length=64); snmp_port: int = Field(161, ge=1, le=65535)
    ssh_port: int = Field(22, ge=1, le=65535); telnet_port: int = Field(23, ge=1, le=65535)
    group_id: str; description: str = Field(default="", max_length=200)
class RouterUpdate(BaseModel):
    name: str = Field(min_length=2); host: str; port: int = Field(8728, ge=1, le=65535)
    username: str = Field("", max_length=64); password: str | None = None
    device_type: str = Field("mikrotik", pattern="^(mikrotik|huawei|juniper|cisco|other)$")
    use_ssl: bool = False
    snmp_enabled: bool = False; snmp_community: str = Field("", max_length=64); snmp_port: int = Field(161, ge=1, le=65535)
    ssh_port: int = Field(22, ge=1, le=65535); telnet_port: int = Field(23, ge=1, le=65535)
    group_id: str; description: str = Field(default="", max_length=200)
class ConfigWrite(BaseModel):
    values: dict[str, str] = Field(default_factory=dict); item_id: str | None = Field(default=None, pattern=r"^\*[A-Za-z0-9]+$")
class TelegramConfigIn(BaseModel):
    bot_token: str = Field(min_length=20, max_length=200, pattern=r"^\d+:[A-Za-z0-9_\-]+$")
    chat_id: str = Field(min_length=1, max_length=40, pattern=r"^-?\d+$")
    enabled: bool = True
class AlarmDispatch(BaseModel):
    kind: str = Field(pattern="^(cpu-threshold|interface-status|router-unreachable|test)$")
    router_id: str = Field(min_length=1); detail: str = Field(default="", max_length=280)


# ---------- visibility helpers ----------
def router_filter(user: dict, ws: str) -> dict:
    if user.get("is_super_admin"): return {"workspace_id": ws}
    return {"workspace_id": ws, "group_id": {"$in": user["effective_group_ids"]}}

async def visible_router(router_id: str, request: Request, user: dict) -> dict[str, Any]:
    ws = await current_workspace(request, user)
    doc = await db.routers.find_one({"id": router_id, **router_filter(user, ws)}, {"_id": 0})
    if not doc: raise HTTPException(404, "Router not found in managed inventory")
    return doc

async def group_in_workspace(group_id: str, ws: str) -> dict:
    g = await db.groups.find_one({"id": group_id, "workspace_id": ws}, {"_id": 0})
    if not g: raise HTTPException(404, "Group not found in this workspace")
    return g

def can_manage_group(user: dict, group_id: str) -> bool:
    return bool(user.get("is_super_admin")) or group_id in user["effective_group_ids"]


# ---------- RouterOS pooled sessions (per router + per user credentials) ----------
_ROS_POOLS: dict[str, dict[str, Any]] = {}
_ROS_LOCK = threading.Lock()

def ros_credentials(router: dict, user: dict, user_secret: dict) -> tuple[str, str]:
    if user_secret.get("ros_username") and user_secret.get("ros_password_enc"):
        return user_secret["ros_username"], credential_box().decrypt(user_secret["ros_password_enc"].encode()).decode()
    if (user.get("is_super_admin") or router.get("created_by") == user["user_id"]) and router.get("password_enc"):
        return router["username"], credential_box().decrypt(router["password_enc"].encode()).decode()
    raise HTTPException(428, "Isi kredensial MikroTik Anda dulu di My settings sebelum membuka router yang di-share")

def _new_pool(router: dict, username: str, password: str):
    import routeros_api
    port = router.get("port", 8728)
    use_ssl = bool(router.get("use_ssl")) if router.get("use_ssl") is not None else port == 8729
    pool = routeros_api.RouterOsApiPool(router["host"], username=username, password=password, port=port, use_ssl=use_ssl, plaintext_login=not use_ssl)
    pool.socket_timeout = 8
    return pool

def _drop_pool(router_id: str, user_id: str | None = None):
    with _ROS_LOCK:
        keys = [k for k in _ROS_POOLS if k.startswith(f"{router_id}:") and (user_id is None or k.endswith(f":{user_id}"))]
        entries = [_ROS_POOLS.pop(k) for k in keys]
    for entry in entries:
        try: entry["pool"].disconnect()
        except Exception: pass

def drop_user_pools(user_id: str):
    with _ROS_LOCK:
        keys = [k for k in _ROS_POOLS if k.endswith(f":{user_id}")]
        entries = [_ROS_POOLS.pop(k) for k in keys]
    for entry in entries:
        try: entry["pool"].disconnect()
        except Exception: pass

def _get_pool_entry(router: dict, user_id: str, creds: tuple[str, str]):
    key = f"{router['id']}:{user_id}"
    with _ROS_LOCK:
        entry = _ROS_POOLS.get(key)
        if entry: return entry
    pool = _new_pool(router, *creds)
    api_client = pool.get_api()
    entry = {"pool": pool, "api": api_client, "connected_at": time.time(), "last_used": time.time()}
    with _ROS_LOCK: _ROS_POOLS[key] = entry
    return entry

def ros_call(router: dict, user_id: str, creds: tuple[str, str], path: str, command: str = "print", params: dict | None = None):
    last_exc: Exception | None = None
    for _attempt in (1, 2):
        try:
            entry = _get_pool_entry(router, user_id, creds)
            result = entry["api"].get_resource(path).call(command, params or {})
            entry["last_used"] = time.time()
            return result
        except Exception as exc:
            last_exc = exc
            _drop_pool(router["id"], user_id)
            if "permission" in str(exc).lower(): break
    raise last_exc if last_exc else RuntimeError("RouterOS call failed")

def sanitize_error(exc: Exception, router: dict) -> str:
    msg = str(exc)[:180]
    for value in (router.get("host"), router.get("username")):
        if value: msg = msg.replace(value, "[redacted]")
    return msg

def ros_http_error(exc: Exception, router: dict, verb: str) -> HTTPException:
    text = str(exc).lower()
    if "not enough permissions" in text or "permission" in text: return HTTPException(403, "not enough permission")
    if "invalid user name or password" in text or "login failure" in text: return HTTPException(401, "RouterOS rejected the MikroTik username/password")
    return HTTPException(424, f"RouterOS {verb} failed: {sanitize_error(exc, router)}")

async def user_secret(user_id: str) -> dict:
    return await db.users.find_one({"user_id": user_id}, {"_id": 0, "ros_username": 1, "ros_password_enc": 1}) or {}

def probe_router(router: dict, creds: tuple[str, str], user_id: str = "system") -> dict[str, Any]:
    try:
        rows = ros_call(router, user_id, creds, "/system/resource")
        row = rows[0] if rows else {}
        free = int(row.get("free-memory", 0) or 0); total = int(row.get("total-memory", 0) or 0)
        memory_pct = int(round((total - free) * 100 / total)) if total else 0
        return {"status": "online", "cpu": int(row.get("cpu-load", 0) or 0), "memory": memory_pct, "uptime": row.get("uptime", "—"), "version": row.get("version", "—")}
    except Exception as exc:
        return {"status": "offline", "error": sanitize_error(exc, router)}

async def probe_generic(device: dict) -> dict[str, Any]:
    """Non-MikroTik vendors: reachability comes from ICMP ping, health from the SNMP sweep."""
    from monitor import ping_device, poll_snmp
    ping = await ping_device(device["host"])
    out: dict[str, Any] = {"status": "online" if ping["alive"] else "offline", "ping_ms": ping.get("rtt_ms"), "ping_loss": ping.get("loss"), "reachable": ping["alive"]}
    if not ping["alive"]: out["error"] = "ICMP ping did not answer"
    if device.get("snmp_enabled"):
        snmp = await poll_snmp(device)
        if snmp.get("error"): out["error"] = snmp["error"]
        else: out.update({"cpu": snmp.get("cpu", 0), "uptime": snmp.get("uptime", "—"), "version": (snmp.get("sysdescr") or "—")[:60], "interfaces": len(snmp.get("interfaces") or [])})
    return out


def stored_creds(router: dict) -> tuple[str, str]:
    return router["username"], credential_box().decrypt(router["password_enc"].encode()).decode()

MANAGED_PUBLIC_FIELDS = ("id", "name", "host", "port", "use_ssl", "device_type", "snmp_enabled", "snmp_port", "ping_ms", "ping_loss", "reachable", "last_ping_at", "ssh_port", "telnet_port", "group", "group_id", "workspace_id", "description", "status", "cpu", "memory", "uptime", "version", "traffic", "interfaces", "color", "created_at", "created_by", "last_probed_at", "updated_at")

def sanitize_router(doc: dict, user: dict | None = None) -> dict:
    out = {k: doc[k] for k in MANAGED_PUBLIC_FIELDS if k in doc}
    if user and (user.get("is_super_admin") or doc.get("created_by") == user["user_id"]): out["username"] = doc.get("username")
    return out

async def audit(user: dict, action: str, target: str, detail: str = ""):
    await db.audit_log.insert_one({"id": f"aud-{uuid.uuid4().hex[:8]}", "user_id": user["user_id"], "email": user["email"], "action": action, "target": target, "detail": detail[:300], "created_at": datetime.now(timezone.utc).isoformat()})


# ---------- monitoring ----------
@api.get("/")
async def root(): return {"service": "NetPulse", "status": "ok", "auth": "required"}

@api.get("/health")
async def health():
    try: await db.command("ping"); state = "connected"
    except Exception: state = "unavailable"
    return {"ok": True, "database": state, "timestamp": datetime.now(timezone.utc).isoformat()}

@api.get("/monitoring/overview")
async def overview(request: Request, user: dict = Depends(require("overview", "read"))):
    ws = await current_workspace(request, user)
    managed = await db.routers.find(router_filter(user, ws), {"_id": 0}).to_list(500)
    routers = []
    for m in managed:
        row = sanitize_router(m, user)
        for k, v in (("status", "pending"), ("cpu", 0), ("memory", 0), ("uptime", "—"), ("interfaces", 0), ("traffic", "—"), ("version", "—"), ("color", "cyan")): row.setdefault(k, v)
        routers.append(row)
    workspace = await db.workspaces.find_one({"id": ws}, {"_id": 0})
    alarms = await db.alarm_log.find({"workspace_id": ws}, {"_id": 0}).sort("created_at", -1).to_list(20)
    return {"workspace": workspace, "routers": routers, "groups": await groups_for(ws, user), "alarms": alarms}

@api.post("/monitoring/probe-all")
async def probe_all(request: Request, user: dict = Depends(require("routers", "read"))):
    ws = await current_workspace(request, user)
    docs = await db.routers.find(router_filter(user, ws)).to_list(500)
    secret = await user_secret(user["user_id"])
    async def one(doc):
        try: creds = ros_credentials(doc, user, secret)
        except HTTPException: return {"id": doc["id"], "status": doc.get("status", "pending"), "skipped": "no-credentials"}
        probe = await asyncio.to_thread(probe_router, doc, creds, user["user_id"])
        await db.routers.update_one({"id": doc["id"]}, {"$set": {**{k: v for k, v in probe.items() if k != "error"}, "last_probed_at": datetime.now(timezone.utc).isoformat()}})
        return {"id": doc["id"], "status": probe.get("status")}
    results = await asyncio.gather(*[one(d) for d in docs], return_exceptions=True)
    return {"ok": True, "count": len(docs), "results": [r for r in results if not isinstance(r, Exception)]}


# ---------- routers ----------
@api.get("/routers")
async def list_routers(request: Request, user: dict = Depends(require("routers", "read"))):
    ws = await current_workspace(request, user)
    docs = await db.routers.find(router_filter(user, ws), {"_id": 0}).to_list(500)
    return {"items": [sanitize_router(d, user) for d in docs]}

@api.post("/routers")
async def create_router(item: RouterCreate, request: Request, user: dict = Depends(require("routers", "write"))):
    ws = await current_workspace(request, user)
    group = await group_in_workspace(item.group_id, ws)
    if not can_manage_group(user, item.group_id): raise HTTPException(403, "No access to this group")
    doc = item.model_dump(); password = doc.pop("password"); community = doc.pop("snmp_community", "")
    if doc["device_type"] == "mikrotik" and not (doc["username"] and password): raise HTTPException(422, "MikroTik devices need an API username and password")
    if doc["snmp_enabled"] and not community: raise HTTPException(422, "A community string is required to enable SNMP")
    doc.update({"id": f"mr-{secrets.token_hex(4)}", "group": group["name"], "workspace_id": ws, "created_by": user["user_id"],
                "created_at": datetime.now(timezone.utc).isoformat(), "status": "pending"})
    if password: doc["password_enc"] = credential_box().encrypt(password.encode()).decode()
    if community: doc["snmp_community_enc"] = credential_box().encrypt(community.encode()).decode()
    probe = await asyncio.to_thread(probe_router, doc, (doc["username"], password), user["user_id"]) if doc["device_type"] == "mikrotik" else await probe_generic(doc)
    doc.update({k: v for k, v in probe.items() if k != "error"}); doc["last_probed_at"] = datetime.now(timezone.utc).isoformat()
    await db.routers.insert_one(dict(doc))
    await audit(user, "router.create", doc["id"], doc["name"])
    return {"ok": True, "message": "Router onboarded", "router": sanitize_router(doc, user), "probe": {"status": probe.get("status"), "error": probe.get("error")}}

@api.put("/routers/{router_id}")
async def update_router(router_id: str, item: RouterUpdate, request: Request, user: dict = Depends(require("routers", "write"))):
    router = await visible_router(router_id, request, user)
    group = await group_in_workspace(item.group_id, router["workspace_id"])
    if not can_manage_group(user, item.group_id): raise HTTPException(403, "No access to this group")
    if not (user.get("is_super_admin") or router.get("created_by") == user["user_id"]) and (item.username != router.get("username") or item.password):
        raise HTTPException(403, "Only the owner or a Super Admin can change stored router credentials")
    update = item.model_dump(); password = update.pop("password"); community = update.pop("snmp_community", "")
    if update["snmp_enabled"] and not (community or router.get("snmp_community_enc")): raise HTTPException(422, "A community string is required to enable SNMP")
    if community: update["snmp_community_enc"] = credential_box().encrypt(community.encode()).decode()
    update.update({"name": update["name"].strip(), "host": update["host"].strip(), "username": update["username"].strip(), "group": group["name"], "updated_at": datetime.now(timezone.utc).isoformat()})
    if password: update["password_enc"] = credential_box().encrypt(password.encode()).decode()
    await db.routers.update_one({"id": router_id}, {"$set": update})
    await asyncio.to_thread(_drop_pool, router_id)
    doc = await db.routers.find_one({"id": router_id}, {"_id": 0})
    probe = await asyncio.to_thread(probe_router, doc, stored_creds(doc), user["user_id"]) if doc.get("device_type", "mikrotik") == "mikrotik" else await probe_generic(doc)
    doc.update({k: v for k, v in probe.items() if k != "error"}); doc["last_probed_at"] = datetime.now(timezone.utc).isoformat()
    await db.routers.update_one({"id": router_id}, {"$set": {k: doc[k] for k in ("status", "cpu", "memory", "uptime", "version", "last_probed_at") if k in doc}})
    await audit(user, "router.update", router_id, doc["name"])
    return {"ok": True, "message": "Router updated", "router": sanitize_router(doc, user), "probe": {"status": probe.get("status"), "error": probe.get("error")}}

@api.delete("/routers/{router_id}")
async def delete_router(router_id: str, request: Request, user: dict = Depends(require("routers", "write"))):
    router = await visible_router(router_id, request, user)
    await db.routers.delete_one({"id": router_id})
    await asyncio.to_thread(_drop_pool, router_id)
    await audit(user, "router.delete", router_id, router.get("name", ""))
    return {"ok": True, "id": router_id}

@api.post("/routers/{router_id}/test-connection")
async def test_connection(router_id: str, request: Request, user: dict = Depends(require("routers", "read"))):
    router = await visible_router(router_id, request, user)
    if (router.get("device_type") or "mikrotik") != "mikrotik":
        probe = await probe_generic(router)
        await db.routers.update_one({"id": router_id}, {"$set": {**{k: v for k, v in probe.items() if k != "error"}, "last_probed_at": datetime.now(timezone.utc).isoformat()}})
        return {"ok": True, "status": probe.get("status"), "error": probe.get("error"), "cpu": probe.get("cpu"), "uptime": probe.get("uptime"), "version": probe.get("version")}
    creds = ros_credentials(router, user, await user_secret(user["user_id"]))
    probe = await asyncio.to_thread(probe_router, router, creds, user["user_id"])
    update = {k: v for k, v in probe.items() if k != "error"}; update["last_probed_at"] = datetime.now(timezone.utc).isoformat()
    await db.routers.update_one({"id": router_id}, {"$set": update})
    return {"ok": True, "status": probe.get("status"), "error": probe.get("error"), "cpu": probe.get("cpu"), "uptime": probe.get("uptime"), "version": probe.get("version")}

@api.post("/routers/{router_id}/disconnect")
async def disconnect_router(router_id: str, request: Request, user: dict = Depends(require("routers", "read"))):
    await visible_router(router_id, request, user)
    await asyncio.to_thread(_drop_pool, router_id, user["user_id"])
    return {"ok": True, "id": router_id, "connected": False}

@api.get("/routers/{router_id}/connection")
async def connection_state(router_id: str, request: Request, user: dict = Depends(require("routers", "read"))):
    await visible_router(router_id, request, user)
    with _ROS_LOCK: entry = _ROS_POOLS.get(f"{router_id}:{user['user_id']}")
    if not entry: return {"connected": False}
    return {"connected": True, "connected_at": entry["connected_at"], "last_used": entry["last_used"]}

@api.get("/routers/{router_id}/resources/{resource}")
async def read_resource(router_id: str, resource: str, request: Request, reveal: bool = Query(False), user: dict = Depends(require("routers", "read"))):
    if resource not in RESOURCE_PATHS: raise HTTPException(400, "Resource is not allow-listed")
    router = await visible_router(router_id, request, user)
    if (router.get("device_type") or "mikrotik") != "mikrotik": raise HTTPException(400, "RouterOS menus are only available on MikroTik devices — use SNMP or the SSH/Telnet terminal")
    creds = ros_credentials(router, user, await user_secret(user["user_id"]))
    try: items = await asyncio.to_thread(ros_call, router, user["user_id"], creds, RESOURCE_PATHS[resource])
    except Exception as exc: raise ros_http_error(exc, router, "read")
    redacted = False
    if resource in SENSITIVE_FIELDS and not reveal:
        items = [{**row, **{field: REDACTED_PLACEHOLDER for field in SENSITIVE_FIELDS[resource] if field in row}} for row in items]
        redacted = True
    return {"resource": resource, "items": items, "redacted": redacted, "writable": sorted(WRITE_COMMANDS.get(resource, set())) if level_of(user, "ros_config") >= 2 else []}

@api.post("/routers/{router_id}/config/{resource}/{command}")
async def write_config(router_id: str, resource: str, command: str, body: ConfigWrite, request: Request, user: dict = Depends(require("ros_config", "write"))):
    if resource not in RESOURCE_PATHS: raise HTTPException(400, "Resource is not allow-listed")
    if command not in WRITE_COMMANDS.get(resource, set()): raise HTTPException(400, f"'{command}' is not allowed on {resource}")
    if command in ("set", "remove") and not body.item_id and resource not in ("system-clock", "system-identity"): raise HTTPException(422, "item_id is required")
    if command == "remove": body.values = {}
    for k, v in body.values.items():
        if not KEY_RE.match(k): raise HTTPException(422, f"Invalid property name: {k}")
        if len(v) > 500: raise HTTPException(422, f"Value too long for {k}")
    router = await visible_router(router_id, request, user)
    creds = ros_credentials(router, user, await user_secret(user["user_id"]))
    params = dict(body.values)
    if body.item_id: params[".id"] = body.item_id
    if command == "remove": params = {".id": body.item_id}
    try: result = await asyncio.to_thread(ros_call, router, user["user_id"], creds, RESOURCE_PATHS[resource], command, params)
    except Exception as exc: raise ros_http_error(exc, router, command)
    await audit(user, f"ros.{command}", f"{router_id}:{resource}", body.item_id or ",".join(f"{k}={v}" for k, v in list(body.values.items())[:4]))
    return {"ok": True, "command": command, "result": result}


# ---------- backups (.rsc snapshot via API → object storage) ----------
EXPORT_SECTIONS = [("/system/identity", "system identity"), ("/system/clock", "system clock"), ("/interface", "interface"), ("/ip/address", "ip address"), ("/ip/arp", "ip arp"),
                   ("/ip/dhcp-server", "ip dhcp-server"), ("/ip/dhcp-server/lease", "ip dhcp-server lease"), ("/ip/route", "ip route"), ("/ip/firewall/filter", "ip firewall filter"),
                   ("/ip/firewall/nat", "ip firewall nat"), ("/ppp/profile", "ppp profile"), ("/ppp/secret", "ppp secret"), ("/queue/simple", "queue simple")]
SKIP_PROPS = {".id", "dynamic", "running", "active", "invalid", "complete", "bytes", "packets", "last-link-up-time", "last-link-down-time", "link-downs", "status", "expires-after", "last-seen", "host-name", "age", "rx-byte", "tx-byte", "rx-packet", "tx-packet", "rx-drop", "tx-drop", "rx-error", "tx-error", "fp-rx-byte", "fp-tx-byte", "fp-rx-packet", "fp-tx-packet", "default-name", "actual-mtu", "l2mtu", "max-l2mtu", "mac-address", "orig-mac-address", "last-logged-out", "last-caller-id", "last-disconnect-reason", "queue", "total-max-limit", "total-queue", "total-bytes", "total-packets", "dropped", "total-dropped", "queued-bytes", "queued-packets", "total-queued-bytes", "total-queued-packets", "rate", "packet-rate", "total-packet-rate", "total-rate", "lends", "borrows", "total-lends", "total-borrows"}

def rsc_value(v: str) -> str:
    v = str(v)
    if v == "true": return "yes"
    if v == "false": return "no"
    return f'"{v}"' if (" " in v or v == "" or any(c in v for c in "\"'")) else v

def build_rsc(router: dict, user_id: str, creds: tuple[str, str]) -> tuple[str, list[str]]:
    lines = [f"# NetPulse API snapshot export — {router['name']} ({router['host']})", f"# generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", "# note: built from RouterOS API reads of managed sections (not a full /export); passwords redacted", ""]
    sections = []
    for path, label in EXPORT_SECTIONS:
        try: rows = ros_call(router, user_id, creds, path)
        except Exception as exc: lines.append(f"# /{label}: read failed ({str(exc)[:80]})"); lines.append(""); continue
        sections.append(label); lines.append(f"/{label}")
        single = path in ("/system/identity", "/system/clock")
        for row in rows:
            if row.get("dynamic") == "true": continue
            props = " ".join(f"{k}={rsc_value(v)}" for k, v in row.items() if k not in SKIP_PROPS and not k.startswith(".") and v not in (None, "") and not (path == "/ppp/secret" and k == "password"))
            if path == "/ppp/secret" and "password" in row: props += " password=\"<redacted>\""
            lines.append(f"{'set' if single else 'add'} {props}".rstrip())
        lines.append("")
    return "\n".join(lines), sections

@api.get("/routers/{router_id}/backups")
async def backup_history(router_id: str, request: Request, user: dict = Depends(require("backups", "read"))):
    await visible_router(router_id, request, user)
    rows = await db.backups.find({"router_id": router_id, "is_deleted": False}, {"_id": 0, "storage_path": 0}).sort("created_at", -1).to_list(100)
    return {"items": rows}

@api.post("/routers/{router_id}/backup-now")
async def backup_now(router_id: str, request: Request, user: dict = Depends(require("backups", "write"))):
    from storage import put_object, APP_NAME
    router = await visible_router(router_id, request, user)
    creds = ros_credentials(router, user, await user_secret(user["user_id"]))
    try: text, sections = await asyncio.to_thread(build_rsc, router, user["user_id"], creds)
    except Exception as exc: raise ros_http_error(exc, router, "export")
    if not sections: raise HTTPException(424, "RouterOS export failed: no sections could be read")
    stamp = datetime.now(timezone.utc)
    filename = f"{re.sub(r'[^A-Za-z0-9_-]+', '_', router['name'])}_{stamp.strftime('%Y%m%d-%H%M%S')}.rsc"
    path = f"{APP_NAME}/backups/{router['workspace_id']}/{router_id}/{uuid.uuid4().hex}.rsc"
    try: result = await asyncio.to_thread(put_object, path, text.encode(), "text/plain")
    except Exception as exc: raise HTTPException(502, f"Object storage upload failed: {type(exc).__name__}")
    doc = {"id": f"bk-{uuid.uuid4().hex[:8]}", "router_id": router_id, "router_name": router["name"], "workspace_id": router["workspace_id"], "filename": filename, "storage_path": result["path"], "size": result.get("size", len(text)),
           "sections": sections, "kind": "rsc", "created_by": user["user_id"], "created_by_email": user["email"], "is_deleted": False, "created_at": stamp.isoformat()}
    await db.backups.insert_one(dict(doc))
    await audit(user, "backup.create", router_id, filename)
    doc.pop("storage_path")
    return {"ok": True, "backup": doc}

@api.get("/backups/{backup_id}/download")
async def backup_download(backup_id: str, request: Request, user: dict = Depends(require("backups", "read"))):
    from storage import get_object
    from fastapi.responses import Response
    doc = await db.backups.find_one({"id": backup_id, "is_deleted": False}, {"_id": 0})
    if not doc: raise HTTPException(404, "Backup not found")
    await visible_router(doc["router_id"], request, user)
    try: data, ctype = await asyncio.to_thread(get_object, doc["storage_path"])
    except Exception as exc: raise HTTPException(502, f"Object storage download failed: {type(exc).__name__}")
    return Response(content=data, media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{doc["filename"]}"'})

@api.delete("/backups/{backup_id}")
async def backup_delete(backup_id: str, request: Request, user: dict = Depends(require("backups", "write"))):
    doc = await db.backups.find_one({"id": backup_id, "is_deleted": False}, {"_id": 0})
    if not doc: raise HTTPException(404, "Backup not found")
    await visible_router(doc["router_id"], request, user)
    await db.backups.update_one({"id": backup_id}, {"$set": {"is_deleted": True, "deleted_at": datetime.now(timezone.utc).isoformat()}})
    await audit(user, "backup.delete", doc["router_id"], doc["filename"])
    return {"ok": True, "id": backup_id}


# ---------- audit ----------
@api.get("/audit")
async def audit_list(user: dict = Depends(require("audit", "read"))):
    rows = await db.audit_log.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"items": rows}


# ---------- Telegram per role ----------
ALARM_LABELS = {"cpu-threshold": ("🔥", "CPU threshold exceeded"), "interface-status": ("📡", "Interface status changed"), "router-unreachable": ("🚨", "Device unreachable"), "syslog-match": ("📜", "Syslog alarm"), "test": ("✅", "NetPulse test alert")}

def mask_token(token: str) -> str:
    if not token or len(token) < 12: return "••••••"
    return f"{token[:5]}••••{token[-4:]}"

async def telegram_send(bot_token: str, chat_id: str, text: str) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        async with httpx.AsyncClient(timeout=10.0) as http: response = await http.post(url, json=payload)
    except httpx.HTTPError as exc: raise HTTPException(502, f"Telegram unreachable: {type(exc).__name__}")
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"ok": False, "description": "non-json response"}
    if not data.get("ok"):
        raise HTTPException(response.status_code if response.status_code >= 400 else 502, f"Telegram: {data.get('description', 'send failed')[:200]}")
    return data

def format_alarm(kind: str, router_name: str, detail: str) -> str:
    emoji, label = ALARM_LABELS.get(kind, ("🔔", "Alarm"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [f"{emoji} <b>{html.escape(label)}</b>", f"<b>Router:</b> {html.escape(router_name)}"]
    if detail: parts.append(f"<b>Detail:</b> {html.escape(detail)}")
    parts.append(f"<i>{now}</i>")
    return "\n".join(parts)

def telegram_public(role: dict) -> dict:
    tg = role.get("telegram") or {}
    return {"role_id": role["id"], "role_name": role["name"], "configured": bool(tg.get("token_enc")), "chat_id": tg.get("chat_id", ""), "enabled": bool(tg.get("enabled", False)), "token_hint": tg.get("token_hint", "••••••"), "updated_at": tg.get("updated_at")}

@api.get("/notifications/telegram")
async def list_telegram_configs(user: dict = Depends(require("notifications", "read"))):
    roles = await db.roles.find({}, {"_id": 0}).to_list(200)
    return {"items": [telegram_public(r) for r in roles]}

@api.put("/notifications/telegram/{role_id}")
async def upsert_telegram_config(role_id: str, config: TelegramConfigIn, user: dict = Depends(require("notifications", "write"))):
    if not await db.roles.find_one({"id": role_id}): raise HTTPException(404, "Role not found")
    tg = {"token_enc": credential_box().encrypt(config.bot_token.encode()).decode(), "token_hint": mask_token(config.bot_token), "chat_id": config.chat_id, "enabled": config.enabled, "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.roles.update_one({"id": role_id}, {"$set": {"telegram": tg}})
    return {"ok": True, "role_id": role_id, "token_hint": tg["token_hint"], "enabled": config.enabled}

@api.delete("/notifications/telegram/{role_id}")
async def delete_telegram_config(role_id: str, user: dict = Depends(require("notifications", "write"))):
    r = await db.roles.update_one({"id": role_id, "telegram": {"$exists": True}}, {"$unset": {"telegram": ""}})
    if r.matched_count == 0: raise HTTPException(404, "Telegram is not configured for this role")
    return {"ok": True, "role_id": role_id}

@api.post("/notifications/telegram/{role_id}/test")
async def test_telegram_config(role_id: str, user: dict = Depends(require("notifications", "write"))):
    role = await db.roles.find_one({"id": role_id}, {"_id": 0})
    if not role or not (role.get("telegram") or {}).get("token_enc"): raise HTTPException(404, "Telegram is not configured for this role")
    token = credential_box().decrypt(role["telegram"]["token_enc"].encode()).decode()
    result = await telegram_send(token, role["telegram"]["chat_id"], format_alarm("test", "NetPulse control plane", f"Telegram delivery verified for role {role['name']}"))
    return {"ok": True, "message_id": result.get("result", {}).get("message_id")}

async def deliver_alarm(router: dict, kind: str, detail: str, source: str = "auto", extra: dict | None = None) -> list[str]:
    """Send an alarm to the Telegram channel of every role that covers this router's group, then log it."""
    roles = await db.roles.find({"group_ids": router.get("group_id"), "telegram.enabled": True}, {"_id": 0}).to_list(200)
    text = format_alarm(kind, router.get("name", "router"), detail); sent = []; failed = []
    for role in roles:
        try:
            token = credential_box().decrypt(role["telegram"]["token_enc"].encode()).decode()
            await telegram_send(token, role["telegram"]["chat_id"], text)
            sent.append(role["name"])
        except Exception as exc: failed.append(f"{role['name']}: {type(exc).__name__}")
    await db.alarm_log.insert_one({"id": f"alm-{uuid.uuid4().hex[:8]}", "workspace_id": router.get("workspace_id"), "router_id": router["id"], "router_name": router.get("name"),
                                   "group_id": router.get("group_id"), "kind": kind, "detail": detail, "roles_notified": sent, "roles_failed": failed, "source": source,
                                   **(extra or {}), "created_at": datetime.now(timezone.utc).isoformat()})
    return sent

@api.post("/alarms/dispatch")
async def dispatch_alarm(alarm: AlarmDispatch, request: Request, user: dict = Depends(require("alarms", "write"))):
    router = await visible_router(alarm.router_id, request, user)
    if not await db.roles.find_one({"group_ids": router.get("group_id"), "telegram.enabled": True}): raise HTTPException(409, "No role with Telegram enabled has access to this router's group")
    return {"ok": True, "roles_notified": await deliver_alarm(router, alarm.kind, alarm.detail, source="manual")}


# ---------- terminal (RouterOS command line over API) ----------
TERMINAL_VERBS = {"print", "get", "add", "set", "remove", "enable", "disable", "export"}
TERMINAL_BLOCKED = ("/system/reboot", "/system/shutdown", "/system/reset-configuration", "/user", "/password", "/import", "/system/package", "/file", "/tool/fetch", "/system/script/run", "/certificate")
class TerminalIn(BaseModel):
    command: str = Field(min_length=1, max_length=600)

def parse_terminal(cmd: str) -> tuple[str, str, dict[str, str], dict[str, str]]:
    tokens = cmd.strip().split()
    if not tokens or not tokens[0].startswith("/"): raise HTTPException(422, "Command must start with a menu path, e.g. /ip address print")
    path_parts: list[str] = []; i = 0
    while i < len(tokens) and tokens[i].lower() not in TERMINAL_VERBS:
        path_parts.extend(p for p in tokens[i].split("/") if p); i += 1
    path = "/" + "/".join(path_parts)
    if any(path.startswith(b) for b in TERMINAL_BLOCKED): raise HTTPException(403, f"'{path}' is blocked in the NetPulse terminal for safety")
    if i >= len(tokens): raise HTTPException(422, f"Missing command. Supported: {', '.join(sorted(TERMINAL_VERBS))}")
    verb = tokens[i].lower(); params: dict[str, str] = {}; where: dict[str, str] = {}
    target = params
    for tok in tokens[i + 1:]:
        if tok.lower() == "where": target = where; continue
        if "=" in tok: k, v = tok.split("=", 1); target[k.strip()] = v.strip().strip('"')
        elif tok.startswith("*"): target[".id"] = tok
        elif tok.lower() in ("detail", "terse", "brief", "without-paging", "numbers"): continue
        else: target[".id"] = tok if verb in ("set", "remove", "enable", "disable") else target.get(".id", tok)
    return path, verb, params, where

@api.post("/routers/{router_id}/terminal")
async def terminal(router_id: str, body: TerminalIn, request: Request, user: dict = Depends(require("routers", "read"))):
    path, verb, params, where = parse_terminal(body.command)
    if any(path.startswith(b) for b in TERMINAL_BLOCKED): raise HTTPException(403, f"'{path}' is blocked in the NetPulse terminal for safety")
    if verb == "export": raise HTTPException(400, "Use Files › Backups for configuration export (the API cannot stream /export output)")
    write = verb not in ("print", "get")
    if write and level_of(user, "ros_config") < 2: raise HTTPException(403, "not enough permission")
    router = await visible_router(router_id, request, user)
    creds = ros_credentials(router, user, await user_secret(user["user_id"]))
    if verb in ("enable", "disable"): params = {**params, "disabled": "no" if verb == "enable" else "yes"}; verb = "set"
    if verb == "get": verb = "print"
    started = time.time()
    def run():
        entry = _get_pool_entry(router, user["user_id"], creds)
        res = entry["api"].get_resource(path)
        if verb == "print":
            rows = res.get(**{k: v for k, v in {**where, **params}.items()}) if (where or params) else res.get()
            return list(rows)
        return res.call(verb, params)
    try: result = await asyncio.to_thread(run)
    except Exception as exc:
        _drop_pool(router_id, user["user_id"])
        raise ros_http_error(exc, router, verb)
    if write: await audit(user, f"terminal.{verb}", f"{router_id}:{path}", body.command)
    if path == "/ppp/secret" and isinstance(result, list): result = [{**r, **{f: REDACTED_PLACEHOLDER for f in PPP_SECRET_SENSITIVE if f in r}} for r in result]
    return {"ok": True, "path": path, "command": verb, "rows": result if isinstance(result, list) else [result] if result else [], "elapsed_ms": int((time.time() - started) * 1000), "write": write}

# ---------- startup migration ----------
async def migrate_legacy():
    now = datetime.now(timezone.utc).isoformat()
    names = list(LEGACY_GROUP_NAMES)
    for old in await db.groups.find({"id": {"$exists": False}}, {"_id": 0, "name": 1}).to_list(200): names.append(old["name"])
    for name in {r["group"] for r in await db.routers.find({"group": {"$exists": True}}, {"_id": 0, "group": 1}).to_list(500) if r.get("group")}: names.append(name)
    await db.groups.delete_many({"id": {"$exists": False}})
    for name in dict.fromkeys(names):
        if not await db.groups.find_one({"name": name, "workspace_id": DEFAULT_WORKSPACE_ID, "parent_id": None}):
            await db.groups.insert_one({"id": f"grp-{uuid.uuid4().hex[:8]}", "name": name, "parent_id": None, "workspace_id": DEFAULT_WORKSPACE_ID, "created_at": now})
    admin = await db.users.find_one({"is_super_admin": True}, {"_id": 0, "user_id": 1})
    for r in await db.routers.find({"$or": [{"group_id": {"$exists": False}}, {"workspace_id": {"$exists": False}}]}, {"_id": 0}).to_list(500):
        g = await db.groups.find_one({"name": r.get("group", "Unassigned"), "workspace_id": DEFAULT_WORKSPACE_ID}, {"_id": 0})
        if not g:
            g = {"id": f"grp-{uuid.uuid4().hex[:8]}", "name": r.get("group", "Unassigned"), "parent_id": None, "workspace_id": DEFAULT_WORKSPACE_ID, "created_at": now}
            await db.groups.insert_one(dict(g))
        await db.routers.update_one({"id": r["id"]}, {"$set": {"group_id": g["id"], "workspace_id": DEFAULT_WORKSPACE_ID, "created_by": r.get("created_by") or (admin or {}).get("user_id")}})

@app.on_event("startup")
async def startup():
    await seed_auth()
    await migrate_legacy()
    try:
        from storage import init_storage
        await asyncio.to_thread(init_storage)
    except Exception as exc: print(f"[storage] init failed: {exc}")
    try:
        from monitor import ensure_indexes
        await ensure_indexes()
    except Exception as exc: print(f"[monitor] index setup failed: {exc}")
    try:
        from syslogd import start_syslog
        state = await start_syslog()
        print(f"[syslog] listening={state.get('listening')} port={state.get('port')} {state.get('error', '')}")
    except Exception as exc: print(f"[syslog] start failed: {exc}")

from engine import engine_router
from monitor import monitor_router
from topology import topology_router
from sshterm import ssh_router
from syslogd import syslog_router
from display import display_admin, public_router
from boards import boards_router

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(engine_router)
app.include_router(monitor_router)
app.include_router(topology_router)
app.include_router(ssh_router)
app.include_router(syslog_router)
app.include_router(display_admin)
app.include_router(public_router)
app.include_router(boards_router)
app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])

@app.on_event("shutdown")
async def shutdown():
    with _ROS_LOCK:
        for entry in _ROS_POOLS.values():
            try: entry["pool"].disconnect()
            except Exception: pass
        _ROS_POOLS.clear()
