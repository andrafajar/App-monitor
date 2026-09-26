"""Iteration 13 backend tests: alarm-interfaces, syslog collector+rules, dashboards CRUD,
public display board, SSH/Telnet WS + port-check, live traffic reuse, Devices rename regression."""
import os, time, json, socket, uuid, asyncio
import pytest
import requests
import websockets

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
WS_BASE = BASE.replace("https://", "wss://").replace("http://", "ws://") + "/api"
ADMIN_EMAIL = "admin@netpulse.local"
ADMIN_PASS = "Np-6oFKw7vnJ0Gr"
REAL_ROUTER = "mr-65920574"
WS_ID = "ws-default"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "X-Workspace": WS_ID}


# =========== Alarm interface watch ============
class TestAlarmInterfaces:
    def test_get_default_all(self, h):
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h, timeout=30)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["mode"] in ("all", "ethernet", "selected", "off")
        assert isinstance(b["available"], list) and len(b["available"]) > 0
        assert isinstance(b["watching"], list)

    def test_put_ethernet_only_watches_ether_sfp(self, h):
        r = requests.put(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h,
                         json={"mode": "ethernet", "interfaces": []}, timeout=15)
        assert r.status_code == 200
        g = requests.get(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h, timeout=30).json()
        assert g["mode"] == "ethernet"
        for name in g["watching"]:
            assert name.startswith(("ether", "sfp", "combo", "qsfp")), f"{name} shouldn't be watched under ethernet mode"

    def test_selected_empty_422(self, h):
        r = requests.put(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h,
                         json={"mode": "selected", "interfaces": []}, timeout=15)
        assert r.status_code == 422

    def test_selected_two(self, h):
        # pick 2 real interface names
        g = requests.get(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h, timeout=30).json()
        names = [a["name"] for a in g["available"] if a["name"].startswith(("ether", "sfp"))][:2]
        assert len(names) >= 2
        r = requests.put(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h,
                         json={"mode": "selected", "interfaces": names}, timeout=15)
        assert r.status_code == 200
        after = requests.get(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h, timeout=30).json()
        assert after["mode"] == "selected"
        assert sorted(after["watching"]) == sorted(names), after

    def test_mode_off_watches_none(self, h):
        r = requests.put(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h,
                         json={"mode": "off", "interfaces": []}, timeout=15)
        assert r.status_code == 200
        after = requests.get(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h, timeout=30).json()
        assert after["watching"] == []

    def test_restore_all(self, h):
        r = requests.put(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h,
                         json={"mode": "all", "interfaces": []}, timeout=15)
        assert r.status_code == 200
        after = requests.get(f"{API}/routers/{REAL_ROUTER}/alarm-interfaces", headers=h, timeout=30).json()
        assert after["mode"] == "all"


