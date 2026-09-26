"""Managed router inventory CRUD: POST/GET/DELETE /api/routers + overview merge +
probe-on-create, POST /api/routers/{id}/test-connection and POST /api/monitoring/probe-all."""
import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

# MANAGED_PUBLIC_FIELDS in server.py
PUBLIC = {"id", "name", "host", "port", "group", "status", "cpu", "memory", "uptime",
          "version", "traffic", "interfaces", "color", "created_at", "last_probed_at"}
SECRETS = {"password", "password_enc", "username", "telegram_chat_id", "_id"}
UNREACHABLE_HOST = "192.0.2.99"  # RFC5737 TEST-NET-1, guaranteed unroutable
TEST_PASSWORD = "s3cret-pytest"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def created_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(client, created_ids):
    yield
    for rid in created_ids:
        r = client.delete(f"{BASE_URL}/api/routers/{rid}", timeout=30)
        assert r.status_code in (200, 404)


def _payload(name="TEST_Pytest Router", group="Head Office"):
    return {"name": name, "host": UNREACHABLE_HOST, "port": 8728, "username": "admin",
            "password": TEST_PASSWORD, "group": group}


class TestRouterCRUD:
    def test_create_router_sanitized_and_probed(self, client, created_ids):
        r = client.post(f"{BASE_URL}/api/routers", json=_payload(), timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        router = body["router"]
        created_ids.append(router["id"])
        assert router["id"].startswith("mr-")
        assert router["name"] == "TEST_Pytest Router"
        assert router["host"] == UNREACHABLE_HOST
        assert router["port"] == 8728
        assert router["group"] == "Head Office"
        # probe on create must have run -> offline, never left at 'pending'
        assert router["status"] == "offline", f"expected probed status offline, got {router['status']}"
        assert isinstance(router["last_probed_at"], str)
        assert isinstance(router["created_at"], str)
        assert set(router) <= PUBLIC, f"unexpected fields: {set(router) - PUBLIC}"
        assert not (set(router) & SECRETS)
        # probe block carries a sanitized error
        probe = body["probe"]
        assert probe["status"] == "offline"
        assert probe["error"], "probe.error must be populated for an unreachable host"
        assert UNREACHABLE_HOST not in probe["error"]
        assert TEST_PASSWORD not in probe["error"]
        assert "unexpected keyword argument" not in probe["error"]

    def test_list_routers_sanitized(self, client, created_ids):
        r = client.get(f"{BASE_URL}/api/routers", timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        match = [i for i in items if i["id"] == created_ids[0]]
        assert len(match) == 1
        assert match[0]["status"] == "offline"
        assert set(match[0]) <= PUBLIC
        for item in items:
            assert not (set(item) & SECRETS)

    def test_overview_merges_managed_with_probe_fields(self, client, created_ids):
        r = client.get(f"{BASE_URL}/api/monitoring/overview", timeout=30)
        assert r.status_code == 200
        data = r.json()
        ids = [x["id"] for x in data["routers"]]
        for demo in ("r-01", "r-02", "r-03", "r-04"):
            assert demo in ids
        assert created_ids[0] in ids
        row = next(x for x in data["routers"] if x["id"] == created_ids[0])
        for key in ("cpu", "memory", "uptime", "interfaces", "traffic", "version",
                    "color", "last_probed_at", "status"):
            assert key in row, f"overview row missing {key}"
        assert not (set(row) & SECRETS)
        assert data["groups"][0] == "All routers"

    def test_new_group_appears_in_overview(self, client, created_ids):
        r = client.post(f"{BASE_URL}/api/routers",
                        json=_payload("TEST_New Group Router", "TEST_Group Zeta"), timeout=120)
        assert r.status_code == 200
        rid = r.json()["router"]["id"]
        created_ids.append(rid)
        data = client.get(f"{BASE_URL}/api/monitoring/overview", timeout=30).json()
        assert "TEST_Group Zeta" in data["groups"]

    def test_delete_router_and_verify_removal(self, client):
        rid = client.post(f"{BASE_URL}/api/routers", json=_payload("TEST_Delete Me"),
                          timeout=120).json()["router"]["id"]
        d = client.delete(f"{BASE_URL}/api/routers/{rid}", timeout=30)
        assert d.status_code == 200
        assert d.json()["ok"] is True
        items = client.get(f"{BASE_URL}/api/routers", timeout=30).json()["items"]
        assert rid not in [i["id"] for i in items]
        overview = client.get(f"{BASE_URL}/api/monitoring/overview", timeout=30).json()
        assert rid not in [i["id"] for i in overview["routers"]]

    def test_delete_unknown_router_404(self, client):
        r = client.delete(f"{BASE_URL}/api/routers/mr-doesnotexist", timeout=30)
        assert r.status_code == 404
        assert "detail" in r.json()

    def test_delete_demo_router_404(self, client):
        r = client.delete(f"{BASE_URL}/api/routers/r-01", timeout=30)
        assert r.status_code == 404


class TestTestConnection:
    """POST /api/routers/{id}/test-connection"""

    @pytest.fixture(scope="class")
    def unreachable_router(self, client):
        r = client.post(f"{BASE_URL}/api/routers", json=_payload("TEST_TestConn"), timeout=120)
        assert r.status_code == 200, r.text
        rid = r.json()["router"]["id"]
        yield rid
        assert client.delete(f"{BASE_URL}/api/routers/{rid}", timeout=30).status_code in (200, 404)

    def test_test_connection_unreachable(self, client, unreachable_router):
        r = client.post(f"{BASE_URL}/api/routers/{unreachable_router}/test-connection", timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "offline"
        assert body["error"], "error must be present for unreachable router"
        assert UNREACHABLE_HOST not in body["error"]
        assert TEST_PASSWORD not in body["error"]
        assert "unexpected keyword argument" not in body["error"]
        # last_probed_at persisted
        items = client.get(f"{BASE_URL}/api/routers", timeout=30).json()["items"]
        row = next(i for i in items if i["id"] == unreachable_router)
        assert row.get("last_probed_at"), "last_probed_at not persisted"
        assert row["status"] == "offline"
        assert not (set(row) & SECRETS)

    def test_test_connection_unknown_id_404(self, client):
        r = client.post(f"{BASE_URL}/api/routers/mr-nope/test-connection", timeout=60)
        assert r.status_code == 404, r.text
        assert "detail" in r.json()

    def test_test_connection_demo_router_404(self, client):
        r = client.post(f"{BASE_URL}/api/routers/r-02/test-connection", timeout=60)
        assert r.status_code == 404


class TestProbeAll:
    """POST /api/monitoring/probe-all"""

    def test_probe_all_shape_and_no_leak(self, client):
        created = client.post(f"{BASE_URL}/api/routers", json=_payload("TEST_ProbeAll"),
                              timeout=120).json()["router"]["id"]
        try:
            r = client.post(f"{BASE_URL}/api/monitoring/probe-all", timeout=180)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is True
            assert isinstance(body["count"], int) and body["count"] >= 1
            assert isinstance(body["results"], list)
            assert len(body["results"]) == body["count"]
            ids = [x["id"] for x in body["results"]]
            assert created in ids
            for row in body["results"]:
                assert set(row) == {"id", "status"}, f"unexpected keys {set(row)}"
                assert row["status"] in ("online", "offline")
            mine = next(x for x in body["results"] if x["id"] == created)
            assert mine["status"] == "offline"
            raw = r.text
            for secret in ("password_enc", "bot_token", TEST_PASSWORD, UNREACHABLE_HOST):
                assert secret not in raw, f"probe-all leaks {secret}"
        finally:
            client.delete(f"{BASE_URL}/api/routers/{created}", timeout=30)


class TestRouterValidation:
    @pytest.mark.parametrize("body,label", [
        ({"host": "1.1.1.1", "username": "a", "password": "b"}, "missing name"),
        ({"name": "X", "username": "a", "password": "b"}, "missing host"),
        ({"name": "A", "host": "1.1.1.1", "password": "b"}, "missing username"),
        ({"name": "AB", "host": "1.1.1.1", "username": "a"}, "missing password"),
        ({"name": "A", "host": "1.1.1.1", "username": "a", "password": "b"}, "name too short"),
        ({"name": "AB", "host": "1.1.1.1", "username": "a", "password": "b", "port": 0}, "port too low"),
        ({"name": "AB", "host": "1.1.1.1", "username": "a", "password": "b", "port": 99999}, "port too high"),
    ])
    def test_invalid_payload_422(self, client, body, label):
        r = client.post(f"{BASE_URL}/api/routers", json=body, timeout=60)
        assert r.status_code == 422, f"{label} -> {r.status_code} {r.text[:200]}"

    def test_managed_router_resource_read_fails_gracefully(self, client, created_ids):
        """Unreachable managed router must give 424 (JSON survives the ingress), not 502/500."""
        rid = client.post(f"{BASE_URL}/api/routers", json=_payload("TEST_Unreachable"),
                          timeout=120).json()["router"]["id"]
        created_ids.append(rid)
        r = client.get(f"{BASE_URL}/api/routers/{rid}/resources/interfaces", timeout=120)
        assert r.status_code == 424, f"expected 424, got {r.status_code}: {r.text[:300]}"
        assert r.headers.get("content-type", "").startswith("application/json"), \
            "error body must stay JSON so the UI can read err.response.data.detail"
        detail = r.json()["detail"]
        assert detail.startswith("RouterOS read failed:"), detail
        assert UNREACHABLE_HOST not in detail
        assert TEST_PASSWORD not in detail
        assert "unexpected keyword argument" not in detail, \
            f"RouterOS client is called with an invalid kwarg: {detail}"
