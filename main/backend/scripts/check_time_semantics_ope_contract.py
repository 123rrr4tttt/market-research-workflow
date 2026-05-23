#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_prompt_time_density_gonogo import build_gonogo_report

try:
    from app.services.ingest import digestion_scaffold
except Exception:  # noqa: BLE001 - deterministic gate must survive app import drift.
    from scripts.check_time_density_runtime_support import digestion_scaffold

try:
    from app.services.stats import prompt_time_density
except Exception:  # noqa: BLE001 - fallback keeps this checker repo-local under python3.
    from scripts import check_time_density_runtime_support as prompt_time_density

try:
    from scripts.run_prompt_time_density_ope import evaluate_ope
except Exception:  # noqa: BLE001 - OPE script imports live DB settings in some runtimes.
    from scripts.check_time_density_runtime_support import evaluate_ope


CONTRACT_VERSION = "time-semantics-ope-deterministic-contract.v1"


def _fake_density_rows(*, start: date, end: date, **_: object) -> list[dict[str, object]]:
    window_days = (end - start).days + 1
    return [
        {
            "source_domain": "neutral.example",
            "noun_group_id": "robotics",
            "prompt_group_id": "robotics",
            "bucket_time": end.isoformat(),
            "effective_new_docs": 3,
            "density": 3.0 / float(window_days),
            "baseline_density": 0.1,
            "norm_density": 0.2,
            "dup_ratio": 0.0,
        }
    ]


def _ope_fixture_rows(*, created_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for request_id in ("req-1", "req-2", "req-3"):
        for window, p_base, p_new, chosen in (
            ("7d", 0.40, 0.55, True),
            ("30d", 0.35, 0.30, False),
            ("90d", 0.25, 0.15, False),
        ):
            rows.append(
                {
                    "request_id": request_id,
                    "source_domain": "neutral.example",
                    "noun_group_id": "robotics",
                    "window": window,
                    "chosen_window": "7d",
                    "is_chosen": chosen,
                    "p_base": p_base,
                    "p_new": p_new,
                    "vector_overlap": 0.62,
                    "offpeak_confidence": 0.7,
                    "observed_reward": 0.75 if chosen else None,
                    "features_json": {
                        "dup_ratio": 0.0,
                        "peak_pressure": 0.2,
                        "target_overlap": 0.55,
                        "target_overlap_gap": 0.0,
                    },
                    "created_at": created_at,
                }
            )
    return rows


def _source_time_window_contract() -> dict[str, Any]:
    semantics = digestion_scaffold.build_time_semantics(
        source_time="2026-03-01T08:00:00Z",
        processed_time="2026-03-10T08:00:00Z",
        task_window="7d",
    )
    doc = SimpleNamespace(
        extracted_data={"source_time": "2026-03-01T08:00:00Z"},
        publish_date=None,
        created_at=datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc),
    )
    effective_day = prompt_time_density.resolve_document_effective_day(doc)
    return {
        "effective_time_uses_source_time": semantics.effective_time.isoformat() == "2026-03-01T08:00:00+00:00",
        "window_bounds_anchor_to_effective_time": semantics.task_window_start == date(2026, 2, 23)
        and semantics.task_window_end == date(2026, 3, 1),
        "time_provenance": semantics.time_provenance,
        "density_day_uses_source_time": effective_day == date(2026, 3, 1),
    }


def _target_overlap_contract() -> dict[str, Any]:
    with patch.object(prompt_time_density, "query_prompt_time_density", side_effect=_fake_density_rows), patch.object(
        prompt_time_density,
        "_persist_policy_decision_logs",
    ):
        low_target = {
            str(row["window"]): row
            for row in prompt_time_density.query_prompt_time_density_priority(
                end=date(2026, 3, 31),
                candidate_windows=["7d", "30d", "90d"],
                min_overlap=0.35,
                target_overlap=0.55,
                eta=1.0,
                delta_max=1.0,
                tau=10.0,
                avoid_peak=True,
            )
        }
        high_target = {
            str(row["window"]): row
            for row in prompt_time_density.query_prompt_time_density_priority(
                end=date(2026, 3, 31),
                candidate_windows=["7d", "30d", "90d"],
                min_overlap=0.35,
                target_overlap=0.95,
                eta=1.0,
                delta_max=1.0,
                tau=10.0,
                avoid_peak=True,
            )
        }
    return {
        "target_overlap_gap_observed": float(high_target["90d"]["target_overlap_gap"]) > 0.0,
        "target_overlap_changes_probability": float(high_target["90d"]["p_new"])
        < float(low_target["90d"]["p_new"]),
        "policy_trace_carries_target_overlap": (
            (high_target["90d"].get("policy_decision_trace") or {})
            .get("shift_signal_breakdown", {})
            .get("target_overlap")
            == 0.95
        ),
    }


def _ope_freshness_contract() -> dict[str, Any]:
    now = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    rows = _ope_fixture_rows(created_at="2026-05-22T10:00:00+00:00")
    report = evaluate_ope(rows, n_bootstrap=50, now=now, stale_after_hours=24.0)
    gate = build_gonogo_report(
        realcase={"failed": 0},
        perf={"api_p95_seconds": 0.3, "api_error_rate": 0.0},
        ope=report,
        require_ope=True,
        ope_min_contexts=2,
        ope_max_latest_age_hours=24.0,
        ope_min_ess_ratio=0.2,
        ope_max_weight_cv=2.5,
    )
    stale = evaluate_ope(
        _ope_fixture_rows(created_at="2026-05-18T10:00:00+00:00"),
        n_bootstrap=50,
        now=now,
        stale_after_hours=24.0,
    )
    stale_gate = build_gonogo_report(
        realcase={"failed": 0},
        perf={"api_p95_seconds": 0.3, "api_error_rate": 0.0},
        ope=stale,
        require_ope=True,
        ope_min_contexts=2,
        ope_max_latest_age_hours=24.0,
    )
    return {
        "freshness_status": report["freshness"]["status"],
        "diagnostics_present": "effective_sample_size_ratio" in report["diagnostics"],
        "fresh_gate_go": gate["decision"] == "GO",
        "stale_gate_no_go": stale_gate["decision"] == "NO-GO",
    }


def build_contract() -> dict[str, Any]:
    checks = {
        "source_time_window": _source_time_window_contract(),
        "target_overlap_priority": _target_overlap_contract(),
        "ope_freshness_gate": _ope_freshness_contract(),
    }
    failures: list[str] = []
    for group, result in checks.items():
        for key, passed in result.items():
            if isinstance(passed, bool) and not passed:
                failures.append(f"{group}.{key}")
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "deterministic_current_state_no_live_production_probe",
        "status": "failed" if failures else "passed_with_known_gaps",
        "checks": checks,
        "failures": failures,
        "remaining_gaps": [
            "live_prompt_time_policy_decision_log_volume_not_verified",
            "live_prompt_time_window_feedback_alignment_not_verified",
            "real_production_data_validation_not_run",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check deterministic time semantics + OPE contract.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    contract = build_contract()
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(contract, ensure_ascii=False, sort_keys=True))
    return 0 if not contract["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