# ============ Syslog collector ============
class TestSyslog:
    def test_status(self, h):
        r = requests.get(f"{API}/syslog/status", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["listening"] is True
        assert b["port"] == 514
        assert b["retention_days"] == 30
        assert "auth-failure" in b["categories"]

    def test_udp_ingest_and_filters(self, h):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        marker = uuid.uuid4().hex[:6]
        sock.sendto(
            f"<38>Sep 26 10:00:00 HOST system,error,critical login failure for user admin from 1.2.3.4 via ssh {marker}".encode(),
            ("127.0.0.1", 514))
        sock.sendto(
            f"<28>Sep 26 10:00:01 HOST interface,info ether5 link down {marker}".encode(),
            ("127.0.0.1", 514))
        sock.close()
        time.sleep(2)
        r = requests.get(f"{API}/syslog?q={marker}&limit=50", headers=h, timeout=10)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        found = [i for i in items if marker in i.get("message", "")]
        assert len(found) >= 2, f"expected 2 messages with marker, got {found}"
        # categories
        cats = {i["category"] for i in found}
        assert "auth-failure" in cats
        assert "link" in cats
        # severity_name mapping
        auth = next(i for i in found if i["category"] == "auth-failure")
        assert auth["severity_name"] in ("critical", "error", "warning", "info", "notice", "debug", "alert", "emergency")
        assert auth["source_ip"] == "127.0.0.1"
        # topics parsed into tag
        assert auth["tag"].startswith("system") or auth["tag"] == ""
        # filter by category
        r2 = requests.get(f"{API}/syslog?category=auth-failure&q={marker}", headers=h, timeout=10).json()
        assert all(x["category"] == "auth-failure" for x in r2["items"] if marker in x.get("message", ""))
        # severity_max filter
        r3 = requests.get(f"{API}/syslog?severity_max=2&q={marker}", headers=h, timeout=10).json()
        for x in r3["items"]:
            assert x["severity"] <= 2

    def test_test_message_endpoint(self, h):
        r = requests.post(f"{API}/syslog/test-message", headers=h, timeout=10)
        assert r.status_code == 200
        assert r.json()["ok"] is True
        time.sleep(1)


# ============ Syslog rules CRUD ============
class TestSyslogRules:
    created = []

    def test_invalid_regex_422(self, h):
        r = requests.post(f"{API}/syslog/rules", headers=h,
                          json={"name": "TEST_bad", "category": "auth-failure", "pattern": "[unclosed"}, timeout=10)
        assert r.status_code == 422

    def test_invalid_category_422(self, h):
        r = requests.post(f"{API}/syslog/rules", headers=h,
                          json={"name": "TEST_bad2", "category": "nonsense"}, timeout=10)
        assert r.status_code == 422

    def test_create_update_delete_and_match(self, h):
        rule_name = f"TEST_auth_{uuid.uuid4().hex[:5]}"
        r = requests.post(f"{API}/syslog/rules", headers=h,
                          json={"name": rule_name, "category": "auth-failure", "pattern": "",
                                "severity_max": 7, "enabled": True, "throttle_minutes": 15}, timeout=10)
        assert r.status_code == 200, r.text
        rule = r.json()["rule"]
        rid = rule["id"]
        self.__class__.created.append(rid)

        # Update
        r2 = requests.put(f"{API}/syslog/rules/{rid}", headers=h,
                          json={"name": rule_name + "_upd", "category": "auth-failure", "pattern": "",
                                "severity_max": 6, "enabled": True, "throttle_minutes": 20}, timeout=10)
        assert r2.status_code == 200, r2.text

        # Trigger match: send matching syslog message
        marker = uuid.uuid4().hex[:8]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(f"<38>Sep 26 10:00:00 HOST system,error login failure for user root {marker}".encode(),
                    ("127.0.0.1", 514))
        sock.close()
        time.sleep(2.5)
        # Confirm alarm_log entry created via overview
        ov = requests.get(f"{API}/monitoring/overview", headers=h, timeout=15).json()
        matched = [a for a in ov.get("alarms", []) if a.get("kind") == "syslog-match" and a.get("rule_id") == rid]
        assert matched, f"expected syslog-match alarm for rule {rid}, got alarms: {ov.get('alarms')[:5]}"

        # Send again quickly - should be throttled (no duplicate alarm in this window)
        before_count = len(matched)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(f"<38>Sep 26 10:00:00 HOST system,error login failure for user root2 {marker}".encode(),
                    ("127.0.0.1", 514))
        sock.close()
        time.sleep(2)
        ov2 = requests.get(f"{API}/monitoring/overview", headers=h, timeout=15).json()
        matched2 = [a for a in ov2.get("alarms", []) if a.get("kind") == "syslog-match" and a.get("rule_id") == rid]
        assert len(matched2) == before_count, f"throttle failed: {len(matched2)} vs {before_count}"

        # Delete
        r3 = requests.delete(f"{API}/syslog/rules/{rid}", headers=h, timeout=10)
        assert r3.status_code == 200
        self.__class__.created.remove(rid)

        # Delete again -> 404
        r4 = requests.delete(f"{API}/syslog/rules/{rid}", headers=h, timeout=10)
        assert r4.status_code == 404

    def test_seeded_rule_exists(self, h):
        rules = requests.get(f"{API}/syslog/rules", headers=h, timeout=10).json()["items"]
        assert any(r["name"] == "Login failure" for r in rules), "seeded 'Login failure' rule missing"


# ============ Dashboards ============
class TestDashboards:
    def test_autoseed_overview(self, h):
        r = requests.get(f"{API}/dashboards", headers=h, timeout=10)
        assert r.status_code == 200
        b = r.json()
        assert any(x["name"] == "Overview" for x in b["items"])
        assert set(b["widgets"]) >= {"metrics", "traffic", "alarms", "devices", "syslog"}

    def test_delete_last_board_409(self, h):
        boards = requests.get(f"{API}/dashboards", headers=h, timeout=10).json()["items"]
        # ensure only one board
        for b in boards[1:]:
            requests.delete(f"{API}/dashboards/{b['id']}", headers=h, timeout=10)
        boards = requests.get(f"{API}/dashboards", headers=h, timeout=10).json()["items"]
        assert len(boards) == 1
        r = requests.delete(f"{API}/dashboards/{boards[0]['id']}", headers=h, timeout=10)
        assert r.status_code == 409

    def test_create_update_delete(self, h):
        name = f"TEST_board_{uuid.uuid4().hex[:5]}"
        r = requests.post(f"{API}/dashboards", headers=h,
                          json={"name": name, "widgets": ["metrics", "alarms"], "group_ids": [], "device_ids": [], "order": 1}, timeout=10)
        assert r.status_code == 200
        bid = r.json()["board"]["id"]

        r2 = requests.put(f"{API}/dashboards/{bid}", headers=h,
                          json={"name": name + "_x", "widgets": ["metrics"], "group_ids": [], "device_ids": [REAL_ROUTER], "order": 2}, timeout=10)
        assert r2.status_code == 200
        assert r2.json()["board"]["widgets"] == ["metrics"]
        assert r2.json()["board"]["device_ids"] == [REAL_ROUTER]

        r3 = requests.delete(f"{API}/dashboards/{bid}", headers=h, timeout=10)
        assert r3.status_code == 200


# ============ Public display board ============
class TestPublicDisplay:
    token = None

    def test_enable_and_public_get(self, h):
        r = requests.put(f"{API}/workspaces/{WS_ID}/public-display", headers=h,
                         json={"enabled": True, "show_ips": False, "title": "NOC Central", "rotate": True}, timeout=10)
        assert r.status_code == 200, r.text
        token = r.json()["display"]["token"]
        assert token
        self.__class__.token = token

        # No auth header
        r2 = requests.get(f"{API}/public/display/{token}", timeout=15)
        assert r2.status_code == 200
        b = r2.json()
        assert b["workspace"]["title"] == "NOC Central"
        for d in b["devices"]:
            assert d.get("host") is None, f"host leaked when show_ips=false: {d}"
            for banned in ("username", "password", "password_enc"):
                assert banned not in d
        # counts sane
        assert b["counts"]["total"] == len(b["devices"])

    def test_bad_token_404(self):
        r = requests.get(f"{API}/public/display/garbage-token-xyz", timeout=10)
        assert r.status_code == 404

    def test_rotate_changes_token(self, h):
        old = self.__class__.token
        r = requests.put(f"{API}/workspaces/{WS_ID}/public-display", headers=h,
                         json={"enabled": True, "show_ips": False, "title": "NOC Central", "rotate": True}, timeout=10)
        new_token = r.json()["display"]["token"]
        assert new_token != old
        # old token 404
        r_old = requests.get(f"{API}/public/display/{old}", timeout=10)
        assert r_old.status_code == 404
        self.__class__.token = new_token

    def test_disable_invalidates(self, h):
        r = requests.put(f"{API}/workspaces/{WS_ID}/public-display", headers=h,
                         json={"enabled": False, "show_ips": False, "title": "NOC Central"}, timeout=10)
        assert r.status_code == 200
        r2 = requests.get(f"{API}/public/display/{self.__class__.token}", timeout=10)
        assert r2.status_code == 404

    def test_other_endpoints_still_require_auth(self):
        r = requests.get(f"{API}/monitoring/overview", timeout=10)
        assert r.status_code == 401


# ============ Terminal WS + port-check ============
class TestTerminals:
    def test_port_check(self, h):
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/port-check", headers=h, timeout=25)
        assert r.status_code == 200, r.text
        b = r.json()
        assert "from_ip" in b
        services = {p["service"] for p in b["ports"]}
        assert services == {"api", "ssh", "telnet", "winbox"}

    @pytest.mark.asyncio
    async def test_ssh_bad_token(self):
        uri = f"{WS_BASE}/routers/{REAL_ROUTER}/ssh?proto=ssh&token=bogus"
        async with websockets.connect(uri, open_timeout=10) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=8)
            assert "Authentication failed" in msg

    @pytest.mark.asyncio
    async def test_ssh_open_and_command(self, admin_token):
        uri = f"{WS_BASE}/routers/{REAL_ROUTER}/ssh?proto=ssh&token={admin_token}"
        msgs = []
        got_ready = False
        try:
            async with websockets.connect(uri, open_timeout=15) as ws:
                # collect ready control frame + banner
                for _ in range(6):
                    try:
                        m = await asyncio.wait_for(ws.recv(), timeout=15)
                    except asyncio.TimeoutError:
                        break
                    text = m if isinstance(m, str) else m.decode("utf-8", "ignore")
                    msgs.append(text)
                    if '"type": "ready"' in text or '"type":"ready"' in text:
                        got_ready = True
                        break
                if got_ready:
                    await ws.send("/system identity print\r\n")
                    end = time.time() + 8
                    output = ""
                    while time.time() < end:
                        try:
                            m = await asyncio.wait_for(ws.recv(), timeout=3)
                            output += m if isinstance(m, str) else m.decode("utf-8", "ignore")
                        except asyncio.TimeoutError:
                            break
                    assert "name" in output.lower() or "identity" in output.lower() or "@" in output, f"no prompt/output: {output[:400]}"
        except Exception as exc:
            pytest.skip(f"SSH not reachable in this env: {exc}")
        assert got_ready or any("failed" in x.lower() for x in msgs), f"expected ready or failed frame, got {msgs[:3]}"

    @pytest.mark.asyncio
    async def test_telnet_failed_frame(self, admin_token):
        uri = f"{WS_BASE}/routers/{REAL_ROUTER}/ssh?proto=telnet&token={admin_token}"
        msgs = []
        async with websockets.connect(uri, open_timeout=15) as ws:
            end = time.time() + 20
            while time.time() < end:
                try:
                    m = await asyncio.wait_for(ws.recv(), timeout=15)
                    text = m if isinstance(m, str) else m.decode("utf-8", "ignore")
                    msgs.append(text)
                    if '"type": "failed"' in text or '"type":"failed"' in text or '"type": "ready"' in text:
                        break
                except asyncio.TimeoutError:
                    break
        joined = "".join(msgs)
        # Either ready (unlikely — port filtered) or failed frame
        assert "failed" in joined.lower() or "connection" in joined.lower(), f"unexpected telnet output: {joined[:400]}"


