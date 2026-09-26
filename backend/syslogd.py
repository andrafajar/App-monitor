"""Syslog collector (RFC3164 over UDP) with categories, retention and alarm rules per workspace."""
import asyncio, os, re, uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from core import db, DEFAULT_WORKSPACE_ID
from auth import require, current_workspace

syslog_router = APIRouter(prefix="/api")
now = lambda: datetime.now(timezone.utc)
RETENTION_DAYS = 30
SEVERITIES = ["emergency", "alert", "critical", "error", "warning", "notice", "info", "debug"]
CATEGORY_RULES = [
    ("auth-failure", re.compile(r"login failure|authentication fail|invalid user|failed to log|auth.*(failed|denied)|access denied", re.I)),
    ("auth-success", re.compile(r"logged in|login success|user .* logged", re.I)),
    ("link", re.compile(r"link (up|down)|link-(up|down)|interface .*(up|down)", re.I)),
    ("ppp", re.compile(r"pppoe|l2tp|sstp|ovpn|ppp ", re.I)),
    ("dhcp", re.compile(r"dhcp", re.I)),
    ("wireless", re.compile(r"wlan|wireless|wifi", re.I)),
    ("firewall", re.compile(r"firewall|drop input|reject", re.I)),
    ("system", re.compile(r"reboot|shutdown|upgrade|config|script|watchdog", re.I)),
]
CATEGORIES = ["auth-failure", "auth-success", "link", "ppp", "dhcp", "wireless", "firewall", "system", "other"]
HEADER_RE = re.compile(r"^<(?P<pri>\d{1,3})>(?P<rest>.*)$", re.S)
SYSLOG_TS = re.compile(r"^([A-Z][a-z]{2}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)$", re.S)


class SyslogRuleIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    category: str = Field("any", max_length=20)
    pattern: str = Field("", max_length=200)
    severity_max: int = Field(7, ge=0, le=7)
    enabled: bool = True
    throttle_minutes: int = Field(15, ge=1, le=1440)


def categorize(message: str) -> str:
    for name, rx in CATEGORY_RULES:
        if rx.search(message): return name
    return "other"


def parse_syslog(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", "replace").strip()
    facility, severity, body = 1, 6, text
    header = HEADER_RE.match(text)
    if header:
        pri = int(header.group("pri"))
        facility, severity = pri // 8, pri % 8
        body = header.group("rest").strip()
    hostname, message = "", body
    stamped = SYSLOG_TS.match(body)
    if stamped:
        hostname, message = stamped.group(2), stamped.group(3).strip()
    tag = ""
    topics = re.match(r"^([a-z][a-z0-9\-]*(?:,[a-z0-9\-]+)+)\s+(.*)$", message, re.S)
    named = re.match(r"^([A-Za-z0-9_\-/.\[\]]{1,32}):\s+(.*)$", message, re.S)
    if topics: tag, message = topics.group(1), topics.group(2).strip()
    elif named: tag, message = named.group(1), named.group(2).strip()
    return {"facility": facility, "severity": severity, "severity_name": SEVERITIES[severity], "host": hostname, "tag": tag, "message": message or body}


async def resolve_device(source_ip: str) -> dict[str, Any]:
    fields = {"_id": 0, "id": 1, "name": 1, "workspace_id": 1, "group_id": 1}
    router = await db.routers.find_one({"host": source_ip}, fields)
    return router or await db.devices.find_one({"host": source_ip}, fields) or {}


async def store_message(source_ip: str, raw: bytes):
    parsed = parse_syslog(raw)
    device = await resolve_device(source_ip)
    stamp = now()
    doc = {"id": f"log-{uuid.uuid4().hex[:10]}", "source_ip": source_ip, "router_id": device.get("id"), "router_name": device.get("name") or source_ip,
           "workspace_id": device.get("workspace_id") or DEFAULT_WORKSPACE_ID, "group_id": device.get("group_id"),
           "category": categorize(f"{parsed['tag']} {parsed['message']}"), "received_dt": stamp, "created_at": stamp.isoformat(), **parsed}
    await db.syslog.insert_one(dict(doc))
    await evaluate_rules(doc, device)


async def evaluate_rules(doc: dict, device: dict):
    rules = await db.syslog_rules.find({"workspace_id": doc["workspace_id"], "enabled": True}, {"_id": 0}).to_list(100)
    if not rules: return
    from server import deliver_alarm
    haystack = f"{doc['tag']} {doc['message']}"
    for rule in rules:
        if rule["category"] not in ("any", doc["category"]): continue
        if doc["severity"] > rule["severity_max"]: continue
        if rule.get("pattern"):
            try:
                if not re.search(rule["pattern"], haystack, re.I): continue
            except re.error: continue
        cutoff = (now() - timedelta(minutes=rule.get("throttle_minutes", 15))).isoformat()
        if await db.alarm_log.find_one({"kind": "syslog-match", "rule_id": rule["id"], "created_at": {"$gt": cutoff}}): continue
        target = {**(device or {}), "id": doc.get("router_id") or doc["source_ip"], "name": doc["router_name"], "workspace_id": doc["workspace_id"], "group_id": doc.get("group_id")}
        await deliver_alarm(target, "syslog-match", f"[{rule['name']}] {doc['severity_name']} · {haystack[:180]}", source="syslog",
                            extra={"rule_id": rule["id"], "rule_name": rule["name"], "source_ip": doc["source_ip"]})


class SyslogProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, addr):
        asyncio.get_running_loop().create_task(store_message(addr[0], data))


