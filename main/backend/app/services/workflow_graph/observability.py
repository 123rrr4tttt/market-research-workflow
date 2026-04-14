from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.models.base import SessionLocal
from app.models.entities import WorkflowGraphEvent


OBSERVABILITY_CONTRACT_VERSION = "workflow_graph.observability.v1"


def query_top_failure_reasons(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 20), 100))
    try:
        with SessionLocal() as session:
            rows = (
                session.query(WorkflowGraphEvent)
                .filter(WorkflowGraphEvent.event_type.in_(["node.failed", "run.failed", "handoff.persisted", "handoff.replayed"]))
                .order_by(WorkflowGraphEvent.id.desc())
                .limit(2000)
                .all()
            )
    except Exception:  # noqa: BLE001
        rows = []

    reason_counter: Counter[str] = Counter()
    reason_meta: dict[str, dict[str, Any]] = {}
    handoff_persisted = 0
    handoff_replayed = 0

    for row in rows:
        event_type = str(row.event_type or "")
        payload = row.payload if isinstance(row.payload, dict) else {}
        if event_type == "handoff.persisted":
            handoff_persisted += 1
            continue
        if event_type == "handoff.replayed":
            handoff_replayed += 1
            continue
        reason_code = _resolve_reason_code(event_type=event_type, payload=payload)
        reason_counter[reason_code] += 1
        if reason_code not in reason_meta:
            reason_meta[reason_code] = {
                "sample_run_id": row.run_id,
                "event_type": event_type,
                "last_seen_at": _to_iso(row.ts),
            }

    items: list[dict[str, Any]] = []
    for reason_code, count in reason_counter.most_common(safe_limit):
        meta = reason_meta.get(reason_code) or {}
        items.append(
            {
                "reason_code": reason_code,
                "count": int(count),
                "event_type": meta.get("event_type"),
                "sample_run_id": meta.get("sample_run_id"),
                "last_seen_at": meta.get("last_seen_at"),
            }
        )

    return {
        "contract_version": OBSERVABILITY_CONTRACT_VERSION,
        "taxonomy_version": "workflow_graph.reason_taxonomy.v1",
        "window": "latest_2000_events",
        "items": items,
        "total_reasons": len(reason_counter),
        "handoff_metrics": {
            "persisted_total": handoff_persisted,
            "replayed_total": handoff_replayed,
            "replay_ratio": _safe_ratio(handoff_replayed, handoff_persisted),
        },
        "backend_marker": "workflow_graph.events",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _resolve_reason_code(*, event_type: str, payload: dict[str, Any]) -> str:
    explicit = str(payload.get("reason_code") or "").strip().lower()
    if explicit:
        return explicit
    reason_text = str(payload.get("reason") or payload.get("error") or "").strip().lower()
    if not reason_text:
        return f"{event_type}.unknown"
    if "prompt_template_missing_inputs" in reason_text:
        return "prompt_template_missing_inputs"
    if "unsupported node_type" in reason_text:
        return "unsupported_node_type"
    if "node_missing_in_graph" in reason_text:
        return "node_missing_in_graph"
    if "timeout" in reason_text:
        return "timeout"
    return f"{event_type}.error"


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return None
