"""Regression coverage for native RouterOS management and backup API boundaries."""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL") or "").rstrip("/")


@pytest.fixture
def api_client():
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    return session


pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is not configured")


def url(path):
    return f"{BASE_URL}{path}"


def test_unknown_resource_is_rejected_before_router_lookup(api_client):
    response = api_client.get(url("/api/routers/r-01/resources/secret"), timeout=15)
    assert response.status_code == 400
    assert "allow-listed" in response.json()["detail"]


def test_allowlisted_resource_requires_managed_router(api_client):
    response = api_client.get(url("/api/routers/r-01/resources/interfaces"), timeout=15)
    assert response.status_code == 404
    assert "managed inventory" in response.json()["detail"]


def test_unknown_action_is_rejected(api_client):
    response = api_client.post(url("/api/routers/r-01/actions/run-command"), json={"item_id": "*1"}, timeout=15)
    assert response.status_code == 400
    assert "allow-listed" in response.json()["detail"]


def test_reboot_is_explicitly_blocked(api_client):
    response = api_client.post(url("/api/routers/r-01/actions/reboot"), json={"item_id": "*1"}, timeout=15)
    assert response.status_code == 403
    assert "Super Admin" in response.json()["detail"]


def test_invalid_routeros_item_id_is_rejected(api_client):
    response = api_client.post(url("/api/routers/r-01/actions/interface-disable"), json={"item_id": "ether1"}, timeout=15)
    assert response.status_code == 422


def test_create_router_never_echoes_plaintext_password(api_client):
    """CREDENTIALS_FERNET_KEY is configured, so create succeeds; the plaintext must never come back."""
    response = api_client.post(url("/api/routers"), json={
        "name": "TEST_secure-router", "host": "192.0.2.1", "username": "TEST_user", "password": "TEST_plaintext",
    }, timeout=120)
    assert response.status_code in (200, 503), response.text
    assert "TEST_plaintext" not in response.text
    if response.status_code == 503:
        assert "CREDENTIALS_FERNET_KEY" in response.json()["detail"]
        return
    body = response.json()
    assert body["router"]["status"] == "offline"
    assert "password_enc" not in response.text
    assert api_client.delete(url(f"/api/routers/{body['router']['id']}"), timeout=30).status_code == 200


def test_backup_now_reports_missing_configuration_for_demo_router(api_client):
    response = api_client.post(url("/api/routers/r-01/backup-now"), timeout=15)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "configuration_required"
    assert "BACKUP_ROOT" in body["message"]


def test_backup_history_is_secret_free(api_client):
    response = api_client.get(url("/api/routers/r-01/backups"), timeout=15)
    assert response.status_code == 200
    assert isinstance(response.json()["items"], list)
    assert "password" not in response.text.lower()


def test_schedule_requires_managed_router(api_client):
    response = api_client.post(url("/api/routers/r-01/backup-schedule"), json={"frequency": "daily", "hour": 2, "minute": 30}, timeout=15)
    assert response.status_code == 404
    assert "managed inventory" in response.json()["detail"]


def test_schedule_validates_frequency(api_client):
    response = api_client.post(url("/api/routers/r-01/backup-schedule"), json={"frequency": "hourly", "hour": 2, "minute": 30}, timeout=15)
    assert response.status_code == 422


def test_health_and_overview_remain_available(api_client):
    health = api_client.get(url("/api/health"), timeout=15)
    overview = api_client.get(url("/api/monitoring/overview"), timeout=15)
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert overview.status_code == 200
    assert len(overview.json()["routers"]) >= 4
