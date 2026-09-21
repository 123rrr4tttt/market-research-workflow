#!/usr/bin/env python3
"""Cleanup entrypoint for persisted LLM report export token state rows."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_settings_defaults() -> tuple[int, bool]:
    sys.path.insert(0, str(_backend_root()))
    from app.settings.config import settings  # noqa: PLC0415

    return (
        int(getattr(settings, "llm_report_export_token_state_retention_days", 30)),
        bool(getattr(settings, "llm_report_export_token_state_cleanup_dry_run_default", True)),
    )


def _run_cleanup(*, retention_days: int, dry_run: bool) -> dict[str, Any]:
    sys.path.insert(0, str(_backend_root()))
    from app.services.llm_report_export_token_state import (  # noqa: PLC0415
        prune_llm_report_export_token_states,
    )

    return prune_llm_report_export_token_states(retention_days=retention_days, dry_run=dry_run)


def build_cleanup_report(
    *,
    retention_days: int,
    dry_run: bool,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=prune_llm_report_export_token_states.summary "
    "witness=test:test_c15_backend_misc_cli_report_metadata_preserves_abi",
]:
    started_at_utc = _utcnow_iso()
    summary = _run_cleanup(retention_days=retention_days, dry_run=dry_run)
    finished_at_utc = _utcnow_iso()
    degraded = bool(summary.get("token_state_store_degraded"))
    return {
        "run_id": str(uuid4()),
        "script_name": "cleanup_llm_report_export_token_state",
        "contract_version": "llm_report.export_token_state_cleanup_script.v1",
        "status": "degraded" if degraded else "ok",
        "mode": "dry_run" if dry_run else "execute",
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "retention_plan": {
            "retention_days": retention_days,
            "dry_run": dry_run,
            "include_active_tokens": False,
        },
        "query_window": {
            "activity_cutoff": summary.get("cutoff"),
        },
        "counts": {
            "candidate_count": int(summary.get("candidate_count") or 0),
            "deleted_count": int(summary.get("deleted_count") or 0),
            "memory_candidate_count": int(summary.get("memory_candidate_count") or 0),
            "memory_deleted_count": int(summary.get("memory_deleted_count") or 0),
        },
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    default_retention_days, default_dry_run = _load_settings_defaults()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retention-days",
        type=int,
        default=default_retention_days,
        help="delete terminal used/revoked rows whose last activity is older than this many days",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="only count eligible rows")
    mode.add_argument("--execute", action="store_true", help="delete eligible rows")
    args = parser.parse_args(argv)

    if args.retention_days < 1:
        parser.error("--retention-days must be >= 1")

    dry_run = bool(default_dry_run)
    if args.dry_run:
        dry_run = True
    if args.execute:
        dry_run = False

    report = build_cleanup_report(retention_days=args.retention_days, dry_run=dry_run)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
