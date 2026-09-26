import uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from core import db, MODULES, LEVELS, DEFAULT_WORKSPACE_ID
from auth import require, current_workspace, hash_password, get_current_user

admin_router = APIRouter(prefix="/api")
now_iso = lambda: datetime.now(timezone.utc).isoformat()


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
class GroupIn(BaseModel):
    name: str = Field(min_length=2, max_length=60); parent_id: str | None = None
class RoleIn(BaseModel):
    name: str = Field(min_length=2, max_length=60); description: str = Field(default="", max_length=200)
    privileges: dict[str, str] = Field(default_factory=dict); group_ids: list[str] = Field(default_factory=list)
class UserIn(BaseModel):
    email: str = Field(min_length=3, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"); name: str = Field(min_length=1, max_length=80)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role_id: str | None = None; is_super_admin: bool = False; disabled: bool = False
    workspace_ids: list[str] = Field(default_factory=list); allowed_group_ids: list[str] | None = None


def clean_privileges(p: dict[str, str]) -> dict[str, str]:
    out = {}
    for m in MODULES:
        lvl = p.get(m, "none")
        if lvl not in LEVELS: raise HTTPException(422, f"Invalid level for {m}")
        out[m] = lvl
    return out


def public_user(u: dict) -> dict: return {k: v for k, v in u.items() if k not in ("password_hash", "ros_password_enc", "_id")}


# ---------- Workspaces ----------
@admin_router.get("/workspaces")
async def list_workspaces(user: dict = Depends(get_current_user)):
    rows = await db.workspaces.find({"id": {"$in": user["workspace_ids"]}}, {"_id": 0}).to_list(200)
    for r in rows: r["router_count"] = await db.routers.count_documents({"workspace_id": r["id"]})
    return {"items": rows}

@admin_router.post("/workspaces")
async def create_workspace(body: WorkspaceIn, user: dict = Depends(require("workspaces", "write"))):
    doc = {"id": f"ws-{uuid.uuid4().hex[:8]}", "name": body.name.strip(), "created_at": now_iso(), "created_by": user["user_id"]}
    await db.workspaces.insert_one(dict(doc))
    if not user.get("is_super_admin"): await db.users.update_one({"user_id": user["user_id"]}, {"$addToSet": {"workspace_ids": doc["id"]}})
    return {"ok": True, "workspace": doc}

@admin_router.put("/workspaces/{ws_id}")
async def rename_workspace(ws_id: str, body: WorkspaceIn, user: dict = Depends(require("workspaces", "write"))):
    if ws_id not in user["workspace_ids"]: raise HTTPException(403, "No access to this workspace")
    r = await db.workspaces.update_one({"id": ws_id}, {"$set": {"name": body.name.strip(), "updated_at": now_iso()}})
    if r.matched_count == 0: raise HTTPException(404, "Workspace not found")
    return {"ok": True, "id": ws_id, "name": body.name.strip()}

@admin_router.delete("/workspaces/{ws_id}")
async def delete_workspace(ws_id: str, user: dict = Depends(require("workspaces", "write"))):
    if ws_id == DEFAULT_WORKSPACE_ID: raise HTTPException(400, "The default workspace cannot be removed")
    if await db.routers.count_documents({"workspace_id": ws_id}): raise HTTPException(409, "Remove routers from this workspace first")
    r = await db.workspaces.delete_one({"id": ws_id})
    if r.deleted_count == 0: raise HTTPException(404, "Workspace not found")
    await db.groups.delete_many({"workspace_id": ws_id})
    await db.users.update_many({}, {"$pull": {"workspace_ids": ws_id}})
    return {"ok": True, "id": ws_id}


# ---------- Groups (hierarchical) ----------
def build_tree(rows: list[dict]) -> list[dict]:
    by_parent: dict[str | None, list[dict]] = {}
    for r in rows: by_parent.setdefault(r.get("parent_id"), []).append(r)
    out: list[dict] = []
    def walk(parent, depth, path):
        for g in sorted(by_parent.get(parent, []), key=lambda x: x["name"].lower()):
            full = [*path, g["name"]]
            out.append({**g, "depth": depth, "path": " › ".join(full)})
            walk(g["id"], depth + 1, full)
    walk(None, 0, [])
    return out

async def groups_for(ws_id: str, user: dict) -> list[dict]:
    rows = await db.groups.find({"workspace_id": ws_id}, {"_id": 0}).to_list(500)
    tree = build_tree(rows)
    for g in tree: g["router_count"] = await db.routers.count_documents({"group_id": g["id"]})
    if user.get("is_super_admin"): return tree
    allowed = set(user["effective_group_ids"])
    return [g for g in tree if g["id"] in allowed]

@admin_router.get("/groups")
async def list_groups(request: Request, user: dict = Depends(require("groups", "read"))):
    ws = await current_workspace(request, user)
    return {"items": await groups_for(ws, user), "all": await groups_for(ws, {**user, "is_super_admin": True}) if user.get("is_super_admin") or user["privileges"].get("groups") == "write" else []}

@admin_router.post("/groups")
async def create_group(body: GroupIn, request: Request, user: dict = Depends(require("groups", "write"))):
    ws = await current_workspace(request, user); name = body.name.strip()
    if body.parent_id and not await db.groups.find_one({"id": body.parent_id, "workspace_id": ws}): raise HTTPException(404, "Parent group not found")
    if await db.groups.find_one({"workspace_id": ws, "name": name, "parent_id": body.parent_id}): raise HTTPException(409, "Group already exists under this parent")
    doc = {"id": f"grp-{uuid.uuid4().hex[:8]}", "name": name, "parent_id": body.parent_id, "workspace_id": ws, "created_at": now_iso()}
    await db.groups.insert_one(dict(doc))
    return {"ok": True, "group": doc}

@admin_router.put("/groups/{group_id}")
async def update_group(group_id: str, body: GroupIn, request: Request, user: dict = Depends(require("groups", "write"))):
    ws = await current_workspace(request, user)
    g = await db.groups.find_one({"id": group_id, "workspace_id": ws}, {"_id": 0})
    if not g: raise HTTPException(404, "Group not found")
    if body.parent_id == group_id: raise HTTPException(400, "A group cannot be its own parent")
    if body.parent_id:
        cursor, seen = body.parent_id, set()
        while cursor and cursor not in seen:
            if cursor == group_id: raise HTTPException(400, "Cannot move a group under its own child")
            seen.add(cursor); p = await db.groups.find_one({"id": cursor}, {"_id": 0, "parent_id": 1}); cursor = (p or {}).get("parent_id")
    name = body.name.strip()
    await db.groups.update_one({"id": group_id}, {"$set": {"name": name, "parent_id": body.parent_id, "updated_at": now_iso()}})
    await db.routers.update_many({"group_id": group_id}, {"$set": {"group": name}})
    return {"ok": True, "group": {**g, "name": name, "parent_id": body.parent_id}}

@admin_router.get("/groups/{group_id}/access")
async def group_access(group_id: str, request: Request, user: dict = Depends(require("groups", "read"))):
    ws = await current_workspace(request, user)
    g = await db.groups.find_one({"id": group_id, "workspace_id": ws}, {"_id": 0})
    if not g: raise HTTPException(404, "Group not found")
    roles = await db.roles.find({"group_ids": group_id}, {"_id": 0}).to_list(200)
    users = await db.users.find({"$or": [{"allowed_group_ids": group_id}, {"role_id": {"$in": [r["id"] for r in roles]}, "allowed_group_ids": None}]}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "role_id": 1}).to_list(500)
    routers = await db.routers.find({"group_id": group_id}, {"_id": 0, "id": 1, "name": 1, "host": 1, "status": 1}).to_list(500)
    return {"group": g, "routers": routers,
            "roles": [{"id": r["id"], "name": r["name"], "telegram_enabled": bool((r.get("telegram") or {}).get("enabled")), "telegram_configured": bool((r.get("telegram") or {}).get("token_enc")), "chat_id": (r.get("telegram") or {}).get("chat_id", "")} for r in roles],
            "users": users}

