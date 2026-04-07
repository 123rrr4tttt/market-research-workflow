from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .store import InMemoryRunStore, SqlRunStore, build_run_store

HANDOFF_CONTRACT_VERSION = "workflow_graph.handoff.v1"
_ALLOWED_HANDOFF_MODES = {"pull_prepared_evidence", "push_payload"}
_ALLOWED_EVENT_TYPES = {"handoff.persisted", "handoff.replayed"}


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
        self._store = store or build_run_store()

    def persist(self, *, graph_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        envelope = _normalize_handoff_payload(graph_id=graph_id, payload=payload)
        self._ensure_run_exists(envelope.run_id, graph_id)
        event = self._store.append_event(
            envelope.run_id,
            event_type="handoff.persisted",
            payload=envelope.to_dict(),
        )
        return {
            "contract_version": HANDOFF_CONTRACT_VERSION,
            "run_id": envelope.run_id,
            "handoff_id": envelope.handoff_id,
            "event_seq": event.get("seq"),
            "event_type": event.get("type"),
            "backend_marker": "workflow_graph.run_store",
        }

    def list_handoffs(self, *, run_id: str, handoff_mode: str | None = None) -> dict[str, Any]:
        events = self._store.get_events(str(run_id))
        items: list[dict[str, Any]] = []
        for event in events:
            event_type = str(event.get("type") or "")
            if not event_type.startswith("handoff."):
                continue
            if event_type not in _ALLOWED_EVENT_TYPES:
                raise ValueError(f"unknown handoff event type: {event_type}")
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
            raise ValueError("handoff_id is required")
        events = self._store.get_events(resolved_run_id)
        matched: list[dict[str, Any]] = []
        current_payload: dict[str, Any] | None = None
        for event in events:
            event_type = str(event.get("type") or "")
            if not event_type.startswith("handoff."):
                continue
            if event_type not in _ALLOWED_EVENT_TYPES:
                raise ValueError(f"unknown handoff event type: {event_type}")
            payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
            if str(payload.get("handoff_id") or "") != resolved_handoff_id:
                continue
            matched.append(event)
            if event_type == "handoff.persisted":
                current_payload = dict(payload)
        if current_payload is None:
            raise KeyError(f"handoff not found: {resolved_handoff_id}")

        replay_event = self._store.append_event(
            resolved_run_id,
            event_type="handoff.replayed",
            payload={
                "run_id": resolved_run_id,
                "handoff_id": resolved_handoff_id,
                "contract_version": HANDOFF_CONTRACT_VERSION,
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
        try:
            self._store.get_run(run_id)
        except KeyError:
            self._store.create_run(run_id=run_id, topo_order=[], metadata={"workflow_id": graph_id, "source": "handoff"})


def _normalize_handoff_payload(*, graph_id: str, payload: Mapping[str, Any]) -> HandoffEnvelope:
    if not isinstance(payload, Mapping):
        raise ValueError("handoff payload must be a mapping")

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
        raise ValueError("handoff_id is required")
    if not contract_version:
        raise ValueError("contract_version is required")
    if handoff_mode not in _ALLOWED_HANDOFF_MODES:
        raise ValueError(f"unsupported handoff_mode: {handoff_mode}")
    if not consumer:
        raise ValueError("consumer is required")
    if not producer:
        raise ValueError("producer is required")

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
