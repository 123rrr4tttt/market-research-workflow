"""C9 projection semantic-source effect readers and exact persistence.

This module is the only PostgreSQL effect boundary for the pure C9 typed
source vocabulary defined in ``substrate/projections/c9_sources.py``.  It
never redefines source/segment/closure dataclasses; every reader returns the
pure ``RuntimeSessionSourceV1``, ``ResearchGraphSourceV1`` or
``C7SearchSourceV1`` value, and ``build_semantic_source_closure`` returns the
pure ``C9SemanticSourceClosureV1``.

The readers fill the actual semantic fields from canonical tables:

- runtime session: ``runtime_runs`` identity plus ordered ``runtime_events``;
- research graph: project ``research_objects`` and ``research_relations``;
- C7 search: ``c7_movement_canonical_documents`` mapped to searchable
  segments with explicit field paths and ``NOT_EXECUTED`` provider/vector
  statuses.

Persistence reuses the existing ``successor_values`` project table through
:class:`ValueRepository`.  Each closure writes three content/revision/
incarnation-bound immutable typed source rows plus one immutable closure
manifest row; value ids are never reused for different exact content, so a
legal Research Ledger advance writes new rows instead of conflicting with the
fixed identity.  The public ``runtime_projection_offsets`` table is the
canonical project-scoped current-closure pointer: it stores only closure
facts (revision, digest, manifest ref) and is advanced with an exact CAS, so
the public plane never becomes a payload truth source.  ``load_exact`` reads
the current pointer, re-derives every immutable row, and compares the result
with a freshly built live closure, so event gaps, incarnation drift, byte
drift, wrong types, duplicate component identities, provenance drift, ABA
reversion and cross-project drift all fail closed.  Legacy tables are never
read.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.ingest_c7_candidate_values import (
    C7_STRUCTURED_VALUE_CODEC_ID,
    C7_STRUCTURED_VALUE_OBJECT_TYPE,
    C7_STRUCTURED_VALUE_STATE,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
)
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
    ProjectionOffsetRepository,
)
from app.successor_runtime.substrate.postgres.research_ledger import (
    ExactContentConflict,
    ProjectCASConflict,
    ProjectRecordNotFound,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    StaleRevisionError,
    _mapping_rows,
    _one_mapping,
    _scope_key,
    _table,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository
from app.successor_runtime.substrate.projections import c9_sources as c9

__all__ = [
    "C7_SEARCH_SOURCE_OBJECT_TYPE",
    "C9_CLOSURE_MANIFEST_OBJECT_TYPE",
    "C9_SOURCE_CODEC_ID",
    "C9_SOURCE_CONTRACT_REF",
    "C9_SOURCE_VALUE_ID_PREFIX",
    "C9_TYPED_SOURCE_PROJECTOR_ID",
    "RESEARCH_GRAPH_SOURCE_OBJECT_TYPE",
    "RUNTIME_SESSION_SOURCE_OBJECT_TYPE",
    "C9ProjectionSourceError",
    "C9SourceClosureDriftError",
    "C9SourceDuplicateComponentError",
    "C9SourceEventGapError",
    "C9SourceMissingRowError",
    "C9SourceProvenanceDriftError",
    "C9SourceStaleClosureError",
    "C9SourceTypeDriftError",
    "C9SourceUnavailableError",
    "C9SourceValueConflictError",
    "SemanticSourcePutResult",
    "build_semantic_source_closure",
    "load_exact_semantic_source_closure",
    "put_semantic_source_rows",
    "read_c7_search_source",
    "read_research_graph_source",
    "read_runtime_session_source",
]

C9_SOURCE_CONTRACT_REF = c9.C9_SOURCES_CONTRACT
C9_SOURCE_CODEC_ID = "mrw.successor.c9.typed-source.canonical-json.v1"
C9_SOURCE_VALUE_ID_PREFIX = "c9:semantic-source"
C9_CLOSURE_MANIFEST_SCHEMA = "mrw.successor.c9.semantic-source-closure-manifest.v1"
C9_CLOSURE_MANIFEST_OBJECT_TYPE = "C9SemanticSourceClosureManifest.v1"
C9_CLOSURE_MANIFEST_KIND = "closure_manifest"
C9_TYPED_SOURCE_PROJECTOR_ID = "projection.c9-typed-source-identity.v1"
C9_TYPED_SOURCE_PROJECTOR_VERSION = "1.0.0"
C9_SEMANTIC_SOURCE_KIND = "c9_semantic_source"

RUNTIME_SESSION_SOURCE_OBJECT_TYPE = c9.RUNTIME_SESSION_SOURCE_SCHEMA
RESEARCH_GRAPH_SOURCE_OBJECT_TYPE = c9.RESEARCH_GRAPH_SOURCE_SCHEMA
C7_SEARCH_SOURCE_OBJECT_TYPE = c9.C7_SEARCH_SOURCE_SCHEMA

_SOURCE_OBJECT_TYPES: dict[str, str] = {
    "runtime_session": RUNTIME_SESSION_SOURCE_OBJECT_TYPE,
    "research_graph": RESEARCH_GRAPH_SOURCE_OBJECT_TYPE,
    "c7_search": C7_SEARCH_SOURCE_OBJECT_TYPE,
}


class C9ProjectionSourceError(RuntimeError):
    """Base fail-closed error for C9 projection semantic sources."""


class C9SourceEventGapError(C9ProjectionSourceError):
    """Runtime event sequences are not contiguous from one."""


class C9SourceDuplicateComponentError(C9ProjectionSourceError):
    """The same component identity appears more than once in a source."""


class C9SourceClosureDriftError(C9ProjectionSourceError):
    """A source table changed after the exact closure was persisted."""


class C9SourceMissingRowError(C9ProjectionSourceError):
    """A typed source row is missing from the exact store."""


class C9SourceTypeDriftError(C9ProjectionSourceError):
    """A persisted C9 value row is not the exact typed source row."""


class C9SourceProvenanceDriftError(C9ProjectionSourceError):
    """Persisted provenance does not match the exact closure identity."""


class C9SourceUnavailableError(C9ProjectionSourceError):
    """A typed source has no searchable canonical content."""


class C9SourceValueConflictError(C9ProjectionSourceError):
    """A successor value already holds different exact content."""


class C9SourceStaleClosureError(C9ProjectionSourceError):
    """A persisted closure is older than the newly observed source state."""


@dataclass(frozen=True, slots=True)
class SemanticSourcePutResult:
    changed: bool
    closure_digest: str
    value_ids: tuple[str, ...]
    manifest_value_id: str = ""
    pointer_ref: str = ""


def _source_ref(project_key: str) -> str:
    return f"{C9_SOURCE_VALUE_ID_PREFIX}:{project_key}"


def _manifest_source_ref(project_key: str) -> str:
    return f"{_source_ref(project_key)}:{C9_CLOSURE_MANIFEST_KIND}"


def _closure_incarnation(digest: str) -> str:
    return f"c9:semantic-source:{digest[:32]}"


def _versioned_value_id(
    project_key: str,
    source_kind: str,
    closure: c9.C9SemanticSourceClosureV1,
) -> str:
    """Return a content/revision/incarnation-bound, never-reused value id."""

    return (
        f"{_source_ref(project_key)}:{source_kind}:"
        f"rev-{closure.revision}:{closure.closure_digest[:24]}"
    )


def _manifest_value_id(
    project_key: str,
    closure: c9.C9SemanticSourceClosureV1,
) -> str:
    return (
        f"{_manifest_source_ref(project_key)}:"
        f"rev-{closure.revision}:{closure.closure_digest[:24]}"
    )


def _closure_pointer_key(
    scope: RuntimeScope,
    closure_id: str,
) -> ProjectionOffsetKey:
    return ProjectionOffsetKey(
        projector_id=C9_TYPED_SOURCE_PROJECTOR_ID,
        projector_version=C9_TYPED_SOURCE_PROJECTOR_VERSION,
        source_kind=C9_SEMANTIC_SOURCE_KIND,
        source_ref=closure_id,
        source_incarnation=scope.project_scope.incarnation,
    )


def _require_contiguous_event_sequences(
    events: Sequence[Mapping[str, Any]],
) -> None:
    sequences = sorted(int(event["seq"]) for event in events)
    expected = 1
    for sequence in sequences:
        if sequence != expected:
            raise C9SourceEventGapError(
                f"runtime event sequence gap: expected {expected}, found {sequence}"
            )
        expected += 1


def _event_kind(event_type: str) -> str:
    if event_type in c9.RUNTIME_EVENT_KINDS:
        return event_type
    return c9.SESSION_PROJECTION_REFRESHED


def _event_ref(row: Mapping[str, Any], sequence: int) -> str:
    if row.get("payload_ref"):
        return str(row["payload_ref"])
    return f"runtime-run:{row['run_id']}:event:{sequence}"


def _event_note(row: Mapping[str, Any]) -> str:
    metadata = dict(row.get("event_metadata_json") or {})
    if row.get("payload_digest"):
        metadata["payload_digest"] = str(row["payload_digest"])
    if row.get("authority_digest"):
        metadata["authority_digest"] = str(row["authority_digest"])
    if not metadata:
        return ""
    return json.dumps(metadata, sort_keys=True, separators=(",", ":"))


def _event_digest(row: Mapping[str, Any]) -> str:
    if row.get("payload_digest"):
        return str(row["payload_digest"])
    return str(row["authority_digest"])


def _session_events(
    events: Sequence[Mapping[str, Any]],
) -> tuple[c9.RuntimeSessionEventV1, ...]:
    _require_contiguous_event_sequences(events)
    return tuple(
        c9.RuntimeSessionEventV1(
            schema_version=c9.RUNTIME_SESSION_EVENT_SCHEMA,
            sequence=int(row["seq"]),
            event_kind=_event_kind(str(row["event_type"])),
            event_ref=_event_ref(row, int(row["seq"])),
            event_note=_event_note(row),
        )
        for row in sorted(events, key=lambda item: int(item["seq"]))
    )


def _empty_session_event(project_key: str) -> c9.RuntimeSessionEventV1:
    return c9.RuntimeSessionEventV1(
        schema_version=c9.RUNTIME_SESSION_EVENT_SCHEMA,
        sequence=0,
        event_kind=c9.SESSION_CREATED,
        event_ref=f"project:{project_key}:runtime-session:no-events",
        event_note="no successor runtime events observed",
    )


def read_runtime_session_source(
    connection: Connection,
    scope: RuntimeScope,
) -> c9.RuntimeSessionSourceV1:
    """Read the successor runtime run/events as the pure session source."""

    project_key = _scope_key(scope)
    runs = _mapping_rows(
        connection.execute(
            select(_table("runtime_runs")).where(
                _table("runtime_runs").c.project_key == project_key
            )
        )
    )
    events = _mapping_rows(
        connection.execute(
            select(_table("runtime_events"))
            .where(_table("runtime_events").c.project_key == project_key)
            .order_by(_table("runtime_events").c.seq)
        )
    )
    if not runs:
        raise C9SourceMissingRowError(
            f"runtime session source requires runtime_runs row: {project_key}"
        )
    run = runs[0]
    session_events = _session_events(events)
    if not session_events:
        session_events = (_empty_session_event(project_key),)
    return c9.RuntimeSessionSourceV1(
        schema_version=c9.RUNTIME_SESSION_SOURCE_SCHEMA,
        project_scope_ref=scope.project_scope.scope_digest,
        session_ref=f"run:{run['run_id']}",
        revision=str(run["revision"]),
        incarnation=scope.project_scope.incarnation,
        events=session_events,
    )


def _graph_objects(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[c9.ResearchGraphObjectV1, ...]:
    seen: set[str] = set()
    objects: list[c9.ResearchGraphObjectV1] = []
    for row in rows:
        object_id = str(row["object_id"])
        if object_id in seen:
            raise C9SourceDuplicateComponentError(
                f"duplicate research graph object {object_id}"
            )
        seen.add(object_id)
        label = str(row["content_ref"] or row["content_digest"] or object_id)
        objects.append(
            c9.ResearchGraphObjectV1(
                schema_version=c9.RESEARCH_GRAPH_OBJECT_SCHEMA,
                object_id=object_id,
                object_type=str(row["object_type"]),
                label=label,
            )
        )
    return tuple(objects)


def _graph_relations(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[c9.ResearchGraphRelationV1, ...]:
    seen: set[str] = set()
    relations: list[c9.ResearchGraphRelationV1] = []
    for row in rows:
        relation_id = str(row["relation_id"])
        if relation_id in seen:
            raise C9SourceDuplicateComponentError(
                f"duplicate research graph relation {relation_id}"
            )
        seen.add(relation_id)
        relations.append(
            c9.ResearchGraphRelationV1(
                schema_version=c9.RESEARCH_GRAPH_RELATION_SCHEMA,
                relation_id=relation_id,
                relation_type=str(row["relation_type"]),
                source_object_id=str(row["source_object_ref"]),
                target_object_id=str(row["target_object_ref"]),
                occurrence_ref=str(row["scope_ref"] or relation_id),
            )
        )
    return tuple(relations)


def read_research_graph_source(
    connection: Connection,
    scope: RuntimeScope,
) -> c9.ResearchGraphSourceV1:
    """Read project Research Ledger objects/relations as the pure graph source."""

    project_key = _scope_key(scope)
    run = _one_mapping(
        connection.execute(
            select(_table("runtime_runs")).where(
                _table("runtime_runs").c.project_key == project_key
            )
        )
    )
    if run is None:
        raise C9SourceMissingRowError(
            f"research graph source requires runtime_runs row: {project_key}"
        )
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    objects = _mapping_rows(
        connection.execute(
            select(tables.research_objects)
            .where(tables.research_objects.c.project_key == project_key)
            .order_by(tables.research_objects.c.object_id)
        )
    )
    relations = _mapping_rows(
        connection.execute(
            select(tables.research_relations)
            .where(tables.research_relations.c.project_key == project_key)
            .order_by(tables.research_relations.c.relation_id)
        )
    )
    return c9.ResearchGraphSourceV1(
        schema_version=c9.RESEARCH_GRAPH_SOURCE_SCHEMA,
        project_scope_ref=scope.project_scope.scope_digest,
        graph_ref=f"project:{project_key}:research-graph",
        revision=str(run["revision"]),
        incarnation=scope.project_scope.incarnation,
        objects=_graph_objects(objects),
        relations=_graph_relations(relations),
    )


_SEARCHABLE_FIELDS = frozenset(
    {
        "body",
        "text",
        "title",
        "summary",
        "language",
        "source_domain",
        "effective_time",
    }
)


def _require_head_value_binding(
    connection: Connection,
    scope: RuntimeScope,
    head: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Re-read the exact C7 structured value and bind it to the canonical head."""

    value_ref = str(head["value_ref"])
    prefix = "project-value:"
    if not value_ref.startswith(prefix):
        raise C9SourceProvenanceDriftError(
            "C7 canonical head value_ref is not a project-value ref"
        )
    value_id = value_ref[len(prefix) :]
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    row = _one_mapping(
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key == _scope_key(scope),
                tables.successor_values.c.value_id == value_id,
            )
        )
    )
    if row is None:
        raise C9SourceMissingRowError(
            f"C7 structured value not found for head {head['object_id']}"
        )
    checks = (
        ("object_type", row["object_type"], C7_STRUCTURED_VALUE_OBJECT_TYPE),
        ("codec_id", row["codec_id"], C7_STRUCTURED_VALUE_CODEC_ID),
        ("revision", int(row["revision"]), int(head["value_revision"])),
        ("incarnation", row["incarnation"], head["value_incarnation"]),
        ("content_digest", row["content_digest"], head["value_digest"]),
        (
            "provenance_digest",
            row["provenance_digest"],
            head["value_provenance_digest"],
        ),
        ("source_ref", row["source_ref"], head["snapshot_ref"]),
        ("state", row["state"], C7_STRUCTURED_VALUE_STATE),
    )
    for field, stored, expected in checks:
        if str(stored) != str(expected):
            raise C9SourceProvenanceDriftError(
                f"C7 head/value {field} drift for {head['object_id']}"
            )
    content = row["content_json"]
    if not isinstance(content, dict):
        raise C9SourceTypeDriftError(
            f"C7 structured value {value_id} is not stored as content_json"
        )
    if hashlib.sha256(canonical_bytes(content)).hexdigest() != str(
        row["content_digest"]
    ):
        raise C9SourceClosureDriftError(f"C7 structured value {value_id} bytes drift")
    provenance = row["provenance_json"]
    if not isinstance(provenance, dict) or set(provenance) != {
        "provenance_closure_digest"
    }:
        raise C9SourceProvenanceDriftError(
            f"C7 structured value {value_id} provenance record drift"
        )
    if str(provenance["provenance_closure_digest"]) != str(row["provenance_digest"]):
        raise C9SourceProvenanceDriftError(
            f"C7 structured value {value_id} provenance digest drift"
        )
    return content


