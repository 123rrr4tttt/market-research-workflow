from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.e2e


def test_health_endpoint_core_payload_and_contract_exempt_shape() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "provider" in payload
    assert "env" in payload
    assert "data" not in payload
    assert "error" not in payload
    assert "meta" not in payload
    assert response.headers.get("X-Request-Id")


def test_deep_health_endpoint_core_payload_and_contract_exempt_shape() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/deep")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert isinstance(payload.get("database"), str)
    assert isinstance(payload.get("elasticsearch"), str)
    assert "data" not in payload
    assert "error" not in payload
    assert "meta" not in payload
    assert response.headers.get("X-Request-Id")


def test_health_project_key_uses_query_when_header_missing() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health?project_key=query_only")

    assert response.status_code == 200
    assert response.headers.get("X-Project-Key-Source") == "query"
    assert response.headers.get("X-Project-Key-Resolved") == "query_only"


def test_health_project_key_header_takes_precedence_over_query() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health?project_key=query_value",
            headers={"X-Project-Key": "header_value"},
        )

    assert response.status_code == 200
    assert response.headers.get("X-Project-Key-Source") == "header"
    assert response.headers.get("X-Project-Key-Resolved") == "header_value"


def test_deep_health_project_key_uses_query_when_header_missing() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/deep?project_key=deep_query")

    assert response.status_code == 200
    assert response.headers.get("X-Project-Key-Source") == "query"
    assert response.headers.get("X-Project-Key-Resolved") == "deep_query"


def test_deep_health_project_key_header_takes_precedence_over_query() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health/deep?project_key=deep_query",
            headers={"X-Project-Key": "deep_header"},
        )

    assert response.status_code == 200
    assert response.headers.get("X-Project-Key-Source") == "header"
    assert response.headers.get("X-Project-Key-Resolved") == "deep_header"
