import os, uuid, bcrypt, jwt, httpx
from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from core import db, credential_box, MODULES, LEVELS, level_of, DEFAULT_WORKSPACE_ID

JWT_ALGORITHM = "HS256"
COOKIE_OPTS = dict(httponly=True, secure=True, samesite="none", path="/")
auth_router = APIRouter(prefix="/api/auth")


def hash_password(password: str) -> str: return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
def verify_password(plain: str, hashed: str) -> bool:
    try: return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception: return False
def jwt_secret() -> str: return os.environ["JWT_SECRET"]
def create_access_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(hours=12), "type": "access"}, jwt_secret(), algorithm=JWT_ALGORITHM)
def create_refresh_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}, jwt_secret(), algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, user_id: str) -> str:
    access = create_access_token(user_id)
    response.set_cookie("access_token", access, max_age=43200, **COOKIE_OPTS)
    response.set_cookie("refresh_token", create_refresh_token(user_id), max_age=604800, **COOKIE_OPTS)
    return access


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=120); password: str = Field(min_length=1, max_length=200)
class SessionIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=300)
class RosCredsIn(BaseModel):
    username: str = Field(min_length=1, max_length=64); password: str = Field(min_length=1, max_length=200)
class PasswordIn(BaseModel):
    current_password: str = Field(max_length=200); new_password: str = Field(min_length=8, max_length=200)


async def _user_by_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") == "access": return await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
    except jwt.InvalidTokenError: pass
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session: return None
    expires = session["expires_at"]
    if isinstance(expires, str): expires = datetime.fromisoformat(expires)
    if expires.tzinfo is None: expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc): return None
    return await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})


async def enrich_user(user: dict) -> dict[str, Any]:
    role = await db.roles.find_one({"id": user.get("role_id")}, {"_id": 0}) if user.get("role_id") else None
    privileges = dict((role or {}).get("privileges") or {})
    if user.get("is_super_admin"): privileges = {m: "write" for m in MODULES}
    role_groups = list((role or {}).get("group_ids") or [])
    effective = user.get("allowed_group_ids") if user.get("allowed_group_ids") is not None else role_groups
    if user.get("is_super_admin"): ws_ids = [w["id"] for w in await db.workspaces.find({}, {"_id": 0, "id": 1}).to_list(200)]
    else: ws_ids = list(user.get("workspace_ids") or [])
    public = {k: v for k, v in user.items() if k not in ("password_hash", "ros_password_enc")}
    public.update({"role": {"id": role["id"], "name": role["name"]} if role else None, "privileges": privileges,
                   "effective_group_ids": effective, "workspace_ids": ws_ids,
                   "has_ros_credentials": bool(user.get("ros_username") and user.get("ros_password_enc")),
                   "ros_username": user.get("ros_username") or ""})
    return public


async def get_current_user(request: Request) -> dict[str, Any]:
    token = request.cookies.get("access_token") or request.cookies.get("session_token")
    user = await _user_by_token(token) if token else None
    if not user:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "): user = await _user_by_token(header[7:])
    if not user: raise HTTPException(401, "Not authenticated")
    if user.get("disabled"): raise HTTPException(403, "Account is disabled")
    return await enrich_user(user)


def require(module: str, level: str = "read"):
    async def dep(user: dict = Depends(get_current_user)):
        if level_of(user, module) < LEVELS[level]: raise HTTPException(403, f"Requires {level} access to {module}")
        return user
    return dep


async def current_workspace(request: Request, user: dict) -> str:
    wanted = request.headers.get("X-Workspace") or request.query_params.get("workspace")
    if wanted:
        if wanted not in user["workspace_ids"]: raise HTTPException(403, "No access to this workspace")
        return wanted
    if not user["workspace_ids"]: raise HTTPException(403, "You are not assigned to any workspace yet")
    return DEFAULT_WORKSPACE_ID if DEFAULT_WORKSPACE_ID in user["workspace_ids"] else user["workspace_ids"][0]


@auth_router.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    ident = f"{request.client.host if request.client else 'x'}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": ident})
    now = datetime.now(timezone.utc)
    if attempt and attempt.get("count", 0) >= 5:
        locked_until = attempt.get("locked_until")
        if isinstance(locked_until, str): locked_until = datetime.fromisoformat(locked_until)
        if locked_until and locked_until > now: raise HTTPException(429, "Too many failed attempts, try again in 15 minutes")
        await db.login_attempts.delete_one({"identifier": ident})
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        await db.login_attempts.update_one({"identifier": ident}, {"$inc": {"count": 1}, "$set": {"locked_until": (now + timedelta(minutes=15)).isoformat()}}, upsert=True)
        raise HTTPException(401, "Invalid email or password")
    if user.get("disabled"): raise HTTPException(403, "Account is disabled")
    await db.login_attempts.delete_one({"identifier": ident})
    token = set_auth_cookies(response, user["user_id"])
    return {"user": await enrich_user(user), "access_token": token}


