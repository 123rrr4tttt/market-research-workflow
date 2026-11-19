from __future__ import annotations

from unittest.mock import patch

from main.backend.scripts import cleanup_llm_report_export_token_state as cleanup


def test_cleanup_report_keeps_dry_run_and_counts_explicit() -> None:
    summary = {
        "cutoff": "2026-01-01T00:00:00+00:00",
        "candidate_count": 3,
        "deleted_count": 0,
        "memory_candidate_count": 2,
        "memory_deleted_count": 0,
        "token_state_store_degraded": False,
    }
    with patch.object(cleanup, "_run_cleanup", return_value=summary):
        report = cleanup.build_cleanup_report(retention_days=30, dry_run=True)

    assert report["status"] == "ok"
    assert report["mode"] == "dry_run"
    assert report["retention_plan"] == {
        "retention_days": 30,
        "dry_run": True,
        "include_active_tokens": False,
    }
    assert report["counts"] == {
        "candidate_count": 3,
        "deleted_count": 0,
        "memory_candidate_count": 2,
        "memory_deleted_count": 0,
    }
