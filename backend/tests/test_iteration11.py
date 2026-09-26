"""Iteration 11 backend tests: Auth/RBAC/Workspaces/Groups/Router-writes/Terminal/Backups/Telegram."""
import os, time, uuid
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
ADMIN_EMAIL = "admin@netpulse.local"
ADMIN_PASS = "Np-6oFKw7vnJ0Gr"
REAL_ROUTER = "mr-65920574"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["is_super_admin"] is True
    assert "ws-default" in body["user"]["workspace_ids"]
    assert body.get("access_token")
    return body["access_token"]


@pytest.fixture(scope="session")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------- AUTH ----------------
class TestAuth:
    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong-x"}, timeout=10)
        assert r.status_code == 401

    def test_lockout_5_wrongs_on_throwaway(self):
        throwaway = f"lockout-{uuid.uuid4().hex[:6]}@qa.test"
        codes = []
        for _ in range(6):
            r = requests.post(f"{API}/auth/login", json={"email": throwaway, "password": "x"}, timeout=10)
            codes.append(r.status_code)
        assert 429 in codes, codes

    def test_me_with_bearer(self, admin_h):
        r = requests.get(f"{API}/auth/me", headers=admin_h, timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_me_without_token(self):
        r = requests.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 401

    def test_overview_without_auth(self):
        r = requests.get(f"{API}/monitoring/overview", timeout=10)
        assert r.status_code == 401

    def test_google_session_bogus(self):
        r = requests.post(f"{API}/auth/session", json={"session_id": "bogus_session_id_that_will_never_work"}, timeout=15)
        assert r.status_code in (401, 502)


# --------------- Helpers to fetch head-office group id -------------
@pytest.fixture(scope="session")
def head_office_group_id(admin_h):
    r = requests.get(f"{API}/groups", headers=admin_h, timeout=10)
    assert r.status_code == 200
    for g in r.json()["items"]:
        if g["name"] == "Head Office":
            return g["id"]
    pytest.skip("Head Office group not found")


# --------------- RBAC ---------------
class TestRBAC:
    @pytest.fixture(scope="class")
    def qa_setup(self, admin_h, head_office_group_id):
        """Create QA Viewer role+user and QA Nogroup role+user; cleanup at end."""
        MODULES = ["overview", "routers", "groups", "alarms", "audit", "notifications", "backups", "users", "roles", "workspaces", "ros_config"]
        privs = {m: "none" for m in MODULES}
        privs["overview"] = "read"; privs["routers"] = "read"; privs["groups"] = "read"

        r = requests.post(f"{API}/roles", headers=admin_h,
                          json={"name": f"QA Viewer {uuid.uuid4().hex[:4]}", "description": "qa",
                                "privileges": privs, "group_ids": [head_office_group_id]}, timeout=10)
        assert r.status_code == 200, r.text
        role_viewer = r.json()["role"]

        privs2 = {m: "none" for m in MODULES}; privs2["overview"] = "read"; privs2["routers"] = "read"
        r = requests.post(f"{API}/roles", headers=admin_h,
                          json={"name": f"QA Nogroup {uuid.uuid4().hex[:4]}", "description": "qa",
                                "privileges": privs2, "group_ids": []}, timeout=10)
        assert r.status_code == 200
        role_nogroup = r.json()["role"]

        email_v = f"qa.viewer.{uuid.uuid4().hex[:5]}@netpulse.test"
        r = requests.post(f"{API}/users", headers=admin_h,
                          json={"email": email_v, "name": "QA Viewer", "password": "QaViewer123!",
                                "role_id": role_viewer["id"], "workspace_ids": ["ws-default"]}, timeout=10)
        assert r.status_code == 200, r.text
        user_v = r.json()["user"]

        email_n = f"qa.nogroup.{uuid.uuid4().hex[:5]}@netpulse.test"
        r = requests.post(f"{API}/users", headers=admin_h,
                          json={"email": email_n, "name": "QA Nogroup", "password": "QaNogroup123!",
                                "role_id": role_nogroup["id"], "workspace_ids": ["ws-default"]}, timeout=10)
        assert r.status_code == 200
        user_n = r.json()["user"]

        # login as both
        r = requests.post(f"{API}/auth/login", json={"email": email_v, "password": "QaViewer123!"}, timeout=10)
        tok_v = r.json()["access_token"]
        r = requests.post(f"{API}/auth/login", json={"email": email_n, "password": "QaNogroup123!"}, timeout=10)
        tok_n = r.json()["access_token"]

        yield {"role_v": role_viewer, "role_n": role_nogroup, "user_v": user_v, "user_n": user_n,
               "tok_v": tok_v, "tok_n": tok_n, "email_v": email_v}

        # cleanup
        requests.delete(f"{API}/users/{user_v['user_id']}", headers=admin_h)
        requests.delete(f"{API}/users/{user_n['user_id']}", headers=admin_h)
        requests.delete(f"{API}/roles/{role_viewer['id']}", headers=admin_h)
        requests.delete(f"{API}/roles/{role_nogroup['id']}", headers=admin_h)

    def test_viewer_overview_shows_real_router(self, qa_setup):
        h = {"Authorization": f"Bearer {qa_setup['tok_v']}"}
        r = requests.get(f"{API}/monitoring/overview", headers=h, timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()["routers"]]
        assert REAL_ROUTER in ids

    def test_viewer_users_forbidden(self, qa_setup):
        h = {"Authorization": f"Bearer {qa_setup['tok_v']}"}
        r = requests.get(f"{API}/users", headers=h, timeout=10)
        assert r.status_code == 403

    def test_viewer_router_create_forbidden(self, qa_setup, head_office_group_id):
        h = {"Authorization": f"Bearer {qa_setup['tok_v']}"}
        r = requests.post(f"{API}/routers", headers=h,
                         json={"name": "x1", "host": "1.2.3.4", "port": 8728,
                               "username": "a", "password": "b", "group_id": head_office_group_id}, timeout=10)
        assert r.status_code == 403

    def test_viewer_config_write_forbidden(self, qa_setup):
        h = {"Authorization": f"Bearer {qa_setup['tok_v']}"}
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/config/addresses/add",
                         headers=h, json={"values": {"address": "10.99.99.99/32", "interface": "lo"}}, timeout=10)
        assert r.status_code == 403

    def test_viewer_read_resource_428(self, qa_setup):
        h = {"Authorization": f"Bearer {qa_setup['tok_v']}"}
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/resources/interfaces", headers=h, timeout=15)
        assert r.status_code == 428, r.text

    def test_nogroup_overview_zero_routers(self, qa_setup):
        h = {"Authorization": f"Bearer {qa_setup['tok_n']}"}
        r = requests.get(f"{API}/monitoring/overview", headers=h, timeout=15)
        assert r.status_code == 200
        assert r.json()["routers"] == []

    def test_nogroup_router_resource_404(self, qa_setup):
        h = {"Authorization": f"Bearer {qa_setup['tok_n']}"}
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/resources/interfaces", headers=h, timeout=15)
        assert r.status_code == 404


