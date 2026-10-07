from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, cast

from .contracts import (
    WorkflowGraphEvent,
    raise_workflow_graph_legacy,
    workflow_graph_failure,
)
from .store import (
    HistoricalWorkflowRunReader,
    build_historical_workflow_run_reader,
)

HANDOFF_CONTRACT_VERSION = "workflow_graph.handoff.v1"
_ALLOWED_HANDOFF_MODES = {"pull_prepared_evidence", "push_payload"}
_ALLOWED_EVENT_TYPES = {"handoff.persisted", "handoff.replayed"}


def _raise_handoff_failure(code: str, message: str, *, exception_type: type[Exception] = ValueError) -> None:
    failure = workflow_graph_failure(
        code,
        message,
        owner="workflow_graph.handoff_store",
        public_exception=exception_type,
        public_message=message,
        field="handoff",
        index=-1,
    )
    raise_workflow_graph_legacy(failure, exception_type=exception_type)


@dataclass(frozen=True)
class HandoffEnvelope:
    run_id: str
    graph_id: str
    contract_version: str
    handoff_id: str
    handoff_mode: str
    producer: str
    consumer: str
    evidence_pack: dict[str, Any]
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "graph_id": self.graph_id,
            "contract_version": self.contract_version,
            "handoff_id": self.handoff_id,
            "handoff_mode": self.handoff_mode,
            "producer": self.producer,
            "consumer": self.consumer,
            "evidence_pack": dict(self.evidence_pack),
            "payload": dict(self.payload),
        }