@admin_router.delete("/groups/{group_id}")
async def delete_group(group_id: str, request: Request, user: dict = Depends(require("groups", "write"))):
    ws = await current_workspace(request, user)
    if await db.groups.count_documents({"parent_id": group_id}): raise HTTPException(409, "Remove or move child groups first")
    if await db.routers.count_documents({"group_id": group_id}): raise HTTPException(409, "Move or remove routers from this group first")
    r = await db.groups.delete_one({"id": group_id, "workspace_id": ws})
    if r.deleted_count == 0: raise HTTPException(404, "Group not found")
    await db.telegram_configs.delete_many({"group_id": group_id})
    await db.roles.update_many({}, {"$pull": {"group_ids": group_id}})
    await db.users.update_many({"allowed_group_ids": group_id}, {"$pull": {"allowed_group_ids": group_id}})
    return {"ok": True, "id": group_id}


# ---------- Roles ----------
@admin_router.get("/roles")
async def list_roles(user: dict = Depends(require("roles", "read"))):
    rows = await db.roles.find({}, {"_id": 0}).to_list(200)
    for r in rows: r["user_count"] = await db.users.count_documents({"role_id": r["id"]})
    return {"items": rows, "modules": MODULES}

@admin_router.post("/roles")
async def create_role(body: RoleIn, user: dict = Depends(require("roles", "write"))):
    if await db.roles.find_one({"name": body.name.strip()}): raise HTTPException(409, "Role name already exists")
    doc = {"id": f"role-{uuid.uuid4().hex[:8]}", "name": body.name.strip(), "description": body.description.strip(), "privileges": clean_privileges(body.privileges), "group_ids": body.group_ids, "created_at": now_iso()}
    await db.roles.insert_one(dict(doc))
    return {"ok": True, "role": doc}

