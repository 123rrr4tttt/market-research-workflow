from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from threading import RLock
from typing import TYPE_CHECKING, Literal, NoReturn, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

from functorial_kit import Failure

if TYPE_CHECKING:
    from app.successor_runtime.language.plan import ExecutionPlan
    from app.successor_runtime.substrate.projections.agent_session import (
        AgentSessionSnapshot,
    )

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.workflow_native_contribution import (
    WORKFLOW_RUNTIME_OWNER,
    WorkflowExecutionContext,
    build_workflow_runtime_program,
    decode_workflow_runtime_output,
)

from .compiler import compile_workflow_graph
from .contracts import (
    CompiledWorkflowGraphRecord,
    WORKFLOW_GRAPH_DOMAIN_BINDING_VERSION,
    WorkflowCompilerResponse,
    WorkflowEventView,
    WorkflowGraphEvent,
    WorkflowIntegrityIssueValue,
    WorkflowJsonObject,
    WorkflowJsonValue,
    WorkflowNodeStatus,
    WorkflowNodeResults,
    WorkflowReplayConsistencyReport,
    WorkflowReplayResponse,
    WorkflowRunDetail,
    WorkflowRunEventsResponse,
    WorkflowRunResponse,
    WorkflowRunStatus,
    WorkflowRuntimeNode,
    raise_workflow_graph_legacy,
    workflow_graph_failure,
)
from .curated_service import WorkflowGraphCuratedService
from . import runtime as _workflow_runtime_leaf
del _workflow_runtime_leaf
from .schema import (
    parse_workflow_graph_dsl,
    try_parse_workflow_json_object,
)
from .store import (
    HistoricalWorkflowRunReader,
    InMemoryCompiledGraphStore,
    SqlCompiledGraphStore,
    build_compiled_graph_store,
    build_historical_workflow_run_reader,
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
            "binding_version": WORKFLOW_GRAPH_DOMAIN_BINDING_VERSION,
            "dsl_content_digest": content_digest(normalized_dsl_payload),
        }
        self._resolved_store().save_compiled(compiled_record)
        response: WorkflowCompilerResponse = {
            "graph_id": graph_id,
            "version": compiled.version,
            "checksum": compiled.checksum,
            "topo_order": list(compiled.topo_order),
            "warnings": [],
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
    """Durable workflow facade over the canonical successor Runtime."""

    def __init__(
        self,
        *,
        historical_reader: HistoricalWorkflowRunReader | None = None,
    ) -> None:
        self._historical_reader = historical_reader
        self._historical_reader_lock = RLock()

    def _resolved_historical_reader(self) -> HistoricalWorkflowRunReader:
        with self._historical_reader_lock:
            if self._historical_reader is None:
                self._historical_reader = build_historical_workflow_run_reader()
            return self._historical_reader

    @staticmethod
    def _run_source(value: str) -> Literal["canonical", "historical"]:
        normalized = str(value or "canonical").strip().lower()
        if normalized not in {"canonical", "historical"}:
            _raise_facade_failure(
                "contract_invalid",
                "source must be canonical or historical",
            )
        return cast(Literal["canonical", "historical"], normalized)

    @staticmethod
    def _require_historical_project(
        run: Mapping[str, object], *, project_key: str,
    ) -> None:
        metadata = run.get("metadata")
        metadata_map: Mapping[str, object] = (
            cast(Mapping[str, object], metadata)
            if isinstance(metadata, dict)
            else cast(Mapping[str, object], {})
        )
        historical_project = (
            str(metadata_map.get("project_key") or "").strip()
        )
        if historical_project != project_key:
            _raise_facade_failure(
                "object_not_found",
                "historical workflow run is not available in this project",
                exception_type=KeyError,
            )

    @staticmethod
    def _required_text(payload: Mapping[str, WorkflowJsonValue], key: str) -> str:
        value = payload.get(key)
        normalized = value.strip() if isinstance(value, str) else ""
        if not normalized:
            _raise_facade_failure("contract_invalid", f"{key} is required")
        return normalized

    @staticmethod
    def _runtime_status(value: object) -> WorkflowRunStatus:
        state = str(value or "").strip().upper()
        if state in {"SUBMITTED", "COMPILING", "AWAITING_APPROVAL", "READY"}:
            return "queued"
        if state in {"RUNNING", "WAITING", "RECONCILING", "CANCELLING"}:
            return "running"
        if state == "COMPLETED":
            return "succeeded"
        if state in {"FAILED", "CANCELLED", "SUPERSEDED"}:
            return "failed"
        _raise_facade_failure("integrity_invalid", f"unknown canonical runtime state: {state}")

    @staticmethod
    def _node_status(value: object) -> WorkflowNodeStatus:
        state = str(value or "").strip().upper()
        if state in {"PENDING", "AWAITING_APPROVAL", "READY"}:
            return "queued"
        if state in {"CLAIMED", "RUNNING", "COMMITTING", "WAITING_EXTERNAL",
                     "RETRY_SCHEDULED", "RECONCILING", "CANCEL_REQUESTED"}:
            return "running"
        if state in {"SUCCEEDED", "NOT_SELECTED", "SKIPPED_BY_DECISION"}:
            return "succeeded"
        if state in {"FAILED", "CANCELLED", "SUPERSEDED"}:
            return "failed"
        _raise_facade_failure("integrity_invalid", f"unknown canonical step state: {state}")

    @staticmethod
    def _node_id(step: Mapping[str, object]) -> str:
        operation_id = str(step.get("operation_id") or "")
        if not operation_id.startswith("workflow-node:"):
            _raise_facade_failure(
                "integrity_invalid",
                f"canonical workflow step has unexpected operation id: {operation_id}",
            )
        _, _, node_id = operation_id.split(":", 2)
        if not node_id:
            _raise_facade_failure("integrity_invalid", "canonical workflow step has no node id")
        return node_id

    @classmethod
    def _node_statuses(
        cls, steps: tuple[dict[str, object], ...],
    ) -> dict[str, WorkflowNodeStatus]:
        return {cls._node_id(step): cls._node_status(step.get("state")) for step in steps}

    @staticmethod
    def _read_runtime(
        *, run_id: str, project_key: str, actor_id: str,
    ) -> tuple[dict[str, object], tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
        from app.composition.production import read_installed_program
        from app.models.base import engine

        run, steps, events = read_installed_program(
            engine=engine, project_key=project_key, actor_id=actor_id, run_id=run_id,
        )
        return (
            dict(run),
            tuple(dict(step) for step in steps),
            tuple(dict(event) for event in events),
        )

    @staticmethod
    def _read_runtime_outputs(
        *, run_id: str, project_key: str, actor_id: str,
    ) -> tuple[tuple[str, WorkflowExecutionContext], ...]:
        from app.composition.production import read_installed_program_outputs
        from app.models.base import engine

        return tuple(
            (step_id, decode_workflow_runtime_output(value_ref, exact))
            for step_id, value_ref, exact in read_installed_program_outputs(
                engine=engine,
                project_key=project_key,
                actor_id=actor_id,
                run_id=run_id,
            )
        )

    @staticmethod
    def _read_runtime_plan(
        *, run: Mapping[str, object], project_key: str, actor_id: str,
    ) -> ExecutionPlan:
        from sqlalchemy import MetaData
        from app.models.base import engine
        from app.successor_runtime.runtime.ports import RuntimeScope
        from app.successor_runtime.substrate.postgres.models import project_tables
        from app.successor_runtime.substrate.postgres.plans import PlanRepository
        from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

        with engine.connect() as connection:
            project = ServerProjectScopeResolver(connection=connection).resolve(project_key)
            if (run["resolved_schema"] != project.resolved_schema
                    or run["project_registry_revision"] != project.project_registry_revision
                    or run["project_scope_digest"] != project.scope_digest):
                _raise_facade_failure("integrity_invalid", "workflow replay project scope drift")
            plan = PlanRepository(connection, project_tables(MetaData(), project.resolved_schema)).get(
                RuntimeScope(project_scope=project, actor_id=actor_id), str(run["plan_digest"]),
            )
            if (plan.plan_id != run["plan_id"] or plan.plan_digest != run["plan_digest"]
                    or plan.program_id != run["program_id"] or plan.program_digest != run["program_digest"]):
                _raise_facade_failure("integrity_invalid", "workflow replay Run/Plan identity drift")
            return plan

    @staticmethod
    def _load_agent_session_snapshot(
        *, run_id: str, incarnation: str, project_key: str, actor_id: str,
    ) -> AgentSessionSnapshot:
        from app.models.base import engine
        from app.successor_runtime.runtime.ports import RuntimeScope
        from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver
        from app.successor_runtime.substrate.projections.agent_session import (
            PostgresAgentSessionReadAdapter,
            RuntimeJournalSource,
        )

        with engine.connect() as connection:
            project_scope = ServerProjectScopeResolver(connection=connection).resolve(project_key)
            return PostgresAgentSessionReadAdapter(
                connection,
                RuntimeScope(project_scope=project_scope, actor_id=actor_id),
            ).load(
                RuntimeJournalSource(
                    run_id=run_id,
                    run_incarnation=incarnation,
                    source_ref=f"runtime-run:{run_id}",
                )
            )

    def run(self, payload: Mapping[str, WorkflowJsonValue]) -> WorkflowRunResponse:
        raw_payload = _require_json_object(payload, "run payload must be a JSON mapping")
        graph_id = self._required_text(raw_payload, "graph_id")
        project_key = self._required_text(raw_payload, "project_key")
        actor_id = self._required_text(raw_payload, "actor_id")
        compiled = compiler.get_compiled(graph_id)
        run_input = raw_payload.get("input")
        if run_input is None:
            run_input = raw_payload.get("inputs")
        normalized_run_input = _require_json_object(
            {} if run_input is None else run_input, "input must be a JSON mapping",
        )
        self._require_current_domain_binding(compiled, requested_graph_id=graph_id)

        run_id_value = raw_payload.get("run_id")
        explicit_run_id = (
            run_id_value.strip()
            if isinstance(run_id_value, str) and run_id_value.strip()
            else ""
        )
        idem_value = raw_payload.get("idempotency_key")
        logical_request_id = (
            idem_value.strip()
            if isinstance(idem_value, str) and idem_value.strip()
            else explicit_run_id
        )
        run_id = explicit_run_id or (
            f"workflow-{uuid5(NAMESPACE_URL, f'mrw://workflow/{project_key}/{actor_id}/{logical_request_id}').hex}"
            if logical_request_id
            else f"workflow-{uuid4().hex}"
        )
        if not logical_request_id:
            logical_request_id = run_id
        trace_value = raw_payload.get("trace_id")
        trace_id = (
            trace_value.strip()
            if isinstance(trace_value, str) and trace_value.strip()
            else f"workflow_graph.{run_id}"
        )
        incarnation = f"workflow:{run_id}"

        from app.composition.production import submit_installed_program
        from app.models.base import engine
        from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

        with engine.connect() as connection:
            project_scope = ServerProjectScopeResolver(connection=connection).resolve(project_key)
        runtime_program = build_workflow_runtime_program(
            workflow_id=graph_id,
            nodes=tuple({
                "node_id": node_id, "node_type": node["node_type"],
                "params": dict(node["params"]), "depends_on": list(node["depends_on"]),
            } for node_id, node in compiled["nodes"].items()),
            topo_order=tuple(compiled["topo_order"]), inputs=normalized_run_input,
            program_id=f"workflow-program:{run_id}", project_key=project_key,
            project_registry_revision=project_scope.project_registry_revision,
            project_scope_digest=project_scope.scope_digest,
            incarnation=incarnation, trace_id=trace_id,
        )
        submit_installed_program(
            engine=engine, project_key=project_key, actor_id=actor_id,
            program=runtime_program.program, operation_catalog=runtime_program.catalog,
            operation_contracts=runtime_program.registry, values=runtime_program.values,
            idempotency_id=f"workflow-idempotency:{run_id}",
            identity_capability_id=WORKFLOW_RUNTIME_OWNER,
            logical_request_id=logical_request_id,
            identity_operation_kind=runtime_program.registry.contracts[0].ref.kind,
            run_id=run_id,
            incarnation=incarnation, canonical_bindings=runtime_program.canonical_bindings,
            approvals_by_step={}, trace_id=trace_id, now=datetime.now(UTC), queue="celery",
        )
        run, steps, _ = self._read_runtime(
            run_id=run_id, project_key=project_key, actor_id=actor_id,
        )
        return {
            "run_id": str(run["run_id"]),
            "status": self._runtime_status(run.get("state")),
            "node_statuses": self._node_statuses(steps),
            "session_id": None, "current_phase": None, "root_task_id": None,
            "compat_mode": False,
        }

    def get_run(
        self,
        run_id: str,
        *,
        project_key: str,
        actor_id: str,
        source: str = "canonical",
    ) -> WorkflowRunDetail:
        if self._run_source(source) == "historical":
            historical = self._resolved_historical_reader().get_run(str(run_id))
            self._require_historical_project(historical, project_key=project_key)
            return cast(WorkflowRunDetail, historical)
        run, steps, _ = self._read_runtime(
            run_id=str(run_id), project_key=project_key, actor_id=actor_id,
        )
        created_at = run.get("created_at")
        updated_at = run.get("updated_at")
        return {
            "run_id": str(run["run_id"]), "status": self._runtime_status(run.get("state")),
            "created_at": created_at.isoformat() if isinstance(created_at, datetime) else str(created_at or ""),
            "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at or ""),
            "node_statuses": self._node_statuses(steps),
            "metadata": {
                "project_key": str(run.get("project_key") or project_key),
                "program_id": str(run.get("program_id") or ""),
                "program_digest": str(run.get("program_digest") or ""),
                "plan_id": str(run.get("plan_id") or ""),
                "plan_digest": str(run.get("plan_digest") or ""),
                "runtime_state": str(run.get("state") or ""),
            },
        }

    @staticmethod
    def _require_current_domain_binding(
        compiled: CompiledWorkflowGraphRecord,
        *,
        requested_graph_id: str,
    ) -> None:
        if compiled["graph_id"] != requested_graph_id:
            _raise_facade_failure(
                "integrity_invalid",
                "compiled workflow graph identity does not match the requested graph; recompile the graph",
            )
        if compiled.get("binding_version") != WORKFLOW_GRAPH_DOMAIN_BINDING_VERSION:
            _raise_facade_failure(
                "integrity_invalid",
                "compiled workflow uses a missing or unsupported binding version; recompile the graph",
            )
        if compiled.get("dsl_content_digest") != content_digest(compiled["dsl"]):
            _raise_facade_failure(
                "integrity_invalid",
                "compiled workflow DSL content digest is stale; recompile the graph",
            )

        dsl = parse_workflow_graph_dsl(compiled["dsl"])
        projection = compile_workflow_graph(dsl)
        expected_nodes: dict[str, WorkflowRuntimeNode] = {
            node.node_id: {
                "id": node.node_id,
                "node_type": node.node_type,
                "params": dict(node.config),
                "depends_on": list(projection.incoming_edges.get(node.node_id, ())),
            }
            for node in dsl.nodes
        }
        matches = all(
            (
                compiled["version"] == projection.version,
                compiled["options"] == dict(projection.options),
                compiled["checksum"] == projection.checksum,
                compiled["topo_order"] == list(projection.topo_order),
                compiled["outgoing_edges"]
                == {key: list(value) for key, value in projection.outgoing_edges.items()},
                compiled["incoming_edges"]
                == {key: list(value) for key, value in projection.incoming_edges.items()},
                compiled["nodes"] == expected_nodes,
            )
        )
        if not matches:
            _raise_facade_failure(
                "integrity_invalid",
                "compiled workflow domain projection is stale; recompile the graph",
            )

    def get_run_events(
        self,
        run_id: str,
        *,
        project_key: str,
        actor_id: str,
        source: str = "canonical",
    ) -> WorkflowRunEventsResponse:
        if self._run_source(source) == "historical":
            reader = self._resolved_historical_reader()
            historical = reader.get_run(str(run_id))
            self._require_historical_project(historical, project_key=project_key)
            session_id = historical["metadata"].get("session_id")
            return {
                "items": cast(
                    list[WorkflowEventView], reader.get_events(str(run_id)),
                ),
                "session_id": (
                    session_id.strip()
                    if isinstance(session_id, str) and session_id.strip()
                    else None
                ),
            }
        _, steps, events = self._read_runtime(
            run_id=str(run_id), project_key=project_key, actor_id=actor_id,
        )
        node_by_step = {str(step.get("step_id") or ""): self._node_id(step) for step in steps}
        failures = {}
        if any(event.get("event_type") == "EffectFailed" for event in events):
            from app.composition.production import read_installed_program_failures
            from app.models.base import engine

            failures = dict(read_installed_program_failures(
                engine=engine, run_id=str(run_id), project_key=project_key, actor_id=actor_id,
            ))
        items: list[WorkflowEventView] = []
        for event in events:
            created_at = event.get("created_at")
            timestamp = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at or "")
            event_type = str(event.get("event_type") or "runtime.event")
            metadata = _serialize_json_object(
                event.get("event_metadata_json") or {},
                "canonical runtime event metadata must be JSON",
            )
            raw_seq = event.get("seq")
            seq = raw_seq if isinstance(raw_seq, int) and not isinstance(raw_seq, bool) else 0
            if event_type == "EffectFailed":
                record = failures.get(seq)
                if record is None:
                    _raise_facade_failure("integrity_invalid", "canonical workflow failure was not verified")
                metadata.update(failure_ref=record.failure_ref, failure_digest=record.failure_digest,
                                failure_code=record.failure_code)
                if record.domain_failure is not None:
                    failure = record.domain_failure
                    context = None if failure.context is None else _require_json_object(
                        failure.context, "verified workflow Failure context must be JSON",
                    )
                    metadata.update(failure_family=failure.family, error=failure.message, context=context)
            items.append({
                "ts": timestamp, "type": event_type,
                "node_id": node_by_step.get(str(event.get("step_id") or "")),
                "payload": metadata, "event_id": f"{run_id}:{event.get('seq')}",
                "event_type": event_type, "project_key": project_key, "session_id": None,
                "run_id": str(run_id),
                "trace_id": str(metadata.get("trace_id") or f"workflow_graph.{run_id}"),
                "created_at": timestamp, "seq": seq,
            })
        return {"items": items, "session_id": None}

    def get_run_agent_session(
        self, run_id: str, *, project_key: str, actor_id: str,
    ) -> WorkflowJsonObject:
        run, _, _ = self._read_runtime(
            run_id=str(run_id), project_key=project_key, actor_id=actor_id,
        )
        incarnation = str(run.get("incarnation") or "").strip()
        if not incarnation:
            _raise_facade_failure(
                "integrity_invalid",
                "canonical workflow run has no incarnation",
            )

        snapshot = self._load_agent_session_snapshot(
            run_id=str(run_id), incarnation=incarnation,
            project_key=project_key, actor_id=actor_id,
        )
        session = snapshot.model_dump(mode="json", exclude={"tasks"})
        tasks = [task.model_dump(mode="json") for task in snapshot.tasks]
        events = list(self.get_run_events(
            run_id, project_key=project_key, actor_id=actor_id,
        )["items"])
        return _serialize_json_object(
            {
                "session": session,
                "tasks": tasks,
                "messages": [],
                "artifacts": [],
                "events": events,
                "approvals": [],
            },
            "agent session projection must be JSON",
        )

    def replay_run(
        self, run_id: str, replay_mode: str = "events_only",
        *, project_key: str, actor_id: str,
    ) -> WorkflowReplayResponse:
        raw_mode = str(replay_mode or "events_only").strip().lower() or "events_only"
        if raw_mode not in {"events_only", "stateful"}:
            _raise_facade_failure("contract_invalid", "replay_mode must be events_only or stateful")
        mode: Literal["events_only", "stateful"] = (
            "stateful" if raw_mode == "stateful" else "events_only"
        )
        run, steps, events = self._read_runtime(
            run_id=str(run_id), project_key=project_key, actor_id=actor_id,
        )
        stored_status = self._runtime_status(run.get("state"))
        stored_node_statuses = self._node_statuses(steps)
        incarnation = str(run.get("incarnation") or "").strip()
        if not incarnation:
            _raise_facade_failure("integrity_invalid", "canonical workflow run has no incarnation")
        snapshot = self._load_agent_session_snapshot(
            run_id=str(run_id), incarnation=incarnation,
            project_key=project_key, actor_id=actor_id,
        )
        plan = self._read_runtime_plan(run=run, project_key=project_key, actor_id=actor_id)
        if (snapshot.run_id != str(run_id) or snapshot.run_incarnation != incarnation
                or len(events) != snapshot.last_seq
                or any(event.get("seq") != index for index, event in enumerate(events, 1))):
            _raise_facade_failure("integrity_invalid", "workflow replay journal frontier drift")
        for event_type, expected in (
            ("ProgramAccepted", {"program_id": plan.program_id, "program_digest": plan.program_digest}),
            ("PlanCompiled", {"plan_id": plan.plan_id, "plan_digest": plan.plan_digest}),
        ):
            anchors = tuple(event for event in events if event.get("event_type") == event_type)
            if len(anchors) != 1 or anchors[0].get("event_metadata_json") != expected:
                _raise_facade_failure("integrity_invalid", "workflow replay Program/Plan journal identity drift")
        session_status = str(snapshot.status)
        if session_status == "pending":
            replayed_status: WorkflowRunStatus = "queued"
        elif session_status == "active":
            replayed_status = "running"
        elif session_status == "completed":
            replayed_status = "succeeded"
        elif session_status in {"failed", "canceled", "unknown"}:
            replayed_status = "failed"
        else:
            active_states = {
                "CLAIMED", "RUNNING", "COMMITTING", "WAITING_EXTERNAL",
                "RECONCILING", "CANCEL_REQUESTED",
            }
            replayed_status = (
                "running"
                if any(str(task.step_state) in active_states for task in snapshot.tasks)
                else "queued"
            )
        node_by_step = {step.step_id: self._node_id({"operation_id": step.operation_id})
                        for step in plan.ordered_steps if step.step_kind == "EFFECT"}
        touched_steps = {event["step_id"] for event in events if event.get("step_id") is not None}
        task_steps = {task.step_id for task in snapshot.tasks}
        if (task_steps - set(node_by_step) or touched_steps - set(node_by_step)
                or (set(node_by_step) - task_steps) & touched_steps):
            _raise_facade_failure("integrity_invalid", "workflow replay task/activation differs from exact Plan")
        replayed_node_statuses: dict[str, WorkflowNodeStatus] = {
            node_id: "queued" for node_id in node_by_step.values()
        }
        replayed_node_statuses.update({node_by_step[task.step_id]: self._node_status(task.step_state)
                                      for task in snapshot.tasks})
        issues: list[WorkflowIntegrityIssueValue] = []
        if stored_status != replayed_status:
            issues.append({
                "code": "run_status_mismatch",
                "message": "stored runtime status does not match journal replay",
                "details": {"stored": stored_status, "replayed": replayed_status},
            })
        for node_id in sorted(set(stored_node_statuses) | set(replayed_node_statuses)):
            stored_node = stored_node_statuses.get(node_id)
            replayed_node = replayed_node_statuses.get(node_id)
            if stored_node != replayed_node:
                issues.append({
                    "code": "node_status_mismatch",
                    "message": f"stored node status does not match journal replay: {node_id}",
                    "details": {
                        "node_id": node_id,
                        "stored": stored_node,
                        "replayed": replayed_node,
                    },
                })
        consistency: WorkflowReplayConsistencyReport = {
            "contract_version": "workflow_graph.replay_consistency.v1",
            "consistent": not issues, "issue_count": len(issues), "issues": issues,
            "stored_status": stored_status, "replayed_status": replayed_status,
        }
        response: WorkflowReplayResponse = {
            "run_id": str(run_id), "status": replayed_status,
            "node_statuses": replayed_node_statuses,
            "events_count": len(events), "replay_mode": mode,
            "replay_consistency": consistency,
        }
        if mode == "stateful":
            response["events"] = cast(list[WorkflowGraphEvent], list(self.get_run_events(
                run_id, project_key=project_key, actor_id=actor_id,
            )["items"]))
            output_contexts = self._read_runtime_outputs(
                run_id=str(run_id), project_key=project_key, actor_id=actor_id,
            )
            steps_by_id = {str(step.get("step_id") or ""): step for step in steps}
            latest_context: WorkflowExecutionContext | None = None
            prior_context: WorkflowExecutionContext | None = None
            for step_id, context in output_contexts:
                step = steps_by_id.get(step_id)
                if step is None:
                    _raise_facade_failure(
                        "integrity_invalid",
                        f"canonical workflow output has no matching step: {step_id}",
                    )
                node_id = self._node_id(step)
                completed_node = context.nodes[context.cursor - 1]
                if (
                    context.project_key != project_key
                    or completed_node.get("node_id") != node_id
                    or context.cursor != (1 if prior_context is None else prior_context.cursor + 1)
                    or (
                        prior_context is not None
                        and (
                            context.workflow_id != prior_context.workflow_id
                            or context.trace_id != prior_context.trace_id
                            or context.inputs != prior_context.inputs
                            or context.nodes != prior_context.nodes
                            or any(
                                context.results.get(key) != value
                                for key, value in prior_context.results.items()
                            )
                        )
                    )
                ):
                    _raise_facade_failure(
                        "integrity_invalid",
                        f"canonical workflow output occurrence drift: {step_id}",
                    )
                prior_context = context
                if latest_context is None or context.cursor > latest_context.cursor:
                    latest_context = context
            response["results"] = cast(
                WorkflowNodeResults,
                _serialize_json_object(
                    {} if latest_context is None else latest_context.results,
                    "canonical workflow results must be JSON",
                ),
            )
        return response


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
