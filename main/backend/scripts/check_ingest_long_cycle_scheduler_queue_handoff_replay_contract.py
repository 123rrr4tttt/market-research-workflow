#!/usr/bin/env python3
"""Wave55 gate for repo-local live long-cycle scheduler queue handoff replay."""

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

from app.services.ingest.digestion_scaffold import SqliteLongCycleTaskRepository  # noqa: E402
from app.services.ingest.digestion_scaffold import check_long_cycle_scheduler_queue_handoff_replay_contract  # noqa: E402


TOPIC_EVIDENCE_FILE = (
    REPO_ROOT
    / "docs/development/development-plans/ARCHIVE_CLOSED"
    / "2026-03-07-ingest-digestion-and-long-cycle-automation"
    / "12_wave55-repo-local-live-scheduler-queue-handoff-closure-2026-05-23.md"
)
REQUIRED_TOPIC_MARKERS = (
    "contract_version: ingest.long_cycle_scheduler_queue_replay_check.v2",
    "scheduler_intent_validated: true",
    "queue_item_validated: true",
    "repository_write_readback_validated: true",
    "worker_consumption_validated: true",
    "event_replay_summary_validated: true",
    "digestion_output_readback_validated: true",
    "downstream_handoff_validated: true",
    "repo_local_live_closure_validated: true",
    "live_dispatch: true",
    "live_enqueue: true",
    "live_db_write: true",
    "closure_claim: true",
    "live_scheduler_closure_validated: true",
)


def build_check() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ingest-lc-queue-replay-") as tmp_dir:
        repository = SqliteLongCycleTaskRepository(
            db_path=Path(tmp_dir) / "long_cycle_live.db",
            repository_ref="sqlite://wave55-long-cycle-scheduler-queue-replay",
            logical_table="long_cycle_persistent_tasks",
        )
        return check_long_cycle_scheduler_queue_handoff_replay_contract(
            repository=repository,
            repo_local_live=True,
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
            scheduler_ref="repo-local.scheduler.ingest-long-cycle",
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
    if check.get("contract_version") != "ingest.long_cycle_scheduler_queue_replay_check.v2":
        failures.append("queue replay contract version drifted")
    for field in (
        "scheduler_intent_validated",
        "queue_item_validated",
        "repository_write_readback_validated",
        "worker_consumption_validated",
        "event_replay_summary_validated",
        "digestion_output_readback_validated",
        "downstream_handoff_validated",
        "repo_local_live_closure_validated",
    ):
        if check.get(field) is not True:
            failures.append(f"{field} must be true")
    for field in ("live_dispatch", "live_enqueue", "live_db_write", "closure_claim", "live_scheduler_closure_validated"):
        if check.get(field) is not True:
            failures.append(f"{field} must be true")

    if queue_item.get("contract_version") != "ingest.long_cycle_scheduler_queue_item.v1":
        failures.append("queue item contract version drifted")
    if queue_item.get("queue_state") != "queued_repo_local_live":
        failures.append("queue item state must be queued_repo_local_live")
    if dispatch_intent.get("live_dispatch") is not True:
        failures.append("dispatch intent must claim repo-local live dispatch")
    if queue_item.get("dispatch_key") != dispatch_intent.get("dispatch_key"):
        failures.append("queue item dispatch_key must match scheduler intent")
    if queue_item.get("idempotency_key") != dispatch_intent.get("idempotency_key"):
        failures.append("queue item idempotency_key must match scheduler intent")
    if queue_item.get("task_key") != dispatch_intent.get("task_key"):
        failures.append("queue item task_key must match scheduler intent")
    queue_payload = queue_item.get("payload") if isinstance(queue_item.get("payload"), dict) else {}
    if queue_payload.get("queue_handoff_mode") != "repo_local_live_scheduler_queue":
        failures.append("queue item payload must preserve repo-local live handoff mode")
    if queue_payload.get("live_enqueue") is not True:
        failures.append("queue item payload must claim repo-local live enqueue")

    if repository_readback.get("readback_event_sequence") != ["mark_ready", "dispatch", "succeed"]:
        failures.append(f"repository readback event sequence drifted: {repository_readback.get('readback_event_sequence')}")
    if repository_readback.get("storage_kind") != "sqlite":
        failures.append("repository readback must use repo-local sqlite storage")
    if repository_readback.get("live_db_write") is not True:
        failures.append("repository readback must validate repo-local live DB write")
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
    if replay.get("live_db_write") is not True:
        failures.append("event replay summary must validate repo-local live DB write")
    if replay.get("live_scheduler_closure_validated") is not True:
        failures.append("event replay summary must validate repo-local scheduler closure")

    worker = check.get("worker_consumption") if isinstance(check.get("worker_consumption"), dict) else {}
    downstream_handoff = check.get("downstream_handoff") if isinstance(check.get("downstream_handoff"), dict) else {}
    evidence = check.get("live_scheduler_evidence") if isinstance(check.get("live_scheduler_evidence"), dict) else {}
    if worker.get("consumed") is not True:
        failures.append("worker consumption evidence must show consumed=true")
    if worker.get("event_sequence") != ["mark_ready", "dispatch", "succeed"]:
        failures.append(f"worker event sequence drifted: {worker.get('event_sequence')}")
    if worker.get("db_write_readback") is not True:
        failures.append("worker consumption must prove DB write/readback")
    if downstream_handoff.get("contract_version") != "ingest.long_cycle_downstream_handoff.v1":
        failures.append("downstream handoff contract version drifted")
    if downstream_handoff.get("handoff_state") != "ready_for_downstream":
        failures.append("downstream handoff must be ready_for_downstream")
    if downstream_handoff.get("downstream_handoff_observed") is not True:
        failures.append("downstream handoff must be observed")
    for field in (
        "live_scheduler_dispatch_executed",
        "recurring_schedule_registered",
        "production_worker_task_executed",
        "live_persistent_task_table_write",
        "digestion_output_readback",
        "downstream_handoff_observed",
    ):
        if evidence.get(field) is not True:
            failures.append(f"live scheduler evidence field {field} must be true")
    if check.get("remaining_runtime_gaps") != []:
        failures.append(f"repo-local live closure must leave no runtime gaps: {check.get('remaining_runtime_gaps')}")

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
        description="Validate the Wave55 repo-local live scheduler queue handoff replay gate"
    )
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON output path.")
    args = parser.parse_args(argv)

    check = build_check()
    failures = validate_check(check)
    payload = {
        "status": "fail" if failures else "pass",
        "contract_status": (
            "closed_repo_local_live_scheduler_queue_handoff"
            if not failures
            else "open_repo_local_live_scheduler_queue_handoff_gap"
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
