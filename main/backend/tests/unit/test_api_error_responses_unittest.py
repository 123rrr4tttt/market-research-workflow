from __future__ import annotations

import json

import pytest

from app.api._error_responses import error_json_response
from app.contracts import ErrorCode
from app.contracts.responses import reset_api_context_meta, set_api_context_meta


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("status_code", "code", "message", "details", "meta"),
    [
        (
            422,
            ErrorCode.INVALID_INPUT,
            "invalid fixture",
            {"field": "trace_id", "reason_code": "TRACE_REQUIRED"},
            None,
        ),
        (
            410,
            ErrorCode.INVALID_INPUT,
            "deprecated fixture",
            {"legacy_status": "410_gone"},
            {"deprecated": "legacy.fixture.v1"},
        ),
        (
            404,
            ErrorCode.NOT_FOUND,
            "missing fixture",
            None,
            None,
        ),
    ],
)
def test_error_json_response_preserves_contract_and_http_projection(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: dict | None,
    meta: dict | None,
) -> None:
    monkeypatch.delenv("CONTRACT_GOVERNANCE_DIR", raising=False)
    monkeypatch.delenv("CONTRACTS_GOVERNANCE_DIR", raising=False)
    tokens = set_api_context_meta(trace_id="trace-shared-error", project_key="project_shared")
    try:
        response = error_json_response(
            status_code,
            code,
            message,
            details=details,
            meta=meta,
        )
    finally:
        reset_api_context_meta(tokens)

    body = json.loads(response.body)
    assert response.status_code == status_code
    assert response.headers["x-error-code"] == code.value
    assert body["status"] == "error"
    assert body["data"] is None
    assert body["error"] == {
        "code": code.value,
        "message": message,
        "details": details or {},
    }
    assert body["detail"] == {"error": body["error"], "message": message}
    assert body["meta"]["trace_id"] == "trace-shared-error"
    assert body["meta"]["project_key"] == "project_shared"
    assert body["meta"]["deprecated"] == (meta or {}).get("deprecated")
