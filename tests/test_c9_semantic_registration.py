from __future__ import annotations

import json
import re
from pathlib import Path

from mrw_functorial_kit.core.projection_semantics import projection_projection_loss_kinds, projection_projection_source_schemas, projection_projector_outcomes, projection_runtime_event_kinds, projection_search_segment_kinds, projection_session_statuses, projection_processing_failures

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "main/backend/app/successor_runtime/substrate/projections/projection_sources.py"
EFFECT_SOURCES = (
    ROOT / "main/backend/app/successor_runtime/substrate/postgres/projection_sources.py",
    ROOT / "main/backend/app/successor_runtime/substrate/projections/registry.py",
    ROOT / "main/backend/scripts/c9_projection_rebuild.py",
)


def test_INVARIANT__c9_runtime_vocabularies_match_pure_source() -> None:
    source = SOURCES.read_text(encoding="utf-8")

    def constant(name: str) -> str:
        match = re.search(rf'^{name} = "([^"]+)"', source, re.MULTILINE)
        assert match is not None
        return match.group(1)

    events = (
        constant("TASK_CREATED"),
        constant("TASK_ASSIGNED"),
        constant("TASK_PROJECTION_REFRESHED"),
        constant("TASK_TERMINAL_SUCCEEDED"),
        constant("TASK_TERMINAL_FAILED"),
    )
    session_statuses = (
        constant("TASK_STATUS_WAITING"),
        constant("TASK_STATUS_RUNNING"),
        constant("TASK_STATUS_TERMINAL_SUCCEEDED"),
        constant("TASK_STATUS_TERMINAL_FAILED"),
    )
    segments = (
        constant("MATERIAL_SEGMENT_KIND_TEXT"),
        constant("MATERIAL_SEGMENT_KIND_FIELD"),
    )
    losses = (
        constant("LOSS_KIND_DECLARED"),
        constant("LOSS_KIND_OMITTED_FIELD"),
        constant("LOSS_KIND_NOT_EXECUTED"),
    )
    source_schemas = (
        constant("TASK_SOURCE_SCHEMA"),
        constant("KNOWLEDGE_SOURCE_SCHEMA"),
        constant("MATERIAL_SOURCE_SCHEMA"),
    )
    legacy_source_schemas = (
        constant("LEGACY_TASK_SOURCE_SCHEMA"),
        constant("LEGACY_KNOWLEDGE_SOURCE_SCHEMA"),
        constant("LEGACY_MATERIAL_SOURCE_SCHEMA"),
    )

    assert projection_runtime_event_kinds.members == events
    assert projection_session_statuses.members == session_statuses
    assert projection_search_segment_kinds.members == segments
    assert projection_projection_loss_kinds.members == losses
    assert projection_projection_source_schemas.members == source_schemas
    assert set(projection_projection_source_schemas.members).isdisjoint(legacy_source_schemas)


def test_INVARIANT__c9_projector_projection_matches_canonical_registration() -> None:
    assert projection_projector_outcomes.members == (
        "PROJECTION_APPLIED",
        "PROJECTION_REBUILT",
        "PROJECTION_NO_CHANGE",
    )
    assert projection_processing_failures.codes == (
        "SOURCE_UNAVAILABLE",
        "SOURCE_DRIFT",
        "SOURCE_INCARNATION_STALE",
        "OFFSET_STALE",
        "PROJECTION_OFFSET_CLOSURE_DRIFT",
        "EXTERNAL_INDEX_EFFECT_FAILED",
        "REBUILD_FAILED",
    )
    assert projection_processing_failures.matches(
        projection_processing_failures.fail(
            "REBUILD_FAILED", "registered test failure"
        )
    )


def test_INVARIANT__c9_failure_projection_has_static_runtime_evidence() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in EFFECT_SOURCES)
    evidence = {
        "SOURCE_UNAVAILABLE": "ProjectionSourceUnavailableError",
        "SOURCE_DRIFT": "ProjectionSourceClosureDriftError",
        "SOURCE_INCARNATION_STALE": "ProjectionSourceStaleClosureError",
        "OFFSET_STALE": "SOURCE_STALE",
        "PROJECTION_OFFSET_CLOSURE_DRIFT": "projection offset generation CAS failed",
        "EXTERNAL_INDEX_EFFECT_FAILED": "EXTERNAL_DECLARED_LOSS_SINKS",
        "REBUILD_FAILED": "outcome=\"FAILED\"",
    }
    for code, marker in evidence.items():
        assert code in projection_processing_failures.codes
        assert marker in source, marker


def test_INVARIANT__c9_registry_entries_match_kit_declarations() -> None:
    vocabularies = json.loads((ROOT / "registries/vocabularies.json").read_text())[
        "entries"
    ]
    registry_members = {entry["name"]: tuple(entry["members"]) for entry in vocabularies}
    expected_vocabularies = {
        "projection.outcome": projection_projector_outcomes,
        "projection.task.event.kind": projection_runtime_event_kinds,
        "projection.task.status": projection_session_statuses,
        "projection.material.segment.kind": projection_search_segment_kinds,
        "projection.loss.kind": projection_projection_loss_kinds,
        "projection.source.schema": projection_projection_source_schemas,
    }
    for name, vocabulary in expected_vocabularies.items():
        assert vocabulary.name == name
        assert registry_members[name] == vocabulary.members

    failures = json.loads((ROOT / "registries/failures.json").read_text())["entries"]
    failure_codes = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    assert failure_codes["projection.processing.failure"] == (
        projection_processing_failures.codes
    )


def test_INVARIANT__c9_sketches_have_existing_test_witnesses() -> None:
    from mrw_functorial_kit.contributions import projection as contribution

    sketches = json.loads((ROOT / "sketches.json").read_text())["entries"]
    expected_objects = [
        list(sketch.entry["objects"])
        for sketch in contribution.projection_native_catalog[0].projection.sketches
    ]
    c9_entries = [
        entry
        for entry in sketches
        if entry.get("objects") in expected_objects
    ]
    assert len(c9_entries) == 2
    assert c9_entries == [
        dict(sketch.entry)
        for sketch in contribution.projection_native_catalog[0].projection.sketches
    ]

    witness_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "main/backend/tests/successor_runtime").glob("test_*c9*.py")
    )
    for entry in c9_entries:
        assert entry["failures"] == ["projection.processing.failure"]
        for equation in entry["equations"]:
            assert equation["class"] == "testable"
            witness = equation["witness"].removeprefix("test:")
            assert f"def {witness}(" in witness_sources, witness
