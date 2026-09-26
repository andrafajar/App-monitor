"""Read-only RouterOS resource views, action allow-list, and backup gating tests."""
import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
DEMO = "r-01"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- health / overview ---
def test_health(api):
    r = api.get(f"{BASE_URL}/api/health", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["database"] == "connected", d


def test_overview(api):
    r = api.get(f"{BASE_URL}/api/monitoring/overview", timeout=30)
    assert r.status_code == 200
    d = r.json()
    # demo routers come first; managed routers are appended after them
    assert len(d["routers"]) >= 4
    assert [x["id"] for x in d["routers"][:4]] == ["r-01", "r-02", "r-03", "r-04"]
    assert len(d["groups"]) >= 5 and d["groups"][0] == "All routers"
    assert len(d["traffic"]) == 12
    # ensure no credential leakage in demo payload
    assert all("password" not in k for row in d["routers"] for k in row)


# --- resource allow-list (demo routers not in DB -> 404 safety gate) ---
@pytest.mark.parametrize("resource", ["interfaces", "logs", "ppp-profiles", "ppp-secrets", "system-clock", "addresses", "firewall", "routes"])
def test_allowlisted_resources_return_404_for_demo_router(api, resource):
    r = api.get(f"{BASE_URL}/api/routers/{DEMO}/resources/{resource}", timeout=30)
    assert r.status_code == 404, f"{resource}: {r.status_code} {r.text[:200]}"
    assert r.json()["detail"] == "Router not found in managed inventory"


def test_invalid_resource_rejected(api):
    r = api.get(f"{BASE_URL}/api/routers/{DEMO}/resources/invalid", timeout=30)
    assert r.status_code == 400
    assert r.json()["detail"] == "Resource is not allow-listed"


def test_reveal_param_accepted(api):
    r = api.get(f"{BASE_URL}/api/routers/{DEMO}/resources/ppp-secrets", params={"reveal": "true"}, timeout=30)
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Router not found in managed inventory"


def test_reveal_param_invalid_value(api):
    r = api.get(f"{BASE_URL}/api/routers/{DEMO}/resources/ppp-secrets", params={"reveal": "notabool"}, timeout=30)
    assert r.status_code == 422, r.text


# --- actions ---
def test_reboot_blocked(api):
    r = api.post(f"{BASE_URL}/api/routers/{DEMO}/actions/reboot", json={"item_id": "*A1"}, timeout=30)
    assert r.status_code == 403, r.text
    assert "Super Admin" in r.json()["detail"]


def test_interface_disable_valid_body_reaches_router_lookup(api):
    r = api.post(f"{BASE_URL}/api/routers/{DEMO}/actions/interface-disable", json={"item_id": "*A1"}, timeout=30)
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Router not found in managed inventory"


def test_interface_disable_invalid_item_id(api):
    r = api.post(f"{BASE_URL}/api/routers/{DEMO}/actions/interface-disable", json={"item_id": "bad"}, timeout=30)
    assert r.status_code == 422, r.text


def test_unknown_action_rejected(api):
    r = api.post(f"{BASE_URL}/api/routers/{DEMO}/actions/unknown-action", json={"item_id": "*A1"}, timeout=30)
    assert r.status_code == 400
    assert r.json()["detail"] == "Action is not allow-listed"


# --- backups ---
def test_backup_history_empty(api):
    r = api.get(f"{BASE_URL}/api/routers/{DEMO}/backups", timeout=30)
    assert r.status_code == 200, r.text
    assert r.json() == {"items": []}


def test_backup_now_gated(api):
    r = api.post(f"{BASE_URL}/api/routers/{DEMO}/backup-now", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is False
    assert d["status"] == "configuration_required"
    assert isinstance(d["message"], str) and d["message"]


def test_backup_schedule_requires_managed_router(api):
    r = api.post(f"{BASE_URL}/api/routers/{DEMO}/backup-schedule", json={"frequency": "daily", "hour": 2, "minute": 30}, timeout=30)
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Router not found in managed inventory"


def test_backup_schedule_invalid_frequency(api):
    r = api.post(f"{BASE_URL}/api/routers/{DEMO}/backup-schedule", json={"frequency": "hourly", "hour": 2, "minute": 30}, timeout=30)
    assert r.status_code == 422, r.text


# --- router onboarding gate (no CREDENTIALS_FERNET_KEY configured in this env) ---
def test_create_router_requires_fernet_key(api):
    r = api.post(f"{BASE_URL}/api/routers", json={"name": "TEST_Unreachable", "host": "192.0.2.10", "port": 8728, "username": "admin", "password": "pw", "group": "TEST"}, timeout=30)
    assert r.status_code in (200, 503), r.text
    if r.status_code == 503:
        assert "CREDENTIALS_FERNET_KEY" in r.json()["detail"]
    else:
        # do not leak test data into the managed inventory
        rid = r.json()["router"]["id"]
        assert api.delete(f"{BASE_URL}/api/routers/{rid}", timeout=30).status_code == 200
