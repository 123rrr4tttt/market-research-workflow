from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

try:
    from fastapi.testclient import TestClient

    from app.api import project_customization as customization_api
    from app.contracts.errors import ErrorCode
    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


@pytest.fixture(scope="module")
def client():
    if _IMPORT_ERROR is not None:
        pytest.skip(f"project customization core contract tests require backend dependencies: {_IMPORT_ERROR}")
    return TestClient(backend_app)


def _fake_customization(project_key: str = "demo_proj"):
    return SimpleNamespace(
        project_key=project_key,
        get_workflow_mapping=lambda: {},
    )


def test_get_workflow_template_missing_name_returns_invalid_input_envelope(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(customization_api, "get_project_customization", lambda project_key=None: _fake_customization())

    response = client.get("/api/v1/project-customization/workflows/%20%20/template")

    assert response.status_code == 400
    assert response.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert payload["detail"]["error"]["details"]["field"] == "workflow_name"


def test_get_workflow_template_missing_workflow_returns_not_found_envelope(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(customization_api, "get_project_customization", lambda project_key=None: _fake_customization())

    response = client.get("/api/v1/project-customization/workflows/demo/template")

    assert response.status_code == 404
    assert response.headers.get("x-error-code") == ErrorCode.NOT_FOUND.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert payload["detail"]["error"]["details"]["workflow_name"] == "demo"


def test_upsert_workflow_template_requires_project_key_and_valid_steps(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(customization_api, "get_project_customization", lambda project_key=None: _fake_customization(project_key=""))

    missing_key = client.post(
        "/api/v1/project-customization/workflows/demo/template",
        json={"project_key": "", "steps": [{"handler": "ingest.market"}], "board_layout": {}},
    )
    invalid_steps = client.post(
        "/api/v1/project-customization/workflows/demo/template",
        json={"project_key": "demo_proj", "steps": [{"handler": " "}], "board_layout": {}},
    )

    assert missing_key.status_code == 400
    assert missing_key.headers.get("x-error-code") == ErrorCode.PROJECT_KEY_REQUIRED.value
    assert missing_key.json()["detail"]["error"]["code"] == ErrorCode.PROJECT_KEY_REQUIRED.value

    assert invalid_steps.status_code == 400
    assert invalid_steps.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    assert invalid_steps.json()["detail"]["error"]["details"]["field"] == "steps[1].handler"


def test_delete_workflow_template_missing_custom_workflow_returns_not_found_envelope(client):
    response = client.delete(
        "/api/v1/project-customization/workflows/demo/template",
        params={"project_key": "demo_proj"},
    )

    assert response.status_code == 404
    assert response.headers.get("x-error-code") == ErrorCode.NOT_FOUND.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.NOT_FOUND.value
    assert payload["detail"]["error"]["details"]["workflow_name"] == "demo"


def test_run_workflow_errors_use_standard_envelope(client, monkeypatch: pytest.MonkeyPatch):
    def _boom(**_kwargs):
        raise ValueError("bad workflow input")

    monkeypatch.setattr(customization_api, "execute_project_workflow", _boom)

    missing_key = client.post(
        "/api/v1/project-customization/workflows/demo/run",
        json={"project_key": "", "params": {}},
    )
    invalid_run = client.post(
        "/api/v1/project-customization/workflows/demo/run",
        json={"project_key": "demo_proj", "params": {}},
    )

    assert missing_key.status_code == 400
    assert missing_key.headers.get("x-error-code") == ErrorCode.PROJECT_KEY_REQUIRED.value
    assert missing_key.json()["detail"]["error"]["code"] == ErrorCode.PROJECT_KEY_REQUIRED.value

    assert invalid_run.status_code == 400
    assert invalid_run.headers.get("x-error-code") == ErrorCode.INVALID_INPUT.value
    payload = invalid_run.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.INVALID_INPUT.value


def test_run_workflow_not_found_error_uses_matching_status_code(client, monkeypatch: pytest.MonkeyPatch):
    def _missing(**_kwargs):
        raise RuntimeError("workflow not found")

    monkeypatch.setattr(customization_api, "execute_project_workflow", _missing)

    response = client.post(
        "/api/v1/project-customization/workflows/demo/run",
        json={"project_key": "demo_proj", "params": {}},
    )

    assert response.status_code == 404
    assert response.headers.get("x-error-code") == ErrorCode.NOT_FOUND.value
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == ErrorCode.NOT_FOUND.value