class WorkflowGraphHandoffStore:
    """Build new handoffs and decode retired-run handoffs without writing them."""

    def __init__(self, *, reader: HistoricalWorkflowRunReader | None = None) -> None:
        self._reader = reader

    def _resolved_reader(self) -> HistoricalWorkflowRunReader:
        if self._reader is None:
            self._reader = build_historical_workflow_run_reader()
        return self._reader

    def _require_historical_project(self, *, run_id: str, project_key: str) -> None:
        run = self._resolved_reader().get_run(str(run_id))
        metadata = run.get("metadata")
        stored_project_key = str(metadata.get("project_key") or "").strip()
        if not project_key or stored_project_key != project_key:
            _raise_handoff_failure(
                "object_not_found",
                "historical handoff run is not available in this project",
                exception_type=KeyError,
            )

    def build(self, *, graph_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return the typed request-local handoff carrier without a side effect."""

        envelope = _normalize_handoff_payload(graph_id=graph_id, payload=payload)
        event_payload = envelope.to_dict()
        return {
            "contract_version": HANDOFF_CONTRACT_VERSION,
            "run_id": envelope.run_id,
            "handoff_id": envelope.handoff_id,
            "handoff_mode": envelope.handoff_mode,
            "payload": event_payload,
            "durable": False,
            "backend_marker": "workflow_graph.request_local_handoff",
        }

    def list_handoffs(
        self,
        *,
        run_id: str,
        handoff_mode: str | None = None,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        if project_key is not None:
            self._require_historical_project(run_id=run_id, project_key=project_key)
        events = self._resolved_reader().get_events(str(run_id))
        items: list[dict[str, Any]] = []
        for event in events:
            event_type = str(event.get("type") or "")
            if not event_type.startswith("handoff."):
                continue
            if event_type not in _ALLOWED_EVENT_TYPES:
                _raise_handoff_failure("contract_invalid", f"unknown handoff event type: {event_type}")
            payload = event["payload"]
            if event_type != "handoff.persisted":
                continue
            if handoff_mode and str(payload.get("handoff_mode") or "") != str(handoff_mode):
                continue
            item = {
                "seq": int(event.get("seq") or 0),
                "ts": event.get("ts"),
                "event_type": event_type,
                "handoff_id": payload.get("handoff_id"),
                "handoff_mode": payload.get("handoff_mode"),
                "producer": payload.get("producer"),
                "consumer": payload.get("consumer"),
                "contract_version": payload.get("contract_version"),
            }
            items.append(item)
        return {
            "contract_version": HANDOFF_CONTRACT_VERSION,
            "run_id": str(run_id),
            "items": items,
            "total": len(items),
            "read_only": True,
            "backend_marker": "workflow_graph.historical_run_decoder",
        }

    def replay_handoff(
        self,
        *,
        run_id: str,
        handoff_id: str,
        project_key: str | None = None,
    ) -> dict[str, Any]:
        resolved_run_id = str(run_id)
        resolved_handoff_id = str(handoff_id or "").strip()
        if not resolved_handoff_id:
            _raise_handoff_failure("contract_invalid", "handoff_id is required")
        if project_key is not None:
            self._require_historical_project(
                run_id=resolved_run_id,
                project_key=project_key,
            )
        events = self._resolved_reader().get_events(resolved_run_id)
        matched: list[WorkflowGraphEvent] = []
        current_payload: dict[str, Any] | None = None
        for event in events:
            event_type = str(event.get("type") or "")
            if not event_type.startswith("handoff."):
                continue
            if event_type not in _ALLOWED_EVENT_TYPES:
                _raise_handoff_failure("contract_invalid", f"unknown handoff event type: {event_type}")
            payload = event["payload"]
            if str(payload.get("handoff_id") or "") != resolved_handoff_id:
                continue
            matched.append(event)
            if event_type == "handoff.persisted":
                current_payload = dict(payload)
        if current_payload is None:
            _raise_handoff_failure("object_not_found", f"handoff not found: {resolved_handoff_id}", exception_type=KeyError)

        ordered = sorted(matched, key=lambda x: int(x.get("seq") or 0))
        return {
            "contract_version": HANDOFF_CONTRACT_VERSION,
            "run_id": resolved_run_id,
            "handoff_id": resolved_handoff_id,
            "events": ordered,
            "result": current_payload,
            "read_only": True,
            "backend_marker": "workflow_graph.historical_run_decoder",
        }


def _normalize_handoff_payload(*, graph_id: str, payload: Mapping[str, Any]) -> HandoffEnvelope:
    run_id = str(payload.get("run_id") or "").strip()
    handoff_id = str(payload.get("handoff_id") or "").strip()
    contract_version = str(payload.get("contract_version") or "").strip()
    handoff_mode = str(payload.get("handoff_mode") or "").strip()
    consumer = str(payload.get("consumer") or "").strip()
    producer = str(payload.get("producer") or payload.get("owner") or "workflow_graph.backend_bridge").strip()

    if not run_id:
        fallback_graph = str(graph_id or "graph").strip() or "graph"
        run_id = f"handoff-{fallback_graph}"
    if not handoff_id:
        _raise_handoff_failure("contract_invalid", "handoff_id is required")
    if not contract_version:
        _raise_handoff_failure("contract_invalid", "contract_version is required")
    if handoff_mode not in _ALLOWED_HANDOFF_MODES:
        _raise_handoff_failure("contract_invalid", f"unsupported handoff_mode: {handoff_mode}")
    if not consumer:
        _raise_handoff_failure("contract_invalid", "consumer is required")
    if not producer:
        _raise_handoff_failure("contract_invalid", "producer is required")

    evidence_pack = payload.get("evidence_pack")
    if evidence_pack is None:
        evidence_pack = payload.get("graph_context")
    if not isinstance(evidence_pack, Mapping):
        evidence_pack = {}

    return HandoffEnvelope(
        run_id=run_id,
        graph_id=str(graph_id or "").strip(),
        contract_version=contract_version,
        handoff_id=handoff_id,
        handoff_mode=handoff_mode,
        producer=producer,
        consumer=consumer,
        evidence_pack=dict(cast(Mapping[str, Any], evidence_pack)),
        payload=dict(payload),
    )


handoff_store = WorkflowGraphHandoffStore()
