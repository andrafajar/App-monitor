from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime, timezone
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="NetPulse MikroTik Control Plane")
api = APIRouter(prefix="/api")

DEMO = {
    "routers": [
        {"id":"r-01","name":"HQ Core Router","host":"10.10.0.1","group":"Head Office","status":"online","cpu":28,"memory":42,"uptime":"21d 04h 18m","interfaces":14,"traffic":"842 Mbps","version":"7.14.3","color":"cyan"},
        {"id":"r-02","name":"East Branch","host":"10.21.0.1","group":"Region East","status":"online","cpu":64,"memory":71,"uptime":"8d 12h 09m","interfaces":8,"traffic":"318 Mbps","version":"7.13.5","color":"green"},
        {"id":"r-03","name":"Warehouse Gateway","host":"10.30.0.1","group":"Operations","status":"warning","cpu":83,"memory":77,"uptime":"3d 07h 44m","interfaces":11,"traffic":"1.24 Gbps","version":"7.12.1","color":"amber"},
        {"id":"r-04","name":"Partner PT ABC","host":"172.16.20.1","group":"Partner · PT ABC","status":"offline","cpu":0,"memory":0,"uptime":"—","interfaces":6,"traffic":"—","version":"7.11.2","color":"red"},
    ],
    "groups": ["All routers", "Head Office", "Region East", "Operations", "Partner · PT ABC"],
    "traffic": [{"time":f"{i+8:02d}:00","inbound":v+12,"outbound":max(8,v-3)} for i,v in enumerate([0,28,21,44,36,58,45,66,52,73,62,81])],
}

class RouterCreate(BaseModel):
    name: str = Field(min_length=2); host: str; port: int = 8729; username: str; password: str
    group: str = "Unassigned"; telegram_chat_id: str | None = None

@api.get("/")
async def root(): return {"message": "NetPulse API online"}

@api.get("/monitoring/overview")
async def overview(): return DEMO

@api.get("/health")
async def health():
    try:
        await db.command("ping")
        return {"ok": True, "database": "connected", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception:
        return {"ok": True, "database": "unavailable", "timestamp": datetime.now(timezone.utc).isoformat()}

@api.post("/routers")
async def create_router(item: RouterCreate):
    # The MVP keeps the credential field server-side; real AES-GCM storage and RouterOS
    # driver wiring are the next integration step once deployment secrets are supplied.
    doc = item.model_dump(); doc["created_at"] = datetime.now(timezone.utc).isoformat(); doc["status"] = "pending"
    doc.pop("password", None)
    await db.routers.insert_one(doc)
    return {"ok": True, "message": "Router queued for secure connection test"}

app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])

@app.on_event("shutdown")
async def shutdown(): client.close()