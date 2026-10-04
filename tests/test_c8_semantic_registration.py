from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from app.successor_runtime.capabilities.knowledge_graph_projection_contribution import KNOWLEDGE_GRAPH_PROJECTION_KIND
from app.successor_runtime.capabilities.knowledge_program import (
    KNOWLEDGE_ADMISSION_KIND,
    KNOWLEDGE_DELIVERY_INTENT_PREPARE_KIND,
    KNOWLEDGE_VERIFY_KIND,
    DELIVERY_INTERNAL_EXPORT_KIND,
    build_knowledge_bundle,
)
from app.successor_runtime.capabilities.knowledge_report_contribution import KNOWLEDGE_REPORT_KIND
from app.successor_runtime.capabilities.typed_knowledge_contribution import KNOWLEDGE_READ_KIND
from app.successor_runtime.capabilities.knowledge_writing_contribution import (
    KNOWLEDGE_WRITING_COMPOSE_KIND,
    KNOWLEDGE_WRITING_STAGE_KIND,
)
from app.successor_runtime.language.profiles import (
    FailureProfile,
    build_profile,
    content_digest,
)
from mrw_functorial_kit.core.knowledge_semantics import knowledge_graph_failures, knowledge_operation_kinds, knowledge_report_delivery_failures, knowledge_typed_knowledge_failures, knowledge_writing_failures, knowledge_report_export_contract_failures, knowledge_report_export_token_failures, knowledge_report_export_token_state_failures, read_legacy_c8_failure_codes, read_legacy_c8_operation_kind_members


ROOT = Path(__file__).resolve().parents[1]


def _assert_failure_families_match_cells(
    profiles: dict[str, dict[str, object]],
) -> None:
    expected = {
        "knowledge.read.v2": knowledge_typed_knowledge_failures.codes,
        "knowledge.writing.v2": knowledge_writing_failures.codes,
        "knowledge.report.v2": knowledge_report_delivery_failures.codes,
        "knowledge.graph-projection.v2": knowledge_graph_failures.codes,
    }
    for cell, codes in expected.items():
        profile = profiles[cell]["failure"]
        assert isinstance(profile, FailureProfile), cell
        assert profile.typed_failures == codes, cell
        assert len(set(profile.typed_failures)) == len(profile.typed_failures), cell


def test_INVARIANT__c8_operation_kinds_match_static_runtime_constants() -> None:
    constants = (
        KNOWLEDGE_READ_KIND,
        KNOWLEDGE_WRITING_COMPOSE_KIND,
        KNOWLEDGE_WRITING_STAGE_KIND,
        KNOWLEDGE_REPORT_KIND,
        KNOWLEDGE_GRAPH_PROJECTION_KIND,
        KNOWLEDGE_VERIFY_KIND,
        KNOWLEDGE_ADMISSION_KIND,
        KNOWLEDGE_DELIVERY_INTENT_PREPARE_KIND,
        DELIVERY_INTERNAL_EXPORT_KIND,
    )
    assert len(constants) == len(set(constants)) == 9
    assert len(knowledge_operation_kinds.members) == len(set(knowledge_operation_kinds.members)) == 9
    assert set(knowledge_operation_kinds.members) == set(constants)


def test_INVARIANT__c8_failure_families_match_runtime_profiles() -> None:
    _assert_failure_families_match_cells(build_knowledge_bundle().profiles)


def test_INVARIANT__c8_failure_family_runtime_drift_is_rejected() -> None:
    bundle = build_knowledge_bundle()
    original = bundle.profiles["knowledge.writing.v2"]["failure"]
    assert isinstance(original, FailureProfile)
    values = asdict(original)
    values.pop("profile_digest")
    values["typed_failures"] = original.typed_failures[:-1]
    with pytest.raises(ValueError):
        FailureProfile(**values, profile_digest=original.profile_digest)
    drifted = dict(bundle.profiles)
    drifted["knowledge.writing.v2"] = dict(
        bundle.profiles["knowledge.writing.v2"],
        failure=build_profile(
            FailureProfile, **values, profile_digest=content_digest(values)
        ),
    )
    with pytest.raises(AssertionError):
        _assert_failure_families_match_cells(drifted)


def test_INVARIANT__c8_registry_entries_match_kit_declarations() -> None:
    vocabularies = json.loads((ROOT / "registries/vocabularies.json").read_text())[
        "entries"
    ]
    vocabulary_members = {entry["name"]: tuple(entry["members"]) for entry in vocabularies}
    assert vocabulary_members["knowledge.operation.kind"] == knowledge_operation_kinds.members

    failures = json.loads((ROOT / "registries/failures.json").read_text())["entries"]
    failure_codes = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    expected = {
        "knowledge.read.failure": knowledge_typed_knowledge_failures,
        "knowledge.writing.failure": knowledge_writing_failures,
        "knowledge.graph.failure": knowledge_graph_failures,
        "knowledge.report-delivery.failure": knowledge_report_delivery_failures,
        "knowledge.report.export-contract.failure": (
            knowledge_report_export_contract_failures
        ),
        "knowledge.report.export-token.failure": (
            knowledge_report_export_token_failures
        ),
        "knowledge.report.export-token-state.failure": (
            knowledge_report_export_token_state_failures
        ),
    }
    for name, family in expected.items():
        assert failure_codes[name] == family.codes


def test_INVARIANT__legacy_c8_metadata_is_raw_read_only() -> None:
    assert read_legacy_c8_operation_kind_members()[0] == (
        "c8.typed_knowledge.demand_read.v1"
    )
    assert read_legacy_c8_failure_codes("c8.typed_knowledge.failure") == (
        "DEMAND_READ_UNAVAILABLE",
        "DEMAND_READ_AMBIGUOUS",
        "CANONICAL_REF_VALIDATION_FAILED",
    )
    assert read_legacy_c8_failure_codes("c8.report_export_token.failure") == (
        "export_token_actor_mismatch",
        "export_token_already_used",
        "export_token_expired",
        "export_token_markdown_hash_mismatch",
        "export_token_missing_expiry",
        "export_token_revoked",
        "invalid_export_token_format",
        "invalid_export_token_payload",
        "invalid_export_token_signature",
        "unsupported_export_token_contract",
    )
    assert read_legacy_c8_failure_codes("unknown") is None


def test_INVARIANT__c8_sketches_have_existing_test_witnesses() -> None:
    sketches = json.loads((ROOT / "sketches.json").read_text())["entries"]
    c8_entries = [
        entry
        for entry in sketches
        if any("/c8_" in obj.get("owner", "") for obj in entry["objects"])
    ]
    assert len(c8_entries) == 2

    witness_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "main/backend/tests/successor_runtime").glob("test_*c8*.py")
    )
    for entry in c8_entries:
        assert entry["failures"]
        for equation in entry["equations"]:
            assert equation["class"] == "testable"
            witness = equation["witness"].removeprefix("test:")
            assert f"def {witness}(" in witness_sources, witness