@auth_router.post("/session")
async def google_session(body: SessionIn, response: Response):
    # REMINDER: the Emergent session-data exchange must happen server-side only.
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data", headers={"X-Session-ID": body.session_id})
    except httpx.HTTPError: raise HTTPException(502, "Auth provider unreachable")
    if r.status_code != 200: raise HTTPException(401, "Invalid or expired Google session")
    data = r.json(); email = (data.get("email") or "").lower()
    if not email: raise HTTPException(401, "Google account has no email")
    user = await db.users.find_one({"email": email}, {"_id": 0})
    now = datetime.now(timezone.utc)
    if not user:
        viewer = await db.roles.find_one({"builtin": "viewer"}, {"_id": 0, "id": 1})
        user = {"user_id": f"user_{uuid.uuid4().hex[:12]}", "email": email, "name": data.get("name") or email, "picture": data.get("picture"),
                "is_super_admin": False, "role_id": viewer["id"] if viewer else None, "workspace_ids": [], "allowed_group_ids": None,
                "auth_provider": "google", "created_at": now.isoformat()}
        await db.users.insert_one(dict(user))
    else:
        await db.users.update_one({"email": email}, {"$set": {"picture": data.get("picture") or user.get("picture"), "name": user.get("name") or data.get("name")}})
    if user.get("disabled"): raise HTTPException(403, "Account is disabled")
    token = data["session_token"]
    await db.user_sessions.insert_one({"user_id": user["user_id"], "session_token": token, "expires_at": now + timedelta(days=7), "created_at": now})
    response.set_cookie("session_token", token, max_age=604800, **COOKIE_OPTS)
    return {"user": await enrich_user(user), "access_token": token}


@auth_router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token: raise HTTPException(401, "No refresh token")
    try: payload = jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError: raise HTTPException(401, "Invalid refresh token")
    if payload.get("type") != "refresh": raise HTTPException(401, "Invalid token type")
    user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0})
    if not user: raise HTTPException(401, "User not found")
    return {"access_token": set_auth_cookies(response, user["user_id"])}


@auth_router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token: await db.user_sessions.delete_one({"session_token": token})
    for name in ("access_token", "refresh_token", "session_token"): response.delete_cookie(name, path="/")
    return {"ok": True}


@auth_router.get("/me")
async def me(user: dict = Depends(get_current_user)): return user


@auth_router.put("/me/ros-credentials")
async def set_ros_credentials(body: RosCredsIn, user: dict = Depends(get_current_user)):
    enc = credential_box().encrypt(body.password.encode()).decode()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"ros_username": body.username.strip(), "ros_password_enc": enc, "ros_updated_at": datetime.now(timezone.utc).isoformat()}})
    from server import drop_user_pools
    drop_user_pools(user["user_id"])
    return {"ok": True, "ros_username": body.username.strip(), "has_ros_credentials": True}


@auth_router.delete("/me/ros-credentials")
async def clear_ros_credentials(user: dict = Depends(get_current_user)):
    await db.users.update_one({"user_id": user["user_id"]}, {"$unset": {"ros_username": "", "ros_password_enc": ""}})
    from server import drop_user_pools
    drop_user_pools(user["user_id"])
    return {"ok": True, "has_ros_credentials": False}


@auth_router.put("/me/password")
async def change_password(body: PasswordIn, user: dict = Depends(get_current_user)):
    doc = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 1})
    if doc.get("password_hash") and not verify_password(body.current_password, doc["password_hash"]): raise HTTPException(401, "Current password is incorrect")
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"password_hash": hash_password(body.new_password)}})
    return {"ok": True}


async def seed_auth():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token")
    await db.login_attempts.create_index("identifier")
    now = datetime.now(timezone.utc).isoformat()
    if not await db.workspaces.find_one({"id": DEFAULT_WORKSPACE_ID}):
        await db.workspaces.insert_one({"id": DEFAULT_WORKSPACE_ID, "name": "Central Operations", "created_at": now})
    if not await db.roles.find_one({"builtin": "viewer"}):
        await db.roles.insert_one({"id": f"role-{uuid.uuid4().hex[:8]}", "name": "Viewer", "description": "Read-only access to shared routers", "builtin": "viewer",
                                   "privileges": {m: ("read" if m in ("overview", "routers", "groups", "alarms") else "none") for m in MODULES}, "group_ids": [], "created_at": now})
    email = os.environ["ADMIN_EMAIL"].lower(); password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": email})
    if not existing:
        await db.users.insert_one({"user_id": f"user_{uuid.uuid4().hex[:12]}", "email": email, "name": "Super Admin", "password_hash": hash_password(password),
                                   "is_super_admin": True, "role_id": None, "workspace_ids": [DEFAULT_WORKSPACE_ID], "allowed_group_ids": None, "auth_provider": "local", "created_at": now})
    elif not existing.get("password_hash") or not verify_password(password, existing["password_hash"]):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(password), "is_super_admin": True}})
