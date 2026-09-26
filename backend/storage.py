import os, requests

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "netpulse"
_storage_key: str | None = None


def init_storage(force: bool = False) -> str:
    global _storage_key
    if _storage_key and not force: return _storage_key
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key: raise RuntimeError("EMERGENT_LLM_KEY is not configured")
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": key}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    for attempt in (1, 2):
        resp = requests.put(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(force=attempt == 2), "Content-Type": content_type}, data=data, timeout=120)
        if resp.status_code == 404 and attempt == 1: continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("storage upload failed")


def get_object(path: str) -> tuple[bytes, str]:
    for attempt in (1, 2):
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(force=attempt == 2)}, timeout=60)
        if resp.status_code == 404 and attempt == 1: continue
        resp.raise_for_status()
        return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
    raise RuntimeError("storage download failed")
