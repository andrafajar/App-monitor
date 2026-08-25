"""Regression coverage for public monitoring and health endpoints."""
import os

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


@pytest.fixture
def api_client():
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    return session


@pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is not configured")
def test_health_is_public_and_does_not_expose_secrets(api_client):
    response = api_client.get(f"{BASE_URL.rstrip('/')}/api/health", timeout=15)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["database"] in {"connected", "unavailable"}
    assert "MONGO_URL" not in response.text
    assert "password" not in response.text.lower()


@pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL is not configured")
def test_monitoring_overview_has_router_fleet_and_telemetry(api_client):
    response = api_client.get(f"{BASE_URL.rstrip('/')}/api/monitoring/overview", timeout=15)
    assert response.status_code == 200
    body = response.json()
    assert len(body["routers"]) == 4
    assert "HQ Core Router" in {router["name"] for router in body["routers"]}
    assert body["groups"][0] == "All routers"
    assert body["traffic"]
    assert {"time", "inbound", "outbound"}.issubset(body["traffic"][0])
