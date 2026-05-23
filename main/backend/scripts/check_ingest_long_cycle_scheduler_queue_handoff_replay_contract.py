#!/usr/bin/env python3
"""Wave20 gate for long-cycle scheduler queue handoff and repository replay."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingest.digestion_scaffold import JsonlLongCycleTaskRepository  # noqa: E402
from app.services.ingest.digestion_scaffold import check_long_cycle_scheduler_queue_handoff_replay_contract  # noqa: E402


TOPIC_EVIDENCE_FILE = (
    REPO_ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-03-07-ingest-digestion-and-long-cycle-automation"
    / "09_wave20-long-cycle-scheduler-queue-handoff-replay-2026-05-22.md"
)
REQUIRED_TOPIC_MARKERS = (
    "contract_version: ingest.long_cycle_scheduler_queue_replay_check.v1",
    "scheduler_intent_validated: true",
    "queue_item_validated: true",
    "repository_write_readback_validated: true",
    "event_replay_summary_validated: true",
    "live_dispatch: false",
    "live_enqueue: false",
    "live_db_write: false",
    "closure_claim: false",
    "live_scheduler_closure_validated: false",
)


def build_check() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ingest-lc-queue-replay-") as tmp_dir:
        repository = JsonlLongCycleTaskRepository(
            storage_dir=tmp_dir,
            repository_ref="jsonl://wave20-long-cycle-scheduler-queue-replay",
            logical_table="long_cycle_persistent_tasks",
        )
        return check_long_cycle_scheduler_queue_handoff_replay_contract(
            repository=repository,
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
            persistent_ref=repository.repository_ref,
            event_time="2026-03-08T11:00:00Z",
            run_at="2026-03-08T11:02:00Z",
        )


def validate_check(check: dict[str, object]) -> list[str]:
    failures: list[str] = []
    queue_item = check.get("queue_item") if isinstance(check.get("queue_item"), dict) else {}
    replay = check.get("event_replay_summary") if isinstance(check.get("event_replay_summary"), dict) else {}
    dispatch_intent = check.get("dispatch_intent") if isinstance(check.get("dispatch_intent"), dict) else {}
    repository_readback = check.get("repository_readback") if isinstance(check.get("repository_readback"), dict) else {}

    if check.get("status") != "pass":
        failures.append(f"expected pass, got {check.get('status')}: {check.get('blockers')}")
    if check.get("contract_version") != "ingest.long_cycle_scheduler_queue_replay_check.v1":
        failures.append("queue replay contract version drifted")
    for field in (
        "scheduler_intent_validated",
        "queue_item_validated",
        "repository_write_readback_validated",
        "event_replay_summary_validated",
    ):
        if check.get(field) is not True:
            failures.append(f"{field} must be true")
    for field in ("live_dispatch", "live_enqueue", "live_db_write", "closure_claim", "live_scheduler_closure_validated"):
        if check.get(field) is not False:
            failures.append(f"{field} must remain false")

    if queue_item.get("contract_version") != "ingest.long_cycle_scheduler_queue_item.v1":
        failures.append("queue item contract version drifted")
    if queue_item.get("queue_state") != "queued_contract_only":
        failures.append("queue item state must remain queued_contract_only")
    if queue_item.get("dispatch_key") != dispatch_intent.get("dispatch_key"):
        failures.append("queue item dispatch_key must match scheduler intent")
    if queue_item.get("idempotency_key") != dispatch_intent.get("idempotency_key"):
        failures.append("queue item idempotency_key must match scheduler intent")
    if queue_item.get("task_key") != dispatch_intent.get("task_key"):
        failures.append("queue item task_key must match scheduler intent")
    queue_payload = queue_item.get("payload") if isinstance(queue_item.get("payload"), dict) else {}
    if queue_payload.get("queue_handoff_mode") != "durable_repository_replay_contract_only":
        failures.append("queue item payload must preserve contract-only handoff mode")
    if queue_payload.get("live_enqueue") is not False:
        failures.append("queue item payload must not claim live enqueue")

    if repository_readback.get("readback_event_sequence") != ["mark_ready", "dispatch", "succeed"]:
        failures.append(f"repository readback event sequence drifted: {repository_readback.get('readback_event_sequence')}")
    if repository_readback.get("live_db_write") is not False:
        failures.append("repository readback must not claim live DB write")
    if replay.get("contract_version") != "ingest.long_cycle_repository_event_replay_summary.v1":
        failures.append("event replay summary contract version drifted")
    if replay.get("replay_complete") is not True:
        failures.append("event replay summary must be complete")
    if replay.get("repository_write_readback") is not True:
        failures.append("event replay summary must validate repository write/readback")
    if replay.get("event_sequence") != ["mark_ready", "dispatch", "succeed"]:
        failures.append(f"event replay sequence drifted: {replay.get('event_sequence')}")
    if replay.get("write_status_sequence") != ["ready", "running", "succeeded"]:
        failures.append(f"write status sequence drifted: {replay.get('write_status_sequence')}")
    if replay.get("terminal_status") != "succeeded":
        failures.append(f"terminal replay status must be succeeded, got {replay.get('terminal_status')}")
    if "live_scheduler_queue_enqueue_not_executed" not in check.get("remaining_runtime_gaps", []):
        failures.append("remaining gaps must preserve live scheduler queue enqueue boundary")
    if "live_db_persistent_task_table_not_validated" not in check.get("remaining_runtime_gaps", []):
        failures.append("remaining gaps must preserve live DB boundary")

    if not TOPIC_EVIDENCE_FILE.is_file():
        failures.append(f"missing topic evidence file: {TOPIC_EVIDENCE_FILE.relative_to(REPO_ROOT)}")
    else:
        evidence_text = TOPIC_EVIDENCE_FILE.read_text(encoding="utf-8")
        for marker in REQUIRED_TOPIC_MARKERS:
            if marker not in evidence_text:
                failures.append(f"topic evidence file missing marker {marker!r}")

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the Wave20 scheduler queue handoff and durable repository replay gate"
    )
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    args = parser.parse_args(argv)

    check = build_check()
    failures = validate_check(check)
    payload = {
        "status": "fail" if failures else "pass",
        "contract_status": (
            "closed_narrow_scheduler_queue_replay_contract"
            if not failures
            else "open_scheduler_queue_replay_gap"
        ),
        "failures": failures,
        "check": check,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
