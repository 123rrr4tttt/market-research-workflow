#!/usr/bin/env python3
"""Materialize the frozen functorial-debt workstream registry deterministically."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = ROOT / "docs/governance/functorial-structural-debt-remediation-completion5-classification.v1.json"
OUTPUT = ROOT / "docs/governance/functorial-debt-zero-baseline-packets.v1.json"
EXPECTED_COUNTS = {
    "K0d": 1,
    "W01": 59,
    "W02": 67,
    "W03": 68,
    "W04": 79,
    "W05": 57,
    "W06": 98,
    "W07": 53,
    "W08": 72,
    "W09": 75,
    "W10": 27,
    "W11": 33,
    "W12": 38,
}

PACKET_METADATA = {
    "K0d": ("C7 exact-byte additive failure repair", "C7 movement contract", "root-only additive successor"),
    "W01": ("App surfaces and miscellaneous backend services", "application contracts and projections", "declared app/service owners"),
    "W02": ("Agent services", "agent plans, views, sessions, approvals, and effects", "agent domain stores and ports"),
    "W03": ("Ingest and provider effects", "ingest, collection, crawler, resource, HTTP, and index effects", "ingest/resource/provider ports"),
    "W04": ("Knowledge and workflow services", "typed knowledge, graph, document, search, workflow, and writing objects", "typed stores and workflow ports"),
    "W05": ("Successor agent and collect capabilities", "successor agent/collect programs and outcomes", "capability-owned closed families"),
    "W06": ("Remaining successor capabilities", "successor source, C8/C9, first-specimen, and port capabilities", "capability-owned closed families"),
    "W07": ("Successor semantic core", "language, runtime, research, and ops-domain objects", "semantic-core closed families"),
    "W08": ("Successor materialization and compatibility", "migration, assembly, substrate, and specification representations", "assembly/substrate effect boundaries"),
    "W09": ("Backend CLI check/build reports", "backend checker and builder evidence", "CLI report runtime"),
    "W10": ("Other backend CLI reports", "backend generator, cleanup, and operational evidence", "CLI report runtime"),
    "W11": ("Root CLI check/build reports", "root checker and builder evidence", "CLI report runtime"),
    "W12": ("Other root CLI reports", "root smoke, runtime, and operational evidence", "CLI report runtime"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _packet_id(row: dict[str, Any]) -> str:
    path = row["file"]
    name = Path(path).name
    if row["category"] == "CLI_OR_REPORT":
        if path.startswith("main/backend/scripts/"):
            return "W09" if name.startswith(("check_", "build_")) else "W10"
        if path.startswith("scripts/"):
            return "W11" if name.startswith(("check_", "build_")) else "W12"
    if path == "main/backend/app/successor_runtime/capabilities/ingest_c7_movements.py":
        return "K0d"
    if path.startswith("main/backend/app/successor_runtime/capabilities/"):
        stem = Path(path).stem
        return "W05" if stem.startswith(("agent_", "collect_")) else "W06"
    if path.startswith(
        (
            "main/backend/app/successor_runtime/language/",
            "main/backend/app/successor_runtime/runtime/",
            "main/backend/app/successor_runtime/research/",
            "main/backend/app/successor_runtime/ops_domain/",
        )
    ):
        return "W07"
    if path.startswith(
        (
            "main/backend/app/successor_migration/",
            "main/backend/app/successor_runtime/assembly/",
            "main/backend/app/successor_runtime/substrate/",
            "main/backend/app/successor_runtime/specification/",
        )
    ):
        return "W08"
    if path.startswith(
        (
            "main/backend/app/services/agent_batch/",
            "main/backend/app/services/agent_core/",
            "main/backend/app/services/agent_runtime/",
            "main/backend/app/services/agent_sessions/",
        )
    ) or path in {
        "main/backend/app/services/codex_oauth.py",
        "main/backend/app/services/skill_runtime.py",
    }:
        return "W02"
    if path.startswith(
        (
            "main/backend/app/services/ingest/",
            "main/backend/app/services/collect_runtime/",
            "main/backend/app/services/crawlers/",
            "main/backend/app/services/resource_pool/",
            "main/backend/app/services/http/",
            "main/backend/app/services/indexer/",
        )
    ) or path == "main/backend/app/services/job_logger.py":
        return "W03"
    if path.startswith(
        (
            "main/backend/app/services/typed_knowledge/",
            "main/backend/app/services/graph/",
            "main/backend/app/services/clue_chains/",
            "main/backend/app/services/document_views/",
            "main/backend/app/services/document_queries/",
            "main/backend/app/services/search/",
            "main/backend/app/services/workflow_graph/",
            "main/backend/app/services/writing/",
        )
    ):
        return "W04"
    if path.startswith("main/backend/app/"):
        return "W01"
    raise ValueError(f"unassigned classification row: {row['key']}")


def _packet(packet_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    title, domain_object, failure_owner = PACKET_METADATA[packet_id]
    files = sorted({row["file"] for row in rows})
    key_rows = sorted(rows, key=lambda row: row["key"])
    root_only = packet_id == "K0d"
    return {
        "id": packet_id,
        "title": title,
        "goal": "Resolve every owned key by typed authority/failure semantics without changing observable ABI or authority.",
        "domain_object": domain_object,
        "canonical_representation": "Use the existing domain owner; add only kit authority metadata, closed Failure values, or a proved compatibility boundary.",
        "authority_direction": "canonical owner -> read-only projection or prepared command; writes remain at the named writer/effect boundary",
        "failure_owner": failure_owner,
        "change_class": "extension" if root_only else "refinement",
        "root_only": root_only,
        "owned_files": files,
        "read_only_context_files": [
            "docs/governance/functorial-debt-zero-baseline-task-spec.v1.md",
            "docs/governance/functorial-structural-debt-remediation-completion5-classification.v1.json",
            "functorial-kit.json",
            "registries/failures.json",
            "sketches.json",
        ],
        "allowed_edits": (
            ["additive exact-byte rebind candidates and their dedicated tests"]
            if root_only
            else [*files, f"main/backend/tests/functorial_debt/test_{packet_id.lower()}.py", f"tests/functorial_debt/test_{packet_id.lower()}.py"]
        ),
        "forbidden_edits": [
            "docs/governance/functorial-debt-zero-baseline-task-spec.v1.md",
            "docs/governance/functorial-debt-zero-baseline-progress.v1.md",
            "docs/governance/functorial-debt-zero-baseline.freeze.v1.json",
            "arch-baseline.json",
            "functorial-kit.json",
            "registries/**",
            "sketches.json",
            "scripts/formal_release/**",
            "tests/formal_release/**",
            "frozen predecessor evidence",
        ],
        "key_count": len(key_rows),
        "gate_counts": dict(sorted(Counter(row["gate"] for row in key_rows).items())),
        "category_counts": dict(sorted(Counter(row["category"] for row in key_rows).items())),
        "expected_removed_keys": [row["key"] for row in key_rows],
        "input_rows": key_rows,
        "verification": {
            "worker": "owned focused tests plus exact-key pure scan",
            "integration": "pure architecture scan; new_fail_keys=0; git diff --check",
            "full_gate_boundary": "family or milestone only",
        },
        "rollback_route": "Revert only packet-owned implementation/test changes; workers never mutate the baseline or shared registries.",
        "authority_ceiling": "IMPLEMENTATION_ONLY_NOT_PROMOTION_NOT_PRODUCTION_NOT_LIVE_NOT_CUTOVER",
        "worker_return": ["result", "changed_files", "verification_status", "removed_keys_observed", "remaining_risks"],
    }


def main() -> int:
    source = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))
    rows = source["classification_rows"]
    grouped: dict[str, list[dict[str, Any]]] = {packet_id: [] for packet_id in EXPECTED_COUNTS}
    for row in rows:
        grouped[_packet_id(row)].append(row)
    observed = {packet_id: len(packet_rows) for packet_id, packet_rows in grouped.items()}
    if observed != EXPECTED_COUNTS:
        raise ValueError(f"packet count drift: expected={EXPECTED_COUNTS}, observed={observed}")
    all_keys = [row["key"] for row in rows]
    if len(all_keys) != 727 or len(set(all_keys)) != 727:
        raise ValueError("classification key set must contain exactly 727 unique keys")
    registry = {
        "schema": "mrw.functorial_debt_zero_baseline.packet_registry.v1",
        "status": "FROZEN_WORKSTREAM_PARTITION_NOT_AUTHORITY",
        "source": {
            "path": CLASSIFICATION.relative_to(ROOT).as_posix(),
            "sha256": _sha256(CLASSIFICATION),
            "key_count": len(all_keys),
        },
        "partition": {
            "packet_count": len(grouped),
            "key_count": len(all_keys),
            "unique_key_count": len(set(all_keys)),
            "assigned_once": True,
            "counts": EXPECTED_COUNTS,
        },
        "execution_order": ["K0d is root-only and exact-byte gated", "W01-W08 semantic families", "W09-W12 CLI/report families"],
        "packets": [_packet(packet_id, grouped[packet_id]) for packet_id in EXPECTED_COUNTS],
    }
    OUTPUT.write_text(json.dumps(registry, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
