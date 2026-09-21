"""Focused authority and unresolved-raise inventory for packet W05."""

from __future__ import annotations

import ast
import inspect
import typing
from pathlib import Path

from functorial_kit.arch.gates import scan_project

from app.successor_runtime.capabilities.agent_batch_c4 import (
    build_agent_batch_c4_bundle,
    build_agent_batch_c4_catalog,
    build_agent_batch_c4_registry,
    build_agent_batch_submission_digest,
    build_batch_plan,
    build_search_brief,
)
from app.successor_runtime.capabilities.agent_batch_c4_program import (
    build_agent_batch_c4_1_program,
    build_agent_batch_c4_1_traversal_program,
    build_agent_batch_c4_2_program,
    build_agent_batch_c4_3_program,
)
from app.successor_runtime.capabilities.agent_core_c6_1 import (
    build_agent_core_c6_1_bundle,
    build_agent_core_c6_1_catalog,
    build_agent_core_c6_1_registry,
)
from app.successor_runtime.capabilities.agent_core_c6_1_program import (
    build_agent_core_c6_1_program,
)
from app.successor_runtime.capabilities.agent_core_c6_2 import (
    build_agent_core_c6_2_bundle,
    build_agent_core_c6_2_catalog,
    build_agent_core_c6_2_registry,
    build_c6_2_receipt_only_evidence,
)
from app.successor_runtime.capabilities.agent_core_c6_2_live_model_port import (
    build_openai_live_provider_port,
)
from app.successor_runtime.capabilities.agent_core_c6_2_program import (
    build_agent_core_c6_2_program,
)
from app.successor_runtime.capabilities.agent_core_c6_3 import (
    build_agent_core_c6_3_bundle,
    build_agent_core_c6_3_catalog,
    build_agent_core_c6_3_registry,
)
from app.successor_runtime.capabilities.agent_core_c6_3_program import (
    build_agent_core_c6_3_program,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    build_p3_c6_fragment,
    build_payload_codec,
)
from app.successor_runtime.capabilities.collect_c3 import (
    build_collect_batch_plan,
    build_collect_c3_bundle,
    build_collect_c3_catalog,
    build_collect_c3_registry,
    build_collect_fold_payload,
    build_collect_request_ref,
)
from app.successor_runtime.capabilities.collect_c3_program import (
    build_collect_c3_1_program,
    build_collect_c3_2_program,
    build_collect_c3_2_pure_fold_program,
    build_collect_c3_composed_program,
    build_collect_c3_program,
    build_collect_c3_transform_registry,
    build_declared_traversal_program,
    build_family_payload_value_ref,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
W05_ROOT = REPO_ROOT / "main" / "backend" / "app" / "successor_runtime" / "capabilities"

_VIEWS: dict[object, tuple[str, str, str]] = {
    build_agent_batch_c4_bundle: (
        "view",
        "AGENT_BATCH_C4_OWNER+capability_contract_constants",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_agent_batch_c4_catalog: (
        "view",
        "AgentBatchC4CapabilityBundle.operations",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_agent_batch_c4_registry: (
        "view",
        "AgentBatchC4CapabilityBundle+catalog_snapshot",
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
    build_agent_core_c6_1_bundle: (
        "view",
        "AGENT_CORE_C6_1_OWNER+capability_contract_constants",
        "test_w05_agent_core_authority_metadata",
    ),
    build_agent_core_c6_1_catalog: (
        "view",
        "AgentCoreC6_1CapabilityBundle.operations",
        "test_w05_agent_core_authority_metadata",
    ),
    build_agent_core_c6_1_registry: (
        "view",
        "AgentCoreC6_1CapabilityBundle+catalog_snapshot",
        "test_w05_agent_core_authority_metadata",
    ),
    build_agent_core_c6_2_bundle: (
        "view",
        "AGENT_CORE_C6_2_OWNER+capability_contract_constants",
        "test_w05_agent_core_authority_metadata",
    ),
    build_agent_core_c6_2_catalog: (
        "view",
        "AgentCoreC6_2CapabilityBundle.operations",
        "test_w05_agent_core_authority_metadata",
    ),
    build_agent_core_c6_2_registry: (
        "view",
        "AgentCoreC6_2CapabilityBundle+catalog_snapshot",
        "test_w05_agent_core_authority_metadata",
    ),
    build_agent_core_c6_3_bundle: (
        "view",
        "AGENT_CORE_C6_3_OWNER+capability_contract_constants",
        "test_w05_agent_core_authority_metadata",
    ),
    build_agent_core_c6_3_catalog: (
        "view",
        "AgentCoreC6_3CapabilityBundle.operations",
        "test_w05_agent_core_authority_metadata",
    ),
    build_agent_core_c6_3_registry: (
        "view",
        "AgentCoreC6_3CapabilityBundle+catalog_snapshot",
        "test_w05_agent_core_authority_metadata",
    ),
    build_collect_batch_plan: (
        "view",
        "CollectBatchPlanPayload+ordered_element_policy",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_c3_bundle: (
        "view",
        "COLLECT_C3_OWNER+capability_contract_constants",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_c3_catalog: (
        "view",
        "CollectC3CapabilityBundle.operations",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_c3_registry: (
        "view",
        "CollectC3CapabilityBundle+catalog_snapshot",
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
    build_c6_2_receipt_only_evidence: (
        "generated_evidence",
        "ReceiptOnlyProviderPort+receipt_fields",
        "test_w05_agent_core_authority_metadata",
    ),
    build_p3_c6_fragment: (
        "generated_evidence",
        "ordered_files+ordered_cells+independent_review",
        "test_w05_agent_core_authority_metadata",
    ),
}

_PREPARED: dict[object, tuple[str, str]] = {
    build_agent_batch_c4_1_program: (
        "successor_program_interpreter",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_agent_batch_c4_1_traversal_program: (
        "successor_program_interpreter",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_agent_batch_c4_2_program: (
        "successor_program_interpreter",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_agent_batch_c4_3_program: (
        "successor_program_interpreter",
        "test_w05_agent_batch_authority_metadata",
    ),
    build_agent_core_c6_1_program: (
        "successor_program_interpreter",
        "test_w05_agent_core_authority_metadata",
    ),
    build_agent_core_c6_2_program: (
        "successor_program_interpreter",
        "test_w05_agent_core_authority_metadata",
    ),
    build_agent_core_c6_3_program: (
        "successor_program_interpreter",
        "test_w05_agent_core_authority_metadata",
    ),
    build_collect_c3_1_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_c3_2_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_c3_2_pure_fold_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_c3_composed_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_c3_program: (
        "successor_program_interpreter",
        "test_w05_collect_authority_metadata",
    ),
    build_collect_c3_transform_registry: (
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
    build_openai_live_provider_port: (
        "openai_live_provider_transport",
        "test_w05_agent_core_authority_metadata",
    ),
    build_payload_codec: (
        "typed_payload_encode_decode",
        "test_w05_agent_core_authority_metadata",
    ),
}

_W05_OWNED_CAPABILITY_FILES = {
    "agent_batch_c4.py",
    "agent_batch_c4_interpreters.py",
    "agent_batch_c4_program.py",
    "agent_core_c6_1.py",
    "agent_core_c6_1_interpreters.py",
    "agent_core_c6_1_program.py",
    "agent_core_c6_2.py",
    "agent_core_c6_2_interpreters.py",
    "agent_core_c6_2_live_model_port.py",
    "agent_core_c6_2_program.py",
    "agent_core_c6_3.py",
    "agent_core_c6_3_interpreters.py",
    "agent_core_c6_3_program.py",
    "agent_core_c6_common.py",
    "collect_c3.py",
    "collect_c3_interpreters.py",
    "collect_c3_program.py",
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
        build_agent_batch_c4_bundle,
        build_agent_batch_c4_catalog,
        build_agent_batch_c4_registry,
        build_agent_batch_submission_digest,
        build_batch_plan,
        build_search_brief,
    }
    for function in (
        build_agent_batch_c4_1_program,
        build_agent_batch_c4_1_traversal_program,
        build_agent_batch_c4_2_program,
        build_agent_batch_c4_3_program,
    ):
        marker, fields = _authority(function)
        assert marker == "kit:prepared-command"
        assert fields == {
            "effect_boundary": "successor_program_interpreter",
            "witness": "test:test_w05_agent_batch_authority_metadata",
        }


def test_w05_agent_core_authority_metadata() -> None:
    assert {
        function
        for function, value in _VIEWS.items()
        if value[2].startswith("test_w05_agent_core")
    } == {
        build_agent_core_c6_1_bundle,
        build_agent_core_c6_1_catalog,
        build_agent_core_c6_1_registry,
        build_agent_core_c6_2_bundle,
        build_agent_core_c6_2_catalog,
        build_agent_core_c6_2_registry,
        build_agent_core_c6_3_bundle,
        build_agent_core_c6_3_catalog,
        build_agent_core_c6_3_registry,
        build_c6_2_receipt_only_evidence,
        build_p3_c6_fragment,
    }
    assert {
        function
        for function, value in _PREPARED.items()
        if value[1].startswith("test_w05_agent_core")
    } == {
        build_agent_core_c6_1_program,
        build_agent_core_c6_2_program,
        build_agent_core_c6_3_program,
        build_openai_live_provider_port,
        build_payload_codec,
    }
    for function in (
        build_agent_core_c6_1_program,
        build_agent_core_c6_2_program,
        build_agent_core_c6_3_program,
    ):
        marker, fields = _authority(function)
        assert marker == "kit:prepared-command"
        assert fields["effect_boundary"] == "successor_program_interpreter"


def test_w05_collect_authority_metadata() -> None:
    assert {
        function for function, value in _VIEWS.items() if value[2].startswith("test_w05_collect")
    } == {
        build_collect_batch_plan,
        build_collect_c3_bundle,
        build_collect_c3_catalog,
        build_collect_c3_registry,
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
    assert len(all_functions) == 40
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
