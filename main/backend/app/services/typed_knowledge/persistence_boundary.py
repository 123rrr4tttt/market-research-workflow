from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Mapping

from . import contracts


PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION: Final[str] = "typed_knowledge.persistence_api_boundary.v1"
PERSISTENCE_WRITE_RESULT_CONTRACT_VERSION: Final[str] = "typed_knowledge.persistence_write_result.v1"
PUBLIC_API_ROUTE_CONTRACT_VERSION: Final[str] = "typed_knowledge.public_api_route_contract.v1"
PUBLIC_API_ROUTE_PATH: Final[str] = "/api/v1/typed-knowledge/persistence-boundary"
DEFAULT_REPOSITORY_REF: Final[str] = "memory://typed-knowledge/persistence-api-boundary"
DEFAULT_LOGICAL_TABLE: Final[str] = "typed_knowledge_objects"

OBJECT_TYPE_TYPE_NODE = "type_node"
OBJECT_TYPE_KNOWLEDGE_ITEM = "knowledge_item"
OBJECT_TYPE_TOPIC_CLUSTER = "topic_cluster"
OBJECT_TYPE_BOOKLET = "booklet"
ALLOWED_OBJECT_TYPES: Final[tuple[str, ...]] = (
    OBJECT_TYPE_TYPE_NODE,
    OBJECT_TYPE_KNOWLEDGE_ITEM,
    OBJECT_TYPE_TOPIC_CLUSTER,
    OBJECT_TYPE_BOOKLET,
)

LIFECYCLE_STATE_PROPOSED = "proposed"
LIFECYCLE_STATE_ACTIVE = "active"
LIFECYCLE_STATE_ARCHIVED = "archived"
ALLOWED_LIFECYCLE_STATES: Final[tuple[str, ...]] = (
    LIFECYCLE_STATE_PROPOSED,
    LIFECYCLE_STATE_ACTIVE,
    LIFECYCLE_STATE_ARCHIVED,
)
REVIEW_STATE_LIFECYCLE_STATE: Final[Mapping[str, str]] = MappingProxyType(
    {
        contracts.REVIEW_STATE_DRAFT_CANDIDATE: LIFECYCLE_STATE_PROPOSED,
        contracts.REVIEW_STATE_HUMAN_CONFIRMED: LIFECYCLE_STATE_ACTIVE,
        contracts.REVIEW_STATE_REVISED: LIFECYCLE_STATE_ACTIVE,
        contracts.REVIEW_STATE_DEPRECATED: LIFECYCLE_STATE_ARCHIVED,
    }
)

PERSISTENCE_API_BOUNDARY_FIELDS: Final[tuple[str, ...]] = (
    "contract_version",
    "object_type",
    "object_key",
    "project_key",
    "identity_ref",
    "visibility_scope",
    "lifecycle_state",
    "governance",
    "writing_handoff_refs",
    "payload",
    "updated_at",
)
PERSISTENCE_API_BOUNDARY_CLOSED_SLICE: Final[tuple[str, ...]] = (
    "typed_knowledge_object_identity",
    "review_state_to_visibility_scope",
    "review_state_to_lifecycle_state",
    "in_memory_repository_readback",
    "status_data_error_meta_api_envelope",
    "writing_handoff_reference_preservation",
)
PERSISTENCE_API_BOUNDARY_REMAINING_LIVE_GAPS: Final[tuple[str, ...]] = (
    "live_db_persistence_not_implemented",
    "public_typed_knowledge_api_route_not_implemented",
    "governance_ui_not_implemented",
    "migration_and_backfill_not_executed",
)
PUBLIC_API_ROUTE_CLOSED_SLICE: Final[tuple[str, ...]] = (
    "typed_knowledge_public_api_route_contract",
    "persistence_boundary_envelope_readback",
    "status_data_error_meta_route_envelope",
    "live_db_overclaim_guard",
)
PUBLIC_API_ROUTE_REMAINING_LIVE_GAPS: Final[tuple[str, ...]] = (
    "live_db_persistence_not_implemented",
    "governance_ui_not_implemented",
    "migration_and_backfill_not_executed",
    "live_db_backed_typed_knowledge_readback_not_verified",
)


