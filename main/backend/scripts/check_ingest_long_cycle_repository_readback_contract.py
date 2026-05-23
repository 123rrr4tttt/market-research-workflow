#!/usr/bin/env python3
"""Wave16 gate for durable ingest long-cycle repository readback contracts."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.ingest.digestion_scaffold import JsonlLongCycleTaskRepository  # noqa: E402
from app.services.ingest.digestion_scaffold import check_long_cycle_repository_readback_contract  # noqa: E402


EVIDENCE_FILE = (
    REPO_ROOT
    / "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED"
    / "2026-03-07-ingest-digestion-and-long-cycle-automation"
    / "07_wave16-long-cycle-durable-repository-readback-2026-05-22.md"
)
REQUIRED_EVIDENCE_MARKERS = (
    "contract_version: ingest.long_cycle_repository_readback_check.v1",
    "durable_readback: true",
    "live_db_write: false",
    "closure_claim: false",
    "live_scheduler_closure_validated: false",
)


def main() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="ingest-lc-readback-") as tmp_dir:
        repository = JsonlLongCycleTaskRepository(
            storage_dir=tmp_dir,
            repository_ref="jsonl://wave16-long-cycle-readback",
            logical_table="long_cycle_persistent_tasks",
        )
        check = check_long_cycle_repository_readback_contract(
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

    readiness = check["scheduler_readiness"]
    readback_record = check.get("readback_record") or {}
    if check["status"] != "pass":
        failures.append(f"expected pass, got {check['status']}: {check['blockers']}")
    if check["contract_version"] != "ingest.long_cycle_repository_readback_check.v1":
        failures.append("repository readback contract version drifted")
    if check["durable_readback"] is not True:
        failures.append("durable readback was not validated")
    if check["live_db_write"] is not False:
        failures.append("repository readback must not claim live DB writes")
    if check["repository_ref"] != "jsonl://wave16-long-cycle-readback":
        failures.append("repository ref drifted from durable JSONL contract ref")
    if check["readback_event_sequence"] != ["mark_ready", "dispatch", "succeed"]:
        failures.append(f"unexpected lifecycle event sequence: {check['readback_event_sequence']}")
    if readback_record.get("status") != "succeeded":
        failures.append(f"readback record must be terminal succeeded, got {readback_record.get('status')}")
    if readiness["status"] != "pass":
        failures.append(f"scheduler readiness must pass, got {readiness['status']}")
    if readiness["closure_claim"] is not False:
        failures.append("scheduler readiness must not claim live closure")
    if readiness["live_scheduler_closure_validated"] is not False:
        failures.append("live scheduler closure must remain unvalidated")
    if "live_persistent_task_table_write_not_executed" not in check["remaining_runtime_gaps"]:
        failures.append("remaining gaps must preserve live persistent task table boundary")
    if "live_db_persistent_task_table_not_validated" not in check["remaining_runtime_gaps"]:
        failures.append("remaining gaps must preserve live DB validation boundary")

    if not EVIDENCE_FILE.is_file():
        failures.append(f"missing evidence file: {EVIDENCE_FILE.relative_to(REPO_ROOT)}")
    else:
        evidence_text = EVIDENCE_FILE.read_text(encoding="utf-8")
        for marker in REQUIRED_EVIDENCE_MARKERS:
            if marker not in evidence_text:
                failures.append(f"evidence file missing marker {marker!r}")

    payload = {
        "status": "fail" if failures else "pass",
        "contract_status": (
            "closed_narrow_durable_repository_readback_contract"
            if not failures
            else "open_durable_repository_readback_gap"
        ),
        "failures": failures,
        "check": check,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
