from __future__ import annotations

import json
from collections.abc import Mapping
from threading import RLock
from typing import NoReturn, TypeGuard
from uuid import uuid4

from functorial_kit import Failure

from app.services.agent_sessions import get_agent_session_service
from app.successor_runtime.capabilities.workflow_legacy_dsl import (
    WorkflowLegacyDSLReceipt,
    parse_and_validate_workflow_dsl,
)

from .compiler import compile_workflow_graph
from .contracts import (
    CompiledWorkflowGraphRecord,
    CompiledWorkflowGraphValue,
    WorkflowCompilerResponse,
    WorkflowEventView,
    WorkflowIntegrityIssueValue,
    WorkflowJsonObject,
    WorkflowJsonValue,
    WorkflowNodeStatus,
    WorkflowPlatformBinding,
    WorkflowReplayConsistencyReport,
    WorkflowReplayResponse,
    WorkflowRunDetail,
    WorkflowRunEventsResponse,
    WorkflowRunResponse,
    WorkflowRunStatus,
    WorkflowRuntimeGraph,
    WorkflowRuntimeNode,
    WorkflowRunSnapshot,
    raise_workflow_graph_legacy,
    workflow_graph_failure,
)
from .curated_service import WorkflowGraphCuratedService
from .runtime import WorkflowGraphPlatformInterpreter
from .schema import (
    parse_workflow_graph_dsl,
    try_parse_workflow_json_object,
)
from .store import (
    InMemoryCompiledGraphStore,
    SqlCompiledGraphStore,
    build_compiled_graph_store,
    build_run_store,
)
from .templates import WorkflowGraphTemplateService


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


def _json_object(value: object) -> WorkflowJsonObject | None:
    parsed = try_parse_workflow_json_object(value, field="workflow_graph.facade")
    return None if isinstance(parsed, Failure) else parsed


def _require_json_object(value: object, message: str) -> WorkflowJsonObject:
    parsed = _json_object(value)
    if parsed is None:
        _raise_facade_failure("contract_invalid", message)
    return parsed


