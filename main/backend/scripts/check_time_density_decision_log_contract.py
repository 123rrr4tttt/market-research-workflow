#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from app.services.stats import prompt_time_density
except Exception:  # noqa: BLE001 - deterministic checker can run without full app settings import.
    from scripts import check_time_density_runtime_support as prompt_time_density


CONTRACT_VERSION = prompt_time_density.TIME_DENSITY_DECISION_LOG_CONTRACT_VERSION


def _fake_density_rows(*, start: date, end: date, **_: object) -> list[dict[str, Any]]:
    window_days = (end - start).days + 1
    return [
        {
            "source_domain": "neutral.example",
            "noun_group_id": "robotics",
            "prompt_group_id": "robotics",
            "bucket_time": end.isoformat(),
            "effective_new_docs": 2,
            "density": 2.0 / float(window_days),
            "baseline_density": 0.1,
            "norm_density": 0.2,
            "dup_ratio": 0.0,
            "effective_time_provenance": {
                "total_docs": 2,
                "source_counts": {"source_time": 2},
                "gap_counts": {"effective_time_missing": 2},
                "parse_versions": ["policy-time-expr-v1"],
                "fallback_chain": [
                    "extracted_data.effective_time",
                    "extracted_data.source_time",
                    "extracted_data.policy.effective_date",
                    "publish_date",
                    "created_at",
                ],
            },
        }
    ]


def _priority_fixture() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    captured: dict[str, Any] = {}

    def capture_persist(
        *,
        request_id: str,
        rows: list[dict[str, Any]],
        chosen_window: str,
        project_key: str | None = None,
    ) -> None:
        captured["request_id"] = request_id
        captured["chosen_window"] = chosen_window
        captured["project_key"] = project_key
        captured["rows"] = [dict(row) for row in rows]
        captured["features_json"] = [
            prompt_time_density.build_time_density_decision_log_features(
                row,
                row.get("policy_decision_trace") or {},
            )
            for row in rows
        ]

    with patch.object(
        prompt_time_density,
        "query_prompt_time_density",
        side_effect=_fake_density_rows,
    ), patch.object(
        prompt_time_density,
        "_persist_policy_decision_logs",
        side_effect=capture_persist,
    ):
        rows = prompt_time_density.query_prompt_time_density_priority(
            end=date(2026, 3, 31),
            candidate_windows=["7d", "30d", "90d"],
            min_overlap=0.35,
            target_overlap=0.95,
            eta=1.0,
            delta_max=1.0,
            tau=10.0,
            avoid_peak=True,
            project_key="demo_proj",
        )
    return rows, captured


def build_contract() -> dict[str, Any]:
    rows, captured = _priority_fixture()
    first = rows[0] if rows else {}
    trace = first.get("policy_decision_trace") or {}
    features_json = (captured.get("features_json") or [{}])[0]
    effective_time_provenance = trace.get("effective_time_provenance") or {}
    ope_freshness_inputs = trace.get("ope_freshness_inputs") or {}
    priority_trace = trace.get("priority_decision_trace") or {}
    gap_markers = trace.get("live_data_gap_markers") or []

    checks = {
        "decision_log_contract": {
            "rows_emitted": bool(rows),
            "persist_hook_called": bool(captured.get("rows")),
            "contract_version_recorded": trace.get("contract_version") == CONTRACT_VERSION,
            "features_json_contract_version_recorded": features_json.get("contract_version") == CONTRACT_VERSION,
            "effective_time_provenance_recorded": (
                (effective_time_provenance.get("source_counts") or {}).get("source_time") == 2
            ),
            "ope_freshness_inputs_recorded": (
                ope_freshness_inputs.get("freshness_timestamp_field") == "created_at"
                and ope_freshness_inputs.get("feedback_table") == "public.prompt_time_window_feedback"
                and bool(ope_freshness_inputs.get("chosen_window"))
            ),
            "priority_decision_trace_recorded": (
                priority_trace.get("behavior_policy") == "highest_p_base_window_for_ope_replay"
                and "p_new_desc" in (priority_trace.get("sort_order") or [])
                and int(priority_trace.get("rank") or 0) >= 1
            ),
            "live_data_gap_markers_recorded": (
                "prompt_time_window_feedback_pending" in gap_markers
                and "production_freshness_probe_not_run" in gap_markers
                and "effective_time_gap:effective_time_missing" in gap_markers
            ),
        },
        "persisted_payload_shape": {
            "features_json_carries_provenance": bool(features_json.get("effective_time_provenance")),
            "features_json_carries_ope_inputs": bool(features_json.get("ope_freshness_inputs")),
            "features_json_carries_priority_trace": bool(features_json.get("priority_decision_trace")),
            "features_json_carries_live_gaps": bool(features_json.get("live_data_gap_markers")),
        },
    }
    failures: list[str] = []
    for group, result in checks.items():
        for key, passed in result.items():
            if isinstance(passed, bool) and not passed:
                failures.append(f"{group}.{key}")

    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "deterministic_decision_log_freshness_contract_no_live_probe",
        "status": "failed" if failures else "passed_with_known_gaps",
        "checks": checks,
        "failures": failures,
        "remaining_gaps": [
            "live_prompt_time_policy_decision_log_volume_not_verified",
            "live_prompt_time_window_feedback_alignment_not_verified",
            "production_freshness_not_claimed_by_local_contract",
            "release_pipeline_gate_wiring_not_changed",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check prompt-time-density decision-log freshness contract.")
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
