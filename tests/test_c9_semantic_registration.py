from __future__ import annotations

import json
import re
from pathlib import Path

from mrw_functorial_kit.core.c9_semantics import (
    c9_projection_loss_kinds,
    c9_projection_source_schemas,
    c9_projector_failures,
    c9_projector_outcomes,
    c9_runtime_event_kinds,
    c9_search_segment_kinds,
    c9_session_statuses,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "main/backend/app/successor_runtime/substrate/projections/c9_sources.py"
EFFECT_SOURCES = (
    ROOT / "main/backend/app/successor_runtime/substrate/postgres/c9_projection_sources.py",
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
        constant("SESSION_CREATED"),
        constant("SESSION_TASK_ASSIGNED"),
        constant("SESSION_PROJECTION_REFRESHED"),
        constant("SESSION_TERMINAL_SUCCEEDED"),
        constant("SESSION_TERMINAL_FAILED"),
    )
    session_statuses = (
        constant("SESSION_STATUS_WAITING"),
        constant("SESSION_STATUS_RUNNING"),
        constant("SESSION_STATUS_TERMINAL_SUCCEEDED"),
        constant("SESSION_STATUS_TERMINAL_FAILED"),
    )
    segments = (
        constant("C7_SEGMENT_KIND_TEXT"),
        constant("C7_SEGMENT_KIND_FIELD"),
    )
    losses = (
        constant("LOSS_KIND_DECLARED"),
        constant("LOSS_KIND_OMITTED_FIELD"),
        constant("LOSS_KIND_NOT_EXECUTED"),
    )
    source_schemas = (
        constant("RUNTIME_SESSION_SOURCE_SCHEMA"),
        constant("RESEARCH_GRAPH_SOURCE_SCHEMA"),
        constant("C7_SEARCH_SOURCE_SCHEMA"),
    )

    assert c9_runtime_event_kinds.members == events
    assert c9_session_statuses.members == session_statuses
    assert c9_search_segment_kinds.members == segments
    assert c9_projection_loss_kinds.members == losses
    assert c9_projection_source_schemas.members == source_schemas


def test_INVARIANT__c9_projector_projection_matches_canonical_registration() -> None:
    assert c9_projector_outcomes.members == (
        "PROJECTION_APPLIED",
        "PROJECTION_REBUILT",
        "PROJECTION_NO_CHANGE",
    )
    assert c9_projector_failures.codes == (
        "SOURCE_UNAVAILABLE",
        "SOURCE_DRIFT",
        "SOURCE_INCARNATION_STALE",
        "OFFSET_STALE",
        "PROJECTION_OFFSET_CLOSURE_DRIFT",
        "EXTERNAL_INDEX_EFFECT_FAILED",
        "REBUILD_FAILED",
    )
    assert c9_projector_failures.matches(
        c9_projector_failures.fail("REBUILD_FAILED", "registered test failure")
    )


def test_INVARIANT__c9_failure_projection_has_static_runtime_evidence() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in EFFECT_SOURCES)
    evidence = {
        "SOURCE_UNAVAILABLE": "C9SourceUnavailableError",
        "SOURCE_DRIFT": "C9SourceClosureDriftError",
        "SOURCE_INCARNATION_STALE": "C9SourceStaleClosureError",
        "OFFSET_STALE": "SOURCE_STALE",
        "PROJECTION_OFFSET_CLOSURE_DRIFT": "projection offset generation CAS failed",
        "EXTERNAL_INDEX_EFFECT_FAILED": "EXTERNAL_DECLARED_LOSS_SINKS",
        "REBUILD_FAILED": "outcome=\"FAILED\"",
    }
    for code, marker in evidence.items():
        assert code in c9_projector_failures.codes
        assert marker in source, marker


def test_INVARIANT__c9_registry_entries_match_kit_declarations() -> None:
    vocabularies = json.loads((ROOT / "registries/vocabularies.json").read_text())[
        "entries"
    ]
    registry_members = {entry["name"]: tuple(entry["members"]) for entry in vocabularies}
    expected_vocabularies = {
        "c9.projector.outcome": c9_projector_outcomes,
        "c9.runtime.event.kind": c9_runtime_event_kinds,
        "c9.session.status": c9_session_statuses,
        "c9.search.segment.kind": c9_search_segment_kinds,
        "c9.projection.loss.kind": c9_projection_loss_kinds,
        "c9.projection.source.schema": c9_projection_source_schemas,
    }
    for name, vocabulary in expected_vocabularies.items():
        assert registry_members[name] == vocabulary.members

    failures = json.loads((ROOT / "registries/failures.json").read_text())["entries"]
    failure_codes = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    assert failure_codes["c9.projector.failure"] == c9_projector_failures.codes


def test_INVARIANT__c9_sketches_have_existing_test_witnesses() -> None:
    sketches = json.loads((ROOT / "sketches.json").read_text())["entries"]
    c9_entries = [
        entry
        for entry in sketches
        if any("/c9_" in obj.get("owner", "") for obj in entry["objects"])
    ]
    assert len(c9_entries) == 2

    witness_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "main/backend/tests/successor_runtime").glob("test_*c9*.py")
    )
    for entry in c9_entries:
        assert entry["failures"] == ["c9.projector.failure"]
        for equation in entry["equations"]:
            assert equation["class"] == "testable"
            witness = equation["witness"].removeprefix("test:")
            assert f"def {witness}(" in witness_sources, witness
