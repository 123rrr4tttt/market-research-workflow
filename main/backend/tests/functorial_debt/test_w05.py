"""Focused authority and unresolved-raise inventory for packet W05."""

from __future__ import annotations

import inspect
import typing
from pathlib import Path

from functorial_kit.arch.gates import scan_project

from app.successor_runtime.capabilities.batch_task import build_batch_task_bundle, build_batch_task_catalog, build_batch_task_registry, build_agent_batch_submission_digest, build_batch_plan, build_search_brief
from app.successor_runtime.capabilities.batch_task_program import (
    build_batch_task_plan_program,
    build_batch_task_plan_traversal_program,
    build_batch_task_retry_program,
    build_batch_task_submission_program,
)
from app.successor_runtime.capabilities.acquisition_batch import (
    build_collect_batch_plan,
    build_acquisition_batch_bundle,
    build_acquisition_batch_catalog,
    build_acquisition_batch_registry,
    build_collect_fold_payload,
    build_collect_request_ref,
)
from app.successor_runtime.capabilities.acquisition_batch_program import (
    build_collect_batch_element_program,
    build_collect_fold_ordered_results_program,
    build_collect_fold_ordered_results_pure_program,
    build_acquisition_batch_composed_program,
    build_collect_program,
    build_acquisition_batch_transform_registry,
    build_declared_traversal_program,
    build_family_payload_value_ref,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
_VIEWS: dict[object, tuple[str, str, str]] = {
    build_batch_task_bundle: (
        "view",
        "BATCH_TASK_OWNER+capability_contract_constants",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_batch_task_catalog: (
        "view",
        "BatchTaskCapabilityBundle.operations",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_batch_task_registry: (
        "view",
        "BatchTaskCapabilityBundle+catalog_snapshot",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_agent_batch_submission_digest: (
        "view",
        "AgentBatchSubmission+canonical_json",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_batch_plan: (
        "view",
        "BatchPlanPayload+ordered_task_policy",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_search_brief: (
        "view",
        "normalized_batch_tasks+candidate_keys",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_collect_batch_plan: (
        "view",
        "CollectBatchPlanPayload+ordered_element_policy",
        "test_w05_collect_authority_metadata",
    ),
    build_acquisition_batch_bundle: (
        "view",
        "COLLECT_C3_OWNER+capability_contract_constants",
        "test_w05_collect_authority_metadata",
    ),
    build_acquisition_batch_catalog: (
        "view",
        "AcquisitionBatchCapabilityBundle.operations",
        "test_w05_collect_authority_metadata",
    ),
    build_acquisition_batch_registry: (
        "view",
        "AcquisitionBatchCapabilityBundle+catalog_snapshot",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_fold_payload: (
        "view",
        "ordered_outcomes+aggregation_policy_ref",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_request_ref: (
        "view",
        "normalized_collect_request_inputs",
        "test_w05_collect_authority_metadata",
    ),
}

_PREPARED: dict[object, tuple[str, str]] = {
    build_batch_task_plan_program: (
        "successor_program_interpreter",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_batch_task_plan_traversal_program: (
        "successor_program_interpreter",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_batch_task_retry_program: (
        "successor_program_interpreter",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_batch_task_submission_program: (
        "successor_program_interpreter",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_collect_batch_element_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_fold_ordered_results_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_fold_ordered_results_pure_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_acquisition_batch_composed_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_acquisition_batch_transform_registry: (
        "pure_transform_registry",
        "test_w05_collect_authority_metadata",
    ),
    build_declared_traversal_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_family_payload_value_ref: (
        "successor_values_storage",
        "test_w05_collect_authority_metadata",
    ),
}

_W05_OWNED_CAPABILITY_FILES = {
    "batch_task.py",
    "batch_task_interpreters.py",
    "batch_task_program.py",
    "acquisition_batch.py",
    "acquisition_batch_interpreters.py",
    "acquisition_batch_program.py",
}


def _authority(function: object) -> tuple[str, dict[str, str]]:
    hint = typing.get_type_hints(function, include_extras=True)["return"]
    assert typing.get_origin(hint) is typing.Annotated
    metadata = typing.get_args(hint)[1]
    assert isinstance(metadata, str)
    fields = dict(
        token.split("=", 1) for token in metadata.split()[1:] if "=" in token
    )
    assert fields["witness"].startswith("test:")
    return metadata.split()[0], fields


def test_w05_agent_batch_authority_metadata() -> None:
    assert {
        function for function, value in _VIEWS.items() if value[2].startswith("test_w05_agent_batch")
    } == {
        build_batch_task_bundle,
        build_batch_task_catalog,
        build_batch_task_registry,
        build_agent_batch_submission_digest,
        build_batch_plan,
        build_search_brief,
    }
    for function in (
        build_batch_task_plan_program,
        build_batch_task_plan_traversal_program,
        build_batch_task_retry_program,
        build_batch_task_submission_program,
    ):
        marker, fields = _authority(function)
        assert marker == "kit:prepared-command"
        assert fields == {
            "effect_boundary": "successor_program_interpreter",
            "witness": "test:test_w05_agent_batch_authority_metadata",
        }


def test_w05_collect_authority_metadata() -> None:
    assert {
        function for function, value in _VIEWS.items() if value[2].startswith("test_w05_collect")
    } == {
        build_collect_batch_plan,
        build_acquisition_batch_bundle,
        build_acquisition_batch_catalog,
        build_acquisition_batch_registry,
        build_collect_fold_payload,
        build_collect_request_ref,
    }
    for function, (effect_boundary, witness) in _PREPARED.items():
        if witness.startswith("test_w05_collect"):
            marker, fields = _authority(function)
            assert marker == "kit:prepared-command"
            assert fields["effect_boundary"] == effect_boundary


def test_w05_metadata_exact_and_runtime_types_preserved() -> None:
    all_functions = {*_VIEWS, *_PREPARED}
    assert len(all_functions) == 24
    for function in all_functions:
        marker, fields = _authority(function)
        if function in _VIEWS:
            derived_as, fact_source, witness = _VIEWS[function]
            assert marker == "kit:non-authoritative"
            assert fields == {
                "derived_as": derived_as,
                "fact_source": fact_source,
                "witness": f"test:{witness}",
            }
            assert fields["witness"].removeprefix("test:") in inspect.getsource(
                __import__(__name__, fromlist=[""])
            )
        else:
            assert marker == "kit:prepared-command"
            assert set(fields) == {"effect_boundary", "witness"}


def test_w05_live_scan_has_no_throw_failures() -> None:
    scan = scan_project(REPO_ROOT)
    w05_live_no_throw = [
        violation
        for violation in scan.violations
        if violation.severity == "fail"
        and violation.gate == "no-throw-in-core"
        and violation.file.startswith("main/backend/app/successor_runtime/capabilities/")
        and Path(violation.file).name in _W05_OWNED_CAPABILITY_FILES
    ]
    owned_new = [
        violation
        for violation in w05_live_no_throw
        if Path(violation.file).name in _W05_OWNED_CAPABILITY_FILES
    ]
    assert len(w05_live_no_throw) == 0
    assert len(owned_new) == 0
