from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.e2e


def test_deep_health_endpoint_smoke() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/deep")

    assert response.status_code == 200
    payload = response.json()

    # Deep health depends on runtime infra; keep assertion environment-tolerant.
    assert payload["status"] in {"ok", "degraded"}
    assert "database" in payload
    assert "elasticsearch" in payload
    assert isinstance(payload["database"], str)
    assert isinstance(payload["elasticsearch"], str)
