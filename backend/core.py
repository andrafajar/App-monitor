from dotenv import load_dotenv
from pathlib import Path
import os
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from cryptography.fernet import Fernet

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

MODULES = ["overview", "routers", "groups", "alarms", "audit", "notifications", "backups", "syslog", "users", "roles", "workspaces", "ros_config"]
LEVELS = {"none": 0, "read": 1, "write": 2}
DEFAULT_WORKSPACE_ID = "ws-default"


def credential_box() -> Fernet:
    key = os.environ.get("CREDENTIALS_FERNET_KEY")
    if not key: raise HTTPException(503, "CREDENTIALS_FERNET_KEY is not configured")
    return Fernet(key.encode())


def level_of(user: dict, module: str) -> int:
    if user.get("is_super_admin"): return 2
    return LEVELS.get((user.get("privileges") or {}).get(module, "none"), 0)
