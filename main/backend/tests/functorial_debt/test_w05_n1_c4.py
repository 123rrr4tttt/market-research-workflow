"""Focused no-throw and compatibility witnesses for W05-N1 C4."""

from __future__ import annotations

import typing
from pathlib import Path

import pytest
from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project

from app.successor_runtime.capabilities import batch_task as c4
from app.successor_runtime.capabilities.batch_task_interpreters import (
    BatchPlanBindingMismatch,
    RetryBindingMismatch,
)
from mrw_functorial_kit.core.w05_capability_semantics import (
    successor_capability_contract_failures,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
OWNED_FILES = (
    "main/backend/app/successor_runtime/capabilities/batch_task.py",
    "main/backend/app/successor_runtime/capabilities/batch_task_interpreters.py",
    "main/backend/app/successor_runtime/capabilities/batch_task_program.py",
)


def test_w05_n1_c4_compatibility() -> None:
    scan = scan_project(REPO_ROOT)
    owned_no_throw = {
        violation.file
        for violation in scan.violations
        if violation.gate == "no-throw-in-core"
        and violation.severity == "fail"
        and violation.file in OWNED_FILES
    }
    assert owned_no_throw == set()


def test_w05_n1_c4_uses_canonical_kit_failures() -> None:
    failure = c4._failure("schema_contract_invalid", "exact message")
    assert isinstance(failure, Failure)
    assert failure.family == "successor.capability.contract_failure"
    assert failure.context is not None
    assert failure.context["capability"] == "batch.task.v2"
    assert failure.context["public_exception"] == "ValueError"
    assert failure.context["public_message"] == "exact message"
    assert successor_capability_contract_failures.matches(failure)


def test_w05_n1_c4_public_compatibility_preserves_type_and_message() -> None:
    with pytest.raises(ValueError, match="^batch task surface must not carry source_mode$"):
        c4.reject_source_mode({"source_mode": "site_search"})
    with pytest.raises(ValueError, match="^unsupported agent-batch channel 'bad'$"):
        c4.AgentBatchTask(task_id="task", channel="bad")
    with pytest.raises(
        ValueError,
        match="^BatchPlanPayload.payload_digest does not match content$",
    ):
        c4.BatchPlanPayload(
            schema_version=c4.BATCH_PLAN_PAYLOAD_SCHEMA,
            operation_kind=c4.BATCH_PLAN_KIND,
            project_key="project",
            registry_revision=1,
            resolved_schema="resolved",
            scope_incarnation="scope",
            scope_digest="0" * 64,
            tasks=(),
            retrieval_mode="hybrid",
            command="robot",
            language="zh",
            coverage_axes=(),
            candidates=None,
            limited_branching_enabled=False,
            payload_digest="0" * 64,
        )
    with pytest.raises(
        ValueError,
        match="^BatchPlanResult.result_digest must be a 64-char lowercase hex digest$",
    ):
        c4.BatchPlanResult(
            schema_version=c4.BATCH_PLAN_RESULT_SCHEMA,
            tasks=(),
            supplementation=c4.SupplementationDecision(False),
            branching=c4.BranchingDecision(False),
            search_brief=c4.SearchBrief(
                intent="",
                goal="",
                coverage_axes=(),
                time_mode="all_time",
                days_back=None,
                search_strategies=(),
                source_preferences=c4.SourcePreferences(False, ()),
            ),
            result_digest="not-hex",
        )
    with pytest.raises(
        ValueError,
        match="^RetryTransition.transition_digest must be a 64-char lowercase hex digest$",
    ):
        c4.RetryTransition(
            kind="RETRY_SKIPPED",
            tasks=(),
            observations={},
            transition_digest="not-hex",
        )
    bundle = c4.build_batch_task_bundle()
    with pytest.raises(KeyError) as missing_codec:
        bundle.codec_by_kind("missing.kind")
    assert missing_codec.value.args == ("no C4 payload codec for kind missing.kind",)
    submission_codec = bundle.codec_by_kind(c4.SUBMISSION_KIND)
    with pytest.raises(
        TypeError,
        match="^submission codec expected AgentBatchSubmission$",
    ):
        submission_codec.encode(object())
    with pytest.raises(
        TypeError,
        match="^historical submission payload requires a JSON object$",
    ):
        c4.decode_historical_submission_payload([])  # type: ignore[arg-type]
    with pytest.raises(
        ValueError,
        match="^unsupported historical submission payload codec$",
    ):
        c4.decode_historical_submission_payload(
            {},
            codec_id="mrw.batch.task-submission.codec.v999",
        )
    with pytest.raises(
        ValueError,
        match="^submission receipt bytes are not a JSON object$",
    ):
        c4.decode_submission_receipt_readback(
            codec_id=c4.SUBMISSION_RECEIPT_CODEC_ID,
            exact_bytes=b"not-json",
            stored_digest="0" * 64,
        )


def test_w05_n1_c4_binding_compatibility_keeps_exception_subtypes() -> None:
    plan_failure = c4._failure(
        "program_binding_invalid",
        "agent_batch.build_batch_plan.v1 binding drift: x",
        public_exception="BatchPlanBindingMismatch",
    )
    with pytest.raises(BatchPlanBindingMismatch, match="^.* binding drift: x$"):
        c4._raise_contract_failure(plan_failure, BatchPlanBindingMismatch)
    retry_failure = c4._failure(
        "program_binding_invalid",
        "agent_batch.reduce_retry_action.v1 binding drift: x",
        public_exception="RetryBindingMismatch",
    )
    with pytest.raises(RetryBindingMismatch, match="^.* binding drift: x$"):
        c4._raise_contract_failure(retry_failure, RetryBindingMismatch)


def test_w05_n1_c4_programmer_defect_lift() -> None:
    incomplete = Failure(
        family=successor_capability_contract_failures.name,
        code="schema_contract_invalid",
        message="must not select a public exception by parsing this message",
    )
    with pytest.raises(
        TypeError,
        match="^contract lift context is incomplete or inconsistent$",
    ):
        c4._raise_contract_failure(incomplete)


def test_w05_agent_batch_authority_metadata() -> None:
    from app.successor_runtime.capabilities.batch_task_program import (
        build_batch_task_plan_program,
        build_batch_task_plan_traversal_program,
        build_batch_task_retry_program,
        build_batch_task_submission_program,
    )

    for function in (
        build_batch_task_plan_program,
        build_batch_task_plan_traversal_program,
        build_batch_task_retry_program,
        build_batch_task_submission_program,
    ):
        hint = typing.get_type_hints(function, include_extras=True)["return"]
        metadata = typing.get_args(hint)[1]
        assert "witness=test:test_w05_agent_batch_authority_metadata" in metadata
