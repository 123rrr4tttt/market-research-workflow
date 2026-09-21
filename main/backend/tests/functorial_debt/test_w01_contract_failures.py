"""W01 witnesses for typed contract failures and preserved Pydantic ABI."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from functorial_kit import Failure
from pydantic import ValidationError

from app.contracts import ingest_digestion, successor_runtime
from app.contracts.schemas import writing


REPO_ROOT = Path(__file__).resolve().parents[4]


def _assert_failure_context(failure: Failure, *, family: str, code: str) -> None:
    assert failure.family == family
    assert failure.code == code
    context = dict(failure.context or {})
    for key in ("owner", "operation", "site", "public_exception", "public_message", "witness"):
        assert context.get(key)
    assert context["public_exception"] == "ValueError"
    assert context["public_message"] == failure.message
    assert context["witness"] == "test:test_w01_contract_failures"


def test_w01_ingest_required_text_core_failure() -> None:
    failure = ingest_digestion._normalize_ingest_required_text(" ", field="scheduler_ref")

    assert isinstance(failure, Failure)
    _assert_failure_context(
        failure,
        family="ingest.long_cycle.contract_failure",
        code="required_text_empty",
    )


def test_w01_writing_query_core_failure() -> None:
    failure = writing._normalize_writing_query("\t", operation="KeywordCardRequest.query")

    assert isinstance(failure, Failure)
    _assert_failure_context(
        failure,
        family="writing.request.contract_failure",
        code="query_required",
    )


def test_w01_successor_runtime_core_failure_codes() -> None:
    failures = (
        successor_runtime._validate_command_payload_kind(
            "rebuild_projection",
            "invalidate_projection",
            operation="test.command",
        ),
        successor_runtime._validate_query_params_kind(
            "projection_events",
            "projection_snapshot",
            operation="test.query",
        ),
        successor_runtime._validate_v2_envelope("ok", None, None),
        successor_runtime._validate_v2_envelope("blocked", None, None),
        successor_runtime._validate_legacy_envelope("ok", None, object()),
        successor_runtime._validate_sse_observation(3, [], 4),
    )
    expected_codes = (
        "command_payload_kind_mismatch",
        "query_params_kind_mismatch",
        "successful_envelope_data_missing",
        "error_envelope_details_missing",
        "non_error_envelope_details_present",
        "sse_next_seq_mismatch",
    )
    for failure, code in zip(failures, expected_codes, strict=True):
        assert isinstance(failure, Failure)
        _assert_failure_context(
            failure,
            family="successor_runtime.dto.contract_failure",
            code=code,
        )


def test_w01_ingest_pydantic_lift_preserves_validation_error() -> None:
    with pytest.raises(ValidationError, match=r"value must not be empty"):
        ingest_digestion.LongCycleSchedulerDispatchIntent(
            dispatch_key="dispatch",
            idempotency_key="idempotency",
            scheduler_ref="   ",
            task_key="task",
            selected_window="window",
            cadence="manual",
            run_at="2026-01-01T00:00:00Z",
        )


@pytest.mark.parametrize("model", [writing.KeywordCardRequest, writing.SuggestRequest])
def test_w01_writing_pydantic_lift_preserves_validation_error(model: type[object]) -> None:
    with pytest.raises(ValidationError, match=r"query is required"):
        model(query=" ")


def test_w01_successor_pydantic_lifts_preserve_validation_error() -> None:
    command = {
        "command_id": "command",
        "command_kind": "rebuild_projection",
        "project_locator": "project",
        "trace_id": "trace",
        "payload": {
            "payload_kind": "invalidate_projection",
            "projection_id": "projection",
            "projector_id": "projector",
            "projector_version": "v1",
            "source_kind": "journal",
            "source_ref": "source",
            "source_incarnation": "incarnation",
        },
    }
    with pytest.raises(ValidationError, match=r"command_kind must match the typed payload_kind"):
        successor_runtime.SuccessorRuntimeCommandV2DTO.model_validate(command)


@pytest.mark.parametrize(
    "relative_path",
    (
        "main/backend/app/contracts/ingest_digestion.py",
        "main/backend/app/contracts/schemas/writing.py",
        "main/backend/app/contracts/successor_runtime.py",
    ),
)
def test_w01_each_contract_file_has_one_pydantic_lift_raise(relative_path: str) -> None:
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    raises = [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Raise)]
    assert len(raises) == 1
