"""Iteration 12 backend tests: live traffic, per-router traffic, new Winbox resources,
secret redaction, backup schedules, cron webhooks, alarm engine, SSH WebSocket, ssh_port."""
import os, time, json, uuid, asyncio
import pytest
import requests
import websockets

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
WS_BASE = BASE.replace("https://", "wss://").replace("http://", "ws://") + "/api"
ADMIN_EMAIL = "admin@netpulse.local"
ADMIN_PASS = "Np-6oFKw7vnJ0Gr"
REAL_ROUTER = "mr-65920574"


def _cron_secret():
    for line in open("/app/backend/.env"):
        if line.startswith("WEBHOOK_CRON_SECRET"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


CRON_SECRET = _cron_secret()


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ============ LIVE TRAFFIC ============
class TestLiveTraffic:
    def test_aggregate_warmup_then_ready(self, h):
        r1 = requests.get(f"{API}/monitoring/traffic", headers=h, timeout=30)
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        assert "per_router" in b1 and "series" in b1 and "totals" in b1
        # first call: real router likely warming-up
        pr = next((p for p in b1["per_router"] if p["id"] == REAL_ROUTER), None)
        assert pr is not None
        assert pr["state"] in ("warming-up", "ready", "no-credentials", "unreachable")

        time.sleep(6.5)
        r2 = requests.get(f"{API}/monitoring/traffic", headers=h, timeout=30)
        assert r2.status_code == 200
        b2 = r2.json()
        pr2 = next((p for p in b2["per_router"] if p["id"] == REAL_ROUTER), None)
        assert pr2 is not None
        assert pr2["state"] == "ready", f"expected ready, got {pr2}"
        # non-zero implied by live router; allow 0 but assert numeric type
        assert isinstance(pr2["inbound"], (int, float))
        assert isinstance(pr2["outbound"], (int, float))
        # series should grow
        assert len(b2["series"]) >= 1

    def test_per_router_traffic(self, h):
        r1 = requests.get(f"{API}/routers/{REAL_ROUTER}/traffic", headers=h, timeout=30)
        assert r1.status_code == 200
        time.sleep(5.5)
        r2 = requests.get(f"{API}/routers/{REAL_ROUTER}/traffic", headers=h, timeout=30)
        assert r2.status_code == 200
        body = r2.json()
        assert body["router_id"] == REAL_ROUTER
        assert "items" in body and "totals" in body
        # Ensure totals only sum uplink kinds
        physical = [i for i in body["items"] if i["uplink"]]
        recomputed_rx = round(sum(i["rx_mbps"] for i in physical), 2)
        recomputed_tx = round(sum(i["tx_mbps"] for i in physical), 2)
        assert abs(body["totals"]["rx_mbps"] - recomputed_rx) < 0.05
        assert abs(body["totals"]["tx_mbps"] - recomputed_tx) < 0.05
        # No bridge/vlan should count as uplink
        for it in body["items"]:
            if it["type"].startswith(("bridge", "vlan")):
                assert it["uplink"] is False


# ============ NEW RESOURCE READS ============
NEW_RESOURCES = ["bridge", "bridge-ports", "vlan", "wireless", "wireless-security", "ip-pools",
                 "hotspot-servers", "hotspot-profiles", "hotspot-users", "hotspot-user-profiles",
                 "hotspot-active", "wireless-registration"]


class TestNewResources:
    @pytest.mark.parametrize("resource", NEW_RESOURCES)
    def test_read(self, h, resource):
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/resources/{resource}", headers=h, timeout=25)
        # 200 = read ok; 424 = RouterOS box has no wireless/hotspot package (acceptable per prompt)
        assert r.status_code in (200, 424), f"{resource}: {r.status_code} {r.text[:200]}"

    def test_hotspot_users_redacted(self, h):
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/resources/hotspot-users", headers=h, timeout=15)
        if r.status_code == 424:
            pytest.skip("hotspot not available on this router")
        assert r.status_code == 200
        b = r.json()
        assert b["redacted"] in (True, False)
        for row in b["items"]:
            if "password" in row:
                assert row["password"] == "••••••", "hotspot-users password not redacted"

    def test_hotspot_users_reveal(self, h):
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/resources/hotspot-users?reveal=true", headers=h, timeout=15)
        if r.status_code == 424:
            pytest.skip("hotspot not available")
        assert r.status_code == 200
        b = r.json()
        # When revealed, redacted flag must be False (or missing/False)
        assert b.get("redacted", False) is False

    def test_wireless_security_redaction(self, h):
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/resources/wireless-security", headers=h, timeout=15)
        if r.status_code == 424:
            pytest.skip("wireless package not installed")
        assert r.status_code == 200
        for row in r.json()["items"]:
            for k in ("wpa-pre-shared-key", "wpa2-pre-shared-key"):
                if k in row:
                    assert row[k] == "••••••"


# ============ BACKUP SCHEDULES ============
class TestBackupSchedule:
    def test_full_cycle(self, h):
        payload = {"frequency": "daily", "hour": 2, "minute": 15, "weekday": 0, "enabled": True, "keep": 5}
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/backup-schedule", headers=h, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["ok"] and b["schedule"]["frequency"] == "daily"
        assert b["schedule"]["next_run_at"]

        r = requests.get(f"{API}/routers/{REAL_ROUTER}/backup-schedule", headers=h, timeout=10)
        assert r.status_code == 200
        assert r.json()["schedule"]["hour"] == 2

        r = requests.delete(f"{API}/routers/{REAL_ROUTER}/backup-schedule", headers=h, timeout=10)
        assert r.status_code == 200

        r = requests.delete(f"{API}/routers/{REAL_ROUTER}/backup-schedule", headers=h, timeout=10)
        assert r.status_code == 404

    def test_permission_403(self, h):
        # Create a viewer role/user with backups=write but NOT owner of the real router — must 403 on save
        MODULES = ["overview","routers","groups","alarms","audit","notifications","backups","users","roles","workspaces","ros_config"]
        privs = {m: "none" for m in MODULES}; privs["backups"] = "write"; privs["routers"] = "read"
        # attach to Head Office group
        gr = requests.get(f"{API}/groups", headers=h).json()["items"]
        head_id = next(g["id"] for g in gr if g["name"] == "Head Office")
        r = requests.post(f"{API}/roles", headers=h,
                          json={"name": f"QA Bkup {uuid.uuid4().hex[:4]}", "description": "qa",
                                "privileges": privs, "group_ids": [head_id]}, timeout=10)
        role = r.json()["role"]
        email = f"qa.bkup.{uuid.uuid4().hex[:5]}@netpulse.test"
        r = requests.post(f"{API}/users", headers=h,
                          json={"email": email, "name": "QA Bkup", "password": "QaBkup123!",
                                "role_id": role["id"], "workspace_ids": ["ws-default"]}, timeout=10)
        assert r.status_code == 200
        uid = r.json()["user"]["user_id"]
        tok = requests.post(f"{API}/auth/login", json={"email": email, "password": "QaBkup123!"}).json()["access_token"]
        try:
            r = requests.post(f"{API}/routers/{REAL_ROUTER}/backup-schedule",
                              headers={"Authorization": f"Bearer {tok}"},
                              json={"frequency":"daily","hour":3,"minute":0,"weekday":0,"enabled":True,"keep":3}, timeout=10)
            assert r.status_code == 403, f"expected 403 for non-owner, got {r.status_code}: {r.text}"
        finally:
            requests.delete(f"{API}/users/{uid}", headers=h)
            requests.delete(f"{API}/roles/{role['id']}", headers=h)


# ============ CRON WEBHOOKS ============
class TestCronWebhooks:
    def test_alarm_scan_401_without_token(self):
        r = requests.post(f"{API}/cron/alarm-scan", json={}, timeout=10)
        assert r.status_code == 401

    def test_alarm_scan_401_wrong_token(self):
        r = requests.post(f"{API}/cron/alarm-scan", json={},
                          headers={"Authorization": "Bearer wrong", "Content-Type": "application/json"}, timeout=10)
        assert r.status_code == 401

    def test_alarm_scan_2xx_ack(self):
        run_id = uuid.uuid4().hex
        r = requests.post(f"{API}/cron/alarm-scan", json={},
                          headers={"Authorization": f"Bearer {CRON_SECRET}", "X-Webhook-Id": run_id, "Content-Type": "application/json"},
                          timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] and body["run_id"] == run_id

        # Duplicate
        r2 = requests.post(f"{API}/cron/alarm-scan", json={},
                           headers={"Authorization": f"Bearer {CRON_SECRET}", "X-Webhook-Id": run_id, "Content-Type": "application/json"},
                           timeout=10)
        assert r2.status_code == 200
        assert r2.json().get("duplicate") is True

        # Wait for background job to persist result then read audit
        time.sleep(6)

    def test_backup_scan_ack(self):
        r = requests.post(f"{API}/cron/backup-scan", json={},
                          headers={"Authorization": f"Bearer {CRON_SECRET}", "Content-Type": "application/json"},
                          timeout=10)
        assert r.status_code == 200

    def test_cron_runs_audit(self, h):
        time.sleep(2)
        r = requests.get(f"{API}/cron/runs", headers=h, timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        # At least one finished run with result present
        finished = [x for x in items if x.get("finished_at")]
        assert finished, f"no finished cron runs found among {items[:3]}"


# ============ ALARM ENGINE SETTINGS ============
class TestAlarmSettings:
    def test_get_defaults(self, h):
        r = requests.get(f"{API}/alarms/settings", headers=h, timeout=10)
        assert r.status_code == 200
        b = r.json()
        assert b["settings"]["cpu_threshold"] >= 20
        assert "last_scan_at" in b

    def test_put_and_bounds(self, h):
        # invalid — too low
        r = requests.put(f"{API}/alarms/settings", headers=h,
                         json={"enabled": True, "cpu_threshold": 10, "notify_unreachable": True, "notify_interface": True, "throttle_minutes": 60}, timeout=10)
        assert r.status_code == 422

        # invalid throttle
        r = requests.put(f"{API}/alarms/settings", headers=h,
                         json={"enabled": True, "cpu_threshold": 80, "notify_unreachable": True, "notify_interface": True, "throttle_minutes": 2}, timeout=10)
        assert r.status_code == 422

        r = requests.put(f"{API}/alarms/settings", headers=h,
                         json={"enabled": True, "cpu_threshold": 80, "notify_unreachable": True, "notify_interface": True, "throttle_minutes": 3000}, timeout=10)
        assert r.status_code == 422

        # valid — modify then restore
        r = requests.put(f"{API}/alarms/settings", headers=h,
                         json={"enabled": True, "cpu_threshold": 75, "notify_unreachable": True, "notify_interface": True, "throttle_minutes": 30}, timeout=10)
        assert r.status_code == 200
        assert r.json()["settings"]["cpu_threshold"] == 75

        # restore
        r = requests.put(f"{API}/alarms/settings", headers=h,
                         json={"enabled": True, "cpu_threshold": 80, "notify_unreachable": True, "notify_interface": True, "throttle_minutes": 60}, timeout=10)
        assert r.status_code == 200


# ============ ALARM DISPATCH — test kind ============
class TestAlarmDispatch:
    def test_no_telegram_409(self, h):
        r = requests.post(f"{API}/alarms/dispatch", headers=h,
                          json={"kind": "test", "router_id": REAL_ROUTER, "detail": "qa iteration12"}, timeout=15)
        # Expected 409 when no role has telegram enabled with access; but real router group might still have role -> accept 200 or 409
        assert r.status_code in (200, 409), r.text
        # Ensure no crash


# ============ SSH WEBSOCKET ============
class TestSshWebSocket:
    @pytest.mark.asyncio
    async def test_bad_token(self):
        uri = f"{WS_BASE}/routers/{REAL_ROUTER}/ssh?token=bogus"
        try:
            async with websockets.connect(uri, open_timeout=10) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=8)
                assert "Authentication failed" in msg or "sign in" in msg.lower()
        except Exception as exc:
            pytest.fail(f"WS conn error: {exc}")

    @pytest.mark.asyncio
    async def test_valid_token_conn_refused(self, admin_token):
        uri = f"{WS_BASE}/routers/{REAL_ROUTER}/ssh?token={admin_token}"
        msgs = []
        async with websockets.connect(uri, open_timeout=10) as ws:
            try:
                while len(msgs) < 5:
                    m = await asyncio.wait_for(ws.recv(), timeout=20)
                    msgs.append(m)
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                pass
        joined = "".join(msgs)
        assert "Connecting to" in joined, f"missing connecting banner: {joined!r}"
        assert "SSH connection failed" in joined, f"missing failure msg: {joined!r}"
        assert "/ip service ssh" in joined, f"missing hint: {joined!r}"


# ============ ROUTER ssh_port FIELD ============
class TestRouterSshPort:
    def test_ssh_port_returned(self, h):
        r = requests.get(f"{API}/routers", headers=h, timeout=10)
        assert r.status_code == 200
        real = next(x for x in r.json()["items"] if x["id"] == REAL_ROUTER)
        assert "ssh_port" in real

    def test_put_accepts_ssh_port(self, h):
        r = requests.get(f"{API}/routers", headers=h).json()["items"]
        real = next(x for x in r if x["id"] == REAL_ROUTER)
        orig_ssh = real.get("ssh_port", 22)
        # Put with same values, only changing ssh_port
        payload = {
            "name": real["name"], "host": real["host"], "port": real["port"],
            "username": real["username"], "ssh_port": 2222,
            "group_id": real["group_id"], "description": real.get("description", "")
        }
        r = requests.put(f"{API}/routers/{REAL_ROUTER}", headers=h, json=payload, timeout=25)
        assert r.status_code == 200, r.text
        assert r.json()["router"].get("ssh_port") == 2222
        # restore
        payload["ssh_port"] = orig_ssh or 22
        r = requests.put(f"{API}/routers/{REAL_ROUTER}", headers=h, json=payload, timeout=25)
        assert r.status_code == 200


# ============ REGRESSION ============
class TestRegression:
    def test_overview_no_demo_traffic_array(self, h):
        r = requests.get(f"{API}/monitoring/overview", headers=h, timeout=15)
        assert r.status_code == 200
        b = r.json()
        # 'traffic' key must NOT exist at top level as a series array; it's a per-router str placeholder
        assert "traffic" not in b or not isinstance(b.get("traffic"), list)
        assert isinstance(b["routers"], list)
        assert isinstance(b["groups"], list)

    def test_login_lockout_email_based(self):
        throwaway = f"lockout-probe-{uuid.uuid4().hex[:6]}@example.com"
        codes = []
        for _ in range(7):
            r = requests.post(f"{API}/auth/login", json={"email": throwaway, "password": "x"}, timeout=10)
            codes.append(r.status_code)
        assert 429 in codes, f"no lockout: {codes}"