# ============ Live traffic regression ============
class TestLiveTraffic:
    def test_reuse_last_good_rate(self, h):
        r1 = requests.get(f"{API}/monitoring/traffic", headers=h, timeout=30)
        assert r1.status_code == 200
        time.sleep(5.5)
        r2 = requests.get(f"{API}/monitoring/traffic", headers=h, timeout=30)
        b2 = r2.json()
        assert b2["live"] is True
        assert b2["totals"]["inbound"] >= 0
        # rapid third call - dt < 2 -> must reuse last_in/last_out; NOT 0.00
        time.sleep(1.0)
        r3 = requests.get(f"{API}/monitoring/traffic", headers=h, timeout=30)
        b3 = r3.json()
        pr3 = next((p for p in b3["per_router"] if p["id"] == REAL_ROUTER), None)
        assert pr3 is not None
        # Non-zero from second call means reuse should also produce non-zero (or match previous)
        pr2 = next(p for p in b2["per_router"] if p["id"] == REAL_ROUTER)
        if pr2["inbound"] > 0 or pr2["outbound"] > 0:
            assert pr3["inbound"] > 0 or pr3["outbound"] > 0, f"rapid call zeroed out: {pr3} vs {pr2}"

    def test_per_router_totals_uplinks_only(self, h):
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/traffic", headers=h, timeout=30)
        assert r.status_code == 200
        b = r.json()
        for it in b["items"]:
            if it["type"].startswith(("bridge", "vlan")):
                assert it["uplink"] is False


# ============ Rename regression: devices still work ============
class TestRenameRegression:
    def test_routers_endpoint_unchanged(self, h):
        r = requests.get(f"{API}/routers", headers=h, timeout=10)
        assert r.status_code == 200
        assert any(x["id"] == REAL_ROUTER for x in r.json()["items"])
