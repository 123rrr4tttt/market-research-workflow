"""W02 witnesses for typed agent-core domain failures and preserved ABI."""

from __future__ import annotations

from functorial_kit import Failure

from app.services.agent_core.authoring_tools import (
    _apply_writing_body_operation,
    _normalize_long_task_stage,
    _normalize_long_task_stage_status,
)


def test_w02_agent_core_registry_defects_remain_explicit() -> None:
    from app.services.agent_core.contracts import CoreToolSpec
    from app.services.agent_core.registry import CoreToolRegistry

    registry = CoreToolRegistry()
    status_failure = registry.simple_result(call=object(), status="not-a-status", model_summary="bad")
    name_failure = registry.register(CoreToolSpec(name="", description_for_model="invalid"), lambda *_: None)

    assert isinstance(status_failure, Failure)
    assert isinstance(name_failure, Failure)
    assert (status_failure.family, status_failure.code) == (
        "agent.runtime.failure",
        "tool_status_unsupported",
    )
    assert (name_failure.family, name_failure.code) == (
        "agent.runtime.failure",
        "tool_name_required",
    )


def test_long_task_normalizers_return_closed_runtime_failures() -> None:
    stage = _normalize_long_task_stage("not-a-stage")
    status = _normalize_long_task_stage_status("not-a-status")

    assert isinstance(stage, Failure)
    assert isinstance(status, Failure)
    assert (stage.family, stage.code) == ("agent.runtime.failure", "long_task_stage_invalid")
    assert (status.family, status.code) == ("agent.runtime.failure", "long_task_stage_status_invalid")


def test_writing_operation_returns_closed_runtime_failure_without_throwing() -> None:
    outcome = _apply_writing_body_operation(
        "# Draft\n\nBody",
        operation="replace_range",
        content_md="replacement",
        anchor_heading="",
        anchor_text="",
        range_start=1,
        range_end=99,
    )

    assert isinstance(outcome, Failure)
    assert outcome.family == "agent.runtime.failure"
    assert outcome.code == "writing_range_invalid"
    assert outcome.context["end"] == 99


def test_writing_success_shape_is_unchanged() -> None:
    outcome = _apply_writing_body_operation(
        "# Draft",
        operation="append",
        content_md="Body",
        anchor_heading="",
        anchor_text="",
    )

    assert outcome == "# Draft\n\nBody\n"
