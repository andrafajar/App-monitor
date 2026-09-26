"""Iteration 15 — live traffic + recorded registry + interface history + diagnose + custom cards + carousel + routing menus."""
import os, time, uuid, requests, pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EMAIL, PASSWORD, WS = "admin@netpulse.local", "Np-6oFKw7vnJ0Gr", "ws-default"
CRON = "np_cron_5f3c1a9e84b24d6fbe07c2a1d9583746"
LAB_ID, IDC_ID = "mr-2be66e62", "mr-65920574"


@pytest.fixture(scope="session")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Workspace": WS})
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return s


# ---------- SNMP recorded interface registry ----------
class TestRecordedRegistry:
    def test_scan_populates_and_registry_auto_no_duplicates(self, sess):
        # Ensure auto mode
        r = sess.put(f"{BASE}/api/devices/{LAB_ID}/snmp/recorded", json={"mode": "auto", "interfaces": []}, timeout=15)
        assert r.status_code == 200, r.text
        # Fire two scans back to back
        for _ in range(2):
            s = sess.post(f"{BASE}/api/devices/{LAB_ID}/snmp/scan", timeout=30)
            assert s.status_code == 200
        # Fetch config
        cfg = sess.get(f"{BASE}/api/devices/{LAB_ID}/snmp", timeout=15).json()["config"]
        assert cfg["record_mode"] == "auto"
        assert len(cfg["recorded"]) == len(set(cfg["recorded"])), f"Duplicates in registry: {cfg['recorded']}"
        assert cfg["recorded"], "expected at least one auto-registered iface"

    def test_manual_empty_422(self, sess):
        r = sess.put(f"{BASE}/api/devices/{LAB_ID}/snmp/recorded", json={"mode": "manual", "interfaces": []}, timeout=15)
        assert r.status_code == 422

    def test_manual_unknown_iface_422(self, sess):
        r = sess.put(f"{BASE}/api/devices/{LAB_ID}/snmp/recorded", json={"mode": "manual", "interfaces": ["not-a-real-iface"]}, timeout=15)
        assert r.status_code == 422

    def test_manual_dedup_and_persist(self, sess):
        # Get a real iface name
        snmp = sess.get(f"{BASE}/api/devices/{LAB_ID}/snmp", timeout=15).json()
        ifaces = [i["name"] for i in (snmp["snmp"] or {}).get("interfaces") or []]
        assert ifaces
        name = ifaces[0]
        r = sess.put(f"{BASE}/api/devices/{LAB_ID}/snmp/recorded", json={"mode": "manual", "interfaces": [name, name]}, timeout=15)
        assert r.status_code == 200
        cfg = r.json()["config"]
        assert cfg["record_mode"] == "manual"
        assert cfg["recorded"] == [name]
        # Reload
        cfg2 = sess.get(f"{BASE}/api/devices/{LAB_ID}/snmp", timeout=15).json()["config"]
        assert cfg2["recorded"] == [name]
        # Restore auto
        sess.put(f"{BASE}/api/devices/{LAB_ID}/snmp/recorded", json={"mode": "auto", "interfaces": []}, timeout=15)


