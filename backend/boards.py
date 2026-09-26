"""Custom overview boards: several tabs per workspace, each with its own widgets and device scope."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from core import db
from auth import require, current_workspace

boards_router = APIRouter(prefix="/api")
now_iso = lambda: datetime.now(timezone.utc).isoformat()
WIDGETS = ["metrics", "traffic", "alarms", "devices", "syslog"]
DEFAULT_WIDGETS = ["metrics", "traffic", "alarms", "devices"]
CARD_TYPES = ("iface-traffic", "device-count", "device-ping")
CARD_HOURS = (0, 24, 48, 168, 720)  # live, 1 day, 2 days, 1 week, last month (retention limit)


class CardIn(BaseModel):
    id: str = Field("", max_length=24)
    type: str = Field(pattern="^(iface-traffic|device-count|device-ping)$")
    title: str = Field("", max_length=50)
    device_id: str = Field("", max_length=40)
    iface: str = Field("", max_length=80)
    hours: int = 24


class BoardIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    widgets: list[str] = Field(default_factory=lambda: list(DEFAULT_WIDGETS))
    cards: list[CardIn] = Field(default_factory=list, max_length=24)
    group_ids: list[str] = Field(default_factory=list, max_length=100)
    device_ids: list[str] = Field(default_factory=list, max_length=300)
    order: int = Field(0, ge=0, le=99)


def clean_cards(cards: list[CardIn]) -> list[dict]:
    out = []
    for card in cards:
        if card.type in ("iface-traffic", "device-ping") and not card.device_id: raise HTTPException(422, "Pick a device for that element")
        if card.type == "iface-traffic" and not card.iface: raise HTTPException(422, "Pick an SNMP interface for the traffic element")
        out.append({"id": card.id or f"card-{uuid.uuid4().hex[:6]}", "type": card.type, "title": card.title.strip(),
                    "device_id": card.device_id, "iface": card.iface, "hours": card.hours if card.hours in CARD_HOURS else 24})
    return out


def clean(board: BoardIn) -> dict:
    widgets = [w for w in board.widgets if w in WIDGETS]
    return {"name": board.name.strip(), "widgets": widgets, "cards": clean_cards(board.cards),
            "group_ids": board.group_ids, "device_ids": board.device_ids, "order": board.order}


@boards_router.get("/dashboards")
async def list_boards(request: Request, user: dict = Depends(require("overview", "read"))):
    ws = await current_workspace(request, user)
    rows = await db.dashboards.find({"workspace_id": ws}, {"_id": 0}).sort("order", 1).to_list(50)
    if not rows:
        doc = {"id": f"dash-{uuid.uuid4().hex[:8]}", "workspace_id": ws, "name": "Overview", "widgets": list(DEFAULT_WIDGETS),
               "cards": [], "group_ids": [], "device_ids": [], "order": 0, "builtin": True, "created_at": now_iso()}
        await db.dashboards.insert_one(dict(doc))
        rows = [doc]
    return {"items": [{**r, "cards": r.get("cards") or []} for r in rows], "widgets": WIDGETS, "card_types": list(CARD_TYPES), "card_hours": list(CARD_HOURS)}


@boards_router.post("/dashboards")
async def create_board(body: BoardIn, request: Request, user: dict = Depends(require("overview", "write"))):
    ws = await current_workspace(request, user)
    if await db.dashboards.count_documents({"workspace_id": ws}) >= 12: raise HTTPException(409, "Maximum of 12 boards per workspace")
    doc = {**clean(body), "id": f"dash-{uuid.uuid4().hex[:8]}", "workspace_id": ws, "created_by": user["email"], "created_at": now_iso()}
    await db.dashboards.insert_one(dict(doc))
    return {"ok": True, "board": doc}


@boards_router.put("/dashboards/{board_id}")
async def update_board(board_id: str, body: BoardIn, request: Request, user: dict = Depends(require("overview", "write"))):
    ws = await current_workspace(request, user)
    r = await db.dashboards.update_one({"id": board_id, "workspace_id": ws}, {"$set": {**clean(body), "updated_at": now_iso()}})
    if r.matched_count == 0: raise HTTPException(404, "Board not found")
    return {"ok": True, "board": await db.dashboards.find_one({"id": board_id}, {"_id": 0})}


@boards_router.delete("/dashboards/{board_id}")
async def delete_board(board_id: str, request: Request, user: dict = Depends(require("overview", "write"))):
    ws = await current_workspace(request, user)
    if await db.dashboards.count_documents({"workspace_id": ws}) <= 1: raise HTTPException(409, "Keep at least one board")
    r = await db.dashboards.delete_one({"id": board_id, "workspace_id": ws})
    if r.deleted_count == 0: raise HTTPException(404, "Board not found")
    return {"ok": True, "id": board_id}
