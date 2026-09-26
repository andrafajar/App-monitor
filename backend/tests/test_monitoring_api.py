"""Regression coverage for public monitoring and health endpoints."""
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


@pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is not configured")
def test_health_is_public_and_does_not_expose_secrets(api_client):
    response = api_client.get(f"{BASE_URL}/api/health", timeout=15)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["database"] == "connected"
    assert "MONGO_URL" not in response.text
    assert "password" not in response.text.lower()


@pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is not configured")
def test_monitoring_overview_has_router_fleet_and_telemetry(api_client):
    response = api_client.get(f"{BASE_URL}/api/monitoring/overview", timeout=15)
    assert response.status_code == 200
    body = response.json()
    # 4 demo routers + any managed routers merged in
    assert len(body["routers"]) >= 4
    assert "HQ Core Router" in {router["name"] for router in body["routers"]}
    assert body["groups"][0] == "All routers"
    assert body["traffic"]
    assert {"time", "inbound", "outbound"}.issubset(body["traffic"][0])


@pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is not configured")
def test_overview_managed_rows_expose_probe_fields_without_credentials(api_client):
    response = api_client.get(f"{BASE_URL}/api/monitoring/overview", timeout=15)
    assert response.status_code == 200
    raw = response.text
    for secret in ("password_enc", "bot_token", "token_enc", "\"username\"", "\"password\""):
        assert secret not in raw, f"overview leaks {secret}"
    managed = [r for r in response.json()["routers"] if r["id"].startswith("mr-")]
    for row in managed:
        for key in ("cpu", "memory", "uptime", "version", "status", "last_probed_at"):
            assert key in row, f"managed row {row['id']} missing {key}"
        assert row["status"] in ("online", "offline", "pending", "managed", "warning")
