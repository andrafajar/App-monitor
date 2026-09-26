"""Iteration 14 — multi-vendor + SNMP + topology + retention + blocked-port hint."""
import os, time, uuid, requests, pytest
from datetime import datetime, timezone, timedelta

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://device-nexus-7.preview.emergentagent.com").rstrip("/")
EMAIL = "admin@netpulse.local"
PASSWORD = "Np-6oFKw7vnJ0Gr"
WS = "ws-default"
CRON = "np_cron_5f3c1a9e84b24d6fbe07c2a1d9583746"
LAB_ID = "mr-2be66e62"       # Lab SNMP Agent
IDC_ID = "mr-65920574"       # IDC MONITORING (real MikroTik)


@pytest.fixture(scope="session")
def sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "X-Workspace": WS})
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def head_office_group(sess):
    r = sess.get(f"{BASE}/api/groups", timeout=15)
    assert r.status_code == 200
    g = next((x for x in r.json()["items"] if x["name"] == "Head Office"), None)
    assert g, "Head Office group missing"
    return g["id"]


# ---------- monitor/status + metrics + retention ----------
class TestMonitorStatus:
    def test_monitor_status_shape(self, sess):
        r = sess.get(f"{BASE}/api/monitor/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["retention_days"] == 30
        by_id = {i["id"]: i for i in d["items"]}
        assert IDC_ID in by_id and LAB_ID in by_id
        lab = by_id[LAB_ID]
        assert lab["device_type"] == "other"
        assert lab["snmp_enabled"] is True
        assert "ping_ms" in lab and "snmp_interfaces" in lab
        idc = by_id[IDC_ID]
        assert idc["device_type"] == "mikrotik"

    def test_metrics_has_retention(self, sess):
        r = sess.get(f"{BASE}/api/devices/{LAB_ID}/metrics", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["retention_days"] == 30
        assert isinstance(d["items"], list)


# ---------- SNMP API (never leaks community) ----------
class TestSnmpApi:
    def test_get_snmp_no_community_leak(self, sess):
        r = sess.get(f"{BASE}/api/devices/{LAB_ID}/snmp", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["device_type"] == "other"
        assert d["config"]["configured"] is True
        assert d["config"]["port"] == 1161
        # Ensure community never returned anywhere in response
        blob = repr(d).lower()
        assert "netpulse" not in blob, f"Community leaked: {blob}"
        assert "community" not in d["config"]

    def test_scan_now_populates_interfaces(self, sess):
        r = sess.post(f"{BASE}/api/devices/{LAB_ID}/snmp/scan", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        snmp = d["snmp"]
        assert snmp.get("error") in (None, "")
        assert isinstance(snmp.get("interfaces"), list)
        assert len(snmp["interfaces"]) >= 1
        assert snmp.get("sysname")

    def test_put_snmp_persists(self, sess):
        # Save with same values
        r = sess.put(f"{BASE}/api/devices/{LAB_ID}/snmp", json={"enabled": True, "community": "netpulse", "port": 1161}, timeout=15)
        assert r.status_code == 200
        # GET back
        g = sess.get(f"{BASE}/api/devices/{LAB_ID}/snmp", timeout=15).json()
        assert g["config"]["port"] == 1161 and g["config"]["enabled"] is True

    def test_snmp_wrong_community_error(self, sess):
        # temporarily flip community
        sess.put(f"{BASE}/api/devices/{LAB_ID}/snmp", json={"enabled": True, "community": "wrongcomm", "port": 1161}, timeout=15)
        r = sess.post(f"{BASE}/api/devices/{LAB_ID}/snmp/scan", timeout=30)
        d = r.json()
        assert d["snmp"].get("error"), "expected SNMP error with wrong community"
        # restore
        sess.put(f"{BASE}/api/devices/{LAB_ID}/snmp", json={"enabled": True, "community": "netpulse", "port": 1161}, timeout=15)
        ok = sess.post(f"{BASE}/api/devices/{LAB_ID}/snmp/scan", timeout=30).json()
        assert not ok["snmp"].get("error")

    def test_non_mikrotik_read_resource_400(self, sess):
        r = sess.get(f"{BASE}/api/routers/{LAB_ID}/resources/interfaces", timeout=15)
        assert r.status_code == 400


# ---------- Create device validations ----------
class TestDeviceCreate:
    _created = []

    def test_mikrotik_without_creds_422(self, sess, head_office_group):
        payload = {"name": f"TEST_mik_{uuid.uuid4().hex[:5]}", "host": "10.99.99.99",
                   "port": 8728, "username": "", "password": "", "device_type": "mikrotik",
                   "group_id": head_office_group, "description": ""}
        r = sess.post(f"{BASE}/api/routers", json=payload, timeout=20)
        assert r.status_code == 422, r.text

    def test_snmp_enabled_without_community_422(self, sess, head_office_group):
        payload = {"name": f"TEST_snmp_{uuid.uuid4().hex[:5]}", "host": "127.0.0.1", "port": 8728,
                   "device_type": "cisco", "snmp_enabled": True, "snmp_community": "",
                   "snmp_port": 1161, "group_id": head_office_group}
        r = sess.post(f"{BASE}/api/routers", json=payload, timeout=20)
        assert r.status_code == 422

    @pytest.mark.parametrize("vendor", ["huawei", "cisco", "other"])
    def test_create_non_mikrotik_with_snmp(self, sess, head_office_group, vendor):
        payload = {"name": f"TEST_{vendor}_{uuid.uuid4().hex[:5]}", "host": "127.0.0.1",
                   "port": 8728, "device_type": vendor,
                   "snmp_enabled": True, "snmp_community": "netpulse", "snmp_port": 1161,
                   "group_id": head_office_group, "description": f"test {vendor}"}
        r = sess.post(f"{BASE}/api/routers", json=payload, timeout=40)
        assert r.status_code == 200, r.text
        router = r.json()["router"]
        assert router["device_type"] == vendor
        assert router["status"] == "online", f"expected online, got {router['status']}"
        self.__class__._created.append(router["id"])

    def test_cleanup_created_devices(self, sess):
        for rid in list(self.__class__._created):
            r = sess.delete(f"{BASE}/api/routers/{rid}", timeout=15)
            assert r.status_code == 200


# ---------- Topology ----------
class TestTopology:
    _link_id = None

    def test_get_topology_has_nodes(self, sess):
        r = sess.get(f"{BASE}/api/topology", timeout=15)
        assert r.status_code == 200
        d = r.json()
        ids = {n["device_id"] for n in d["nodes"]}
        assert LAB_ID in ids and IDC_ID in ids
        for n in d["nodes"]:
            assert "x" in n and "y" in n and "device_type" in n

    def test_move_node_persists(self, sess):
        r = sess.put(f"{BASE}/api/topology/nodes/{LAB_ID}", json={"x": 321.0, "y": 234.0}, timeout=15)
        assert r.status_code == 200
        topo = sess.get(f"{BASE}/api/topology", timeout=15).json()
        lab = next(n for n in topo["nodes"] if n["device_id"] == LAB_ID)
        assert lab["x"] == 321.0 and lab["y"] == 234.0

    def test_interfaces_pick_list(self, sess):
        r = sess.get(f"{BASE}/api/topology/interfaces", timeout=15)
        assert r.status_code == 200
        by_id = {i["device_id"]: i for i in r.json()["items"]}
        assert LAB_ID in by_id
        assert by_id[LAB_ID]["snmp_enabled"] is True
        assert len(by_id[LAB_ID]["interfaces"]) >= 1

    def test_create_and_duplicate_link(self, sess):
        # First ensure LAB has at least 1 interface, use it twice against IDC placeholder
        ifaces = sess.get(f"{BASE}/api/topology/interfaces", timeout=15).json()["items"]
        lab = next(x for x in ifaces if x["device_id"] == LAB_ID)
        assert lab["interfaces"], "Lab has no interfaces to link"
        a_iface = lab["interfaces"][0]["name"]
        # b: use IDC with an arbitrary interface name (link creation only checks visibility, not iface exists)
        body = {"a_device": LAB_ID, "a_iface": a_iface,
                "b_device": IDC_ID, "b_iface": "ether1", "label": "TEST_link"}
        r = sess.post(f"{BASE}/api/topology/links", json=body, timeout=15)
        assert r.status_code == 200, r.text
        TestTopology._link_id = r.json()["link"]["id"]
        # Duplicate
        r2 = sess.post(f"{BASE}/api/topology/links", json=body, timeout=15)
        assert r2.status_code == 409

    def test_topology_shows_link(self, sess):
        d = sess.get(f"{BASE}/api/topology", timeout=15).json()
        assert any(l["id"] == TestTopology._link_id for l in d["links"])

    def test_delete_link(self, sess):
        r = sess.delete(f"{BASE}/api/topology/links/{TestTopology._link_id}", timeout=15)
        assert r.status_code == 200
        d = sess.get(f"{BASE}/api/topology", timeout=15).json()
        assert not any(l["id"] == TestTopology._link_id for l in d["links"])


# ---------- Cron webhook ----------
class TestCron:
    def test_cron_no_token_401(self):
        r = requests.post(f"{BASE}/api/cron/monitor-scan", json={}, timeout=15)
        assert r.status_code == 401

    def test_cron_bad_token_401(self):
        r = requests.post(f"{BASE}/api/cron/monitor-scan", json={}, headers={"Authorization": "Bearer wrong"}, timeout=15)
        assert r.status_code == 401

    def test_cron_scan_ok_and_run_recorded(self, sess):
        wid = f"iter14-{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{BASE}/api/cron/monitor-scan", json={},
                          headers={"Authorization": f"Bearer {CRON}", "X-Webhook-Id": wid}, timeout=15)
        assert r.status_code in (200, 202), r.text
        # Poll cron runs
        finished = None
        for _ in range(20):
            time.sleep(2)
            runs = sess.get(f"{BASE}/api/cron/runs", timeout=15).json()
            row = next((x for x in runs.get("items", []) if x.get("run_id") == wid or x.get("webhook_id") == wid), None)
            if row and row.get("finished_at"):
                finished = row; break
        assert finished, f"cron run {wid} did not finish"
        result = finished.get("result") or {}
        assert "devices" in result and "alarms" in result and "retention" in result


# ---------- Retention / TTL index ----------
class TestRetentionIndex:
    def test_ttl_index_present_and_purge(self):
        import asyncio, sys
        sys.path.insert(0, "/app/backend")
        from core import db
        async def check():
            idx = await db.device_metrics.index_information()
            ttl = [k for k, v in idx.items() if "expireAfterSeconds" in v]
            assert ttl, f"no TTL index on device_metrics: {idx}"
            secs = idx[ttl[0]]["expireAfterSeconds"]
            assert secs == 30 * 86400
            # Insert artificially old doc + call purge
            old = {"device_id": LAB_ID, "workspace_id": WS, "created_at": datetime.now(timezone.utc) - timedelta(days=45),
                   "ping_ms": 1, "loss": 0, "cpu": 1}
            ins = await db.device_metrics.insert_one(old)
            from monitor import purge_history
            res = await purge_history()
            found = await db.device_metrics.find_one({"_id": ins.inserted_id})
            assert found is None, "old doc was not purged"
            assert res["metrics"] >= 1
        asyncio.get_event_loop().run_until_complete(check()) if not asyncio.get_event_loop().is_running() else None
        # simple wrapper to run
        try:
            asyncio.run(check())
        except RuntimeError:
            pass


# ---------- Public display topology ----------
class TestPublicDisplay:
    def test_public_topology(self, sess):
        # Enable display
        r = sess.put(f"{BASE}/api/workspaces/{WS}/public-display",
                     json={"enabled": True, "show_ips": False, "title": "iter14", "rotate": False}, timeout=15)
        assert r.status_code == 200
        token = r.json().get("display", {}).get("token")
        assert token
        pub = requests.get(f"{BASE}/api/public/display/{token}", timeout=15)
        assert pub.status_code == 200
        d = pub.json()
        assert "topology" in d, f"no topology in public payload: {list(d.keys())}"
        assert "nodes" in d["topology"] and "links" in d["topology"]
        # No credentials leaked
        blob = repr(d).lower()
        assert "password" not in blob and "netpulse" not in blob
