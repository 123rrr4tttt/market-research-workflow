from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

_TARGET_MODULE_COUNTS = {
    "discovery.py": 5,
    "project_customization.py": 8,
}

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import discovery as discovery_api
    from app.api import project_customization as customization_api
    from app.main import app as backend_app
    from scripts.generate_api_schema_inventory import build_inventory

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


def _require_imports() -> None:
    if _IMPORT_ERROR is not None:
        pytest.skip(f"discovery/project customization schema tests require backend dependencies: {_IMPORT_ERROR}")


def _target_operations() -> list[dict]:
    _require_imports()
    backend_app.openapi_schema = None
    inventory = build_inventory(backend_app)
    return [
        operation
        for operation in inventory["operations"]
        if operation["source_module"] in _TARGET_MODULE_COUNTS
    ]


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    _require_imports()
    monkeypatch.setattr(discovery_api, "start_job", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(discovery_api, "complete_job", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(discovery_api, "fail_job", lambda *_args, **_kwargs: None)

    app = FastAPI()
    app.include_router(discovery_api.router, prefix="/api/v1")
    app.include_router(customization_api.router, prefix="/api/v1")
    return TestClient(app)


def test_discovery_and_project_customization_have_typed_200_response_schemas():
    operations = _target_operations()
    counts = {module: 0 for module in _TARGET_MODULE_COUNTS}
    for operation in operations:
        counts[operation["source_module"]] += 1

    assert counts == _TARGET_MODULE_COUNTS
    assert sum(counts.values()) == 13
    assert [
        f"{operation['method']} {operation['path']}"
        for operation in operations
        if operation["response_200_schema"] == "untyped"
    ] == []
    assert [
        f"{operation['method']} {operation['path']}"
        for operation in operations
        if operation["response_model"] == "none"
    ] == []
    assert all("ApiEnvelope" in operation["response_model"] for operation in operations)


def test_discovery_search_runtime_payload_is_preserved(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        discovery_api.discovery_app,
        "run_search",
        lambda **_kwargs: {
            "results": [{"title": "sample", "score": 0.75}],
            "stored": {"inserted": 1},
            "provider": "fixture",
        },
    )

    response = client.post(
        "/api/v1/discovery/search",
        json={
            "topic": "ai chips",
            "language": "en",
            "max_results": 5,
            "provider": "auto",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"status", "data", "error", "meta"}
    assert payload["status"] == "ok"
    assert payload["error"] is None
    assert payload["data"] == {
        "results": [{"title": "sample", "score": 0.75}],
        "stored": {"inserted": 1},
        "provider": "fixture",
    }


def test_project_customization_menu_runtime_payload_is_preserved(client, monkeypatch: pytest.MonkeyPatch):
    customization = SimpleNamespace(
        project_key="demo_proj",
        get_menu_config=lambda: {
            "sections": [{"id": "sources", "label": "Sources"}],
            "enabled": True,
        },
    )
    monkeypatch.setattr(customization_api, "get_project_customization", lambda project_key=None: customization)

    response = client.get("/api/v1/project-customization/menu", params={"project_key": "demo_proj"})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"status", "data", "error", "meta"}
    assert payload["status"] == "ok"
    assert payload["error"] is None
    assert payload["data"] == {
        "project_key": "demo_proj",
        "menu": {
            "sections": [{"id": "sources", "label": "Sources"}],
            "enabled": True,
        },
    }
