"""Focused authority metadata for the W02 agent-service packet."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
WITNESS = "test:test_w02_agent_authority_metadata"
SERVICE_ROOT = REPO_ROOT / "main" / "backend" / "app" / "services"

EXPECTED: dict[str, dict[str, str]] = {
    "agent_batch/benchmark.py": {
        "build_search_policy_benchmark_pack": (
            "kit:non-authoritative derived_as=view "
            "fact_source=_BENCHMARK_CASES+policy_contract_constants"
        ),
    },
    "agent_batch/planner.py": {
        "build_agent_batch_task_manifest": (
            "kit:non-authoritative derived_as=view "
            "fact_source=plan_payload+plan_inputs"
        ),
        "plan_batch_search_command": (
            "kit:non-authoritative derived_as=view "
            "fact_source=intent+tasks+strategy+constraints"
        ),
    },
    "agent_batch/task_contract.py": {
        "build_agent_batch_approval_argv": (
            "kit:prepared-command effect_boundary=task_contract"
        ),
        "build_agent_batch_dispatch_invocation": (
            "kit:prepared-command effect_boundary=task_contract"
        ),
        "build_agent_batch_dispatch_payload": (
            "kit:prepared-command effect_boundary=task_contract"
        ),
        "build_agent_batch_execution_registry": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_policy_sources"
        ),
        "build_agent_batch_manifest_entry": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_policy_sources"
        ),
        "build_agent_batch_submit_item_data": (
            "kit:non-authoritative derived_as=view "
            "fact_source=normalized_task_input"
        ),
        "build_agent_batch_tasks_schema": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_constants"
        ),
        "build_business_override_params": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task+workflow_run_id"
        ),
        "build_live_quality_threshold_schema": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_constants"
        ),
        "build_provider_quality_readiness_schema": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_constants"
        ),
        "build_quality_promotion_readback_schema": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_constants"
        ),
        "build_retry_action_schema": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_constants"
        ),
        "build_search_brief_schema": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_constants"
        ),
        "build_search_critic_schema": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_constants"
        ),
        "build_search_policy_contract": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_policy_sources"
        ),
        "build_search_quality_replay_schema": (
            "kit:non-authoritative derived_as=view "
            "fact_source=task_contract_constants"
        ),
        "build_source_library_override_params": (
            "kit:non-authoritative derived_as=view "
            "fact_source=business_override+workflow_run_id"
        ),
    },
    "agent_core/external_provider_live_readback.py": {
        "build_agent_core_external_provider_live_readback_evidence": (
            "kit:non-authoritative derived_as=generated_evidence "
            "fact_source=bounded_environment+provider_status_inputs"
        ),
    },
    "agent_core/functorial/workflow.py": {
        "build_workflow_program": (
            "kit:prepared-command effect_boundary=functorial_workflow"
        ),
    },
    "agent_core/live_provider_shim.py": {
        "build_repo_local_live_provider_shim_evidence": (
            "kit:non-authoritative derived_as=generated_evidence "
            "fact_source=repo_local_provider_shim_checks"
        ),
    },
    "agent_core/platform_contract.py": {
        "build_agent_core_platform_contract": (
            "kit:non-authoritative derived_as=view "
            "fact_source=platform_contract_constants"
        ),
        "build_external_framework_boundary": (
            "kit:non-authoritative derived_as=view "
            "fact_source=platform_contract_constants"
        ),
        "build_provider_capability_matrix": (
            "kit:non-authoritative derived_as=view "
            "fact_source=platform_contract_constants"
        ),
    },
    "agent_core/project_tools.py": {
        "build_project_core_tool_registry": (
            "kit:non-authoritative derived_as=view "
            "fact_source=project_core_tool_specs"
        ),
    },
    "agent_core/provider_readiness.py": {
        "build_agent_core_provider_live_readiness_contract": (
            "kit:non-authoritative derived_as=view "
            "fact_source=provider_readiness_contract_constants"
        ),
    },
    "agent_core/provider_trace.py": {
        "build_agent_core_provider_trace_readback_contract": (
            "kit:non-authoritative derived_as=view "
            "fact_source=provider_trace_contract_constants"
        ),
    },
    "agent_core/tool_calling_quality.py": {
        "build_agent_core_tool_calling_quality_contract": (
            "kit:non-authoritative derived_as=view "
            "fact_source=tool_calling_quality_contract_constants"
        ),
    },
    "agent_runtime/progress.py": {
        "build_summary_label": (
            "kit:non-authoritative derived_as=view "
            "fact_source=progress_status_input"
        ),
        "build_task_progress_summary": (
            "kit:non-authoritative derived_as=view "
            "fact_source=progress_item_inputs"
        ),
    },
    "agent_runtime/session_memory.py": {
        "build_budgeted_context": (
            "kit:non-authoritative derived_as=view "
            "fact_source=session_context_inputs"
        ),
        "build_memory_correction_marker": (
            "kit:non-authoritative derived_as=view "
            "fact_source=message_history"
        ),
        "build_project_context": (
            "kit:non-authoritative derived_as=view "
            "fact_source=session+artifact+source+workflow_inputs"
        ),
        "build_session_context_summary": (
            "kit:non-authoritative derived_as=view "
            "fact_source=session+messages+tasks+events+artifacts+approvals"
        ),
        "build_stable_summary": (
            "kit:non-authoritative derived_as=view "
            "fact_source=session+messages+tasks+events+artifacts+approvals"
        ),
        "build_tool_use_summary": (
            "kit:non-authoritative derived_as=view "
            "fact_source=tool_call_history"
        ),
    },
    "agent_runtime/structured_data_search.py": {
        "build_structured_data_model_evidence_manifest": (
            "kit:non-authoritative derived_as=generated_evidence "
            "fact_source=structured_data_model_outputs"
        ),
    },
    "agent_runtime/tool_contract.py": {
        "build_capability_call": (
            "kit:prepared-command effect_boundary=tool_contract"
        ),
        "build_stream_descriptor": (
            "kit:prepared-command effect_boundary=agent_session_stream"
        ),
        "build_tool_definition": (
            "kit:non-authoritative derived_as=view "
            "fact_source=tool_contract_inputs"
        ),
    },
    "agent_runtime/turn_decision.py": {
        "build_routing_hints": (
            "kit:non-authoritative derived_as=view "
            "fact_source=goal+candidate_capabilities"
        ),
        "build_turn_decision_plan": (
            "kit:non-authoritative derived_as=view "
            "fact_source=goal+conversation+candidate_capabilities"
        ),
    },
    "agent_sessions/store.py": {
        "build_agent_session_store": (
            "kit:canonical-read canonical_owner="
            "app.services.agent_sessions.store"
        ),
    },
    "codex_oauth.py": {
        "build_authorize_url": (
            "kit:prepared-command effect_boundary="
            "codex_oauth_authorize_redirect"
        ),
    },
}


def _function_return(path: Path, function_name: str) -> ast.Subscript:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    annotation = function.returns
    assert isinstance(annotation, ast.Subscript)
    assert isinstance(annotation.value, ast.Name)
    assert annotation.value.id == "Annotated"
    assert isinstance(annotation.slice, ast.Tuple)
    return annotation


def test_w02_agent_authority_metadata() -> None:
    function_count = sum(len(functions) for functions in EXPECTED.values())
    assert function_count == 46
    seen: set[tuple[str, str]] = set()

    for relative_path, functions in EXPECTED.items():
        path = SERVICE_ROOT / relative_path
        for function_name, expected_metadata in functions.items():
            annotation = _function_return(path, function_name)
            slice_items = annotation.slice.elts
            assert len(slice_items) == 2
            assert ast.unparse(slice_items[0]) != "None"
            metadata = ast.literal_eval(slice_items[1])
            assert isinstance(metadata, str)
            assert metadata.startswith(expected_metadata)
            assert f"witness={WITNESS}" in metadata
            seen.add((relative_path, function_name))

    assert len(seen) == 46


def test_w02_programmer_defect_boundary() -> None:
    from app.services.agent_core.functorial.catalog import upsert_operator
    from app.services.agent_core.tool_calling_quality import _provider_for

    try:
        upsert_operator(object())
    except TypeError as error:
        assert str(error) == "spec must be an OperatorSpec"
    else:
        raise AssertionError("non-OperatorSpec input must remain a programmer defect")

    try:
        _provider_for("not_a_registered_provider_key")
    except ValueError as error:
        assert str(error) == "unknown provider key: not_a_registered_provider_key"
    else:
        raise AssertionError("unknown private provider key must remain a programmer defect")

    boundary_sources = (
        SERVICE_ROOT / "agent_core/functorial/catalog.py",
        SERVICE_ROOT / "agent_core/tool_calling_quality.py",
    )
    for path in boundary_sources:
        text = path.read_text(encoding="utf-8")
        assert "# kit:boundary owner=" in text
        assert " class=PROGRAMMER_DEFECT failure_family=none " in text
        assert "witness=test:test_w02_programmer_defect_boundary" in text