def _serialize_json_object(value: object, message: str) -> WorkflowJsonObject:
    try:
        normalized: object = json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError) as exc:
        _raise_facade_failure("contract_invalid", f"{message}: {exc}")
    return _require_json_object(normalized, message)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _mapping_value(value: object, key: str) -> object:
    if not _is_object_mapping(value):
        return None
    for raw_key, raw_value in value.items():
        if raw_key == key:
            return raw_value
    return None


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

    def compile(self, payload: Mapping[str, WorkflowJsonValue]) -> WorkflowCompilerResponse:
        raw_payload = _require_json_object(payload, "compile payload must be a JSON mapping")
        dsl_payload: object = raw_payload.get("dsl")
        raw_template_id = raw_payload.get("template_id")
        template_id = raw_template_id.strip() if isinstance(raw_template_id, str) else ""
        raw_version_id = raw_payload.get("version_id")
        requested_version_id = raw_version_id.strip() if isinstance(raw_version_id, str) and raw_version_id.strip() else None
        resolved_version_id: str | None = None
        if template_id:
            dsl_payload, resolved_version_id = self._templates.resolve_version_dsl(
                template_id=template_id,
                version_id=requested_version_id,
            )
        elif _json_object(dsl_payload) is None:
            dsl_payload = raw_payload
        normalized_dsl_payload = _require_json_object(dsl_payload, "dsl payload must be a JSON mapping")
        dsl = parse_workflow_graph_dsl(normalized_dsl_payload)
        compiled = compile_workflow_graph(dsl)
        platform_receipt = parse_and_validate_workflow_dsl(normalized_dsl_payload)
        if not platform_receipt.ok or platform_receipt.program is None or platform_receipt.plan is None:
            failure = platform_receipt.failure
            _raise_facade_failure(
                "integrity_invalid",
                failure.message if failure is not None else "workflow platform lowering failed",
            )

        raw_graph_id = raw_payload.get("graph_id")
        graph_id = raw_graph_id.strip() if isinstance(raw_graph_id, str) else ""
        if not graph_id or graph_id.lower() == "none":
            graph_id = uuid4().hex

        normalized_nodes: dict[str, WorkflowRuntimeNode] = {}
        for node in dsl.nodes:
            normalized_nodes[node.node_id] = {
                "id": node.node_id,
                "node_type": node.node_type,
                "params": dict(node.config),
                "depends_on": list(compiled.incoming_edges.get(node.node_id, ())),
            }
        platform: WorkflowPlatformBinding = {
            "program_digest": platform_receipt.program_digest,
            "plan_digest": platform_receipt.plan_digest,
            "catalog_digest": platform_receipt.catalog_digest,
        }
        compiled_value: CompiledWorkflowGraphValue = {
            "version": compiled.version,
            "options": dict(compiled.options),
            "topo_order": list(compiled.topo_order),
            "outgoing_edges": {node_id: list(targets) for node_id, targets in compiled.outgoing_edges.items()},
            "incoming_edges": {node_id: list(sources) for node_id, sources in compiled.incoming_edges.items()},
            "checksum": compiled.checksum,
        }
        compiled_record: CompiledWorkflowGraphRecord = {
            "graph_id": graph_id,
            "version": compiled.version,
            "options": dict(compiled.options),
            "checksum": compiled.checksum,
            "topo_order": list(compiled.topo_order),
            "outgoing_edges": {node_id: list(targets) for node_id, targets in compiled.outgoing_edges.items()},
            "incoming_edges": {node_id: list(sources) for node_id, sources in compiled.incoming_edges.items()},
            "nodes": normalized_nodes,
            "dsl": normalized_dsl_payload,
            "compiled": compiled_value,
            "platform": platform,
        }
        self._resolved_store().save_compiled(compiled_record)
        response: WorkflowCompilerResponse = {
            "graph_id": graph_id,
            "version": compiled.version,
            "checksum": compiled.checksum,
            "topo_order": list(compiled.topo_order),
            "warnings": [],
            "program_digest": platform_receipt.program_digest,
            "plan_digest": platform_receipt.plan_digest,
            "catalog_digest": platform_receipt.catalog_digest,
        }
        if template_id:
            response["template_id"] = template_id
            response["version_id"] = resolved_version_id
        return response

    def get_compiled(self, graph_id: str) -> CompiledWorkflowGraphRecord:
        return self._resolved_store().get_compiled(str(graph_id))

    def list_compiled(self, limit: int = 20) -> list[CompiledWorkflowGraphRecord]:
        return self._resolved_store().list_compiled(limit=limit)

    def list_templates(self) -> WorkflowJsonObject:
        return _require_json_object(self._templates.list_templates(), "template list must be JSON")

    def create_template(self, payload: Mapping[str, WorkflowJsonValue]) -> WorkflowJsonObject:
        return _require_json_object(self._templates.create_template(payload), "template response must be JSON")

    def get_template(self, template_id: str) -> WorkflowJsonObject:
        return _require_json_object(self._templates.get_template(template_id), "template response must be JSON")

    def patch_template(self, template_id: str, payload: Mapping[str, WorkflowJsonValue]) -> WorkflowJsonObject:
        return _require_json_object(self._templates.patch_template(template_id, payload), "template response must be JSON")

    def delete_template(
        self,
        template_id: str,
        payload: Mapping[str, WorkflowJsonValue] | None = None,
    ) -> WorkflowJsonObject:
        return _require_json_object(self._templates.delete_template(template_id, payload), "template response must be JSON")

    def list_template_versions(self, template_id: str) -> WorkflowJsonObject:
        return _require_json_object(self._templates.list_versions(template_id), "template versions must be JSON")

    def create_template_version(
        self,
        template_id: str,
        payload: Mapping[str, WorkflowJsonValue],
    ) -> WorkflowJsonObject:
        return _require_json_object(self._templates.create_version(template_id, payload), "template version must be JSON")

    def get_template_version(self, template_id: str, version_id: str) -> WorkflowJsonObject:
        return _require_json_object(self._templates.get_version(template_id, version_id), "template version must be JSON")

    def activate_template_version(
        self,
        template_id: str,
        version_id: str,
        payload: Mapping[str, WorkflowJsonValue] | None = None,
    ) -> WorkflowJsonObject:
        return _require_json_object(
            self._templates.activate_version(template_id, version_id, payload),
            "template activation must be JSON",
        )


compiler: WorkflowGraphCompilerService


