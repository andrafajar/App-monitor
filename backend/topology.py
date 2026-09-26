"""Manually arranged topology map: device nodes with saved positions, links drawn between scanned interfaces."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from core import db
from auth import require, current_workspace

topology_router = APIRouter(prefix="/api")
now = lambda: datetime.now(timezone.utc)


class NodeIn(BaseModel):
    x: float = Field(ge=-2000, le=4000); y: float = Field(ge=-2000, le=4000)


class LinkIn(BaseModel):
    a_device: str; a_iface: str = Field(max_length=80)
    b_device: str; b_iface: str = Field(max_length=80)
    label: str = Field("", max_length=60)


async def link_state(device_id: str, iface: str, cache: dict) -> dict:
    if device_id not in cache:
        cache[device_id] = await db.snmp_state.find_one({"device_id": device_id}, {"_id": 0, "counters": 0}) or {}
    rows = (cache[device_id].get("interfaces") or [])
    row = next((r for r in rows if r["name"] == iface), None)
    if not row: return {"status": "unknown", "rx_mbps": None, "tx_mbps": None}
    return {"status": row["status"], "rx_mbps": row.get("rx_mbps"), "tx_mbps": row.get("tx_mbps")}


async def topology_payload(ws: str, device_filter: dict | None = None) -> dict:
    devices = await db.routers.find({"workspace_id": ws, **(device_filter or {})}, {"_id": 0}).to_list(500)
    ids = {d["id"] for d in devices}
    positions = {n["device_id"]: n for n in await db.topo_nodes.find({"workspace_id": ws}, {"_id": 0}).to_list(500)}
    nodes, cache = [], {}
    for i, d in enumerate(sorted(devices, key=lambda x: x["name"])):
        pos = positions.get(d["id"]) or {}
        nodes.append({"device_id": d["id"], "name": d["name"], "device_type": d.get("device_type") or "mikrotik", "status": d.get("status", "pending"),
                      "group": d.get("group", "—"), "cpu": d.get("cpu", 0), "ping_ms": d.get("ping_ms"),
                      "x": pos.get("x", 90 + (i % 4) * 230), "y": pos.get("y", 80 + (i // 4) * 170)})
    links = []
    for link in await db.topo_links.find({"workspace_id": ws}, {"_id": 0}).to_list(500):
        if link["a_device"] not in ids or link["b_device"] not in ids: continue
        a, b = await link_state(link["a_device"], link["a_iface"], cache), await link_state(link["b_device"], link["b_iface"], cache)
        status = "down" if "down" in (a["status"], b["status"]) else ("up" if "up" in (a["status"], b["status"]) else "unknown")
        links.append({**{k: link[k] for k in ("id", "a_device", "a_iface", "b_device", "b_iface", "label")}, "status": status,
                      "rx_mbps": a["rx_mbps"], "tx_mbps": a["tx_mbps"], "a_status": a["status"], "b_status": b["status"]})
    return {"nodes": nodes, "links": links, "generated_at": now().isoformat()}


@topology_router.get("/topology")
async def get_topology(request: Request, user: dict = Depends(require("overview", "read"))):
    from server import router_filter
    ws = await current_workspace(request, user)
    scope = router_filter(user, ws)
    return await topology_payload(ws, {k: v for k, v in scope.items() if k != "workspace_id"})


@topology_router.get("/topology/interfaces")
async def topology_interfaces(request: Request, user: dict = Depends(require("overview", "read"))):
    """Interface pick-lists per device, straight from the last SNMP sweep."""
    from server import router_filter
    ws = await current_workspace(request, user)
    devices = await db.routers.find(router_filter(user, ws), {"_id": 0, "id": 1, "name": 1, "snmp_enabled": 1}).to_list(500)
    states = {s["device_id"]: s for s in await db.snmp_state.find({}, {"_id": 0, "counters": 0}).to_list(500)}
    return {"items": [{"device_id": d["id"], "name": d["name"], "snmp_enabled": bool(d.get("snmp_enabled")),
                       "error": (states.get(d["id"]) or {}).get("error"),
                       "interfaces": [{"name": i["name"], "status": i["status"]} for i in (states.get(d["id"]) or {}).get("interfaces") or []]} for d in devices]}


@topology_router.put("/topology/nodes/{device_id}")
async def move_node(device_id: str, body: NodeIn, request: Request, user: dict = Depends(require("overview", "write"))):
    from server import visible_router
    device = await visible_router(device_id, request, user)
    await db.topo_nodes.update_one({"device_id": device_id}, {"$set": {"device_id": device_id, "workspace_id": device["workspace_id"],
                                                                      "x": body.x, "y": body.y, "updated_at": now().isoformat()}}, upsert=True)
    return {"ok": True, "device_id": device_id, "x": body.x, "y": body.y}


@topology_router.post("/topology/links")
async def create_link(body: LinkIn, request: Request, user: dict = Depends(require("overview", "write"))):
    from server import audit, visible_router
    if body.a_device == body.b_device and body.a_iface == body.b_iface: raise HTTPException(422, "Pick two different interfaces")
    a = await visible_router(body.a_device, request, user)
    await visible_router(body.b_device, request, user)
    if await db.topo_links.find_one({"workspace_id": a["workspace_id"], "a_device": body.a_device, "a_iface": body.a_iface, "b_device": body.b_device, "b_iface": body.b_iface}):
        raise HTTPException(409, "That link already exists")
    doc = {"id": f"lnk-{uuid.uuid4().hex[:8]}", "workspace_id": a["workspace_id"], **body.model_dump(), "created_by": user["email"], "created_at": now().isoformat()}
    await db.topo_links.insert_one(dict(doc))
    await audit(user, "topology.link", doc["id"], f"{body.a_device}:{body.a_iface} ↔ {body.b_device}:{body.b_iface}")
    return {"ok": True, "link": {k: doc[k] for k in ("id", "a_device", "a_iface", "b_device", "b_iface", "label")}}


@topology_router.delete("/topology/links/{link_id}")
async def delete_link(link_id: str, request: Request, user: dict = Depends(require("overview", "write"))):
    ws = await current_workspace(request, user)
    result = await db.topo_links.delete_one({"id": link_id, "workspace_id": ws})
    if result.deleted_count == 0: raise HTTPException(404, "Link not found")
    return {"ok": True, "id": link_id}
