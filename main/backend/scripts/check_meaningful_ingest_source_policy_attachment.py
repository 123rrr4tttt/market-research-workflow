#!/usr/bin/env python3
"""Wave29 source-policy attachment gate for Meaningful Ingest Guardrails."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
SCRIPT_DIR = BACKEND_ROOT / "scripts"
for path in (BACKEND_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from check_crawler_policy_matrix import build_check as build_crawler_policy_matrix_check  # noqa: E402
from check_ingest_canary_24h_metrics_artifact import run_check as run_24h_artifact_check  # noqa: E402
from check_ingest_canary_metrics_readback import run_check as run_metrics_readback_check  # noqa: E402


CONTRACT_VERSION = "meaningful_ingest.source_policy_attachment.v1"
TOPIC_ID = "2026-03-02-meaningful-ingest-guardrails-plan"
TOPIC_DIR = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED") / TOPIC_ID
CRAWLER_POLICY_TOPIC_ID = "2026-03-07-crawler-source-expansion"
CRAWLER_POLICY_DOC = Path(
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
    "2026-03-07-crawler-source-expansion/2026-05-22-wave7-crawler-policy-matrix.md"
)
DECISION_DOC = TOPIC_DIR / "10_wave29-source-policy-tuning-attachment-decision-2026-05-23.md"
DECISION_MARKER = "wave29_source_policy_tuning_attachment_reclassified_external"

PROTECTED_SHARED_INDEXES = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
)

EXTERNAL_BLOCKERS = (
    "live_guardrail_rollout_canary_not_run",
    "production_24h_rejection_rate_readback_not_run",
    "production_24h_inserted_valid_ratio_readback_not_run",
    "production_guardrail_rollout_counts_readback_not_run",
    "operations_strict_gate_promotion_decision_not_recorded",
    "live_canary_feedback_source_policy_tuning_not_available",
)


@dataclass(frozen=True)
class Anchor:
    path: Path
    tokens: tuple[str, ...]


ANCHORS: dict[str, Anchor] = {
    "wave22_decision": Anchor(
        TOPIC_DIR / "08_wave22-external-blocked-migration-decision-2026-05-22.md",
        (
            "wave22_retain_current_dev_policy_tuning_after_live_canary",
            "source-policy tuning after live canary evidence",
            "implemented or split into a successor topic",
            "retained_partial",
        ),
    ),
    "wave27_decision": Anchor(
        TOPIC_DIR / "09_wave27-ingest-canary-closure-readiness-2026-05-23.md",
        (
            "wave27_retain_current_dev_policy_tuning_successor_not_split",
            "source-policy tuning remains attached",
            "not been implemented or split into a successor topic",
            "closure_claim=false",
        ),
    ),
    "wave29_decision": Anchor(
        DECISION_DOC,
        (
            DECISION_MARKER,
            "owned_by_crawler_source_policy_matrix",
            "no_successor_topic_created",
            "source_policy_attachment_resolved_repo_local",
            "live_canary_feedback_required",
            "external_blocked_candidate",
            "do_not_edit_shared_indexes",
            "Recommended location: `ARCHIVE_EXTERNAL_BLOCKED`",
        ),
    ),
    "crawler_policy_matrix_doc": Anchor(
        CRAWLER_POLICY_DOC,
        (
            "A4 status in this branch: `closed`",
            "source_policy_action",
            "`allow`",
            "`downgrade`",
            "`block`",
            "meaningful_gate.py",
        ),
    ),
    "crawler_policy_matrix_checker": Anchor(
        Path("main/backend/scripts/check_crawler_policy_matrix.py"),
        (
            "crawler_policy_matrix.v1",
            "source_candidate_trust",
            "ingest_meaningful_gate",
            "doc_decision_coverage",
        ),
    ),
    "source_candidate_trust": Anchor(
        Path("main/backend/app/services/source_library/source_candidate_trust.py"),
        (
            "SOURCE_POLICY_ACTIONS",
            "source_policy_action",
            "source_policy_reason",
            "medium_trust_candidate_requires_review_before_bulk_ingest",
            "url_quality_gate",
        ),
    ),
    "meaningful_gate": Anchor(
        Path("main/backend/app/services/ingest/meaningful_gate.py"),
        (
            "def url_policy_check",
            "def content_quality_check",
            "ingest_low_value_domains",
            "ingest_low_value_path_keywords",
            "ingest_shell_signatures",
        ),
    ),
}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _anchor_result(root: Path, key: str, anchor: Anchor) -> dict[str, Any]:
    path = root / anchor.path
    exists = path.is_file()
    text = _read_text(path) if exists else ""
    missing_tokens = [token for token in anchor.tokens if token not in text]
    return {
        "key": key,
        "path": str(anchor.path),
        "exists": exists,
        "tokens_checked": list(anchor.tokens),
        "missing_tokens": missing_tokens,
        "passed": bool(exists and not missing_tokens),
    }


def _summarize_status(result: Mapping[str, Any]) -> dict[str, Any]:
    token_results = result.get("token_results") if isinstance(result.get("token_results"), list) else []
    runtime_results = result.get("runtime_results") if isinstance(result.get("runtime_results"), list) else []
    return {
        "contract_version": result.get("contract_version"),
        "status": result.get("status"),
        "token_results_passed": sum(1 for item in token_results if isinstance(item, Mapping) and item.get("passed")),
        "token_results_total": len(token_results),
        "runtime_results_passed": sum(1 for item in runtime_results if isinstance(item, Mapping) and item.get("passed")),
        "runtime_results_total": len(runtime_results),
    }


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT.resolve()
    anchors = {key: _anchor_result(root, key, anchor) for key, anchor in ANCHORS.items()}

    crawler_policy = build_crawler_policy_matrix_check(root)
    metrics_readback = run_metrics_readback_check()
    metrics_24h = run_24h_artifact_check()

    repo_local_blockers: list[dict[str, str]] = []
    errors: list[str] = []
    errors.extend(
        f"{result['key']}: missing {result['path']}"
        for result in anchors.values()
        if not result["exists"]
    )
    errors.extend(
        f"{result['key']}: missing tokens {result['missing_tokens']}"
        for result in anchors.values()
        if result["exists"] and result["missing_tokens"]
    )
    if not bool((crawler_policy.get("validation") or {}).get("passed")):
        errors.append("crawler source policy matrix gate must pass")
    if metrics_readback.get("status") != "passed":
        errors.append("canary metrics readback gate must pass")
    if metrics_24h.get("status") != "passed":
        errors.append("canary 24h metrics artifact gate must pass")

    source_policy_resolution = {
        "status": "resolved_repo_local_attachment",
        "successor_topic_created": False,
        "owned_elsewhere": True,
        "owner_topic_id": CRAWLER_POLICY_TOPIC_ID,
        "owner_policy_doc": str(CRAWLER_POLICY_DOC),
        "owner_gate": "main/backend/scripts/check_crawler_policy_matrix.py",
        "decision_field": "source_policy_action",
        "decision_values": ["allow", "downgrade", "block"],
        "meaningful_ingest_downstream_gate": "main/backend/app/services/ingest/meaningful_gate.py",
        "live_tuning_requires_canary_feedback": True,
    }
    decision = {
        "status": "external_blocked_candidate" if not errors else "failed",
        "archive_eligible": not errors,
        "recommended_location": "ARCHIVE_EXTERNAL_BLOCKED",
        "move_performed": False,
        "shared_index_updates_performed": False,
        "shared_index_updates_required_by_supervisor": True,
        "reason": (
            "repo-local source-policy attachment is resolved by existing crawler source-policy ownership; "
            "remaining tuning depends on live canary feedback"
        ),
    }

    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if not errors else "failed",
        "topic_id": TOPIC_ID,
        "topic_dir": str(TOPIC_DIR),
        "decision_doc": str(DECISION_DOC),
        "decision_marker": DECISION_MARKER,
        "anchors": anchors,
        "source_policy_resolution": source_policy_resolution,
        "crawler_policy_matrix_check": {
            "contract_version": crawler_policy.get("contract_version"),
            "passed": bool((crawler_policy.get("validation") or {}).get("passed")),
            "policy_actions": crawler_policy.get("policy_actions"),
            "doc_decision_coverage": crawler_policy.get("doc_decision_coverage"),
        },
        "canary_metrics_readback_check": _summarize_status(metrics_readback),
        "canary_24h_metrics_artifact_check": _summarize_status(metrics_24h),
        "repo_local_blockers": repo_local_blockers,
        "external_blockers": [{"id": blocker, "classification": "external_live_operational"} for blocker in EXTERNAL_BLOCKERS],
        "decision": decision,
        "protected_shared_indexes": list(PROTECTED_SHARED_INDEXES),
        "validation": {
            "passed": not errors,
            "errors": errors,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave29 meaningful-ingest source-policy attachment decision.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="print JSON output")
    args = parser.parse_args(argv)

    result = build_check(args.repo_root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{result['status'].upper()} {CONTRACT_VERSION} "
            f"topic={result['topic_id']} "
            f"source_policy={result['source_policy_resolution']['status']} "
            f"archive_recommendation={result['decision']['recommended_location']} "
            f"move_performed={str(result['decision']['move_performed']).lower()} "
            f"shared_index_updates_performed={str(result['decision']['shared_index_updates_performed']).lower()}"
        )
        if result["status"] != "passed":
            print(json.dumps(result["validation"]["errors"], ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
