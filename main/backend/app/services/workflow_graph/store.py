from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Annotated, Any
from uuid import uuid4
import json
import logging

from sqlalchemy import func, text

from app.models.base import Base, SessionLocal, engine
from app.models.entities import WorkflowGraphEvent, WorkflowGraphRun
from app.settings.config import settings
from app.services.projects.schema_initialization import run_serialized_schema_ddl
from .contracts import raise_workflow_graph_legacy, workflow_graph_failure

TERMINAL_STATUSES = {"succeeded", "failed"}
NODE_STATUSES = {"queued", "running", "succeeded", "failed"}
RUN_STATUSES = {"queued", "running", "succeeded", "failed"}

logger = logging.getLogger("app.services.workflow_graph.store")


def _raise_store_failure(
    code: str,
    message: str,
    *,
    exception_type: type[Exception] = ValueError,
    cause: BaseException | None = None,
) -> None:
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


class InMemoryRunStore:
    """Thread-safe in-memory store for workflow runs/events/results."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def create_run(
        self,
        *,
        run_id: str | None = None,
        topo_order: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        with self._lock:
            resolved_run_id = str(run_id or uuid4().hex)
            now = _utcnow()
            node_statuses = {node_id: "queued" for node_id in (topo_order or [])}
            self._runs[resolved_run_id] = {
                "run_id": resolved_run_id,
                "status": "queued",
                "created_at": now,
                "updated_at": now,
                "node_statuses": node_statuses,
                "metadata": deepcopy(metadata or {}),
            }
            self._events[resolved_run_id] = []
            self._results[resolved_run_id] = {}
            return resolved_run_id

    def ensure_node(self, run_id: str, node_id: str) -> None:
        with self._lock:
            run = self._must_get_run_ref(run_id)
            run["node_statuses"].setdefault(node_id, "queued")
            run["updated_at"] = _utcnow()

    def set_run_status(self, run_id: str, status: str) -> None:
        if status not in RUN_STATUSES:
            _raise_store_failure("contract_invalid", f"unsupported run status: {status}")
        with self._lock:
            run = self._must_get_run_ref(run_id)
            run["status"] = status
            run["updated_at"] = _utcnow()

    def set_node_status(self, run_id: str, node_id: str, status: str) -> None:
        if status not in NODE_STATUSES:
            _raise_store_failure("contract_invalid", f"unsupported node status: {status}")
        with self._lock:
            run = self._must_get_run_ref(run_id)
            run["node_statuses"][node_id] = status
            run["updated_at"] = _utcnow()

    def set_node_result(self, run_id: str, node_id: str, result: Any) -> None:
        with self._lock:
            self._must_get_run_ref(run_id)
            self._results[run_id][node_id] = deepcopy(result)

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            run = self._must_get_run_ref(run_id)
            seq = len(self._events[run_id]) + 1
            event = _build_event_record(
                run_id=run_id,
                seq=seq,
                event_type=str(event_type),
                node_id=node_id,
                payload=payload,
                run_metadata=run.get("metadata"),
            )
            self._events[run_id].append(event)
            return deepcopy(event)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._must_get_run_ref(run_id))

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._must_get_run_ref(run_id)
            return deepcopy(self._events[run_id])

    def get_results(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            self._must_get_run_ref(run_id)
            return deepcopy(self._results[run_id])

    def snapshot(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return {
                "run": self.get_run(run_id),
                "events": self.get_events(run_id),
                "results": self.get_results(run_id),
            }

    def _must_get_run_ref(self, run_id: str) -> dict[str, Any]:
        run = self._runs.get(run_id)
        if run is None:
            _raise_store_failure("object_not_found", f"run not found: {run_id}", exception_type=KeyError)
        return run


class InMemoryCompiledGraphStore:
    """Thread-safe in-memory store for compiled workflow graph artifacts."""

    def __init__(self) -> None:
        self._compiled: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def save_compiled(self, record: dict[str, Any]) -> None:
        normalized = _normalize_compiled_record(record)
        graph_id = str(normalized.get("graph_id") or "").strip()
        with self._lock:
            self._compiled[graph_id] = normalized

    def get_compiled(self, graph_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._compiled.get(str(graph_id))
        if row is None:
            _raise_store_failure("object_not_found", f"compiled graph not found: {graph_id}", exception_type=KeyError)
        return deepcopy(row)

    def list_compiled(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._compiled.values())
        return [deepcopy(row) for row in rows[: max(1, int(limit or 20))]]


class SqlRunStore:
    """DB-backed store for workflow graph runs/events/results."""

    def __init__(self) -> None:
        def _create_tables(conn: Any) -> None:
            conn.execute(text('SET search_path TO "public"'))
            Base.metadata.create_all(
                bind=conn,
                tables=[WorkflowGraphRun.__table__, WorkflowGraphEvent.__table__],
                checkfirst=True,
            )

        run_serialized_schema_ddl(
            engine,
            schema_name="public",
            operation=_create_tables,
        )

    def create_run(
        self,
        *,
        run_id: str | None = None,
        topo_order: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        resolved_run_id = str(run_id or uuid4().hex)
        node_statuses = {node_id: "queued" for node_id in (topo_order or [])}
        with SessionLocal() as session:
            row = session.query(WorkflowGraphRun).filter(WorkflowGraphRun.run_id == resolved_run_id).one_or_none()
            if row is None:
                row = WorkflowGraphRun(
                    run_id=resolved_run_id,
                    workflow_id=str((metadata or {}).get("workflow_id") or "") or None,
                    status="queued",
                    node_statuses=node_statuses,
                    metadata_json=dict(metadata or {}),
                    results={},
                )
                session.add(row)
            else:
                row.status = "queued"
                row.node_statuses = node_statuses
                row.metadata_json = dict(metadata or {})
                row.results = {}
            session.commit()
        return resolved_run_id

    def ensure_node(self, run_id: str, node_id: str) -> None:
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            status_map = dict(row.node_statuses or {})
            status_map.setdefault(node_id, "queued")
            row.node_statuses = status_map
            session.commit()

    def set_run_status(self, run_id: str, status: str) -> None:
        if status not in RUN_STATUSES:
            _raise_store_failure("contract_invalid", f"unsupported run status: {status}")
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            row.status = status
            session.commit()

    def set_node_status(self, run_id: str, node_id: str, status: str) -> None:
        if status not in NODE_STATUSES:
            _raise_store_failure("contract_invalid", f"unsupported node status: {status}")
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            status_map = dict(row.node_statuses or {})
            status_map[node_id] = status
            row.node_statuses = status_map
            session.commit()

    def set_node_result(self, run_id: str, node_id: str, result: Any) -> None:
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            results = dict(row.results or {})
            results[node_id] = deepcopy(result)
            row.results = results
            session.commit()

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as session:
            self._must_get_run_row(session, run_id)
            seq = int(
                session.query(func.coalesce(func.max(WorkflowGraphEvent.seq), 0))
                .filter(WorkflowGraphEvent.run_id == run_id)
                .scalar()
                or 0
            ) + 1
            row = WorkflowGraphEvent(
                run_id=run_id,
                seq=seq,
                event_type=str(event_type),
                node_id=node_id,
                payload=deepcopy(payload or {}),
            )
            session.add(row)
            session.commit()
            run_metadata = deepcopy((self._must_get_run_row(session, run_id).metadata_json or {}))
            return _build_event_record(
                run_id=run_id,
                seq=seq,
                event_type=row.event_type,
                node_id=row.node_id,
                payload=row.payload,
                run_metadata=run_metadata,
                created_at=_to_iso(row.ts),
            )

    def get_run(self, run_id: str) -> dict[str, Any]:
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            return {
                "run_id": row.run_id,
                "status": row.status,
                "created_at": _to_iso(row.created_at),
                "updated_at": _to_iso(row.updated_at),
                "node_statuses": deepcopy(row.node_statuses or {}),
                "metadata": deepcopy(row.metadata_json or {}),
            }

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        with SessionLocal() as session:
            run = self._must_get_run_row(session, run_id)
            run_metadata = deepcopy(run.metadata_json or {})
            rows = (
                session.query(WorkflowGraphEvent)
                .filter(WorkflowGraphEvent.run_id == run_id)
                .order_by(WorkflowGraphEvent.seq.asc())
                .all()
            )
            return [
                _build_event_record(
                    run_id=run_id,
                    seq=int(row.seq or 0),
                    event_type=row.event_type,
                    node_id=row.node_id,
                    payload=row.payload,
                    run_metadata=run_metadata,
                    created_at=_to_iso(row.ts),
                )
                for row in rows
            ]

    def get_results(self, run_id: str) -> dict[str, Any]:
        with SessionLocal() as session:
            row = self._must_get_run_row(session, run_id)
            return deepcopy(row.results or {})

    def snapshot(self, run_id: str) -> dict[str, Any]:
        return {
            "run": self.get_run(run_id),
            "events": self.get_events(run_id),
            "results": self.get_results(run_id),
        }

    @staticmethod
    def _must_get_run_row(session: Any, run_id: str) -> WorkflowGraphRun:
        row = session.query(WorkflowGraphRun).filter(WorkflowGraphRun.run_id == run_id).one_or_none()
        if row is None:
            _raise_store_failure("object_not_found", f"run not found: {run_id}", exception_type=KeyError)
        return row


class SqlCompiledGraphStore:
    """DB-backed store for durable compiled workflow graph artifacts."""

    _TABLE_NAME = "workflow_graph_compiled_artifacts"

    def __init__(self) -> None:
        def _create_table(conn: Any) -> None:
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

        run_serialized_schema_ddl(
            engine,
            schema_name="public",
            operation=_create_table,
        )

    def save_compiled(self, record: dict[str, Any]) -> None:
        normalized = _normalize_compiled_record(record)
        with engine.begin() as conn:
            conn.execute(text('SET search_path TO "public"'))
            conn.execute(
                text(
                    f"""
                    INSERT INTO {self._TABLE_NAME} (
                        graph_id,
                        version,
                        checksum,
                        payload_json,
                        created_at,
                        updated_at
                    ) VALUES (
                        :graph_id,
                        :version,
                        :checksum,
                        CAST(:payload_json AS JSONB),
                        NOW(),
                        NOW()
                    )
                    ON CONFLICT (graph_id) DO UPDATE SET
                        version = EXCLUDED.version,
                        checksum = EXCLUDED.checksum,
                        payload_json = EXCLUDED.payload_json,
                        updated_at = NOW()
                    """
                ),
                {
                    "graph_id": str(normalized.get("graph_id") or ""),
                    "version": str(normalized.get("version") or ""),
                    "checksum": str(normalized.get("checksum") or ""),
                    "payload_json": json.dumps(normalized, sort_keys=True),
                },
            )

    def get_compiled(self, graph_id: str) -> dict[str, Any]:
        with engine.connect() as conn:
            conn.execute(text('SET search_path TO "public"'))
            row = conn.execute(
                text(
                    f"""
                    SELECT payload_json
                    FROM {self._TABLE_NAME}
                    WHERE graph_id = :graph_id
                    """
                ),
                {"graph_id": str(graph_id)},
            ).mappings().one_or_none()
        if row is None:
            _raise_store_failure("object_not_found", f"compiled graph not found: {graph_id}", exception_type=KeyError)
        return _normalize_compiled_payload(row.get("payload_json"))

    def list_compiled(self, limit: int = 20) -> list[dict[str, Any]]:
        with engine.connect() as conn:
            conn.execute(text('SET search_path TO "public"'))
            rows = conn.execute(
                text(
                    f"""
                    SELECT payload_json
                    FROM {self._TABLE_NAME}
                    ORDER BY updated_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, int(limit or 20))},
            ).mappings().all()
        return [_normalize_compiled_payload(row.get("payload_json")) for row in rows]