@admin_router.put("/roles/{role_id}")
async def update_role(role_id: str, body: RoleIn, user: dict = Depends(require("roles", "write"))):
    dup = await db.roles.find_one({"name": body.name.strip(), "id": {"$ne": role_id}})
    if dup: raise HTTPException(409, "Role name already exists")
    r = await db.roles.update_one({"id": role_id}, {"$set": {"name": body.name.strip(), "description": body.description.strip(), "privileges": clean_privileges(body.privileges), "group_ids": body.group_ids, "updated_at": now_iso()}})
    if r.matched_count == 0: raise HTTPException(404, "Role not found")
    return {"ok": True, "id": role_id}

@admin_router.delete("/roles/{role_id}")
async def delete_role(role_id: str, user: dict = Depends(require("roles", "write"))):
    role = await db.roles.find_one({"id": role_id}, {"_id": 0})
    if not role: raise HTTPException(404, "Role not found")
    if role.get("builtin"): raise HTTPException(400, "Built-in roles cannot be removed")
    if await db.users.count_documents({"role_id": role_id}): raise HTTPException(409, "Reassign users before removing this role")
    await db.roles.delete_one({"id": role_id})
    return {"ok": True, "id": role_id}


# ---------- Users ----------
@admin_router.get("/users")
async def list_users(user: dict = Depends(require("users", "read"))):
    rows = await db.users.find({}, {"_id": 0, "password_hash": 0, "ros_password_enc": 0}).to_list(500)
    for r in rows: r["has_ros_credentials"] = bool(r.get("ros_username"))
    return {"items": rows}

@admin_router.post("/users")
async def create_user(body: UserIn, user: dict = Depends(require("users", "write"))):
    if body.is_super_admin and not user.get("is_super_admin"): raise HTTPException(403, "Only a Super Admin can grant Super Admin")
    email = body.email.strip().lower()
    if await db.users.find_one({"email": email}): raise HTTPException(409, "Email already registered")
    if body.role_id and not await db.roles.find_one({"id": body.role_id}): raise HTTPException(404, "Role not found")
    doc = {"user_id": f"user_{uuid.uuid4().hex[:12]}", "email": email, "name": body.name.strip(), "is_super_admin": body.is_super_admin, "role_id": body.role_id,
           "workspace_ids": body.workspace_ids, "allowed_group_ids": body.allowed_group_ids, "disabled": body.disabled, "auth_provider": "local" if body.password else "google", "created_at": now_iso()}
    if body.password: doc["password_hash"] = hash_password(body.password)
    await db.users.insert_one(dict(doc))
    return {"ok": True, "user": public_user(doc)}

@admin_router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserIn, user: dict = Depends(require("users", "write"))):
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target: raise HTTPException(404, "User not found")
    if (body.is_super_admin != bool(target.get("is_super_admin"))) and not user.get("is_super_admin"): raise HTTPException(403, "Only a Super Admin can change Super Admin status")
    if target["user_id"] == user["user_id"] and (not body.is_super_admin and target.get("is_super_admin")): raise HTTPException(400, "You cannot remove your own Super Admin status")
    if body.role_id and not await db.roles.find_one({"id": body.role_id}): raise HTTPException(404, "Role not found")
    email = body.email.strip().lower()
    if await db.users.find_one({"email": email, "user_id": {"$ne": user_id}}): raise HTTPException(409, "Email already registered")
    update = {"email": email, "name": body.name.strip(), "is_super_admin": body.is_super_admin, "role_id": body.role_id, "workspace_ids": body.workspace_ids,
              "allowed_group_ids": body.allowed_group_ids, "disabled": body.disabled, "updated_at": now_iso()}
    if body.password: update["password_hash"] = hash_password(body.password)
    await db.users.update_one({"user_id": user_id}, {"$set": update})
    return {"ok": True, "user": public_user({**target, **update})}

@admin_router.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require("users", "write"))):
    if user_id == user["user_id"]: raise HTTPException(400, "You cannot delete your own account")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target: raise HTTPException(404, "User not found")
    if target.get("is_super_admin") and not user.get("is_super_admin"): raise HTTPException(403, "Only a Super Admin can remove a Super Admin")
    await db.users.delete_one({"user_id": user_id}); await db.user_sessions.delete_many({"user_id": user_id})
    return {"ok": True, "user_id": user_id}


@admin_router.get("/meta/modules")
async def modules(user: dict = Depends(get_current_user)): return {"modules": MODULES, "levels": list(LEVELS)}