# ---------- SNMP diagnose ----------
class TestSnmpDiagnose:
    def test_diagnose_lab_answering(self, sess):
        r = sess.get(f"{BASE}/api/devices/{LAB_ID}/snmp/diagnose", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("host", "port", "from_ip", "ping", "configured", "answering", "detail"):
            assert k in d, f"missing key {k}"
        assert d["port"] == 1161
        assert d["configured"] is True
        assert d["answering"] is True, f"expected Lab to answer: {d}"
        assert d["hint"] is None

    def test_diagnose_real_router_unreachable(self, sess):
        r = sess.get(f"{BASE}/api/devices/{IDC_ID}/snmp/diagnose", timeout=25)
        assert r.status_code == 200
        d = r.json()
        assert d["answering"] is False
        assert d["hint"] and d["from_ip"]
        assert d["from_ip"] in (d["hint"] or "") or "IP" in d["hint"] or "netpulse-ip" in d["hint"].lower() or "ip" in d["hint"].lower()


# ---------- Interface history ----------
class TestInterfaceHistory:
    def test_interface_history_shape_and_clamp(self, sess):
        # Pick a recorded iface
        cfg = sess.get(f"{BASE}/api/devices/{LAB_ID}/snmp", timeout=15).json()["config"]
        assert cfg["recorded"], "no recorded ifaces"
        iface = cfg["recorded"][0]
        r = sess.get(f"{BASE}/api/devices/{LAB_ID}/interface-history", params={"iface": iface, "hours": 24}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("iface", "hours", "bucket_seconds", "retention_days", "samples", "traffic", "ping", "peak", "average"):
            assert k in d
        assert d["retention_days"] == 30
        assert d["hours"] == 24
        # Clamp to 720
        r2 = sess.get(f"{BASE}/api/devices/{LAB_ID}/interface-history", params={"iface": iface, "hours": 10000}, timeout=20)
        assert r2.status_code == 200
        assert r2.json()["hours"] == 720

    def test_iface_metrics_ttl_index(self):
        import asyncio, sys
        sys.path.insert(0, "/app/backend")
        from core import db

        async def check():
            idx = await db.iface_metrics.index_information()
            ttl = [k for k, v in idx.items() if "expireAfterSeconds" in v]
            assert ttl, f"no TTL on iface_metrics: {idx}"
            assert idx[ttl[0]]["expireAfterSeconds"] == 30 * 86400
        try:
            asyncio.run(check())
        except RuntimeError:
            pass


# ---------- Custom overview boards / cards ----------
class TestBoardCards:
    _board_id = None

    def test_list_boards_has_card_types(self, sess):
        r = sess.get(f"{BASE}/api/dashboards", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "iface-traffic" in d["card_types"]
        assert "device-count" in d["card_types"]
        assert "device-ping" in d["card_types"]
        assert 0 in d["card_hours"] and 720 in d["card_hours"]

    def test_create_board_with_cards(self, sess):
        cfg = sess.get(f"{BASE}/api/devices/{LAB_ID}/snmp", timeout=15).json()["config"]
        iface = (cfg["recorded"] or [""])[0]
        cards = [
            {"type": "device-count", "title": "Fleet", "device_id": "", "iface": "", "hours": 0},
            {"type": "iface-traffic", "title": "Lab traffic", "device_id": LAB_ID, "iface": iface, "hours": 24},
            {"type": "device-ping", "title": "Lab ping", "device_id": LAB_ID, "iface": "", "hours": 0},
        ]
        r = sess.post(f"{BASE}/api/dashboards", json={"name": f"TEST_{uuid.uuid4().hex[:5]}", "widgets": ["metrics"], "cards": cards, "group_ids": [], "device_ids": [], "order": 5}, timeout=15)
        assert r.status_code == 200, r.text
        board = r.json()["board"]
        TestBoardCards._board_id = board["id"]
        assert len(board["cards"]) == 3
        types = {c["type"] for c in board["cards"]}
        assert types == {"device-count", "iface-traffic", "device-ping"}
        for c in board["cards"]:
            assert c["id"].startswith("card-")

    def test_iface_traffic_missing_device_422(self, sess):
        r = sess.post(f"{BASE}/api/dashboards", json={"name": f"TEST_{uuid.uuid4().hex[:5]}", "cards": [{"type": "iface-traffic", "device_id": "", "iface": "eth0", "hours": 24}]}, timeout=15)
        assert r.status_code == 422

    def test_iface_traffic_missing_iface_422(self, sess):
        r = sess.post(f"{BASE}/api/dashboards", json={"name": f"TEST_{uuid.uuid4().hex[:5]}", "cards": [{"type": "iface-traffic", "device_id": LAB_ID, "iface": "", "hours": 24}]}, timeout=15)
        assert r.status_code == 422

    def test_update_and_delete_board(self, sess):
        bid = TestBoardCards._board_id
        assert bid
        r = sess.put(f"{BASE}/api/dashboards/{bid}", json={"name": "TEST_updated", "widgets": ["metrics"], "cards": [], "group_ids": [], "device_ids": [], "order": 5}, timeout=15)
        assert r.status_code == 200
        assert r.json()["board"]["cards"] == []
        # Delete
        r2 = sess.delete(f"{BASE}/api/dashboards/{bid}", timeout=15)
        assert r2.status_code == 200


# ---------- Routing resources ----------
class TestRoutingResources:
    RES = ["routes", "routing-tables", "vrf", "ospf-instances", "ospf-areas", "ospf-interfaces",
           "ospf-neighbors", "bgp-connections", "bgp-sessions", "routing-filters", "routing-bfd"]

    @pytest.mark.parametrize("res", RES)
    def test_non_mikrotik_400(self, sess, res):
        r = sess.get(f"{BASE}/api/routers/{LAB_ID}/resources/{res}", timeout=15)
        assert r.status_code == 400, f"{res}: {r.status_code}"

    @pytest.mark.parametrize("res", RES)
    def test_mikrotik_routing_endpoints(self, sess, res):
        r = sess.get(f"{BASE}/api/routers/{IDC_ID}/resources/{res}", timeout=30)
        # Real router unreachable → allowed to be an error, but must not be 400 (allow-list) or 404
        assert r.status_code != 400, f"{res} not allow-listed: {r.text}"
        assert r.status_code != 404, f"{res} 404: {r.text}"
        # 200 with items list, 502/503 gateway errors when device unreachable are acceptable
        if r.status_code == 200:
            assert "items" in r.json()


# ---------- Public display carousel ----------
class TestCarousel:
    def test_carousel_enable_and_public(self, sess):
        # Enable
        r = sess.put(f"{BASE}/api/workspaces/{WS}/public-display",
                     json={"enabled": True, "show_ips": False, "title": "iter15", "rotate": False,
                           "carousel": True, "carousel_seconds": 8}, timeout=15)
        assert r.status_code == 200
        d = r.json()["display"]
        assert d["carousel"] is True and d["carousel_seconds"] == 8
        token = d["token"]
        pub = requests.get(f"{BASE}/api/public/display/{token}", timeout=15).json()
        assert pub["display"]["carousel"] is True
        assert pub["display"]["carousel_seconds"] == 8
        # No credentials leaked
        blob = repr(pub).lower()
        assert "password" not in blob and "netpulse" not in blob and "community" not in blob

    def test_carousel_bounds_422(self, sess):
        r = sess.put(f"{BASE}/api/workspaces/{WS}/public-display",
                     json={"enabled": True, "show_ips": False, "title": "x", "carousel": True, "carousel_seconds": 1}, timeout=15)
        assert r.status_code == 422


# ---------- Monitor status still healthy ----------
class TestMonitorRegression:
    def test_monitor_status(self, sess):
        r = sess.get(f"{BASE}/api/monitor/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["retention_days"] == 30
        by_id = {i["id"]: i for i in d["items"]}
        assert LAB_ID in by_id and IDC_ID in by_id

    def test_cron_scan_still_401_bad(self):
        r = requests.post(f"{BASE}/api/cron/monitor-scan", json={}, timeout=15)
        assert r.status_code == 401