def build_run_store() -> Annotated[
    InMemoryRunStore | SqlRunStore,
    "kit:prepared-command effect_boundary=workflow_graph_run_store "
    "witness=test:test_w04_authority_metadata",
]:
    """Construct runtime store with fail-closed option."""
    if not bool(getattr(settings, "workflow_graph_db_store_enabled", True)):
        return InMemoryRunStore()
    try:
        return SqlRunStore()
    except Exception as exc:  # noqa: BLE001
        if bool(getattr(settings, "workflow_graph_db_store_fail_closed", True)):
            _raise_store_failure("store_unavailable", f"workflow graph db store unavailable (fail-closed): {exc}", exception_type=RuntimeError, cause=exc)
        logger.warning("workflow graph db store disabled by runtime error, fallback to memory: %s", exc)
        return InMemoryRunStore()


def build_compiled_graph_store() -> Annotated[
    InMemoryCompiledGraphStore | SqlCompiledGraphStore,
    "kit:prepared-command effect_boundary=workflow_graph_compiled_store "
    "witness=test:test_w04_authority_metadata",
]:
    """Construct durable compiled graph store with the same fail-closed policy as run store."""
    if not bool(getattr(settings, "workflow_graph_db_store_enabled", True)):
        return InMemoryCompiledGraphStore()
    try:
        return SqlCompiledGraphStore()
    except Exception as exc:  # noqa: BLE001
        if bool(getattr(settings, "workflow_graph_db_store_fail_closed", True)):
            _raise_store_failure("store_unavailable", f"workflow graph compiled store unavailable (fail-closed): {exc}", exception_type=RuntimeError, cause=exc)
        logger.warning("workflow graph compiled store disabled by runtime error, fallback to memory: %s", exc)
        return InMemoryCompiledGraphStore()


