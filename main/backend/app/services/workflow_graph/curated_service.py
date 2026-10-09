from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Callable, Mapping, NoReturn, SupportsFloat, SupportsIndex, SupportsInt, TypedDict, TypeGuard
from uuid import uuid4

from app.services.ingest_config.service import get_config as get_ingest_config
from app.services.ingest_config.service import upsert_config as upsert_ingest_config
from app.services.projects import current_project_key
from app.services.workflow_graph.contracts import raise_workflow_graph_legacy, workflow_graph_failure
from app.services.workflow_graph.edit_contract import parse_graph_edit_draft_contract
from app.services.workflow_graph.governance_contract import (
    build_graph_edit_audit_record,
    build_graph_rollback_contract,
)

CONFIG_KEY = "workflow_graph_curated_v1"
CONFIG_TYPE = "workflow_graph_curated"
EVIDENCE_PACK_CONTRACT_VERSION = "graph_evidence_pack.v1"
HANDOFF_CONTRACT_VERSION = "graph_handoff.v1"
HANDOFF_PRODUCER = "workflow_graph.backend_bridge"


class _CuratedGraph(TypedDict):
    graph_id: str
    revision: int
    active_version_id: str | None
    draft: dict[str, object]
    current: dict[str, object]
    versions: dict[str, dict[str, object]]
    audits: list[dict[str, object]]
    updated_at: str
    last_sync_status: str


class _CuratedState(TypedDict):
    base_version: int
    graphs: dict[str, _CuratedGraph]


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _string_object_mapping(value: object) -> dict[str, object] | None:
    if not _is_object_mapping(value):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def _raise_curated_failure(
    code: str, message: str, *, exception_type: type[Exception] = ValueError
) -> NoReturn:
    failure = workflow_graph_failure(code, message, owner="workflow_graph.curated_service", public_exception=exception_type, public_message=message, field="curated", index=-1)
    raise_workflow_graph_legacy(failure, exception_type=exception_type)


class WorkflowGraphSyncConflictError(ValueError):
    def __init__(self, *, expected_revision: int, actual_revision: int) -> None:
        super().__init__(f"conflict: revision mismatch expected={expected_revision} actual={actual_revision}")
        self.expected_revision = int(expected_revision)
        self.actual_revision = int(actual_revision)

    def to_details(self) -> dict[str, object]:
        return {
            "category": "version_conflict",
            "expected_revision": self.expected_revision,
            "actual_revision": self.actual_revision,
        }


class WorkflowGraphObjectMissingError(KeyError):
    pass


