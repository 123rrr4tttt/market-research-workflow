#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


CONTRACT_VERSION = "source-time.production-readiness.v1"
TOPIC_DIR = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-03-02-source-time-window-smart-timestamp-plan"
)

WAVE10_EVIDENCE = TOPIC_DIR / "04_wave10-source-time-window-contract-evidence-2026-05-22.md"
WAVE12_EVIDENCE = TOPIC_DIR / "05_wave12-time-density-decision-log-provenance-evidence-2026-05-22.md"
WAVE15_EVIDENCE = TOPIC_DIR / "06_wave15-source-time-production-readiness-2026-05-22.md"
WAVE17_EVIDENCE = TOPIC_DIR / "07_wave17-source-time-production-sample-readback-gate-2026-05-22.md"

LIVE_EVIDENCE_REQUIREMENTS = (
    "production_data_semantic_chain_verified",
    "live_query_used",
    "configured_services_used",
    "effective_time_source_distribution_readback",
    "source_time_coverage_measured",
    "decision_log_rows_readback",
    "decision_log_features_readback",
)

DEFAULT_LIVE_GAPS = (
    "production_data_semantic_chain_live_validation_not_run",
    "live_source_time_coverage_distribution_not_measured",
    "live_decision_log_features_readback_not_verified",
)

PROTECTED_SHARED_INDEXES = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
)


def _load_script_module(script_name: str):
    module_path = BACKEND_ROOT / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(script_name.removesuffix(".py"), module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load checker module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _token_check(root: Path, relative_path: Path, tokens: tuple[str, ...]) -> dict[str, Any]:
    path = root / relative_path
    exists = path.is_file()
    text = _read_text(path) if exists else ""
    missing = [token for token in tokens if token not in text]
    return {
        "path": str(relative_path),
        "exists": exists,
        "tokens_checked": list(tokens),
        "missing_tokens": missing,
        "passed": bool(exists and not missing),
    }


def _load_runtime_contracts() -> dict[str, dict[str, Any]]:
    source_time = _load_script_module("check_time_semantics_ope_contract.py")
    decision_log = _load_script_module("check_time_density_decision_log_contract.py")
    return {
        "source_time_contract": source_time.build_contract(),
        "decision_log_provenance": decision_log.build_contract(),
    }


def _sample_density_rows(*, start: date, end: date, **_: object) -> list[dict[str, Any]]:
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


def _deterministic_sample_readback_stage() -> dict[str, Any]:
    from app.services.ingest import digestion_scaffold
    from app.services.stats import prompt_time_density

    source_time = "2026-03-02T12:00:00Z"
    processed_time = "2026-03-10T12:00:00Z"
    semantics = digestion_scaffold.build_time_semantics(
        source_time=source_time,
        processed_time=processed_time,
        task_window="7d",
    )
    sample_doc = SimpleNamespace(
        extracted_data={
            "source_time": source_time,
            "time_parse_version": "source-time-window-v1",
            "source_domain": "neutral.example",
            "topic_cluster": "robotics",
        },
        publish_date=None,
        created_at=semantics.processed_time,
        uri="https://neutral.example/research/robotics",
    )
    doc_provenance = prompt_time_density.resolve_document_effective_time_provenance(sample_doc)
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
        side_effect=_sample_density_rows,
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
            project_key="wave17_sample",
        )

    row_by_window = {str(row.get("window")): row for row in rows}
    features_by_window = {
        str(row.get("window")): features
        for row, features in zip(captured.get("rows") or [], captured.get("features_json") or [])
    }
    row_90d = row_by_window.get("90d") or {}
    features_90d = features_by_window.get("90d") or {}
    trace_90d = row_90d.get("policy_decision_trace") or {}
    source_counts = (
        (features_90d.get("effective_time_provenance") or {}).get("source_counts") or {}
    )
    priority_trace = features_90d.get("priority_decision_trace") or {}
    checks = {
        "sample_source_time_readback": semantics.source_time.isoformat() == "2026-03-02T12:00:00+00:00",
        "sample_processed_time_readback": semantics.processed_time.isoformat() == "2026-03-10T12:00:00+00:00",
        "sample_effective_time_prefers_source_time": semantics.time_provenance == "source_time"
        and semantics.effective_time.isoformat() == "2026-03-02T12:00:00+00:00",
        "document_provenance_reads_source_time": doc_provenance.get("source") == "source_time"
        and doc_provenance.get("effective_day") == "2026-03-02",
        "density_rows_read_back_source_time_counts": source_counts.get("source_time") == 2,
        "target_overlap_gap_read_back": float(row_90d.get("target_overlap_gap") or 0.0) > 0.0,
        "target_overlap_decision_trace_read_back": priority_trace.get("target_overlap") == 0.95
        and priority_trace.get("chosen_window") in {"7d", "30d", "90d"},
        "features_json_read_back_decision_evidence": features_90d.get("target_overlap") == 0.95
        and float(features_90d.get("target_overlap_gap") or 0.0) == float(row_90d.get("target_overlap_gap") or 0.0)
        and bool(features_90d.get("live_data_gap_markers")),
        "sample_does_not_claim_live_production": "production_freshness_probe_not_run"
        in (trace_90d.get("live_data_gap_markers") or []),
    }
    missing = [key for key, passed in checks.items() if not passed]
    return {
        "name": "deterministic_sample_readback_chain",
        "status": "passed" if not missing else "failed",
        "passed": not missing,
        "missing_requirements": missing,
        "production_live_verified": False,
        "evidence": {
            "sample_id": "wave17_source_time_density_chain_sample",
            "source_time": source_time,
            "processed_time": processed_time,
            "effective_time": semantics.effective_time.isoformat(),
            "time_provenance": semantics.time_provenance,
            "document_effective_day": doc_provenance.get("effective_day"),
            "row_windows": sorted(row_by_window),
            "target_overlap": row_90d.get("target_overlap"),
            "target_overlap_gap_90d": row_90d.get("target_overlap_gap"),
            "features_json_target_overlap_gap_90d": features_90d.get("target_overlap_gap"),
            "live_gap_markers_90d": trace_90d.get("live_data_gap_markers") or [],
            "project_key": captured.get("project_key"),
        },
    }


