from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.e2e


def test_health_endpoint_smoke() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "provider" in payload
    assert "env" in payload

    # Request middleware should always stamp request id.
    assert response.headers.get("X-Request-Id")
