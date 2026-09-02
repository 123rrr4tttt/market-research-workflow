"""C9 pure typed source and projection payload layer.

This module owns the C9-M004 source-bound projection vocabulary for the local
successor milestone: immutable typed AgentSession/graph/search sources, a
semantic source closure, field-level loss records and three semantically
distinct projection payloads.  It is deliberately pure: no network, provider,
database, credential or canonical-write effect exists here.

Contract invariants:

- Runtime session terminal state is derived only from the ordered event chain;
  no terminal field is accepted as source input.
- Research graph payloads map objects and relations one-to-one; a relation may
  only reference object ids present in the same source, so no edge is
  manufactured.
- Search segments carry an explicit field path and provider/vectorization
  status that is always ``NOT_EXECUTED``; no provider identity, model or vector
  field is present.
- Every source and payload carries its family-specific C8 coverage-incomplete
  flag (extra legal flags are allowed but cannot substitute the required one),
  an identity/revision/incarnation closure ref and a canonical content digest.
- Canonical JSON accepts only string keys and finite numbers, sorts keys
  deterministically and never falls back to ``str()`` for unknown values.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "AGENT_SESSION_PROJECTION_PAYLOAD_SCHEMA",
    "C7_SEARCH_SEGMENT_SCHEMA",
    "C7_SEARCH_SOURCE_SCHEMA",
    "C7_SEGMENT_KINDS",
    "C7_SEGMENT_KIND_FIELD",
    "C7_SEGMENT_KIND_TEXT",
    "C8_COVERAGE_INCOMPLETE_FLAGS",
    "C8_COVERAGE_INCOMPLETE_GRAPH",
    "C8_COVERAGE_INCOMPLETE_SEARCH",
    "C8_COVERAGE_INCOMPLETE_SESSION",
    "C9_SEMANTIC_SOURCE_CLOSURE_SCHEMA",
    "C9_SOURCES_CONTRACT",
    "LOSS_KINDS",
    "LOSS_KIND_DECLARED",
    "LOSS_KIND_NOT_EXECUTED",
    "LOSS_KIND_OMITTED_FIELD",
    "NOT_EXECUTED",
    "PROJECTION_FIELD_LOSS_SCHEMA",
    "RESEARCH_GRAPH_OBJECT_SCHEMA",
    "RESEARCH_GRAPH_PROJECTION_PAYLOAD_SCHEMA",
    "RESEARCH_GRAPH_RELATION_SCHEMA",
    "RESEARCH_GRAPH_SOURCE_SCHEMA",
    "RUNTIME_EVENT_KINDS",
    "RUNTIME_SESSION_EVENT_SCHEMA",
    "RUNTIME_SESSION_SOURCE_SCHEMA",
    "RUNTIME_TERMINAL_EVENT_KINDS",
    "SEARCH_PROJECTION_PAYLOAD_SCHEMA",
    "SESSION_STATUSES",
    "SESSION_STATUS_RUNNING",
    "SESSION_STATUS_TERMINAL_FAILED",
    "SESSION_STATUS_TERMINAL_SUCCEEDED",
    "SESSION_STATUS_WAITING",
    "AgentSessionProjectionPayloadV1",
    "C7SearchSegmentV1",
    "C7SearchSourceV1",
    "C9SemanticSourceClosureV1",
    "ProjectionFieldLossV1",
    "ResearchGraphObjectV1",
    "ResearchGraphProjectionPayloadV1",
    "ResearchGraphRelationV1",
    "ResearchGraphSourceV1",
    "RuntimeSessionEventV1",
    "RuntimeSessionSourceV1",
    "SearchProjectionPayloadV1",
    "build_agent_session_payload",
    "build_research_graph_payload",
    "build_search_payload",
    "canonical_json",
    "content_digest",
    "require_hex64",
    "sha256_hex",
]


C9_SOURCES_CONTRACT = "mrw.functorial_successor.c9_typed_sources.pure.v1"

RUNTIME_SESSION_SOURCE_SCHEMA = "mrw.successor.c9.runtime-session-source.v1"
RUNTIME_SESSION_EVENT_SCHEMA = "mrw.successor.c9.runtime-session-event.v1"
RESEARCH_GRAPH_SOURCE_SCHEMA = "mrw.successor.c9.research-graph-source.v1"
RESEARCH_GRAPH_OBJECT_SCHEMA = "mrw.successor.c9.research-graph-object.v1"
RESEARCH_GRAPH_RELATION_SCHEMA = "mrw.successor.c9.research-graph-relation.v1"
C7_SEARCH_SOURCE_SCHEMA = "mrw.successor.c9.c7-search-source.v1"
C7_SEARCH_SEGMENT_SCHEMA = "mrw.successor.c9.c7-search-segment.v1"
C9_SEMANTIC_SOURCE_CLOSURE_SCHEMA = "mrw.successor.c9.semantic-source-closure.v1"
AGENT_SESSION_PROJECTION_PAYLOAD_SCHEMA = (
    "mrw.successor.c9.agent-session-projection-payload.v1"
)
RESEARCH_GRAPH_PROJECTION_PAYLOAD_SCHEMA = (
    "mrw.successor.c9.research-graph-projection-payload.v1"
)
SEARCH_PROJECTION_PAYLOAD_SCHEMA = "mrw.successor.c9.search-projection-payload.v1"
PROJECTION_FIELD_LOSS_SCHEMA = "mrw.successor.c9.projection-field-loss.v1"

NOT_EXECUTED = "NOT_EXECUTED"

SESSION_STATUS_WAITING = "WAITING"
SESSION_STATUS_RUNNING = "RUNNING"
SESSION_STATUS_TERMINAL_SUCCEEDED = "TERMINAL_SUCCEEDED"
SESSION_STATUS_TERMINAL_FAILED = "TERMINAL_FAILED"
SESSION_STATUSES: tuple[str, ...] = (
    SESSION_STATUS_WAITING,
    SESSION_STATUS_RUNNING,
    SESSION_STATUS_TERMINAL_SUCCEEDED,
    SESSION_STATUS_TERMINAL_FAILED,
)

SESSION_CREATED = "SESSION_CREATED"
SESSION_TASK_ASSIGNED = "SESSION_TASK_ASSIGNED"
SESSION_PROJECTION_REFRESHED = "SESSION_PROJECTION_REFRESHED"
SESSION_TERMINAL_SUCCEEDED = "SESSION_TERMINAL_SUCCEEDED"
SESSION_TERMINAL_FAILED = "SESSION_TERMINAL_FAILED"
RUNTIME_EVENT_KINDS: frozenset[str] = frozenset(
    {
        SESSION_CREATED,
        SESSION_TASK_ASSIGNED,
        SESSION_PROJECTION_REFRESHED,
        SESSION_TERMINAL_SUCCEEDED,
        SESSION_TERMINAL_FAILED,
    }
)
RUNTIME_TERMINAL_EVENT_KINDS: frozenset[str] = frozenset(
    {SESSION_TERMINAL_SUCCEEDED, SESSION_TERMINAL_FAILED}
)

C7_SEGMENT_KIND_TEXT = "TEXT_SEGMENT"
C7_SEGMENT_KIND_FIELD = "FIELD_SEGMENT"
C7_SEGMENT_KINDS: frozenset[str] = frozenset(
    {C7_SEGMENT_KIND_TEXT, C7_SEGMENT_KIND_FIELD}
)

LOSS_KIND_DECLARED = "DECLARED_LOSS"
LOSS_KIND_OMITTED_FIELD = "OMITTED_FIELD"
LOSS_KIND_NOT_EXECUTED = "NOT_EXECUTED"
LOSS_KINDS: frozenset[str] = frozenset(
    {LOSS_KIND_DECLARED, LOSS_KIND_OMITTED_FIELD, LOSS_KIND_NOT_EXECUTED}
)

C8_COVERAGE_INCOMPLETE_SESSION = "C8.SESSION_PROJECTION_COVERAGE_INCOMPLETE"
C8_COVERAGE_INCOMPLETE_GRAPH = "C8.GRAPH_PROJECTION_COVERAGE_INCOMPLETE"
C8_COVERAGE_INCOMPLETE_SEARCH = "C8.SEARCH_PROJECTION_COVERAGE_INCOMPLETE"
C8_COVERAGE_INCOMPLETE_FLAGS: tuple[str, ...] = (
    C8_COVERAGE_INCOMPLETE_SESSION,
    C8_COVERAGE_INCOMPLETE_GRAPH,
    C8_COVERAGE_INCOMPLETE_SEARCH,
)


def sha256_hex(data: bytes) -> str:
    """Return the lowercase SHA-256 hex digest of ``data``."""

    return hashlib.sha256(data).hexdigest()


def _canonicalize(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _canonicalize(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {
            _require_string_key(key): _canonicalize(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON rejects non-finite numbers")
        return value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def _require_string_key(key: Any) -> str:
    if not isinstance(key, str):
        raise TypeError("canonical JSON requires string dictionary keys")
    return key


def canonical_json(value: Any) -> str:
    """Serialize ``value`` into deterministic canonical JSON.

    Dictionary keys must be strings, numbers must be finite, unknown object
    types fail closed instead of falling back to ``str()``, and keys are sorted
    so equivalent documents serialize identically.
    """

    return json.dumps(
        _canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_digest(value: Any) -> str:
    """Return the SHA-256 digest of the canonical JSON form of ``value``."""

    return sha256_hex(canonical_json(value).encode("utf-8"))


def require_hex64(value: str, field_name: str) -> str:
    """Fail closed unless ``value`` is a 64-character SHA-256 hex digest."""

    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} must be a 64-character SHA-256 hex digest"
        ) from exc
    return value


def _finite_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be a finite integer")
    return value


def _require_text(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} is required")
    return normalized


def _assign_digest(obj: Any, field_name: str, expected: str) -> None:
    current = getattr(obj, field_name)
    if current == "":
        object.__setattr__(obj, field_name, expected)
        return
    require_hex64(current, f"{type(obj).__name__}.{field_name}")
    if current != expected:
        raise ValueError(f"{type(obj).__name__}.{field_name} does not match content")


def _assign_closure_ref(
    obj: Any,
    field_name: str,
    *,
    identity: str,
    revision: str,
    incarnation: str,
) -> None:
    expected = content_digest(
        {
            "identity": identity,
            "revision": revision,
            "incarnation": incarnation,
        }
    )
    current = getattr(obj, field_name)
    if current == "":
        object.__setattr__(obj, field_name, expected)
        return
    require_hex64(current, f"{type(obj).__name__}.{field_name}")
    if current != expected:
        raise ValueError(
            f"{type(obj).__name__}.{field_name} does not match "
            "identity/revision/incarnation closure"
        )


def _normalize_flags(
    values: Iterable[str],
    field_name: str,
    *,
    allowed: tuple[str, ...] = C8_COVERAGE_INCOMPLETE_FLAGS,
    required_flag: str | None = None,
) -> tuple[str, ...]:
    normalized: list[str] = []
    for item in values or ():
        flag = _require_text(item, field_name)
        if flag not in allowed:
            raise ValueError(f"unsupported coverage flag: {flag}")
        if flag not in normalized:
            normalized.append(flag)
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty; C8 coverage is incomplete")
    if required_flag is not None and required_flag not in normalized:
        raise ValueError(
            f"{field_name} must include required C8 coverage flag {required_flag}"
        )
    return tuple(sorted(normalized))


def _require_required_flag(
    flags: tuple[str, ...],
    required_flag: str,
    label: str,
) -> None:
    if required_flag not in flags:
        raise ValueError(
            f"{label} must include required C8 coverage flag {required_flag}"
        )


def _normalize_losses(
    values: Iterable[ProjectionFieldLossV1] | None,
) -> tuple[ProjectionFieldLossV1, ...]:
    normalized: list[ProjectionFieldLossV1] = []
    for item in values or ():
        if not isinstance(item, ProjectionFieldLossV1):
            raise TypeError("declared losses must be ProjectionFieldLossV1 records")
        normalized.append(item)
    return tuple(normalized)


def _normalize_events(
    values: Iterable[RuntimeSessionEventV1],
    field_name: str,
) -> tuple[RuntimeSessionEventV1, ...]:
    events = tuple(values or ())
    if not events:
        raise ValueError(f"{field_name} requires at least one runtime event")
    for event in events:
        if not isinstance(event, RuntimeSessionEventV1):
            raise TypeError(f"{field_name} entries must be RuntimeSessionEventV1")
    ordered = tuple(sorted(events, key=lambda event: event.sequence))
    for index in range(1, len(ordered)):
        if ordered[index].sequence == ordered[index - 1].sequence:
            raise ValueError("runtime event sequences must be unique")
    terminal = tuple(
        event for event in ordered if event.event_kind in RUNTIME_TERMINAL_EVENT_KINDS
    )
    if len(terminal) > 1:
        raise ValueError("runtime event chain has more than one terminal event")
    if terminal and terminal[0].sequence != ordered[-1].sequence:
        raise ValueError("terminal runtime event must be the last event")
    return ordered


def _normalize_objects(
    values: Iterable[ResearchGraphObjectV1],
    field_name: str,
) -> tuple[ResearchGraphObjectV1, ...]:
    objects = tuple(values or ())
    for obj in objects:
        if not isinstance(obj, ResearchGraphObjectV1):
            raise TypeError(f"{field_name} entries must be ResearchGraphObjectV1")
    ids = [obj.object_id for obj in objects]
    if len(ids) != len(set(ids)):
        raise ValueError("research graph object ids must be unique")
    return objects


def _normalize_relations(
    values: Iterable[ResearchGraphRelationV1],
    field_name: str,
    *,
    object_ids: frozenset[str],
) -> tuple[ResearchGraphRelationV1, ...]:
    relations = tuple(values or ())
    for relation in relations:
        if not isinstance(relation, ResearchGraphRelationV1):
            raise TypeError(f"{field_name} entries must be ResearchGraphRelationV1")
        if relation.source_object_id not in object_ids:
            raise ValueError(
                "relation source object does not exist in the same source: "
                f"{relation.source_object_id}"
            )
        if relation.target_object_id not in object_ids:
            raise ValueError(
                "relation target object does not exist in the same source: "
                f"{relation.target_object_id}"
            )
    ids = [relation.relation_id for relation in relations]
    if len(ids) != len(set(ids)):
        raise ValueError("research graph relation ids must be unique")
    return relations


def _normalize_segments(
    values: Iterable[C7SearchSegmentV1],
    field_name: str,
) -> tuple[C7SearchSegmentV1, ...]:
    segments = tuple(values or ())
    if not segments:
        raise ValueError(f"{field_name} requires at least one search segment")
    for segment in segments:
        if not isinstance(segment, C7SearchSegmentV1):
            raise TypeError(f"{field_name} entries must be C7SearchSegmentV1")
    ids = [segment.segment_id for segment in segments]
    if len(ids) != len(set(ids)):
        raise ValueError("search segment ids must be unique")
    return segments


@dataclass(frozen=True, slots=True)
class RuntimeSessionEventV1:
    """One ordered runtime session event; never a caller-supplied terminal."""

    schema_version: str
    sequence: int
    event_kind: str
    event_ref: str
    event_note: str = ""
    event_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SESSION_EVENT_SCHEMA:
            raise ValueError("RuntimeSessionEventV1.schema_version is not frozen")
        sequence = _finite_int(self.sequence, "RuntimeSessionEventV1.sequence")
        if sequence < 0:
            raise ValueError("RuntimeSessionEventV1.sequence must be non-negative")
        object.__setattr__(self, "sequence", sequence)
        if self.event_kind not in RUNTIME_EVENT_KINDS:
            raise ValueError(f"unsupported runtime event kind: {self.event_kind}")
        object.__setattr__(
            self,
            "event_ref",
            _require_text(self.event_ref, "RuntimeSessionEventV1.event_ref"),
        )
        object.__setattr__(
            self,
            "event_note",
            _require_text(
                self.event_note, "RuntimeSessionEventV1.event_note", allow_empty=True
            ),
        )
        _assign_digest(
            self,
            "event_digest",
            content_digest(
                {
                    "schema_version": self.schema_version,
                    "sequence": self.sequence,
                    "event_kind": self.event_kind,
                    "event_ref": self.event_ref,
                    "event_note": self.event_note,
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "event_kind": self.event_kind,
            "event_ref": self.event_ref,
            "event_note": self.event_note,
            "event_digest": self.event_digest,
        }


@dataclass(frozen=True, slots=True)
class RuntimeSessionSourceV1:
    """Immutable agent-session source; terminal state exists only in events."""

    schema_version: str
    project_scope_ref: str
    session_ref: str
    revision: str
    incarnation: str
    events: tuple[RuntimeSessionEventV1, ...]
    coverage_incomplete_flags: tuple[str, ...] = (C8_COVERAGE_INCOMPLETE_SESSION,)
    source_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SESSION_SOURCE_SCHEMA:
            raise ValueError("RuntimeSessionSourceV1.schema_version is not frozen")
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref, "RuntimeSessionSourceV1.project_scope_ref"
            ),
        )
        object.__setattr__(
            self,
            "session_ref",
            _require_text(self.session_ref, "RuntimeSessionSourceV1.session_ref"),
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "RuntimeSessionSourceV1.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(self.incarnation, "RuntimeSessionSourceV1.incarnation"),
        )
        object.__setattr__(
            self,
            "events",
            _normalize_events(self.events, "RuntimeSessionSourceV1.events"),
        )
        object.__setattr__(
            self,
            "coverage_incomplete_flags",
            _normalize_flags(
                self.coverage_incomplete_flags,
                "RuntimeSessionSourceV1.coverage_incomplete_flags",
                required_flag=C8_COVERAGE_INCOMPLETE_SESSION,
            ),
        )
        _assign_closure_ref(
            self,
            "closure_ref",
            identity=self.session_ref,
            revision=self.revision,
            incarnation=self.incarnation,
        )
        _assign_digest(
            self,
            "source_digest",
            content_digest(
                {
                    key: value
                    for key, value in self.to_plain().items()
                    if key != "source_digest"
                }
            ),
        )

    @property
    def terminal_event(self) -> RuntimeSessionEventV1 | None:
        """Return the terminal event derived from the chain, or None."""

        if not self.events:
            return None
        terminal = self.events[-1]
        if terminal.event_kind not in RUNTIME_TERMINAL_EVENT_KINDS:
            return None
        return terminal

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_scope_ref": self.project_scope_ref,
            "session_ref": self.session_ref,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "events": [event.to_plain() for event in self.events],
            "coverage_incomplete_flags": self.coverage_incomplete_flags,
            "source_digest": self.source_digest,
            "closure_ref": self.closure_ref,
        }


@dataclass(frozen=True, slots=True)
class ResearchGraphObjectV1:
    """One immutable research graph object from the canonical source."""

    schema_version: str
    object_id: str
    object_type: str
    label: str
    object_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_GRAPH_OBJECT_SCHEMA:
            raise ValueError("ResearchGraphObjectV1.schema_version is not frozen")
        object.__setattr__(
            self,
            "object_id",
            _require_text(self.object_id, "ResearchGraphObjectV1.object_id"),
        )
        object.__setattr__(
            self,
            "object_type",
            _require_text(self.object_type, "ResearchGraphObjectV1.object_type"),
        )
        object.__setattr__(
            self, "label", _require_text(self.label, "ResearchGraphObjectV1.label")
        )
        _assign_digest(
            self,
            "object_digest",
            content_digest(
                {
                    "schema_version": self.schema_version,
                    "object_id": self.object_id,
                    "object_type": self.object_type,
                    "label": self.label,
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "object_id": self.object_id,
            "object_type": self.object_type,
            "label": self.label,
            "object_digest": self.object_digest,
        }


@dataclass(frozen=True, slots=True)
class ResearchGraphRelationV1:
    """One relation occurrence referencing two objects in the same source."""

    schema_version: str
    relation_id: str
    relation_type: str
    source_object_id: str
    target_object_id: str
    occurrence_ref: str
    relation_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_GRAPH_RELATION_SCHEMA:
            raise ValueError("ResearchGraphRelationV1.schema_version is not frozen")
        object.__setattr__(
            self,
            "relation_id",
            _require_text(self.relation_id, "ResearchGraphRelationV1.relation_id"),
        )
        object.__setattr__(
            self,
            "relation_type",
            _require_text(self.relation_type, "ResearchGraphRelationV1.relation_type"),
        )
        object.__setattr__(
            self,
            "source_object_id",
            _require_text(
                self.source_object_id, "ResearchGraphRelationV1.source_object_id"
            ),
        )
        object.__setattr__(
            self,
            "target_object_id",
            _require_text(
                self.target_object_id, "ResearchGraphRelationV1.target_object_id"
            ),
        )
        object.__setattr__(
            self,
            "occurrence_ref",
            _require_text(
                self.occurrence_ref, "ResearchGraphRelationV1.occurrence_ref"
            ),
        )
        _assign_digest(
            self,
            "relation_digest",
            content_digest(
                {
                    "schema_version": self.schema_version,
                    "relation_id": self.relation_id,
                    "relation_type": self.relation_type,
                    "source_object_id": self.source_object_id,
                    "target_object_id": self.target_object_id,
                    "occurrence_ref": self.occurrence_ref,
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "relation_id": self.relation_id,
            "relation_type": self.relation_type,
            "source_object_id": self.source_object_id,
            "target_object_id": self.target_object_id,
            "occurrence_ref": self.occurrence_ref,
            "relation_digest": self.relation_digest,
        }


@dataclass(frozen=True, slots=True)
class ResearchGraphSourceV1:
    """Immutable research graph source; projection never adds relations."""

    schema_version: str
    project_scope_ref: str
    graph_ref: str
    revision: str
    incarnation: str
    objects: tuple[ResearchGraphObjectV1, ...]
    relations: tuple[ResearchGraphRelationV1, ...]
    coverage_incomplete_flags: tuple[str, ...] = (C8_COVERAGE_INCOMPLETE_GRAPH,)
    source_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_GRAPH_SOURCE_SCHEMA:
            raise ValueError("ResearchGraphSourceV1.schema_version is not frozen")
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref, "ResearchGraphSourceV1.project_scope_ref"
            ),
        )
        object.__setattr__(
            self,
            "graph_ref",
            _require_text(self.graph_ref, "ResearchGraphSourceV1.graph_ref"),
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "ResearchGraphSourceV1.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(self.incarnation, "ResearchGraphSourceV1.incarnation"),
        )
        object.__setattr__(
            self,
            "objects",
            _normalize_objects(self.objects, "ResearchGraphSourceV1.objects"),
        )
        object_ids = frozenset(obj.object_id for obj in self.objects)
        object.__setattr__(
            self,
            "relations",
            _normalize_relations(
                self.relations,
                "ResearchGraphSourceV1.relations",
                object_ids=object_ids,
            ),
        )
        object.__setattr__(
            self,
            "coverage_incomplete_flags",
            _normalize_flags(
                self.coverage_incomplete_flags,
                "ResearchGraphSourceV1.coverage_incomplete_flags",
                required_flag=C8_COVERAGE_INCOMPLETE_GRAPH,
            ),
        )
        _assign_closure_ref(
            self,
            "closure_ref",
            identity=self.graph_ref,
            revision=self.revision,
            incarnation=self.incarnation,
        )
        _assign_digest(
            self,
            "source_digest",
            content_digest(
                {
                    key: value
                    for key, value in self.to_plain().items()
                    if key != "source_digest"
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_scope_ref": self.project_scope_ref,
            "graph_ref": self.graph_ref,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "objects": [obj.to_plain() for obj in self.objects],
            "relations": [relation.to_plain() for relation in self.relations],
            "coverage_incomplete_flags": self.coverage_incomplete_flags,
            "source_digest": self.source_digest,
            "closure_ref": self.closure_ref,
        }


@dataclass(frozen=True, slots=True)
class C7SearchSegmentV1:
    """One C7 search segment with field path and NOT_EXECUTED statuses."""

    schema_version: str
    segment_id: str
    field_path: str
    segment_text: str
    segment_kind: str = C7_SEGMENT_KIND_TEXT
    length_bytes: int = 0
    provider_status: str = NOT_EXECUTED
    vectorization_status: str = NOT_EXECUTED
    segment_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != C7_SEARCH_SEGMENT_SCHEMA:
            raise ValueError("C7SearchSegmentV1.schema_version is not frozen")
        object.__setattr__(
            self,
            "segment_id",
            _require_text(self.segment_id, "C7SearchSegmentV1.segment_id"),
        )
        object.__setattr__(
            self,
            "field_path",
            _require_text(self.field_path, "C7SearchSegmentV1.field_path"),
        )
        object.__setattr__(
            self,
            "segment_text",
            _require_text(self.segment_text, "C7SearchSegmentV1.segment_text"),
        )
        if self.segment_kind not in C7_SEGMENT_KINDS:
            raise ValueError(f"unsupported search segment kind: {self.segment_kind}")
        if self.provider_status != NOT_EXECUTED:
            raise ValueError("C7SearchSegmentV1.provider_status must be NOT_EXECUTED")
        if self.vectorization_status != NOT_EXECUTED:
            raise ValueError(
                "C7SearchSegmentV1.vectorization_status must be NOT_EXECUTED"
            )
        length = _finite_int(self.length_bytes, "C7SearchSegmentV1.length_bytes")
        expected_length = len(self.segment_text.encode("utf-8"))
        if length == 0:
            object.__setattr__(self, "length_bytes", expected_length)
        else:
            if length != expected_length:
                raise ValueError(
                    "C7SearchSegmentV1.length_bytes does not match UTF-8 byte length"
                )
        _assign_digest(
            self,
            "segment_digest",
            content_digest(
                {
                    "schema_version": self.schema_version,
                    "segment_id": self.segment_id,
                    "field_path": self.field_path,
                    "segment_text": self.segment_text,
                    "segment_kind": self.segment_kind,
                    "length_bytes": self.length_bytes,
                    "provider_status": self.provider_status,
                    "vectorization_status": self.vectorization_status,
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "segment_id": self.segment_id,
            "field_path": self.field_path,
            "segment_text": self.segment_text,
            "segment_kind": self.segment_kind,
            "length_bytes": self.length_bytes,
            "provider_status": self.provider_status,
            "vectorization_status": self.vectorization_status,
            "segment_digest": self.segment_digest,
        }


@dataclass(frozen=True, slots=True)
class C7SearchSourceV1:
    """Immutable C7 search source; providers and vectorization never execute."""

    schema_version: str
    project_scope_ref: str
    search_ref: str
    revision: str
    incarnation: str
    segments: tuple[C7SearchSegmentV1, ...]
    provider_status: str = NOT_EXECUTED
    vectorization_status: str = NOT_EXECUTED
    coverage_incomplete_flags: tuple[str, ...] = (C8_COVERAGE_INCOMPLETE_SEARCH,)
    source_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != C7_SEARCH_SOURCE_SCHEMA:
            raise ValueError("C7SearchSourceV1.schema_version is not frozen")
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(self.project_scope_ref, "C7SearchSourceV1.project_scope_ref"),
        )
        object.__setattr__(
            self,
            "search_ref",
            _require_text(self.search_ref, "C7SearchSourceV1.search_ref"),
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "C7SearchSourceV1.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(self.incarnation, "C7SearchSourceV1.incarnation"),
        )
        object.__setattr__(
            self,
            "segments",
            _normalize_segments(self.segments, "C7SearchSourceV1.segments"),
        )
        if self.provider_status != NOT_EXECUTED:
            raise ValueError("C7SearchSourceV1.provider_status must be NOT_EXECUTED")
        if self.vectorization_status != NOT_EXECUTED:
            raise ValueError(
                "C7SearchSourceV1.vectorization_status must be NOT_EXECUTED"
            )
        object.__setattr__(
            self,
            "coverage_incomplete_flags",
            _normalize_flags(
                self.coverage_incomplete_flags,
                "C7SearchSourceV1.coverage_incomplete_flags",
                required_flag=C8_COVERAGE_INCOMPLETE_SEARCH,
            ),
        )
        _assign_closure_ref(
            self,
            "closure_ref",
            identity=self.search_ref,
            revision=self.revision,
            incarnation=self.incarnation,
        )
        _assign_digest(
            self,
            "source_digest",
            content_digest(
                {
                    key: value
                    for key, value in self.to_plain().items()
                    if key != "source_digest"
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_scope_ref": self.project_scope_ref,
            "search_ref": self.search_ref,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "segments": [segment.to_plain() for segment in self.segments],
            "provider_status": self.provider_status,
            "vectorization_status": self.vectorization_status,
            "coverage_incomplete_flags": self.coverage_incomplete_flags,
            "source_digest": self.source_digest,
            "closure_ref": self.closure_ref,
        }


@dataclass(frozen=True, slots=True)
class C9SemanticSourceClosureV1:
    """Identity/revision/incarnation closure over the three C9 sources."""

    schema_version: str
    project_scope_ref: str
    closure_id: str
    revision: str
    incarnation: str
    runtime_session_source: RuntimeSessionSourceV1
    research_graph_source: ResearchGraphSourceV1
    c7_search_source: C7SearchSourceV1
    coverage_incomplete_flags: tuple[str, ...] = ()
    closure_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != C9_SEMANTIC_SOURCE_CLOSURE_SCHEMA:
            raise ValueError("C9SemanticSourceClosureV1.schema_version is not frozen")
        if not isinstance(self.runtime_session_source, RuntimeSessionSourceV1):
            raise TypeError(
                "C9SemanticSourceClosureV1.runtime_session_source must be "
                "RuntimeSessionSourceV1"
            )
        if not isinstance(self.research_graph_source, ResearchGraphSourceV1):
            raise TypeError(
                "C9SemanticSourceClosureV1.research_graph_source must be "
                "ResearchGraphSourceV1"
            )
        if not isinstance(self.c7_search_source, C7SearchSourceV1):
            raise TypeError(
                "C9SemanticSourceClosureV1.c7_search_source must be C7SearchSourceV1"
            )
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref, "C9SemanticSourceClosureV1.project_scope_ref"
            ),
        )
        object.__setattr__(
            self,
            "closure_id",
            _require_text(self.closure_id, "C9SemanticSourceClosureV1.closure_id"),
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "C9SemanticSourceClosureV1.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(self.incarnation, "C9SemanticSourceClosureV1.incarnation"),
        )
        sources = (
            self.runtime_session_source,
            self.research_graph_source,
            self.c7_search_source,
        )
        for source in sources:
            if source.project_scope_ref != self.project_scope_ref:
                raise ValueError(
                    "C9SemanticSourceClosureV1 sources must share project_scope_ref"
                )
            if source.revision != self.revision:
                raise ValueError(
                    "C9SemanticSourceClosureV1 sources must share revision"
                )
            if source.incarnation != self.incarnation:
                raise ValueError(
                    "C9SemanticSourceClosureV1 sources must share incarnation"
                )
        merged_flags = list(self.coverage_incomplete_flags)
        for source in sources:
            for flag in source.coverage_incomplete_flags:
                if flag not in merged_flags:
                    merged_flags.append(flag)
        object.__setattr__(
            self,
            "coverage_incomplete_flags",
            _normalize_flags(
                merged_flags,
                "C9SemanticSourceClosureV1.coverage_incomplete_flags",
            ),
        )
        _assign_closure_ref(
            self,
            "closure_ref",
            identity=self.closure_id,
            revision=self.revision,
            incarnation=self.incarnation,
        )
        _assign_digest(
            self,
            "closure_digest",
            content_digest(
                {
                    key: value
                    for key, value in self.to_plain().items()
                    if key != "closure_digest"
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_scope_ref": self.project_scope_ref,
            "closure_id": self.closure_id,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "runtime_session_source": self.runtime_session_source.to_plain(),
            "research_graph_source": self.research_graph_source.to_plain(),
            "c7_search_source": self.c7_search_source.to_plain(),
            "coverage_incomplete_flags": self.coverage_incomplete_flags,
            "closure_digest": self.closure_digest,
            "closure_ref": self.closure_ref,
        }


@dataclass(frozen=True, slots=True)
class ProjectionFieldLossV1:
    """One field-level loss record for a projection."""

    schema_version: str
    field_path: str
    loss_kind: str
    reason: str
    loss_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != PROJECTION_FIELD_LOSS_SCHEMA:
            raise ValueError("ProjectionFieldLossV1.schema_version is not frozen")
        object.__setattr__(
            self,
            "field_path",
            _require_text(self.field_path, "ProjectionFieldLossV1.field_path"),
        )
        if self.loss_kind not in LOSS_KINDS:
            raise ValueError(f"unsupported projection loss kind: {self.loss_kind}")
        object.__setattr__(
            self, "reason", _require_text(self.reason, "ProjectionFieldLossV1.reason")
        )
        _assign_digest(
            self,
            "loss_digest",
            content_digest(
                {
                    "schema_version": self.schema_version,
                    "field_path": self.field_path,
                    "loss_kind": self.loss_kind,
                    "reason": self.reason,
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "field_path": self.field_path,
            "loss_kind": self.loss_kind,
            "reason": self.reason,
            "loss_digest": self.loss_digest,
        }


@dataclass(frozen=True, slots=True)
class AgentSessionProjectionPayloadV1:
    """Agent-session projection payload; terminal state comes from events."""

    schema_version: str
    project_scope_ref: str
    session_ref: str
    source_ref: str
    source_digest: str
    revision: str
    incarnation: str
    events: tuple[RuntimeSessionEventV1, ...]
    status: str
    terminal_event_ref: str | None
    declared_losses: tuple[ProjectionFieldLossV1, ...]
    coverage_incomplete_flags: tuple[str, ...] = (C8_COVERAGE_INCOMPLETE_SESSION,)
    payload_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_SESSION_PROJECTION_PAYLOAD_SCHEMA:
            raise ValueError(
                "AgentSessionProjectionPayloadV1.schema_version is not frozen"
            )
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref,
                "AgentSessionProjectionPayloadV1.project_scope_ref",
            ),
        )
        object.__setattr__(
            self,
            "session_ref",
            _require_text(
                self.session_ref, "AgentSessionProjectionPayloadV1.session_ref"
            ),
        )
        object.__setattr__(
            self,
            "source_ref",
            _require_text(
                self.source_ref, "AgentSessionProjectionPayloadV1.source_ref"
            ),
        )
        require_hex64(
            self.source_digest, "AgentSessionProjectionPayloadV1.source_digest"
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "AgentSessionProjectionPayloadV1.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(
                self.incarnation, "AgentSessionProjectionPayloadV1.incarnation"
            ),
        )
        object.__setattr__(
            self,
            "events",
            _normalize_events(self.events, "AgentSessionProjectionPayloadV1.events"),
        )
        if self.status not in SESSION_STATUSES:
            raise ValueError(f"unsupported session status: {self.status}")
        terminal_events = tuple(
            event
            for event in self.events
            if event.event_kind in RUNTIME_TERMINAL_EVENT_KINDS
        )
        if self.status in (
            SESSION_STATUS_TERMINAL_SUCCEEDED,
            SESSION_STATUS_TERMINAL_FAILED,
        ):
            if not terminal_events:
                raise ValueError(
                    "terminal status requires a terminal event from the chain"
                )
            expected_kind = (
                SESSION_TERMINAL_SUCCEEDED
                if self.status == SESSION_STATUS_TERMINAL_SUCCEEDED
                else SESSION_TERMINAL_FAILED
            )
            if terminal_events[0].event_kind != expected_kind:
                raise ValueError("session status does not match terminal event kind")
            if self.terminal_event_ref != terminal_events[0].event_ref:
                raise ValueError("terminal_event_ref does not match the terminal event")
        else:
            if terminal_events:
                raise ValueError("non-terminal status cannot include a terminal event")
            if self.terminal_event_ref is not None:
                raise ValueError(
                    "terminal_event_ref must be None for non-terminal status"
                )
        object.__setattr__(
            self,
            "declared_losses",
            _normalize_losses(self.declared_losses),
        )
        object.__setattr__(
            self,
            "coverage_incomplete_flags",
            _normalize_flags(
                self.coverage_incomplete_flags,
                "AgentSessionProjectionPayloadV1.coverage_incomplete_flags",
                required_flag=C8_COVERAGE_INCOMPLETE_SESSION,
            ),
        )
        _assign_closure_ref(
            self,
            "closure_ref",
            identity=self.session_ref,
            revision=self.revision,
            incarnation=self.incarnation,
        )
        _assign_digest(
            self,
            "payload_digest",
            content_digest(
                {
                    key: value
                    for key, value in self.to_plain().items()
                    if key != "payload_digest"
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_scope_ref": self.project_scope_ref,
            "session_ref": self.session_ref,
            "source_ref": self.source_ref,
            "source_digest": self.source_digest,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "events": [event.to_plain() for event in self.events],
            "status": self.status,
            "terminal_event_ref": self.terminal_event_ref,
            "declared_losses": [loss.to_plain() for loss in self.declared_losses],
            "coverage_incomplete_flags": self.coverage_incomplete_flags,
            "payload_digest": self.payload_digest,
            "closure_ref": self.closure_ref,
        }


@dataclass(frozen=True, slots=True)
class ResearchGraphProjectionPayloadV1:
    """Graph projection payload; objects and relations stay one-to-one."""

    schema_version: str
    project_scope_ref: str
    graph_ref: str
    source_ref: str
    source_digest: str
    revision: str
    incarnation: str
    objects: tuple[ResearchGraphObjectV1, ...]
    relations: tuple[ResearchGraphRelationV1, ...]
    declared_losses: tuple[ProjectionFieldLossV1, ...]
    coverage_incomplete_flags: tuple[str, ...] = (C8_COVERAGE_INCOMPLETE_GRAPH,)
    payload_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != RESEARCH_GRAPH_PROJECTION_PAYLOAD_SCHEMA:
            raise ValueError(
                "ResearchGraphProjectionPayloadV1.schema_version is not frozen"
            )
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref,
                "ResearchGraphProjectionPayloadV1.project_scope_ref",
            ),
        )
        object.__setattr__(
            self,
            "graph_ref",
            _require_text(self.graph_ref, "ResearchGraphProjectionPayloadV1.graph_ref"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _require_text(
                self.source_ref, "ResearchGraphProjectionPayloadV1.source_ref"
            ),
        )
        require_hex64(
            self.source_digest, "ResearchGraphProjectionPayloadV1.source_digest"
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "ResearchGraphProjectionPayloadV1.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(
                self.incarnation, "ResearchGraphProjectionPayloadV1.incarnation"
            ),
        )
        object.__setattr__(
            self,
            "objects",
            _normalize_objects(
                self.objects, "ResearchGraphProjectionPayloadV1.objects"
            ),
        )
        object_ids = frozenset(obj.object_id for obj in self.objects)
        object.__setattr__(
            self,
            "relations",
            _normalize_relations(
                self.relations,
                "ResearchGraphProjectionPayloadV1.relations",
                object_ids=object_ids,
            ),
        )
        object.__setattr__(
            self,
            "declared_losses",
            _normalize_losses(self.declared_losses),
        )
        object.__setattr__(
            self,
            "coverage_incomplete_flags",
            _normalize_flags(
                self.coverage_incomplete_flags,
                "ResearchGraphProjectionPayloadV1.coverage_incomplete_flags",
                required_flag=C8_COVERAGE_INCOMPLETE_GRAPH,
            ),
        )
        _assign_closure_ref(
            self,
            "closure_ref",
            identity=self.graph_ref,
            revision=self.revision,
            incarnation=self.incarnation,
        )
        _assign_digest(
            self,
            "payload_digest",
            content_digest(
                {
                    key: value
                    for key, value in self.to_plain().items()
                    if key != "payload_digest"
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_scope_ref": self.project_scope_ref,
            "graph_ref": self.graph_ref,
            "source_ref": self.source_ref,
            "source_digest": self.source_digest,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "objects": [obj.to_plain() for obj in self.objects],
            "relations": [relation.to_plain() for relation in self.relations],
            "declared_losses": [loss.to_plain() for loss in self.declared_losses],
            "coverage_incomplete_flags": self.coverage_incomplete_flags,
            "payload_digest": self.payload_digest,
            "closure_ref": self.closure_ref,
        }


@dataclass(frozen=True, slots=True)
class SearchProjectionPayloadV1:
    """Search projection payload; provider and vectorization stay NOT_EXECUTED."""

    schema_version: str
    project_scope_ref: str
    search_ref: str
    source_ref: str
    source_digest: str
    revision: str
    incarnation: str
    segments: tuple[C7SearchSegmentV1, ...]
    provider_status: str
    vectorization_status: str
    declared_losses: tuple[ProjectionFieldLossV1, ...]
    coverage_incomplete_flags: tuple[str, ...] = (C8_COVERAGE_INCOMPLETE_SEARCH,)
    payload_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SEARCH_PROJECTION_PAYLOAD_SCHEMA:
            raise ValueError("SearchProjectionPayloadV1.schema_version is not frozen")
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref, "SearchProjectionPayloadV1.project_scope_ref"
            ),
        )
        object.__setattr__(
            self,
            "search_ref",
            _require_text(self.search_ref, "SearchProjectionPayloadV1.search_ref"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _require_text(self.source_ref, "SearchProjectionPayloadV1.source_ref"),
        )
        require_hex64(self.source_digest, "SearchProjectionPayloadV1.source_digest")
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "SearchProjectionPayloadV1.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(self.incarnation, "SearchProjectionPayloadV1.incarnation"),
        )
        object.__setattr__(
            self,
            "segments",
            _normalize_segments(self.segments, "SearchProjectionPayloadV1.segments"),
        )
        if self.provider_status != NOT_EXECUTED:
            raise ValueError(
                "SearchProjectionPayloadV1.provider_status must be NOT_EXECUTED"
            )
        if self.vectorization_status != NOT_EXECUTED:
            raise ValueError(
                "SearchProjectionPayloadV1.vectorization_status must be NOT_EXECUTED"
            )
        object.__setattr__(
            self,
            "declared_losses",
            _normalize_losses(self.declared_losses),
        )
        object.__setattr__(
            self,
            "coverage_incomplete_flags",
            _normalize_flags(
                self.coverage_incomplete_flags,
                "SearchProjectionPayloadV1.coverage_incomplete_flags",
                required_flag=C8_COVERAGE_INCOMPLETE_SEARCH,
            ),
        )
        _assign_closure_ref(
            self,
            "closure_ref",
            identity=self.search_ref,
            revision=self.revision,
            incarnation=self.incarnation,
        )
        _assign_digest(
            self,
            "payload_digest",
            content_digest(
                {
                    key: value
                    for key, value in self.to_plain().items()
                    if key != "payload_digest"
                }
            ),
        )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_scope_ref": self.project_scope_ref,
            "search_ref": self.search_ref,
            "source_ref": self.source_ref,
            "source_digest": self.source_digest,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "segments": [segment.to_plain() for segment in self.segments],
            "provider_status": self.provider_status,
            "vectorization_status": self.vectorization_status,
            "declared_losses": [loss.to_plain() for loss in self.declared_losses],
            "coverage_incomplete_flags": self.coverage_incomplete_flags,
            "payload_digest": self.payload_digest,
            "closure_ref": self.closure_ref,
        }


def build_agent_session_payload(
    source: RuntimeSessionSourceV1,
    *,
    declared_losses: tuple[ProjectionFieldLossV1, ...],
) -> AgentSessionProjectionPayloadV1:
    """Project one runtime-session source into a loss-bound session payload."""

    if not isinstance(source, RuntimeSessionSourceV1):
        raise TypeError("build_agent_session_payload requires RuntimeSessionSourceV1")
    losses = _normalize_losses(declared_losses)
    if not losses:
        raise ValueError("agent-session projection requires declared field losses")
    _require_required_flag(
        source.coverage_incomplete_flags,
        C8_COVERAGE_INCOMPLETE_SESSION,
        "RuntimeSessionSourceV1.coverage_incomplete_flags",
    )
    terminal = source.terminal_event
    if terminal is None:
        status = (
            SESSION_STATUS_WAITING
            if len(source.events) == 1
            else SESSION_STATUS_RUNNING
        )
        terminal_event_ref = None
    else:
        status = (
            SESSION_STATUS_TERMINAL_SUCCEEDED
            if terminal.event_kind == SESSION_TERMINAL_SUCCEEDED
            else SESSION_STATUS_TERMINAL_FAILED
        )
        terminal_event_ref = terminal.event_ref
    return AgentSessionProjectionPayloadV1(
        schema_version=AGENT_SESSION_PROJECTION_PAYLOAD_SCHEMA,
        project_scope_ref=source.project_scope_ref,
        session_ref=source.session_ref,
        source_ref=f"runtime-session:{source.session_ref}",
        source_digest=source.source_digest,
        revision=source.revision,
        incarnation=source.incarnation,
        events=source.events,
        status=status,
        terminal_event_ref=terminal_event_ref,
        declared_losses=losses,
        coverage_incomplete_flags=source.coverage_incomplete_flags,
    )


def build_research_graph_payload(
    source: ResearchGraphSourceV1,
    *,
    declared_losses: tuple[ProjectionFieldLossV1, ...],
) -> ResearchGraphProjectionPayloadV1:
    """Project graph objects and relations one-to-one without new edges."""

    if not isinstance(source, ResearchGraphSourceV1):
        raise TypeError("build_research_graph_payload requires ResearchGraphSourceV1")
    losses = _normalize_losses(declared_losses)
    if not losses:
        raise ValueError("research-graph projection requires declared field losses")
    _require_required_flag(
        source.coverage_incomplete_flags,
        C8_COVERAGE_INCOMPLETE_GRAPH,
        "ResearchGraphSourceV1.coverage_incomplete_flags",
    )
    return ResearchGraphProjectionPayloadV1(
        schema_version=RESEARCH_GRAPH_PROJECTION_PAYLOAD_SCHEMA,
        project_scope_ref=source.project_scope_ref,
        graph_ref=source.graph_ref,
        source_ref=f"research-graph:{source.graph_ref}",
        source_digest=source.source_digest,
        revision=source.revision,
        incarnation=source.incarnation,
        objects=source.objects,
        relations=source.relations,
        declared_losses=losses,
        coverage_incomplete_flags=source.coverage_incomplete_flags,
    )


def build_search_payload(
    source: C7SearchSourceV1,
    *,
    declared_losses: tuple[ProjectionFieldLossV1, ...],
) -> SearchProjectionPayloadV1:
    """Project C7 search segments with explicit NOT_EXECUTED statuses."""

    if not isinstance(source, C7SearchSourceV1):
        raise TypeError("build_search_payload requires C7SearchSourceV1")
    losses = _normalize_losses(declared_losses)
    if not losses:
        raise ValueError("search projection requires declared field losses")
    _require_required_flag(
        source.coverage_incomplete_flags,
        C8_COVERAGE_INCOMPLETE_SEARCH,
        "C7SearchSourceV1.coverage_incomplete_flags",
    )
    return SearchProjectionPayloadV1(
        schema_version=SEARCH_PROJECTION_PAYLOAD_SCHEMA,
        project_scope_ref=source.project_scope_ref,
        search_ref=source.search_ref,
        source_ref=f"c7-search:{source.search_ref}",
        source_digest=source.source_digest,
        revision=source.revision,
        incarnation=source.incarnation,
        segments=source.segments,
        provider_status=source.provider_status,
        vectorization_status=source.vectorization_status,
        declared_losses=losses,
        coverage_incomplete_flags=source.coverage_incomplete_flags,
    )
