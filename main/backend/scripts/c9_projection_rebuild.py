"""C9 projection generation/rebuild over existing P0-D substrate (C9-M004/M005).

The rebuild is deterministic and database-bound.  It reads the canonical
source closure from the existing project ``successor_values`` table and
rejects any caller-supplied revision/digest that does not match the actually
read rows.  Candidate values and receipts are content-addressed and isolated
by the exact projector/source key plus projection offset and generation, so
cross-source generations never mix.  One exact generation CAS activates the
new offset; required-sink failure records typed repair and never activates.
Prior generation values remain recoverable and rollback points the active
offset back to them without changing canonical source or deleting receipts.

Local agent-session/graph/search projections use distinct ``*LocalProjection``
object types.  Elasticsearch, Qdrant and the live graph provider are not
called in this milestone: every external sink is explicitly
``DECLARED_LOSS_NO_CALL``.  The sink registry is fixed; callers cannot shrink
``required_sinks``.  Receipts never use wall-clock time in their identity, and
retrying the same source closure reproduces the same receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, runtime_checkable

from sqlalchemy import select, update
from sqlalchemy.engine import Connection, Engine

from app.successor_runtime.research.codec import sha256_hex
from app.successor_runtime.runtime.facade_contracts import (
    C9_LOCAL_SINK_NAMES,
    C9_ROLLBACK_TRANSITION_CONTRACT,
    C9Unavailable,
    projection_key_digest,
    rollback_transition_id,
    rollback_transition_ref,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.c9_projection_sources import (
    load_exact_semantic_source_closure,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_TABLES,
    ProjectTables,
    project_tables,
)
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
    ProjectionOffsetRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    RecordNotFound,
    StaleRevisionError,
)
from app.successor_runtime.substrate.postgres.session import (
    create_runtime_engine,
    validate_project_scope_ref,
)
from app.successor_runtime.substrate.postgres.values import (
    ReceiptRepository,
    ValueRepository,
)
from app.successor_runtime.substrate.projections.c9_sources import (
    PROJECTION_FIELD_LOSS_SCHEMA,
    C9SemanticSourceClosureV1,
    ProjectionFieldLossV1,
    build_agent_session_payload,
    build_research_graph_payload,
    build_search_payload,
)
from app.successor_runtime.substrate.projections.c9_sources import (
    content_digest as c9_content_digest,
)

__all__ = [
    "C9_REBUILD_CODEC_ID",
    "C9_RECEIPT_CODEC_ID",
    "C9_SOURCE_KIND",
    "CANDIDATE_CODECS",
    "CANDIDATE_OBJECT_TYPES",
    "EXTERNAL_DECLARED_LOSS_SINKS",
    "REQUIRED_LOCAL_SINKS",
    "SOURCE_OBJECT_TYPES",
    "GenerationCompleteness",
    "PostgresC9ProjectionRebuilder",
    "PostgresProjectionSinkWriter",
    "RebuildOutcome",
    "RebuildSinkStatus",
    "RollbackResult",
    "build_loss_profile",
    "candidate_value_id",
    "derive_rebuild_id",
    "generation_closure_ref",
    "receipt_payload",
    "rollback_position_payload",
    "source_closure_digest",
    "source_closure_revision",
]

C9_SOURCE_KIND = "successor_values"
C9_REBUILD_CODEC_ID = "mrw.successor.c9.projection-candidate.canonical-json.v1"
C9_RECEIPT_CODEC_ID = "mrw.successor.c9.projection-receipt.canonical-json.v1"
PROJECTION_ID = "projection.c9-movement-closure.v1"
REQUIRED_LOCAL_SINKS: tuple[str, ...] = tuple(C9_LOCAL_SINK_NAMES)
EXTERNAL_DECLARED_LOSS_SINKS: tuple[str, ...] = (
    "elasticsearch",
    "qdrant",
    "graph_provider",
)
CANDIDATE_OBJECT_TYPES: Mapping[str, str] = {
    "agent_session": "AgentSessionLocalProjection.v1",
    "graph": "GraphLocalProjection.v1",
    "search": "SearchLocalProjection.v1",
}
CANDIDATE_CODECS: Mapping[str, str] = {
    "agent_session": "mrw.successor.c9.agent-session-projection.canonical-json.v1",
    "graph": "mrw.successor.c9.graph-projection.canonical-json.v1",
    "search": "mrw.successor.c9.search-projection.canonical-json.v1",
}
SOURCE_OBJECT_TYPES: Mapping[str, str] = {
    "agent_session": "AgentSessionSource.v1",
    "graph": "GraphSource.v1",
    "search": "SearchSource.v1",
}


def build_loss_profile(sink: str) -> tuple[str, ...]:
    """Explicit per-sink loss profile; external sinks are declared loss."""

    if sink in EXTERNAL_DECLARED_LOSS_SINKS:
        return ("DECLARED_LOSS", "no provider call")
    if sink in REQUIRED_LOCAL_SINKS:
        return ("LOCAL_EXACT", "postgres readback")
    return ("UNREGISTERED_SINK", "no projection written")


def _key_identity(key: ProjectionOffsetKey) -> Mapping[str, Any]:
    return {
        "projector_id": key.projector_id,
        "projector_version": key.projector_version,
        "source_kind": key.source_kind,
        "source_ref": key.source_ref,
        "source_incarnation": key.source_incarnation,
    }


def _key_digest(key: ProjectionOffsetKey) -> str:
    return sha256_hex(_key_identity(key))


def source_closure_digest(
    source_ref: str,
    rows: Sequence[Mapping[str, Any]],
) -> str:
    """Canonical digest over the actual source rows read from PostgreSQL."""

    values = [
        {
            "value_id": str(row["value_id"]),
            "object_type": str(row["object_type"]),
            "content_digest": str(row["content_digest"]),
            "byte_size": int(row["byte_size"]),
            "revision": int(row["revision"]),
        }
        for row in sorted(rows, key=lambda item: str(item["value_id"]))
    ]
    return sha256_hex({"source_ref": source_ref, "values": values})


def source_closure_revision(rows: Sequence[Mapping[str, Any]]) -> int:
    if not rows:
        return 0
    return max(int(row["revision"]) for row in rows)


def derive_rebuild_id(
    key: ProjectionOffsetKey,
    generation: int,
    closure_digest: str,
) -> str:
    """Deterministic rebuild identity; retry of the same closure reuses it."""

    if len(closure_digest) != 64 or any(
        character not in "0123456789abcdef" for character in closure_digest
    ):
        raise ValueError("closure digest must be canonical SHA-256 hex")
    return "rebuild:c9:" + sha256_hex(
        {
            "key": _key_identity(key),
            "projection_generation": generation,
            "closure_digest": closure_digest,
        }
    )


def _projection_declared_losses(
    sink: str,
) -> tuple[ProjectionFieldLossV1, ...]:
    """Fixed local field-loss profile; external realization is not called."""

    return (
        ProjectionFieldLossV1(
            schema_version=PROJECTION_FIELD_LOSS_SCHEMA,
            field_path=f"{sink}.provider_realization",
            loss_kind="DECLARED_LOSS",
            reason="local milestone; external provider realization not executed",
        ),
    )


def _payload_for_sink(
    sink: str,
    closure: C9SemanticSourceClosureV1,
) -> dict[str, Any]:
    """Project one canonical source through the parallel typed builder."""

    losses = _projection_declared_losses(sink)
    if sink == "agent_session":
        return build_agent_session_payload(
            closure.runtime_session_source, declared_losses=losses
        ).to_plain()
    if sink == "graph":
        return build_research_graph_payload(
            closure.research_graph_source, declared_losses=losses
        ).to_plain()
    if sink == "search":
        return build_search_payload(
            closure.c7_search_source, declared_losses=losses
        ).to_plain()
    raise ValueError(f"unregistered C9 projection sink: {sink}")


def candidate_value_id(
    sink: str,
    key: ProjectionOffsetKey,
    generation: int,
    digest: str,
) -> str:
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError("candidate digest must be canonical SHA-256 hex")
    source_hash = _key_digest(key)[:8]
    return f"c9:{sink}:{source_hash}:gen-{generation}:{digest[:12]}"


def receipt_payload(
    *,
    sink: str,
    key: ProjectionOffsetKey,
    generation: int,
    rebuild_id: str,
    candidate_value_id: str,
    candidate_digest: str,
) -> dict[str, Any]:
    return {
        "schema_version": "mrw.successor.c9.projection-receipt.v1",
        "sink": sink,
        "projector_id": key.projector_id,
        "projector_version": key.projector_version,
        "source_kind": key.source_kind,
        "source_ref": key.source_ref,
        "source_incarnation": key.source_incarnation,
        "projection_generation": generation,
        "rebuild_id": rebuild_id,
        "candidate_value_id": candidate_value_id,
        "candidate_digest": candidate_digest,
    }


def rollback_position_payload(
    *,
    projection_generation: int,
    offset_revision: int,
    source_revision: int,
    source_digest: str,
    offset_ref: str,
) -> Mapping[str, Any]:
    """Exact projection position identity shared by offsets and rollbacks.

    The query snapshot exposes ``projection_revision == projection_generation``
    and ``cursor == source_revision``; rollback receipts must bind the same
    identity so sanctioned rollback is accepted for any persisted target
    generation, not only when the target generation happens to equal the
    canonical source revision.
    """

    return {
        "projection_generation": projection_generation,
        "offset_revision": offset_revision,
        "projection_revision": projection_generation,
        "source_digest": source_digest,
        "cursor": source_revision,
        "offset_ref": offset_ref,
    }


def generation_closure_ref(
    resolved_schema: str,
    generation: int,
    closure_digest: str,
) -> str:
    if generation < 0:
        raise ValueError("generation must be non-negative")
    if len(closure_digest) != 64 or any(
        character not in "0123456789abcdef" for character in closure_digest
    ):
        raise ValueError("closure digest must be canonical SHA-256 hex")
    return f"value:{resolved_schema}:c9:generation:{generation}:{closure_digest}"


def _put_receipt_idempotent(
    connection: Connection,
    scope: RuntimeScope,
    tables: ProjectTables,
    *,
    receipt_id: str,
    receipt_digest: str,
    delivery_intent_ref: str,
    attempt_ref: str,
    provider_locator: str,
    content: Mapping[str, Any],
) -> str:
    """Write one deterministic receipt; replay never overwrites identity fields.

    ``outcome_time`` is the real observation timestamp and is persisted/returned
    only through the receipt row, never included in the identity digest.  An
    existing receipt for the same deterministic id is read back unchanged so a
    retry of the same source closure stays idempotent.
    """

    table = tables.successor_receipts
    existing = (
        connection.execute(
            select(table).where(
                table.c.project_key == scope.project_scope.project_key,
                table.c.receipt_id == receipt_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if existing is not None:
        if existing["receipt_digest"] != receipt_digest:
            raise C9Unavailable("persisted receipt digest drift")
        return receipt_id
    ReceiptRepository(connection, tables).put_exact(
        scope=scope,
        receipt_id=receipt_id,
        receipt_digest=receipt_digest,
        delivery_intent_ref=delivery_intent_ref,
        attempt_ref=attempt_ref,
        provider_locator=provider_locator,
        content=content,
        outcome_time=datetime.now(UTC),
    )
    return receipt_id


@dataclass(frozen=True)
class RebuildSinkStatus:
    sink: str
    outcome: Literal["LOCAL_WRITTEN", "DECLARED_LOSS_NO_CALL", "FAILED"]
    candidate_value_ref: str | None = None
    candidate_digest: str | None = None
    receipt_ref: str | None = None
    declared_loss: tuple[str, ...] = ()
    failure_code: str | None = None


@dataclass(frozen=True)
class RebuildOutcome:
    rebuild_id: str
    key: ProjectionOffsetKey
    source_revision: int
    source_digest: str
    generation_activated: bool
    generation: int | None
    sink_statuses: tuple[RebuildSinkStatus, ...]
    repair_refs: tuple[str, ...] = ()
    activated_offset: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class GenerationCompleteness:
    key: ProjectionOffsetKey
    generation: int
    candidates: tuple[Mapping[str, Any], ...]
    receipts: tuple[str, ...]


@dataclass(frozen=True)
class RollbackResult:
    receipt_id: str
    receipt_ref: str
    key: ProjectionOffsetKey
    from_generation: int
    target_generation: int
    offset_revision: int
    source_digest: str
    observed_at: str | None
    offset: Mapping[str, Any]


@runtime_checkable
class LocalSinkWriter(Protocol):
    """Deterministic local sink adapter writing one candidate and receipt."""

    def write_candidate(
        self,
        *,
        sink: str,
        key: ProjectionOffsetKey,
        projection_offset_id: str,
        generation: int,
        closure: C9SemanticSourceClosureV1,
        rebuild_id: str,
    ) -> Mapping[str, Any]: ...

    def write_receipt(
        self,
        *,
        sink: str,
        key: ProjectionOffsetKey,
        generation: int,
        rebuild_id: str,
        candidate: Mapping[str, Any],
    ) -> str: ...


class PostgresProjectionSinkWriter:
    """PostgreSQL sink adapter using existing successor_values/receipts."""

    def __init__(
        self,
        connection: Connection,
        scope: RuntimeScope,
        tables: ProjectTables,
    ) -> None:
        self.connection = connection
        self.scope = scope
        self.tables = tables

    def write_candidate(
        self,
        *,
        sink: str,
        key: ProjectionOffsetKey,
        projection_offset_id: str,
        generation: int,
        closure: C9SemanticSourceClosureV1,
        rebuild_id: str,
    ) -> Mapping[str, Any]:
        content = {
            "schema_version": "mrw.successor.c9.projection-candidate-envelope.v1",
            "projection_id": PROJECTION_ID,
            "projector_id": key.projector_id,
            "projector_version": key.projector_version,
            "source_kind": key.source_kind,
            "source_ref": key.source_ref,
            "source_incarnation": key.source_incarnation,
            "projection_offset_id": projection_offset_id,
            "projection_generation": generation,
            "payload": _payload_for_sink(sink, closure),
        }
        digest = sha256_hex(content)
        value_id = candidate_value_id(sink, key, generation, digest)
        provenance = {
            **_key_identity(key),
            "projection_offset_id": projection_offset_id,
            "sink": sink,
            "projection_generation": generation,
            "rebuild_id": rebuild_id,
            "closure_digest": closure.closure_digest,
            "closure_revision": int(closure.revision),
        }
        stored = ValueRepository(self.connection, self.tables).put_exact(
            scope=self.scope,
            value_id=value_id,
            object_type=CANDIDATE_OBJECT_TYPES[sink],
            codec_id=CANDIDATE_CODECS[sink],
            content=content,
            expected_digest=digest,
            provenance_digest=sha256_hex(provenance),
            expected_revision=0,
            expected_incarnation=self.scope.project_scope.incarnation,
            source_ref=closure.closure_id,
            provenance=provenance,
            state="AVAILABLE",
        )
        return {
            "value_id": stored.value_id,
            "content_digest": stored.content_digest,
            "revision": stored.revision,
            "incarnation": stored.incarnation,
        }

    def write_receipt(
        self,
        *,
        sink: str,
        key: ProjectionOffsetKey,
        generation: int,
        rebuild_id: str,
        candidate: Mapping[str, Any],
    ) -> str:
        content = receipt_payload(
            sink=sink,
            key=key,
            generation=generation,
            rebuild_id=rebuild_id,
            candidate_value_id=str(candidate["value_id"]),
            candidate_digest=str(candidate["content_digest"]),
        )
        digest = sha256_hex(content)
        source_hash = _key_digest(key)[:8]
        receipt_id = f"c9:{sink}:receipt:{source_hash}:gen-{generation}:{digest[:12]}"
        return _put_receipt_idempotent(
            self.connection,
            self.scope,
            self.tables,
            receipt_id=receipt_id,
            receipt_digest=digest,
            delivery_intent_ref=f"c9-local-projection:{sink}:gen-{generation}",
            attempt_ref=f"rebuild:{rebuild_id}",
            provider_locator=(
                f"local:postgres:{self.scope.project_scope.resolved_schema}:{sink}"
            ),
            content=content,
        )


class PostgresC9ProjectionRebuilder:
    """Generation CAS rebuild over the existing offset/value substrate."""

    def __init__(
        self,
        connection: Connection,
        scope: RuntimeScope,
        *,
        tables: ProjectTables | None = None,
        metadata: Any = None,
    ) -> None:
        self.connection = connection
        self.scope = scope
        if tables is None:
            if metadata is None:
                metadata = _project_metadata(scope.project_scope.resolved_schema)
            tables = project_tables(metadata, scope.project_scope.resolved_schema)
        self.tables = tables

    def initialize(
        self,
        *,
        projection_offset_id: str,
        key: ProjectionOffsetKey,
        source_revision: int,
        source_digest: str,
        source_ref: str,
        writer: LocalSinkWriter | None = None,
    ) -> Mapping[str, Any]:
        """Create a verified generation-0 baseline over the real source rows."""

        if source_ref != key.source_ref:
            raise C9Unavailable(
                "source_ref does not exactly match the projection source key"
            )
        closure = self._load_semantic_source_closure(source_ref, key)
        observed_digest = closure.closure_digest
        observed_revision = int(closure.revision)
        if observed_digest != source_digest or observed_revision != source_revision:
            raise C9Unavailable(
                "source closure digest/revision does not match the actually read rows"
            )
        sink_writer = writer or PostgresProjectionSinkWriter(
            self.connection, self.scope, self.tables
        )
        rebuild_id = derive_rebuild_id(key, 0, observed_digest)
        statuses: list[RebuildSinkStatus] = []
        for sink in REQUIRED_LOCAL_SINKS:
            candidate = sink_writer.write_candidate(
                sink=sink,
                key=key,
                projection_offset_id=projection_offset_id,
                generation=0,
                closure=closure,
                rebuild_id=rebuild_id,
            )
            sink_writer.write_receipt(
                sink=sink,
                key=key,
                generation=0,
                rebuild_id=rebuild_id,
                candidate=candidate,
            )
            statuses.append(
                RebuildSinkStatus(
                    sink=sink,
                    outcome="LOCAL_WRITTEN",
                    candidate_digest=str(candidate["content_digest"]),
                )
            )
        offset_ref = generation_closure_ref(
            self.scope.project_scope.resolved_schema,
            0,
            sha256_hex(
                {
                    "key": _key_identity(key),
                    "generation": 0,
                    "sinks": [
                        {
                            "sink": status.sink,
                            "candidate_digest": status.candidate_digest,
                        }
                        for status in statuses
                    ],
                }
            ),
        )
        return ProjectionOffsetRepository(self.connection, self.scope).create(
            projection_offset_id=projection_offset_id,
            key=key,
            projection_generation=0,
            source_revision=observed_revision,
            source_digest=observed_digest,
            offset_ref=offset_ref,
        )

    def rebuild(
        self,
        *,
        key: ProjectionOffsetKey,
        source_revision: int,
        source_digest: str,
        source_ref: str,
        writer: LocalSinkWriter | None = None,
    ) -> RebuildOutcome:
        offsets = ProjectionOffsetRepository(self.connection, self.scope)
        current = offsets.load_source(key, for_update=True)
        if current is None:
            raise C9Unavailable(
                "rebuild requires an existing initialized projection offset"
            )
        if source_ref != key.source_ref:
            raise C9Unavailable(
                "source_ref does not exactly match the projection source key; "
                "offset A cannot be activated by source B"
            )
        next_generation = int(current["projection_generation"]) + 1
        closure = self._load_semantic_source_closure(source_ref, key)
        observed_digest = closure.closure_digest
        observed_revision = int(closure.revision)
        if observed_digest != source_digest or observed_revision != source_revision:
            raise C9Unavailable(
                "source closure digest/revision does not match the actually read rows; "
                "caller-forged source binding rejected"
            )
        rebuild_id = derive_rebuild_id(key, next_generation, observed_digest)
        sink_writer = writer or PostgresProjectionSinkWriter(
            self.connection, self.scope, self.tables
        )
        statuses: list[RebuildSinkStatus] = []
        repair_refs: list[str] = []
        projection_offset_id = str(current["projection_offset_id"])
        for sink in REQUIRED_LOCAL_SINKS:
            try:
                candidate = sink_writer.write_candidate(
                    sink=sink,
                    key=key,
                    projection_offset_id=projection_offset_id,
                    generation=next_generation,
                    closure=closure,
                    rebuild_id=rebuild_id,
                )
                receipt_ref = sink_writer.write_receipt(
                    sink=sink,
                    key=key,
                    generation=next_generation,
                    rebuild_id=rebuild_id,
                    candidate=candidate,
                )
            except Exception as exc:  # noqa: BLE001 - typed required-sink repair
                statuses.append(
                    RebuildSinkStatus(
                        sink=sink,
                        outcome="FAILED",
                        failure_code=f"{type(exc).__name__}:{exc}",
                    )
                )
                repair_refs.append(f"c9:repair:required-sink:{sink}")
                continue
            statuses.append(
                RebuildSinkStatus(
                    sink=sink,
                    outcome="LOCAL_WRITTEN",
                    candidate_value_ref=(
                        f"value:{self.scope.project_scope.resolved_schema}:"
                        f"{candidate['value_id']}"
                    ),
                    candidate_digest=str(candidate["content_digest"]),
                    receipt_ref=receipt_ref,
                    declared_loss=build_loss_profile(sink),
                )
            )
        for sink in EXTERNAL_DECLARED_LOSS_SINKS:
            statuses.append(
                RebuildSinkStatus(
                    sink=sink,
                    outcome="DECLARED_LOSS_NO_CALL",
                    declared_loss=build_loss_profile(sink),
                )
            )
        if repair_refs:
            return RebuildOutcome(
                rebuild_id=rebuild_id,
                key=key,
                source_revision=observed_revision,
                source_digest=observed_digest,
                generation_activated=False,
                generation=next_generation,
                sink_statuses=tuple(statuses),
                repair_refs=tuple(repair_refs),
            )
        closure_digest = sha256_hex(
            {
                "key": _key_identity(key),
                "generation": next_generation,
                "sinks": [
                    {
                        "sink": status.sink,
                        "candidate_digest": status.candidate_digest,
                    }
                    for status in statuses
                    if status.outcome == "LOCAL_WRITTEN"
                ],
            }
        )
        offset_ref = generation_closure_ref(
            self.scope.project_scope.resolved_schema,
            next_generation,
            closure_digest,
        )
        row = self._activate_generation(
            current,
            key=key,
            next_generation=next_generation,
            source_revision=observed_revision,
            source_digest=observed_digest,
            offset_ref=offset_ref,
        )
        return RebuildOutcome(
            rebuild_id=rebuild_id,
            key=key,
            source_revision=observed_revision,
            source_digest=observed_digest,
            generation_activated=True,
            generation=next_generation,
            sink_statuses=tuple(statuses),
            activated_offset=row,
        )

    def rollback(
        self,
        *,
        key: ProjectionOffsetKey,
        target_generation: int,
    ) -> Mapping[str, Any]:
        """Backward-compatible wrapper returning the activated offset row."""

        return self.rollback_with_receipt(
            key=key, target_generation=target_generation
        ).offset

    def rollback_with_receipt(
        self,
        *,
        key: ProjectionOffsetKey,
        target_generation: int,
    ) -> RollbackResult:
        """Atomic rollback: lock offset, verify target, CAS + immutable receipt."""

        offsets = ProjectionOffsetRepository(self.connection, self.scope)
        current = offsets.load_source(key, for_update=True)
        if current is None:
            raise RecordNotFound("projection offset not found")
        active_generation = int(current["projection_generation"])
        if target_generation < 0:
            raise ValueError("rollback target generation must be non-negative")
        if active_generation == target_generation:
            # Retry after a durable rollback: same receipt, no revision bump.
            receipt_row = self._find_rollback_receipt(key, current)
            return self._rollback_result_from_receipt(receipt_row, current, key)
        if target_generation > active_generation:
            raise ValueError(
                "rollback target generation must be older than the active generation"
            )
        completeness = self.validate_generation_completeness(
            key=key, generation=target_generation
        )
        prior_revision, prior_digest = self._prior_source_binding(
            key, target_generation
        )
        closure_digest = sha256_hex(
            {
                "key": _key_identity(key),
                "generation": target_generation,
                "candidates": [
                    {
                        "value_id": candidate["value_id"],
                        "content_digest": candidate["content_digest"],
                    }
                    for candidate in completeness.candidates
                ],
            }
        )
        offset_ref = generation_closure_ref(
            self.scope.project_scope.resolved_schema,
            target_generation,
            closure_digest,
        )
        completeness_digest = self._generation_completeness_digest(
            key, target_generation, completeness
        )
        from_position = rollback_position_payload(
            projection_generation=active_generation,
            offset_revision=int(current["revision"]),
            source_revision=int(current["source_revision"]),
            source_digest=str(current["source_digest"]),
            offset_ref=str(current["offset_ref"]),
        )
        savepoint = self.connection.begin_nested()
        try:
            row = self._cas_rollback_offset(
                current,
                key=key,
                target_generation=target_generation,
                source_revision=prior_revision,
                source_digest=prior_digest,
                offset_ref=offset_ref,
            )
            to_position = rollback_position_payload(
                projection_generation=target_generation,
                offset_revision=int(row["revision"]),
                source_revision=prior_revision,
                source_digest=prior_digest,
                offset_ref=offset_ref,
            )
            transition_id = rollback_transition_id(
                from_position=from_position,
                to_position=to_position,
                generation_completeness_digest=completeness_digest,
            )
            ref = rollback_transition_ref(transition_id)
            content = {
                "contract": C9_ROLLBACK_TRANSITION_CONTRACT,
                "ref": ref,
                "digest": "",
                "projection_id": PROJECTION_ID,
                "projector_id": key.projector_id,
                "projector_version": key.projector_version,
                "source_kind": key.source_kind,
                "source_ref": key.source_ref,
                "source_incarnation": key.source_incarnation,
                "from": from_position,
                "to": to_position,
                "generation_completeness_digest": completeness_digest,
            }
            content["digest"] = c9_content_digest(
                {
                    key_name: value
                    for key_name, value in content.items()
                    if key_name != "digest"
                }
            )
            receipt_id = f"c9:rollback-transition:{transition_id[:32]}"
            key_digest = projection_key_digest(
                projector_id=key.projector_id,
                projector_version=key.projector_version,
                source_kind=key.source_kind,
                source_ref=key.source_ref,
                source_incarnation=key.source_incarnation,
            )
            _put_receipt_idempotent(
                self.connection,
                self.scope,
                self.tables,
                receipt_id=receipt_id,
                receipt_digest=c9_content_digest(content),
                delivery_intent_ref=(
                    f"c9-rollback:{key_digest[:16]}:{transition_id[:16]}"
                ),
                attempt_ref=f"rollback:{ref}",
                provider_locator=(
                    f"local:postgres:{self.scope.project_scope.resolved_schema}:rollback"
                ),
                content=content,
            )
            savepoint.commit()
        except Exception:
            if savepoint.is_active:
                savepoint.rollback()
            raise
        fresh = offsets.load_source(key)
        receipt_row = self._find_rollback_receipt(key, fresh)
        return self._rollback_result_from_receipt(receipt_row, fresh, key)

    def _find_rollback_receipt(
        self,
        key: ProjectionOffsetKey,
        offset_row: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Locate the exact rollback receipt whose ``to`` is the active offset."""

        table = self.tables.successor_receipts
        rows = (
            self.connection.execute(
                select(table).where(
                    table.c.project_key == self.scope.project_scope.project_key,
                    table.c.receipt_id.like("c9:rollback-transition:%"),
                )
            )
            .mappings()
            .all()
        )
        matches: list[Mapping[str, Any]] = []
        for row in rows:
            content = row["receipt_json"]
            if not isinstance(content, Mapping):
                continue
            if content.get("contract") != C9_ROLLBACK_TRANSITION_CONTRACT:
                continue
            if content.get("projector_id") != key.projector_id:
                continue
            if content.get("source_ref") != key.source_ref:
                continue
            to_position = content.get("to")
            if not isinstance(to_position, Mapping):
                continue
            if (
                to_position.get("projection_generation")
                != int(offset_row["projection_generation"])
                or to_position.get("offset_revision") != int(offset_row["revision"])
                or to_position.get("source_digest") != str(offset_row["source_digest"])
                or to_position.get("offset_ref") != str(offset_row["offset_ref"])
            ):
                continue
            if c9_content_digest(content) != row["receipt_digest"]:
                raise C9Unavailable("rollback receipt digest drift")
            matches.append(row)
        if len(matches) != 1:
            raise C9Unavailable(
                f"rollback receipt for active offset is missing or duplicated "
                f"({len(matches)})"
            )
        return matches[0]

    def _generation_completeness_digest(
        self,
        key: ProjectionOffsetKey,
        generation: int,
        completeness: GenerationCompleteness,
    ) -> str:
        return sha256_hex(
            {
                "key": _key_identity(key),
                "generation": generation,
                "candidates": [
                    {
                        "value_id": candidate["value_id"],
                        "content_digest": candidate["content_digest"],
                    }
                    for candidate in completeness.candidates
                ],
                "receipts": list(completeness.receipts),
            }
        )

    def _cas_rollback_offset(
        self,
        current: Mapping[str, Any],
        *,
        key: ProjectionOffsetKey,
        target_generation: int,
        source_revision: int,
        source_digest: str,
        offset_ref: str,
    ) -> Mapping[str, Any]:
        table = PUBLIC_TABLES["runtime_projection_offsets"]
        result = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == self.scope.project_scope.project_key,
                table.c.projection_offset_id == current["projection_offset_id"],
                table.c.projector_id == key.projector_id,
                table.c.projector_version == key.projector_version,
                table.c.source_kind == key.source_kind,
                table.c.source_ref == key.source_ref,
                table.c.source_incarnation == key.source_incarnation,
                table.c.projection_generation == current["projection_generation"],
                table.c.revision == current["revision"],
                table.c.source_revision == current["source_revision"],
                table.c.source_digest == current["source_digest"],
            )
            .values(
                projection_generation=target_generation,
                source_revision=source_revision,
                source_digest=source_digest,
                offset_ref=offset_ref,
                revision=int(current["revision"]) + 1,
                updated_at=datetime.now(UTC),
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("projection offset rollback CAS failed")
        return ProjectionOffsetRepository(self.connection, self.scope).load(
            str(current["projection_offset_id"])
        )

    def _rollback_result_from_receipt(
        self,
        receipt_row: Mapping[str, Any],
        offset_row: Mapping[str, Any],
        key: ProjectionOffsetKey,
    ) -> RollbackResult:
        content = receipt_row["receipt_json"]
        if not isinstance(content, Mapping):
            raise C9Unavailable("rollback receipt payload is malformed")
        if c9_content_digest(content) != receipt_row["receipt_digest"]:
            raise C9Unavailable("rollback receipt digest drift")
        expected_digest = c9_content_digest(
            {name: value for name, value in content.items() if name != "digest"}
        )
        if content.get("digest") != expected_digest:
            raise C9Unavailable("rollback receipt transition digest drift")
        to_position = content.get("to")
        from_position = content.get("from")
        if not isinstance(to_position, Mapping) or not isinstance(
            from_position, Mapping
        ):
            raise C9Unavailable("rollback receipt positions are malformed")
        if (
            to_position.get("projection_generation")
            != int(offset_row["projection_generation"])
            or to_position.get("offset_revision") != int(offset_row["revision"])
            or to_position.get("source_digest") != str(offset_row["source_digest"])
            or to_position.get("offset_ref") != str(offset_row["offset_ref"])
        ):
            raise C9Unavailable("rollback receipt position drift")
        observed_at = (
            receipt_row["outcome_time"].astimezone(UTC).isoformat()
            if receipt_row["outcome_time"]
            else None
        )
        return RollbackResult(
            receipt_id=str(receipt_row["receipt_id"]),
            receipt_ref=str(content["ref"]),
            key=key,
            from_generation=int(from_position["projection_generation"]),
            target_generation=int(to_position["projection_generation"]),
            offset_revision=int(to_position["offset_revision"]),
            source_digest=str(to_position["source_digest"]),
            observed_at=observed_at,
            offset=dict(offset_row),
        )

    def readback(
        self,
        key: ProjectionOffsetKey,
        *,
        generation: int | None = None,
    ) -> Mapping[str, Any]:
        offsets = ProjectionOffsetRepository(self.connection, self.scope)
        row = offsets.load_source(key)
        if row is None:
            raise RecordNotFound("projection offset not found")
        active_generation = int(row["projection_generation"])
        target = active_generation if generation is None else generation
        candidates = self._candidate_rows_for_generation(key, target)
        verified: list[Mapping[str, Any]] = []
        for candidate in candidates:
            exact = ValueRepository(self.connection, self.tables).get_exact(
                self.scope,
                value_id=str(candidate["value_id"]),
                expected_revision=int(candidate["revision"]),
                expected_incarnation=str(candidate["incarnation"]),
                expected_digest=str(candidate["content_digest"]),
            )
            if hashlib.sha256(exact).hexdigest() != candidate["content_digest"]:
                raise C9Unavailable("candidate value readback digest mismatch")
            verified.append(
                {
                    "value_id": candidate["value_id"],
                    "object_type": candidate["object_type"],
                    "content_digest": candidate["content_digest"],
                    "byte_size": int(candidate["byte_size"]),
                }
            )
        return {
            "projection_offset_id": row["projection_offset_id"],
            "projection_generation": active_generation,
            "projection_revision": active_generation,
            "source_revision": int(row["source_revision"]),
            "source_digest": row["source_digest"],
            "offset_ref": row["offset_ref"],
            "offset_revision": int(row["revision"]),
            "candidates": tuple(verified),
            "fresh_session": True,
        }

    def _activate_generation(
        self,
        current: Mapping[str, Any],
        *,
        key: ProjectionOffsetKey,
        next_generation: int,
        source_revision: int,
        source_digest: str,
        offset_ref: str,
    ) -> Mapping[str, Any]:
        table = PUBLIC_TABLES["runtime_projection_offsets"]
        result = self.connection.execute(
            update(table)
            .where(
                table.c.project_key == self.scope.project_scope.project_key,
                table.c.projection_offset_id == current["projection_offset_id"],
                table.c.projector_id == key.projector_id,
                table.c.projector_version == key.projector_version,
                table.c.source_kind == key.source_kind,
                table.c.source_ref == key.source_ref,
                table.c.source_incarnation == key.source_incarnation,
                table.c.projection_generation == current["projection_generation"],
                table.c.revision == current["revision"],
                table.c.source_revision == current["source_revision"],
                table.c.source_digest == current["source_digest"],
            )
            .values(
                projection_generation=next_generation,
                source_revision=source_revision,
                source_digest=source_digest,
                offset_ref=offset_ref,
                revision=int(current["revision"]) + 1,
                updated_at=datetime.now(UTC),
            )
        )
        if getattr(result, "rowcount", None) != 1:
            raise StaleRevisionError("projection offset generation CAS failed")
        return ProjectionOffsetRepository(self.connection, self.scope).load(
            str(current["projection_offset_id"])
        )

    def _load_semantic_source_closure(
        self,
        source_ref: str,
        key: ProjectionOffsetKey,
    ) -> C9SemanticSourceClosureV1:
        """Load the official exact closure and bind it to the source key."""

        if source_ref != key.source_ref:
            raise C9Unavailable(
                "source_ref does not exactly match the projection source key"
            )
        closure = load_exact_semantic_source_closure(self.connection, self.scope)
        if closure.closure_id != key.source_ref:
            raise C9Unavailable(
                "semantic source closure identity does not match the projection "
                "source key"
            )
        if closure.incarnation != key.source_incarnation:
            raise C9Unavailable(
                "semantic source closure incarnation does not match the projection "
                "source key"
            )
        return closure

    def _prior_source_binding(
        self,
        key: ProjectionOffsetKey,
        generation: int,
    ) -> tuple[int, str]:
        """Restore the exact source revision/digest recorded by the old candidates."""

        candidates = self._candidate_rows_for_generation(key, generation)
        revisions: set[int] = set()
        digests: set[str] = set()
        for candidate in candidates:
            content = candidate.get("content_json")
            if not isinstance(content, Mapping):
                raise C9Unavailable(
                    f"prior generation {generation} candidate content is missing"
                )
            provenance = candidate.get("provenance_json")
            if not isinstance(provenance, Mapping):
                raise C9Unavailable(
                    f"prior generation {generation} candidate provenance is missing"
                )
            revisions.add(int(provenance["closure_revision"]))
            digests.add(str(provenance["closure_digest"]))
        if len(revisions) != 1 or len(digests) != 1:
            raise C9Unavailable(
                f"prior generation {generation} source binding is ambiguous"
            )
        return revisions.pop(), digests.pop()

    def validate_generation_completeness(
        self,
        *,
        key: ProjectionOffsetKey,
        generation: int,
    ) -> GenerationCompleteness:
        """Exact 3 candidates + 3 receipts; missing/duplicate/tamper fail."""

        candidates = self._candidate_rows_for_generation(key, generation)
        if len(candidates) != len(CANDIDATE_OBJECT_TYPES):
            raise C9Unavailable(
                f"generation completeness: expected {len(CANDIDATE_OBJECT_TYPES)} "
                f"candidates, got {len(candidates)}"
            )
        by_object_type: dict[str, list[Mapping[str, Any]]] = {}
        for row in candidates:
            by_object_type.setdefault(str(row["object_type"]), []).append(row)
        verified: list[Mapping[str, Any]] = []
        for sink, object_type in CANDIDATE_OBJECT_TYPES.items():
            matches = by_object_type.get(object_type, [])
            if len(matches) != 1:
                raise C9Unavailable(
                    f"generation completeness: required sink {sink} "
                    "candidate missing or duplicated"
                )
            verified.append(
                self._verify_completeness_candidate(matches[0], key, generation, sink)
            )
        receipts = self._generation_receipts(key, generation)
        candidate_by_value = {
            candidate["value_id"]: candidate for candidate in verified
        }
        for receipt in receipts:
            content = receipt["receipt_json"]
            if not isinstance(content, Mapping):
                raise C9Unavailable("generation receipt payload is malformed")
            if sha256_hex(content) != receipt["receipt_digest"]:
                raise C9Unavailable("generation receipt digest tampered")
            candidate_id = content.get("candidate_value_id")
            candidate = (
                candidate_by_value.get(str(candidate_id)) if candidate_id else None
            )
            if (
                candidate is None
                or content.get("candidate_digest") != candidate["content_digest"]
            ):
                raise C9Unavailable("generation receipt does not bind its candidate")
            if content.get("projection_generation") != generation:
                raise C9Unavailable("generation receipt generation drift")
            if content.get("rebuild_id") != candidate["provenance"].get("rebuild_id"):
                raise C9Unavailable("generation receipt rebuild identity drift")
        return GenerationCompleteness(
            key=key,
            generation=generation,
            candidates=tuple(verified),
            receipts=tuple(str(receipt["receipt_id"]) for receipt in receipts),
        )

    def _verify_completeness_candidate(
        self,
        row: Mapping[str, Any],
        key: ProjectionOffsetKey,
        generation: int,
        sink: str,
    ) -> Mapping[str, Any]:
        provenance = row["provenance_json"]
        if not isinstance(provenance, Mapping):
            raise C9Unavailable(f"generation candidate provenance missing: {sink}")
        expected = {
            "projector_id": key.projector_id,
            "projector_version": key.projector_version,
            "source_kind": key.source_kind,
            "source_ref": key.source_ref,
            "source_incarnation": key.source_incarnation,
            "projection_generation": generation,
            "sink": sink,
        }
        for field, value in expected.items():
            if provenance.get(field) != value:
                raise C9Unavailable(
                    f"generation candidate provenance drift: {sink}.{field}"
                )
        if not provenance.get("rebuild_id"):
            raise C9Unavailable(
                f"generation candidate rebuild identity missing: {sink}"
            )
        envelope = row["content_json"]
        if not isinstance(envelope, Mapping):
            raise C9Unavailable(f"generation candidate payload missing: {sink}")
        payload = envelope.get("payload")
        if not isinstance(payload, Mapping):
            raise C9Unavailable(f"generation candidate typed payload missing: {sink}")
        losses = payload.get("declared_losses")
        if not isinstance(losses, list) or not losses:
            raise C9Unavailable(f"generation candidate loss records missing: {sink}")
        for loss in losses:
            if not isinstance(loss, Mapping) or loss.get("schema_version") != (
                PROJECTION_FIELD_LOSS_SCHEMA
            ):
                raise C9Unavailable(f"generation candidate loss record drift: {sink}")
        exact = ValueRepository(self.connection, self.tables).get_exact(
            self.scope,
            value_id=str(row["value_id"]),
            expected_revision=int(row["revision"]),
            expected_incarnation=str(row["incarnation"]),
            expected_digest=str(row["content_digest"]),
        )
        if len(exact) != int(row["byte_size"]):
            raise C9Unavailable(f"generation candidate byte_size drift: {sink}")
        return {
            "value_id": str(row["value_id"]),
            "object_type": str(row["object_type"]),
            "content_digest": str(row["content_digest"]),
            "byte_size": int(row["byte_size"]),
            "revision": int(row["revision"]),
            "incarnation": str(row["incarnation"]),
            "sink": sink,
            "payload": payload,
            "provenance": provenance,
        }

    def _generation_receipts(
        self,
        key: ProjectionOffsetKey,
        generation: int,
    ) -> tuple[Mapping[str, Any], ...]:
        table = self.tables.successor_receipts
        source_hash = projection_key_digest(
            projector_id=key.projector_id,
            projector_version=key.projector_version,
            source_kind=key.source_kind,
            source_ref=key.source_ref,
            source_incarnation=key.source_incarnation,
        )[:8]
        pattern = f"c9:%:receipt:{source_hash}:gen-{generation}:%"
        rows = (
            self.connection.execute(
                select(table).where(
                    table.c.project_key == self.scope.project_scope.project_key,
                    table.c.receipt_id.like(pattern),
                )
            )
            .mappings()
            .all()
        )
        if len(rows) != len(CANDIDATE_OBJECT_TYPES):
            raise C9Unavailable(
                f"generation completeness: expected {len(CANDIDATE_OBJECT_TYPES)} "
                f"receipts for generation {generation}, got {len(rows)}"
            )
        sinks: set[str] = set()
        for row in rows:
            content = row["receipt_json"]
            if not isinstance(content, Mapping):
                raise C9Unavailable("generation receipt payload is malformed")
            sinks.add(str(content.get("sink")))
            if row["delivery_intent_ref"] != (
                f"c9-local-projection:{content.get('sink')}:gen-{generation}"
            ):
                raise C9Unavailable("generation receipt delivery intent drift")
        if sinks != set(CANDIDATE_OBJECT_TYPES):
            raise C9Unavailable("generation receipt sink set is incomplete/duplicated")
        return tuple(rows)

    def _candidate_rows_for_generation(
        self,
        key: ProjectionOffsetKey,
        generation: int,
    ) -> tuple[Mapping[str, Any], ...]:
        table = self.tables.successor_values
        statement = select(table).where(
            table.c.project_key == self.scope.project_scope.project_key,
            table.c.object_type.in_(tuple(CANDIDATE_OBJECT_TYPES.values())),
            table.c.provenance_json["projector_id"].as_string() == key.projector_id,
            table.c.provenance_json["projector_version"].as_string()
            == key.projector_version,
            table.c.provenance_json["source_kind"].as_string() == key.source_kind,
            table.c.provenance_json["source_ref"].as_string() == key.source_ref,
            table.c.provenance_json["source_incarnation"].as_string()
            == key.source_incarnation,
            table.c.provenance_json["projection_generation"].as_integer() == generation,
        )
        rows = self.connection.execute(statement).mappings().all()
        return tuple(
            {
                "value_id": row["value_id"],
                "object_type": row["object_type"],
                "content_digest": row["content_digest"],
                "byte_size": int(row["byte_size"]),
                "revision": int(row["revision"]),
                "incarnation": row["incarnation"],
                "content_json": row["content_json"],
                "provenance_json": row["provenance_json"],
            }
            for row in sorted(rows, key=lambda item: str(item["value_id"]))
        )


def _project_metadata(resolved_schema: str) -> Any:
    from sqlalchemy import MetaData

    return MetaData(schema=resolved_schema)


def _cli_rebuild(args: argparse.Namespace) -> dict[str, Any]:
    from app.successor_runtime.runtime.ports import ProjectScopeRef

    scope = RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=args.project_key,
            resolved_schema=args.resolved_schema,
            project_registry_revision=args.registry_revision,
            incarnation=args.incarnation,
            scope_digest=args.scope_digest,
        ),
        actor_id="server:c9-projection-rebuild",
    )
    validate_project_scope_ref(scope.project_scope)
    key = ProjectionOffsetKey(
        projector_id=args.projector_id,
        projector_version=args.projector_version,
        source_kind=args.source_kind,
        source_ref=args.source_ref,
        source_incarnation=args.source_incarnation,
    )
    engine: Engine = create_runtime_engine(args.database_url, pool_pre_ping=False)
    try:
        with engine.begin() as connection:
            rebuilder = PostgresC9ProjectionRebuilder(connection, scope)
            if args.mode == "rebuild":
                outcome = rebuilder.rebuild(
                    key=key,
                    source_revision=args.source_revision,
                    source_digest=args.source_digest,
                    source_ref=args.source_ref,
                )
                return {
                    "rebuild_id": outcome.rebuild_id,
                    "generation_activated": outcome.generation_activated,
                    "generation": outcome.generation,
                    "repair_refs": list(outcome.repair_refs),
                }
            if args.mode == "readback":
                return dict(rebuilder.readback(key))
            raise ValueError(f"unknown mode {args.mode!r}")
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="C9 projection generation/rebuild over existing P0-D substrate"
    )
    parser.add_argument("--mode", choices=("rebuild", "readback"), required=True)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("SUCCESSOR_TEST_DATABASE_URL", ""),
    )
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--resolved-schema", required=True)
    parser.add_argument("--registry-revision", type=int, default=1)
    parser.add_argument("--incarnation", required=True)
    parser.add_argument("--scope-digest", required=True)
    parser.add_argument("--projector-id", required=True)
    parser.add_argument("--projector-version", default="1")
    parser.add_argument("--source-kind", default=C9_SOURCE_KIND)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-incarnation", required=True)
    parser.add_argument("--source-revision", type=int, required=True)
    parser.add_argument("--source-digest", required=True)
    args = parser.parse_args()
    if not args.database_url:
        print("SUCCESSOR_TEST_DATABASE_URL is required", file=sys.stderr)
        return 2
    try:
        print(repr(_cli_rebuild(args)))
    except Exception as exc:  # noqa: BLE001 - CLI fail closed
        print(f"c9 projection rebuild failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