class TypedKnowledgePersistenceBoundaryError(contracts.TypedKnowledgeContractError):
    """Raised when the typed-knowledge persistence/API boundary is violated."""


@dataclass(frozen=True, slots=True)
class WritingHandoffRef:
    contract_version: str
    knowledge_item_key: str
    consumer: str = "writing.keyword_card"
    card_source_type: str = "resource"
    selection_hash: str | None = None
    selection_text: str | None = None


@dataclass(frozen=True, slots=True)
class PersistenceBoundaryRecord:
    contract_version: str
    object_type: str
    object_key: str
    project_key: str
    identity_ref: str
    visibility_scope: str
    lifecycle_state: str
    governance: Mapping[str, Any]
    writing_handoff_refs: tuple[WritingHandoffRef, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class PersistenceWriteResult:
    contract_version: str
    repository_ref: str
    logical_table: str
    operation: str
    identity_ref: str
    object_type: str
    object_key: str
    status_before: str | None
    status_after: str
    visibility_scope: str
    write_time: str
    payload_ref: str
    live_db_write: bool = False


class InMemoryTypedKnowledgeRepository:
    def __init__(
        self,
        *,
        repository_ref: str = DEFAULT_REPOSITORY_REF,
        logical_table: str = DEFAULT_LOGICAL_TABLE,
    ) -> None:
        self.repository_ref = str(repository_ref or "").strip() or DEFAULT_REPOSITORY_REF
        self.logical_table = str(logical_table or "").strip() or DEFAULT_LOGICAL_TABLE
        self._records: dict[str, PersistenceBoundaryRecord] = {}
        self._writes: list[PersistenceWriteResult] = []

    def upsert_record(
        self,
        record: PersistenceBoundaryRecord,
        *,
        write_time: str | None = None,
        operation: str = "upsert",
    ) -> PersistenceWriteResult:
        validate_persistence_boundary_record(record)
        normalized_operation = str(operation or "").strip() or "upsert"
        previous = self._records.get(record.identity_ref)
        normalized_write_time = _normalize_write_time(write_time, record.updated_at)
        self._records[record.identity_ref] = record
        result = PersistenceWriteResult(
            contract_version=PERSISTENCE_WRITE_RESULT_CONTRACT_VERSION,
            repository_ref=self.repository_ref,
            logical_table=self.logical_table,
            operation=normalized_operation,
            identity_ref=record.identity_ref,
            object_type=record.object_type,
            object_key=record.object_key,
            status_before=previous.lifecycle_state if previous else None,
            status_after=record.lifecycle_state,
            visibility_scope=record.visibility_scope,
            write_time=normalized_write_time,
            payload_ref=f"{self.repository_ref}/{self.logical_table}/{record.identity_ref}",
            live_db_write=False,
        )
        self._writes.append(result)
        return result

    def get_record(self, identity_ref: str) -> PersistenceBoundaryRecord | None:
        return self._records.get(str(identity_ref or "").strip())

    def list_records(self, *, project_key: str | None = None) -> tuple[PersistenceBoundaryRecord, ...]:
        normalized_project_key = str(project_key or "").strip() or None
        records = tuple(self._records[key] for key in sorted(self._records))
        if normalized_project_key is None:
            return records
        return tuple(record for record in records if record.project_key == normalized_project_key)

    def list_writes(self) -> tuple[PersistenceWriteResult, ...]:
        return tuple(self._writes)


def build_writing_handoff_ref(handoff: contracts.WritingKnowledgeHandoff) -> WritingHandoffRef:
    contracts.validate_writing_knowledge_handoff(handoff)
    consumer_boundary = handoff.facets.get("consumer_boundary") if isinstance(handoff.facets, Mapping) else None
    if not isinstance(consumer_boundary, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("writing_handoff_ref_missing_consumer_boundary")
    return WritingHandoffRef(
        contract_version=handoff.contract_version,
        knowledge_item_key=handoff.knowledge_item_key,
        consumer=str(consumer_boundary.get("consumer") or ""),
        card_source_type=str(consumer_boundary.get("card_source_type") or ""),
        selection_hash=handoff.selection_hash,
        selection_text=handoff.selection_text,
    )


def build_persistence_boundary_record(
    obj: contracts.TypeNode | contracts.KnowledgeItem | contracts.TopicCluster | contracts.Booklet,
    *,
    writing_handoffs: tuple[contracts.WritingKnowledgeHandoff, ...] = (),
) -> PersistenceBoundaryRecord:
    object_type, object_key, project_key, review_state, payload, updated_at = _object_parts(obj)
    visibility_scope = contracts.REVIEW_STATE_VISIBILITY_SCOPE[review_state]
    lifecycle_state = REVIEW_STATE_LIFECYCLE_STATE[review_state]
    handoff_refs = tuple(
        build_writing_handoff_ref(handoff)
        for handoff in writing_handoffs
        if object_type == OBJECT_TYPE_KNOWLEDGE_ITEM and handoff.knowledge_item_key == object_key
    )
    record = PersistenceBoundaryRecord(
        contract_version=PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION,
        object_type=object_type,
        object_key=object_key,
        project_key=project_key,
        identity_ref=build_identity_ref(project_key=project_key, object_type=object_type, object_key=object_key),
        visibility_scope=visibility_scope,
        lifecycle_state=lifecycle_state,
        governance=MappingProxyType(
            {
                "review_state": review_state,
                "visibility_scope": visibility_scope,
                "lifecycle_state": lifecycle_state,
                "human_final_acceptance_required": review_state
                in {contracts.REVIEW_STATE_HUMAN_CONFIRMED, contracts.REVIEW_STATE_DEPRECATED},
            }
        ),
        writing_handoff_refs=handoff_refs,
        payload=MappingProxyType(payload),
        updated_at=updated_at,
    )
    validate_persistence_boundary_record(record)
    return record


def build_identity_ref(*, project_key: str, object_type: str, object_key: str) -> str:
    normalized_project = str(project_key or "").strip()
    normalized_type = str(object_type or "").strip()
    normalized_key = str(object_key or "").strip()
    if not normalized_project or not normalized_type or not normalized_key:
        raise TypedKnowledgePersistenceBoundaryError("persistence_boundary_missing_identity_ref_part")
    return f"{normalized_project}:{normalized_type}:{normalized_key}"


def persist_typed_knowledge_boundary(
    *,
    type_nodes: tuple[contracts.TypeNode, ...],
    knowledge_items: tuple[contracts.KnowledgeItem, ...],
    topic_clusters: tuple[contracts.TopicCluster, ...],
    booklets: tuple[contracts.Booklet, ...],
    writing_handoffs: tuple[contracts.WritingKnowledgeHandoff, ...] = (),
    repository: InMemoryTypedKnowledgeRepository | None = None,
    project_key: str | None = None,
    write_time: str | None = None,
) -> dict[str, Any]:
    contracts.validate_relationships(
        type_nodes=type_nodes,
        knowledge_items=knowledge_items,
        topic_clusters=topic_clusters,
        booklets=booklets,
    )
    repo = repository or InMemoryTypedKnowledgeRepository()
    records = tuple(
        build_persistence_boundary_record(item, writing_handoffs=writing_handoffs)
        for item in (*type_nodes, *knowledge_items, *topic_clusters, *booklets)
    )
    writes = tuple(repo.upsert_record(record, write_time=write_time) for record in records)
    return build_persistence_api_envelope(repository=repo, project_key=project_key, writes=writes)


def build_persistence_api_envelope(
    *,
    repository: InMemoryTypedKnowledgeRepository,
    project_key: str | None = None,
    writes: tuple[PersistenceWriteResult, ...] = (),
) -> dict[str, Any]:
    records = repository.list_records(project_key=project_key)
    record_payloads = [serialize_persistence_boundary_record(record) for record in records]
    writing_refs = [
        _serialize_writing_handoff_ref(ref)
        for record in records
        for ref in record.writing_handoff_refs
    ]
    envelope = {
        "status": "ok",
        "data": {
            "contract_version": PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION,
            "repository": {
                "repository_ref": repository.repository_ref,
                "logical_table": repository.logical_table,
                "persistence_mode": "in_memory_contract",
                "live_db_write": False,
            },
            "records": record_payloads,
            "writing_handoff_refs": writing_refs,
            "writes": [serialize_persistence_write_result(write) for write in writes],
        },
        "error": None,
        "meta": {
            "contract_readiness": "ready",
            "closed_slice": list(PERSISTENCE_API_BOUNDARY_CLOSED_SLICE),
            "readiness": {
                "repository_contract": True,
                "api_envelope": True,
                "writing_handoff_refs": True,
                "live_db_persistence": False,
                "public_api_route": False,
                "governance_ui": False,
            },
            "remaining_live_gaps": list(PERSISTENCE_API_BOUNDARY_REMAINING_LIVE_GAPS),
            "non_goal": "no_live_db_write_no_product_ui",
        },
    }
    validate_persistence_api_envelope(envelope)
    return envelope


def validate_persistence_boundary_record(record: PersistenceBoundaryRecord) -> None:
    if record.contract_version != PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION:
        raise TypedKnowledgePersistenceBoundaryError("persistence_boundary_contract_version_mismatch")
    if record.object_type not in ALLOWED_OBJECT_TYPES:
        raise TypedKnowledgePersistenceBoundaryError(f"persistence_boundary_unknown_object_type:{record.object_type}")
    expected_identity_ref = build_identity_ref(
        project_key=record.project_key,
        object_type=record.object_type,
        object_key=record.object_key,
    )
    if record.identity_ref != expected_identity_ref:
        raise TypedKnowledgePersistenceBoundaryError("persistence_boundary_identity_ref_mismatch")
    if record.visibility_scope not in {
        contracts.VISIBILITY_SCOPE_INTERNAL_ONLY,
        contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY,
    }:
        raise TypedKnowledgePersistenceBoundaryError("persistence_boundary_invalid_visibility_scope")
    if record.lifecycle_state not in ALLOWED_LIFECYCLE_STATES:
        raise TypedKnowledgePersistenceBoundaryError("persistence_boundary_invalid_lifecycle_state")
    review_state = str(record.governance.get("review_state") or "")
    if review_state not in contracts.ALLOWED_REVIEW_STATES:
        raise TypedKnowledgePersistenceBoundaryError("persistence_boundary_invalid_review_state")
    if contracts.REVIEW_STATE_VISIBILITY_SCOPE[review_state] != record.visibility_scope:
        raise TypedKnowledgePersistenceBoundaryError("persistence_boundary_visibility_scope_mismatch")
    if REVIEW_STATE_LIFECYCLE_STATE[review_state] != record.lifecycle_state:
        raise TypedKnowledgePersistenceBoundaryError("persistence_boundary_lifecycle_state_mismatch")
    if record.writing_handoff_refs and record.object_type != OBJECT_TYPE_KNOWLEDGE_ITEM:
        raise TypedKnowledgePersistenceBoundaryError("persistence_boundary_handoff_refs_only_for_knowledge_items")
    for ref in record.writing_handoff_refs:
        _validate_writing_handoff_ref(ref, expected_knowledge_item_key=record.object_key)


def validate_persistence_api_envelope(envelope: Mapping[str, Any]) -> None:
    if not isinstance(envelope, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_not_mapping")
    if envelope.get("status") != "ok":
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_status_not_ok")
    data = envelope.get("data")
    meta = envelope.get("meta")
    if not isinstance(data, Mapping) or not isinstance(meta, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_missing_data_or_meta")
    if data.get("contract_version") != PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION:
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_contract_version_mismatch")
    repository = data.get("repository")
    if not isinstance(repository, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_missing_repository")
    if repository.get("persistence_mode") != "in_memory_contract" or repository.get("live_db_write") is not False:
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_live_db_claim_forbidden")
    readiness = meta.get("readiness")
    if not isinstance(readiness, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_missing_readiness")
    if readiness.get("repository_contract") is not True or readiness.get("api_envelope") is not True:
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_contract_not_ready")
    if (
        readiness.get("live_db_persistence") is not False
        or readiness.get("public_api_route") is not False
        or readiness.get("governance_ui") is not False
    ):
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_overclaims_live_completion")
    remaining_gaps = tuple(meta.get("remaining_live_gaps") or ())
    for required_gap in PERSISTENCE_API_BOUNDARY_REMAINING_LIVE_GAPS:
        if required_gap not in remaining_gaps:
            raise TypedKnowledgePersistenceBoundaryError(
                f"persistence_api_envelope_missing_remaining_gap:{required_gap}"
            )
    records = data.get("records")
    if not isinstance(records, list) or not records:
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_missing_records")
    for record in records:
        if not isinstance(record, Mapping):
            raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_invalid_record")
        for field_name in PERSISTENCE_API_BOUNDARY_FIELDS:
            if field_name not in record:
                raise TypedKnowledgePersistenceBoundaryError(
                    f"persistence_api_envelope_record_missing_field:{field_name}"
                )
        if record.get("contract_version") != PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION:
            raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_record_version_mismatch")
    writes = data.get("writes")
    if not isinstance(writes, list):
        raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_invalid_writes")
    for write in writes:
        if not isinstance(write, Mapping) or write.get("live_db_write") is not False:
            raise TypedKnowledgePersistenceBoundaryError("persistence_api_envelope_live_write_claim_forbidden")


def serialize_persistence_boundary_record(record: PersistenceBoundaryRecord) -> dict[str, Any]:
    validate_persistence_boundary_record(record)
    return {
        "contract_version": record.contract_version,
        "object_type": record.object_type,
        "object_key": record.object_key,
        "project_key": record.project_key,
        "identity_ref": record.identity_ref,
        "visibility_scope": record.visibility_scope,
        "lifecycle_state": record.lifecycle_state,
        "governance": _json_safe(record.governance),
        "writing_handoff_refs": [_serialize_writing_handoff_ref(ref) for ref in record.writing_handoff_refs],
        "payload": _json_safe(record.payload),
        "updated_at": record.updated_at,
    }


def serialize_persistence_write_result(result: PersistenceWriteResult) -> dict[str, Any]:
    return {
        "contract_version": result.contract_version,
        "repository_ref": result.repository_ref,
        "logical_table": result.logical_table,
        "operation": result.operation,
        "identity_ref": result.identity_ref,
        "object_type": result.object_type,
        "object_key": result.object_key,
        "status_before": result.status_before,
        "status_after": result.status_after,
        "visibility_scope": result.visibility_scope,
        "write_time": result.write_time,
        "payload_ref": result.payload_ref,
        "live_db_write": result.live_db_write,
    }


def build_sample_boundary_envelope(*, project_key: str = "demo_proj") -> dict[str, Any]:
    normalized_project_key = str(project_key or "").strip() or "demo_proj"
    type_node = contracts.TypeNode(
        key="type:market_signal",
        project_key=normalized_project_key,
        label="Market Signal",
        review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
    )
    topic_cluster = contracts.TopicCluster(
        key="topic:robotics",
        project_key=normalized_project_key,
        label="Robotics",
        knowledge_item_keys=("ki:robotics-policy",),
        review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
    )
    booklet = contracts.Booklet(
        key="booklet:q2-review",
        project_key=normalized_project_key,
        title="Q2 Review",
        included_type_node_keys=(type_node.key,),
        included_topic_cluster_keys=(topic_cluster.key,),
        included_knowledge_item_keys=("ki:robotics-policy",),
        review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
    )
    item = contracts.KnowledgeItem(
        key="ki:robotics-policy",
        project_key=normalized_project_key,
        canonical_statement="Humanoid robotics investment is shifting toward industrial pilots.",
        primary_type_node_key=type_node.key,
        evidence_refs=("doc:robotics:42",),
        topic_cluster_keys=(topic_cluster.key,),
        booklet_keys=(booklet.key,),
        review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
        quality_grade=contracts.QUALITY_GRADE_GOLD,
        locale="en",
        updated_at="2026-05-22T00:00:00Z",
    )
    handoff = contracts.build_writing_knowledge_handoff(
        contracts.build_downstream_contract_draft(item),
        selection_hash="selection:robotics",
        selection_text="robotics investment",
    )
    return persist_typed_knowledge_boundary(
        type_nodes=(type_node,),
        knowledge_items=(item,),
        topic_clusters=(topic_cluster,),
        booklets=(booklet,),
        writing_handoffs=(handoff,),
        project_key=normalized_project_key,
        write_time="2026-05-22T00:00:00Z",
    )


def build_public_api_route_contract_envelope(*, project_key: str = "demo_proj") -> dict[str, Any]:
    boundary_envelope = build_sample_boundary_envelope(project_key=project_key)
    envelope = {
        "status": "ok",
        "data": {
            "contract_version": PUBLIC_API_ROUTE_CONTRACT_VERSION,
            "route": {
                "method": "GET",
                "path": PUBLIC_API_ROUTE_PATH,
                "tag": "typed_knowledge",
                "public_api_route": True,
                "live_db_backed": False,
                "response_contract": PUBLIC_API_ROUTE_CONTRACT_VERSION,
            },
            "persistence_boundary": boundary_envelope["data"],
            "persistence_boundary_meta": boundary_envelope["meta"],
            "boundary_fingerprint": boundary_fingerprint(boundary_envelope),
        },
        "error": None,
        "meta": {
            "contract_readiness": "ready",
            "closed_slice": list(PUBLIC_API_ROUTE_CLOSED_SLICE),
            "readiness": {
                "public_api_route": True,
                "api_contract": True,
                "repository_contract": True,
                "live_db_persistence": False,
                "governance_ui": False,
            },
            "remaining_live_gaps": list(PUBLIC_API_ROUTE_REMAINING_LIVE_GAPS),
            "non_goal": "no_live_db_write_no_product_ui",
        },
    }
    validate_public_api_route_contract_envelope(envelope)
    return envelope


def validate_public_api_route_contract_envelope(envelope: Mapping[str, Any]) -> None:
    if not isinstance(envelope, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_envelope_not_mapping")
    if envelope.get("status") != "ok":
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_envelope_status_not_ok")
    data = envelope.get("data")
    meta = envelope.get("meta")
    if not isinstance(data, Mapping) or not isinstance(meta, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_envelope_missing_data_or_meta")
    if data.get("contract_version") != PUBLIC_API_ROUTE_CONTRACT_VERSION:
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_contract_version_mismatch")
    route = data.get("route")
    if not isinstance(route, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_missing_route")
    if route.get("method") != "GET" or route.get("path") != PUBLIC_API_ROUTE_PATH:
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_path_mismatch")
    if route.get("public_api_route") is not True or route.get("live_db_backed") is not False:
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_readiness_mismatch")

    persistence_boundary = data.get("persistence_boundary")
    if not isinstance(persistence_boundary, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_missing_persistence_boundary")
    repository = persistence_boundary.get("repository")
    if not isinstance(repository, Mapping) or repository.get("live_db_write") is not False:
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_live_db_overclaim")
    records = persistence_boundary.get("records")
    if not isinstance(records, list) or not records:
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_missing_records")

    readiness = meta.get("readiness")
    if not isinstance(readiness, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_missing_readiness")
    if readiness.get("public_api_route") is not True or readiness.get("api_contract") is not True:
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_contract_not_ready")
    if readiness.get("live_db_persistence") is not False or readiness.get("governance_ui") is not False:
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_live_completion_overclaim")

    remaining_gaps = tuple(meta.get("remaining_live_gaps") or ())
    for required_gap in PUBLIC_API_ROUTE_REMAINING_LIVE_GAPS:
        if required_gap not in remaining_gaps:
            raise TypedKnowledgePersistenceBoundaryError(f"public_api_route_missing_remaining_gap:{required_gap}")
    if "public_typed_knowledge_api_route_not_implemented" in remaining_gaps:
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_keeps_closed_gap_open")


def _object_parts(
    obj: contracts.TypeNode | contracts.KnowledgeItem | contracts.TopicCluster | contracts.Booklet,
) -> tuple[str, str, str, str, dict[str, Any], str | None]:
    if isinstance(obj, contracts.TypeNode):
        contracts.validate_type_node(obj)
        return (
            OBJECT_TYPE_TYPE_NODE,
            obj.key,
            obj.project_key,
            obj.review_state,
            {
                "label": obj.label,
                "primary_parent_key": obj.primary_parent_key,
                "aliases": tuple(obj.aliases),
            },
            None,
        )
    if isinstance(obj, contracts.KnowledgeItem):
        contracts.validate_knowledge_item(obj)
        return (
            OBJECT_TYPE_KNOWLEDGE_ITEM,
            obj.key,
            obj.project_key,
            obj.review_state,
            {
                "canonical_statement": obj.canonical_statement.strip(),
                "primary_type_node_key": obj.primary_type_node_key,
                "topic_cluster_keys": tuple(obj.topic_cluster_keys),
                "booklet_keys": tuple(obj.booklet_keys),
                "quality_grade": obj.quality_grade,
                "locale": obj.locale,
                "locale_variants": dict(obj.locale_variants),
                "evidence_refs": tuple(obj.evidence_refs),
            },
            obj.updated_at.strip() if obj.updated_at is not None else None,
        )
    if isinstance(obj, contracts.TopicCluster):
        contracts.validate_topic_cluster(obj)
        return (
            OBJECT_TYPE_TOPIC_CLUSTER,
            obj.key,
            obj.project_key,
            obj.review_state,
            {
                "label": obj.label,
                "summary": obj.summary,
                "membership_mode": contracts.TOPIC_CLUSTER_MEMBERSHIP_MODE,
                "knowledge_item_keys": tuple(obj.knowledge_item_keys),
            },
            None,
        )
    if isinstance(obj, contracts.Booklet):
        contracts.validate_booklet(obj)
        return (
            OBJECT_TYPE_BOOKLET,
            obj.key,
            obj.project_key,
            obj.review_state,
            {
                "title": obj.title,
                "description": obj.description,
                "membership_mode": contracts.BOOKLET_MEMBERSHIP_MODE,
                "included_type_node_keys": tuple(obj.included_type_node_keys),
                "included_topic_cluster_keys": tuple(obj.included_topic_cluster_keys),
                "included_knowledge_item_keys": tuple(obj.included_knowledge_item_keys),
            },
            None,
        )
    raise TypedKnowledgePersistenceBoundaryError("persistence_boundary_unsupported_object")


def _validate_writing_handoff_ref(ref: WritingHandoffRef, *, expected_knowledge_item_key: str) -> None:
    if ref.contract_version != contracts.WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION:
        raise TypedKnowledgePersistenceBoundaryError("writing_handoff_ref_contract_version_mismatch")
    if ref.knowledge_item_key != expected_knowledge_item_key:
        raise TypedKnowledgePersistenceBoundaryError("writing_handoff_ref_knowledge_item_mismatch")
    if ref.consumer != "writing.keyword_card":
        raise TypedKnowledgePersistenceBoundaryError("writing_handoff_ref_consumer_mismatch")
    if ref.card_source_type != "resource":
        raise TypedKnowledgePersistenceBoundaryError("writing_handoff_ref_card_source_type_mismatch")
    if ref.selection_hash is not None and not ref.selection_hash.strip():
        raise TypedKnowledgePersistenceBoundaryError("writing_handoff_ref_invalid_selection_hash")


def _serialize_writing_handoff_ref(ref: WritingHandoffRef) -> dict[str, Any]:
    return {
        "contract_version": ref.contract_version,
        "knowledge_item_key": ref.knowledge_item_key,
        "consumer": ref.consumer,
        "card_source_type": ref.card_source_type,
        "selection_hash": ref.selection_hash,
        "selection_text": ref.selection_text,
    }


def _normalize_write_time(write_time: str | None, updated_at: str | None) -> str:
    normalized = str(write_time or updated_at or "").strip()
    if normalized:
        return normalized
    return "contract-time://typed-knowledge-persistence-api-boundary"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def boundary_fingerprint(envelope: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        _json_safe(envelope),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", errors="ignore")
    return hashlib.sha1(serialized, usedforsecurity=False).hexdigest()[:16]
