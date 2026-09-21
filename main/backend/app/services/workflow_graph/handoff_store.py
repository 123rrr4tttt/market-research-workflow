from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Mapping

from .governance_contract import build_handoff_audit_record
from .store import InMemoryRunStore, SqlRunStore, build_run_store
from .contracts import raise_workflow_graph_legacy, workflow_graph_failure

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
    def __init__(self, *, store: InMemoryRunStore | SqlRunStore | None = None) -> None:
        self._store = store
        self._lock = RLock()

    def _resolved_store(self) -> InMemoryRunStore | SqlRunStore:
        with self._lock:
            if self._store is None:
                self._store = build_run_store()
            return self._store

    def persist(self, *, graph_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        envelope = _normalize_handoff_payload(graph_id=graph_id, payload=payload)
        self._ensure_run_exists(envelope.run_id, graph_id)
        event_payload = envelope.to_dict()
        event_payload["audit"] = build_handoff_audit_record(
            action="handoff.persisted",
            graph_id=envelope.graph_id,
            run_id=envelope.run_id,
            handoff_id=envelope.handoff_id,
            handoff_mode=envelope.handoff_mode,
            producer=envelope.producer,
            consumer=envelope.consumer,
            evidence_pack=envelope.evidence_pack,
        )
        event = self._resolved_store().append_event(
            envelope.run_id,
            event_type="handoff.persisted",
            payload=event_payload,
        )
        return {
            "contract_version": HANDOFF_CONTRACT_VERSION,
            "run_id": envelope.run_id,
            "handoff_id": envelope.handoff_id,
            "event_seq": event.get("seq"),
            "event_type": event.get("type"),
            "audit_id": event_payload["audit"].get("audit_id"),
            "audit_contract_version": event_payload["audit"].get("contract_version"),
            "backend_marker": "workflow_graph.run_store",
        }

    def list_handoffs(self, *, run_id: str, handoff_mode: str | None = None) -> dict[str, Any]:
        events = self._resolved_store().get_events(str(run_id))
        items: list[dict[str, Any]] = []
        for event in events:
            event_type = str(event.get("type") or "")
            if not event_type.startswith("handoff."):
                continue
            if event_type not in _ALLOWED_EVENT_TYPES:
                _raise_handoff_failure("contract_invalid", f"unknown handoff event type: {event_type}")
            payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
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
            "backend_marker": "workflow_graph.run_store",
        }

    def replay_handoff(self, *, run_id: str, handoff_id: str) -> dict[str, Any]:
        resolved_run_id = str(run_id)
        resolved_handoff_id = str(handoff_id or "").strip()
        if not resolved_handoff_id:
            _raise_handoff_failure("contract_invalid", "handoff_id is required")
        store = self._resolved_store()
        events = store.get_events(resolved_run_id)
        matched: list[dict[str, Any]] = []
        current_payload: dict[str, Any] | None = None
        for event in events:
            event_type = str(event.get("type") or "")
            if not event_type.startswith("handoff."):
                continue
            if event_type not in _ALLOWED_EVENT_TYPES:
                _raise_handoff_failure("contract_invalid", f"unknown handoff event type: {event_type}")
            payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
            if str(payload.get("handoff_id") or "") != resolved_handoff_id:
                continue
            matched.append(event)
            if event_type == "handoff.persisted":
                current_payload = dict(payload)
        if current_payload is None:
            _raise_handoff_failure("object_not_found", f"handoff not found: {resolved_handoff_id}", exception_type=KeyError)

        replay_event = store.append_event(
            resolved_run_id,
            event_type="handoff.replayed",
            payload={
                "run_id": resolved_run_id,
                "handoff_id": resolved_handoff_id,
                "contract_version": HANDOFF_CONTRACT_VERSION,
                "audit": build_handoff_audit_record(
                    action="handoff.replayed",
                    graph_id=str(current_payload.get("graph_id") or "unknown"),
                    run_id=resolved_run_id,
                    handoff_id=resolved_handoff_id,
                    handoff_mode=str(current_payload.get("handoff_mode") or "pull_prepared_evidence"),
                    producer=str(
                        current_payload.get("producer")
                        or current_payload.get("owner")
                        or "workflow_graph.backend_bridge"
                    ),
                    consumer=str(current_payload.get("consumer") or "unknown"),
                    evidence_pack=current_payload.get("evidence_pack")
                    if isinstance(current_payload.get("evidence_pack"), Mapping)
                    else {},
                ),
            },
        )
        matched.append(replay_event)
        ordered = sorted(matched, key=lambda x: int(x.get("seq") or 0))
        return {
            "contract_version": HANDOFF_CONTRACT_VERSION,
            "run_id": resolved_run_id,
            "handoff_id": resolved_handoff_id,
            "events": ordered,
            "result": current_payload,
            "backend_marker": "workflow_graph.run_store",
        }

    def _ensure_run_exists(self, run_id: str, graph_id: str) -> None:
        store = self._resolved_store()
        try:
            store.get_run(run_id)
        except KeyError:
            store.create_run(run_id=run_id, topo_order=[], metadata={"workflow_id": graph_id, "source": "handoff"})


def _normalize_handoff_payload(*, graph_id: str, payload: Mapping[str, Any]) -> HandoffEnvelope:
    if not isinstance(payload, Mapping):
        _raise_handoff_failure("contract_invalid", "handoff payload must be a mapping")

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
        evidence_pack=dict(evidence_pack),
        payload=dict(payload),
    )


handoff_store = WorkflowGraphHandoffStore()
