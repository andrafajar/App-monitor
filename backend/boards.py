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


class BoardIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    widgets: list[str] = Field(default_factory=lambda: list(DEFAULT_WIDGETS))
    group_ids: list[str] = Field(default_factory=list, max_length=100)
    device_ids: list[str] = Field(default_factory=list, max_length=300)
    order: int = Field(0, ge=0, le=99)


def clean(board: BoardIn) -> dict:
    widgets = [w for w in board.widgets if w in WIDGETS] or list(DEFAULT_WIDGETS)
    return {"name": board.name.strip(), "widgets": widgets, "group_ids": board.group_ids, "device_ids": board.device_ids, "order": board.order}


@boards_router.get("/dashboards")
async def list_boards(request: Request, user: dict = Depends(require("overview", "read"))):
    ws = await current_workspace(request, user)
    rows = await db.dashboards.find({"workspace_id": ws}, {"_id": 0}).sort("order", 1).to_list(50)
    if not rows:
        doc = {"id": f"dash-{uuid.uuid4().hex[:8]}", "workspace_id": ws, "name": "Overview", "widgets": list(DEFAULT_WIDGETS),
               "group_ids": [], "device_ids": [], "order": 0, "builtin": True, "created_at": now_iso()}
        await db.dashboards.insert_one(dict(doc))
        rows = [doc]
    return {"items": rows, "widgets": WIDGETS}


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
