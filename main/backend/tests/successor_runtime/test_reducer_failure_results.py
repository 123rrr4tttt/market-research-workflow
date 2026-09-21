"""Focused Failure-family and no-throw witnesses for the runtime reducer."""

from __future__ import annotations

from pathlib import Path

import pytest
from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project

from app.successor_runtime.runtime.reducer import (
    BranchArmControl,
    BranchSelectionControl,
    CompletionPolicy,
    RunSnapshot,
    StepSnapshot,
    guard_holds,
    guard_holds_result,
    reduce_run_completion_result,
    reduce_run_event_result,
    reduce_step,
    reduce_step_result,
)
from app.successor_runtime.runtime.transitions import (
    IllegalTransition,
    RunEvent,
    RunState,
    StepEvent,
    StepState,
)


ROOT = Path(__file__).resolve().parents[4]
REDUCER = "main/backend/app/successor_runtime/runtime/reducer.py"


def test_reducer_has_no_unqualified_core_throws() -> None:
    scan = scan_project(ROOT)
    assert [
        violation
        for violation in scan.violations
        if violation.file == REDUCER
        and violation.gate == "no-throw-in-core"
        and violation.severity == "fail"
    ] == []


def test_reducer_result_paths_return_runtime_failures() -> None:
    step = StepSnapshot("step", StepState.PENDING)
    step_failure = reduce_step_result(
        step, StepEvent.PURE_VALUE_PRODUCED, StepState.SUCCEEDED, guard=True
    )
    assert isinstance(step_failure, Failure)
    assert step_failure.family == "successor.runtime.failure"
    assert step_failure.code == "ILLEGAL_STEP_TRANSITION"

    guard_failure = guard_holds_result("outcome.", {})
    assert isinstance(guard_failure, Failure)
    assert guard_failure.code == "GUARD_EXPRESSION_INVALID"

    run = RunSnapshot("run", RunState.SUBMITTED)
    completion_failure = reduce_run_completion_result(
        run, (), CompletionPolicy(frozenset())
    )
    assert isinstance(completion_failure, Failure)
    assert completion_failure.code == "ILLEGAL_RUN_TRANSITION"

    event_failure = reduce_run_event_result(
        run, RunEvent.RUN_COMPLETION_DERIVED, RunState.COMPLETED, guard=True
    )
    assert isinstance(event_failure, Failure)
    assert event_failure.code == "RUN_EVENT_INVALID"


def test_reducer_legacy_lifts_preserve_exception_abi() -> None:
    with pytest.raises(IllegalTransition, match="illegal step transition"):
        reduce_step(
            StepSnapshot("step", StepState.PENDING),
            StepEvent.PURE_VALUE_PRODUCED,
            StepState.SUCCEEDED,
            guard=True,
        )
    with pytest.raises(ValueError, match="compiled guard expression is invalid"):
        guard_holds("outcome.", {})


def test_reducer_programmer_defect_boundaries() -> None:
    with pytest.raises(ValueError, match="branch control requires identity"):
        BranchArmControl("", (), ())
    with pytest.raises(ValueError, match="branch selection control identity"):
        BranchSelectionControl("", "", "", "0" * 64, ())

    source = (ROOT / REDUCER).read_text(encoding="utf-8")
    assert "owner=successor.runtime.reducer.invariant" in source
    assert "class=PROGRAMMER_DEFECT" in source
    assert "witness=test:test_reducer_programmer_defect_boundaries" in source