def _missing_truthy(payload: dict[str, Any], required_keys: tuple[str, ...]) -> list[str]:
    return [key for key in required_keys if payload.get(key) is not True]


def _source_time_stage(contract: dict[str, Any]) -> dict[str, Any]:
    checks = contract.get("checks") if isinstance(contract.get("checks"), dict) else {}
    source_time_window = checks.get("source_time_window") if isinstance(checks.get("source_time_window"), dict) else {}
    required = (
        "effective_time_uses_source_time",
        "window_bounds_anchor_to_effective_time",
        "density_day_uses_source_time",
    )
    missing = _missing_truthy(source_time_window, required)
    passed = (
        contract.get("status") == "passed_with_known_gaps"
        and not contract.get("failures")
        and not missing
    )
    return {
        "name": "deterministic_source_time_contract",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "missing_requirements": missing,
        "evidence": {
            "contract_version": contract.get("contract_version"),
            "scope": contract.get("scope"),
            "time_provenance": source_time_window.get("time_provenance"),
            "remaining_gaps": contract.get("remaining_gaps") or [],
        },
    }


def _decision_log_stage(contract: dict[str, Any]) -> dict[str, Any]:
    checks = contract.get("checks") if isinstance(contract.get("checks"), dict) else {}
    log_contract = (
        checks.get("decision_log_contract")
        if isinstance(checks.get("decision_log_contract"), dict)
        else {}
    )
    payload_shape = (
        checks.get("persisted_payload_shape")
        if isinstance(checks.get("persisted_payload_shape"), dict)
        else {}
    )
    required_log = (
        "rows_emitted",
        "persist_hook_called",
        "contract_version_recorded",
        "features_json_contract_version_recorded",
        "effective_time_provenance_recorded",
        "ope_freshness_inputs_recorded",
        "priority_decision_trace_recorded",
        "live_data_gap_markers_recorded",
    )
    required_payload = (
        "features_json_carries_provenance",
        "features_json_carries_ope_inputs",
        "features_json_carries_priority_trace",
        "features_json_carries_live_gaps",
    )
    missing = [
        *(f"decision_log_contract.{key}" for key in _missing_truthy(log_contract, required_log)),
        *(f"persisted_payload_shape.{key}" for key in _missing_truthy(payload_shape, required_payload)),
    ]
    passed = (
        contract.get("status") == "passed_with_known_gaps"
        and not contract.get("failures")
        and not missing
    )
    return {
        "name": "decision_log_provenance",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "missing_requirements": missing,
        "evidence": {
            "contract_version": contract.get("contract_version"),
            "scope": contract.get("scope"),
            "remaining_gaps": contract.get("remaining_gaps") or [],
        },
    }


