"""Public, read-only NOC display board (no login) exposed per workspace behind a share token."""
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from core import db
from auth import require

public_router = APIRouter(prefix="/api/public")
display_admin = APIRouter(prefix="/api")
now = lambda: datetime.now(timezone.utc)


class DisplayIn(BaseModel):
    enabled: bool = True
    show_ips: bool = False
    title: str = Field("", max_length=80)
    rotate: bool = False


def display_public(ws: dict) -> dict:
    cfg = ws.get("public_display") or {}
    return {"enabled": bool(cfg.get("enabled")), "show_ips": bool(cfg.get("show_ips")), "title": cfg.get("title", ""),
            "token": cfg.get("token"), "path": f"/display/{cfg['token']}" if cfg.get("token") else None, "updated_at": cfg.get("updated_at")}


@display_admin.get("/workspaces/{ws_id}/public-display")
async def get_display(ws_id: str, user: dict = Depends(require("workspaces", "read"))):
    ws = await db.workspaces.find_one({"id": ws_id}, {"_id": 0})
    if not ws or (ws_id not in user["workspace_ids"]): raise HTTPException(404, "Workspace not found")
    return {"display": display_public(ws)}


@display_admin.put("/workspaces/{ws_id}/public-display")
async def set_display(ws_id: str, body: DisplayIn, user: dict = Depends(require("workspaces", "write"))):
    ws = await db.workspaces.find_one({"id": ws_id}, {"_id": 0})
    if not ws or (ws_id not in user["workspace_ids"]): raise HTTPException(404, "Workspace not found")
    cfg = ws.get("public_display") or {}
    token = cfg.get("token")
    if body.rotate or not token: token = secrets.token_urlsafe(18)
    cfg = {"enabled": body.enabled, "show_ips": body.show_ips, "title": body.title.strip(), "token": token, "updated_at": now().isoformat(), "updated_by": user["email"]}
    await db.workspaces.update_one({"id": ws_id}, {"$set": {"public_display": cfg}})
    return {"ok": True, "display": display_public({"public_display": cfg})}


@public_router.get("/display/{token}")
async def display_board(token: str):
    """Read-only board: device health, live bandwidth and alarms. No credentials, hosts hidden unless allowed."""
    ws = await db.workspaces.find_one({"public_display.token": token, "public_display.enabled": True}, {"_id": 0})
    if not ws: raise HTTPException(404, "This display link is not active")
    cfg = ws["public_display"]
    groups = {g["id"]: g["name"] for g in await db.groups.find({"workspace_id": ws["id"]}, {"_id": 0, "id": 1, "name": 1}).to_list(300)}
    devices = await db.routers.find({"workspace_id": ws["id"]}, {"_id": 0}).sort("name", 1).to_list(300)
    board = [{"id": d["id"], "name": d["name"], "status": d.get("status", "pending"), "cpu": d.get("cpu", 0), "memory": d.get("memory", 0),
              "uptime": d.get("uptime", "—"), "version": d.get("version", "—"), "group": groups.get(d.get("group_id"), d.get("group", "—")),
              "host": d.get("host") if cfg.get("show_ips") else None, "last_probed_at": d.get("last_probed_at")} for d in devices]
    series = await db.traffic_series.find({"workspace_id": ws["id"]}, {"_id": 0}).sort("ts", -1).to_list(60)
    alarms = await db.alarm_log.find({"workspace_id": ws["id"]}, {"_id": 0, "roles_notified": 0, "roles_failed": 0}).sort("created_at", -1).to_list(12)
    since = (now() - timedelta(hours=24)).isoformat()
    return {"workspace": {"id": ws["id"], "name": ws["name"], "title": cfg.get("title") or ws["name"]},
            "devices": board,
            "counts": {"total": len(board), "online": sum(1 for d in board if d["status"] == "online"), "offline": sum(1 for d in board if d["status"] == "offline"),
                       "alarms_24h": await db.alarm_log.count_documents({"workspace_id": ws["id"], "created_at": {"$gt": since}})},
            "traffic": [{"time": datetime.fromisoformat(s["ts"]).strftime("%H:%M:%S"), "inbound": s["inbound"], "outbound": s["outbound"]} for s in reversed(series)],
            "alarms": [{"kind": a.get("kind"), "device": a.get("router_name"), "detail": a.get("detail", "")[:160], "created_at": a.get("created_at")} for a in alarms],
            "generated_at": now().isoformat()}
