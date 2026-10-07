from __future__ import annotations

from typing import Any

import pytest

from app.project_customization.interfaces import WorkflowDefinition, WorkflowStep
from app.services.agent_core.contracts import CoreToolResult, CoreToolSpec
from app.services.agent_core.registry import CoreToolRegistry
from app.services.projects import workflow as workflow_module
from mrw_functorial_kit.core.agent_service_semantics import agent_runtime_failures


def _workflow(*steps: WorkflowStep) -> tuple[str, WorkflowDefinition]:
    return "project-1", WorkflowDefinition(steps=list(steps))


def test_project_workflow_uses_core_registry_and_preserves_disabled_and_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        workflow_module,
        "_resolve_workflow",
        lambda *_: _workflow(
            WorkflowStep(handler="ingest.market", enabled=False, name="disabled"),
            WorkflowStep(
                handler="ingest.market",
                params={"limit": 2, "nested": {"left": 1}},
            ),
        ),
    )

    def collect(**params: Any) -> dict[str, Any]:
        calls.append(params)
        return {"inserted": 1}

    monkeypatch.setattr(workflow_module, "collect_market_info", collect)

    result = workflow_module.execute_project_workflow(
        workflow_name="demo",
        project_key="project-1",
        params={"limit": 4, "nested": {"right": 2}},
    )

    assert calls == [
        {
            "keywords": [],
            "limit": 4,
            "enable_extraction": True,
        }
    ]
    assert [step["status"] for step in result["steps"]] == ["skipped", "ok"]
    assert result["steps"][1]["params"] == {
        "limit": 4,
        "nested": {"left": 1, "right": 2},
    }
    assert result["steps"][1]["tool_status"] == "completed"
    assert result["status"] == "ok"


def test_project_workflow_registration_failure_preserves_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = agent_runtime_failures.fail(
        "tool_name_required",
        "tool spec name is required",
        {"field": "name"},
    )
    monkeypatch.setattr(
        CoreToolRegistry,
        "register",
        lambda _self, _spec, _handler: failure,
    )

    with pytest.raises(ValueError, match="^tool spec name is required$"):
        workflow_module.build_project_workflow_tool_registry()


def test_project_workflow_preserves_typed_blocked_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = CoreToolRegistry()
    spec = CoreToolSpec(
        name="approval.step",
        description_for_model="approval",
        permission="ask",
    )
    registry.register(
        spec,
        lambda call, *_: CoreToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="completed",
            model_summary="must not execute",
        ),
    )
    monkeypatch.setattr(
        workflow_module,
        "_resolve_workflow",
        lambda *_: _workflow(
            WorkflowStep(handler="approval.step"),
            WorkflowStep(handler="approval.step"),
        ),
    )
    monkeypatch.setattr(
        workflow_module,
        "build_project_workflow_tool_registry",
        lambda: registry,
    )

    result = workflow_module.execute_project_workflow(workflow_name="demo")

    assert result["status"] == "blocked"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["tool_status"] == "needs_approval"
    assert result["steps"][0]["status"] == "blocked"


def test_project_workflow_missing_handler_preserves_public_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        workflow_module,
        "_resolve_workflow",
        lambda *_: _workflow(WorkflowStep(handler="missing.step")),
    )

    with pytest.raises(ValueError, match="workflow handler not found: missing.step"):
        workflow_module.execute_project_workflow(workflow_name="demo")
