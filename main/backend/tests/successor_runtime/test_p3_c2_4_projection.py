"""P3 C2.4 pure projection, declared loss, offset and delete/rebuild tests."""

from __future__ import annotations

from typing import Any

import pytest

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_planning import (
    CollectionCompleted,
    CollectionOutcomeUnknown,
    CollectionPartiallyCompleted,
    OrderedFailure,
    ProviderHandoff,
    SourceCollectionTerminal,
)
from app.successor_runtime.capabilities.source_provider_acquisition import (
    CapturedSourceRecordRef,
)
from app.successor_runtime.capabilities.source_terminal_projection import (
    DECLARED_LOSS_PROFILE_REF,
    SOURCE_COLLECTION_PROJECTION_SOURCE_HISTORICAL_SCHEMA,
    SOURCE_TERMINAL_PROJECTION_OWNER,
    ProjectedWithLoss,
    ProjectionRejected,
    SourceCollectionProjectionSource,
    build_source_terminal_projection_profiles,
    historical_source_collection_projection_source_from_plain,
    project_source_collection,
)
from app.successor_runtime.substrate.projections.source_library_terminal import (
    InMemorySourceLibraryTerminalProjector,
    ProjectionStaleError,
    SourceLibraryProjectionNotFound,
    rollback_read_routing,
)

SCOPE_DIGEST = content_digest({"scope": "p3-c2-4"})


def _record(index: int) -> CapturedSourceRecordRef:
    return CapturedSourceRecordRef(
        record_id=f"record:{index}",
        content_ref=f"content:{index}",
        content_digest=content_digest({"record": index}),
        source_ref="source:handler.cluster",
    )


def _terminal(
    *,
    status: str = "ok",
    records_count: int = 0,
    failures: tuple[OrderedFailure, ...] = (),
) -> SourceCollectionTerminal:
    return SourceCollectionTerminal(
        terminal_id="terminal:p3-c2-4",
        mode="site_search",
        status=status,  # type: ignore[arg-type]
        records_count=records_count,
        provider_handoff=ProviderHandoff(
            handoff_id="handoff:p3-c2-4",
            mode="site_search",
            provider="fixture",
            provider_job_id="job:p3-c2-4",
            provider_status="COMPLETED",
            receipt_digest=content_digest({"receipt": "p3-c2-4"}),
        ),
        ordered_failures=failures,
    )


def _source(
    *,
    outcome: Any,
    records: tuple[CapturedSourceRecordRef, ...] = (),
    failures: tuple[OrderedFailure, ...] = (),
    source_incarnation: str = "inc:p3-c2-4",
    revision: int = 1,
) -> SourceCollectionProjectionSource:
    return SourceCollectionProjectionSource(
        source_kind="RUNTIME_JOURNAL",
        source_ref="runtime-run:run:p3-c2-4",
        run_id="run:p3-c2-4",
        run_incarnation="run-inc:p3-c2-4",
        source_revision=revision,
        source_incarnation=source_incarnation,
        source_digest="",
        project_key="demo_proj",
        project_scope_digest=SCOPE_DIGEST,
        source_mode="site_search",
        collection_outcome=outcome,
        record_refs=records,
        ordered_failures=failures,
        provider_handoff=None,
        observed_at="2030-09-01T08:00:00Z",
    )


def _historical_source_plain() -> dict[str, Any]:
    outcome = {
        "kind": "outcome_unknown",
        "reason": "retained historical readback",
    }
    outcome["outcome_digest"] = content_digest(
        {
            "schema": "mrw.successor.source-library.c2-2.collection-outcome.v1",
            **outcome,
        }
    )
    plain: dict[str, Any] = {
        "schema_version": SOURCE_COLLECTION_PROJECTION_SOURCE_HISTORICAL_SCHEMA,
        "source_kind": "RUNTIME_JOURNAL",
        "source_ref": "runtime-run:run:p3-c2-4-history",
        "run_id": "run:p3-c2-4-history",
        "run_incarnation": "run-inc:p3-c2-4-history",
        "source_revision": 7,
        "source_incarnation": "inc:p3-c2-4-history",
        "project_key": "demo_proj",
        "project_scope_digest": SCOPE_DIGEST,
        "source_mode": "site_search",
        "collection_outcome": outcome,
        "record_refs": [],
        "ordered_failures": [],
        "provider_handoff": None,
        "observed_at": "2030-08-31T08:00:00Z",
    }
    plain["source_digest"] = content_digest(
        {
            "schema": SOURCE_COLLECTION_PROJECTION_SOURCE_HISTORICAL_SCHEMA,
            "source_ref": plain["source_ref"],
            "run_id": plain["run_id"],
            "run_incarnation": plain["run_incarnation"],
            "source_revision": plain["source_revision"],
            "source_incarnation": plain["source_incarnation"],
            "project_key": plain["project_key"],
            "project_scope_digest": plain["project_scope_digest"],
            "source_mode": plain["source_mode"],
            "collection_outcome_digest": outcome["outcome_digest"],
            "record_refs": [],
            "ordered_failures": [],
            "provider_handoff": None,
            "observed_at": plain["observed_at"],
        }
    )
    return plain


def test_profiles_declare_projection_loss_and_zero_authority() -> None:
    profiles = build_source_terminal_projection_profiles()
    semantic = profiles["semantic"]
    assert DECLARED_LOSS_PROFILE_REF in semantic.declared_loss
    assert profiles["effect"].execution_class == "PROJECTION"
    assert profiles["effect"].network_required is False
    assert "SOURCE_STALE" in profiles["failure"].typed_failures
    assert "OFFSET_STALE" in profiles["failure"].typed_failures
    assert profiles["authority"].canonical_owner == SOURCE_TERMINAL_PROJECTION_OWNER