# --------------- Groups ---------------
class TestGroups:
    def test_group_hierarchy(self, admin_h):
        r = requests.post(f"{API}/groups", headers=admin_h, json={"name": f"QA Parent {uuid.uuid4().hex[:4]}"}, timeout=10)
        assert r.status_code == 200
        parent = r.json()["group"]
        r = requests.post(f"{API}/groups", headers=admin_h, json={"name": "QA Child", "parent_id": parent["id"]}, timeout=10)
        assert r.status_code == 200
        child = r.json()["group"]

        r = requests.get(f"{API}/groups", headers=admin_h, timeout=10)
        items = r.json()["items"]
        child_row = next(g for g in items if g["id"] == child["id"])
        assert child_row["depth"] == 1
        assert "›" in child_row["path"] and child_row["path"].endswith("QA Child")

        # self parent
        r = requests.put(f"{API}/groups/{child['id']}", headers=admin_h, json={"name": "QA Child", "parent_id": child["id"]}, timeout=10)
        assert r.status_code == 400
        # parent under its child
        r = requests.put(f"{API}/groups/{parent['id']}", headers=admin_h, json={"name": parent["name"], "parent_id": child["id"]}, timeout=10)
        assert r.status_code == 400
        # delete parent while child exists
        r = requests.delete(f"{API}/groups/{parent['id']}", headers=admin_h, timeout=10)
        assert r.status_code == 409
        # delete child first
        r = requests.delete(f"{API}/groups/{child['id']}", headers=admin_h, timeout=10)
        assert r.status_code == 200
        r = requests.delete(f"{API}/groups/{parent['id']}", headers=admin_h, timeout=10)
        assert r.status_code == 200

    def test_head_office_delete_conflict(self, admin_h, head_office_group_id):
        r = requests.delete(f"{API}/groups/{head_office_group_id}", headers=admin_h, timeout=10)
        assert r.status_code == 409


