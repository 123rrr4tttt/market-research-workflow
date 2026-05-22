from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Mapping

from . import contracts


PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION: Final[str] = "typed_knowledge.persistence_api_boundary.v1"
PERSISTENCE_WRITE_RESULT_CONTRACT_VERSION: Final[str] = "typed_knowledge.persistence_write_result.v1"
PUBLIC_API_ROUTE_CONTRACT_VERSION: Final[str] = "typed_knowledge.public_api_route_contract.v1"
DURABLE_REPOSITORY_READBACK_CONTRACT_VERSION: Final[str] = "typed_knowledge.durable_repository_readback.v1"
PERSISTED_CARD_REQUEST_RESPONSE_READBACK_CONTRACT_VERSION: Final[str] = (
    "typed_knowledge.persisted_card_request_response_readback.v1"
)
PUBLIC_API_ROUTE_PATH: Final[str] = "/api/v1/typed-knowledge/persistence-boundary"
WRITING_KEYWORD_CARD_ROUTE_PATH: Final[str] = "/api/v1/writing/keyword-cards"
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
ALLOWED_CONTRACT_PERSISTENCE_MODES: Final[tuple[str, ...]] = (
    "in_memory_contract",
    "jsonl_durable_contract",
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
    "persisted_card_request_response_readback",
    "status_data_error_meta_route_envelope",
    "live_db_overclaim_guard",
)
PUBLIC_API_ROUTE_REMAINING_LIVE_GAPS: Final[tuple[str, ...]] = (
    "live_db_persistence_not_implemented",
    "governance_ui_not_implemented",
    "migration_and_backfill_not_executed",
    "live_db_backed_typed_knowledge_readback_not_verified",
)
PERSISTED_CARD_READBACK_CLOSED_SLICE: Final[tuple[str, ...]] = (
    "typed_knowledge_api_boundary_persisted_context",
    "persisted_document_metadata_request_payload",
    "writing_keyword_card_request_shape",
    "typed_knowledge_resource_card_response_shape",
    "live_db_api_ui_overclaim_guard",
)
PERSISTED_CARD_READBACK_REMAINING_LIVE_GAPS: Final[tuple[str, ...]] = (
    "live_db_persistence_not_implemented",
    "live_db_backed_typed_knowledge_readback_not_verified",
    "live_api_request_response_closure_not_verified",
    "live_browser_ui_readback_not_verified",
    "governance_ui_not_implemented",
    "migration_and_backfill_not_executed",
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
        self.persistence_mode = "in_memory_contract"
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


class JsonlTypedKnowledgeRepository(InMemoryTypedKnowledgeRepository):
    """Small durable repository for readback contracts without claiming live DB writes."""

    def __init__(
        self,
        *,
        storage_dir: str | Path,
        repository_ref: str | None = None,
        logical_table: str = DEFAULT_LOGICAL_TABLE,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        super().__init__(
            repository_ref=repository_ref or f"jsonl://{self.storage_dir.as_posix()}",
            logical_table=logical_table,
        )
        self.persistence_mode = "jsonl_durable_contract"
        self._records_path = self.storage_dir / "typed_knowledge_records.jsonl"
        self._writes_path = self.storage_dir / "typed_knowledge_writes.jsonl"
        self._load()

    def _load(self) -> None:
        self._records = {}
        self._writes = []
        for row in _read_jsonl(self._records_path):
            record = deserialize_persistence_boundary_record(row)
            self._records[record.identity_ref] = record
        for row in _read_jsonl(self._writes_path):
            self._writes.append(deserialize_persistence_write_result(row))

    def reopen(self) -> "JsonlTypedKnowledgeRepository":
        return JsonlTypedKnowledgeRepository(
            storage_dir=self.storage_dir,
            repository_ref=self.repository_ref,
            logical_table=self.logical_table,
        )

    def upsert_record(
        self,
        record: PersistenceBoundaryRecord,
        *,
        write_time: str | None = None,
        operation: str = "upsert",
    ) -> PersistenceWriteResult:
        result = super().upsert_record(record, write_time=write_time, operation=operation)
        _append_jsonl(self._records_path, serialize_persistence_boundary_record(record))
        _append_jsonl(self._writes_path, serialize_persistence_write_result(result))
        return result


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
                "persistence_mode": getattr(repository, "persistence_mode", "in_memory_contract"),
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
    if (
        repository.get("persistence_mode") not in ALLOWED_CONTRACT_PERSISTENCE_MODES
        or repository.get("live_db_write") is not False
    ):
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


def deserialize_persistence_boundary_record(payload: Mapping[str, Any]) -> PersistenceBoundaryRecord:
    refs_payload = payload.get("writing_handoff_refs") or ()
    refs = tuple(
        WritingHandoffRef(
            contract_version=str(ref.get("contract_version") or ""),
            knowledge_item_key=str(ref.get("knowledge_item_key") or ""),
            consumer=str(ref.get("consumer") or ""),
            card_source_type=str(ref.get("card_source_type") or ""),
            selection_hash=ref.get("selection_hash"),
            selection_text=ref.get("selection_text"),
        )
        for ref in refs_payload
        if isinstance(ref, Mapping)
    )
    record = PersistenceBoundaryRecord(
        contract_version=str(payload.get("contract_version") or ""),
        object_type=str(payload.get("object_type") or ""),
        object_key=str(payload.get("object_key") or ""),
        project_key=str(payload.get("project_key") or ""),
        identity_ref=str(payload.get("identity_ref") or ""),
        visibility_scope=str(payload.get("visibility_scope") or ""),
        lifecycle_state=str(payload.get("lifecycle_state") or ""),
        governance=MappingProxyType(dict(payload.get("governance") or {})),
        writing_handoff_refs=refs,
        payload=MappingProxyType(dict(payload.get("payload") or {})),
        updated_at=payload.get("updated_at"),
    )
    validate_persistence_boundary_record(record)
    return record


def deserialize_persistence_write_result(payload: Mapping[str, Any]) -> PersistenceWriteResult:
    result = PersistenceWriteResult(
        contract_version=str(payload.get("contract_version") or ""),
        repository_ref=str(payload.get("repository_ref") or ""),
        logical_table=str(payload.get("logical_table") or ""),
        operation=str(payload.get("operation") or ""),
        identity_ref=str(payload.get("identity_ref") or ""),
        object_type=str(payload.get("object_type") or ""),
        object_key=str(payload.get("object_key") or ""),
        status_before=payload.get("status_before"),
        status_after=str(payload.get("status_after") or ""),
        visibility_scope=str(payload.get("visibility_scope") or ""),
        write_time=str(payload.get("write_time") or ""),
        payload_ref=str(payload.get("payload_ref") or ""),
        live_db_write=bool(payload.get("live_db_write")),
    )
    if result.contract_version != PERSISTENCE_WRITE_RESULT_CONTRACT_VERSION:
        raise TypedKnowledgePersistenceBoundaryError("persistence_write_result_contract_version_mismatch")
    if result.live_db_write:
        raise TypedKnowledgePersistenceBoundaryError("persistence_write_result_live_db_claim_forbidden")
    if result.status_after not in ALLOWED_LIFECYCLE_STATES:
        raise TypedKnowledgePersistenceBoundaryError("persistence_write_result_invalid_status_after")
    return result


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
    persisted_card_readback = build_persisted_card_request_response_readback(
        project_key=project_key,
        boundary_envelope=boundary_envelope,
    )
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
            "persisted_card_request_response_readback": persisted_card_readback,
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
                "persisted_card_request_response_readback": True,
                "live_db_persistence": False,
                "live_api_closure": False,
                "live_ui_closure": False,
                "governance_ui": False,
            },
            "remaining_live_gaps": list(PUBLIC_API_ROUTE_REMAINING_LIVE_GAPS),
            "non_goal": "no_live_db_write_no_product_ui",
        },
    }
    validate_public_api_route_contract_envelope(envelope)
    return envelope


