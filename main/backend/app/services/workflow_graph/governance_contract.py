from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

AUDIT_CONTRACT_VERSION = "workflow_graph.governance_audit.v1"
ROLLBACK_CONTRACT_VERSION = "workflow_graph.rollback.v1"

GRAPH_EDIT_AUDIT_ACTIONS = frozenset({"submit", "rollback"})
HANDOFF_AUDIT_ACTIONS = frozenset({"handoff.persisted", "handoff.replayed"})
AUDIT_ACTIONS = GRAPH_EDIT_AUDIT_ACTIONS | HANDOFF_AUDIT_ACTIONS

GRAPH_GOVERNANCE_OBJECT_SCOPES = frozenset({"curated_business_graph", "graph_handoff"})
AUDIT_STATUSES = frozenset({"succeeded", "failed", "rejected"})
HANDOFF_MODES = frozenset({"pull_prepared_evidence", "push_payload"})

ROLLBACK_SCOPE = "snapshot_restore"
VERSION_SEMANTICS = "curated_graph_revision_separate_from_template_versions"


def build_graph_edit_audit_record(
    *,
    action: str,
    actor_id: str,
    project_key: str,
    graph_id: str,
    object_scope: str,
    from_revision: int,
    to_revision: int,
    version_id: str,
    timestamp: str | None = None,
    audit_id: str | None = None,
    status: str = "succeeded",
    rollback_from_version_id: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_action = _required_str(action, "action")
    if resolved_action not in GRAPH_EDIT_AUDIT_ACTIONS:
        raise ValueError(f"unsupported graph edit audit action: {resolved_action}")

    resolved_scope = _required_str(object_scope, "object_scope")
    if resolved_scope != "curated_business_graph":
        raise ValueError(f"unsupported graph edit object_scope: {resolved_scope}")

    resolved_from_revision = _non_negative_int(from_revision, "from_revision")
    resolved_to_revision = _non_negative_int(to_revision, "to_revision")
    if resolved_to_revision <= resolved_from_revision:
        raise ValueError("to_revision must be greater than from_revision")

    resolved_rollback_from = str(rollback_from_version_id or "").strip() or None
    if resolved_action == "rollback" and not resolved_rollback_from:
        raise ValueError("rollback_from_version_id is required for rollback audit")
    if resolved_action == "submit" and resolved_rollback_from:
        raise ValueError("rollback_from_version_id is only allowed for rollback audit")

    record = _base_audit_record(
        action=resolved_action,
        actor_id=actor_id,
        graph_id=graph_id,
        object_scope=resolved_scope,
        timestamp=timestamp,
        audit_id=audit_id,
        status=status,
        project_key=project_key,
    )
    record.update(
        {
            "from_revision": resolved_from_revision,
            "to_revision": resolved_to_revision,
            "version_id": _required_str(version_id, "version_id"),
            "version_semantics": VERSION_SEMANTICS,
        }
    )
    if resolved_rollback_from:
        record["rollback_from_version_id"] = resolved_rollback_from
    if context is not None:
        record["context"] = dict(context)
    return record


def build_graph_rollback_contract(
    *,
    actor_id: str,
    project_key: str,
    graph_id: str,
    target_version_id: str,
    current_revision: int,
    base_revision: int | None,
    requested_at: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    resolved_current_revision = _non_negative_int(current_revision, "current_revision")
    resolved_base_revision = None
    if base_revision is not None:
        resolved_base_revision = _non_negative_int(base_revision, "base_revision")

    contract = {
        "contract_version": ROLLBACK_CONTRACT_VERSION,
        "graph_id": _required_str(graph_id, "graph_id"),
        "actor_id": _required_str(actor_id, "actor_id"),
        "project_key": _required_str(project_key, "project_key"),
        "object_scope": "curated_business_graph",
        "rollback_scope": ROLLBACK_SCOPE,
        "target_version_id": _required_str(target_version_id, "target_version_id"),
        "current_revision": resolved_current_revision,
        "base_revision": resolved_base_revision,
        "requires_base_revision_match": True,
        "version_semantics": VERSION_SEMANTICS,
        "requested_at": requested_at or _utcnow(),
    }
    resolved_reason = str(reason or "").strip()
    if resolved_reason:
        contract["reason"] = resolved_reason[:500]
    return contract


def build_handoff_audit_record(
    *,
    action: str,
    graph_id: str,
    run_id: str,
    handoff_id: str,
    handoff_mode: str,
    producer: str,
    consumer: str,
    timestamp: str | None = None,
    status: str = "succeeded",
    evidence_pack: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_action = _required_str(action, "action")
    if resolved_action not in HANDOFF_AUDIT_ACTIONS:
        raise ValueError(f"unsupported handoff audit action: {resolved_action}")

    resolved_mode = _required_str(handoff_mode, "handoff_mode")
    if resolved_mode not in HANDOFF_MODES:
        raise ValueError(f"unsupported handoff_mode: {resolved_mode}")

    pack = dict(evidence_pack or {})
    provenance = pack.get("provenance") if isinstance(pack.get("provenance"), Mapping) else {}
    project_key = str(provenance.get("project_key") or "").strip() or None

    record = _base_audit_record(
        action=resolved_action,
        actor_id=producer,
        graph_id=graph_id,
        object_scope="graph_handoff",
        timestamp=timestamp,
        audit_id=None,
        status=status,
        project_key=project_key,
    )
    record["context"] = {
        "run_id": _required_str(run_id, "run_id"),
        "handoff_id": _required_str(handoff_id, "handoff_id"),
        "handoff_mode": resolved_mode,
        "consumer": _required_str(consumer, "consumer"),
        "evidence_pack_contract_version": str(pack.get("contract_version") or "").strip() or None,
        "evidence_pack_id": str(pack.get("pack_id") or "").strip() or None,
    }
    return record


def _base_audit_record(
    *,
    action: str,
    actor_id: str,
    graph_id: str,
    object_scope: str,
    timestamp: str | None,
    audit_id: str | None,
    status: str,
    project_key: str | None,
) -> dict[str, Any]:
    resolved_status = _required_str(status, "status")
    if resolved_status not in AUDIT_STATUSES:
        raise ValueError(f"unsupported audit status: {resolved_status}")

    resolved_scope = _required_str(object_scope, "object_scope")
    if resolved_scope not in GRAPH_GOVERNANCE_OBJECT_SCOPES:
        raise ValueError(f"unsupported audit object_scope: {resolved_scope}")

    record = {
        "contract_version": AUDIT_CONTRACT_VERSION,
        "audit_id": str(audit_id or "").strip() or f"audit_{uuid4().hex[:12]}",
        "action": _required_str(action, "action"),
        "actor_id": _required_str(actor_id, "actor_id"),
        "graph_id": _required_str(graph_id, "graph_id"),
        "object_scope": resolved_scope,
        "timestamp": timestamp or _utcnow(),
        "status": resolved_status,
    }
    resolved_project_key = str(project_key or "").strip()
    if resolved_project_key:
        record["project_key"] = resolved_project_key
    return record


def _required_str(value: Any, field: str) -> str:
    resolved = str(value or "").strip()
    if not resolved:
        raise ValueError(f"{field} is required")
    return resolved


def _non_negative_int(value: Any, field: str) -> int:
    try:
        resolved = int(value)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{field} must be an integer") from exc
    if resolved < 0:
        raise ValueError(f"{field} must be >= 0")
    return resolved


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