# --------------- Workspaces ---------------
class TestWorkspaces:
    def test_workspace_flow(self, admin_h, admin_token):
        r = requests.post(f"{API}/workspaces", headers=admin_h, json={"name": f"QA Tenant {uuid.uuid4().hex[:4]}"}, timeout=10)
        assert r.status_code == 200
        ws = r.json()["workspace"]

        h = {**admin_h, "X-Workspace": ws["id"]}
        r = requests.get(f"{API}/monitoring/overview", headers=h, timeout=15)
        assert r.status_code == 200
        assert r.json()["routers"] == []
        assert r.json()["groups"] == []

        # default cannot be deleted
        r = requests.delete(f"{API}/workspaces/ws-default", headers=admin_h, timeout=10)
        assert r.status_code == 400
        # delete qa
        r = requests.delete(f"{API}/workspaces/{ws['id']}", headers=admin_h, timeout=10)
        assert r.status_code == 200

    def test_unauthorized_workspace_header(self, admin_h):
        # A workspace admin doesn't have access to must 403 — use a bogus id
        h = {**admin_h, "X-Workspace": "ws-does-not-exist"}
        r = requests.get(f"{API}/monitoring/overview", headers=h, timeout=10)
        assert r.status_code == 403


# --------------- Router write ops on real router ---------------
class TestRouterWrite:
    @pytest.fixture(scope="class")
    def interface_name(self, admin_h):
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/resources/interfaces", headers=admin_h, timeout=20)
        if r.status_code != 200:
            pytest.skip(f"Cannot fetch interfaces: {r.status_code} {r.text[:120]}")
        items = r.json()["items"]
        for name in ("loopback",):
            for it in items:
                if it.get("name") == name:
                    return name
        # pick any
        if items:
            return items[0]["name"]
        pytest.skip("No interfaces available")

    def test_full_add_set_remove(self, admin_h, interface_name):
        payload = {"values": {"address": "10.255.255.254/32", "interface": interface_name, "comment": "netpulse-qa-temp"}}
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/config/addresses/add",
                         headers=admin_h, json=payload, timeout=25)
        assert r.status_code == 200, r.text

        # find id
        r2 = requests.get(f"{API}/routers/{REAL_ROUTER}/resources/addresses", headers=admin_h, timeout=20)
        assert r2.status_code == 200
        row = next((x for x in r2.json()["items"] if x.get("comment") == "netpulse-qa-temp" and x.get("address") == "10.255.255.254/32"), None)
        assert row, "created row not found"
        item_id = row.get("id") or row.get(".id")
        assert item_id and item_id.startswith("*"), f"unexpected id: {item_id}"

        # set comment
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/config/addresses/set",
                         headers=admin_h, json={"values": {"comment": "netpulse-qa-temp2"}, "item_id": item_id}, timeout=20)
        assert r.status_code == 200, r.text

        # remove
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/config/addresses/remove",
                         headers=admin_h, json={"item_id": item_id}, timeout=20)
        assert r.status_code == 200

        # verify gone
        r2 = requests.get(f"{API}/routers/{REAL_ROUTER}/resources/addresses", headers=admin_h, timeout=20)
        assert all(x.get("comment") != "netpulse-qa-temp2" for x in r2.json()["items"])

    def test_invalid_logs_add(self, admin_h):
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/config/logs/add", headers=admin_h, json={"values": {}}, timeout=10)
        assert r.status_code == 400

    def test_set_without_item_id(self, admin_h):
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/config/addresses/set",
                         headers=admin_h, json={"values": {"comment": "x"}}, timeout=10)
        assert r.status_code == 422

    def test_uppercase_key(self, admin_h):
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/config/addresses/add",
                         headers=admin_h, json={"values": {"Foo": "bar"}}, timeout=10)
        assert r.status_code == 422


# --------------- Terminal ---------------
class TestTerminal:
    def test_ip_address_print(self, admin_h):
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/terminal", headers=admin_h,
                          json={"command": "/ip address print"}, timeout=25)
        assert r.status_code == 200, r.text
        b = r.json()
        assert len(b["rows"]) > 0
        assert "elapsed_ms" in b

    def test_interface_where_filter(self, admin_h):
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/terminal", headers=admin_h,
                          json={"command": "/interface print where type=ether"}, timeout=25)
        assert r.status_code == 200

    def test_reboot_blocked(self, admin_h):
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/terminal", headers=admin_h,
                          json={"command": "/system reboot"}, timeout=10)
        assert r.status_code == 403

    def test_no_leading_slash(self, admin_h):
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/terminal", headers=admin_h,
                          json={"command": "ip address print"}, timeout=10)
        assert r.status_code == 422

    def test_no_verb(self, admin_h):
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/terminal", headers=admin_h,
                          json={"command": "/ip address"}, timeout=10)
        assert r.status_code == 422