class WorkflowGraphRuntimeService:
    """Runtime facade backed by the current workflow platform interpreter."""

    def __init__(self) -> None:
        self._engine: WorkflowGraphPlatformInterpreter | None = None
        self._lock = RLock()

    def _resolved_engine(self) -> WorkflowGraphPlatformInterpreter:
        with self._lock:
            if self._engine is None:
                self._engine = WorkflowGraphPlatformInterpreter(store=build_run_store())
            return self._engine

    def run(self, payload: Mapping[str, WorkflowJsonValue]) -> WorkflowRunResponse:
        raw_payload = _require_json_object(payload, "run payload must be a JSON mapping")
        raw_graph_id = raw_payload.get("graph_id")
        graph_id = raw_graph_id.strip() if isinstance(raw_graph_id, str) else ""
        if not graph_id:
            _raise_facade_failure("contract_invalid", "graph_id is required")

        compiled = compiler.get_compiled(graph_id)
        run_input = raw_payload.get("input")
        if run_input is None:
            run_input = raw_payload.get("inputs")
        normalized_run_input = _require_json_object(
            {} if run_input is None else run_input,
            "input must be a JSON mapping",
        )
        raw_project_key = raw_payload.get("project_key")
        project_key = raw_project_key.strip() if isinstance(raw_project_key, str) else ""
        raw_trace_id = raw_payload.get("trace_id")
        trace_id = raw_trace_id.strip() if isinstance(raw_trace_id, str) and raw_trace_id.strip() else None

        receipt = parse_and_validate_workflow_dsl(compiled["dsl"])
        if (
            not receipt.ok
            or receipt.program is None
            or receipt.plan is None
            or not self._platform_binding_matches(compiled, receipt)
        ):
            _raise_facade_failure("integrity_invalid", "compiled workflow platform binding is stale")

        dsl = parse_workflow_graph_dsl(compiled["dsl"])
        runtime_nodes: dict[str, WorkflowRuntimeNode] = {}
        for node in dsl.nodes:
            runtime_nodes[node.node_id] = {
                "id": node.node_id,
                "node_type": node.node_type,
                "params": dict(node.config),
                "depends_on": list(compiled["incoming_edges"].get(node.node_id, [])),
            }
        workflow: WorkflowRuntimeGraph = {
            "workflow_id": graph_id,
            "project_key": project_key or None,
            "program_digest": receipt.program_digest,
            "plan_digest": receipt.plan_digest,
            "topo_order": list(receipt.topo_order),
            "nodes": runtime_nodes,
        }
        if project_key:
            normalized_run_input.setdefault("project_key", project_key)
        if trace_id:
            normalized_run_input.setdefault("trace_id", trace_id)
        raw_run_id = raw_payload.get("run_id")
        run_id = raw_run_id.strip() if isinstance(raw_run_id, str) and raw_run_id.strip() else None
        snapshot = self._resolved_engine().run(
            plan=receipt.plan,
            program=receipt.program,
            workflow=workflow,
            inputs=normalized_run_input,
            run_id=run_id,
            project_key=project_key or None,
            trace_id=trace_id,
        )
        run = snapshot["run"]
        session_bundle = get_agent_session_service().project_workflow_graph_run(
            graph_id=graph_id,
            run_id=run["run_id"],
            workflow=workflow,
            inputs=normalized_run_input,
            snapshot=snapshot,
            project_key=project_key or None,
        )
        if isinstance(session_bundle, Failure):
            _raise_facade_failure("integrity_invalid", "workflow run session projection failed")
        session = _mapping_value(session_bundle, "session")
        return {
            "run_id": run["run_id"],
            "status": run["status"],
            "node_statuses": dict(run["node_statuses"]),
            "session_id": _optional_object_string(_mapping_value(session, "session_id")),
            "current_phase": _optional_object_string(_mapping_value(session, "current_phase")),
            "root_task_id": _optional_object_string(_mapping_value(session, "root_task_id")),
            "compat_mode": False,
        }

    def get_run(self, run_id: str) -> WorkflowRunDetail:
        stored_run = self._resolved_engine().store.get_run(str(run_id))
        out: WorkflowRunDetail = {
            "run_id": stored_run["run_id"],
            "status": stored_run["status"],
            "created_at": stored_run["created_at"],
            "updated_at": stored_run["updated_at"],
            "node_statuses": dict(stored_run["node_statuses"]),
            "metadata": dict(stored_run["metadata"]),
        }
        session_raw = get_agent_session_service().find_session_by_logical_task_list_key(str(run_id))
        if _is_object_mapping(session_raw):
            out["session_id"] = _optional_object_string(_mapping_value(session_raw, "session_id"))
            out["current_phase"] = _optional_object_string(_mapping_value(session_raw, "current_phase"))
            out["root_task_id"] = _optional_object_string(_mapping_value(session_raw, "root_task_id"))
        return out

    @staticmethod
    def _platform_binding_matches(
        compiled: CompiledWorkflowGraphRecord,
        receipt: WorkflowLegacyDSLReceipt,
    ) -> bool:
        expected = compiled["platform"]
        return all(
            (
                expected["program_digest"] == receipt.program_digest,
                expected["plan_digest"] == receipt.plan_digest,
                expected["catalog_digest"] == receipt.catalog_digest,
            )
        )

    def get_run_events(self, run_id: str) -> WorkflowRunEventsResponse:
        items: list[WorkflowEventView] = [
            {
                "ts": event["ts"],
                "type": event["type"],
                "node_id": event["node_id"],
                "payload": event["payload"],
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "project_key": event["project_key"],
                "session_id": event["session_id"],
                "run_id": event["run_id"],
                "trace_id": event["trace_id"],
                "created_at": event["created_at"],
                "seq": event["seq"],
            }
            for event in self._resolved_engine().store.get_events(str(run_id))
        ]
        session_raw = get_agent_session_service().find_session_by_logical_task_list_key(str(run_id))
        session = session_raw if _is_object_mapping(session_raw) else None
        if session is not None:
            session_id = _optional_object_string(_mapping_value(session, "session_id"))
            session_events = get_agent_session_service().list_events(session_id or "")
            if isinstance(session_events, Failure):
                _raise_facade_failure(
                    "integrity_invalid",
                    "agent session events projection failed",
                )
            for raw_event in session_events:
                payload = _serialize_json_object(
                    _mapping_value(raw_event, "payload") or {},
                    "agent session event payload must be JSON",
                )
                event_type = _optional_object_string(_mapping_value(raw_event, "event_type")) or "unknown"
                items.append(
                    {
                        "ts": _optional_object_string(_mapping_value(raw_event, "ts")) or "",
                        "type": f"agent_session.{event_type}",
                        "node_id": None,
                        "payload": payload,
                    }
                )
        return {
            "items": items,
            "session_id": _optional_object_string(_mapping_value(session, "session_id")) if session is not None else None,
        }

    def get_run_agent_session(self, run_id: str) -> WorkflowJsonObject:
        session_raw = get_agent_session_service().find_session_by_logical_task_list_key(str(run_id))
        if not _is_object_mapping(session_raw):
            _raise_facade_failure(
                "object_not_found",
                f"agent session not found for run: {run_id}",
                exception_type=KeyError,
            )
        session_id = _optional_object_string(_mapping_value(session_raw, "session_id")) or ""
        bundle = get_agent_session_service().get_session_bundle(session_id)
        if isinstance(bundle, Failure):
            _raise_facade_failure("object_not_found", "agent session bundle not found", exception_type=KeyError)
        return _serialize_json_object(bundle, "agent session bundle must be JSON")

    def replay_run(self, run_id: str, replay_mode: str = "events_only") -> WorkflowReplayResponse:
        resolved_mode = str(replay_mode or "events_only").strip().lower() or "events_only"
        if resolved_mode not in {"events_only", "stateful"}:
            _raise_facade_failure("contract_invalid", "replay_mode must be events_only or stateful")

        snapshot = self._resolved_engine().store.snapshot(str(run_id))
        replay_consistency = _build_replay_consistency_report(snapshot)
        if resolved_mode == "stateful":
            run = snapshot["run"]
            return {
                "run_id": run["run_id"],
                "status": run["status"],
                "node_statuses": dict(run["node_statuses"]),
                "events_count": len(snapshot["events"]),
                "events": list(snapshot["events"]),
                "results": dict(snapshot["results"]),
                "replay_mode": "stateful",
                "replay_consistency": replay_consistency,
            }

        events = self._resolved_engine().store.get_events(str(run_id))
        node_statuses: dict[str, WorkflowNodeStatus] = {}
        run_status: WorkflowRunStatus = "queued"
        for event in events:
            event_type = event["type"]
            node_id = event["node_id"] or ""
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


