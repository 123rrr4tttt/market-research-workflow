"""Focused W02 agent-batch failure-family and no-throw witnesses."""

from __future__ import annotations

from pathlib import Path

import pytest
from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project

from app.services.agent_batch.approval_binding import approve_approval
from app.services.agent_batch.planner import plan_batch_search_command
from app.services.agent_batch.routing import validate_lane
from app.services.agent_batch.task_contract import (
    _raise_legacy_agent_batch_failure,
    build_agent_batch_manifest_entry,
)
from mrw_functorial_kit.core.agent_service_semantics import agent_batch_failures


REPO_ROOT = Path(__file__).resolve().parents[4]
OWNED_FILES = {
    "main/backend/app/services/agent_batch/agent_loop.py",
    "main/backend/app/services/agent_batch/approval_binding.py",
    "main/backend/app/services/agent_batch/planner.py",
    "main/backend/app/services/agent_batch/routing.py",
    "main/backend/app/services/agent_batch/task_contract.py",
}


def test_w02_agent_batch_core_failures_use_closed_family() -> None:
    failure = agent_batch_failures.fail(
        "channel_unknown",
        "unknown agent batch channel: bad",
        {"channel": "bad"},
    )
    assert type(failure) is Failure
    assert agent_batch_failures.matches(failure)
    assert (failure.family, failure.code, failure.message) == (
        "agent.batch.failure",
        "channel_unknown",
        "unknown agent batch channel: bad",
    )


def test_w02_legacy_lift_preserves_public_exception_observation() -> None:
    with pytest.raises(ValueError, match="^command is required$"):
        plan_batch_search_command("   ")
    with pytest.raises(ValueError, match="^lane is required"):
        validate_lane("invalid")
    with pytest.raises(KeyError, match="unknown agent batch channel: bad"):
        build_agent_batch_manifest_entry("bad")
    with pytest.raises(ValueError, match="^approval_token is required$"):
        approve_approval(approval_token="")


def test_w02_no_throw_scan_is_clear_for_owned_agent_batch_files() -> None:
    scan = scan_project(REPO_ROOT)
    assert {
        violation.file
        for violation in scan.violations
        if violation.gate == "no-throw-in-core"
        and violation.severity == "fail"
        and violation.file in OWNED_FILES
    } == set()


def test_w02_abi_lift_rejects_non_agent_batch_failure_as_programmer_defect() -> None:
    with pytest.raises(TypeError, match="^agent batch ABI lift requires"):
        _raise_legacy_agent_batch_failure(
            Failure("other.family", "other_code", "not an agent batch failure")
        )
