"""W01 typed-failure witnesses for project and request identity boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project
from starlette.requests import Request

from app.project_customization.registry import (
    register_project_customization_prefix,
)
from app.services.projects import context as project_context
from app.services.projects import workflow as project_workflow
from app.services.request_identity import require_trusted_actor_context
from app.subprojects import registry as extraction_registry
from mrw_functorial_kit.core.application_failure_semantics import (
    project_operation_failures,
    request_identity_failures,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
OWNED_FILES = {
    "main/backend/app/project_customization/registry.py",
    "main/backend/app/services/projects/context.py",
    "main/backend/app/services/projects/workflow.py",
    "main/backend/app/services/request_identity.py",
    "main/backend/app/subprojects/registry.py",
}


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/protected",
            "headers": [(b"x-actor-id", b"legacy-actor")],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
            "state": {},
        }
    )


def test_w01_project_failure_producer_is_closed() -> None:
    failure = project_context._project_failure(
        "prefix_required",
        "prefix is required",
        operation="test",
        site="test_w01",
        public_exception="ValueError",
    )
    assert type(failure) is Failure
    assert project_operation_failures.matches(failure)
    assert (failure.family, failure.code, failure.message) == (
        "project.operation.failure",
        "prefix_required",
        "prefix is required",
    )


def test_w01_project_registry_prefix_paths_preserve_value_error_abi() -> None:
    with pytest.raises(ValueError, match="^prefix is required$"):
        register_project_customization_prefix("", lambda: None)
    with pytest.raises(ValueError, match="^prefix is required$"):
        extraction_registry.register_extraction_adapter_prefix("", object)


def test_w01_project_context_and_workflow_lifts_preserve_public_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(project_context.settings, "project_key_enforcement_mode", "require")
    with pytest.raises(RuntimeError, match="^project key required but missing"):
        project_context.current_project_key()

    failure = project_workflow._workflow_failure(
        "workflow_not_found",
        "workflow not found: missing",
        operation="test",
        site="test_w01",
    )
    with pytest.raises(ValueError, match="^workflow not found: missing$"):
        project_workflow._raise_workflow_failure(failure)


def test_w01_request_identity_preserves_http_403_detail_envelope() -> None:
    with pytest.raises(HTTPException) as raised:
        require_trusted_actor_context(_request())
    assert raised.value.status_code == 403
    assert raised.value.detail["reason_code"] == "trusted_actor_required"
    assert raised.value.detail["next_action"] == "authenticate_request"
    assert raised.value.detail["actor_context"]["identity_source"] == "legacy_header"

    failure = project_context._project_failure(
        "project_key_required",
        "project_key is required",
        operation="test",
        site="test_w01",
        public_exception="ValueError",
    )
    assert project_operation_failures.matches(failure)


def test_w01_request_and_project_failure_families_are_visible() -> None:
    assert request_identity_failures.matches(
        request_identity_failures.fail(
            "trusted_actor_required",
            "trusted actor required",
            {"actor_trusted": False},
        )
    )
    scan = scan_project(REPO_ROOT)
    assert {
        violation.file
        for violation in scan.violations
        if violation.gate == "no-throw-in-core"
        and violation.severity == "fail"
        and violation.file in OWNED_FILES
    } == set()