def _optional_object_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _build_replay_consistency_report(snapshot: WorkflowRunSnapshot) -> WorkflowReplayConsistencyReport:
    run = snapshot["run"]
    events = snapshot["events"]
    derived_status: WorkflowRunStatus = "queued"
    derived_node_statuses: dict[str, WorkflowNodeStatus] = {}
    issues: list[WorkflowIntegrityIssueValue] = []

    for event in events:
        event_type = event["type"]
        node_id = event["node_id"] or ""
        if event_type == "run.queued":
            raw_topo_order = event["payload"].get("topo_order")
            if isinstance(raw_topo_order, list):
                for raw_node_id in raw_topo_order:
                    if isinstance(raw_node_id, str) and raw_node_id:
                        derived_node_statuses.setdefault(raw_node_id, "queued")
        elif event_type == "run.running":
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

    stored_status = run["status"]
    if stored_status != derived_status:
        issues.append(
            {
                "code": "run_status_mismatch",
                "message": f"stored run status '{stored_status}' does not match replayed status '{derived_status}'",
                "details": {"stored_status": stored_status, "replayed_status": derived_status},
            }
        )

    stored_node_statuses = run["node_statuses"]
    for node_id in sorted(set(stored_node_statuses) | set(derived_node_statuses)):
        stored_node_status = stored_node_statuses.get(node_id, "")
        derived_node_status = derived_node_statuses.get(node_id, "")
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