def test_projection_is_declared_loss_and_never_authority() -> None:
    source = _source(
        outcome=CollectionCompleted(terminal=_terminal(records_count=2)),
        records=(_record(0), _record(1)),
    )
    result = project_source_collection(source)
    assert isinstance(result, ProjectedWithLoss)
    assert result.loss_profile_ref == DECLARED_LOSS_PROFILE_REF
    assert result.compat.status == "declared_loss"
    assert "legacy_result" in result.compat.inferred_fields
    assert "raw_snapshot" in result.compat.inferred_fields
    assert result.terminal.contract_version == "source_library.terminal_output.v2"
    assert result.terminal.source_mode == "site_search"
    assert result.terminal.status == "ok"
    assert result.terminal.results.stats.records == 2
    assert result.summary.is_authority is False
    assert result.terminal.meta.legacy_result_ref is None
    assert result.terminal.meta.raw_snapshot_ref is None


def test_projection_is_deterministic() -> None:
    source = _source(
        outcome=CollectionCompleted(terminal=_terminal(records_count=1)),
        records=(_record(0),),
    )
    left = project_source_collection(source)
    right = project_source_collection(source)
    assert isinstance(left, ProjectedWithLoss)
    assert isinstance(right, ProjectedWithLoss)
    assert left.terminal.projection_digest == right.terminal.projection_digest
    assert left.compat.compat_digest == right.compat.compat_digest
    assert left.summary.projection_digest == right.summary.projection_digest


def test_partial_and_unknown_derive_typed_terminal_status() -> None:
    partial = _source(
        outcome=CollectionPartiallyCompleted(
            terminal=_terminal(
                status="partial",
                records_count=1,
                failures=(
                    OrderedFailure(
                        order_index=0,
                        code="TRANSPORT",
                        message="one url failed",
                        source="url-0",
                    ),
                ),
            )
        ),
        records=(_record(0),),
        failures=(
            OrderedFailure(
                order_index=0,
                code="TRANSPORT",
                message="one url failed",
                source="url-0",
            ),
        ),
    )
    result = project_source_collection(partial)
    assert isinstance(result, ProjectedWithLoss)
    assert result.terminal.status == "partial"
    assert result.terminal.meta.reason_code == "partial_records"
    assert result.terminal.results.stats.errors == 1

    unknown = _source(
        outcome=CollectionOutcomeUnknown(reason="readback unavailable"),
    )
    result_unknown = project_source_collection(unknown)
    assert isinstance(result_unknown, ProjectedWithLoss)
    assert result_unknown.terminal.status == "error"
    assert result_unknown.terminal.meta.reason_code == "outcome_unknown"


def test_unsupported_schema_and_malformed_mode_fail_closed() -> None:
    source = _source(
        outcome=CollectionCompleted(terminal=_terminal()),
    )
    unsupported = object.__new__(SourceCollectionProjectionSource)
    for name, value in source.to_plain().items():
        object.__setattr__(unsupported, name, value)
    object.__setattr__(unsupported, "schema_version", "mrw.successor.unknown.v1")
    result = project_source_collection(unsupported)
    assert isinstance(result, ProjectionRejected)
    assert result.code == "UNSUPPORTED_VERSION"
    with pytest.raises(ValueError):
        pytest.importorskip("dataclasses").replace(source, source_mode="not_a_mode")


def test_historical_projection_source_uses_explicit_read_only_decoder() -> None:
    plain = _historical_source_plain()
    source = historical_source_collection_projection_source_from_plain(plain)
    assert source.to_plain() == plain
    assert source.source_digest == plain["source_digest"]

    current_result = project_source_collection(source)  # type: ignore[arg-type]
    assert isinstance(current_result, ProjectionRejected)
    assert current_result.code == "UNSUPPORTED_VERSION"

    wrong_version = dict(plain)
    wrong_version["schema_version"] = "mrw.source.unknown.v9"
    with pytest.raises(ValueError, match="exact C2.4 schema"):
        historical_source_collection_projection_source_from_plain(wrong_version)


def test_in_memory_delete_rebuild_is_digest_equivalent() -> None:
    source = _source(
        outcome=CollectionCompleted(terminal=_terminal(records_count=1)),
        records=(_record(0),),
    )
    projector = InMemorySourceLibraryTerminalProjector()
    first = projector.apply(source)
    rebuilt = projector.rebuild(source)
    # Delete/rebuild is content-digest equivalent; generation is a row fact.
    assert rebuilt.terminal["projection_digest"] == first.terminal["projection_digest"]
    assert rebuilt.compat["compat_digest"] == first.compat["compat_digest"]
    assert rebuilt.summary["projection_digest"] == first.summary["projection_digest"]
    assert rebuilt.generation == 1
    loaded = projector.load(source)
    assert loaded.terminal["projection_digest"] == first.terminal["projection_digest"]
    projector.delete(source)
    with pytest.raises(SourceLibraryProjectionNotFound):
        projector.load(source)


def test_stale_source_fails_closed() -> None:
    source = _source(
        outcome=CollectionCompleted(terminal=_terminal()),
    )
    projector = InMemorySourceLibraryTerminalProjector()
    projector.apply(source)
    stale = pytest.importorskip("dataclasses").replace(
        source,
        source_incarnation="inc:new",
        source_digest="",
    )
    with pytest.raises(ProjectionStaleError):
        projector.apply(stale)
    with pytest.raises(ProjectionStaleError):
        projector.load(stale)


def test_read_routing_rollback_retains_projection_rows() -> None:
    rollback = rollback_read_routing()
    assert rollback.claim_owner == "legacy"
    assert rollback.projection_rows_retained is True
    assert rollback.rollback_digest
