#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


CONTRACT_VERSION = "time-semantics.release-gate-readback.v1"
TARGET_DIR = Path(
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
    "2026-03-14-time-semantics-density-merged-plan"
)
TARGET_README = TARGET_DIR / "README.md"
TARGET_EVIDENCE = TARGET_DIR / "12_wave55-time-semantics-release-gate-readback-2026-05-23.md"
PRE_RELEASE_GATE = Path("main/backend/scripts/pre_release_gate.sh")

DOC_MARKERS = (
    "Wave55 Time Semantics Release Gate/Source Distribution Readback",
    "check_time_semantics_release_gate.py",
    f"contract_version={CONTRACT_VERSION}",
    "source_time_distribution_repo_local_verified=true",
    "decision_log_features_readback_repo_local_verified=true",
    "release_gate_integration_verified=true",
    "production_data_semantic_chain_live_verified=false",
    "closure_claim=false",
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


def _fake_distribution_rows(*, start: date, end: date, **_: object) -> list[dict[str, Any]]:
    window_days = (end - start).days + 1
    return [
        {
            "source_domain": "neutral.example",
            "noun_group_id": "robotics",
            "prompt_group_id": "robotics",
            "bucket_time": end.isoformat(),
            "effective_new_docs": 6,
            "density": 6.0 / float(window_days),
            "baseline_density": 0.1,
            "norm_density": 0.3,
            "dup_ratio": 0.0,
            "effective_time_provenance": {
                "total_docs": 6,
                "source_counts": {
                    "effective_time": 1,
                    "source_time": 4,
                    "created_at": 1,
                },
                "gap_counts": {
                    "effective_time_missing": 5,
                    "created_at_fallback_used": 1,
                    "semantic_time_fallback_used": 1,
                },
                "parse_versions": ["policy-time-expr-v1", "source-time-window-v1"],
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


def _build_distribution_readback_stage() -> dict[str, Any]:
    try:
        from app.services.stats import prompt_time_density
    except Exception:  # noqa: BLE001 - release gate must remain repo-local under fallback imports.
        from scripts import check_time_density_runtime_support as prompt_time_density

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
        side_effect=_fake_distribution_rows,
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
            project_key="wave55_time_semantics_release_gate",
        )

    features_by_window = {
        str(row.get("window")): features
        for row, features in zip(captured.get("rows") or [], captured.get("features_json") or [])
    }
    features_90d = features_by_window.get("90d") or {}
    distribution_90d = features_90d.get("effective_time_source_distribution") or {}
    rows_by_window = {str(row.get("window")): row for row in rows}
    trace_90d = (rows_by_window.get("90d") or {}).get("policy_decision_trace") or {}
    trace_distribution = trace_90d.get("effective_time_source_distribution") or {}

    source_time_coverage = float(distribution_90d.get("source_time_coverage") or 0.0)
    semantic_coverage = float(distribution_90d.get("explicit_semantic_time_coverage") or 0.0)
    fallback_rate = float(distribution_90d.get("fallback_rate") or 0.0)
    checks = {
        "priority_rows_emitted": bool(rows),
        "persisted_rows_captured": bool(captured.get("rows")),
        "source_time_distribution_repo_local_verified": (
            distribution_90d.get("total_docs") == 6
            and distribution_90d.get("source_time_count") == 4
            and round(source_time_coverage, 6) == round(4.0 / 6.0, 6)
            and round(semantic_coverage, 6) == round(5.0 / 6.0, 6)
            and round(fallback_rate, 6) == round(1.0 / 6.0, 6)
        ),
        "decision_log_features_readback_repo_local_verified": (
            features_90d.get("contract_version")
            == prompt_time_density.TIME_DENSITY_DECISION_LOG_CONTRACT_VERSION
            and features_90d.get("effective_time_source_distribution") == trace_distribution
            and round(float(features_90d.get("source_time_coverage") or 0.0), 6)
            == round(source_time_coverage, 6)
            and bool(features_90d.get("live_data_gap_markers"))
        ),
        "live_gap_markers_retained": (
            "production_freshness_probe_not_run" in (features_90d.get("live_data_gap_markers") or [])
            and "prompt_time_window_feedback_pending" in (features_90d.get("live_data_gap_markers") or [])
        ),
    }
    missing = [name for name, passed in checks.items() if passed is not True]
    return {
        "name": "source_time_distribution_decision_log_readback",
        "status": "passed" if not missing else "failed",
        "passed": not missing,
        "checks": checks,
        "missing_requirements": missing,
        "evidence": {
            "project_key": captured.get("project_key"),
            "row_windows": sorted(rows_by_window),
            "source_distribution_90d": distribution_90d,
            "source_time_coverage_90d": source_time_coverage,
            "explicit_semantic_time_coverage_90d": semantic_coverage,
            "fallback_rate_90d": fallback_rate,
            "features_contract_version": features_90d.get("contract_version"),
            "live_gap_markers_90d": features_90d.get("live_data_gap_markers") or [],
        },
    }


def _release_gate_stage(repo_root: Path, pre_release_gate_path: Path | None = None) -> dict[str, Any]:
    relative_path = pre_release_gate_path or PRE_RELEASE_GATE
    path = relative_path if relative_path.is_absolute() else repo_root / relative_path
    text = _read_text(path)
    checks = {
        "pre_release_gate_exists": path.is_file(),
        "release_gate_calls_time_semantics_checker": "scripts/check_time_semantics_release_gate.py" in text,
        "release_gate_runs_time_semantics_unit_test": (
            "tests/unit/test_time_semantics_release_gate_unittest.py" in text
        ),
        "release_gate_keeps_sample_readback_test": (
            "tests/unit/test_time_semantics_sample_provenance_readback_unittest.py" in text
        ),
    }
    missing = [name for name, passed in checks.items() if passed is not True]
    return {
        "name": "pre_release_gate_integration",
        "status": "passed" if not missing else "failed",
        "passed": not missing,
        "path": str(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else str(path),
        "checks": checks,
        "missing_requirements": missing,
    }


def _doc_stage(repo_root: Path) -> dict[str, Any]:
    evidence_path = repo_root / TARGET_EVIDENCE
    evidence_text = _read_text(evidence_path)
    readme_text = _read_text(repo_root / TARGET_README)
    missing_markers = [marker for marker in DOC_MARKERS if marker not in evidence_text]
    checks = {
        "target_evidence_exists": evidence_path.is_file(),
        "target_evidence_markers_present": not missing_markers,
        "target_readme_links_evidence": TARGET_EVIDENCE.name in readme_text,
    }
    missing = [name for name, passed in checks.items() if passed is not True]
    return {
        "name": "target_doc_artifact",
        "status": "passed" if not missing else "failed",
        "passed": not missing,
        "checks": checks,
        "path": str(TARGET_EVIDENCE),
        "missing_requirements": missing,
        "missing_markers": missing_markers,
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


def build_check(
    *,
    repo_root: Path | str | None = None,
    live_evidence: dict[str, Any] | None = None,
    include_doc_checks: bool = True,
    pre_release_gate_path: Path | None = None,
    strict_closure: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()
    source_readiness = _load_script_module("check_source_time_production_readiness.py").build_check(
        repo_root=root,
        live_evidence=live_evidence,
        include_doc_checks=False,
    )
    sample_readback = _load_script_module("check_time_semantics_sample_provenance_readback.py").build_check(
        repo_root=root,
        include_doc_checks=False,
    )
    distribution_stage = _build_distribution_readback_stage()
    release_gate = _release_gate_stage(root, pre_release_gate_path=pre_release_gate_path)
    doc_stage = _doc_stage(root) if include_doc_checks else {
        "name": "target_doc_artifact",
        "status": "skipped",
        "passed": True,
        "checks": {},
        "missing_requirements": [],
        "missing_markers": [],
    }

    production_live_verified = bool(
        source_readiness.get("checks", {}).get("production_data_semantic_chain_live_verified")
    )
    configured_semantic_chain_verified = bool(
        source_readiness.get("checks", {}).get("configured_semantic_chain_evidence_verified")
    )
    configured_production_like_verified = bool(
        source_readiness.get("checks", {}).get(
            "configured_production_like_semantic_chain_evidence_verified"
        )
    )
    stages = [distribution_stage, release_gate, doc_stage]
    failures: list[str] = []
    if source_readiness.get("failures"):
        failures.append("source_readiness.failed")
    if sample_readback.get("failures"):
        failures.append("sample_readback.failed")
    for stage in stages:
        if not stage.get("passed"):
            failures.append(f"stage.{stage['name']}.{stage['status']}")
    if strict_closure and not production_live_verified:
        failures.append("production_data_semantic_chain_live_required")

    if failures:
        status = "failed"
    elif production_live_verified:
        status = "passed"
    elif configured_semantic_chain_verified:
        status = "passed_with_configured_evidence"
    else:
        status = "passed_with_known_gaps"
    external_blockers_reduced = []
    if release_gate.get("passed"):
        external_blockers_reduced.append("release_gate_integration")
    stage_checks = distribution_stage.get("checks") or {}
    if stage_checks.get("source_time_distribution_repo_local_verified"):
        external_blockers_reduced.append("source_time_distribution_repo_local_readback")
    if stage_checks.get("decision_log_features_readback_repo_local_verified"):
        external_blockers_reduced.append("decision_log_features_repo_local_readback")

    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "time_semantics_density_release_gate_repo_local_readback",
        "status": status,
        "strict_closure": bool(strict_closure),
        "closure_claim": False,
        "full_closure_allowed": bool(production_live_verified and not failures),
        "target": str(TARGET_DIR),
        "checks": {
            "deterministic_source_time_contract_verified": bool(
                source_readiness.get("checks", {}).get("deterministic_source_time_contract_verified")
            ),
            "decision_log_provenance_verified": bool(
                source_readiness.get("checks", {}).get("decision_log_provenance_verified")
            ),
            "sample_provenance_readback_verified": sample_readback.get("status")
            == "passed_with_known_gaps",
            "source_time_distribution_repo_local_verified": bool(
                stage_checks.get("source_time_distribution_repo_local_verified")
            ),
            "decision_log_features_readback_repo_local_verified": bool(
                stage_checks.get("decision_log_features_readback_repo_local_verified")
            ),
            "release_gate_integration_verified": bool(release_gate.get("passed")),
            "configured_semantic_chain_evidence_verified": configured_semantic_chain_verified,
            "configured_production_like_semantic_chain_evidence_verified": configured_production_like_verified,
            "production_data_semantic_chain_live_verified": production_live_verified,
            "target_doc_artifact_verified": bool(doc_stage.get("passed")),
        },
        "external_blockers_reduced": external_blockers_reduced,
        "remaining_external_blockers": []
        if production_live_verified
        else list(source_readiness.get("remaining_live_gaps") or []),
        "remaining_live_requirements": []
        if production_live_verified
        else [
            "explicit configured-live or production-like semantic-chain evidence with tier/data_source/source-time coverage proof"
            if not configured_semantic_chain_verified
            else "explicit production/live dataset tier and data_source beyond configured production-like sample",
            "configured production/live source-time coverage count and total proof",
            "configured production/live prompt-time policy decision-log rows",
            "configured production/live feedback reward alignment",
        ],
        "readiness_boundaries": source_readiness.get("readiness_boundaries") or {},
        "stages": stages,
        "source_readiness_status": source_readiness.get("status"),
        "sample_readback_status": sample_readback.get("status"),
        "failures": sorted(set(failures)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check time-semantics density release-gate/source-distribution readback."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to scan.")
    parser.add_argument("--live-evidence-json", default="", help="Optional live production evidence JSON.")
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    parser.add_argument("--output", type=Path, default=None, help="Write full JSON output.")
    parser.add_argument("--skip-doc-checks", action="store_true", help="Skip target evidence doc checks.")
    parser.add_argument("--pre-release-gate-path", type=Path, default=None)
    parser.add_argument(
        "--strict-closure",
        action="store_true",
        help="Fail unless production/live semantic-chain evidence fully verifies the remaining blocker.",
    )
    args = parser.parse_args(argv)

    result = build_check(
        repo_root=args.repo_root,
        live_evidence=_read_json(args.live_evidence_json),
        include_doc_checks=not args.skip_doc_checks,
        pre_release_gate_path=args.pre_release_gate_path,
        strict_closure=bool(args.strict_closure),
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        checks = result["checks"]
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"source_time_distribution_repo_local_verified="
            f"{str(checks['source_time_distribution_repo_local_verified']).lower()} "
            f"decision_log_features_readback_repo_local_verified="
            f"{str(checks['decision_log_features_readback_repo_local_verified']).lower()} "
            f"release_gate_integration_verified="
            f"{str(checks['release_gate_integration_verified']).lower()} "
            f"configured_semantic_chain_evidence_verified="
            f"{str(checks['configured_semantic_chain_evidence_verified']).lower()} "
            f"production_data_semantic_chain_live_verified="
            f"{str(checks['production_data_semantic_chain_live_verified']).lower()} "
            f"closure_claim={str(result['closure_claim']).lower()} "
            f"remaining_external_blockers={len(result['remaining_external_blockers'])}"
        )
        if result["status"] == "failed":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
