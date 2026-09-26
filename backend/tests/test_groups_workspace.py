"""Tests for NEW iteration-9 features: Groups CRUD, pooled sessions/disconnect,
allow-listed resources for real router mr-65920574."""
import os, time, pytest, requests
from pathlib import Path

# load frontend/.env
env = Path("/app/frontend/.env").read_text()
for line in env.splitlines():
    if line.startswith("REACT_APP_BACKEND_URL="):
        os.environ["REACT_APP_BACKEND_URL"] = line.split("=", 1)[1].strip()

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
REAL_ROUTER = "mr-65920574"
TEST_GROUP = "QA Test Group"


@pytest.fixture(scope="module")
def s():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    yield session
    # cleanup
    try:
        session.delete(f"{BASE_URL}/api/groups/{TEST_GROUP}")
    except Exception:
        pass


# ---------- Groups CRUD ----------
class TestGroupsCRUD:
    def test_create_group_ok(self, s):
        # ensure clean
        s.delete(f"{BASE_URL}/api/groups/{TEST_GROUP}")
        r = s.post(f"{BASE_URL}/api/groups", json={"name": TEST_GROUP})
        assert r.status_code == 200, r.text
        assert r.json()["group"] == TEST_GROUP

    def test_overview_lists_group(self, s):
        r = s.get(f"{BASE_URL}/api/monitoring/overview")
        assert r.status_code == 200
        data = r.json()
        assert TEST_GROUP in data["groups"]
        assert TEST_GROUP in data.get("custom_groups", [])

    def test_duplicate_returns_409(self, s):
        r = s.post(f"{BASE_URL}/api/groups", json={"name": TEST_GROUP})
        assert r.status_code == 409

    def test_builtin_name_returns_409(self, s):
        r = s.post(f"{BASE_URL}/api/groups", json={"name": "Head Office"})
        assert r.status_code == 409

    def test_too_short_returns_422(self, s):
        r = s.post(f"{BASE_URL}/api/groups", json={"name": "A"})
        assert r.status_code == 422

    def test_delete_builtin_returns_400(self, s):
        r = s.delete(f"{BASE_URL}/api/groups/Head%20Office")
        assert r.status_code == 400

    def test_delete_group_ok(self, s):
        r = s.delete(f"{BASE_URL}/api/groups/{TEST_GROUP}")
        assert r.status_code == 200
        # verify gone
        r2 = s.get(f"{BASE_URL}/api/monitoring/overview")
        assert TEST_GROUP not in r2.json().get("custom_groups", [])

    def test_delete_again_returns_404(self, s):
        r = s.delete(f"{BASE_URL}/api/groups/{TEST_GROUP}")
        assert r.status_code == 404


# ---------- Pooled sessions + connection endpoint ----------
class TestConnectionPool:
    def test_disconnect_baseline(self, s):
        # start clean
        s.post(f"{BASE_URL}/api/routers/{REAL_ROUTER}/disconnect")
        r = s.get(f"{BASE_URL}/api/routers/{REAL_ROUTER}/connection")
        assert r.status_code == 200
        assert r.json()["connected"] is False

    def test_read_creates_pool_and_is_fast_on_repeat(self, s):
        times = []
        for _ in range(3):
            t0 = time.time()
            r = s.get(f"{BASE_URL}/api/routers/{REAL_ROUTER}/resources/interfaces", timeout=15)
            times.append(time.time() - t0)
            assert r.status_code == 200, r.text
            assert isinstance(r.json().get("items"), list)
        print(f"interfaces read times: {times}")
        # 2nd/3rd should be faster than 3s (pooled)
        assert times[1] < 3.0
        assert times[2] < 3.0

    def test_connection_reports_connected(self, s):
        r = s.get(f"{BASE_URL}/api/routers/{REAL_ROUTER}/connection")
        assert r.status_code == 200
        assert r.json()["connected"] is True

    def test_disconnect_closes_session(self, s):
        r = s.post(f"{BASE_URL}/api/routers/{REAL_ROUTER}/disconnect")
        assert r.status_code == 200
        assert r.json()["connected"] is False
        r2 = s.get(f"{BASE_URL}/api/routers/{REAL_ROUTER}/connection")
        assert r2.json()["connected"] is False

    def test_reconnects_automatically(self, s):
        r = s.get(f"{BASE_URL}/api/routers/{REAL_ROUTER}/resources/system-identity", timeout=15)
        assert r.status_code == 200
        r2 = s.get(f"{BASE_URL}/api/routers/{REAL_ROUTER}/connection")
        assert r2.json()["connected"] is True


# ---------- Resource allow-list ----------
RESOURCES = [
    "interfaces", "addresses", "arp", "dhcp-server", "dhcp-leases",
    "firewall", "routes", "ppp-profiles", "ppp-secrets", "queues",
    "system-clock", "system-resource", "system-identity", "system-health", "logs",
]

class TestResources:
    @pytest.mark.parametrize("resource", RESOURCES)
    def test_resource_200(self, s, resource):
        r = s.get(f"{BASE_URL}/api/routers/{REAL_ROUTER}/resources/{resource}", timeout=15)
        assert r.status_code == 200, f"{resource}: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert body.get("resource") == resource
        assert isinstance(body.get("items"), list)

    def test_ppp_secrets_masked_by_default(self, s):
        r = s.get(f"{BASE_URL}/api/routers/{REAL_ROUTER}/resources/ppp-secrets", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("redacted") is True
        for row in body["items"]:
            if "password" in row:
                assert row["password"] == "\u2022" * 6

    def test_ppp_secrets_revealed_with_flag(self, s):
        r = s.get(f"{BASE_URL}/api/routers/{REAL_ROUTER}/resources/ppp-secrets?reveal=true", timeout=15)
        assert r.status_code == 200
        assert r.json().get("redacted") is False

    def test_unknown_resource_400(self, s):
        r = s.get(f"{BASE_URL}/api/routers/{REAL_ROUTER}/resources/not-a-thing")
        assert r.status_code == 400

    def test_unknown_router_404(self, s):
        r = s.get(f"{BASE_URL}/api/routers/mr-nope/resources/interfaces")
        assert r.status_code == 404
