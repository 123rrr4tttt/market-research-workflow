from __future__ import annotations

from dataclasses import asdict
from collections.abc import Mapping, Set
from threading import RLock
from typing import Any, NoReturn, Protocol, runtime_checkable
from uuid import uuid4

from functorial_kit import Failure

from app.services.agent_sessions import get_agent_session_service

from .compiler import compile_workflow_graph
from .curated_service import WorkflowGraphCuratedService
from app.successor_runtime.capabilities.workflow_legacy_dsl import (
    parse_and_validate_workflow_dsl,
    workflow_program_metadata,
    WorkflowLegacyDSLReceipt,
)
from .runtime import WorkflowGraphPlatformInterpreter
from .store import (
    InMemoryCompiledGraphStore,
    SqlCompiledGraphStore,
    build_compiled_graph_store,
    build_run_store,
)
from .templates import WorkflowGraphTemplateService
from .contracts import raise_workflow_graph_legacy, workflow_graph_failure


def _raise_facade_failure(
    code: str,
    message: str,
    *,
    exception_type: type[Exception] = ValueError,
) -> NoReturn:
    failure = workflow_graph_failure(
        code,
        message,
        owner="workflow_graph.facade",
        public_exception=exception_type,
        public_message=message,
        field="facade",
        index=-1,
    )
    raise_workflow_graph_legacy(failure, exception_type=exception_type)


@runtime_checkable
class _StringKeyMapping(Protocol):
    def keys(self) -> Set[str]: ...
    def __getitem__(self, key: str) -> Any: ...


@runtime_checkable
class _ObjectSequence(Protocol):
    def __len__(self) -> int: ...
    def __getitem__(self, index: int) -> object: ...


def _mapping(value: object) -> dict[str, Any] | None:
    if not isinstance(value, _StringKeyMapping):
        return None
    if not all(type(key) is str for key in value.keys()):
        return None
    return {key: value[key] for key in value.keys()}


def _object_list(value: object) -> list[object] | None:
    if not isinstance(value, _ObjectSequence):
        return None
    return [value[index] for index in range(len(value))]


def _object_dict(value: object) -> dict[str, Any] | None:
    return _mapping(value)


def _mapping_list(value: object) -> list[dict[str, Any]] | None:
    items = _object_list(value)
    if items is None:
        return None
    normalized: list[dict[str, Any]] = []
    for item in items:
        item_map = _mapping(item)
        if item_map is None:
            return None
        normalized.append(item_map)
    return normalized