def build_persisted_card_request_response_readback(
    *,
    project_key: str = "demo_proj",
    boundary_envelope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a repo-local persisted-card request/response readback contract.

    The returned payload mirrors the persisted Writing Workbench card request path
    while staying inside deterministic typed-knowledge API boundary data.
    """

    normalized_project_key = str(project_key or "").strip() or "demo_proj"
    source_envelope = boundary_envelope or build_sample_boundary_envelope(project_key=normalized_project_key)
    validate_persistence_api_envelope(source_envelope)
    handoff = _build_writing_handoff_from_boundary_envelope(source_envelope)
    typed_context = contracts.build_writing_knowledge_context_envelope((handoff,))
    query = handoff.selection_text or handoff.canonical_statement
    normalized_query = _normalize_card_query(query)
    card_url = f"typed-knowledge://{handoff.knowledge_item_key}"
    card_id = _keyword_card_id(
        source_type="resource",
        title=handoff.canonical_statement,
        url=card_url,
        normalized_query=normalized_query,
    )
    persisted_document = {
        "document_ref": f"repo-local://writing-workbench/{normalized_project_key}/wave19-typed-card",
        "project_key": normalized_project_key,
        "metadata_json": {
            "typed_knowledge_context": typed_context,
        },
        "source": "typed_knowledge_api_boundary_fixture",
        "live_db_document": False,
    }
    request_body = {
        "project_key": normalized_project_key,
        "query": query,
        "selection_hash": handoff.selection_hash,
        "limit": 10,
        "sources": ["document", "resource", "graph"],
        "context": {
            "contract_version": "writing.context_boundary.e3.v1",
            "typed_knowledge_context": typed_context,
        },
    }
    response_body = {
        "cards": [
            {
                "card_id": card_id,
                "source_type": "resource",
                "title": handoff.canonical_statement,
                "snippet": handoff.canonical_statement,
                "url": card_url,
                "score": 0.78,
                "publisher": "typed_knowledge",
                "evidence": handoff.canonical_statement,
                "relevance_tags": [normalized_query],
                "credibility": 0.78,
                "quick_actions": ["insert_quote", "insert_summary", "open_detail"],
                "extra": {
                    "handoff_source": "typed_knowledge",
                    "typed_knowledge_contract_version": contracts.WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION,
                    "knowledge_item_key": handoff.knowledge_item_key,
                    "primary_type_node_key": handoff.primary_type_node_key,
                    "topic_cluster_keys": list(handoff.topic_cluster_keys),
                    "booklet_keys": list(handoff.booklet_keys),
                    "review_state": handoff.review_state,
                    "quality_grade": handoff.quality_grade,
                    "locale": handoff.locale,
                    "evidence_refs": list(handoff.evidence_refs),
                    "visibility_scope": handoff.visibility_scope,
                    "selection_hash": handoff.selection_hash,
                    "selection_text": handoff.selection_text,
                    "facets": _json_safe(handoff.facets),
                    "handoff_payload": contracts.serialize_writing_knowledge_handoff(handoff),
                },
            }
        ],
        "selection_hash": _selection_hash(normalized_project_key, query),
        "suggested_queries": [normalized_query],
        "search_backends_used": [],
        "source_count": {"document": 0, "resource": 1, "graph": 0},
        "dedupe_count": 0,
        "context_boundary": {
            "contract_version": "writing.context_boundary.e3.v1",
            "typed_knowledge_context_attached": True,
            "typed_knowledge_context_count": 1,
            "typed_knowledge_boundary_rule": "consume_typed_knowledge_handoff_as_resource_card_only",
        },
        "dependency_gate": {
            "contract_version": "writing.cross_theme_gate.e8.v1",
            "passed": True,
            "typed_knowledge": {
                "mode": "optional_consume_only",
                "attached": True,
                "consumer": "writing.keyword_card",
                "card_source_type": "resource",
            },
        },
        "cache_hit": False,
    }
    readback = {
        "contract_version": PERSISTED_CARD_REQUEST_RESPONSE_READBACK_CONTRACT_VERSION,
        "typed_knowledge_api_boundary": {
            "route_path": PUBLIC_API_ROUTE_PATH,
            "contract_version": PUBLIC_API_ROUTE_CONTRACT_VERSION,
            "boundary_fingerprint": boundary_fingerprint(source_envelope),
            "live_db_backed": False,
        },
        "persisted_document": persisted_document,
        "keyword_card_request": {
            "method": "POST",
            "path": WRITING_KEYWORD_CARD_ROUTE_PATH,
            "source": "persisted_writing_document_metadata",
            "body": request_body,
        },
        "keyword_card_response": {
            "response_contract": "KeywordCardListResponse",
            "source": "repo_local_expected_response_shape",
            "body": response_body,
        },
        "readback": {
            "request_uses_persisted_metadata_json": True,
            "typed_context_contract": contracts.WRITING_KNOWLEDGE_CONTEXT_ENVELOPE_VERSION,
            "handoff_contract": contracts.WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION,
            "card_id": card_id,
            "card_source_type": "resource",
            "publisher": "typed_knowledge",
            "knowledge_item_key": handoff.knowledge_item_key,
            "selection_hash": handoff.selection_hash,
            "request_response_readback": True,
        },
        "meta": {
            "contract_readiness": "ready",
            "closed_slice": list(PERSISTED_CARD_READBACK_CLOSED_SLICE),
            "readiness": {
                "repo_local_persisted_card_readback": True,
                "typed_knowledge_api_boundary": True,
                "writing_keyword_card_request_shape": True,
                "live_db_persistence": False,
                "live_api_closure": False,
                "live_ui_closure": False,
                "governance_ui": False,
            },
            "remaining_live_gaps": list(PERSISTED_CARD_READBACK_REMAINING_LIVE_GAPS),
            "non_goal": "no_live_db_no_live_api_no_live_ui_closure",
        },
    }
    validate_persisted_card_request_response_readback(readback)
    return readback


def check_durable_repository_readback_contract(
    *,
    repository: JsonlTypedKnowledgeRepository,
    project_key: str = "demo_proj",
) -> dict[str, Any]:
    """Validate JSONL reopen/readback without claiming live DB/API/UI closure."""

    envelope = build_sample_boundary_envelope(project_key=project_key)
    sample_records = tuple(deserialize_persistence_boundary_record(record) for record in envelope["data"]["records"])
    writes = tuple(
        repository.upsert_record(record, write_time="2026-05-22T00:00:00Z")
        for record in sample_records
    )
    reopened = repository.reopen()
    readback_envelope = build_persistence_api_envelope(repository=reopened, project_key=project_key, writes=writes)
    readback_records = readback_envelope["data"]["records"]
    sample_identity_refs = sorted(record.identity_ref for record in sample_records)
    readback_identity_refs = sorted(record["identity_ref"] for record in readback_records)
    write_identity_refs = sorted(write.identity_ref for write in reopened.list_writes())
    blockers: list[str] = []

    if readback_identity_refs != sample_identity_refs:
        blockers.append("durable_repository_identity_readback_mismatch")
    if not set(sample_identity_refs).issubset(set(write_identity_refs)):
        blockers.append("durable_repository_write_readback_mismatch")
    if readback_envelope["data"]["repository"]["persistence_mode"] != "jsonl_durable_contract":
        blockers.append("durable_repository_persistence_mode_mismatch")
    if any(write["live_db_write"] for write in readback_envelope["data"]["writes"]):
        blockers.append("durable_repository_must_not_claim_live_db_write")
    if readback_envelope["meta"]["readiness"]["live_db_persistence"] is not False:
        blockers.append("durable_repository_must_keep_live_db_gap_open")

    result = {
        "contract_version": DURABLE_REPOSITORY_READBACK_CONTRACT_VERSION,
        "status": "fail" if blockers else "pass",
        "blockers": blockers,
        "closed_slice": [
            "jsonl_repository_write_readback",
            "typed_knowledge_object_reopen_readback",
            "write_result_reopen_readback",
            "status_data_error_meta_envelope_preserved",
        ],
        "repository_ref": reopened.repository_ref,
        "logical_table": reopened.logical_table,
        "storage_kind": "jsonl",
        "durable_readback": not blockers,
        "live_db_write": False,
        "live_db_persistence": False,
        "public_api_route": True,
        "governance_ui": False,
        "readback_identity_refs": readback_identity_refs,
        "write_identity_refs": write_identity_refs,
        "readback_fingerprint": boundary_fingerprint(readback_envelope),
        "remaining_live_gaps": [
            "live_db_persistence_not_implemented",
            "live_db_backed_typed_knowledge_readback_not_verified",
            "governance_ui_not_implemented",
            "migration_and_backfill_not_executed",
        ],
    }
    return result


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
    readback = data.get("persisted_card_request_response_readback")
    if not isinstance(readback, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_missing_persisted_card_readback")
    validate_persisted_card_request_response_readback(readback)

    readiness = meta.get("readiness")
    if not isinstance(readiness, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_missing_readiness")
    if readiness.get("public_api_route") is not True or readiness.get("api_contract") is not True:
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_contract_not_ready")
    if (
        readiness.get("live_db_persistence") is not False
        or readiness.get("governance_ui") is not False
        or readiness.get("live_api_closure") is not False
        or readiness.get("live_ui_closure") is not False
    ):
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_live_completion_overclaim")

    remaining_gaps = tuple(meta.get("remaining_live_gaps") or ())
    for required_gap in PUBLIC_API_ROUTE_REMAINING_LIVE_GAPS:
        if required_gap not in remaining_gaps:
            raise TypedKnowledgePersistenceBoundaryError(f"public_api_route_missing_remaining_gap:{required_gap}")
    if "public_typed_knowledge_api_route_not_implemented" in remaining_gaps:
        raise TypedKnowledgePersistenceBoundaryError("public_api_route_keeps_closed_gap_open")


def validate_persisted_card_request_response_readback(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_not_mapping")
    if payload.get("contract_version") != PERSISTED_CARD_REQUEST_RESPONSE_READBACK_CONTRACT_VERSION:
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_contract_version_mismatch")

    api_boundary = payload.get("typed_knowledge_api_boundary")
    if not isinstance(api_boundary, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_missing_api_boundary")
    if api_boundary.get("route_path") != PUBLIC_API_ROUTE_PATH or api_boundary.get("live_db_backed") is not False:
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_api_boundary_overclaim")

    persisted_document = payload.get("persisted_document")
    if not isinstance(persisted_document, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_missing_document")
    metadata_json = persisted_document.get("metadata_json")
    if not isinstance(metadata_json, Mapping) or persisted_document.get("live_db_document") is not False:
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_invalid_persisted_document")
    typed_context = metadata_json.get("typed_knowledge_context")
    if not isinstance(typed_context, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_missing_typed_context")
    contracts.validate_writing_knowledge_context_envelope(typed_context)

    request = payload.get("keyword_card_request")
    if not isinstance(request, Mapping) or request.get("path") != WRITING_KEYWORD_CARD_ROUTE_PATH:
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_invalid_request_route")
    request_body = request.get("body")
    if not isinstance(request_body, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_missing_request_body")
    request_context = request_body.get("context")
    if not isinstance(request_context, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_missing_request_context")
    if request_context.get("typed_knowledge_context") != typed_context:
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_context_mismatch")
    if "resource" not in tuple(request_body.get("sources") or ()):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_request_missing_resource_source")

    response = payload.get("keyword_card_response")
    if not isinstance(response, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_missing_response")
    response_body = response.get("body")
    if not isinstance(response_body, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_missing_response_body")
    cards = response_body.get("cards")
    if not isinstance(cards, list) or len(cards) != 1:
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_expected_one_card")
    card = cards[0]
    if not isinstance(card, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_invalid_card")
    if card.get("source_type") != "resource" or card.get("publisher") != "typed_knowledge":
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_card_boundary_mismatch")
    extra = card.get("extra")
    if not isinstance(extra, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_missing_card_extra")
    if extra.get("handoff_source") != "typed_knowledge" or extra.get("visibility_scope") != "downstream_ready":
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_card_extra_mismatch")

    meta = payload.get("meta")
    if not isinstance(meta, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_missing_meta")
    readiness = meta.get("readiness")
    if not isinstance(readiness, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_missing_readiness")
    if readiness.get("repo_local_persisted_card_readback") is not True:
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_not_ready")
    if (
        readiness.get("live_db_persistence") is not False
        or readiness.get("live_api_closure") is not False
        or readiness.get("live_ui_closure") is not False
        or readiness.get("governance_ui") is not False
    ):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_live_completion_overclaim")
    remaining_gaps = tuple(meta.get("remaining_live_gaps") or ())
    for required_gap in PERSISTED_CARD_READBACK_REMAINING_LIVE_GAPS:
        if required_gap not in remaining_gaps:
            raise TypedKnowledgePersistenceBoundaryError(f"persisted_card_readback_missing_remaining_gap:{required_gap}")


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


def _build_writing_handoff_from_boundary_envelope(envelope: Mapping[str, Any]) -> contracts.WritingKnowledgeHandoff:
    data = envelope.get("data")
    if not isinstance(data, Mapping):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_source_missing_data")
    records = data.get("records")
    if not isinstance(records, list):
        raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_source_missing_records")
    for record in records:
        if not isinstance(record, Mapping) or record.get("object_type") != OBJECT_TYPE_KNOWLEDGE_ITEM:
            continue
        refs = record.get("writing_handoff_refs")
        if not isinstance(refs, list) or not refs:
            continue
        ref = refs[0]
        if not isinstance(ref, Mapping):
            continue
        payload = record.get("payload") if isinstance(record.get("payload"), Mapping) else {}
        governance = record.get("governance") if isinstance(record.get("governance"), Mapping) else {}
        item = contracts.KnowledgeItem(
            key=str(record.get("object_key") or ""),
            project_key=str(record.get("project_key") or ""),
            canonical_statement=str(payload.get("canonical_statement") or ""),
            primary_type_node_key=str(payload.get("primary_type_node_key") or ""),
            evidence_refs=_tuple_of_strings(payload.get("evidence_refs")),
            topic_cluster_keys=_tuple_of_strings(payload.get("topic_cluster_keys")),
            booklet_keys=_tuple_of_strings(payload.get("booklet_keys")),
            review_state=str(governance.get("review_state") or ""),
            quality_grade=_optional_payload_string(payload.get("quality_grade")),
            locale=_optional_payload_string(payload.get("locale")),
            locale_variants=dict(payload.get("locale_variants") or {})
            if isinstance(payload.get("locale_variants"), Mapping)
            else {},
            updated_at=_optional_payload_string(record.get("updated_at")),
        )
        return contracts.build_writing_knowledge_handoff(
            contracts.build_downstream_contract_draft(item),
            selection_hash=_optional_payload_string(ref.get("selection_hash")),
            selection_text=_optional_payload_string(ref.get("selection_text")),
        )
    raise TypedKnowledgePersistenceBoundaryError("persisted_card_readback_source_missing_handoff")


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _optional_payload_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_card_query(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _selection_hash(project_key: str, query: str) -> str:
    payload = f"{project_key}:{_normalize_card_query(query)}"
    return hashlib.sha1(
        payload.encode("utf-8", errors="ignore"),
        usedforsecurity=False,
    ).hexdigest()[:16]


def _keyword_card_id(*, source_type: str, title: str, url: str | None, normalized_query: str) -> str:
    payload = f"{source_type}|{title}|{url or ''}|{normalized_query}"
    return hashlib.sha1(
        payload.encode("utf-8", errors="ignore"),
        usedforsecurity=False,
    ).hexdigest()[:24]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise TypedKnowledgePersistenceBoundaryError(
                    f"typed_knowledge_jsonl_invalid_json:{path}:{line_number}"
                ) from exc
            if not isinstance(payload, dict):
                raise TypedKnowledgePersistenceBoundaryError(
                    f"typed_knowledge_jsonl_row_not_mapping:{path}:{line_number}"
                )
            rows.append(payload)
    return rows


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True))
        handle.write("\n")


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
