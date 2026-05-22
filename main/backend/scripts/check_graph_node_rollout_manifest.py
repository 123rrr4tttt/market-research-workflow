#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.graph.persistence.graph_node_live_db_rollout_gate import (  # noqa: E402
    build_graph_node_live_db_rollout_gate,
)
from app.services.graph.persistence.graph_node_rollout_manifest import (  # noqa: E402
    build_graph_node_rollout_manifest,
)
from app.services.graph.persistence.graph_projection_contract import (  # noqa: E402
    build_graph_projection_dry_run,
    build_graph_projection_rollout_readiness,
)
from app.settings.config import settings  # noqa: E402

from check_graph_projection_contract import (  # noqa: E402
    DEFAULT_MIGRATION_ROOT,
    _failure_isolation_checks,
    _fixture_graph,
    _migration_checks,
    _split_projects,
)


DEFAULT_SOURCE_DOCS = [
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-02-graph-node-standardization-a-then-b-plan/02_wave7-status-evidence-and-min-plan-2026-05-22.md",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-02-graph-node-standardization-a-then-b-plan/04_wave10-db-rollout-readiness-contract-2026-05-22.md",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-02-graph-node-standardization-a-then-b-plan/06_wave14-live-db-rollout-gate-2026-05-22.md",
]


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_evidence_read_error": str(exc)}
    return data if isinstance(data, dict) else {"_evidence_read_error": "evidence JSON must be an object"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and read back the deterministic Graph Node rollout manifest"
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--database-url", default=str(settings.database_url or ""))
    parser.add_argument("--read-mode", default=str(settings.graph_node_projection_read_mode or "a_only"))
    parser.add_argument("--write-mode", default=str(settings.graph_node_projection_write_mode or "shadow"))
    parser.add_argument("--canary-projects", default=str(settings.graph_node_projection_canary_projects or "demo_proj"))
    parser.add_argument("--backfill-limit", type=int, default=10)
    parser.add_argument("--max-dry-run-limit", type=int, default=1000)
    parser.add_argument("--backfill-apply", action="store_true", help="validate apply-mode readiness; should fail pre-live")
    parser.add_argument("--migration-root", default=str(DEFAULT_MIGRATION_ROOT))
    parser.add_argument("--live-db-evidence-json", default="")
    parser.add_argument("--source-doc", action="append", default=[], help="extra source document reference")
    args = parser.parse_args()

    no_db_report = build_graph_projection_dry_run(_fixture_graph())
    readiness_report = build_graph_projection_rollout_readiness(
        read_mode=args.read_mode,
        write_mode=args.write_mode,
        canary_projects=_split_projects(args.canary_projects),
        backfill_dry_run=not args.backfill_apply,
        backfill_limit=args.backfill_limit,
        migration_checks=_migration_checks(Path(args.migration_root)),
        failure_isolation_checks=_failure_isolation_checks(),
        max_dry_run_limit=args.max_dry_run_limit,
    )
    gate_report = build_graph_node_live_db_rollout_gate(
        no_db_report=no_db_report,
        readiness_report=readiness_report,
        database_url=args.database_url,
        live_db_evidence=_read_json(args.live_db_evidence_json),
    )
    report = build_graph_node_rollout_manifest(
        no_db_report=no_db_report,
        readiness_report=readiness_report,
        gate_report=gate_report,
        source_docs=[*DEFAULT_SOURCE_DOCS, *args.source_doc],
    )
    payload = report.to_dict()

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"status={payload['status']}")
        print(f"manifest_id={payload['manifest_id']}")
        print(f"manifest_digest={payload['manifest_digest']}")
        print(f"deterministic_readback={payload['deterministic_readback']}")
        print(f"live_db_validated={payload['live_db_validated']}")
        print(f"live_db_closure_ready={payload['live_db_closure_ready']}")
        print(f"closure_claim={payload['closure_claim']}")
        print("stages:")
        for stage in payload["stages"]:
            print(f"- {stage['name']}: {stage['status']}")
        if payload["readback_failures"]:
            print("readback_failures:")
            for failure in payload["readback_failures"]:
                print(f"- {failure}")
        if payload["remaining_live_db_gaps"]:
            print("remaining_live_db_gaps:")
            for gap in payload["remaining_live_db_gaps"]:
                print(f"- {gap}")

    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
