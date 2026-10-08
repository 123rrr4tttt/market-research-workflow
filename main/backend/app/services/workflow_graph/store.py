from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Annotated, NoReturn, Protocol, TypeGuard

from functorial_kit import Failure
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.models.base import engine
from app.services.projects.schema_initialization import run_serialized_schema_ddl
from app.settings.config import settings

from .contracts import (
    CompiledWorkflowGraphRecord,
    WORKFLOW_GRAPH_DOMAIN_BINDING_VERSION,
    WorkflowGraphEvent,
    WorkflowJsonObject,
    WorkflowNodeResults,
    WorkflowNodeStatus,
    WorkflowRunRecord,
    WorkflowRunSnapshot,
    WorkflowRunStatus,
    WorkflowRuntimeNode,
    raise_workflow_graph_legacy,
    workflow_graph_failure,
)
from .schema import try_parse_workflow_json_object

TERMINAL_STATUSES: frozenset[WorkflowRunStatus] = frozenset({"succeeded", "failed"})
NODE_STATUSES: frozenset[WorkflowNodeStatus] = frozenset({"queued", "running", "succeeded", "failed"})
RUN_STATUSES: frozenset[WorkflowRunStatus] = frozenset({"queued", "running", "succeeded", "failed"})

logger = logging.getLogger("app.services.workflow_graph.store")


def _raise_store_failure(
    code: str,
    message: str,
    *,
    exception_type: type[Exception] = ValueError,
    cause: BaseException | None = None,
) -> NoReturn:
    failure = workflow_graph_failure(
        code,
        message,
        owner="workflow_graph.store",
        public_exception=exception_type,
        public_message=message,
        field="store",
        index=-1,
    )
    raise_workflow_graph_legacy(failure, exception_type=exception_type, cause=cause)


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _mapping_value(value: object, key: str) -> object:
    if not _is_object_mapping(value):
        _raise_store_failure("contract_invalid", "database row must be a mapping")
    for raw_key, raw_value in value.items():
        if raw_key == key:
            return raw_value
    return None


def _json_object(value: object, *, field: str) -> WorkflowJsonObject:
    decoded: object = value
    if isinstance(decoded, str):
        try:
            decoded = json.loads(decoded)
        except (TypeError, ValueError) as exc:
            _raise_store_failure(
                "contract_invalid",
                f"{field} is not valid JSON: {exc}",
                cause=exc,
            )
    parsed = try_parse_workflow_json_object(decoded, field=field)
    if isinstance(parsed, Failure):
        _raise_store_failure("contract_invalid", f"{field} must be a JSON object")
    return parsed