async def start_syslog() -> dict[str, Any]:
    await db.syslog.create_index("received_dt", expireAfterSeconds=RETENTION_DAYS * 86400)
    await db.syslog.create_index([("workspace_id", 1), ("created_at", -1)])
    port = int(os.environ.get("SYSLOG_UDP_PORT", 514))
    loop = asyncio.get_running_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(SyslogProtocol, local_addr=("0.0.0.0", port))
        STATE.update({"listening": True, "port": port, "transport": transport})
    except Exception as exc:
        STATE.update({"listening": False, "port": port, "error": f"{type(exc).__name__}: {exc}"})
    if not await db.syslog_rules.find_one({"workspace_id": DEFAULT_WORKSPACE_ID}):
        await db.syslog_rules.insert_one({"id": f"slr-{uuid.uuid4().hex[:8]}", "workspace_id": DEFAULT_WORKSPACE_ID, "name": "Login failure", "category": "auth-failure",
                                          "pattern": "", "severity_max": 7, "enabled": True, "throttle_minutes": 15, "created_at": now().isoformat()})
    return STATE


STATE: dict[str, Any] = {"listening": False, "port": int(os.environ.get("SYSLOG_UDP_PORT", 514))}


# ---------- API ----------
@syslog_router.get("/syslog/status")
async def syslog_status(request: Request, user: dict = Depends(require("syslog", "read"))):
    ws = await current_workspace(request, user)
    total = await db.syslog.count_documents({"workspace_id": ws})
    last = await db.syslog.find_one({"workspace_id": ws}, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
    return {"listening": STATE.get("listening"), "port": STATE.get("port"), "error": STATE.get("error"), "retention_days": RETENTION_DAYS,
            "stored": total, "last_message_at": (last or {}).get("created_at"), "categories": CATEGORIES, "severities": SEVERITIES}


@syslog_router.get("/syslog")
async def list_syslog(request: Request, q: str = "", category: str = "", severity_max: int = 7, router_id: str = "", limit: int = 200,
                      user: dict = Depends(require("syslog", "read"))):
    ws = await current_workspace(request, user)
    query: dict[str, Any] = {"workspace_id": ws, "severity": {"$lte": max(0, min(7, severity_max))}}
    if category: query["category"] = category
    if router_id: query["router_id"] = router_id
    if q: query["$or"] = [{"message": {"$regex": re.escape(q), "$options": "i"}}, {"tag": {"$regex": re.escape(q), "$options": "i"}}, {"source_ip": q}]
    rows = await db.syslog.find(query, {"_id": 0, "received_dt": 0}).sort("created_at", -1).to_list(max(1, min(500, limit)))
    counts = await db.syslog.aggregate([{"$match": {"workspace_id": ws}}, {"$group": {"_id": "$category", "count": {"$sum": 1}}}]).to_list(30)
    return {"items": rows, "by_category": {c["_id"]: c["count"] for c in counts}}


@syslog_router.delete("/syslog")
async def clear_syslog(request: Request, user: dict = Depends(require("syslog", "write"))):
    ws = await current_workspace(request, user)
    result = await db.syslog.delete_many({"workspace_id": ws})
    return {"ok": True, "deleted": result.deleted_count}


@syslog_router.get("/syslog/rules")
async def list_rules(request: Request, user: dict = Depends(require("syslog", "read"))):
    ws = await current_workspace(request, user)
    return {"items": await db.syslog_rules.find({"workspace_id": ws}, {"_id": 0}).sort("created_at", 1).to_list(100), "categories": CATEGORIES, "severities": SEVERITIES}


@syslog_router.post("/syslog/rules")
async def create_rule(body: SyslogRuleIn, request: Request, user: dict = Depends(require("syslog", "write"))):
    ws = await current_workspace(request, user)
    if body.category not in CATEGORIES + ["any"]: raise HTTPException(422, "Unknown category")
    if body.pattern:
        try: re.compile(body.pattern)
        except re.error: raise HTTPException(422, "Invalid regular expression")
    doc = {**body.model_dump(), "id": f"slr-{uuid.uuid4().hex[:8]}", "workspace_id": ws, "created_at": now().isoformat(), "created_by": user["email"]}
    await db.syslog_rules.insert_one(dict(doc))
    return {"ok": True, "rule": doc}


@syslog_router.put("/syslog/rules/{rule_id}")
async def update_rule(rule_id: str, body: SyslogRuleIn, request: Request, user: dict = Depends(require("syslog", "write"))):
    ws = await current_workspace(request, user)
    if body.pattern:
        try: re.compile(body.pattern)
        except re.error: raise HTTPException(422, "Invalid regular expression")
    r = await db.syslog_rules.update_one({"id": rule_id, "workspace_id": ws}, {"$set": {**body.model_dump(), "updated_at": now().isoformat()}})
    if r.matched_count == 0: raise HTTPException(404, "Rule not found")
    return {"ok": True, "id": rule_id}


@syslog_router.delete("/syslog/rules/{rule_id}")
async def delete_rule(rule_id: str, request: Request, user: dict = Depends(require("syslog", "write"))):
    ws = await current_workspace(request, user)
    r = await db.syslog_rules.delete_one({"id": rule_id, "workspace_id": ws})
    if r.deleted_count == 0: raise HTTPException(404, "Rule not found")
    return {"ok": True, "id": rule_id}


@syslog_router.post("/syslog/test-message")
async def inject_test(request: Request, user: dict = Depends(require("syslog", "write"))):
    """Inject a synthetic message so operators can verify categories and rules without waiting for a device."""
    ws = await current_workspace(request, user)
    router = await db.routers.find_one({"workspace_id": ws}, {"_id": 0, "host": 1})
    source = (router or {}).get("host", "127.0.0.1")
    await store_message(source, b"<38>Jan  1 00:00:00 netpulse system,error,critical login failure for user admin from 203.0.113.9 via ssh")
    return {"ok": True, "source_ip": source}
