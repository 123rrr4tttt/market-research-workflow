"""C9 pure typed source and projection payload layer.

This module owns the C9-M004 source-bound projection vocabulary for the local
successor milestone: immutable typed task, knowledge, and material sources, a
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
from typing import Annotated, Any

__all__ = [
    "TASK_VIEW_SCHEMA",
    "MATERIAL_SEGMENT_SCHEMA",
    "MATERIAL_SOURCE_SCHEMA",
    "MATERIAL_SEGMENT_KINDS",
    "MATERIAL_SEGMENT_KIND_FIELD",
    "MATERIAL_SEGMENT_KIND_TEXT",
    "PROJECTION_COVERAGE_INCOMPLETE_FLAGS",
    "PROJECTION_KNOWLEDGE_COVERAGE_INCOMPLETE",
    "PROJECTION_MATERIAL_COVERAGE_INCOMPLETE",
    "PROJECTION_TASK_COVERAGE_INCOMPLETE",
    "PROJECT_SOURCE_CLOSURE_SCHEMA",
    "PROJECTION_SOURCES_CONTRACT",
    "LEGACY_PROJECT_SOURCE_CLOSURE_SCHEMA",
    "LEGACY_PROJECTION_SOURCES_CONTRACT",
    "LEGACY_MATERIAL_SOURCE_SCHEMA",
    "LEGACY_KNOWLEDGE_SOURCE_SCHEMA",
    "LEGACY_TASK_SOURCE_SCHEMA",
    "LOSS_KINDS",
    "LOSS_KIND_DECLARED",
    "LOSS_KIND_NOT_EXECUTED",
    "LOSS_KIND_OMITTED_FIELD",
    "NOT_EXECUTED",
    "PROJECTION_FIELD_LOSS_SCHEMA",
    "KNOWLEDGE_OBJECT_SCHEMA",
    "KNOWLEDGE_VIEW_SCHEMA",
    "KNOWLEDGE_RELATION_SCHEMA",
    "KNOWLEDGE_SOURCE_SCHEMA",
    "TASK_ASSIGNED",
    "TASK_EVENT_KINDS",
    "TASK_EVENT_SCHEMA",
    "TASK_CREATED",
    "TASK_PROJECTION_REFRESHED",
    "TASK_SOURCE_SCHEMA",
    "TASK_TERMINAL_EVENT_KINDS",
    "TASK_TERMINAL_FAILED",
    "TASK_TERMINAL_SUCCEEDED",
    "MATERIAL_VIEW_SCHEMA",
    "TASK_STATUSES",
    "TASK_STATUS_RUNNING",
    "TASK_STATUS_TERMINAL_FAILED",
    "TASK_STATUS_TERMINAL_SUCCEEDED",
    "TASK_STATUS_WAITING",
    "TaskView",
    "MaterialSegment",
    "MaterialSource",
    "ProjectSourceClosure",
    "ProjectionFieldLoss",
    "KnowledgeObject",
    "KnowledgeView",
    "KnowledgeRelation",
    "KnowledgeSource",
    "TaskSourceEvent",
    "TaskSource",
    "MaterialView",
    "build_task_view",
    "build_knowledge_view",
    "build_material_view",
    "canonical_json",
    "content_digest",
    "require_hex64",
    "sha256_hex",
]


PROJECTION_SOURCES_CONTRACT = "mrw.projection.project-sources.pure.v2"

TASK_SOURCE_SCHEMA = "mrw.projection.task-source.v2"
TASK_EVENT_SCHEMA = "mrw.projection.task-event.v2"
KNOWLEDGE_SOURCE_SCHEMA = "mrw.projection.knowledge-source.v2"
KNOWLEDGE_OBJECT_SCHEMA = "mrw.projection.knowledge-object.v2"
KNOWLEDGE_RELATION_SCHEMA = "mrw.projection.knowledge-relation.v2"
MATERIAL_SOURCE_SCHEMA = "mrw.projection.material-source.v2"
MATERIAL_SEGMENT_SCHEMA = "mrw.projection.material-segment.v2"
PROJECT_SOURCE_CLOSURE_SCHEMA = "mrw.projection.project-source-closure.v2"
TASK_VIEW_SCHEMA = (
    "mrw.projection.task-view.v2"
)
KNOWLEDGE_VIEW_SCHEMA = (
    "mrw.projection.knowledge-view.v2"
)
MATERIAL_VIEW_SCHEMA = "mrw.projection.material-view.v2"
PROJECTION_FIELD_LOSS_SCHEMA = "mrw.projection.field-loss.v2"

# Historical v1 wire identities are decoder inputs only.  New values always use
# the business-named v2 schemas above; callers must never rebuild or re-hash a
# v1 row as a v2 value.
LEGACY_PROJECTION_SOURCES_CONTRACT = "mrw.functorial_successor.c9_typed_sources.pure.v1"
LEGACY_TASK_SOURCE_SCHEMA = "mrw.successor.c9.runtime-session-source.v1"
LEGACY_KNOWLEDGE_SOURCE_SCHEMA = "mrw.successor.c9.research-graph-source.v1"
LEGACY_MATERIAL_SOURCE_SCHEMA = "mrw.successor.c9.c7-search-source.v1"
LEGACY_PROJECT_SOURCE_CLOSURE_SCHEMA = (
    "mrw.successor.c9.semantic-source-closure.v1"
)

NOT_EXECUTED = "NOT_EXECUTED"

TASK_STATUS_WAITING = "WAITING"
TASK_STATUS_RUNNING = "RUNNING"
TASK_STATUS_TERMINAL_SUCCEEDED = "TERMINAL_SUCCEEDED"
TASK_STATUS_TERMINAL_FAILED = "TERMINAL_FAILED"
TASK_STATUSES: tuple[str, ...] = (
    TASK_STATUS_WAITING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_TERMINAL_SUCCEEDED,
    TASK_STATUS_TERMINAL_FAILED,
)

TASK_CREATED = "TASK_CREATED"
TASK_ASSIGNED = "TASK_ASSIGNED"
TASK_PROJECTION_REFRESHED = "TASK_PROJECTION_REFRESHED"
TASK_TERMINAL_SUCCEEDED = "TASK_TERMINAL_SUCCEEDED"
TASK_TERMINAL_FAILED = "TASK_TERMINAL_FAILED"
TASK_EVENT_KINDS: frozenset[str] = frozenset(
    {
        TASK_CREATED,
        TASK_ASSIGNED,
        TASK_PROJECTION_REFRESHED,
        TASK_TERMINAL_SUCCEEDED,
        TASK_TERMINAL_FAILED,
    }
)
TASK_TERMINAL_EVENT_KINDS: frozenset[str] = frozenset(
    {TASK_TERMINAL_SUCCEEDED, TASK_TERMINAL_FAILED}
)

MATERIAL_SEGMENT_KIND_TEXT = "TEXT_SEGMENT"
MATERIAL_SEGMENT_KIND_FIELD = "FIELD_SEGMENT"
MATERIAL_SEGMENT_KINDS: frozenset[str] = frozenset(
    {MATERIAL_SEGMENT_KIND_TEXT, MATERIAL_SEGMENT_KIND_FIELD}
)

LOSS_KIND_DECLARED = "DECLARED_LOSS"
LOSS_KIND_OMITTED_FIELD = "OMITTED_FIELD"
LOSS_KIND_NOT_EXECUTED = "NOT_EXECUTED"
LOSS_KINDS: frozenset[str] = frozenset(
    {LOSS_KIND_DECLARED, LOSS_KIND_OMITTED_FIELD, LOSS_KIND_NOT_EXECUTED}
)

PROJECTION_TASK_COVERAGE_INCOMPLETE = "projection.task.coverage-incomplete.v2"
PROJECTION_KNOWLEDGE_COVERAGE_INCOMPLETE = "projection.knowledge.coverage-incomplete.v2"
PROJECTION_MATERIAL_COVERAGE_INCOMPLETE = "projection.material.coverage-incomplete.v2"
PROJECTION_COVERAGE_INCOMPLETE_FLAGS: tuple[str, ...] = (
    PROJECTION_TASK_COVERAGE_INCOMPLETE,
    PROJECTION_KNOWLEDGE_COVERAGE_INCOMPLETE,
    PROJECTION_MATERIAL_COVERAGE_INCOMPLETE,
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
    allowed: tuple[str, ...] = PROJECTION_COVERAGE_INCOMPLETE_FLAGS,
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
    values: Iterable[ProjectionFieldLoss] | None,
) -> tuple[ProjectionFieldLoss, ...]:
    normalized: list[ProjectionFieldLoss] = []
    for item in values or ():
        if not isinstance(item, ProjectionFieldLoss):
            raise TypeError("declared losses must be ProjectionFieldLoss records")
        normalized.append(item)
    return tuple(normalized)


def _normalize_events(
    values: Iterable[TaskSourceEvent],
    field_name: str,
) -> tuple[TaskSourceEvent, ...]:
    events = tuple(values or ())
    if not events:
        raise ValueError(f"{field_name} requires at least one runtime event")
    for event in events:
        if not isinstance(event, TaskSourceEvent):
            raise TypeError(f"{field_name} entries must be TaskSourceEvent")
    ordered = tuple(sorted(events, key=lambda event: event.sequence))
    for index in range(1, len(ordered)):
        if ordered[index].sequence == ordered[index - 1].sequence:
            raise ValueError("runtime event sequences must be unique")
    terminal = tuple(
        event for event in ordered if event.event_kind in TASK_TERMINAL_EVENT_KINDS
    )
    if len(terminal) > 1:
        raise ValueError("runtime event chain has more than one terminal event")
    if terminal and terminal[0].sequence != ordered[-1].sequence:
        raise ValueError("terminal runtime event must be the last event")
    return ordered


def _normalize_objects(
    values: Iterable[KnowledgeObject],
    field_name: str,
) -> tuple[KnowledgeObject, ...]:
    objects = tuple(values or ())
    for obj in objects:
        if not isinstance(obj, KnowledgeObject):
            raise TypeError(f"{field_name} entries must be KnowledgeObject")
    ids = [obj.object_id for obj in objects]
    if len(ids) != len(set(ids)):
        raise ValueError("research graph object ids must be unique")
    return objects


def _normalize_relations(
    values: Iterable[KnowledgeRelation],
    field_name: str,
    *,
    object_ids: frozenset[str],
) -> tuple[KnowledgeRelation, ...]:
    relations = tuple(values or ())
    for relation in relations:
        if not isinstance(relation, KnowledgeRelation):
            raise TypeError(f"{field_name} entries must be KnowledgeRelation")
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
    values: Iterable[MaterialSegment],
    field_name: str,
) -> tuple[MaterialSegment, ...]:
    segments = tuple(values or ())
    if not segments:
        raise ValueError(f"{field_name} requires at least one search segment")
    for segment in segments:
        if not isinstance(segment, MaterialSegment):
            raise TypeError(f"{field_name} entries must be MaterialSegment")
    ids = [segment.segment_id for segment in segments]
    if len(ids) != len(set(ids)):
        raise ValueError("search segment ids must be unique")
    return segments


@dataclass(frozen=True, slots=True)
class TaskSourceEvent:
    """One ordered runtime session event; never a caller-supplied terminal."""

    schema_version: str
    sequence: int
    event_kind: str
    event_ref: str
    event_note: str = ""
    event_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != TASK_EVENT_SCHEMA:
            raise ValueError("TaskSourceEvent.schema_version is not frozen")
        sequence = _finite_int(self.sequence, "TaskSourceEvent.sequence")
        if sequence < 0:
            raise ValueError("TaskSourceEvent.sequence must be non-negative")
        object.__setattr__(self, "sequence", sequence)
        if self.event_kind not in TASK_EVENT_KINDS:
            raise ValueError(f"unsupported runtime event kind: {self.event_kind}")
        object.__setattr__(
            self,
            "event_ref",
            _require_text(self.event_ref, "TaskSourceEvent.event_ref"),
        )
        object.__setattr__(
            self,
            "event_note",
            _require_text(
                self.event_note, "TaskSourceEvent.event_note", allow_empty=True
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
class TaskSource:
    """Immutable agent-session source; terminal state exists only in events."""

    schema_version: str
    project_scope_ref: str
    session_ref: str
    revision: str
    incarnation: str
    events: tuple[TaskSourceEvent, ...]
    coverage_incomplete_flags: tuple[str, ...] = (PROJECTION_TASK_COVERAGE_INCOMPLETE,)
    source_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != TASK_SOURCE_SCHEMA:
            raise ValueError("TaskSource.schema_version is not frozen")
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref, "TaskSource.project_scope_ref"
            ),
        )
        object.__setattr__(
            self,
            "session_ref",
            _require_text(self.session_ref, "TaskSource.session_ref"),
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "TaskSource.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(self.incarnation, "TaskSource.incarnation"),
        )
        object.__setattr__(
            self,
            "events",
            _normalize_events(self.events, "TaskSource.events"),
        )
        object.__setattr__(
            self,
            "coverage_incomplete_flags",
            _normalize_flags(
                self.coverage_incomplete_flags,
                "TaskSource.coverage_incomplete_flags",
                required_flag=PROJECTION_TASK_COVERAGE_INCOMPLETE,
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
    def terminal_event(self) -> TaskSourceEvent | None:
        """Return the terminal event derived from the chain, or None."""

        if not self.events:
            return None
        terminal = self.events[-1]
        if terminal.event_kind not in TASK_TERMINAL_EVENT_KINDS:
            return None
        return terminal

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_scope_ref": self.project_scope_ref,
            "task_ref": self.session_ref,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "events": [event.to_plain() for event in self.events],
            "coverage_incomplete_flags": self.coverage_incomplete_flags,
            "source_digest": self.source_digest,
            "closure_ref": self.closure_ref,
        }


@dataclass(frozen=True, slots=True)
class KnowledgeObject:
    """One immutable research graph object from the canonical source."""

    schema_version: str
    object_id: str
    object_type: str
    label: str
    object_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != KNOWLEDGE_OBJECT_SCHEMA:
            raise ValueError("KnowledgeObject.schema_version is not frozen")
        object.__setattr__(
            self,
            "object_id",
            _require_text(self.object_id, "KnowledgeObject.object_id"),
        )
        object.__setattr__(
            self,
            "object_type",
            _require_text(self.object_type, "KnowledgeObject.object_type"),
        )
        object.__setattr__(
            self, "label", _require_text(self.label, "KnowledgeObject.label")
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
class KnowledgeRelation:
    """One relation occurrence referencing two objects in the same source."""

    schema_version: str
    relation_id: str
    relation_type: str
    source_object_id: str
    target_object_id: str
    occurrence_ref: str
    relation_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != KNOWLEDGE_RELATION_SCHEMA:
            raise ValueError("KnowledgeRelation.schema_version is not frozen")
        object.__setattr__(
            self,
            "relation_id",
            _require_text(self.relation_id, "KnowledgeRelation.relation_id"),
        )
        object.__setattr__(
            self,
            "relation_type",
            _require_text(self.relation_type, "KnowledgeRelation.relation_type"),
        )
        object.__setattr__(
            self,
            "source_object_id",
            _require_text(
                self.source_object_id, "KnowledgeRelation.source_object_id"
            ),
        )
        object.__setattr__(
            self,
            "target_object_id",
            _require_text(
                self.target_object_id, "KnowledgeRelation.target_object_id"
            ),
        )
        object.__setattr__(
            self,
            "occurrence_ref",
            _require_text(
                self.occurrence_ref, "KnowledgeRelation.occurrence_ref"
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
class KnowledgeSource:
    """Immutable research graph source; projection never adds relations."""

    schema_version: str
    project_scope_ref: str
    graph_ref: str
    revision: str
    incarnation: str
    objects: tuple[KnowledgeObject, ...]
    relations: tuple[KnowledgeRelation, ...]
    coverage_incomplete_flags: tuple[str, ...] = (PROJECTION_KNOWLEDGE_COVERAGE_INCOMPLETE,)
    source_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != KNOWLEDGE_SOURCE_SCHEMA:
            raise ValueError("KnowledgeSource.schema_version is not frozen")
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref, "KnowledgeSource.project_scope_ref"
            ),
        )
        object.__setattr__(
            self,
            "graph_ref",
            _require_text(self.graph_ref, "KnowledgeSource.graph_ref"),
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "KnowledgeSource.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(self.incarnation, "KnowledgeSource.incarnation"),
        )
        object.__setattr__(
            self,
            "objects",
            _normalize_objects(self.objects, "KnowledgeSource.objects"),
        )
        object_ids = frozenset(obj.object_id for obj in self.objects)
        object.__setattr__(
            self,
            "relations",
            _normalize_relations(
                self.relations,
                "KnowledgeSource.relations",
                object_ids=object_ids,
            ),
        )
        object.__setattr__(
            self,
            "coverage_incomplete_flags",
            _normalize_flags(
                self.coverage_incomplete_flags,
                "KnowledgeSource.coverage_incomplete_flags",
                required_flag=PROJECTION_KNOWLEDGE_COVERAGE_INCOMPLETE,
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
            "knowledge_ref": self.graph_ref,
            "revision": self.revision,
            "incarnation": self.incarnation,
            "objects": [obj.to_plain() for obj in self.objects],
            "relations": [relation.to_plain() for relation in self.relations],
            "coverage_incomplete_flags": self.coverage_incomplete_flags,
            "source_digest": self.source_digest,
            "closure_ref": self.closure_ref,
        }


@dataclass(frozen=True, slots=True)
class MaterialSegment:
    """One C7 search segment with field path and NOT_EXECUTED statuses."""

    schema_version: str
    segment_id: str
    field_path: str
    segment_text: str
    segment_kind: str = MATERIAL_SEGMENT_KIND_TEXT
    length_bytes: int = 0
    provider_status: str = NOT_EXECUTED
    vectorization_status: str = NOT_EXECUTED
    segment_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != MATERIAL_SEGMENT_SCHEMA:
            raise ValueError("MaterialSegment.schema_version is not frozen")
        object.__setattr__(
            self,
            "segment_id",
            _require_text(self.segment_id, "MaterialSegment.segment_id"),
        )
        object.__setattr__(
            self,
            "field_path",
            _require_text(self.field_path, "MaterialSegment.field_path"),
        )
        object.__setattr__(
            self,
            "segment_text",
            _require_text(self.segment_text, "MaterialSegment.segment_text"),
        )
        if self.segment_kind not in MATERIAL_SEGMENT_KINDS:
            raise ValueError(f"unsupported search segment kind: {self.segment_kind}")
        if self.provider_status != NOT_EXECUTED:
            raise ValueError("MaterialSegment.provider_status must be NOT_EXECUTED")
        if self.vectorization_status != NOT_EXECUTED:
            raise ValueError(
                "MaterialSegment.vectorization_status must be NOT_EXECUTED"
            )
        length = _finite_int(self.length_bytes, "MaterialSegment.length_bytes")
        expected_length = len(self.segment_text.encode("utf-8"))
        if length == 0:
            object.__setattr__(self, "length_bytes", expected_length)
        else:
            if length != expected_length:
                raise ValueError(
                    "MaterialSegment.length_bytes does not match UTF-8 byte length"
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
class MaterialSource:
    """Immutable C7 search source; providers and vectorization never execute."""

    schema_version: str
    project_scope_ref: str
    search_ref: str
    revision: str
    incarnation: str
    segments: tuple[MaterialSegment, ...]
    provider_status: str = NOT_EXECUTED
    vectorization_status: str = NOT_EXECUTED
    coverage_incomplete_flags: tuple[str, ...] = (PROJECTION_MATERIAL_COVERAGE_INCOMPLETE,)
    source_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != MATERIAL_SOURCE_SCHEMA:
            raise ValueError("MaterialSource.schema_version is not frozen")
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(self.project_scope_ref, "MaterialSource.project_scope_ref"),
        )
        object.__setattr__(
            self,
            "search_ref",
            _require_text(self.search_ref, "MaterialSource.search_ref"),
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "MaterialSource.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(self.incarnation, "MaterialSource.incarnation"),
        )
        object.__setattr__(
            self,
            "segments",
            _normalize_segments(self.segments, "MaterialSource.segments"),
        )
        if self.provider_status != NOT_EXECUTED:
            raise ValueError("MaterialSource.provider_status must be NOT_EXECUTED")
        if self.vectorization_status != NOT_EXECUTED:
            raise ValueError(
                "MaterialSource.vectorization_status must be NOT_EXECUTED"
            )
        object.__setattr__(
            self,
            "coverage_incomplete_flags",
            _normalize_flags(
                self.coverage_incomplete_flags,
                "MaterialSource.coverage_incomplete_flags",
                required_flag=PROJECTION_MATERIAL_COVERAGE_INCOMPLETE,
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
            "material_ref": self.search_ref,
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
class ProjectSourceClosure:
    """Identity/revision/incarnation closure over the three C9 sources."""

    schema_version: str
    project_scope_ref: str
    closure_id: str
    revision: str
    incarnation: str
    task_source: TaskSource
    knowledge_source: KnowledgeSource
    material_source: MaterialSource
    coverage_incomplete_flags: tuple[str, ...] = ()
    closure_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != PROJECT_SOURCE_CLOSURE_SCHEMA:
            raise ValueError("ProjectSourceClosure.schema_version is not frozen")
        if not isinstance(self.task_source, TaskSource):
            raise TypeError(
                "ProjectSourceClosure.task_source must be "
                "TaskSource"
            )
        if not isinstance(self.knowledge_source, KnowledgeSource):
            raise TypeError(
                "ProjectSourceClosure.knowledge_source must be "
                "KnowledgeSource"
            )
        if not isinstance(self.material_source, MaterialSource):
            raise TypeError(
                "ProjectSourceClosure.material_source must be MaterialSource"
            )
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref, "ProjectSourceClosure.project_scope_ref"
            ),
        )
        object.__setattr__(
            self,
            "closure_id",
            _require_text(self.closure_id, "ProjectSourceClosure.closure_id"),
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "ProjectSourceClosure.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(self.incarnation, "ProjectSourceClosure.incarnation"),
        )
        sources = (
            self.task_source,
            self.knowledge_source,
            self.material_source,
        )
        for source in sources:
            if source.project_scope_ref != self.project_scope_ref:
                raise ValueError(
                    "ProjectSourceClosure sources must share project_scope_ref"
                )
            if source.revision != self.revision:
                raise ValueError(
                    "ProjectSourceClosure sources must share revision"
                )
            if source.incarnation != self.incarnation:
                raise ValueError(
                    "ProjectSourceClosure sources must share incarnation"
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
                "ProjectSourceClosure.coverage_incomplete_flags",
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
            "task_source": self.task_source.to_plain(),
            "knowledge_source": self.knowledge_source.to_plain(),
            "material_source": self.material_source.to_plain(),
            "coverage_incomplete_flags": self.coverage_incomplete_flags,
            "closure_digest": self.closure_digest,
            "closure_ref": self.closure_ref,
        }


@dataclass(frozen=True, slots=True)
class ProjectionFieldLoss:
    """One field-level loss record for a projection."""

    schema_version: str
    field_path: str
    loss_kind: str
    reason: str
    loss_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != PROJECTION_FIELD_LOSS_SCHEMA:
            raise ValueError("ProjectionFieldLoss.schema_version is not frozen")
        object.__setattr__(
            self,
            "field_path",
            _require_text(self.field_path, "ProjectionFieldLoss.field_path"),
        )
        if self.loss_kind not in LOSS_KINDS:
            raise ValueError(f"unsupported projection loss kind: {self.loss_kind}")
        object.__setattr__(
            self, "reason", _require_text(self.reason, "ProjectionFieldLoss.reason")
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
class TaskView:
    """Agent-session projection payload; terminal state comes from events."""

    schema_version: str
    project_scope_ref: str
    session_ref: str
    source_ref: str
    source_digest: str
    revision: str
    incarnation: str
    events: tuple[TaskSourceEvent, ...]
    status: str
    terminal_event_ref: str | None
    declared_losses: tuple[ProjectionFieldLoss, ...]
    coverage_incomplete_flags: tuple[str, ...] = (PROJECTION_TASK_COVERAGE_INCOMPLETE,)
    payload_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != TASK_VIEW_SCHEMA:
            raise ValueError(
                "TaskView.schema_version is not frozen"
            )
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref,
                "TaskView.project_scope_ref",
            ),
        )
        object.__setattr__(
            self,
            "session_ref",
            _require_text(
                self.session_ref, "TaskView.session_ref"
            ),
        )
        object.__setattr__(
            self,
            "source_ref",
            _require_text(
                self.source_ref, "TaskView.source_ref"
            ),
        )
        require_hex64(
            self.source_digest, "TaskView.source_digest"
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "TaskView.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(
                self.incarnation, "TaskView.incarnation"
            ),
        )
        object.__setattr__(
            self,
            "events",
            _normalize_events(self.events, "TaskView.events"),
        )
        if self.status not in TASK_STATUSES:
            raise ValueError(f"unsupported session status: {self.status}")
        terminal_events = tuple(
            event
            for event in self.events
            if event.event_kind in TASK_TERMINAL_EVENT_KINDS
        )
        if self.status in (
            TASK_STATUS_TERMINAL_SUCCEEDED,
            TASK_STATUS_TERMINAL_FAILED,
        ):
            if not terminal_events:
                raise ValueError(
                    "terminal status requires a terminal event from the chain"
                )
            expected_kind = (
                TASK_TERMINAL_SUCCEEDED
                if self.status == TASK_STATUS_TERMINAL_SUCCEEDED
                else TASK_TERMINAL_FAILED
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
                "TaskView.coverage_incomplete_flags",
                required_flag=PROJECTION_TASK_COVERAGE_INCOMPLETE,
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
class KnowledgeView:
    """Graph projection payload; objects and relations stay one-to-one."""

    schema_version: str
    project_scope_ref: str
    graph_ref: str
    source_ref: str
    source_digest: str
    revision: str
    incarnation: str
    objects: tuple[KnowledgeObject, ...]
    relations: tuple[KnowledgeRelation, ...]
    declared_losses: tuple[ProjectionFieldLoss, ...]
    coverage_incomplete_flags: tuple[str, ...] = (PROJECTION_KNOWLEDGE_COVERAGE_INCOMPLETE,)
    payload_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != KNOWLEDGE_VIEW_SCHEMA:
            raise ValueError(
                "KnowledgeView.schema_version is not frozen"
            )
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref,
                "KnowledgeView.project_scope_ref",
            ),
        )
        object.__setattr__(
            self,
            "graph_ref",
            _require_text(self.graph_ref, "KnowledgeView.graph_ref"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _require_text(
                self.source_ref, "KnowledgeView.source_ref"
            ),
        )
        require_hex64(
            self.source_digest, "KnowledgeView.source_digest"
        )
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "KnowledgeView.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(
                self.incarnation, "KnowledgeView.incarnation"
            ),
        )
        object.__setattr__(
            self,
            "objects",
            _normalize_objects(
                self.objects, "KnowledgeView.objects"
            ),
        )
        object_ids = frozenset(obj.object_id for obj in self.objects)
        object.__setattr__(
            self,
            "relations",
            _normalize_relations(
                self.relations,
                "KnowledgeView.relations",
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
                "KnowledgeView.coverage_incomplete_flags",
                required_flag=PROJECTION_KNOWLEDGE_COVERAGE_INCOMPLETE,
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
class MaterialView:
    """Search projection payload; provider and vectorization stay NOT_EXECUTED."""

    schema_version: str
    project_scope_ref: str
    search_ref: str
    source_ref: str
    source_digest: str
    revision: str
    incarnation: str
    segments: tuple[MaterialSegment, ...]
    provider_status: str
    vectorization_status: str
    declared_losses: tuple[ProjectionFieldLoss, ...]
    coverage_incomplete_flags: tuple[str, ...] = (PROJECTION_MATERIAL_COVERAGE_INCOMPLETE,)
    payload_digest: str = ""
    closure_ref: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != MATERIAL_VIEW_SCHEMA:
            raise ValueError("MaterialView.schema_version is not frozen")
        object.__setattr__(
            self,
            "project_scope_ref",
            _require_text(
                self.project_scope_ref, "MaterialView.project_scope_ref"
            ),
        )
        object.__setattr__(
            self,
            "search_ref",
            _require_text(self.search_ref, "MaterialView.search_ref"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _require_text(self.source_ref, "MaterialView.source_ref"),
        )
        require_hex64(self.source_digest, "MaterialView.source_digest")
        object.__setattr__(
            self,
            "revision",
            _require_text(self.revision, "MaterialView.revision"),
        )
        object.__setattr__(
            self,
            "incarnation",
            _require_text(self.incarnation, "MaterialView.incarnation"),
        )
        object.__setattr__(
            self,
            "segments",
            _normalize_segments(self.segments, "MaterialView.segments"),
        )
        if self.provider_status != NOT_EXECUTED:
            raise ValueError(
                "MaterialView.provider_status must be NOT_EXECUTED"
            )
        if self.vectorization_status != NOT_EXECUTED:
            raise ValueError(
                "MaterialView.vectorization_status must be NOT_EXECUTED"
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
                "MaterialView.coverage_incomplete_flags",
                required_flag=PROJECTION_MATERIAL_COVERAGE_INCOMPLETE,
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


def build_task_view(
    source: TaskSource,
    *,
    declared_losses: tuple[ProjectionFieldLoss, ...],
) -> Annotated[
    TaskView,
    "kit:non-authoritative derived_as=view "
    "fact_source=app.successor_runtime.substrate.projections.projection_sources."
    "TaskSource "
    "witness=test:test_w08e_projection_authority_metadata_is_exact",
]:
    """Project one runtime-session source into a loss-bound session payload."""

    if not isinstance(source, TaskSource):
        raise TypeError("build_task_view requires TaskSource")
    losses = _normalize_losses(declared_losses)
    if not losses:
        raise ValueError("agent-session projection requires declared field losses")
    _require_required_flag(
        source.coverage_incomplete_flags,
        PROJECTION_TASK_COVERAGE_INCOMPLETE,
        "TaskSource.coverage_incomplete_flags",
    )
    terminal = source.terminal_event
    if terminal is None:
        status = (
            TASK_STATUS_WAITING
            if len(source.events) == 1
            else TASK_STATUS_RUNNING
        )
        terminal_event_ref = None
    else:
        status = (
            TASK_STATUS_TERMINAL_SUCCEEDED
            if terminal.event_kind == TASK_TERMINAL_SUCCEEDED
            else TASK_STATUS_TERMINAL_FAILED
        )
        terminal_event_ref = terminal.event_ref
    return TaskView(
        schema_version=TASK_VIEW_SCHEMA,
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


def build_knowledge_view(
    source: KnowledgeSource,
    *,
    declared_losses: tuple[ProjectionFieldLoss, ...],
) -> Annotated[
    KnowledgeView,
    "kit:non-authoritative derived_as=view "
    "fact_source=app.successor_runtime.substrate.projections.projection_sources."
    "KnowledgeSource "
    "witness=test:test_w08e_projection_authority_metadata_is_exact",
]:
    """Project graph objects and relations one-to-one without new edges."""

    if not isinstance(source, KnowledgeSource):
        raise TypeError("build_knowledge_view requires KnowledgeSource")
    losses = _normalize_losses(declared_losses)
    if not losses:
        raise ValueError("research-graph projection requires declared field losses")
    _require_required_flag(
        source.coverage_incomplete_flags,
        PROJECTION_KNOWLEDGE_COVERAGE_INCOMPLETE,
        "KnowledgeSource.coverage_incomplete_flags",
    )
    return KnowledgeView(
        schema_version=KNOWLEDGE_VIEW_SCHEMA,
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


def build_material_view(
    source: MaterialSource,
    *,
    declared_losses: tuple[ProjectionFieldLoss, ...],
) -> Annotated[
    MaterialView,
    "kit:non-authoritative derived_as=view "
    "fact_source=app.successor_runtime.substrate.projections.projection_sources."
    "MaterialSource "
    "witness=test:test_w08e_projection_authority_metadata_is_exact",
]:
    """Project C7 search segments with explicit NOT_EXECUTED statuses."""

    if not isinstance(source, MaterialSource):
        raise TypeError("build_material_view requires MaterialSource")
    losses = _normalize_losses(declared_losses)
    if not losses:
        raise ValueError("search projection requires declared field losses")
    _require_required_flag(
        source.coverage_incomplete_flags,
        PROJECTION_MATERIAL_COVERAGE_INCOMPLETE,
        "MaterialSource.coverage_incomplete_flags",
    )
    return MaterialView(
        schema_version=MATERIAL_VIEW_SCHEMA,
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