def _required_text(payload: WorkflowJsonObject, key: str, *, field: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        _raise_store_failure("contract_invalid", f"{field}.{key} must be a non-empty string")
    return value


def _required_object(payload: WorkflowJsonObject, key: str, *, field: str) -> WorkflowJsonObject:
    value = payload.get(key)
    if not isinstance(value, dict):
        _raise_store_failure("contract_invalid", f"{field}.{key} must be an object")
    return value


def _required_text_list(payload: WorkflowJsonObject, key: str, *, field: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _raise_store_failure("contract_invalid", f"{field}.{key} must be a string list")
    return [item for item in value if isinstance(item, str)]


def _required_edge_map(payload: WorkflowJsonObject, key: str, *, field: str) -> dict[str, list[str]]:
    raw = _required_object(payload, key, field=field)
    result: dict[str, list[str]] = {}
    for node_id, targets in raw.items():
        if not isinstance(targets, list) or not all(isinstance(item, str) for item in targets):
            _raise_store_failure("contract_invalid", f"{field}.{key}.{node_id} must be a string list")
        result[node_id] = [item for item in targets if isinstance(item, str)]
    return result


def _runtime_node(value: object, *, field: str) -> WorkflowRuntimeNode:
    payload = _json_object(value, field=field)
    node_id = _required_text(payload, "id", field=field)
    node_type = _required_text(payload, "node_type", field=field)
    params = _required_object(payload, "params", field=field)
    depends_on = _required_text_list(payload, "depends_on", field=field)
    return {"id": node_id, "node_type": node_type, "params": params, "depends_on": depends_on}


def _runtime_nodes(value: object, *, field: str) -> dict[str, WorkflowRuntimeNode]:
    payload = _json_object(value, field=field)
    nodes: dict[str, WorkflowRuntimeNode] = {}
    for node_id, raw_node in payload.items():
        node = _runtime_node(raw_node, field=f"{field}.{node_id}")
        if node["id"] != node_id:
            _raise_store_failure("integrity_invalid", f"{field}.{node_id}.id does not match its key")
        nodes[node_id] = node
    return nodes


def _normalize_compiled_record(value: object) -> CompiledWorkflowGraphRecord:
    record = _json_object(value, field="compiled_graph")
    normalized: CompiledWorkflowGraphRecord = {
        "graph_id": _required_text(record, "graph_id", field="compiled_graph"),
        "version": _required_text(record, "version", field="compiled_graph"),
        "options": _required_object(record, "options", field="compiled_graph"),
        "checksum": _required_text(record, "checksum", field="compiled_graph"),
        "topo_order": _required_text_list(record, "topo_order", field="compiled_graph"),
        "outgoing_edges": _required_edge_map(record, "outgoing_edges", field="compiled_graph"),
        "incoming_edges": _required_edge_map(record, "incoming_edges", field="compiled_graph"),
        "nodes": _runtime_nodes(record.get("nodes"), field="compiled_graph.nodes"),
        "dsl": _required_object(record, "dsl", field="compiled_graph"),
    }
    if "binding_version" in record:
        binding_version = _required_text(
            record, "binding_version", field="compiled_graph"
        )
        if binding_version != WORKFLOW_GRAPH_DOMAIN_BINDING_VERSION:
            _raise_store_failure(
                "integrity_invalid",
                "compiled workflow uses an unsupported binding version; recompile the graph",
            )
        normalized["binding_version"] = WORKFLOW_GRAPH_DOMAIN_BINDING_VERSION
    if "dsl_content_digest" in record:
        normalized["dsl_content_digest"] = _required_text(
            record, "dsl_content_digest", field="compiled_graph"
        )
    # Historical compile artifacts remain list/get readable with their exact
    # nested payloads. They are never accepted as current execution bindings.
    if "compiled" in record:
        normalized["compiled"] = _required_object(
            record, "compiled", field="compiled_graph"
        )
    if "platform" in record:
        normalized["platform"] = _required_object(
            record, "platform", field="compiled_graph"
        )
    return normalized


def _node_statuses(value: object) -> dict[str, WorkflowNodeStatus]:
    payload = _json_object(value, field="node_statuses")
    result: dict[str, WorkflowNodeStatus] = {}
    for node_id, raw_status in payload.items():
        result[node_id] = _node_status(raw_status)
    return result


def _node_status(value: object) -> WorkflowNodeStatus:
    if value == "queued":
        return "queued"
    if value == "running":
        return "running"
    if value == "succeeded":
        return "succeeded"
    if value == "failed":
        return "failed"
    _raise_store_failure("contract_invalid", f"unsupported node status: {value}")


def _run_status(value: object) -> WorkflowRunStatus:
    if value == "queued":
        return "queued"
    if value == "running":
        return "running"
    if value == "succeeded":
        return "succeeded"
    if value == "failed":
        return "failed"
    _raise_store_failure("contract_invalid", f"unsupported run status: {value}")


def _node_results(value: object) -> WorkflowNodeResults:
    payload = _json_object(value, field="results")
    results: WorkflowNodeResults = {}
    for node_id, raw_result in payload.items():
        if not isinstance(raw_result, dict):
            _raise_store_failure(
                "contract_invalid",
                f"results.{node_id} must be an object",
            )
        results[node_id] = raw_result
    return results


class HistoricalWorkflowRunReader(Protocol):
    """Read-only decoder for rows written by the retired workflow runner."""

    def get_run(self, run_id: str) -> WorkflowRunRecord: ...

    def get_events(self, run_id: str) -> list[WorkflowGraphEvent]: ...

    def get_results(self, run_id: str) -> WorkflowNodeResults: ...

    def snapshot(self, run_id: str) -> WorkflowRunSnapshot: ...


class InMemoryHistoricalWorkflowRunReader:
    """Immutable historical fixtures for decoder and API compatibility tests."""

    def __init__(
        self,
        snapshots: Mapping[str, WorkflowRunSnapshot] | None = None,
    ) -> None:
        self._snapshots = deepcopy(dict(snapshots or {}))

    def _snapshot(self, run_id: str) -> WorkflowRunSnapshot:
        snapshot = self._snapshots.get(str(run_id))
        if snapshot is None:
            _raise_store_failure(
                "object_not_found",
                f"historical run not found: {run_id}",
                exception_type=KeyError,
            )
        return deepcopy(snapshot)

    def get_run(self, run_id: str) -> WorkflowRunRecord:
        return self._snapshot(run_id)["run"]

    def get_events(self, run_id: str) -> list[WorkflowGraphEvent]:
        return self._snapshot(run_id)["events"]

    def get_results(self, run_id: str) -> WorkflowNodeResults:
        return self._snapshot(run_id)["results"]

    def snapshot(self, run_id: str) -> WorkflowRunSnapshot:
        return self._snapshot(run_id)


class SqlHistoricalWorkflowRunReader:
    """Read legacy workflow rows without creating tables or acquiring write rights."""

    def get_run(self, run_id: str) -> WorkflowRunRecord:
        with engine.connect() as conn:
            row: object = conn.execute(
                text(
                    """
                    SELECT run_id, status, node_statuses, metadata, created_at, updated_at
                    FROM public.workflow_graph_runs WHERE run_id = :run_id
                    """
                ),
                {"run_id": run_id},
            ).mappings().one_or_none()
        if row is None:
            _raise_store_failure(
                "object_not_found",
                f"historical run not found: {run_id}",
                exception_type=KeyError,
            )
        return {
            "run_id": str(_mapping_value(row, "run_id")),
            "status": _run_status(_mapping_value(row, "status")),
            "created_at": _to_iso(_mapping_value(row, "created_at")),
            "updated_at": _to_iso(_mapping_value(row, "updated_at")),
            "node_statuses": _node_statuses(_mapping_value(row, "node_statuses")),
            "metadata": _json_object(_mapping_value(row, "metadata"), field="run.metadata"),
        }

    def get_events(self, run_id: str) -> list[WorkflowGraphEvent]:
        run = self.get_run(run_id)
        with engine.connect() as conn:
            raw_rows: object = conn.execute(
                text(
                    """
                    SELECT seq, event_type, node_id, payload, ts
                    FROM public.workflow_graph_events
                    WHERE run_id = :run_id ORDER BY seq ASC
                    """
                ),
                {"run_id": run_id},
            ).mappings().all()
        if not isinstance(raw_rows, list):
            _raise_store_failure("contract_invalid", "event query must return a list")
        events: list[WorkflowGraphEvent] = []
        for raw_row in raw_rows:
            raw_seq = _mapping_value(raw_row, "seq")
            event_type = _mapping_value(raw_row, "event_type")
            raw_node_id = _mapping_value(raw_row, "node_id")
            if not isinstance(raw_seq, int) or not isinstance(event_type, str):
                _raise_store_failure("contract_invalid", "stored event identity is invalid")
            if raw_node_id is not None and not isinstance(raw_node_id, str):
                _raise_store_failure("contract_invalid", "stored event node_id is invalid")
            events.append(
                _build_event_record(
                    run_id=run_id,
                    seq=raw_seq,
                    event_type=event_type,
                    node_id=raw_node_id,
                    payload=_json_object(
                        _mapping_value(raw_row, "payload"), field="event.payload"
                    ),
                    run_metadata=run["metadata"],
                    created_at=_to_iso(_mapping_value(raw_row, "ts")),
                )
            )
        return events

    def get_results(self, run_id: str) -> WorkflowNodeResults:
        with engine.connect() as conn:
            row: object = conn.execute(
                text(
                    "SELECT results FROM public.workflow_graph_runs "
                    "WHERE run_id = :run_id"
                ),
                {"run_id": run_id},
            ).mappings().one_or_none()
        if row is None:
            _raise_store_failure(
                "object_not_found",
                f"historical run not found: {run_id}",
                exception_type=KeyError,
            )
        return _node_results(_mapping_value(row, "results"))

    def snapshot(self, run_id: str) -> WorkflowRunSnapshot:
        return {
            "run": self.get_run(run_id),
            "events": self.get_events(run_id),
            "results": self.get_results(run_id),
        }


def build_historical_workflow_run_reader() -> Annotated[
    HistoricalWorkflowRunReader,
    (
        "kit:prepared-command effect_boundary=workflow_graph.historical_readback "
        "witness=test:test_historical_handoff_reader_is_built_only_for_readback"
    ),
]:
    """Resolve the legacy decoder without initializing or mutating its tables."""

    if not bool(getattr(settings, "workflow_graph_db_store_enabled", True)):
        return InMemoryHistoricalWorkflowRunReader()
    return SqlHistoricalWorkflowRunReader()


class InMemoryCompiledGraphStore:
    """Thread-safe in-memory authority for compiled workflow artifacts."""

    def __init__(self) -> None:
        self._compiled: dict[str, CompiledWorkflowGraphRecord] = {}
        self._lock = RLock()

    def save_compiled(self, record: CompiledWorkflowGraphRecord) -> None:
        normalized = _normalize_compiled_record(record)
        with self._lock:
            self._compiled[normalized["graph_id"]] = normalized

    def get_compiled(self, graph_id: str) -> CompiledWorkflowGraphRecord:
        with self._lock:
            row = self._compiled.get(str(graph_id))
        if row is None:
            _raise_store_failure("object_not_found", f"compiled graph not found: {graph_id}", exception_type=KeyError)
        return deepcopy(row)

    def list_compiled(self, limit: int = 20) -> list[CompiledWorkflowGraphRecord]:
        with self._lock:
            rows = list(self._compiled.values())
        return [deepcopy(row) for row in rows[: max(1, int(limit or 20))]]


class SqlCompiledGraphStore:
    """PostgreSQL authority for durable compiled workflow artifacts."""

    _TABLE_NAME = "public.workflow_graph_compiled_artifacts"

    def __init__(self) -> None:
        def _create_table(conn: Connection) -> None:
            conn.execute(text('SET search_path TO "public"'))
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._TABLE_NAME} (
                        graph_id TEXT PRIMARY KEY,
                        version TEXT NOT NULL,
                        checksum TEXT NOT NULL,
                        payload_json JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )

        run_serialized_schema_ddl(engine, schema_name="public", operation=_create_table)

    def save_compiled(self, record: CompiledWorkflowGraphRecord) -> None:
        normalized = _normalize_compiled_record(record)
        with engine.begin() as conn:
            conn.execute(text('SET search_path TO "public"'))
            conn.execute(
                text(
                    f"""
                    INSERT INTO {self._TABLE_NAME}
                        (graph_id, version, checksum, payload_json, created_at, updated_at)
                    VALUES (:graph_id, :version, :checksum, CAST(:payload_json AS JSONB), NOW(), NOW())
                    ON CONFLICT (graph_id) DO UPDATE SET
                        version = EXCLUDED.version,
                        checksum = EXCLUDED.checksum,
                        payload_json = EXCLUDED.payload_json,
                        updated_at = NOW()
                    """
                ),
                {
                    "graph_id": normalized["graph_id"],
                    "version": normalized["version"],
                    "checksum": normalized["checksum"],
                    "payload_json": json.dumps(normalized, sort_keys=True),
                },
            )

    def get_compiled(self, graph_id: str) -> CompiledWorkflowGraphRecord:
        with engine.connect() as conn:
            row: object = conn.execute(
                text(f"SELECT payload_json FROM {self._TABLE_NAME} WHERE graph_id = :graph_id"),
                {"graph_id": str(graph_id)},
            ).mappings().one_or_none()
        if row is None:
            _raise_store_failure("object_not_found", f"compiled graph not found: {graph_id}", exception_type=KeyError)
        return _normalize_compiled_record(_mapping_value(row, "payload_json"))

    def list_compiled(self, limit: int = 20) -> list[CompiledWorkflowGraphRecord]:
        with engine.connect() as conn:
            raw_rows: object = conn.execute(
                text(
                    f"""
                    SELECT payload_json FROM {self._TABLE_NAME}
                    ORDER BY updated_at DESC LIMIT :limit
                    """
                ),
                {"limit": max(1, int(limit or 20))},
            ).mappings().all()
        if not isinstance(raw_rows, list):
            _raise_store_failure("contract_invalid", "compiled graph query must return a list")
        return [_normalize_compiled_record(_mapping_value(row, "payload_json")) for row in raw_rows]


def build_compiled_graph_store() -> Annotated[
    InMemoryCompiledGraphStore | SqlCompiledGraphStore,
    "kit:prepared-command effect_boundary=workflow_graph_compiled_store witness=test:test_w04_authority_metadata",
]:
    if not bool(getattr(settings, "workflow_graph_db_store_enabled", True)):
        return InMemoryCompiledGraphStore()
    try:
        return SqlCompiledGraphStore()
    except Exception as exc:  # noqa: BLE001
        if bool(getattr(settings, "workflow_graph_db_store_fail_closed", True)):
            _raise_store_failure(
                "store_unavailable",
                f"workflow graph compiled store unavailable (fail-closed): {exc}",
                exception_type=RuntimeError,
                cause=exc,
            )
        logger.warning("workflow graph compiled store disabled by runtime error, fallback to memory: %s", exc)
        return InMemoryCompiledGraphStore()


def _build_event_record(
    *,
    run_id: str,
    seq: int,
    event_type: str,
    node_id: str | None,
    payload: WorkflowJsonObject | None,
    run_metadata: WorkflowJsonObject | None,
    created_at: str | None = None,
) -> WorkflowGraphEvent:
    timestamp = str(created_at or "").strip() or _utcnow()
    normalized_payload = deepcopy(payload or {})
    metadata = run_metadata or {}
    project_key = _event_optional_text(normalized_payload, metadata, "project_key")
    session_id = _event_optional_text(normalized_payload, metadata, "session_id")
    trace_id = _event_optional_text(normalized_payload, metadata, "trace_id") or f"workflow_graph.{run_id}"
    return {
        "event_id": f"{run_id}:{seq}",
        "event_type": event_type,
        "project_key": project_key,
        "session_id": session_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "created_at": timestamp,
        "ts": timestamp,
        "seq": seq,
        "type": event_type,
        "node_id": node_id,
        "payload": normalized_payload,
    }


def _event_optional_text(
    payload: WorkflowJsonObject,
    metadata: WorkflowJsonObject,
    key: str,
) -> str | None:
    payload_value = payload.get(key)
    if isinstance(payload_value, str) and payload_value.strip():
        return payload_value.strip()
    metadata_value = metadata.get(key)
    if isinstance(metadata_value, str) and metadata_value.strip():
        return metadata_value.strip()
    return None


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _to_iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, str) and value.strip():
        return value
    return _utcnow()