# --------------- Backups ---------------
class TestBackups:
    def test_backup_create_download_delete(self, admin_h):
        r = requests.post(f"{API}/routers/{REAL_ROUTER}/backup-now", headers=admin_h, timeout=60)
        assert r.status_code == 200, r.text
        bk = r.json()["backup"]
        assert bk["filename"].endswith(".rsc")
        assert len(bk["sections"]) > 0
        assert "storage_path" not in bk
        bid = bk["id"]

        r = requests.get(f"{API}/routers/{REAL_ROUTER}/backups", headers=admin_h, timeout=15)
        assert r.status_code == 200
        row = next((x for x in r.json()["items"] if x["id"] == bid), None)
        assert row and "storage_path" not in row

        r = requests.get(f"{API}/backups/{bid}/download", headers=admin_h, timeout=30)
        assert r.status_code == 200
        assert r.text.startswith("# NetPulse")
        assert "attachment" in r.headers.get("Content-Disposition", "")

        r = requests.delete(f"{API}/backups/{bid}", headers=admin_h, timeout=10)
        assert r.status_code == 200
        r = requests.get(f"{API}/routers/{REAL_ROUTER}/backups", headers=admin_h, timeout=10)
        assert all(x["id"] != bid for x in r.json()["items"])


# --------------- Telegram per role ---------------
class TestTelegram:
    def test_role_telegram_flow(self, admin_h, head_office_group_id):
        # create temp role
        MODULES = ["overview", "routers", "groups", "alarms", "audit", "notifications", "backups", "users", "roles", "workspaces", "ros_config"]
        privs = {m: "none" for m in MODULES}
        r = requests.post(f"{API}/roles", headers=admin_h,
                         json={"name": f"QA TG {uuid.uuid4().hex[:4]}", "description": "qa",
                               "privileges": privs, "group_ids": [head_office_group_id]}, timeout=10)
        assert r.status_code == 200
        role = r.json()["role"]
        try:
            # put
            r = requests.put(f"{API}/notifications/telegram/{role['id']}", headers=admin_h,
                            json={"bot_token": "123456789:AAFakeTokenFakeTokenFakeToken", "chat_id": "-100123",
                                  "enabled": True}, timeout=10)
            assert r.status_code == 200
            assert "•" in r.json()["token_hint"]

            # list
            r = requests.get(f"{API}/notifications/telegram", headers=admin_h, timeout=10)
            row = next(x for x in r.json()["items"] if x["role_id"] == role["id"])
            assert row["configured"] is True

            # test (expect error relayed, not 500)
            r = requests.post(f"{API}/notifications/telegram/{role['id']}/test", headers=admin_h, timeout=15)
            assert r.status_code in (401, 404, 502) and r.status_code != 500, f"got {r.status_code}: {r.text}"
            assert "Telegram" in r.text or "unreachable" in r.text.lower()

            # dispatch — role has alarms=none; try with admin role directly instead
            # Dispatch requires alarms write; admin has it. Router group must match.
            r = requests.post(f"{API}/alarms/dispatch", headers=admin_h,
                             json={"kind": "cpu-threshold", "router_id": REAL_ROUTER, "detail": "qa"}, timeout=20)
            # Real Telegram fake token → send fails → roles_notified=[] but 200
            assert r.status_code == 200, f"{r.status_code} {r.text}"
            assert isinstance(r.json().get("roles_notified"), list)

            # delete
            r = requests.delete(f"{API}/notifications/telegram/{role['id']}", headers=admin_h, timeout=10)
            assert r.status_code == 200

            # unknown role → 404
            r = requests.put(f"{API}/notifications/telegram/role-doesnotexist", headers=admin_h,
                            json={"bot_token": "123456789:AAFakeTokenFakeTokenFakeToken", "chat_id": "-1"}, timeout=10)
            assert r.status_code == 404
        finally:
            requests.delete(f"{API}/roles/{role['id']}", headers=admin_h)
