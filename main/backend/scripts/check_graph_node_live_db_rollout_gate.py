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
        description="Check Graph Node live DB rollout readiness without treating dry-run evidence as closure"
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--database-url", default=str(settings.database_url or ""))
    parser.add_argument("--read-mode", default=str(settings.graph_node_projection_read_mode or "a_only"))
    parser.add_argument("--write-mode", default=str(settings.graph_node_projection_write_mode or "shadow"))
    parser.add_argument("--canary-projects", default=str(settings.graph_node_projection_canary_projects or "demo_proj"))
    parser.add_argument("--backfill-limit", type=int, default=10)
    parser.add_argument("--max-dry-run-limit", type=int, default=1000)
    parser.add_argument("--backfill-apply", action="store_true", help="validate apply-mode readiness; should fail without live evidence")
    parser.add_argument("--migration-root", default=str(DEFAULT_MIGRATION_ROOT))
    parser.add_argument("--live-db-evidence-json", default="")
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
    report = build_graph_node_live_db_rollout_gate(
        no_db_report=no_db_report,
        readiness_report=readiness_report,
        database_url=args.database_url,
        live_db_evidence=_read_json(args.live_db_evidence_json),
    )
    payload = report.to_dict()

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"status={payload['status']}")
        print(f"closure_state={payload['closure_state']}")
        print(f"dry_run_ready={payload['dry_run_ready']}")
        print(f"read_mode_dry_run_safe={payload['read_mode_dry_run_safe']}")
        print(f"backfill_dry_run_ready={payload['backfill_dry_run_ready']}")
        print(f"live_db_validated={payload['live_db_validated']}")
        print(f"live_db_closure_ready={payload['live_db_closure_ready']}")
        print(f"closure_claim={payload['closure_claim']}")
        print(f"read_mode={payload['read_mode']}")
        print(f"write_mode={payload['write_mode']}")
        failed_checks = [check for check in payload["checks"] if not check["passed"]]
        if failed_checks:
            print("failed_checks:")
            for check in failed_checks:
                print(f"- {check['stage']}.{check['name']}: {check['detail']}")
        if payload["remaining_live_db_gaps"]:
            print("remaining_live_db_gaps:")
            for gap in payload["remaining_live_db_gaps"]:
                print(f"- {gap}")

    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
