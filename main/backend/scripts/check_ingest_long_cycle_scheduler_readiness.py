#!/usr/bin/env python3
"""Wave13 gate for ingest long-cycle scheduler readiness without live closure."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.ingest.digestion_scaffold import check_long_cycle_scheduler_readiness_contract


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_evidence_read_error": str(exc)}
    return payload if isinstance(payload, dict) else {"_evidence_read_error": "evidence JSON must be an object"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify long-cycle scheduler dry-run readiness separately from live scheduler closure"
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--scheduler-runtime-configured", action="store_true")
    parser.add_argument("--live-scheduler-evidence-json", default="")
    args = parser.parse_args()

    check = check_long_cycle_scheduler_readiness_contract(
        task_goal="Digest weekly report inputs",
        project_key="demo_proj",
        entrypoint="ingest.raw_import",
        source_locator="file:///tmp/weekly-report.md",
        content_format="markdown",
        content_length=8000,
        processed_time="2026-03-08T11:00:00Z",
        candidate_windows=["7d", "30d"],
        selected_window="7d",
        cadence="weekly",
        scheduler_ref="contract.scheduler.ingest-long-cycle",
        persistent_ref="fake-db://long_cycle_persistent_tasks",
        event_time="2026-03-08T11:00:00Z",
        run_at="2026-03-08T11:02:00Z",
        scheduler_runtime_configured=args.scheduler_runtime_configured,
        live_scheduler_evidence=_read_json(args.live_scheduler_evidence_json),
    )

    if args.format == "json":
        print(json.dumps(check, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"status={check['status']}")
        print(f"readiness_state={check['readiness_state']}")
        print(f"closure_claim={check['closure_claim']}")
        print(f"local_deterministic_readiness={check['local_deterministic_readiness']}")
        print(f"dry_run_dispatch_ready={check['dry_run_dispatch_ready']}")
        print(f"live_scheduler_closure_validated={check['live_scheduler_closure_validated']}")
        for stage in check["stages"]:
            print(f"{stage['name']}={stage['status']} passed={stage['passed']} validated={stage['validated']}")
        if check["remaining_runtime_gaps"]:
            print("remaining_runtime_gaps:")
            for gap in check["remaining_runtime_gaps"]:
                print(f"- {gap}")

    return 0 if check["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
