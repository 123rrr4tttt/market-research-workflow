#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


CONTRACT_VERSION = "time-semantics.sample-provenance-readback.v1"
SCOPE = "repo_local_deterministic_sample_provenance_readback_no_live_production_probe"

SOURCE_READINESS_SCRIPT = "check_source_time_production_readiness.py"
CURRENT_DEV_ROOT = Path("development/latest-dev-docs/development-plans/CURRENT_DEV")
ARCHIVE_EXTERNAL_BLOCKED_ROOT = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED")


def _evidence_path_candidates(topic_dir: str, filename: str) -> tuple[Path, Path]:
    return (
        ARCHIVE_EXTERNAL_BLOCKED_ROOT / topic_dir / filename,
        CURRENT_DEV_ROOT / topic_dir / filename,
    )


TOPIC_EVIDENCE = {
    "source_time_window": {
        "label": "Source Time Window",
        "paths": _evidence_path_candidates(
            "2026-03-02-source-time-window-smart-timestamp-plan",
            "08_wave20-time-semantics-sample-provenance-readback-2026-05-22.md",
        ),
    },
    "time_statistics": {
        "label": "Time Statistics",
        "paths": _evidence_path_candidates(
            "2026-03-05-time-statistics-remediation-plan",
            "10_wave20-time-semantics-sample-provenance-readback-2026-05-22.md",
        ),
    },
    "time_semantics_density": {
        "label": "Time Semantics Density",
        "paths": _evidence_path_candidates(
            "2026-03-14-time-semantics-density-merged-plan",
            "10_wave20-time-semantics-sample-provenance-readback-2026-05-22.md",
        ),
    },
}