class WorkflowGraphCuratedService:
    def get_graph(self, graph_id: str) -> dict[str, object]:
        gid = _normalize_graph_id(graph_id)
        state = self._load_state()
        graph = state["graphs"].get(gid)
        if graph is None:
            _raise_curated_failure("object_not_found", f"curated graph not found: {gid}", exception_type=WorkflowGraphObjectMissingError)
        return {
            "graph_id": gid,
            "revision": int(graph.get("revision") or 0),
            "active_version_id": graph.get("active_version_id"),
            "draft": deepcopy(graph.get("draft") or {}),
            "has_draft": bool(graph.get("draft")),
            "updated_at": graph.get("updated_at"),
            "base_version": state["base_version"],
            "version_semantics": "curated_graph_revision_separate_from_template_versions",
        }

    def save_draft(self, graph_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        gid = _normalize_graph_id(graph_id)
        dsl = _string_object_mapping(payload.get("dsl"))
        if dsl is None:
            _raise_curated_failure("contract_invalid", "dsl is required and must be a mapping")
        parse_graph_edit_draft_contract(dsl, object_kind="template_graph")
        base_revision = _read_optional_int(payload, "base_revision")
        actor_id = str(payload.get("actor_id") or payload.get("user_id") or "").strip() or "unknown"

        now = _utcnow()

        def _mutator(state: _CuratedState) -> _CuratedState:
            graph = self._ensure_graph(state, gid)
            current_revision = int(graph.get("revision") or 0)
            if base_revision is not None and base_revision != current_revision:
                message = f"conflict: revision mismatch expected={base_revision} actual={current_revision}"
                failure = workflow_graph_failure("revision_conflict", message, owner="workflow_graph.curated_service", public_exception=WorkflowGraphSyncConflictError, public_message=message, field="base_revision", index=-1, expected_revision=base_revision, actual_revision=current_revision)
                raise_workflow_graph_legacy(failure, exception_type=WorkflowGraphSyncConflictError, exception_kwargs={"expected_revision": base_revision, "actual_revision": current_revision})
            graph["draft"] = {
                "dsl": dsl,
                "updated_at": now,
                "updated_by": actor_id,
                "base_revision": current_revision,
            }
            graph["updated_at"] = now
            graph["last_sync_status"] = "draft_saved"
            return state

        state = self._mutate(base_version=_read_base_version(payload), mutator=_mutator)
        graph = state["graphs"][gid]
        return {
            "graph_id": gid,
            "sync_status": "draft_saved",
            "revision": int(graph.get("revision") or 0),
            "active_version_id": graph.get("active_version_id"),
            "draft_updated_at": (graph.get("draft") or {}).get("updated_at"),
            "base_version": state["base_version"],
        }

    def submit_draft(self, graph_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        gid = _normalize_graph_id(graph_id)
        base_revision = _read_optional_int(payload, "base_revision")
        actor_id = str(payload.get("actor_id") or payload.get("user_id") or "").strip() or "unknown"
        object_scope = str(payload.get("object_scope") or "curated_business_graph").strip() or "curated_business_graph"
        explicit_version_id = str(payload.get("version_id") or "").strip() or None
        now = _utcnow()

        def _mutator(state: _CuratedState) -> _CuratedState:
            graph = state["graphs"].get(gid)
            if graph is None:
                _raise_curated_failure("object_not_found", f"curated graph not found: {gid}", exception_type=WorkflowGraphObjectMissingError)
            current_revision = int(graph.get("revision") or 0)
            if base_revision is not None and base_revision != current_revision:
                message = f"conflict: revision mismatch expected={base_revision} actual={current_revision}"
                failure = workflow_graph_failure("revision_conflict", message, owner="workflow_graph.curated_service", public_exception=WorkflowGraphSyncConflictError, public_message=message, field="base_revision", index=-1, expected_revision=base_revision, actual_revision=current_revision)
                raise_workflow_graph_legacy(failure, exception_type=WorkflowGraphSyncConflictError, exception_kwargs={"expected_revision": base_revision, "actual_revision": current_revision})
            draft = graph["draft"]
            draft_dsl = _string_object_mapping(draft.get("dsl"))
            if draft_dsl is None:
                _raise_curated_failure("contract_invalid", "draft missing: save draft before submit")
            # Submit path enforces curated-business constraints; temporary ids must be resolved.
            parse_graph_edit_draft_contract(draft_dsl, object_kind="curated_business_graph")
            new_revision = current_revision + 1
            version_id = explicit_version_id or f"cver_{new_revision}_{uuid4().hex[:8]}"
            if version_id in graph["versions"]:
                _raise_curated_failure("contract_invalid", f"version already exists: {version_id}")
            audit_id = f"audit_{uuid4().hex[:12]}"
            audit_record = build_graph_edit_audit_record(
                audit_id=audit_id,
                action="submit",
                actor_id=actor_id,
                project_key=current_project_key(),
                graph_id=gid,
                object_scope=object_scope,
                timestamp=now,
                from_revision=current_revision,
                to_revision=new_revision,
                version_id=version_id,
            )

            graph["revision"] = new_revision
            graph["active_version_id"] = version_id
            graph["current"] = {
                "revision": new_revision,
                "version_id": version_id,
                "dsl": deepcopy(draft_dsl),
                "submitted_at": now,
                "submitted_by": actor_id,
                "object_scope": object_scope,
                "audit_id": audit_id,
            }
            graph["versions"][version_id] = {
                "version_id": version_id,
                "revision": new_revision,
                "dsl": deepcopy(draft_dsl),
                "created_at": now,
                "created_by": actor_id,
                "action": "submit",
                "audit_id": audit_id,
            }
            graph["audits"].append(audit_record)
            graph["updated_at"] = now
            graph["last_sync_status"] = "submitted"
            return state

        state = self._mutate(base_version=_read_base_version(payload), mutator=_mutator)
        graph = state["graphs"][gid]
        current = graph.get("current") or {}
        return {
            "graph_id": gid,
            "submit_status": "submitted",
            "revision": int(graph.get("revision") or 0),
            "active_version_id": graph.get("active_version_id"),
            "audit_id": current.get("audit_id"),
            "base_version": state["base_version"],
        }

    def sync_graph(self, graph_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        gid = _normalize_graph_id(graph_id)
        since_revision = _read_optional_int(payload, "since_revision")
        state = self._load_state()
        graph = state["graphs"].get(gid)
        if graph is None:
            _raise_curated_failure("object_not_found", f"curated graph not found: {gid}", exception_type=WorkflowGraphObjectMissingError)
        current_revision = int(graph.get("revision") or 0)
        if since_revision is None:
            sync_status = "snapshot"
            in_sync = False
        elif since_revision == current_revision:
            sync_status = "in_sync"
            in_sync = True
        else:
            sync_status = "out_of_sync"
            in_sync = False
        return {
            "graph_id": gid,
            "sync_status": sync_status,
            "in_sync": in_sync,
            "revision": current_revision,
            "active_version_id": graph.get("active_version_id"),
            "has_draft": bool(graph.get("draft")),
            "server_snapshot": deepcopy(graph.get("current") or {}),
            "base_version": state["base_version"],
        }

    def rollback(self, graph_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        gid = _normalize_graph_id(graph_id)
        target_version_id = str(payload.get("target_version_id") or "").strip()
        if not target_version_id:
            _raise_curated_failure("contract_invalid", "target_version_id is required")
        base_revision = _read_optional_int(payload, "base_revision")
        actor_id = str(payload.get("actor_id") or payload.get("user_id") or "").strip() or "unknown"
        now = _utcnow()

        def _mutator(state: _CuratedState) -> _CuratedState:
            graph = state["graphs"].get(gid)
            if graph is None:
                _raise_curated_failure("object_not_found", f"curated graph not found: {gid}", exception_type=WorkflowGraphObjectMissingError)
            current_revision = int(graph.get("revision") or 0)
            if base_revision is not None and base_revision != current_revision:
                message = f"conflict: revision mismatch expected={base_revision} actual={current_revision}"
                failure = workflow_graph_failure("revision_conflict", message, owner="workflow_graph.curated_service", public_exception=WorkflowGraphSyncConflictError, public_message=message, field="base_revision", index=-1, expected_revision=base_revision, actual_revision=current_revision)
                raise_workflow_graph_legacy(failure, exception_type=WorkflowGraphSyncConflictError, exception_kwargs={"expected_revision": base_revision, "actual_revision": current_revision})
            target = graph["versions"].get(target_version_id)
            if target is None:
                _raise_curated_failure("object_not_found", f"version not found: {target_version_id}", exception_type=WorkflowGraphObjectMissingError)

            new_revision = current_revision + 1
            rollback_version_id = f"cver_{new_revision}_{uuid4().hex[:8]}"
            audit_id = f"audit_{uuid4().hex[:12]}"
            rolled_dsl = deepcopy(_string_object_mapping(target.get("dsl")) or {})
            project_key = current_project_key()
            rollback_contract = build_graph_rollback_contract(
                actor_id=actor_id,
                project_key=project_key,
                graph_id=gid,
                target_version_id=target_version_id,
                current_revision=current_revision,
                base_revision=base_revision,
                requested_at=now,
                reason=str(payload.get("reason") or "").strip() or None,
            )
            audit_record = build_graph_edit_audit_record(
                audit_id=audit_id,
                action="rollback",
                actor_id=actor_id,
                project_key=project_key,
                graph_id=gid,
                object_scope="curated_business_graph",
                timestamp=now,
                from_revision=current_revision,
                to_revision=new_revision,
                version_id=rollback_version_id,
                rollback_from_version_id=target_version_id,
                context={"rollback_contract": rollback_contract},
            )
            graph["revision"] = new_revision
            graph["active_version_id"] = rollback_version_id
            graph["current"] = {
                "revision": new_revision,
                "version_id": rollback_version_id,
                "dsl": rolled_dsl,
                "submitted_at": now,
                "submitted_by": actor_id,
                "object_scope": "curated_business_graph",
                "audit_id": audit_id,
                "rollback_from_version_id": target_version_id,
                "rollback_contract": rollback_contract,
            }
            graph["versions"][rollback_version_id] = {
                "version_id": rollback_version_id,
                "revision": new_revision,
                "dsl": rolled_dsl,
                "created_at": now,
                "created_by": actor_id,
                "action": "rollback",
                "rollback_from_version_id": target_version_id,
                "audit_id": audit_id,
                "rollback_contract": rollback_contract,
            }
            graph["audits"].append(audit_record)
            graph["updated_at"] = now
            graph["last_sync_status"] = "rolled_back"
            return state

        state = self._mutate(base_version=_read_base_version(payload), mutator=_mutator)
        graph = state["graphs"][gid]
        current = graph.get("current") or {}
        return {
            "graph_id": gid,
            "rollback_status": "succeeded",
            "revision": int(graph.get("revision") or 0),
            "active_version_id": graph.get("active_version_id"),
            "rollback_from_version_id": current.get("rollback_from_version_id"),
            "rollback_contract": current.get("rollback_contract") or {},
            "audit_id": current.get("audit_id"),
            "base_version": state["base_version"],
        }

    def list_audits(self, graph_id: str, *, limit: int = 50) -> dict[str, object]:
        gid = _normalize_graph_id(graph_id)
        state = self._load_state()
        graph = state["graphs"].get(gid)
        if graph is None:
            _raise_curated_failure("object_not_found", f"curated graph not found: {gid}", exception_type=WorkflowGraphObjectMissingError)
        safe_limit = max(1, min(int(limit or 50), 200))
        audits = list(graph.get("audits") or [])
        audits = audits[-safe_limit:]
        audits.reverse()
        return {
            "graph_id": gid,
            "items": deepcopy(audits),
            "total": len(graph.get("audits") or []),
            "base_version": state["base_version"],
        }

    def build_evidence_pack(self, graph_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        gid = _normalize_graph_id(graph_id)
        version_id = str(payload.get("version_id") or "").strip() or None
        selected_node_ids = _normalize_selected_node_ids(payload.get("selected_node_ids"))
        state = self._load_state()
        graph = state["graphs"].get(gid)
        if graph is None:
            _raise_curated_failure("object_not_found", f"curated graph not found: {gid}", exception_type=WorkflowGraphObjectMissingError)

        version = None
        if version_id:
            version = graph["versions"].get(version_id)
            if version is None:
                _raise_curated_failure("object_not_found", f"version not found: {version_id}", exception_type=WorkflowGraphObjectMissingError)
        if version is None:
            current = graph["current"]
            version = current
            version_id = str(current.get("version_id") or "").strip() or None

        dsl = _string_object_mapping(version.get("dsl"))
        if dsl is None:
            _raise_curated_failure("contract_invalid", "graph version dsl missing")
        parse_graph_edit_draft_contract(dsl, object_kind="curated_business_graph")
        raw_nodes_value = dsl.get("nodes")
        raw_edges_value = dsl.get("edges")
        nodes_raw = raw_nodes_value if _is_object_list(raw_nodes_value) else []
        edges_raw = raw_edges_value if _is_object_list(raw_edges_value) else []

        node_map: dict[str, dict[str, object]] = {}
        for node_value in nodes_raw:
            node = _string_object_mapping(node_value)
            if node is None:
                continue
            node_id = str(node.get("node_id") or node.get("id") or node.get("key") or "").strip()
            if not node_id:
                continue
            if selected_node_ids and node_id not in selected_node_ids:
                continue
            node_map[node_id] = {
                "node_id": node_id,
                "node_type": str(node.get("node_type") or node.get("type") or "").strip() or "Entity",
                "title": _first_non_empty(node, ("title", "name", "label", "text")) or node_id,
                "summary": _first_non_empty(node, ("summary", "text", "description")),
                "source_uri": _first_non_empty(node, ("source_uri", "uri", "url")),
                "provenance": _extract_provenance(node),
            }

        relations: list[dict[str, object]] = []
        for edge_value in edges_raw:
            edge = _string_object_mapping(edge_value)
            if edge is None:
                continue
            from_node_id = _edge_node_id(edge, "from")
            to_node_id = _edge_node_id(edge, "to")
            if not from_node_id or not to_node_id:
                continue
            if from_node_id not in node_map or to_node_id not in node_map:
                continue
            relations.append(
                {
                    "from_node_id": from_node_id,
                    "to_node_id": to_node_id,
                    "edge_type": str(edge.get("edge_type") or edge.get("type") or edge.get("predicate") or "RELATED_TO"),
                    "evidence": _first_non_empty(edge, ("evidence", "summary", "text")),
                    "confidence": _safe_float(edge.get("confidence")),
                    "provenance": _extract_provenance(edge),
                }
            )

        revision = _safe_int(version.get("revision"), default=graph["revision"])
        audit_id = str(version.get("audit_id") or "").strip() or None
        pack_id = f"gep_{gid}_{revision}_{uuid4().hex[:8]}"
        return {
            "contract_version": EVIDENCE_PACK_CONTRACT_VERSION,
            "pack_id": pack_id,
            "graph_id": gid,
            "graph_scope": "curated_business_graph",
            "revision": revision,
            "version_id": version_id,
            "generated_at": _utcnow(),
            "selected_nodes": list(node_map.values()),
            "relations": relations,
            "provenance": {
                "project_key": current_project_key(),
                "audit_id": audit_id,
                "source": "workflow_graph.curated",
            },
        }

    def build_reporting_handoff(self, graph_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        topic = str(payload.get("topic") or "").strip()
        if not topic:
            _raise_curated_failure("contract_invalid", "topic is required")
        evidence_pack = self.build_evidence_pack(graph_id, payload)
        sources: list[dict[str, object]] = []
        selected_nodes = evidence_pack.get("selected_nodes")
        if not _is_object_list(selected_nodes):
            _raise_curated_failure("contract_invalid", "evidence pack selected_nodes must be an array")
        for node_value in selected_nodes:
            node = _string_object_mapping(node_value)
            if node is None:
                continue
            url = str(node.get("source_uri") or "").strip()
            if not (url.startswith("http://") or url.startswith("https://")):
                continue
            evidence = str(node.get("summary") or "").strip()
            if not evidence:
                evidence = f"Graph node {node.get('node_id')} selected from curated graph."
            sources.append(
                {
                    "id": f"GRAPHNODE-{node.get('node_id')}",
                    "title": str(node.get("title") or node.get("node_id") or "Graph Node"),
                    "url": url,
                    "publisher": f"graph:{node.get('node_type')}",
                    "published_at": None,
                    "retrieved_at": _utcnow(),
                    "evidence": evidence[:2000],
                }
            )
            if len(sources) >= 100:
                break
        return {
            "contract_version": HANDOFF_CONTRACT_VERSION,
            "handoff_id": f"handoff_report_{uuid4().hex[:12]}",
            "owner": HANDOFF_PRODUCER,
            "producer": HANDOFF_PRODUCER,
            "handoff_mode": "pull_prepared_evidence",
            "consumer": "llm_report.generate",
            "report_generate_request": {
                "topic": topic,
                "sources": sources,
                "section_titles": payload.get("section_titles") if isinstance(payload.get("section_titles"), list) else [],
            },
            "evidence_pack": evidence_pack,
        }

    def build_writing_handoff(self, graph_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        query = str(payload.get("query") or payload.get("topic") or "").strip()
        if not query:
            _raise_curated_failure("contract_invalid", "query is required")
        evidence_pack = self.build_evidence_pack(graph_id, payload)
        return {
            "contract_version": HANDOFF_CONTRACT_VERSION,
            "handoff_id": f"handoff_writing_{uuid4().hex[:12]}",
            "owner": HANDOFF_PRODUCER,
            "producer": HANDOFF_PRODUCER,
            "handoff_mode": "pull_prepared_evidence",
            "consumer": "writing.keyword_cards",
            "keyword_card_request": {
                "project_key": current_project_key(),
                "query": query,
                "sources": ["graph"],
                "context": {
                    "contract_version": "writing.context_boundary.e3.v1",
                    "selection_context": {},
                    "evidence_context": {},
                    "accepted_citation_context": {},
                    "graph_context": evidence_pack,
                },
            },
            "graph_context": evidence_pack,
        }

    def _load_state(self) -> _CuratedState:
        project_key = current_project_key()
        cfg = get_ingest_config(project_key, CONFIG_KEY)
        payload = cfg.get("payload") if cfg is not None else None
        return _normalize_state(payload)

    def _save_state(self, state: _CuratedState) -> _CuratedState:
        project_key = current_project_key()
        saved = upsert_ingest_config(project_key, CONFIG_KEY, CONFIG_TYPE, payload=deepcopy(dict(state)))
        payload = saved.get("payload")
        return _normalize_state(payload)

    def _mutate(
        self, *, base_version: int | None, mutator: Callable[[_CuratedState], _CuratedState]
    ) -> _CuratedState:
        state = self._load_state()
        current = int(state["base_version"])
        if base_version is not None and base_version != current:
            _raise_curated_failure("revision_conflict", f"conflict: base_version mismatch expected={base_version} actual={current}")
        updated = mutator(deepcopy(state))
        updated["base_version"] = current + 1
        return self._save_state(updated)

    @staticmethod
    def _ensure_graph(state: _CuratedState, graph_id: str) -> _CuratedGraph:
        graphs = state["graphs"]
        existing = graphs.get(graph_id)
        if existing is not None:
            return existing
        graph: _CuratedGraph = {
            "graph_id": graph_id,
            "revision": 0,
            "active_version_id": None,
            "draft": {},
            "current": {},
            "versions": {},
            "audits": [],
            "updated_at": _utcnow(),
            "last_sync_status": "created",
        }
        graphs[graph_id] = graph
        return graph


def _normalize_state(payload: object) -> _CuratedState:
    state = _string_object_mapping(payload) or {}
    raw_graphs = _string_object_mapping(state.get("graphs")) or {}
    graphs: dict[str, _CuratedGraph] = {}
    for raw_gid, raw_graph_value in raw_graphs.items():
        gid = _normalize_graph_id(raw_gid)
        raw_graph = _string_object_mapping(raw_graph_value)
        if not gid or raw_graph is None:
            continue
        draft = _string_object_mapping(raw_graph.get("draft")) or {}
        current = _string_object_mapping(raw_graph.get("current")) or {}
        raw_versions = _string_object_mapping(raw_graph.get("versions")) or {}
        versions: dict[str, dict[str, object]] = {}
        for raw_vid, raw_version_value in raw_versions.items():
            vid = str(raw_vid or "").strip()
            raw_version = _string_object_mapping(raw_version_value)
            if not vid or raw_version is None:
                continue
            versions[vid] = {
                "version_id": vid,
                "revision": _safe_int(raw_version.get("revision"), default=0),
                "dsl": _string_object_mapping(raw_version.get("dsl")) or {},
                "created_at": str(raw_version.get("created_at") or _utcnow()),
                "created_by": str(raw_version.get("created_by") or "").strip() or None,
                "action": str(raw_version.get("action") or "submit").strip(),
                "audit_id": str(raw_version.get("audit_id") or "").strip() or None,
                "rollback_from_version_id": str(raw_version.get("rollback_from_version_id") or "").strip() or None,
                "rollback_contract": _string_object_mapping(raw_version.get("rollback_contract")) or {},
            }
        raw_audits = raw_graph.get("audits")
        audits: list[dict[str, object]] = []
        if _is_object_list(raw_audits):
            for item in raw_audits:
                normalized_item = _string_object_mapping(item)
                if normalized_item is None:
                    _raise_curated_failure(
                        "contract_invalid",
                        "curated graph audit record must be a string-keyed mapping",
                        exception_type=TypeError,
                    )
                audits.append(normalized_item)
        graphs[gid] = {
            "graph_id": gid,
            "revision": _safe_int(raw_graph.get("revision"), default=0),
            "active_version_id": str(raw_graph.get("active_version_id") or "").strip() or None,
            "draft": {
                "dsl": _string_object_mapping(draft.get("dsl")) or {},
                "updated_at": str(draft.get("updated_at") or _utcnow()),
                "updated_by": str(draft.get("updated_by") or "").strip() or None,
                "base_revision": _safe_int(draft.get("base_revision"), default=0),
            } if draft else {},
            "current": {
                "revision": _safe_int(current.get("revision"), default=0),
                "version_id": str(current.get("version_id") or "").strip() or None,
                "dsl": _string_object_mapping(current.get("dsl")) or {},
                "submitted_at": str(current.get("submitted_at") or _utcnow()),
                "submitted_by": str(current.get("submitted_by") or "").strip() or None,
                "object_scope": str(current.get("object_scope") or "curated_business_graph").strip(),
                "audit_id": str(current.get("audit_id") or "").strip() or None,
                "rollback_from_version_id": str(current.get("rollback_from_version_id") or "").strip() or None,
                "rollback_contract": _string_object_mapping(current.get("rollback_contract")) or {},
            } if current else {},
            "versions": versions,
            "audits": audits,
            "updated_at": str(raw_graph.get("updated_at") or _utcnow()),
            "last_sync_status": str(raw_graph.get("last_sync_status") or "unknown").strip() or "unknown",
        }
    base_version = _safe_int(state.get("base_version"), default=0)
    if base_version < 0:
        base_version = 0
    return {"base_version": base_version, "graphs": graphs}


def _read_base_version(payload: Mapping[str, object]) -> int | None:
    if "base_version" not in payload:
        return None
    return _read_optional_int(payload, "base_version")


def _read_optional_int(payload: Mapping[str, object], field: str) -> int | None:
    if field not in payload:
        return None
    raw = payload.get(field)
    if raw in (None, ""):
        return None
    if not _is_int_convertible(raw):
        _raise_curated_failure("contract_invalid", f"{field} must be an integer")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        _raise_curated_failure("contract_invalid", f"{field} must be an integer")
    if value < 0:
        _raise_curated_failure("contract_invalid", f"{field} must be >= 0")
    return value


def _normalize_selected_node_ids(raw: object) -> set[str]:
    if not _is_object_list(raw):
        return set()
    out: set[str] = set()
    for item in raw:
        value = str(item or "").strip()
        if value:
            out.add(value)
    return out


def _edge_node_id(edge: Mapping[str, object], field: str) -> str:
    endpoint = edge.get(field)
    endpoint_mapping = _string_object_mapping(endpoint)
    if endpoint_mapping is not None:
        return str(endpoint_mapping.get("node_id") or endpoint_mapping.get("id") or endpoint_mapping.get("key") or "").strip()
    if isinstance(endpoint, str):
        return endpoint.strip()
    return str(edge.get(f"{field}_node_id") or edge.get(f"{field}_id") or "").strip()


def _extract_provenance(item: Mapping[str, object]) -> dict[str, object]:
    provenance = _string_object_mapping(item.get("provenance"))
    if provenance is not None:
        return provenance
    keys = ("source_id", "document_id", "uri", "url", "source_uri")
    out: dict[str, object] = {}
    for key in keys:
        if item.get(key) not in (None, ""):
            out[key] = item.get(key)
    return out


def _first_non_empty(item: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return None


def _safe_int(value: object, *, default: int) -> int:
    if not _is_int_convertible(value):
        return default
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return default


def _safe_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    if not _is_float_convertible(value):
        return None
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _normalize_graph_id(value: object) -> str:
    gid = str(value or "").strip()
    if not gid:
        _raise_curated_failure("contract_invalid", "graph_id is required")
    return gid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_int_convertible(value: object) -> TypeGuard[str | bytes | bytearray | SupportsInt | SupportsIndex]:
    return isinstance(value, (str, bytes, bytearray, SupportsInt, SupportsIndex))


def _is_float_convertible(value: object) -> TypeGuard[str | bytes | bytearray | SupportsFloat | SupportsIndex]:
    return isinstance(value, (str, bytes, bytearray, SupportsFloat, SupportsIndex))