def _field_segments(
    value: Any,
    *,
    object_id: str,
    path: str,
) -> tuple[c9.C7SearchSegmentV1, ...]:
    if isinstance(value, Mapping):
        segments: list[c9.C7SearchSegmentV1] = []
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            segments.extend(
                _field_segments(
                    item,
                    object_id=object_id,
                    path=child_path,
                )
            )
        return tuple(segments)
    if isinstance(value, list):
        segments = []
        for index, item in enumerate(value):
            segments.extend(
                _field_segments(
                    item,
                    object_id=object_id,
                    path=f"{path}[{index}]",
                )
            )
        return tuple(segments)
    if isinstance(value, str):
        leaf = path.rsplit(".", 1)[-1].split("[", 1)[0]
        if leaf not in _SEARCHABLE_FIELDS or not value.strip():
            return ()
        return (
            c9.C7SearchSegmentV1(
                schema_version=c9.C7_SEARCH_SEGMENT_SCHEMA,
                segment_id=f"document:{object_id}:{path}",
                field_path=path,
                segment_text=value,
                segment_kind=c9.C7_SEGMENT_KIND_TEXT,
            ),
        )
    return ()


def _document_segments(
    connection: Connection,
    scope: RuntimeScope,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[c9.C7SearchSegmentV1, ...]:
    seen: set[str] = set()
    segments: list[c9.C7SearchSegmentV1] = []
    for row in rows:
        object_id = str(row["object_id"])
        if object_id in seen:
            raise C9SourceDuplicateComponentError(
                f"duplicate C7 canonical document {object_id}"
            )
        seen.add(object_id)
        payload = _require_head_value_binding(connection, scope, row)
        segments.extend(
            _field_segments(
                payload,
                object_id=object_id,
                path="structured_payload",
            )
        )
    return tuple(segments)


def read_c7_search_source(
    connection: Connection,
    scope: RuntimeScope,
) -> c9.C7SearchSourceV1:
    """Read C7 canonical documents as the pure search source segments."""

    project_key = _scope_key(scope)
    run = _one_mapping(
        connection.execute(
            select(_table("runtime_runs")).where(
                _table("runtime_runs").c.project_key == project_key
            )
        )
    )
    if run is None:
        raise C9SourceMissingRowError(
            f"C7 search source requires runtime_runs row: {project_key}"
        )
    documents = _mapping_rows(
        connection.execute(
            select(C7_MOVEMENT_CANONICAL_DOCUMENTS)
            .where(C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == project_key)
            .order_by(C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id)
        )
    )
    segments = _document_segments(connection, scope, documents)
    if not segments:
        raise C9SourceUnavailableError(
            "C7 search source has no searchable structured payload fields"
        )
    return c9.C7SearchSourceV1(
        schema_version=c9.C7_SEARCH_SOURCE_SCHEMA,
        project_scope_ref=scope.project_scope.scope_digest,
        search_ref=f"project:{project_key}:c7-search",
        revision=str(run["revision"]),
        incarnation=scope.project_scope.incarnation,
        segments=segments,
    )


def build_semantic_source_closure(
    connection: Connection,
    scope: RuntimeScope,
) -> c9.C9SemanticSourceClosureV1:
    """Build the pure three-source semantic closure for one project."""

    runtime_session = read_runtime_session_source(connection, scope)
    research_graph = read_research_graph_source(connection, scope)
    c7_search = read_c7_search_source(connection, scope)
    revision = runtime_session.revision
    incarnation = runtime_session.incarnation
    return c9.C9SemanticSourceClosureV1(
        schema_version=c9.C9_SEMANTIC_SOURCE_CLOSURE_SCHEMA,
        project_scope_ref=scope.project_scope.scope_digest,
        closure_id=f"project:{_scope_key(scope)}:semantic-sources",
        revision=revision,
        incarnation=incarnation,
        runtime_session_source=runtime_session,
        research_graph_source=research_graph,
        c7_search_source=c7_search,
    )


def _provenance(
    closure: c9.C9SemanticSourceClosureV1,
    source_kind: str,
    source_ref: str,
) -> dict[str, str]:
    return {
        "contract_ref": C9_SOURCE_CONTRACT_REF,
        "project_key": closure.project_scope_ref,
        "source_ref": source_ref,
        "incarnation": closure.incarnation,
        "source_kind": source_kind,
        "closure_digest": closure.closure_digest,
    }


def _manifest_provenance(
    closure: c9.C9SemanticSourceClosureV1,
    source_ref: str,
) -> dict[str, str]:
    return {
        "contract_ref": C9_SOURCE_CONTRACT_REF,
        "project_key": closure.project_scope_ref,
        "source_ref": source_ref,
        "incarnation": closure.incarnation,
        "source_kind": C9_CLOSURE_MANIFEST_KIND,
        "closure_digest": closure.closure_digest,
    }


def _manifest_content(
    scope: RuntimeScope,
    closure: c9.C9SemanticSourceClosureV1,
    value_ids: Mapping[str, str],
) -> dict[str, Any]:
    if set(value_ids) != set(_SOURCE_OBJECT_TYPES):
        raise C9SourceProvenanceDriftError(
            "closure manifest must reference exactly the three typed sources"
        )
    return {
        "schema_version": C9_CLOSURE_MANIFEST_SCHEMA,
        "contract_ref": C9_SOURCE_CONTRACT_REF,
        "project_key": _scope_key(scope),
        "project_scope_ref": scope.project_scope.scope_digest,
        "closure_id": closure.closure_id,
        "revision": closure.revision,
        "incarnation": closure.incarnation,
        "closure_digest": closure.closure_digest,
        "sources": dict(sorted(value_ids.items())),
    }


def _persist_current_pointer(
    connection: Connection,
    scope: RuntimeScope,
    closure: c9.C9SemanticSourceClosureV1,
    manifest_value_id: str,
) -> Mapping[str, Any] | None:
    """Create or CAS-advance the project-scoped exact current-closure pointer."""

    key = _closure_pointer_key(scope, closure.closure_id)
    offsets = ProjectionOffsetRepository(connection, scope)
    current = offsets.load_source(key)
    if current is not None:
        if (
            str(current["source_digest"]) == closure.closure_digest
            and str(current["offset_ref"]) == manifest_value_id
            and int(current["source_revision"]) == int(closure.revision)
        ):
            return None
        return offsets.advance(
            str(current["projection_offset_id"]),
            key=key,
            expected_revision=int(current["revision"]),
            expected_generation=int(current["projection_generation"]),
            expected_source_revision=int(current["source_revision"]),
            expected_source_digest=str(current["source_digest"]),
            source_revision=int(closure.revision),
            source_digest=closure.closure_digest,
            offset_ref=manifest_value_id,
        )
    return offsets.create(
        projection_offset_id=f"c9:semantic-source:{_scope_key(scope)}:current",
        key=key,
        projection_generation=0,
        source_revision=int(closure.revision),
        source_digest=closure.closure_digest,
        offset_ref=manifest_value_id,
    )


def put_semantic_source_rows(
    connection: Connection,
    scope: RuntimeScope,
    closure: c9.C9SemanticSourceClosureV1,
) -> SemanticSourcePutResult:
    """Persist versioned typed sources, a closure manifest and current pointer."""

    project_key = _scope_key(scope)
    expected_closure_id = f"project:{project_key}:semantic-sources"
    if closure.closure_id != expected_closure_id:
        raise C9SourceProvenanceDriftError(
            "closure identity does not match the RuntimeScope project"
        )
    if closure.project_scope_ref != scope.project_scope.scope_digest:
        raise C9SourceProvenanceDriftError(
            "closure scope ref does not match the RuntimeScope"
        )
    if closure.incarnation != scope.project_scope.incarnation:
        raise C9SourceProvenanceDriftError(
            "closure incarnation does not match the RuntimeScope"
        )
    source_ref = _source_ref(project_key)
    sources = (
        ("runtime_session", closure.runtime_session_source),
        ("research_graph", closure.research_graph_source),
        ("c7_search", closure.c7_search_source),
    )
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    repository = ValueRepository(connection, tables)
    incarnation = _closure_incarnation(closure.closure_digest)
    value_ids: list[str] = []
    changed = False
    try:
        for source_kind, source in sources:
            value_id = _versioned_value_id(project_key, source_kind, closure)
            value_ids.append(value_id)
            content = source.to_plain()
            content_digest_value = hashlib.sha256(canonical_bytes(content)).hexdigest()
            existing = _one_mapping(
                connection.execute(
                    select(tables.successor_values).where(
                        tables.successor_values.c.project_key == project_key,
                        tables.successor_values.c.value_id == value_id,
                    )
                )
            )
            if existing is not None:
                if str(existing["object_type"]) != _SOURCE_OBJECT_TYPES[source_kind]:
                    raise C9SourceTypeDriftError(
                        f"existing value {value_id} is not a C9 typed source row"
                    )
                if str(existing["content_digest"]) != content_digest_value:
                    raise C9SourceValueConflictError(
                        f"existing value {value_id} holds different exact content"
                    )
            repository.put_exact(
                scope,
                value_id=value_id,
                object_type=_SOURCE_OBJECT_TYPES[source_kind],
                codec_id=C9_SOURCE_CODEC_ID,
                content=content,
                expected_digest=content_digest_value,
                provenance_digest=hashlib.sha256(
                    canonical_bytes(_provenance(closure, source_kind, source_ref))
                ).hexdigest(),
                expected_revision=0,
                expected_incarnation=incarnation,
                source_ref=source_ref,
                provenance=_provenance(closure, source_kind, source_ref),
                state="AVAILABLE",
            )
            if existing is None:
                changed = True
        manifest_value_id = _manifest_value_id(project_key, closure)
        manifest = _manifest_content(
            scope,
            closure,
            {
                source_kind: value_id
                for (source_kind, _source), value_id in zip(sources, value_ids)
            },
        )
        manifest_digest = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
        manifest_source_ref = _manifest_source_ref(project_key)
        existing_manifest = _one_mapping(
            connection.execute(
                select(tables.successor_values).where(
                    tables.successor_values.c.project_key == project_key,
                    tables.successor_values.c.value_id == manifest_value_id,
                )
            )
        )
        if existing_manifest is not None:
            if str(existing_manifest["object_type"]) != C9_CLOSURE_MANIFEST_OBJECT_TYPE:
                raise C9SourceTypeDriftError(
                    f"existing value {manifest_value_id} is not a C9 closure manifest"
                )
            if str(existing_manifest["content_digest"]) != manifest_digest:
                raise C9SourceValueConflictError(
                    f"existing value {manifest_value_id} holds different exact content"
                )
        repository.put_exact(
            scope,
            value_id=manifest_value_id,
            object_type=C9_CLOSURE_MANIFEST_OBJECT_TYPE,
            codec_id=C9_SOURCE_CODEC_ID,
            content=manifest,
            expected_digest=manifest_digest,
            provenance_digest=hashlib.sha256(
                canonical_bytes(_manifest_provenance(closure, manifest_source_ref))
            ).hexdigest(),
            expected_revision=0,
            expected_incarnation=incarnation,
            source_ref=manifest_source_ref,
            provenance=_manifest_provenance(closure, manifest_source_ref),
            state="AVAILABLE",
        )
        if existing_manifest is None:
            changed = True
        pointer = _persist_current_pointer(
            connection,
            scope,
            closure,
            manifest_value_id,
        )
        if pointer is not None:
            changed = True
    except (ExactContentConflict, ProjectCASConflict, ProjectRecordNotFound) as exc:
        raise C9SourceValueConflictError(str(exc)) from exc
    except (ExactBindingConflict, StaleRevisionError) as exc:
        raise C9SourceValueConflictError(str(exc)) from exc
    return SemanticSourcePutResult(
        changed=changed,
        closure_digest=closure.closure_digest,
        value_ids=tuple(value_ids),
        manifest_value_id=manifest_value_id,
        pointer_ref=(
            str(pointer["offset_ref"]) if pointer is not None else manifest_value_id
        ),
    )


def _source_from_plain(
    object_type: str,
    plain: Mapping[str, Any],
) -> c9.RuntimeSessionSourceV1 | c9.ResearchGraphSourceV1 | c9.C7SearchSourceV1:
    stripped = {
        key: value
        for key, value in dict(plain).items()
        if key not in {"source_digest", "closure_ref"}
    }
    if object_type == RUNTIME_SESSION_SOURCE_OBJECT_TYPE:
        events = tuple(
            c9.RuntimeSessionEventV1(
                schema_version=str(event["schema_version"]),
                sequence=int(event["sequence"]),
                event_kind=str(event["event_kind"]),
                event_ref=str(event["event_ref"]),
                event_note=str(event["event_note"]),
                event_digest=str(event["event_digest"]),
            )
            for event in stripped["events"]
        )
        return c9.RuntimeSessionSourceV1(
            schema_version=c9.RUNTIME_SESSION_SOURCE_SCHEMA,
            project_scope_ref=str(stripped["project_scope_ref"]),
            session_ref=str(stripped["session_ref"]),
            revision=str(stripped["revision"]),
            incarnation=str(stripped["incarnation"]),
            events=events,
            coverage_incomplete_flags=tuple(stripped["coverage_incomplete_flags"]),
        )
    if object_type == RESEARCH_GRAPH_SOURCE_OBJECT_TYPE:
        objects = tuple(
            c9.ResearchGraphObjectV1(
                schema_version=str(item["schema_version"]),
                object_id=str(item["object_id"]),
                object_type=str(item["object_type"]),
                label=str(item["label"]),
                object_digest=str(item["object_digest"]),
            )
            for item in stripped["objects"]
        )
        relations = tuple(
            c9.ResearchGraphRelationV1(
                schema_version=str(item["schema_version"]),
                relation_id=str(item["relation_id"]),
                relation_type=str(item["relation_type"]),
                source_object_id=str(item["source_object_id"]),
                target_object_id=str(item["target_object_id"]),
                occurrence_ref=str(item["occurrence_ref"]),
                relation_digest=str(item["relation_digest"]),
            )
            for item in stripped["relations"]
        )
        return c9.ResearchGraphSourceV1(
            schema_version=c9.RESEARCH_GRAPH_SOURCE_SCHEMA,
            project_scope_ref=str(stripped["project_scope_ref"]),
            graph_ref=str(stripped["graph_ref"]),
            revision=str(stripped["revision"]),
            incarnation=str(stripped["incarnation"]),
            objects=objects,
            relations=relations,
            coverage_incomplete_flags=tuple(stripped["coverage_incomplete_flags"]),
        )
    if object_type == C7_SEARCH_SOURCE_OBJECT_TYPE:
        segments = tuple(
            c9.C7SearchSegmentV1(
                schema_version=str(item["schema_version"]),
                segment_id=str(item["segment_id"]),
                field_path=str(item["field_path"]),
                segment_text=str(item["segment_text"]),
                segment_kind=str(item["segment_kind"]),
                length_bytes=int(item["length_bytes"]),
                provider_status=str(item["provider_status"]),
                vectorization_status=str(item["vectorization_status"]),
                segment_digest=str(item["segment_digest"]),
            )
            for item in stripped["segments"]
        )
        return c9.C7SearchSourceV1(
            schema_version=c9.C7_SEARCH_SOURCE_SCHEMA,
            project_scope_ref=str(stripped["project_scope_ref"]),
            search_ref=str(stripped["search_ref"]),
            revision=str(stripped["revision"]),
            incarnation=str(stripped["incarnation"]),
            segments=segments,
            coverage_incomplete_flags=tuple(stripped["coverage_incomplete_flags"]),
        )
    raise C9SourceTypeDriftError(f"unknown C9 source object type {object_type!r}")


def _closure_from_sources(
    project_scope_ref: str,
    closure_id: str,
    revision: str,
    incarnation: str,
    runtime_session: c9.RuntimeSessionSourceV1,
    research_graph: c9.ResearchGraphSourceV1,
    c7_search: c9.C7SearchSourceV1,
) -> c9.C9SemanticSourceClosureV1:
    return c9.C9SemanticSourceClosureV1(
        schema_version=c9.C9_SEMANTIC_SOURCE_CLOSURE_SCHEMA,
        project_scope_ref=project_scope_ref,
        closure_id=closure_id,
        revision=revision,
        incarnation=incarnation,
        runtime_session_source=runtime_session,
        research_graph_source=research_graph,
        c7_search_source=c7_search,
    )


def _value_row(
    connection: Connection,
    scope: RuntimeScope,
    *,
    source_kind: str,
    value_id: str,
) -> Mapping[str, Any]:
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    row = _one_mapping(
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key == _scope_key(scope),
                tables.successor_values.c.value_id == value_id,
            )
        )
    )
    if row is None:
        raise C9SourceMissingRowError(f"missing exact C9 source row {source_kind}")
    return row


