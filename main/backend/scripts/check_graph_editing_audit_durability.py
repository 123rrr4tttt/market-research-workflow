#!/usr/bin/env python3
"""Gate graph editing audit durability/readback without claiming live closure."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
FRONTEND_ROOT = REPO_ROOT / "main" / "frontend-modern"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.workflow_graph.curated_service import (  # noqa: E402
    WorkflowGraphCuratedService,
    WorkflowGraphSyncConflictError,
)
from app.services.workflow_graph.handoff_store import WorkflowGraphHandoffStore  # noqa: E402
from app.services.workflow_graph.store import InMemoryRunStore  # noqa: E402


CONTRACT_VERSION = "graph.editing_audit_durability_gate.v1"

AUDIT_CONTRACT_VERSION = "workflow_graph.governance_audit.v1"
ROLLBACK_CONTRACT_VERSION = "workflow_graph.rollback.v1"
HANDOFF_CONTRACT_VERSION = "workflow_graph.handoff.v1"
VERSION_SEMANTICS = "curated_graph_revision_separate_from_template_versions"

LIVE_DB_AUDIT_EVIDENCE_FIELDS = (
    "live_db_audit_durability_validated",
    "curated_submit_audit_readback_from_fresh_session",
    "curated_rollback_audit_readback_from_fresh_session",
    "handoff_persist_replay_readback_from_fresh_session",
    "tenant_project_scope_checked",
)

GRAPHPAGE_AUDIT_UI_EVIDENCE_FIELDS = (
    "graphpage_audit_readback_validated",
    "graphpage_rollback_control_validated",
    "graphpage_used_live_backend",
    "audit_records_visible_after_submit_rollback",
    "handoff_replay_visible_or_linked",
)

TENANT_LIKE_PROJECT_KEY = "tenant_like_graph_audit_fixture"
TENANT_LIKE_GRAPH_ID = "cg-wave18-tenant-like-audit"
TENANT_LIKE_ACTOR_ID = "wave18.worker6"

CONFLICT_READBACK_PROJECT_KEY = "tenant_like_graph_audit_conflict_fixture"
CONFLICT_READBACK_GRAPH_ID = "cg-wave20-audit-conflict"
CONFLICT_READBACK_ACTOR_ID = "wave20.worker3"


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_evidence_read_error": str(exc)}
    return data if isinstance(data, dict) else {"_evidence_read_error": "evidence JSON must be an object"}


def _contains_all(source: str, needles: tuple[str, ...]) -> bool:
    return all(needle in source for needle in needles)


def _missing_true_fields(evidence: dict[str, Any] | None, fields: tuple[str, ...]) -> list[str]:
    if not evidence:
        return list(fields)
    return [field for field in fields if evidence.get(field) is not True]


def _failed_check_names(checks: dict[str, bool]) -> list[str]:
    return sorted(name for name, passed in checks.items() if not passed)


def _stage(
    *,
    name: str,
    status: str,
    passed: bool,
    validated: bool,
    detail: str,
    gaps: list[str],
    evidence_required: tuple[str, ...] | list[str] = (),
    failures: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "passed": passed,
        "validated": validated,
        "detail": detail,
        "gaps": gaps,
        "evidence_required": list(evidence_required),
        "failures": failures or [],
        "metrics": metrics or {},
    }


def _expect(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _curated_dsl(target_node: str, *, source_uri: str) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": "node-acme",
                "type": "Company",
                "name": "Acme Robotics",
                "summary": "Acme robotics market signal.",
                "source_uri": source_uri,
            },
            {
                "id": target_node,
                "type": "Market",
                "name": f"{target_node} market",
                "summary": f"{target_node} market evidence.",
            },
        ],
        "edges": [
            {
                "from": "node-acme",
                "to": target_node,
                "predicate": "in_market",
                "evidence": f"Acme participates in {target_node}.",
            }
        ],
    }


def _exercise_curated_audit_readback() -> dict[str, Any]:
    failures: list[str] = []
    metrics: dict[str, Any] = {}
    state_store: dict[str, Any] = {"payload": {"base_version": 0, "graphs": {}}}

    def fake_get_config(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"payload": deepcopy(state_store["payload"])}

    def fake_upsert_config(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        state_store["payload"] = deepcopy(kwargs.get("payload"))
        return {"payload": deepcopy(state_store["payload"])}

    try:
        with patch("app.services.workflow_graph.curated_service.current_project_key", return_value="demo_proj"), patch(
            "app.services.workflow_graph.curated_service.get_ingest_config",
            side_effect=fake_get_config,
        ), patch(
            "app.services.workflow_graph.curated_service.upsert_ingest_config",
            side_effect=fake_upsert_config,
        ):
            writer = WorkflowGraphCuratedService()
            writer.save_draft(
                "cg-audit-durability",
                {"dsl": _curated_dsl("node-robotics", source_uri="https://example.com/robotics")},
            )
            submit_1 = writer.submit_draft(
                "cg-audit-durability",
                {"base_revision": 0, "actor_id": "wave15.worker8", "version_id": "cver-1"},
            )
            writer.save_draft(
                "cg-audit-durability",
                {
                    "base_revision": 1,
                    "dsl": _curated_dsl("node-industrial-ai", source_uri="https://example.com/industrial-ai"),
                },
            )
            submit_2 = writer.submit_draft(
                "cg-audit-durability",
                {"base_revision": 1, "actor_id": "wave15.worker8", "version_id": "cver-2"},
            )
            rollback = writer.rollback(
                "cg-audit-durability",
                {
                    "base_revision": 2,
                    "actor_id": "wave15.worker8",
                    "target_version_id": "cver-1",
                    "reason": "wave15 audit durability fixture",
                },
            )

            reader = WorkflowGraphCuratedService()
            audits = reader.list_audits("cg-audit-durability", limit=10)
            sync_readback = reader.sync_graph("cg-audit-durability", {"since_revision": 2})
    except Exception as exc:  # noqa: BLE001
        return {"failures": [f"curated audit fixture raised: {exc}"], "metrics": metrics}

    items = audits.get("items") if isinstance(audits.get("items"), list) else []
    actions = [str(item.get("action") or "") for item in items]
    audit_ids = [str(item.get("audit_id") or "") for item in items]
    snapshot = sync_readback.get("server_snapshot") if isinstance(sync_readback, dict) else {}
    snapshot_dsl = snapshot.get("dsl") if isinstance(snapshot, dict) else {}
    snapshot_nodes = snapshot_dsl.get("nodes") if isinstance(snapshot_dsl, dict) else []
    snapshot_node_ids = {
        str(node.get("id") or node.get("node_id") or "").strip()
        for node in snapshot_nodes
        if isinstance(node, dict)
    }
    rollback_audit = items[0] if items else {}
    rollback_contract = {}
    if isinstance(rollback_audit.get("context"), dict):
        rollback_contract = rollback_audit["context"].get("rollback_contract") or {}

    persisted_graph = state_store["payload"].get("graphs", {}).get("cg-audit-durability", {})
    persisted_audits = persisted_graph.get("audits") if isinstance(persisted_graph, dict) else []

    _expect(failures, submit_1.get("revision") == 1, "first submit did not create revision 1")
    _expect(failures, submit_2.get("revision") == 2, "second submit did not create revision 2")
    _expect(failures, rollback.get("revision") == 3, "rollback did not create revision 3")
    _expect(failures, actions == ["rollback", "submit", "submit"], f"audit readback actions mismatch: {actions}")
    _expect(failures, len(set(audit_ids)) == 3 and all(audit_ids), "audit ids were not durable and unique")
    _expect(
        failures,
        all(item.get("contract_version") == AUDIT_CONTRACT_VERSION for item in items),
        "audit contract version mismatch",
    )
    _expect(
        failures,
        all(item.get("project_key") == "demo_proj" for item in items),
        "project_key was not preserved in audit readback",
    )
    _expect(
        failures,
        all(item.get("version_semantics") == VERSION_SEMANTICS for item in items),
        "curated graph version semantics missing from audit readback",
    )
    _expect(
        failures,
        rollback.get("rollback_contract", {}).get("contract_version") == ROLLBACK_CONTRACT_VERSION,
        "rollback response contract version mismatch",
    )
    _expect(
        failures,
        rollback_contract.get("target_version_id") == "cver-1"
        and rollback_contract.get("requires_base_revision_match") is True,
        "rollback audit context did not preserve target version/base revision contract",
    )
    _expect(
        failures,
        "node-robotics" in snapshot_node_ids and "node-industrial-ai" not in snapshot_node_ids,
        "rollback readback did not restore the target version snapshot",
    )
    _expect(
        failures,
        isinstance(persisted_audits, list) and len(persisted_audits) == 3,
        "config payload did not persist three audit records",
    )

    metrics.update(
        {
            "curated_audit_count": len(items),
            "curated_audit_actions": actions,
            "rollback_revision": rollback.get("revision"),
            "restored_node_ids": sorted(snapshot_node_ids),
        }
    )
    return {"failures": failures, "metrics": metrics}


def _exercise_tenant_like_fixture_audit_trace() -> dict[str, Any]:
    failures: list[str] = []
    metrics: dict[str, Any] = {}
    state_store: dict[str, Any] = {"payload": {"base_version": 0, "graphs": {}}}
    rollback_reason = "wave18 tenant-like rollback trace fixture"

    def fake_get_config(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"payload": deepcopy(state_store["payload"])}

    def fake_upsert_config(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        state_store["payload"] = deepcopy(kwargs.get("payload"))
        return {"payload": deepcopy(state_store["payload"])}

    try:
        with patch(
            "app.services.workflow_graph.curated_service.current_project_key",
            return_value=TENANT_LIKE_PROJECT_KEY,
        ), patch(
            "app.services.workflow_graph.curated_service.get_ingest_config",
            side_effect=fake_get_config,
        ), patch(
            "app.services.workflow_graph.curated_service.upsert_ingest_config",
            side_effect=fake_upsert_config,
        ):
            writer = WorkflowGraphCuratedService()
            writer.save_draft(
                TENANT_LIKE_GRAPH_ID,
                {
                    "actor_id": TENANT_LIKE_ACTOR_ID,
                    "dsl": _curated_dsl("node-wave18-baseline", source_uri="https://example.com/wave18/baseline"),
                },
            )
            submit_1 = writer.submit_draft(
                TENANT_LIKE_GRAPH_ID,
                {
                    "base_revision": 0,
                    "actor_id": TENANT_LIKE_ACTOR_ID,
                    "version_id": "cver-wave18-baseline",
                },
            )
            writer.save_draft(
                TENANT_LIKE_GRAPH_ID,
                {
                    "base_revision": 1,
                    "actor_id": TENANT_LIKE_ACTOR_ID,
                    "dsl": _curated_dsl(
                        "node-wave18-experimental",
                        source_uri="https://example.com/wave18/experimental",
                    ),
                },
            )
            submit_2 = writer.submit_draft(
                TENANT_LIKE_GRAPH_ID,
                {
                    "base_revision": 1,
                    "actor_id": TENANT_LIKE_ACTOR_ID,
                    "version_id": "cver-wave18-experimental",
                },
            )
            rollback = writer.rollback(
                TENANT_LIKE_GRAPH_ID,
                {
                    "base_revision": 2,
                    "actor_id": TENANT_LIKE_ACTOR_ID,
                    "target_version_id": "cver-wave18-baseline",
                    "reason": rollback_reason,
                },
            )

            reader = WorkflowGraphCuratedService()
            graph = reader.get_graph(TENANT_LIKE_GRAPH_ID)
            audits = reader.list_audits(TENANT_LIKE_GRAPH_ID, limit=10)
            sync_readback = reader.sync_graph(TENANT_LIKE_GRAPH_ID, {"since_revision": 2})
    except Exception as exc:  # noqa: BLE001
        return {"failures": [f"tenant-like audit fixture raised: {exc}"], "metrics": metrics}

    persisted_graph = state_store["payload"].get("graphs", {}).get(TENANT_LIKE_GRAPH_ID, {})
    raw_audits = persisted_graph.get("audits") if isinstance(persisted_graph, dict) else []
    raw_audits = raw_audits if isinstance(raw_audits, list) else []
    items = audits.get("items") if isinstance(audits.get("items"), list) else []
    raw_actions = [str(item.get("action") or "") for item in raw_audits if isinstance(item, dict)]
    readback_actions = [str(item.get("action") or "") for item in items]
    raw_audit_ids = [str(item.get("audit_id") or "") for item in raw_audits if isinstance(item, dict)]
    readback_audit_ids = [str(item.get("audit_id") or "") for item in items]

    rollback_audit = items[0] if items else {}
    rollback_context = rollback_audit.get("context") if isinstance(rollback_audit.get("context"), dict) else {}
    rollback_contract = rollback_context.get("rollback_contract") if isinstance(rollback_context, dict) else {}
    rollback_contract = rollback_contract if isinstance(rollback_contract, dict) else {}

    snapshot = sync_readback.get("server_snapshot") if isinstance(sync_readback, dict) else {}
    snapshot_dsl = snapshot.get("dsl") if isinstance(snapshot, dict) else {}
    snapshot_nodes = snapshot_dsl.get("nodes") if isinstance(snapshot_dsl, dict) else []
    snapshot_node_ids = {
        str(node.get("id") or node.get("node_id") or "").strip()
        for node in snapshot_nodes
        if isinstance(node, dict)
    }

    current = persisted_graph.get("current") if isinstance(persisted_graph, dict) else {}
    current = current if isinstance(current, dict) else {}

    _expect(failures, submit_1.get("revision") == 1, "tenant-like first submit did not create revision 1")
    _expect(failures, submit_2.get("revision") == 2, "tenant-like second submit did not create revision 2")
    _expect(failures, rollback.get("revision") == 3, "tenant-like rollback did not create revision 3")
    _expect(failures, graph.get("revision") == 3, "fresh graph readback did not expose rollback revision 3")
    _expect(failures, audits.get("total") == 3, "tenant-like audit list did not report three events")
    _expect(failures, raw_actions == ["submit", "submit", "rollback"], f"raw audit write order mismatch: {raw_actions}")
    _expect(
        failures,
        readback_actions == ["rollback", "submit", "submit"],
        f"audit readback order mismatch: {readback_actions}",
    )
    _expect(
        failures,
        readback_audit_ids == list(reversed(raw_audit_ids)) and all(readback_audit_ids),
        "audit readback ids do not match persisted audit trace",
    )
    _expect(
        failures,
        all(item.get("project_key") == TENANT_LIKE_PROJECT_KEY for item in items),
        "tenant-like project_key was not preserved in audit readback",
    )
    _expect(
        failures,
        all(item.get("graph_id") == TENANT_LIKE_GRAPH_ID for item in items),
        "tenant-like graph_id was not preserved in audit readback",
    )
    _expect(
        failures,
        all(item.get("actor_id") == TENANT_LIKE_ACTOR_ID for item in items),
        "tenant-like actor_id was not preserved in audit readback",
    )
    _expect(
        failures,
        all(item.get("contract_version") == AUDIT_CONTRACT_VERSION for item in items),
        "tenant-like audit contract version mismatch",
    )
    _expect(
        failures,
        rollback_audit.get("rollback_from_version_id") == "cver-wave18-baseline",
        "rollback audit did not preserve target version id",
    )
    _expect(
        failures,
        rollback_contract.get("contract_version") == ROLLBACK_CONTRACT_VERSION
        and rollback_contract.get("project_key") == TENANT_LIKE_PROJECT_KEY
        and rollback_contract.get("actor_id") == TENANT_LIKE_ACTOR_ID
        and rollback_contract.get("target_version_id") == "cver-wave18-baseline"
        and rollback_contract.get("current_revision") == 2
        and rollback_contract.get("base_revision") == 2
        and rollback_contract.get("requires_base_revision_match") is True
        and rollback_contract.get("reason") == rollback_reason,
        "rollback trace contract did not preserve tenant-like target/project/revision/reason metadata",
    )
    _expect(
        failures,
        current.get("audit_id") == rollback_audit.get("audit_id")
        and current.get("rollback_from_version_id") == "cver-wave18-baseline",
        "persisted current snapshot does not point back to rollback audit trace",
    )
    _expect(
        failures,
        "node-wave18-baseline" in snapshot_node_ids and "node-wave18-experimental" not in snapshot_node_ids,
        "tenant-like rollback readback did not restore the target version snapshot",
    )

    metrics.update(
        {
            "tenant_like_project_key": TENANT_LIKE_PROJECT_KEY,
            "tenant_like_graph_id": TENANT_LIKE_GRAPH_ID,
            "tenant_like_audit_count": len(items),
            "tenant_like_raw_audit_actions": raw_actions,
            "tenant_like_readback_audit_actions": readback_actions,
            "tenant_like_rollback_revision": rollback.get("revision"),
            "tenant_like_restored_node_ids": sorted(snapshot_node_ids),
            "live_tenant_db_audit_open": True,
        }
    )
    return {"failures": failures, "metrics": metrics}


def _exercise_conflict_rollback_readback_fixture() -> dict[str, Any]:
    failures: list[str] = []
    metrics: dict[str, Any] = {}
    state_store: dict[str, Any] = {"payload": {"base_version": 0, "graphs": {}}}
    rollback_reason = "wave20 rollback intent after stale conflict marker"
    conflict_details: dict[str, Any] = {}
    conflict_error_message = ""
    audit_count_after_conflict = -1

    def fake_get_config(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"payload": deepcopy(state_store["payload"])}

    def fake_upsert_config(*_args: Any, **kwargs: Any) -> dict[str, Any]:
        state_store["payload"] = deepcopy(kwargs.get("payload"))
        return {"payload": deepcopy(state_store["payload"])}

    try:
        with patch(
            "app.services.workflow_graph.curated_service.current_project_key",
            return_value=CONFLICT_READBACK_PROJECT_KEY,
        ), patch(
            "app.services.workflow_graph.curated_service.get_ingest_config",
            side_effect=fake_get_config,
        ), patch(
            "app.services.workflow_graph.curated_service.upsert_ingest_config",
            side_effect=fake_upsert_config,
        ):
            writer = WorkflowGraphCuratedService()
            writer.save_draft(
                CONFLICT_READBACK_GRAPH_ID,
                {
                    "actor_id": CONFLICT_READBACK_ACTOR_ID,
                    "dsl": _curated_dsl("node-wave20-baseline", source_uri="https://example.com/wave20/baseline"),
                },
            )
            submit_1 = writer.submit_draft(
                CONFLICT_READBACK_GRAPH_ID,
                {
                    "base_revision": 0,
                    "actor_id": CONFLICT_READBACK_ACTOR_ID,
                    "version_id": "cver-wave20-baseline",
                },
            )
            writer.save_draft(
                CONFLICT_READBACK_GRAPH_ID,
                {
                    "base_revision": 1,
                    "actor_id": CONFLICT_READBACK_ACTOR_ID,
                    "dsl": _curated_dsl(
                        "node-wave20-candidate",
                        source_uri="https://example.com/wave20/candidate",
                    ),
                },
            )
            submit_2 = writer.submit_draft(
                CONFLICT_READBACK_GRAPH_ID,
                {
                    "base_revision": 1,
                    "actor_id": CONFLICT_READBACK_ACTOR_ID,
                    "version_id": "cver-wave20-candidate",
                },
            )

            try:
                writer.rollback(
                    CONFLICT_READBACK_GRAPH_ID,
                    {
                        "base_revision": 1,
                        "actor_id": CONFLICT_READBACK_ACTOR_ID,
                        "target_version_id": "cver-wave20-baseline",
                        "reason": rollback_reason,
                    },
                )
            except WorkflowGraphSyncConflictError as exc:
                conflict_details = exc.to_details()
                conflict_error_message = str(exc)
            else:
                failures.append("stale rollback base_revision did not raise WorkflowGraphSyncConflictError")

            persisted_after_conflict = state_store["payload"].get("graphs", {}).get(CONFLICT_READBACK_GRAPH_ID, {})
            raw_after_conflict = (
                persisted_after_conflict.get("audits") if isinstance(persisted_after_conflict, dict) else []
            )
            audit_count_after_conflict = len(raw_after_conflict) if isinstance(raw_after_conflict, list) else -1

            rollback = writer.rollback(
                CONFLICT_READBACK_GRAPH_ID,
                {
                    "base_revision": 2,
                    "actor_id": CONFLICT_READBACK_ACTOR_ID,
                    "target_version_id": "cver-wave20-baseline",
                    "reason": rollback_reason,
                },
            )

            reader = WorkflowGraphCuratedService()
            graph = reader.get_graph(CONFLICT_READBACK_GRAPH_ID)
            audits = reader.list_audits(CONFLICT_READBACK_GRAPH_ID, limit=10)
            sync_readback = reader.sync_graph(CONFLICT_READBACK_GRAPH_ID, {"since_revision": 2})
    except Exception as exc:  # noqa: BLE001
        return {"failures": [*failures, f"conflict rollback readback fixture raised: {exc}"], "metrics": metrics}

    persisted_graph = state_store["payload"].get("graphs", {}).get(CONFLICT_READBACK_GRAPH_ID, {})
    raw_audits = persisted_graph.get("audits") if isinstance(persisted_graph, dict) else []
    raw_audits = raw_audits if isinstance(raw_audits, list) else []
    items = audits.get("items") if isinstance(audits.get("items"), list) else []
    raw_actions = [str(item.get("action") or "") for item in raw_audits if isinstance(item, dict)]
    readback_actions = [str(item.get("action") or "") for item in items]
    rollback_audit = items[0] if items else {}
    rollback_context = rollback_audit.get("context") if isinstance(rollback_audit.get("context"), dict) else {}
    rollback_contract = rollback_context.get("rollback_contract") if isinstance(rollback_context, dict) else {}
    rollback_contract = rollback_contract if isinstance(rollback_contract, dict) else {}

    snapshot = sync_readback.get("server_snapshot") if isinstance(sync_readback, dict) else {}
    snapshot_dsl = snapshot.get("dsl") if isinstance(snapshot, dict) else {}
    snapshot_nodes = snapshot_dsl.get("nodes") if isinstance(snapshot_dsl, dict) else []
    snapshot_node_ids = {
        str(node.get("id") or node.get("node_id") or "").strip()
        for node in snapshot_nodes
        if isinstance(node, dict)
    }
    current = persisted_graph.get("current") if isinstance(persisted_graph, dict) else {}
    current = current if isinstance(current, dict) else {}

    _expect(failures, submit_1.get("revision") == 1, "conflict fixture first submit did not create revision 1")
    _expect(failures, submit_2.get("revision") == 2, "conflict fixture second submit did not create revision 2")
    _expect(
        failures,
        conflict_details == {"category": "version_conflict", "expected_revision": 1, "actual_revision": 2},
        f"conflict marker mismatch: {conflict_details}",
    )
    _expect(
        failures,
        "revision mismatch expected=1 actual=2" in conflict_error_message,
        "conflict error message did not preserve expected/actual revisions",
    )
    _expect(
        failures,
        audit_count_after_conflict == 2,
        "stale conflict should not append an audit event before accepted rollback",
    )
    _expect(failures, rollback.get("revision") == 3, "accepted rollback did not create revision 3")
    _expect(failures, graph.get("revision") == 3, "fresh graph readback did not expose rollback revision 3")
    _expect(failures, raw_actions == ["submit", "submit", "rollback"], f"raw audit actions mismatch: {raw_actions}")
    _expect(
        failures,
        readback_actions == ["rollback", "submit", "submit"],
        f"readback audit actions mismatch: {readback_actions}",
    )
    _expect(
        failures,
        rollback_audit.get("contract_version") == AUDIT_CONTRACT_VERSION
        and rollback_audit.get("action") == "rollback"
        and rollback_audit.get("status") == "succeeded"
        and rollback_audit.get("project_key") == CONFLICT_READBACK_PROJECT_KEY
        and rollback_audit.get("actor_id") == CONFLICT_READBACK_ACTOR_ID,
        "rollback audit event did not preserve audit/project/actor status metadata",
    )
    _expect(
        failures,
        rollback_contract.get("contract_version") == ROLLBACK_CONTRACT_VERSION
        and rollback_contract.get("rollback_scope") == "snapshot_restore"
        and rollback_contract.get("target_version_id") == "cver-wave20-baseline"
        and rollback_contract.get("current_revision") == 2
        and rollback_contract.get("base_revision") == 2
        and rollback_contract.get("requires_base_revision_match") is True
        and rollback_contract.get("reason") == rollback_reason,
        "rollback intent did not preserve scope/target/revision/reason metadata",
    )
    _expect(
        failures,
        current.get("audit_id") == rollback_audit.get("audit_id")
        and current.get("rollback_from_version_id") == "cver-wave20-baseline",
        "readback current snapshot does not point to the rollback audit event",
    )
    _expect(
        failures,
        "node-wave20-baseline" in snapshot_node_ids and "node-wave20-candidate" not in snapshot_node_ids,
        "rollback readback summary did not restore baseline and remove candidate node",
    )

    rollback_intent = {
        "target_version_id": rollback_contract.get("target_version_id"),
        "reason": rollback_contract.get("reason"),
        "rollback_scope": rollback_contract.get("rollback_scope"),
        "requires_base_revision_match": rollback_contract.get("requires_base_revision_match"),
        "base_revision": rollback_contract.get("base_revision"),
    }
    readback_summary = {
        "graph_revision": graph.get("revision"),
        "audit_actions": readback_actions,
        "active_version_id": graph.get("active_version_id"),
        "restored_node_ids": sorted(snapshot_node_ids),
        "current_audit_id": current.get("audit_id"),
    }
    metrics.update(
        {
            "conflict_readback_project_key": CONFLICT_READBACK_PROJECT_KEY,
            "conflict_readback_graph_id": CONFLICT_READBACK_GRAPH_ID,
            "audit_event_validated": not failures,
            "conflict_marker": conflict_details,
            "conflict_did_not_append_audit_event": audit_count_after_conflict == 2,
            "rollback_intent": rollback_intent,
            "readback_summary": readback_summary,
            "raw_audit_actions": raw_actions,
            "readback_audit_actions": readback_actions,
            "live_tenant_db_audit_open": True,
        }
    )
    return {"failures": failures, "metrics": metrics}


def _exercise_handoff_audit_readback() -> dict[str, Any]:
    failures: list[str] = []
    metrics: dict[str, Any] = {}
    run_store = InMemoryRunStore()
    payload = {
        "run_id": "run-audit-durability",
        "contract_version": "graph_handoff.v1",
        "handoff_id": "handoff-audit-durability",
        "handoff_mode": "pull_prepared_evidence",
        "producer": "workflow_graph.backend_bridge",
        "consumer": "llm_report.generate",
        "evidence_pack": {
            "contract_version": "graph_evidence_pack.v1",
            "pack_id": "gep-audit-durability",
            "provenance": {"project_key": "demo_proj", "audit_id": "audit-from-curated"},
        },
    }

    try:
        writer = WorkflowGraphHandoffStore(store=run_store)
        persisted = writer.persist(graph_id="cg-audit-durability", payload=payload)
        reader = WorkflowGraphHandoffStore(store=run_store)
        listed = reader.list_handoffs(run_id="run-audit-durability")
        replayed = reader.replay_handoff(run_id="run-audit-durability", handoff_id="handoff-audit-durability")
        events = run_store.get_events("run-audit-durability")
    except Exception as exc:  # noqa: BLE001
        return {"failures": [f"handoff audit fixture raised: {exc}"], "metrics": metrics}

    event_types = [str(event.get("type") or "") for event in events]
    persisted_event = events[0] if events else {}
    replay_event = events[-1] if events else {}
    persisted_audit = {}
    replay_audit = {}
    if isinstance(persisted_event.get("payload"), dict):
        persisted_audit = persisted_event["payload"].get("audit") or {}
    if isinstance(replay_event.get("payload"), dict):
        replay_audit = replay_event["payload"].get("audit") or {}

    _expect(failures, persisted.get("audit_contract_version") == AUDIT_CONTRACT_VERSION, "persist audit contract missing")
    _expect(failures, listed.get("total") == 1, "handoff list readback did not return one persisted handoff")
    _expect(
        failures,
        replayed.get("contract_version") == HANDOFF_CONTRACT_VERSION
        and replayed.get("handoff_id") == "handoff-audit-durability",
        "handoff replay readback contract mismatch",
    )
    _expect(
        failures,
        event_types == ["handoff.persisted", "handoff.replayed"],
        f"handoff event sequence mismatch: {event_types}",
    )
    _expect(
        failures,
        persisted_audit.get("contract_version") == AUDIT_CONTRACT_VERSION
        and persisted_audit.get("action") == "handoff.persisted"
        and persisted_audit.get("project_key") == "demo_proj",
        "persisted handoff audit record did not preserve governance metadata",
    )
    _expect(
        failures,
        replay_audit.get("contract_version") == AUDIT_CONTRACT_VERSION
        and replay_audit.get("action") == "handoff.replayed"
        and replay_audit.get("context", {}).get("handoff_id") == "handoff-audit-durability",
        "replayed handoff audit record did not preserve replay metadata",
    )

    metrics.update(
        {
            "handoff_event_count": len(events),
            "handoff_event_types": event_types,
            "persisted_audit_id": persisted.get("audit_id"),
        }
    )
    return {"failures": failures, "metrics": metrics}


def repo_local_static_checks(repo_root: Path = REPO_ROOT) -> dict[str, bool]:
    governance_source = _read_file(repo_root / "main" / "backend" / "app" / "services" / "workflow_graph" / "governance_contract.py")
    curated_source = _read_file(repo_root / "main" / "backend" / "app" / "services" / "workflow_graph" / "curated_service.py")
    handoff_source = _read_file(repo_root / "main" / "backend" / "app" / "services" / "workflow_graph" / "handoff_store.py")
    api_source = _read_file(repo_root / "main" / "backend" / "app" / "api" / "workflow_graph.py")
    return {
        "governance_audit_and_rollback_builders_exist": _contains_all(
            governance_source,
            (
                'AUDIT_CONTRACT_VERSION = "workflow_graph.governance_audit.v1"',
                'ROLLBACK_CONTRACT_VERSION = "workflow_graph.rollback.v1"',
                "def build_graph_edit_audit_record",
                "def build_graph_rollback_contract",
                "def build_handoff_audit_record",
                "VERSION_SEMANTICS",
            ),
        ),
        "curated_submit_rollback_persist_audits": _contains_all(
            curated_source,
            (
                "build_graph_edit_audit_record(",
                "build_graph_rollback_contract(",
                'graph["audits"].append(audit_record)',
                "def list_audits",
                "audits.reverse()",
            ),
        ),
        "workflow_graph_api_exposes_audit_rollback_and_replay_readback": _contains_all(
            api_source,
            (
                '"/curated/{graph_id}/rollback"',
                '"/curated/{graph_id}/audit"',
                '"/runs/{run_id}/handoff/{handoff_id}/replay"',
                "def list_workflow_graph_curated_audits",
                "def replay_workflow_graph_handoff",
            ),
        ),
        "handoff_store_persists_and_replays_audited_events": _contains_all(
            handoff_source,
            (
                'event_type="handoff.persisted"',
                'event_type="handoff.replayed"',
                '"audit": build_handoff_audit_record(',
                "def list_handoffs",
                "def replay_handoff",
            ),
        ),
    }


def graphpage_audit_ui_static_checks(repo_root: Path = REPO_ROOT) -> dict[str, bool]:
    graph_api_source = _read_file(repo_root / "main" / "frontend-modern" / "src" / "lib" / "api" / "domains" / "graph-workflow.ts")
    endpoints_source = _read_file(repo_root / "main" / "frontend-modern" / "src" / "lib" / "api" / "endpoints.ts")
    graph_page_source = _read_file(repo_root / "main" / "frontend-modern" / "src" / "pages" / "GraphPage.tsx")
    e2e_source = _read_file(repo_root / "main" / "frontend-modern" / "tests" / "e2e" / "graphpage.spec.ts")
    combined_frontend_source = "\n".join((graph_api_source, endpoints_source, graph_page_source, e2e_source))
    return {
        "graphpage_curated_submit_and_reporting_bridge_exists": _contains_all(
            graph_page_source,
            (
                "handleSubmitCuratedGraph",
                "handleBuildCuratedReportingHandoff",
                'data-testid="graph-curated-submit"',
                'data-testid="graph-curated-reporting-handoff"',
            ),
        ),
        "frontend_curated_audit_readback_api_wrapper_exists": _contains_all(
            graph_api_source,
            (
                "listWorkflowGraphCuratedAudits",
                "curatedAudit",
            ),
        ),
        "frontend_curated_rollback_api_wrapper_exists": _contains_all(
            graph_api_source,
            (
                "rollbackWorkflowGraphCuratedState",
                "curatedRollback",
            ),
        ),
        "graphpage_audit_readback_control_exists": _contains_all(
            graph_page_source,
            (
                "handleListCuratedAudits",
                'data-testid="graph-curated-audit"',
            ),
        ),
        "graphpage_rollback_control_exists": _contains_all(
            graph_page_source,
            (
                "handleRollbackCuratedGraph",
                'data-testid="graph-curated-rollback"',
            ),
        ),
        "frontend_handoff_replay_surface_exists": _contains_all(
            combined_frontend_source,
            (
                "replayWorkflowGraphHandoff",
                "handoffReplay",
                "/handoff/",
            ),
        ),
        "graphpage_e2e_covers_audit_rollback_and_handoff_replay": _contains_all(
            e2e_source,
            (
                "graph builder submits local draft to curated workflow graph API",
                "audit_readback items=1",
                "rollback_succeeded r2 audits=2",
                "handoff_replay_ready events=2",
                "expect(hits.curatedAuditHit).toBe(2)",
                "expect(hits.curatedRollbackHit).toBe(1)",
                "expect(hits.handoffReplayHit).toBe(1)",
            ),
        ),
    }


def _build_repo_local_stage(*, static_checks: dict[str, bool]) -> dict[str, Any]:
    static_failures = _failed_check_names(static_checks)
    curated = _exercise_curated_audit_readback()
    handoff = _exercise_handoff_audit_readback()
    failures = [*static_failures, *curated["failures"], *handoff["failures"]]
    metrics = {
        "static_checks": static_checks,
        **curated["metrics"],
        **handoff["metrics"],
    }
    return _stage(
        name="repo_local_audit_readback_contract",
        status="validated" if not failures else "failed",
        passed=not failures,
        validated=not failures,
        detail=(
            "deterministic service fixture validates curated submit, rollback, audit list, "
            "handoff persist/list/replay, and fresh service readback without opening live DB"
        ),
        gaps=[] if not failures else ["repo-local audit/readback contract is broken"],
        failures=failures,
        metrics=metrics,
    )


def _build_tenant_like_fixture_stage() -> dict[str, Any]:
    fixture = _exercise_tenant_like_fixture_audit_trace()
    failures = list(fixture["failures"])
    return _stage(
        name="tenant_like_fixture_audit_trace",
        status="validated" if not failures else "failed",
        passed=not failures,
        validated=not failures,
        detail=(
            "tenant-like in-memory fixture validates audit event write/readback order, "
            "project-scoped metadata, and rollback trace integrity while leaving live tenant DB open"
        ),
        gaps=[] if not failures else ["tenant-like fixture audit/readback/rollback trace is broken"],
        failures=failures,
        metrics=fixture["metrics"],
    )


def _build_conflict_rollback_readback_stage() -> dict[str, Any]:
    fixture = _exercise_conflict_rollback_readback_fixture()
    failures = list(fixture["failures"])
    return _stage(
        name="conflict_rollback_readback_fixture",
        status="validated" if not failures else "failed",
        passed=not failures,
        validated=not failures,
        detail=(
            "deterministic fixture validates stale revision conflict marker, no audit append on rejected "
            "rollback, accepted rollback intent, rollback audit event, and fresh readback summary"
        ),
        gaps=[] if not failures else ["conflict marker / rollback intent / readback summary fixture is broken"],
        failures=failures,
        metrics=fixture["metrics"],
    )


def _build_graphpage_ui_stage(
    *,
    static_checks: dict[str, bool],
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    required_control_checks = {
        key: value
        for key, value in static_checks.items()
        if key != "graphpage_curated_submit_and_reporting_bridge_exists"
    }
    missing_static = _failed_check_names(required_control_checks)
    if evidence:
        missing_evidence = _missing_true_fields(evidence, GRAPHPAGE_AUDIT_UI_EVIDENCE_FIELDS)
        read_error = str(evidence.get("_evidence_read_error") or "").strip()
        failures = [
            *(f"missing_static:{name}" for name in missing_static),
            *(f"missing_true:{field}" for field in missing_evidence),
        ]
        if read_error:
            failures.append(f"evidence_read_error:{read_error}")
        if not failures:
            return _stage(
                name="graphpage_audit_rollback_readback_ui",
                status="validated",
                passed=True,
                validated=True,
                detail="GraphPage live evidence shows audit readback, rollback control, and handoff replay visibility",
                gaps=[],
                evidence_required=GRAPHPAGE_AUDIT_UI_EVIDENCE_FIELDS,
                metrics={"static_checks": static_checks},
            )
        return _stage(
            name="graphpage_audit_rollback_readback_ui",
            status="failed_evidence",
            passed=False,
            validated=False,
            detail="GraphPage audit/rollback evidence was supplied but static controls or required evidence fields are missing",
            gaps=[
                "GraphPage audit/rollback readback evidence is incomplete",
                "do not treat backend route or mocked API evidence as UI audit durability closure",
            ],
            evidence_required=GRAPHPAGE_AUDIT_UI_EVIDENCE_FIELDS,
            failures=failures,
            metrics={"static_checks": static_checks},
        )

    if missing_static:
        return _stage(
            name="graphpage_audit_rollback_readback_ui",
            status="not_exposed",
            passed=True,
            validated=False,
            detail=f"GraphPage submit/reporting bridge exists, but audit/rollback readback controls are missing: {', '.join(missing_static)}",
            gaps=[
                "GraphPage still needs audit readback controls",
                "GraphPage still needs rollback controls wired to the curated graph rollback endpoint",
                "handoff replay visibility is not exposed as a product UI proof",
            ],
            evidence_required=GRAPHPAGE_AUDIT_UI_EVIDENCE_FIELDS,
            metrics={"static_checks": static_checks},
        )

    return _stage(
        name="graphpage_audit_rollback_readback_ui",
        status="validated",
        passed=True,
        validated=True,
        detail=(
            "repo-local GraphPage controls and e2e coverage prove audit readback, rollback control, "
            "and handoff replay visibility without claiming live tenant DB durability"
        ),
        gaps=[],
        evidence_required=GRAPHPAGE_AUDIT_UI_EVIDENCE_FIELDS,
        metrics={"static_checks": static_checks},
    )


def _build_live_db_audit_stage(
    *,
    database_url: str | None,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    if evidence:
        missing = _missing_true_fields(evidence, LIVE_DB_AUDIT_EVIDENCE_FIELDS)
        read_error = str(evidence.get("_evidence_read_error") or "").strip()
        failures = [*(f"missing_true:{field}" for field in missing)]
        if read_error:
            failures.append(f"evidence_read_error:{read_error}")
        if not failures:
            return _stage(
                name="live_db_audit_durability",
                status="validated",
                passed=True,
                validated=True,
                detail="live tenant evidence proves submit, rollback, and handoff audit readback from persistent storage",
                gaps=[],
                evidence_required=LIVE_DB_AUDIT_EVIDENCE_FIELDS,
            )
        return _stage(
            name="live_db_audit_durability",
            status="failed_evidence",
            passed=False,
            validated=False,
            detail="live DB audit durability evidence was supplied but required fields are missing",
            gaps=[
                "live tenant audit durability evidence is incomplete",
                "do not claim production audit durability from repo-local config/run-store fixtures",
            ],
            evidence_required=LIVE_DB_AUDIT_EVIDENCE_FIELDS,
            failures=failures,
        )

    configured = bool(str(database_url or "").strip())
    return _stage(
        name="live_db_audit_durability",
        status="configured_not_run" if configured else "not_run",
        passed=True,
        validated=False,
        detail=(
            "database URL is configured, but this gate did not open a tenant DB session"
            if configured
            else "no live DB evidence was supplied; this gate only ran repo-local deterministic readback"
        ),
        gaps=[
            "run curated submit and rollback against a tenant DB and read audits back from a fresh session",
            "run handoff persist/list/replay against persistent storage and read replay audit events back",
            "verify project/tenant scoping for audit records",
        ],
        evidence_required=LIVE_DB_AUDIT_EVIDENCE_FIELDS,
    )


def build_gate_snapshot(
    *,
    repo_root: Path = REPO_ROOT,
    database_url: str | None = "",
    graphpage_ui_evidence: dict[str, Any] | None = None,
    live_db_audit_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo_stage = _build_repo_local_stage(static_checks=repo_local_static_checks(repo_root))
    tenant_like_stage = _build_tenant_like_fixture_stage()
    conflict_stage = _build_conflict_rollback_readback_stage()
    ui_stage = _build_graphpage_ui_stage(
        static_checks=graphpage_audit_ui_static_checks(repo_root),
        evidence=graphpage_ui_evidence,
    )
    live_db_stage = _build_live_db_audit_stage(
        database_url=database_url,
        evidence=live_db_audit_evidence,
    )
    stages = [repo_stage, tenant_like_stage, conflict_stage, ui_stage, live_db_stage]
    hard_failures = [failure for stage in stages if not stage["passed"] for failure in stage["failures"]]
    if not repo_stage["validated"] or not tenant_like_stage["validated"] or not conflict_stage["validated"]:
        readiness_state = "failed"
    elif ui_stage["validated"] and live_db_stage["validated"]:
        readiness_state = "live_audit_evidence_recorded_non_closing"
    else:
        readiness_state = "repo_local_validated_live_gaps_open"
    boundary = (
        "repo-local audit/readback contract is deterministic and validated; "
        f"tenant-like fixture audit trace={tenant_like_stage['status']}; "
        f"conflict rollback readback fixture={conflict_stage['status']}; "
        f"GraphPage repo-local audit/rollback UI={ui_stage['status']}; "
        f"live DB audit durability={live_db_stage['status']}; "
        "live_tenant_db_audit_open=true; "
        "closure_claim=false because live tenant audit durability must be sealed by separate live evidence"
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if not hard_failures else "failed",
        "readiness_state": readiness_state,
        "closure_claim": False,
        "repo_local_audit_readback_validated": repo_stage["validated"],
        "tenant_like_fixture_audit_trace_validated": tenant_like_stage["validated"],
        "conflict_rollback_readback_validated": conflict_stage["validated"],
        "graphpage_audit_controls_validated": ui_stage["validated"],
        "live_db_audit_durability_validated": live_db_stage["validated"],
        "live_tenant_db_audit_open": True,
        "boundary": boundary,
        "stages": stages,
        "remaining_gaps": [gap for stage in stages if not stage["validated"] for gap in stage["gaps"]],
        "hard_failures": hard_failures,
    }


def validate_gate_snapshot(snapshot: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if snapshot.get("contract_version") != CONTRACT_VERSION:
        failures.append("unexpected contract_version")
    if snapshot.get("closure_claim") is not False:
        failures.append("closure_claim must remain false")
    if snapshot.get("repo_local_audit_readback_validated") is not True:
        failures.append("repo-local audit/readback contract must be validated")
    if snapshot.get("tenant_like_fixture_audit_trace_validated") is not True:
        failures.append("tenant-like fixture audit trace must be validated")
    if snapshot.get("conflict_rollback_readback_validated") is not True:
        failures.append("conflict rollback readback fixture must be validated")
    if snapshot.get("live_tenant_db_audit_open") is not True:
        failures.append("live_tenant_db_audit_open must remain true")
    if (
        snapshot.get("graphpage_audit_controls_validated") is not True
        or snapshot.get("live_db_audit_durability_validated") is not True
    ) and snapshot.get("readiness_state") != "repo_local_validated_live_gaps_open":
        failures.append("unvalidated UI/live DB audit durability must keep readiness_state open")
    boundary = str(snapshot.get("boundary") or "")
    if (
        "repo-local audit/readback contract" not in boundary
        or "tenant-like fixture audit trace" not in boundary
        or "conflict rollback readback fixture" not in boundary
        or "live_tenant_db_audit_open=true" not in boundary
        or "closure_claim=false" not in boundary
    ):
        failures.append("boundary must distinguish repo-local audit/readback from live closure")
    for failure in snapshot.get("hard_failures") or []:
        failures.append(str(failure))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check graph editing audit durability/readback boundaries without live closure claims"
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--graphpage-ui-evidence-json", default="")
    parser.add_argument("--live-db-audit-evidence-json", default="")
    args = parser.parse_args()

    snapshot = build_gate_snapshot(
        database_url=args.database_url,
        graphpage_ui_evidence=_read_json(args.graphpage_ui_evidence_json),
        live_db_audit_evidence=_read_json(args.live_db_audit_evidence_json),
    )
    validation_failures = validate_gate_snapshot(snapshot)
    if validation_failures:
        snapshot = {**snapshot, "status": "failed", "validation_failures": validation_failures}

    if args.format == "json":
        print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
    else:
        print(f"status={snapshot['status']}")
        print(f"readiness_state={snapshot['readiness_state']}")
        print(f"closure_claim={snapshot['closure_claim']}")
        print(f"repo_local_audit_readback_validated={snapshot['repo_local_audit_readback_validated']}")
        print(f"tenant_like_fixture_audit_trace_validated={snapshot['tenant_like_fixture_audit_trace_validated']}")
        print(f"conflict_rollback_readback_validated={snapshot['conflict_rollback_readback_validated']}")
        print(f"graphpage_audit_controls_validated={snapshot['graphpage_audit_controls_validated']}")
        print(f"live_db_audit_durability_validated={snapshot['live_db_audit_durability_validated']}")
        print(f"live_tenant_db_audit_open={snapshot['live_tenant_db_audit_open']}")
        print(snapshot["boundary"])
        for stage in snapshot["stages"]:
            print(f"{stage['name']}={stage['status']} passed={stage['passed']} validated={stage['validated']}")
        if snapshot["remaining_gaps"]:
            print("remaining_gaps:")
            for gap in snapshot["remaining_gaps"]:
                print(f"- {gap}")
        if validation_failures:
            print("validation_failures:")
            for failure in validation_failures:
                print(f"- {failure}")

    return 0 if snapshot["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