class WorkflowGraphCompilerService:
    """Compiler facade backed only by the compiled-graph store authority."""

    def __init__(
        self,
        *,
        store: InMemoryCompiledGraphStore | SqlCompiledGraphStore | None = None,
    ) -> None:
        self._lock = RLock()
        self._store = store
        self._templates = WorkflowGraphTemplateService()

    def _resolved_store(self) -> InMemoryCompiledGraphStore | SqlCompiledGraphStore:
        with self._lock:
            if self._store is None:
                self._store = build_compiled_graph_store()
            return self._store

    def compile(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        dsl_payload = payload.get("dsl")
        template_id = str(payload.get("template_id") or "").strip()
        requested_version_id = str(payload.get("version_id") or "").strip() or None
        resolved_version_id: str | None = None
        if template_id:
            dsl_payload, resolved_version_id = self._templates.resolve_version_dsl(
                template_id=template_id,
                version_id=requested_version_id,
            )
        elif _mapping(dsl_payload) is None:
            dsl_payload = payload
        normalized_dsl_payload = _mapping(dsl_payload)
        if normalized_dsl_payload is None:
            _raise_facade_failure("contract_invalid", "dsl payload must be a mapping")

        compiled = compile_workflow_graph(normalized_dsl_payload)
        platform_receipt = parse_and_validate_workflow_dsl(dict(normalized_dsl_payload))
        if not platform_receipt.ok or platform_receipt.program is None or platform_receipt.plan is None:
            failure = platform_receipt.failure
            _raise_facade_failure(
                "integrity_invalid",
                failure.message if failure is not None else "workflow platform lowering failed",
            )
        raw_graph_id = payload.get("graph_id")
        graph_id = str(raw_graph_id).strip() if raw_graph_id is not None else ""
        if not graph_id or graph_id.lower() == "none":
            graph_id = uuid4().hex

        nodes = _object_list(normalized_dsl_payload.get("nodes")) or []
        normalized_nodes: dict[str, dict[str, Any]] = {}
        for item in nodes:
            node_data = _mapping(item)
            if node_data is None:
                continue
            node_id = str(node_data.get("node_id") or node_data.get("id") or "").strip()
            if not node_id:
                continue
            node_type = str(node_data.get("node_type") or "").strip()
            config = _mapping(node_data.get("config"))
            if config is None:
                config = _mapping(node_data.get("params")) or {}
            depends_on = list(compiled.incoming_edges.get(node_id, ()))
            normalized_nodes[node_id] = {
                "id": node_id,
                "node_type": node_type,
                "params": dict(config),
                "depends_on": depends_on,
            }

        compiled_record = {
            "graph_id": graph_id,
            "version": compiled.version,
            "options": dict(compiled.options),
            "checksum": compiled.checksum,
            "topo_order": list(compiled.topo_order),
            "outgoing_edges": {k: list(v) for k, v in compiled.outgoing_edges.items()},
            "incoming_edges": {k: list(v) for k, v in compiled.incoming_edges.items()},
            "nodes": normalized_nodes,
            "dsl": dict(normalized_dsl_payload),
            "compiled": asdict(compiled),
            "platform": {
                "program_digest": platform_receipt.program_digest,
                "plan_digest": platform_receipt.plan_digest,
                "catalog_digest": platform_receipt.catalog_digest,
            },
        }
        store = self._resolved_store()
        store.save_compiled(compiled_record)
        response: dict[str, Any] = {
            "graph_id": graph_id,
            "version": compiled.version,
            "checksum": compiled.checksum,
            "topo_order": list(compiled.topo_order),
            "warnings": [],
        }
        if template_id:
            response["template_id"] = template_id
            response["version_id"] = resolved_version_id
        response.update({
            "program_digest": platform_receipt.program_digest,
            "plan_digest": platform_receipt.plan_digest,
            "catalog_digest": platform_receipt.catalog_digest,
        })
        return response

    def get_compiled(self, graph_id: str) -> dict[str, Any]:
        return self._resolved_store().get_compiled(str(graph_id))

    def list_compiled(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._resolved_store().list_compiled(limit=limit)

    def list_templates(self) -> dict[str, Any]:
        return self._templates.list_templates()

    def create_template(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._templates.create_template(payload)

    def get_template(self, template_id: str) -> dict[str, Any]:
        return self._templates.get_template(template_id)

    def patch_template(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._templates.patch_template(template_id, payload)

    def delete_template(self, template_id: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self._templates.delete_template(template_id, payload)

    def list_template_versions(self, template_id: str) -> dict[str, Any]:
        return self._templates.list_versions(template_id)

    def create_template_version(self, template_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._templates.create_version(template_id, payload)

    def get_template_version(self, template_id: str, version_id: str) -> dict[str, Any]:
        return self._templates.get_version(template_id, version_id)

    def activate_template_version(
        self,
        template_id: str,
        version_id: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._templates.activate_version(template_id, version_id, payload)


compiler: WorkflowGraphCompilerService


class WorkflowGraphRuntimeService:
    """Runtime facade backed by the workflow platform interpreter."""

    def __init__(self) -> None:
        self._engine: WorkflowGraphPlatformInterpreter | None = None
        self._lock = RLock()

    def _resolved_engine(self) -> WorkflowGraphPlatformInterpreter:
        with self._lock:
            if self._engine is None:
                self._engine = WorkflowGraphPlatformInterpreter(store=build_run_store())
            return self._engine

    def run(self, payload: Mapping[str, object]) -> dict[str, Any]:
        graph_id = str(payload.get("graph_id") or "").strip()
        if not graph_id:
            _raise_facade_failure("contract_invalid", "graph_id is required")

        compiled = compiler.get_compiled(graph_id)
        run_input: object = payload.get("input")
        if run_input is None:
            run_input = payload.get("inputs")
        if run_input is None:
            run_input = dict[str, object]()
        normalized_run_input = _mapping(run_input)
        if normalized_run_input is None:
            _raise_facade_failure("contract_invalid", "input must be a mapping")
        project_key = str(payload.get("project_key") or "").strip()
        trace_id = str(payload.get("trace_id") or "").strip() or None

        receipt = parse_and_validate_workflow_dsl(dict(_mapping(compiled.get("dsl")) or {}))
        if (
            not receipt.ok
            or receipt.program is None
            or receipt.plan is None
            or not self._platform_binding_matches(compiled, receipt)
        ):
            _raise_facade_failure("integrity_invalid", "compiled workflow platform binding is stale")
        metadata = workflow_program_metadata(receipt.program)
        metadata_nodes: list[dict[str, Any]] = []
        for item in _object_list(metadata.get("nodes")) or []:
            metadata_node = _object_dict(item)
            if metadata_node is not None and str(metadata_node.get("node_id") or "").strip():
                metadata_nodes.append(metadata_node)
        workflow = {
            "workflow_id": graph_id,
            "project_key": project_key or None,
            "program_digest": receipt.program_digest,
            "plan_digest": receipt.plan_digest,
            "topo_order": list(metadata.get("topo_order") or []),
            "nodes": {
                str(item.get("node_id") or ""): {
                    "id": str(item.get("node_id") or ""),
                    "node_type": item.get("node_type"),
                    "params": dict(item.get("config") or {}),
                }
                for item in metadata_nodes
            },
        }
        resolved_run_input = dict(normalized_run_input)
        if project_key:
            resolved_run_input.setdefault("project_key", project_key)
        if trace_id:
            resolved_run_input.setdefault("trace_id", trace_id)
        run_id = str(payload.get("run_id") or "").strip() or None
        snapshot = self._resolved_engine().run(
            plan=receipt.plan,
            program=receipt.program,
            workflow=workflow,
            inputs=resolved_run_input,
            run_id=run_id,
            project_key=project_key or None,
            trace_id=trace_id,
        )
        run = _mapping(snapshot.get("run")) or {}
        session_bundle = get_agent_session_service().project_workflow_graph_run(
            graph_id=graph_id,
            run_id=str(run.get("run_id") or ""),
            workflow=workflow,
            inputs=resolved_run_input,
            snapshot=snapshot,
            project_key=project_key or None,
        )
        if isinstance(session_bundle, Failure):
            _raise_facade_failure("integrity_invalid", "workflow run session projection failed")
        session = _mapping(session_bundle.get("session")) or {}
        return {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "node_statuses": run.get("node_statuses") or {},
            "session_id": session.get("session_id"),
            "current_phase": session.get("current_phase"),
            "root_task_id": session.get("root_task_id"),
            "compat_mode": False,
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        stored_run = self._resolved_engine().store.get_run(str(run_id))
        out: dict[str, Any] = dict(stored_run)
        session = get_agent_session_service().find_session_by_logical_task_list_key(str(run_id))
        if session:
            out["session_id"] = session.get("session_id")
            out["current_phase"] = session.get("current_phase")
            out["root_task_id"] = session.get("root_task_id")
        return out

    @staticmethod
    def _platform_binding_matches(
        compiled: Mapping[str, Any],
        receipt: WorkflowLegacyDSLReceipt,
    ) -> bool:
        expected = dict(compiled.get("platform") or {})
        return all([
            expected.get("program_digest") == receipt.program_digest,
            expected.get("plan_digest") == receipt.plan_digest,
            expected.get("catalog_digest") == receipt.catalog_digest,
        ])

    def get_run_events(self, run_id: str) -> dict[str, Any]:
        items = list(self._resolved_engine().store.get_events(str(run_id)))
        session = get_agent_session_service().find_session_by_logical_task_list_key(str(run_id))
        if session:
            session_events = get_agent_session_service().list_events(str(session.get("session_id") or ""))
            for event in session_events:
                items.append(
                    {
                        "ts": event.get("ts"),
                        "type": f"agent_session.{event.get('event_type')}",
                        "node_id": None,
                        "payload": dict(event.get("payload") or {}),
                    }
                )
        return {"items": items, "session_id": session.get("session_id") if session else None}

    def get_run_agent_session(self, run_id: str) -> dict[str, Any]:
        session = get_agent_session_service().find_session_by_logical_task_list_key(str(run_id))
        if session is None:
            _raise_facade_failure(
                "object_not_found",
                f"agent session not found for run: {run_id}",
                exception_type=KeyError,
            )
        bundle = get_agent_session_service().get_session_bundle(
            str(session.get("session_id") or "")
        )
        if isinstance(bundle, Failure):
            _raise_facade_failure("object_not_found", "agent session bundle not found", exception_type=KeyError)
        return bundle

    def replay_run(self, run_id: str, replay_mode: str = "events_only") -> dict[str, Any]:
        resolved_mode = str(replay_mode or "events_only").strip().lower() or "events_only"
        if resolved_mode not in {"events_only", "stateful"}:
            _raise_facade_failure("contract_invalid", "replay_mode must be events_only or stateful")

        snapshot = self._resolved_engine().store.snapshot(str(run_id))
        replay_consistency = _build_replay_consistency_report(snapshot)

        if resolved_mode == "stateful":
            run = _mapping(snapshot.get("run")) or {}
            events = _mapping_list(snapshot.get("events")) or []
            return {
                "run_id": str(run.get("run_id") or run_id),
                "status": str(run.get("status") or "queued"),
                "node_statuses": dict(run.get("node_statuses") or {}),
                "events_count": len(events),
                "events": events,
                "results": dict(snapshot.get("results") or {}),
                "replay_mode": "stateful",
                "replay_consistency": replay_consistency,
            }

        events = list(self._resolved_engine().store.get_events(str(run_id)))
        node_statuses: dict[str, str] = {}
        run_status = "queued"
        for event in events:
            event_type = str(event.get("type") or "")
            node_id = str(event.get("node_id") or "").strip()
            if event_type == "run.running":
                run_status = "running"
            elif event_type == "run.succeeded":
                run_status = "succeeded"
            elif event_type == "run.failed":
                run_status = "failed"
            elif event_type == "node.running" and node_id:
                node_statuses[node_id] = "running"
            elif event_type == "node.succeeded" and node_id:
                node_statuses[node_id] = "succeeded"
            elif event_type == "node.failed" and node_id:
                node_statuses[node_id] = "failed"
        return {
            "run_id": str(run_id),
            "status": run_status,
            "node_statuses": node_statuses,
            "events_count": len(events),
            "replay_mode": "events_only",
            "replay_consistency": replay_consistency,
        }


def _build_replay_consistency_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    run = _mapping(snapshot.get("run")) or {}
    events = _mapping_list(snapshot.get("events")) or []
    derived_status = "queued"
    derived_node_statuses: dict[str, str] = {}
    issues: list[dict[str, Any]] = []

    for event in events:
        event_type = str(event.get("type") or "")
        node_id = str(event.get("node_id") or "").strip()
        if event_type == "run.running":
            derived_status = "running"
        elif event_type == "run.succeeded":
            derived_status = "succeeded"
        elif event_type == "run.failed":
            derived_status = "failed"
        elif event_type == "node.running" and node_id:
            derived_node_statuses[node_id] = "running"
        elif event_type == "node.succeeded" and node_id:
            derived_node_statuses[node_id] = "succeeded"
        elif event_type == "node.failed" and node_id:
            derived_node_statuses[node_id] = "failed"

    stored_status = str(run.get("status") or "queued")
    if stored_status != derived_status:
        issues.append(
            {
                "code": "run_status_mismatch",
                "message": f"stored run status '{stored_status}' does not match replayed status '{derived_status}'",
                "details": {"stored_status": stored_status, "replayed_status": derived_status},
            }
        )

    stored_node_statuses = dict(run.get("node_statuses") or {})
    for node_id in sorted(set(stored_node_statuses) | set(derived_node_statuses)):
        stored_node_status = str(stored_node_statuses.get(node_id) or "")
        derived_node_status = str(derived_node_statuses.get(node_id) or "")
        if stored_node_status != derived_node_status:
            issues.append(
                {
                    "code": "node_status_mismatch",
                    "message": f"stored node status for '{node_id}' does not match replayed status",
                    "details": {
                        "node_id": node_id,
                        "stored_status": stored_node_status,
                        "replayed_status": derived_node_status,
                    },
                }
            )

    return {
        "contract_version": "workflow_graph.replay_consistency.v1",
        "consistent": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "stored_status": stored_status,
        "replayed_status": derived_status,
    }


compiler = WorkflowGraphCompilerService()
runtime = WorkflowGraphRuntimeService()
curated = WorkflowGraphCuratedService()

__all__ = [
    "compiler",
    "runtime",
    "curated",
    "WorkflowGraphCompilerService",
    "WorkflowGraphRuntimeService",
    "WorkflowGraphCuratedService",
]