def _build_event_record(
    *,
    run_id: str,
    seq: int,
    event_type: str,
    node_id: str | None,
    payload: dict[str, Any] | None,
    run_metadata: dict[str, Any] | None,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = str(created_at or "").strip() or _utcnow()
    normalized_payload = deepcopy(payload or {})
    metadata = run_metadata if isinstance(run_metadata, dict) else {}
    project_key = (
        str(normalized_payload.get("project_key") or "").strip()
        or str(metadata.get("project_key") or "").strip()
        or None
    )
    session_id = (
        str(normalized_payload.get("session_id") or "").strip()
        or str(metadata.get("session_id") or "").strip()
        or None
    )
    trace_id = (
        str(normalized_payload.get("trace_id") or "").strip()
        or str(metadata.get("trace_id") or "").strip()
        or f"workflow_graph.{run_id}"
    )
    return {
        "event_id": f"{run_id}:{seq}",
        "event_type": str(event_type),
        "project_key": project_key,
        "session_id": session_id,
        "run_id": str(run_id),
        "trace_id": trace_id,
        "created_at": timestamp,
        "ts": timestamp,
        "seq": int(seq),
        "type": str(event_type),
        "node_id": node_id,
        "payload": normalized_payload,
    }


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return _utcnow()


def _normalize_compiled_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        _raise_store_failure("contract_invalid", "compiled graph record must be a dict")
    graph_id = str(record.get("graph_id") or "").strip()
    if not graph_id:
        _raise_store_failure("contract_invalid", "compiled graph record requires graph_id")
    version = str(record.get("version") or "").strip()
    checksum = str(record.get("checksum") or "").strip()
    if not version:
        _raise_store_failure("contract_invalid", "compiled graph record requires version")
    if not checksum:
        _raise_store_failure("contract_invalid", "compiled graph record requires checksum")
    return deepcopy(record)


def _normalize_compiled_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception as exc:  # noqa: BLE001
            _raise_store_failure("contract_invalid", f"compiled graph payload is not valid JSON: {exc}", cause=exc)
    if not isinstance(value, dict):
        _raise_store_failure("contract_invalid", "compiled graph payload must be a dict")
    return _normalize_compiled_record(value)