COMMON_DOC_MARKERS = (
    "Wave20 Time Semantics Sample/Provenance Readback",
    "check_time_semantics_sample_provenance_readback.py",
    f"contract_version={CONTRACT_VERSION}",
    "status=passed_with_known_gaps",
    "deterministic_sample_readback_gate=true",
    "provenance_readback_gate=true",
    "production_data_semantic_chain_live_verified=false",
    "production_data_semantic_chain_live_validation_not_run",
    "closure_claim=false",
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


def _build_source_readiness() -> dict[str, Any]:
    module = _load_script_module(SOURCE_READINESS_SCRIPT)
    return module.build_check(include_doc_checks=False)


def _stage_by_name(source_readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(stage.get("name")): stage
        for stage in source_readiness.get("stages", [])
        if isinstance(stage, dict)
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _contains_marker(text: str, marker: str) -> bool:
    return marker.lower() in text.lower()


def _resolve_existing_relative(repo_root: Path, candidates: tuple[Path, ...]) -> Path:
    for relative_path in candidates:
        if (repo_root / relative_path).is_file():
            return relative_path
    return candidates[0]


def _topic_doc_checks(repo_root: Path) -> dict[str, Any]:
    topics: dict[str, Any] = {}
    failures: list[str] = []
    for key, topic in TOPIC_EVIDENCE.items():
        candidate_paths = tuple(Path(path) for path in topic["paths"])
        relative_path = _resolve_existing_relative(repo_root, candidate_paths)
        path = repo_root / relative_path
        exists = path.is_file()
        text = _read_text(path) if exists else ""
        required_markers = (*COMMON_DOC_MARKERS, str(topic["label"]))
        missing = [marker for marker in required_markers if not _contains_marker(text, marker)]
        passed = bool(exists and not missing)
        topics[key] = {
            "label": topic["label"],
            "path": relative_path.as_posix(),
            "candidate_paths": [path.as_posix() for path in candidate_paths],
            "exists": exists,
            "markers_checked": list(required_markers),
            "missing_markers": missing,
            "passed": passed,
        }
        if not passed:
            failures.append(f"doc.{key}.missing_wave20_evidence")
    return {
        "passed": not failures,
        "topics": topics,
        "failures": failures,
    }


def _evaluate_source_readiness(source_readiness: dict[str, Any]) -> dict[str, Any]:
    stages = _stage_by_name(source_readiness)
    source_stage = stages.get("deterministic_source_time_contract") or {}
    decision_stage = stages.get("decision_log_provenance") or {}
    sample_stage = stages.get("deterministic_sample_readback_chain") or {}
    production_stage = stages.get("production_data_semantic_chain") or {}
    sample_evidence = sample_stage.get("evidence") if isinstance(sample_stage.get("evidence"), dict) else {}
    live_gap_markers = sample_evidence.get("live_gap_markers_90d") or []
    remaining_live_gaps = source_readiness.get("remaining_live_gaps") or []

    sample_gap = sample_evidence.get("target_overlap_gap_90d")
    features_gap = sample_evidence.get("features_json_target_overlap_gap_90d")
    source_distribution = sample_evidence.get("effective_time_source_distribution_90d") or {}
    try:
        sample_gap_positive = float(sample_gap or 0.0) > 0.0
        feature_gap_matches = float(sample_gap or 0.0) == float(features_gap or 0.0)
    except (TypeError, ValueError):
        sample_gap_positive = False
        feature_gap_matches = False

    checks = {
        "source_time_contract_passed": source_stage.get("status") == "passed",
        "decision_log_provenance_passed": decision_stage.get("status") == "passed",
        "deterministic_sample_readback_passed": sample_stage.get("status") == "passed",
        "sample_prefers_source_time": sample_evidence.get("time_provenance") == "source_time",
        "sample_source_time_read_back": sample_evidence.get("source_time") == "2026-03-02T12:00:00Z",
        "sample_processed_time_read_back": sample_evidence.get("processed_time") == "2026-03-10T12:00:00Z",
        "document_effective_day_read_back": sample_evidence.get("document_effective_day") == "2026-03-02",
        "target_overlap_gap_read_back": sample_gap_positive,
        "features_json_gap_matches_row": feature_gap_matches,
        "source_time_distribution_read_back": (
            source_distribution.get("source_time_count") == 2
            and float(source_distribution.get("source_time_coverage") or 0.0) == 1.0
            and float(sample_evidence.get("source_time_coverage_90d") or 0.0) == 1.0
        ),
        "features_json_live_gap_retained": "production_freshness_probe_not_run" in live_gap_markers,
        "production_data_semantic_chain_live_verified": bool(
            source_readiness.get("checks", {}).get("production_data_semantic_chain_live_verified")
        ),
        "production_data_semantic_chain_live_gap_retained": bool(
            source_readiness.get("checks", {}).get("production_data_semantic_chain_live_gap_retained")
        ),
        "closure_claim_false": source_readiness.get("closure_claim") is False,
        "full_closure_not_allowed": source_readiness.get("full_closure_allowed") is False,
        "production_stage_ready_not_run": production_stage.get("status") == "ready_not_run",
        "production_live_gap_named": "production_data_semantic_chain_live_validation_not_run"
        in remaining_live_gaps,
    }

    expected_false = ("production_data_semantic_chain_live_verified",)
    missing = [
        key
        for key, passed in checks.items()
        if (key in expected_false and passed is not False)
        or (key not in expected_false and passed is not True)
    ]
    deterministic_gate = all(
        checks[key]
        for key in (
            "source_time_contract_passed",
            "deterministic_sample_readback_passed",
            "sample_prefers_source_time",
            "sample_source_time_read_back",
            "sample_processed_time_read_back",
            "document_effective_day_read_back",
            "target_overlap_gap_read_back",
        )
    )
    provenance_gate = all(
        checks[key]
        for key in (
            "decision_log_provenance_passed",
            "features_json_gap_matches_row",
            "source_time_distribution_read_back",
            "features_json_live_gap_retained",
        )
    )
    production_boundary_gate = (
        checks["production_data_semantic_chain_live_verified"] is False
        and checks["production_data_semantic_chain_live_gap_retained"] is True
        and checks["closure_claim_false"] is True
        and checks["full_closure_not_allowed"] is True
        and checks["production_stage_ready_not_run"] is True
        and checks["production_live_gap_named"] is True
    )
    return {
        "passed": not missing,
        "checks": checks,
        "gate_summary": {
            "deterministic_sample_readback_gate": deterministic_gate,
            "provenance_readback_gate": provenance_gate,
            "production_boundary_gate": production_boundary_gate,
        },
        "missing_checks": missing,
        "sample_evidence": sample_evidence,
        "remaining_live_gaps": remaining_live_gaps,
        "readiness_boundaries": source_readiness.get("readiness_boundaries") or {},
    }


def build_check(
    *,
    repo_root: Path | str | None = None,
    source_readiness: dict[str, Any] | None = None,
    include_doc_checks: bool = True,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()
    readiness = source_readiness if source_readiness is not None else _build_source_readiness()
    source_result = _evaluate_source_readiness(readiness)
    doc_result = _topic_doc_checks(root) if include_doc_checks else {
        "passed": True,
        "topics": {},
        "failures": [],
    }

    failures = [
        *(f"source_readiness.{name}" for name in source_result["missing_checks"]),
        *doc_result["failures"],
    ]
    status = "failed" if failures else "passed_with_known_gaps"
    gate_summary = source_result["gate_summary"]

    return {
        "contract_version": CONTRACT_VERSION,
        "scope": SCOPE,
        "status": status,
        "closure_claim": False,
        "full_closure_allowed": False,
        "production_data_semantic_chain_live_verified": False,
        "protected_shared_indexes": list(PROTECTED_SHARED_INDEXES),
        "checks": {
            "deterministic_sample_readback_gate": gate_summary["deterministic_sample_readback_gate"],
            "provenance_readback_gate": gate_summary["provenance_readback_gate"],
            "production_boundary_gate": gate_summary["production_boundary_gate"],
            "wave20_topic_evidence_gate": doc_result["passed"],
        },
        "readiness_boundaries": source_result["readiness_boundaries"],
        "sample_evidence": source_result["sample_evidence"],
        "topic_evidence": doc_result["topics"],
        "remaining_live_gaps": source_result["remaining_live_gaps"],
        "failures": sorted(set(failures)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check Wave20 time-semantics deterministic sample/provenance readback."
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to scan.")
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    parser.add_argument("--output", type=Path, default=None, help="Write full JSON output.")
    parser.add_argument(
        "--skip-doc-checks",
        action="store_true",
        help="Only evaluate runtime sample/provenance readback, not Wave20 evidence docs.",
    )
    args = parser.parse_args(argv)

    result = build_check(
        repo_root=Path(args.repo_root),
        include_doc_checks=not args.skip_doc_checks,
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
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"deterministic_sample_readback_gate="
            f"{str(result['checks']['deterministic_sample_readback_gate']).lower()} "
            f"provenance_readback_gate={str(result['checks']['provenance_readback_gate']).lower()} "
            f"production_data_semantic_chain_live_verified="
            f"{str(result['production_data_semantic_chain_live_verified']).lower()} "
            f"wave20_topic_evidence_gate="
            f"{str(result['checks']['wave20_topic_evidence_gate']).lower()} "
            f"closure_claim={str(result['closure_claim']).lower()} "
            f"remaining_live_gaps={len(result['remaining_live_gaps'])}"
        )
        if result["status"] == "failed":
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))

    return 0 if result["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