def _production_semantic_chain_stage(
    live_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    if live_evidence is None:
        return {
            "name": "production_data_semantic_chain",
            "status": "ready_not_run",
            "passed": True,
            "production_live_verified": False,
            "missing_requirements": [],
            "remaining_live_gaps": list(DEFAULT_LIVE_GAPS),
            "evidence": {
                "live_evidence_supplied": False,
                "public_or_live_network_attempted": False,
                "semantic_chain_sample_count": 0,
            },
        }

    read_error = live_evidence.get("_evidence_read_error")
    if read_error:
        return {
            "name": "production_data_semantic_chain",
            "status": "failed_evidence",
            "passed": False,
            "production_live_verified": False,
            "missing_requirements": ["live_evidence_json_readable"],
            "remaining_live_gaps": list(DEFAULT_LIVE_GAPS),
            "evidence": {"live_evidence_supplied": True, "read_error": read_error},
        }

    missing = _missing_truthy(live_evidence, LIVE_EVIDENCE_REQUIREMENTS)
    try:
        sample_count = int(
            live_evidence.get("semantic_chain_sample_count")
            or live_evidence.get("sample_count")
            or 0
        )
    except (TypeError, ValueError):
        sample_count = 0
    if sample_count < 1:
        missing.append("semantic_chain_sample_count>=1")

    verified = not missing
    return {
        "name": "production_data_semantic_chain",
        "status": "live_verified" if verified else "failed_evidence",
        "passed": verified,
        "production_live_verified": verified,
        "missing_requirements": missing,
        "remaining_live_gaps": [] if verified else list(DEFAULT_LIVE_GAPS),
        "evidence": {
            "live_evidence_supplied": True,
            "semantic_chain_sample_count": sample_count,
            "requirements_checked": list(LIVE_EVIDENCE_REQUIREMENTS),
            "source_time_coverage": live_evidence.get("source_time_coverage"),
            "decision_log_row_count": live_evidence.get("decision_log_row_count"),
        },
    }


def _doc_token_results(root: Path) -> list[dict[str, Any]]:
    return [
        _token_check(
            root,
            WAVE10_EVIDENCE,
            (
                "Wave10 Source-Time Window Contract Evidence",
                "status=passed_with_known_gaps",
                "source_time_window.effective_time_uses_source_time=true",
                "source_time_window.window_bounds_anchor_to_effective_time=true",
                "source_time_window.density_day_uses_source_time=true",
            ),
        ),
        _token_check(
            root,
            WAVE12_EVIDENCE,
            (
                "Wave12 Time-Density Decision-Log Provenance Evidence",
                "doc_stale",
                "doc_drift",
                "external_gap",
                "check_time_density_decision_log_contract.py",
                "status=passed_with_known_gaps",
                "failures=[]",
            ),
        ),
        _token_check(
            root,
            WAVE15_EVIDENCE,
            (
                "Wave15 Source-Time Production Readiness",
                "check_source_time_production_readiness.py",
                "deterministic_source_time_contract",
                "decision_log_provenance",
                "production_data_semantic_chain",
                "ready_not_run",
                "closure_claim=false",
                "status=passed_with_known_gaps",
            ),
        ),
        _token_check(
            root,
            WAVE17_EVIDENCE,
            (
                "Wave17 Source-Time Production Sample Readback Gate",
                "deterministic_sample_readback_chain",
                "sample_source_time_readback=true",
                "sample_processed_time_readback=true",
                "target_overlap_gap_read_back=true",
                "features_json_read_back_decision_evidence=true",
                "sample_does_not_claim_live_production=true",
                "production_data_semantic_chain_live_validation_not_run",
                "closure_claim=false",
                "status=passed_with_known_gaps",
            ),
        ),
    ]


def build_check(
    *,
    repo_root: Path | str | None = None,
    runtime_contracts: dict[str, dict[str, Any]] | None = None,
    live_evidence: dict[str, Any] | None = None,
    include_doc_checks: bool = True,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()
    contracts = runtime_contracts if runtime_contracts is not None else _load_runtime_contracts()

    source_stage = _source_time_stage(contracts.get("source_time_contract") or {})
    decision_stage = _decision_log_stage(contracts.get("decision_log_provenance") or {})
    sample_stage = _deterministic_sample_readback_stage()
    production_stage = _production_semantic_chain_stage(live_evidence)
    stages = [source_stage, decision_stage, sample_stage, production_stage]

    doc_results = _doc_token_results(root) if include_doc_checks else []
    failures: list[str] = []
    for stage in stages:
        if not stage.get("passed"):
            failures.append(f"stage.{stage['name']}.{stage['status']}")
    for result in doc_results:
        if not result.get("passed"):
            failures.append(f"doc.{result['path']}.missing_tokens")

    production_live_verified = bool(production_stage.get("production_live_verified"))
    if failures:
        status = "failed"
    elif production_live_verified:
        status = "passed"
    else:
        status = "passed_with_known_gaps"

    return {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "scope": "source_time_production_readiness_boundary",
        "closure_claim": False,
        "full_closure_allowed": bool(production_live_verified and not failures),
        "protected_shared_indexes": list(PROTECTED_SHARED_INDEXES),
        "readiness_boundaries": {
            "deterministic_source_time_contract": source_stage["status"],
            "decision_log_provenance": decision_stage["status"],
            "deterministic_sample_readback_chain": sample_stage["status"],
            "production_data_semantic_chain": production_stage["status"],
        },
        "checks": {
            "deterministic_source_time_contract_verified": source_stage["status"] == "passed",
            "decision_log_provenance_verified": decision_stage["status"] == "passed",
            "deterministic_sample_readback_chain_verified": sample_stage["status"] == "passed",
            "production_data_semantic_chain_live_verified": production_live_verified,
            "production_data_semantic_chain_live_gap_retained": production_stage["status"] == "ready_not_run",
            "doc_evidence_current": all(result.get("passed") for result in doc_results),
        },
        "stages": stages,
        "doc_results": doc_results,
        "remaining_live_gaps": list(production_stage.get("remaining_live_gaps") or []),
        "failures": sorted(set(failures)),
    }


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_evidence_read_error": str(exc)}
    if not isinstance(payload, dict):
        return {"_evidence_read_error": "live evidence JSON must be an object"}
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Wave15 source-time production readiness boundary."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to scan.")
    parser.add_argument("--live-evidence-json", default="", help="Optional live production evidence JSON.")
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    parser.add_argument("--write-report", type=Path, default=None, help="Write full JSON output.")
    args = parser.parse_args(argv)

    result = build_check(
        repo_root=args.repo_root,
        live_evidence=_read_json(args.live_evidence_json),
    )

    if args.write_report is not None:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        boundaries = result["readiness_boundaries"]
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"deterministic_source_time_contract={boundaries['deterministic_source_time_contract']} "
            f"decision_log_provenance={boundaries['decision_log_provenance']} "
            f"deterministic_sample_readback_chain={boundaries['deterministic_sample_readback_chain']} "
            f"production_data_semantic_chain={boundaries['production_data_semantic_chain']} "
            f"closure_claim={str(result['closure_claim']).lower()} "
            f"remaining_live_gaps={len(result['remaining_live_gaps'])}"
        )
        if result["status"] == "failed":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))

    return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
