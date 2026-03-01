from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.e2e


def test_health_resolves_project_key_from_header() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health", headers={"X-Project-Key": "My_Project-01"})

    assert response.status_code == 200
    assert response.headers.get("X-Project-Key-Source") == "header"
    # Current middleware contract exposes the original resolved source value.
    assert response.headers.get("X-Project-Key-Resolved") == "My_Project-01"


def test_header_takes_precedence_over_query_project_key() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health?project_key=query_one",
            headers={"X-Project-Key": "header_two"},
        )

    assert response.status_code == 200
    assert response.headers.get("X-Project-Key-Source") == "header"
    assert response.headers.get("X-Project-Key-Resolved") == "header_two"
