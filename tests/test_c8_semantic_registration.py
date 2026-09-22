from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from app.successor_runtime.capabilities.c8_graph_projection_contribution import C8_4_KIND
from app.successor_runtime.capabilities.c8_program import (
    C8_ADMISSION_KIND,
    C8_DELIVERY_INTENT_PREPARE_KIND,
    C8_VERIFY_KIND,
    DELIVERY_INTERNAL_EXPORT_KIND,
    build_c8_bundle,
)
from app.successor_runtime.capabilities.c8_report_contribution import C8_3_KIND
from app.successor_runtime.capabilities.c8_typed_knowledge_contribution import C8_1_KIND
from app.successor_runtime.capabilities.c8_writing_contribution import (
    C8_2_COMPOSE_KIND,
    C8_2_STAGE_KIND,
)
from app.successor_runtime.language.profiles import (
    FailureProfile,
    build_profile,
    content_digest,
)
from mrw_functorial_kit.core.c8_semantics import (
    c8_graph_failures,
    c8_operation_kinds,
    c8_report_delivery_failures,
    c8_typed_knowledge_failures,
    c8_writing_failures,
)


ROOT = Path(__file__).resolve().parents[1]


def _assert_failure_families_match_cells(
    profiles: dict[str, dict[str, object]],
) -> None:
    expected = {
        "C8.1": c8_typed_knowledge_failures.codes,
        "C8.2": c8_writing_failures.codes,
        "C8.3": c8_report_delivery_failures.codes,
        "C8.4": c8_graph_failures.codes,
    }
    for cell, codes in expected.items():
        profile = profiles[cell]["failure"]
        assert isinstance(profile, FailureProfile), cell
        assert profile.typed_failures == codes, cell
        assert len(set(profile.typed_failures)) == len(profile.typed_failures), cell


def test_INVARIANT__c8_operation_kinds_match_static_runtime_constants() -> None:
    constants = (
        C8_1_KIND,
        C8_2_COMPOSE_KIND,
        C8_2_STAGE_KIND,
        C8_3_KIND,
        C8_4_KIND,
        C8_VERIFY_KIND,
        C8_ADMISSION_KIND,
        C8_DELIVERY_INTENT_PREPARE_KIND,
        DELIVERY_INTERNAL_EXPORT_KIND,
    )
    assert len(constants) == len(set(constants)) == 9
    assert len(c8_operation_kinds.members) == len(set(c8_operation_kinds.members)) == 9
    assert set(c8_operation_kinds.members) == set(constants)


def test_INVARIANT__c8_failure_families_match_runtime_profiles() -> None:
    _assert_failure_families_match_cells(build_c8_bundle().profiles)


def test_INVARIANT__c8_failure_family_runtime_drift_is_rejected() -> None:
    bundle = build_c8_bundle()
    original = bundle.profiles["C8.2"]["failure"]
    assert isinstance(original, FailureProfile)
    values = asdict(original)
    values.pop("profile_digest")
    values["typed_failures"] = original.typed_failures[:-1]
    with pytest.raises(ValueError):
        FailureProfile(**values, profile_digest=original.profile_digest)
    drifted = dict(bundle.profiles)
    drifted["C8.2"] = dict(
        bundle.profiles["C8.2"],
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
    assert vocabulary_members["c8.operation.kind"] == c8_operation_kinds.members

    failures = json.loads((ROOT / "registries/failures.json").read_text())["entries"]
    failure_codes = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    expected = {
        "c8.typed_knowledge.failure": c8_typed_knowledge_failures,
        "c8.writing.failure": c8_writing_failures,
        "c8.graph.failure": c8_graph_failures,
        "c8.report_delivery.failure": c8_report_delivery_failures,
    }
    for name, family in expected.items():
        assert failure_codes[name] == family.codes


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
