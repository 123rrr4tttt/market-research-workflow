"""Exact semantic resolutions for packet W01 app surfaces and backend services."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

import pytest
from functorial_kit import Failure

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.llm_report_generator import build_report_capability_truth
from app.services.source_library.single_source_guard import (
    SourceLibrarySingleSourceGuardError,
    validate_single_source_guard,
)
from app.services.streamplus.contracts import build_idempotency_key
from app.services.task_readback_metadata import build_runtime_readback_payload

W01_ROOT = Path(__file__).resolve().parents[4]
WITNESS = "test:test_w01_meta"


EXPECTED_DERIVED_METADATA = {
    "main/backend/app/api/business_lines.py": {
        "build_evidence_matrix": "view fact_source=api.business_lines",
        "build_scheduled_artifact_drilldown": "view fact_source=api.business_lines",
        "build_scheduled_artifact_summaries": "view fact_source=api.business_lines",
        "build_scheduled_matrix_artifact_summary": "view fact_source=api.business_lines",
    },
    "main/backend/app/api/workflow_graph.py": {
        "build_workflow_graph_reporting_handoff": "view fact_source=api.workflow_graph",
        "build_workflow_graph_writing_handoff": "view fact_source=api.workflow_graph",
    },
    "main/backend/app/services/llm/chains.py": {
        "build_policy_classification_chain": "prepared-command effect_boundary=llm.chains",
        "build_policy_summary_chain": "prepared-command effect_boundary=llm.chains",
    },
    "main/backend/app/services/llm/platformization.py": {
        "build_trace_audit_record": (
            "generated_evidence fact_source=llm.runtime_trace"
        ),
    },
    "main/backend/app/services/llm_report_export.py": {
        "build_llm_report_export_artifact": (
            "generated_evidence fact_source=llm.report_export"
        ),
    },
    "main/backend/app/services/llm_report_generator.py": {
        "build_report_capability_truth": (
            "external_claim fact_source=llm.report_contract"
        ),
        "build_structured_report": (
            "generated_evidence fact_source=llm.report_template"
        ),
    },
    "main/backend/app/services/llm_report_trends.py": {
        "build_export_trend_metric": (
            "generated_evidence fact_source=llm.report_export"
        ),
        "build_quality_trend_metric": (
            "view fact_source=llm.report_quality_gate"
        ),
    },
    "main/backend/app/services/source_library/external_project.py": {
        "build_external_project_summary": (
            "view fact_source=source_library.manifest"
        ),
    },
    "main/backend/app/services/source_library/item_plan.py": {
        "build_item_definition_view": (
            "view fact_source=source_library.item_definition"
        ),
        "build_item_execution_plan": (
            "prepared-command effect_boundary=source_library.item_execution"
        ),
    },
    "main/backend/app/services/source_library/relevance_review.py": {
        "build_relevance_review_queue": (
            "view fact_source=source_library.review_candidates"
        ),
        "build_taxonomy_review_readiness": (
            "preflight fact_source=source_library.taxonomy_review"
        ),
    },
    "main/backend/app/services/source_library/single_source_guard.py": {
        "build_single_source_execution_fact": (
            "view fact_source=source_library.single_source_guard"
        ),
        "build_single_source_guard_error_details": (
            "view fact_source=source_library.single_source_guard"
        ),
    },
    "main/backend/app/services/source_library/source_candidate_trust.py": {
        "build_candidate_search_queries": (
            "prepared-command effect_boundary=source_library.candidate_search"
        ),
        "build_source_candidate_plan": (
            "prepared-command effect_boundary=source_library.candidate_search"
        ),
    },
    "main/backend/app/services/source_library/terminal_output.py": {
        "build_source_library_terminal_output": (
            "view fact_source=source_library.raw_result"
        ),
        "build_terminal_output_dto": (
            "view fact_source=source_library.raw_result"
        ),
    },
    "main/backend/app/services/source_library/types.py": {
        "build_source_concurrency_plan": (
            "prepared-command effect_boundary=source_library.concurrency"
        ),
    },
    "main/backend/app/services/stats/prompt_time_density.py": {
        "build_policy_decision_trace": (
            "view fact_source=prompt_time_density.decision_log"
        ),
        "build_time_density_decision_log_features": (
            "view fact_source=prompt_time_density.decision_log"
        ),
        "build_time_density_live_gap_markers": (
            "view fact_source=prompt_time_density.trace"
        ),
    },
    "main/backend/app/services/streamplus/contracts.py": {
        "build_idempotency_key": (
            "prepared-command effect_boundary=streamplus.idempotency"
        ),
    },
    "main/backend/app/services/task_readback_metadata.py": {
        "build_runtime_readback_payload": (
            "view fact_source=task.runtime_readback"
        ),
    },
}


def _return_annotation(file_path: Path, function_name: str) -> str:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )
    assert function.returns is not None
    return ast.unparse(function.returns)


def test_w01_meta() -> None:
    assert len(EXPECTED_DERIVED_METADATA) == 17
    assert sum(len(functions) for functions in EXPECTED_DERIVED_METADATA.values()) == 31

    for relative_path, functions in EXPECTED_DERIVED_METADATA.items():
        source_path = W01_ROOT / relative_path
        for function_name, semantic_fields in functions.items():
            annotation = _return_annotation(source_path, function_name)
            assert annotation.startswith("Annotated[")
            assert "kit:" in annotation
            assert semantic_fields in annotation
            assert WITNESS in annotation


def test_w01_derived_metadata_preserves_runtime_values() -> None:
    capability = build_report_capability_truth(
        route_kind="manual",
        auto_source_enabled=False,
    )
    assert capability["declared_capability"] == "llm_report_generation"
    assert capability["real_model_path"] is False

    idempotency_key = build_idempotency_key(
        canonical_url="https://Example.com/a?b=2",
        content_hash="hash",
        scope="project",
    )
    assert len(idempotency_key) == 64

    payload = build_runtime_readback_payload(
        line_key=" line ",
        status="RUNNING",
        events=[{"kind": "queued"}],
    )
    assert payload["line_key"] == "line"
    assert payload["status"] == "running"
    assert payload["events"] == [{"kind": "queued"}]


def test_w01_annotated_runtime_type_hints_are_standard_library() -> None:
    for function in (
        build_report_capability_truth,
        build_idempotency_key,
        build_runtime_readback_payload,
    ):
        return_hint = get_type_hints(function, include_extras=True)["return"]
        assert get_origin(return_hint).__module__ == "typing"
        assert get_args(return_hint)[0] is not None


def test_w01_single_source_guard_negative_witness() -> None:
    with pytest.raises(SourceLibrarySingleSourceGuardError) as raised:
        validate_single_source_guard({"single_source_guard": "invalid"})

    error = raised.value
    assert str(error) == "override_params.single_source_guard must be an object."
    assert error.details["reason_code"] == "single_source_guard_invalid_shape"
    assert error.details["actual"] == {"single_source_guard": "str"}


def test_w01_source_export_failures() -> None:
    """Exercise every source-library boundary lift witness without changing ABI."""
    from app.services.source_library import (
        external_project,
        external_project_registration,
        external_project_registry,
        loader,
        resolver,
        runner,
        single_source_guard,
    )
    from app.services.source_library.orchestrators import single_channel

    incomplete = Failure(family="wrong.family", code="invalid", message="invalid")
    defect_cases = (
        lambda: external_project._raise_manifest_failure(incomplete),
        lambda: external_project_registration._raise_registration_failure(incomplete),
        lambda: external_project_registry._raise_provider_failure(incomplete),
        lambda: loader._raise_loader_failure(incomplete),
        lambda: resolver._raise_resolver_failure(incomplete),
        lambda: resolver._raise_parallel_failure(incomplete, cause=ValueError("invalid")),
        lambda: runner._raise_runner_failure(incomplete),
        lambda: single_source_guard._raise_guard_failure(incomplete, details={}),
        lambda: single_channel._raise_orchestrator_failure(incomplete),
    )
    for lift in defect_cases:
        with pytest.raises(TypeError):
            lift()

    with pytest.raises(ValueError, match="manifest"):
        external_project._raise_manifest_failure(
            external_project._manifest_failure("external_project_manifest_invalid", "manifest", site="test")
        )
    with pytest.raises(ValueError, match="registration"):
        external_project_registration._raise_registration_failure(
            external_project_registration._registration_failure("external_project_manifest_invalid", "registration", site="test")
        )
    with pytest.raises(ValueError, match="provider"):
        external_project_registry._raise_provider_failure(
            external_project_registry._provider_failure("external_project_manifest_invalid", "provider", site="test")
        )
    with pytest.raises(RuntimeError, match="loader"):
        loader._raise_loader_failure(loader._loader_failure("yaml_parser_unavailable", "loader", site="test"))
    with pytest.raises(ValueError, match="resolver"):
        resolver._raise_resolver_failure(resolver._resolver_failure("external_project_manifest_invalid", "resolver", site="test"))
    parallel_cause = ValueError("parallel")
    with pytest.raises(ValueError, match="parallel"):
        resolver._raise_parallel_failure(
            resolver._parallel_failure(
                "parallel_item_failed", "parallel", site="test", public_exception="ValueError"
            ),
            cause=parallel_cause,
        )
    with pytest.raises(ValueError, match="runner"):
        runner._raise_runner_failure(runner._runner_failure("external_project_manifest_invalid", "runner", site="test"))
    guard_failure = single_source_guard._guard_failure("single_source_guard_blocked", "guard", details={})
    with pytest.raises(single_source_guard.SourceLibrarySingleSourceGuardError, match="guard"):
        single_source_guard._raise_guard_failure(guard_failure, details={})
    with pytest.raises(ValueError, match="orchestrator"):
        single_channel._raise_orchestrator_failure(
            single_channel._orchestrator_failure("external_project_manifest_invalid", "orchestrator", site="test")
        )
