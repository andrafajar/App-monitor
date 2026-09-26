"""Telegram notification config + alarm dispatch endpoint tests (iteration 6)."""
import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

GROUP = "Head Office"
DISABLED_GROUP = "TEST_DisabledGroup"
FAKE_TOKEN = "1234567890:AAABBBCCCdddEEEfff-gg_hh"
FAKE_CHAT = "-4001112223333"
EXPECTED_HINT = "12345••••g_hh"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    yield s
    for g in (GROUP, DISABLED_GROUP, "TEST_SendGroup"):
        s.delete(f"{API}/notifications/telegram/{requests.utils.quote(g)}")
    s.close()


# --- listing ---
class TestTelegramList:
    def test_list_returns_items(self, client):
        r = client.get(f"{API}/notifications/telegram")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        for row in data["items"]:
            assert "bot_token" not in row and "token_enc" not in row
            assert "_id" not in row


# --- upsert / persistence / masking ---
class TestTelegramUpsert:
    def test_put_valid_config(self, client):
        r = client.put(f"{API}/notifications/telegram/Head%20Office",
                       json={"bot_token": FAKE_TOKEN, "chat_id": FAKE_CHAT, "enabled": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["token_hint"] == EXPECTED_HINT
        assert d["enabled"] is True
        assert FAKE_TOKEN not in r.text

    def test_get_after_put_masked(self, client):
        r = client.get(f"{API}/notifications/telegram")
        assert r.status_code == 200
        assert FAKE_TOKEN not in r.text
        row = next((x for x in r.json()["items"] if x["group"] == GROUP), None)
        assert row is not None, "Head Office row not persisted"
        assert row["token_hint"] == EXPECTED_HINT
        assert row["chat_id"] == FAKE_CHAT
        assert row["enabled"] is True
        assert "bot_token" not in row and "token_enc" not in row

    def test_put_invalid_token(self, client):
        r = client.put(f"{API}/notifications/telegram/Head%20Office",
                       json={"bot_token": "nope", "chat_id": FAKE_CHAT, "enabled": True})
        assert r.status_code == 422, r.text

    def test_put_invalid_chat_id(self, client):
        r = client.put(f"{API}/notifications/telegram/Head%20Office",
                       json={"bot_token": FAKE_TOKEN, "chat_id": "x", "enabled": True})
        assert r.status_code == 422, r.text

    def test_put_missing_token(self, client):
        r = client.put(f"{API}/notifications/telegram/Head%20Office",
                       json={"chat_id": FAKE_CHAT, "enabled": True})
        assert r.status_code == 422, r.text


# --- send test ---
class TestTelegramSendTest:
    SEND_GROUP = "TEST_SendGroup"

    def test_test_with_fake_token_returns_telegram_error(self, client):
        # self-sufficient + isolated group so parallel delete tests cannot race this
        client.put(f"{API}/notifications/telegram/{self.SEND_GROUP}",
                   json={"bot_token": FAKE_TOKEN, "chat_id": FAKE_CHAT, "enabled": True})
        r = client.post(f"{API}/notifications/telegram/{self.SEND_GROUP}/test")
        assert r.status_code in (401, 502), f"unexpected {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "Telegram" in detail, detail
        assert FAKE_TOKEN not in r.text
        assert "1234567890" not in r.text

    def test_test_unknown_group_404(self, client):
        r = client.post(f"{API}/notifications/telegram/NonExistent/test")
        assert r.status_code == 404, r.text
        assert r.json()["detail"] == "Telegram is not configured for this group"


# --- alarm dispatch ---
class TestAlarmDispatch:
    def test_dispatch_unknown_group_404(self, client):
        r = client.post(f"{API}/alarms/dispatch",
                        json={"kind": "test", "group": "Ghost", "router_name": "x", "detail": "y"})
        assert r.status_code == 404, r.text

    def test_dispatch_invalid_kind_422(self, client):
        r = client.post(f"{API}/alarms/dispatch",
                        json={"kind": "bogus", "group": GROUP, "router_name": "x", "detail": "y"})
        assert r.status_code == 422, r.text

    def test_dispatch_disabled_group_409(self, client):
        put = client.put(f"{API}/notifications/telegram/{DISABLED_GROUP}",
                         json={"bot_token": FAKE_TOKEN, "chat_id": FAKE_CHAT, "enabled": False})
        assert put.status_code == 200, put.text
        assert put.json()["enabled"] is False
        r = client.post(f"{API}/alarms/dispatch",
                        json={"kind": "cpu-threshold", "group": DISABLED_GROUP, "router_name": "x", "detail": "83%"})
        assert r.status_code == 409, r.text
        assert "disabled" in r.json()["detail"].lower()


# --- delete ---
class TestTelegramDelete:
    def test_delete_then_missing(self, client):
        client.put(f"{API}/notifications/telegram/Head%20Office",
                   json={"bot_token": FAKE_TOKEN, "chat_id": FAKE_CHAT, "enabled": True})
        r = client.delete(f"{API}/notifications/telegram/Head%20Office")
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
        listing = client.get(f"{API}/notifications/telegram")
        assert all(x["group"] != GROUP for x in listing.json()["items"])

    def test_delete_again_404(self, client):
        r = client.delete(f"{API}/notifications/telegram/Head%20Office")
        assert r.status_code == 404, r.text


# --- regression: existing endpoints ---
class TestRegression:
    def test_health(self, client):
        r = client.get(f"{API}/health")
        assert r.status_code == 200
        assert r.json()["database"] == "connected"

    def test_overview(self, client):
        r = client.get(f"{API}/monitoring/overview")
        assert r.status_code == 200
        d = r.json()
        assert len(d["routers"]) >= 4 and len(d["traffic"]) == 12
        assert "Head Office" in d["groups"]

    @pytest.mark.parametrize("resource", ["logs", "ppp-profiles", "ppp-secrets", "system-clock", "interfaces"])
    def test_demo_router_resources_404(self, client, resource):
        r = client.get(f"{API}/routers/r-01/resources/{resource}")
        assert r.status_code == 404, r.text

    def test_unknown_resource_400(self, client):
        r = client.get(f"{API}/routers/r-01/resources/bogus")
        assert r.status_code == 400, r.text