def _manifest_row(
    connection: Connection,
    scope: RuntimeScope,
    *,
    value_id: str,
    closure_digest: str,
) -> Mapping[str, Any]:
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    project_key = _scope_key(scope)
    row = _one_mapping(
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key == project_key,
                tables.successor_values.c.value_id == value_id,
            )
        )
    )
    if row is None:
        raise C9SourceMissingRowError(f"missing exact C9 closure manifest {value_id}")
    if str(row["object_type"]) != C9_CLOSURE_MANIFEST_OBJECT_TYPE:
        raise C9SourceTypeDriftError(
            f"stored value {row['value_id']} is not a C9 closure manifest row"
        )
    if str(row["source_ref"]) != _manifest_source_ref(project_key):
        raise C9SourceProvenanceDriftError(
            f"stored manifest {row['value_id']} source_ref drift"
        )
    if str(row["incarnation"]) != _closure_incarnation(closure_digest):
        raise C9SourceStaleClosureError(
            f"stored manifest {row['value_id']} incarnation drift"
        )
    content = row["content_json"]
    if not isinstance(content, dict):
        raise C9SourceTypeDriftError(
            f"stored manifest {row['value_id']} is not content_json"
        )
    if hashlib.sha256(canonical_bytes(content)).hexdigest() != str(
        row["content_digest"]
    ):
        raise C9SourceClosureDriftError(
            f"stored manifest {row['value_id']} bytes drift"
        )
    provenance = row["provenance_json"]
    if (
        not isinstance(provenance, dict)
        or str(provenance.get("closure_digest", "")) != closure_digest
    ):
        raise C9SourceProvenanceDriftError(
            f"stored manifest {row['value_id']} closure digest drift"
        )
    if str(provenance.get("source_kind", "")) != C9_CLOSURE_MANIFEST_KIND:
        raise C9SourceProvenanceDriftError(
            f"stored manifest {row['value_id']} provenance kind drift"
        )
    return row


