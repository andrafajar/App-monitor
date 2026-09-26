"""Tests for PUT /api/routers/{router_id} (edit router feature - iteration 10)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Read frontend .env as fallback
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
            break

API = f"{BASE_URL}/api"
REAL_ROUTER_ID = "mr-65920574"


@pytest.fixture(scope="module")
def temp_router():
    """Create a temp router with unreachable host; yields the router dict; deletes at end."""
    payload = {
        "name": "TEST_EditTarget",
        "host": "192.0.2.55",
        "port": 8728,
        "username": "admin",
        "password": "OrigPass!23",
        "group": "Unassigned",
    }
    r = requests.post(f"{API}/routers", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    router = r.json()["router"]
    yield router
    requests.delete(f"{API}/routers/{router['id']}", timeout=15)


# ---- Temp router edit tests ----

def test_put_router_updates_all_fields_without_password(temp_router):
    rid = temp_router["id"]
    body = {
        "name": "TEST_EditTargetRenamed",
        "host": "192.0.2.66",
        "port": 8729,
        "username": "operator",
        "group": "Head Office",
        "description": "QA temp router edited",
    }
    r = requests.put(f"{API}/routers/{rid}", json=body, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    router = data["router"]
    assert router["name"] == body["name"]
    assert router["host"] == body["host"]
    assert router["port"] == body["port"]
    assert router["username"] == body["username"]
    assert router["group"] == body["group"]
    assert router["description"] == body["description"]
    # No password/password_enc leaked
    assert "password" not in router
    assert "password_enc" not in router
    assert "probe" in data

    # Verify persisted via GET /api/routers
    r2 = requests.get(f"{API}/routers", timeout=15)
    assert r2.status_code == 200
    items = r2.json()["items"]
    match = next((x for x in items if x["id"] == rid), None)
    assert match is not None
    assert match["name"] == body["name"]
    assert match["host"] == body["host"]
    assert match["description"] == body["description"]
    assert "password" not in match
    assert "password_enc" not in match


def test_put_router_with_password_field(temp_router):
    rid = temp_router["id"]
    body = {
        "name": "TEST_EditTargetRenamed",
        "host": "192.0.2.66",
        "port": 8729,
        "username": "operator",
        "password": "NewPass!45",
        "group": "Head Office",
        "description": "pw rotated",
    }
    r = requests.put(f"{API}/routers/{rid}", json=body, timeout=30)
    assert r.status_code == 200, r.text
    router = r.json()["router"]
    assert router["description"] == "pw rotated"
    assert "password" not in router
    assert "password_enc" not in router


def test_put_router_not_found():
    body = {"name": "Anything", "host": "1.2.3.4", "port": 8728, "username": "x", "group": "Unassigned", "description": ""}
    r = requests.put(f"{API}/routers/does-not-exist", json=body, timeout=15)
    assert r.status_code == 404


def test_put_router_name_too_short(temp_router):
    body = {"name": "a", "host": "1.2.3.4", "port": 8728, "username": "x", "group": "Unassigned", "description": ""}
    r = requests.put(f"{API}/routers/{temp_router['id']}", json=body, timeout=15)
    assert r.status_code == 422


def test_put_router_description_too_long(temp_router):
    body = {
        "name": "TEST_EditTargetRenamed",
        "host": "192.0.2.66",
        "port": 8728,
        "username": "x",
        "group": "Unassigned",
        "description": "x" * 201,
    }
    r = requests.put(f"{API}/routers/{temp_router['id']}", json=body, timeout=15)
    assert r.status_code == 422


def test_put_router_invalid_port(temp_router):
    body = {"name": "TEST_ok", "host": "1.2.3.4", "port": 70000, "username": "x", "group": "Unassigned", "description": ""}
    r = requests.put(f"{API}/routers/{temp_router['id']}", json=body, timeout=15)
    assert r.status_code == 422


# ---- Real router preservation tests ----

def test_put_real_router_preserves_stored_password():
    """PUT the real router with blank password: probe.status must remain online (proves password preserved)."""
    r = requests.get(f"{API}/routers", timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    real = next((x for x in items if x["id"] == REAL_ROUTER_ID), None)
    if not real:
        pytest.skip(f"Real router {REAL_ROUTER_ID} not present")

    body = {
        "name": real["name"],
        "host": real["host"],
        "port": real["port"],
        "username": real["username"],
        "group": real["group"],
        "description": "QA edit check",
    }
    resp = requests.put(f"{API}/routers/{REAL_ROUTER_ID}", json=body, timeout=45)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["probe"]["status"] == "online", f"Expected online, got: {data['probe']}"
    assert data["router"]["description"] == "QA edit check"

    # Restore description to empty
    body["description"] = ""
    resp2 = requests.put(f"{API}/routers/{REAL_ROUTER_ID}", json=body, timeout=45)
    assert resp2.status_code == 200
    assert resp2.json()["router"]["description"] == ""
