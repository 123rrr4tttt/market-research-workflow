#!/usr/bin/env python3
"""Check the current authority for the three historical ingest-canary topics.

The Wave27 checker described topics while they were still in CURRENT_DEV.
Current authority is Wave51/56/57 under ARCHIVE_EXTERNAL_BLOCKED: one parent
assessment is a non-target wrapper and two successor targets remain externally
blocked. Deleted runtime artifacts are deliberately outside this status gate.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parents[0]
REPO_ROOT = BACKEND_ROOT.parents[1]

CONTRACT_VERSION = "ingest.canary_closure_readiness.v2"
PLANS_ROOT = Path("development/latest-dev-docs/development-plans")
CURRENT_DEV_ROOT = PLANS_ROOT / "CURRENT_DEV"
CURRENT_DEV_INDEX = CURRENT_DEV_ROOT / "INDEX.md"
AUTHORITY_ROOT = PLANS_ROOT / "ARCHIVE_EXTERNAL_BLOCKED"
AUTHORITY_INDEX = AUTHORITY_ROOT / "INDEX.md"


@dataclass(frozen=True)
class TopicSpec:
    slug: str
    title: str
    current_status: str
    current_wave: int
    current_doc: Path
    historical_wave27_doc: Path
    target_kind: str
    required_tokens: tuple[str, ...]
    remaining_external_conditions: tuple[str, ...]


TOPICS = (
    TopicSpec(
        slug="2026-03-02-ingest-platformization-assessment",
        title="Ingest Platformization Assessment",
        current_status="non_target_ingest_platformization_assessment_wrapper",
        current_wave=51,
        current_doc=Path("10_wave51-non-target-assessment-wrapper-reclassification-2026-05-23.md"),
        historical_wave27_doc=Path("08_wave27-ingest-canary-closure-readiness-2026-05-23.md"),
        target_kind="non_target_parent_wrapper",
        required_tokens=(
            "Status: `non_target_ingest_platformization_assessment_wrapper`",
            "Previous review status: `external_blocked`",
            "remove this parent assessment from the external-blocked target set",
        ),
        remaining_external_conditions=(),
    ),
    TopicSpec(
        slug="2026-03-02-meaningful-ingest-guardrails-plan",
        title="Meaningful Ingest Guardrails Plan",
        current_status="external_blocked",
        current_wave=56,
        current_doc=Path("13_wave56-strict-promotion-final-gate-2026-05-24.md"),
        historical_wave27_doc=Path("09_wave27-ingest-canary-closure-readiness-2026-05-23.md"),
        target_kind="external_blocked_successor",
        required_tokens=(
            "strict_promotion_final_gate_landed_external_blocker_minimized",
            "production_24h_metrics_satisfied=false",
            "strict_gate_promotion_satisfied=false",
            "closure_claim=false",
        ),
        remaining_external_conditions=(
            "production 24h guardrail metrics",
            "operations strict-gate promotion decision",
        ),
    ),
    TopicSpec(
        slug="2026-03-02-single-url-first-ingest-allocation-plan",
        title="Single URL First Ingest Allocation Plan",
        current_status="external_blocked",
        current_wave=57,
        current_doc=Path("13_wave57-single-url-external-blocker-closure-2026-05-24.md"),
        historical_wave27_doc=Path("09_wave27-ingest-canary-closure-readiness-2026-05-23.md"),
        target_kind="external_blocked_successor",
        required_tokens=(
            "single_url_external_blocker_repo_public_reduced",
            "production_24h_metrics_satisfied=false",
            "provider_credentials_beyond_crossref_open=true",
            "`closure_claim=false`",
        ),
        remaining_external_conditions=(
            "X public high-JS auth or anti-bot boundary",
            "production 24h readback",
            "operations strict-gate promotion decision",
            "credentialed provider quota behavior beyond public Crossref",
        ),
    ),
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _topic_result(topic: TopicSpec, *, current_dev_index_text: str, authority_index_text: str) -> dict[str, Any]:
    topic_dir = AUTHORITY_ROOT / topic.slug
    current_doc = topic_dir / topic.current_doc
    historical_doc = topic_dir / topic.historical_wave27_doc
    current_text = _read_text(REPO_ROOT / current_doc)
    missing_tokens = [token for token in topic.required_tokens if token not in current_text]
    current_dev_row = next((line for line in current_dev_index_text.splitlines() if topic.slug in line), "")
    authority_index_row = next((line for line in authority_index_text.splitlines() if topic.slug in line), "")
    return {
        "slug": topic.slug,
        "title": topic.title,
        "current_status": topic.current_status,
        "current_wave": topic.current_wave,
        "target_kind": topic.target_kind,
        "authority_directory": topic_dir.as_posix(),
        "authority_directory_exists": (REPO_ROOT / topic_dir).is_dir(),
        "current_authority_doc": current_doc.as_posix(),
        "current_authority_doc_exists": (REPO_ROOT / current_doc).is_file(),
        "required_authority_tokens": list(topic.required_tokens),
        "missing_authority_tokens": missing_tokens,
        "authority_index_row": authority_index_row,
        "authority_index_points_to_current_doc": topic.current_doc.as_posix() in authority_index_row,
        "current_dev_directory_exists": (REPO_ROOT / CURRENT_DEV_ROOT / topic.slug).is_dir(),
        "current_dev_navigation_row": current_dev_row,
        "current_dev_navigation_row_present": bool(current_dev_row),
        "current_dev_is_authority": False,
        "remaining_external_conditions": list(topic.remaining_external_conditions),
        "historical_wave27": {
            "path": historical_doc.as_posix(),
            "exists": (REPO_ROOT / historical_doc).is_file(),
            "classification": "historical_pre_wave51_56_57_snapshot",
            "is_current_authority": False,
        },
    }


def validate_report(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    authority = report.get("authority") if isinstance(report.get("authority"), Mapping) else {}
    if authority.get("root") != AUTHORITY_ROOT.as_posix():
        errors.append("authority root mismatch")
    if authority.get("deleted_json_or_jsonl_used_as_evidence") is not False:
        errors.append("deleted JSON or JSONL must not be used as current evidence")
    topics = report.get("topics") if isinstance(report.get("topics"), list) else []
    if len(topics) != len(TOPICS):
        errors.append(f"expected {len(TOPICS)} topic results, got {len(topics)}")
    for topic in topics:
        if not isinstance(topic, Mapping):
            errors.append("topic result must be an object")
            continue
        slug = str(topic.get("slug") or "<missing>")
        if topic.get("authority_directory_exists") is not True:
            errors.append(f"{slug}: authority directory must exist")
        if topic.get("current_authority_doc_exists") is not True:
            errors.append(f"{slug}: current authority document must exist")
        if topic.get("missing_authority_tokens") != []:
            errors.append(f"{slug}: current authority tokens missing")
        if topic.get("authority_index_points_to_current_doc") is not True:
            errors.append(f"{slug}: authority index must point to current document")
        if topic.get("current_dev_directory_exists") is not False:
            errors.append(f"{slug}: topic must remain migrated out of CURRENT_DEV")
        if topic.get("current_dev_navigation_row_present") is not True:
            errors.append(f"{slug}: CURRENT_DEV compatibility navigation row missing")
        if topic.get("current_dev_is_authority") is not False:
            errors.append(f"{slug}: CURRENT_DEV must not be treated as authority")
        history = topic.get("historical_wave27") if isinstance(topic.get("historical_wave27"), Mapping) else {}
        if history.get("is_current_authority") is not False:
            errors.append(f"{slug}: Wave27 history must not be current authority")
        status = topic.get("current_status")
        if topic.get("target_kind") == "non_target_parent_wrapper":
            if status != "non_target_ingest_platformization_assessment_wrapper":
                errors.append(f"{slug}: non-target wrapper status mismatch")
            if topic.get("remaining_external_conditions") != []:
                errors.append(f"{slug}: parent wrapper must delegate rather than duplicate external conditions")
        elif topic.get("target_kind") == "external_blocked_successor":
            if status != "external_blocked":
                errors.append(f"{slug}: successor must remain external_blocked")
            if not topic.get("remaining_external_conditions"):
                errors.append(f"{slug}: external conditions must remain explicit")
    return errors


def run_check(*, write_output: Path | None = None) -> dict[str, Any]:
    current_dev_index_text = _read_text(REPO_ROOT / CURRENT_DEV_INDEX)
    authority_index_text = _read_text(REPO_ROOT / AUTHORITY_INDEX)
    topics = [
        _topic_result(
            topic,
            current_dev_index_text=current_dev_index_text,
            authority_index_text=authority_index_text,
        )
        for topic in TOPICS
    ]
    report: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "status": "passed",
        "scope": [topic.slug for topic in TOPICS],
        "authority": {
            "root": AUTHORITY_ROOT.as_posix(),
            "index": AUTHORITY_INDEX.as_posix(),
            "current_waves": [51, 56, 57],
            "wave27_classification": "history_only",
            "current_dev_classification": "navigation_compatibility_only",
            "deleted_json_or_jsonl_used_as_evidence": False,
        },
        "external_blocked_targets": [
            topic["slug"] for topic in topics if topic["current_status"] == "external_blocked"
        ],
        "non_target_wrappers": [
            topic["slug"] for topic in topics if topic["target_kind"] == "non_target_parent_wrapper"
        ],
        "topics": topics,
    }
    errors = validate_report(report)
    report["validation_errors"] = errors
    report["status"] = "passed" if not errors else "failed"
    if write_output is not None:
        output = write_output if write_output.is_absolute() else REPO_ROOT / write_output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check current ingest topic authority after Wave51/56/57.")
    parser.add_argument("--json", action="store_true", help="print JSON output")
    parser.add_argument("--write-output", type=Path, default=None, help="optional JSON report path")
    args = parser.parse_args(argv)
    report = run_check(write_output=args.write_output)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status'].upper()} {CONTRACT_VERSION} "
            f"external_blocked_targets={len(report['external_blocked_targets'])} "
            f"non_target_wrappers={len(report['non_target_wrappers'])}"
        )
        if report["status"] != "passed":
            print(json.dumps(report["validation_errors"], ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