def _current_pointer_row(
    connection: Connection,
    scope: RuntimeScope,
    *,
    closure_id: str,
) -> Mapping[str, Any]:
    key = _closure_pointer_key(scope, closure_id)
    row = ProjectionOffsetRepository(connection, scope).load_source(key)
    if row is None:
        raise C9SourceMissingRowError(
            f"no current C9 semantic-source pointer for {closure_id}"
        )
    if str(row["source_ref"]) != closure_id:
        raise C9SourceProvenanceDriftError("C9 closure pointer source_ref drift")
    if str(row["source_incarnation"]) != scope.project_scope.incarnation:
        raise C9SourceProvenanceDriftError("C9 closure pointer incarnation drift")
    if str(row["source_kind"]) != C9_SEMANTIC_SOURCE_KIND:
        raise C9SourceProvenanceDriftError("C9 closure pointer source kind drift")
    offset_ref = str(row["offset_ref"])
    manifest_prefix = f"{_manifest_source_ref(_scope_key(scope))}:"
    if not offset_ref.startswith(manifest_prefix):
        raise C9SourceProvenanceDriftError("C9 closure pointer offset_ref drift")
    return row


def load_exact_semantic_source_closure(
    connection: Connection,
    scope: RuntimeScope,
) -> c9.C9SemanticSourceClosureV1:
    """Load the exact persisted pure closure; every drift fails closed."""

    project_key = _scope_key(scope)
    source_ref = _source_ref(project_key)
    closure_id = f"project:{project_key}:semantic-sources"
    pointer = _current_pointer_row(connection, scope, closure_id=closure_id)
    closure_digest = str(pointer["source_digest"])
    closure_revision = int(pointer["source_revision"])
    manifest_value_id = str(pointer["offset_ref"])
    manifest_row = _manifest_row(
        connection,
        scope,
        value_id=manifest_value_id,
        closure_digest=closure_digest,
    )
    manifest = dict(manifest_row["content_json"])
    loaded: dict[str, Any] = {}
    if str(manifest.get("schema_version", "")) != C9_CLOSURE_MANIFEST_SCHEMA:
        raise C9SourceTypeDriftError("stored C9 closure manifest schema drift")
    if str(manifest.get("contract_ref", "")) != C9_SOURCE_CONTRACT_REF:
        raise C9SourceProvenanceDriftError("stored C9 closure manifest contract drift")
    if str(manifest.get("project_key", "")) != project_key:
        raise C9SourceProvenanceDriftError("stored C9 closure manifest project drift")
    if str(manifest.get("project_scope_ref", "")) != scope.project_scope.scope_digest:
        raise C9SourceProvenanceDriftError(
            "stored C9 closure manifest scope digest drift"
        )
    if str(manifest.get("closure_id", "")) != closure_id:
        raise C9SourceProvenanceDriftError(
            "stored C9 closure manifest closure identity drift"
        )
    if str(manifest.get("closure_digest", "")) != closure_digest:
        raise C9SourceClosureDriftError("stored C9 closure manifest digest drift")
    try:
        manifest_revision = int(str(manifest.get("revision", "-1")))
    except (TypeError, ValueError) as exc:
        raise C9SourceProvenanceDriftError(
            "stored C9 closure manifest revision drift"
        ) from exc
    if manifest_revision != closure_revision:
        raise C9SourceProvenanceDriftError("stored C9 closure manifest revision drift")
    if str(manifest.get("incarnation", "")) != scope.project_scope.incarnation:
        raise C9SourceProvenanceDriftError(
            "stored C9 closure manifest incarnation drift"
        )
    manifest_sources = manifest.get("sources")
    if not isinstance(manifest_sources, dict) or set(manifest_sources) != set(
        _SOURCE_OBJECT_TYPES
    ):
        raise C9SourceProvenanceDriftError(
            "stored C9 closure manifest source mapping drift"
        )
    for source_kind, object_type in _SOURCE_OBJECT_TYPES.items():
        value_id = str(manifest_sources[source_kind])
        if not value_id.startswith(f"{source_ref}:"):
            raise C9SourceProvenanceDriftError(
                f"stored C9 closure manifest value id {value_id} is not project-scoped"
            )
        row = _value_row(
            connection,
            scope,
            source_kind=source_kind,
            value_id=value_id,
        )
        if str(row["object_type"]) != object_type:
            raise C9SourceTypeDriftError(
                f"stored value {row['value_id']} is not a C9 typed source row"
            )
        if str(row["source_ref"]) != source_ref:
            raise C9SourceProvenanceDriftError(
                f"stored value {row['value_id']} source_ref drift"
            )
        provenance = dict(row["provenance_json"])
        stored_digest = str(provenance.get("closure_digest", ""))
        if stored_digest != closure_digest:
            raise C9SourceProvenanceDriftError(
                f"stored value {row['value_id']} closure digest drift"
            )
        if str(provenance.get("source_kind", "")) != source_kind:
            raise C9SourceProvenanceDriftError(
                f"stored value {row['value_id']} provenance kind drift"
            )
        if str(row["incarnation"]) != _closure_incarnation(stored_digest):
            raise C9SourceStaleClosureError(
                f"stored value {row['value_id']} incarnation drift"
            )
        content = row["content_json"]
        plain = dict(content) if content is not None else {}
        source = _source_from_plain(object_type, plain)
        if (
            str(row["content_digest"])
            != hashlib.sha256(canonical_bytes(source.to_plain())).hexdigest()
        ):
            raise C9SourceClosureDriftError(
                f"stored value {row['value_id']} content digest drift"
            )
        loaded[source_kind] = source
    closure = _closure_from_sources(
        project_scope_ref=scope.project_scope.scope_digest,
        closure_id=closure_id,
        revision=str(manifest["revision"]),
        incarnation=scope.project_scope.incarnation,
        runtime_session=loaded["runtime_session"],
        research_graph=loaded["research_graph"],
        c7_search=loaded["c7_search"],
    )
    if closure.closure_digest != closure_digest:
        raise C9SourceClosureDriftError(
            "persisted closure digest does not match reconstructed closure"
        )
    for source_kind in _SOURCE_OBJECT_TYPES:
        expected_value_id = _versioned_value_id(
            project_key,
            source_kind,
            closure,
        )
        if str(manifest_sources[source_kind]) != expected_value_id:
            raise C9SourceClosureDriftError(
                f"persisted closure manifest value id {source_kind} drift"
            )
    live = build_semantic_source_closure(connection, scope)
    if live.closure_digest != closure_digest:
        raise C9SourceClosureDriftError(
            "persisted closure digest does not match current source state"
        )
    return closure
