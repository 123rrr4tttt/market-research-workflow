#!/usr/bin/env python3
"""Wave29 repo-local blocker alignment gate for the single-URL ingest topic."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "single_url.wave29_blocker_alignment.v1"
TOPIC_SLUG = "2026-03-02-single-url-first-ingest-allocation-plan"
TOPIC_DIR = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED") / TOPIC_SLUG
WAVE29_DOC = TOPIC_DIR / "10_wave29-ingest-blocker-alignment-2026-05-23.md"
ARCHIVE_RECOMMENDATION = "ARCHIVE_EXTERNAL_BLOCKED"


@dataclass(frozen=True)
class Anchor:
    path: Path
    tokens: tuple[str, ...]


BLOCKER_ANCHORS: dict[str, tuple[Anchor, ...]] = {
    "broader_fetch_router": (
        Anchor(
            Path("main/backend/app/services/ingest/frontdoor_router_contract.py"),
            (
                "ingest.frontdoor_fetch_router.v1",
                "TRI_STATE_STATUSES",
                "needs_browser_runtime",
                "public_browser_replay_performed",
            ),
        ),
        Anchor(
            Path("main/backend/app/services/ingest/url_pool.py"),
            (
                "_frontdoor_route_profile_for_url",
                "_build_frontdoor_status_projection",
                "frontdoor_status_summary",
                "prefer_crawler_first",
            ),
        ),
        Anchor(
            Path("main/backend/tests/unit/test_frontdoor_fetch_router_contract_unittest.py"),
            (
                "test_high_js_profile_marks_needs_browser_without_public_replay",
                "test_frontdoor_status_projection_preserves_router_boundary",
                "needs_browser_runtime",
            ),
        ),
    ),
    "official_api_adapter": (
        Anchor(
            Path("main/backend/app/services/source_library/adapters/official_access.py"),
            (
                "official_api_feed",
                "html_search_fallback",
                "_ARXIV_RESULT_CACHE",
                "official_access.api adapter is a placeholder",
            ),
        ),
        Anchor(
            Path("main/backend/app/services/resource_pool/unified_search.py"),
            (
                "policy.category == \"api_preferred\"",
                "handle_official_access_api",
                "official_api_search",
                "tool\": \"official_access.api\"",
            ),
        ),
        Anchor(
            Path("main/backend/tests/unit/test_source_library_official_access_adapter_unittest.py"),
            (
                "test_arxiv_official_api_returns_candidate_urls",
                "test_arxiv_official_api_falls_back_to_html_search_when_feed_fails",
                "test_arxiv_official_api_reuses_cached_candidates_after_rate_limit",
                "test_unknown_provider_stays_placeholder",
            ),
        ),
        Anchor(
            Path("main/backend/tests/unit/test_resource_pool_unified_search_unittest.py"),
            (
                "test_unified_search_policy_skips_api_preferred_sites",
                "test_unified_search_payload_reads_official_access_site_entries",
            ),
        ),
    ),
    "dashboard_tri_state": (
        Anchor(
            Path("main/backend/app/api/dashboard.py"),
            (
                "_FRONTDOOR_TRI_STATE_STATUSES",
                "_build_frontdoor_tri_state_summary",
                "frontdoor_tri_state",
                "frontdoor_status_summary.dashboard_status_counts",
            ),
        ),
        Anchor(
            Path("main/frontend-modern/src/lib/types.ts"),
            (
                "frontdoor_tri_state",
                "degraded_success",
                "failed",
            ),
        ),
        Anchor(
            Path("main/frontend-modern/src/pages/DashboardPage.tsx"),
            (
                "FrontdoorTriStateStatus",
                "frontdoorTriStateChipClass",
                "dashboardPage.section.frontdoorTriState",
                "triStateCounts",
            ),
        ),
        Anchor(
            Path("main/frontend-modern/src/app/platform/i18n/catalog.ts"),
            (
                "section.frontdoorTriState",
                "triState.degraded_success",
                "Frontdoor ingest status",
            ),
        ),
        Anchor(
            Path("main/backend/tests/core_business/test_admin_dashboard_process_core_contract.py"),
            (
                "frontdoor_tri_state",
                "degraded_success",
                "frontdoor_status_summary",
            ),
        ),
    ),
}

WAVE29_DOC_TOKENS = (
    "wave29_repo_local_blockers_closed_external_blocked_candidate",
    "broader_fetch_router",
    "official_api_adapter",
    "dashboard_tri_state",
    "Archive recommendation",
    "ARCHIVE_EXTERNAL_BLOCKED",
)

EXTERNAL_RETAINED_BOUNDARIES = (
    "public browser/runtime replay across high-JS domains was not run in this worker",
    "non-arXiv official-provider catalog, credentials, and live API quota behavior remain outside this repo-local gate",
    "configured-service single-URL canary and production 24h metrics readback remain operations/live evidence",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _anchor_result(root: Path, anchor: Anchor) -> dict[str, Any]:
    path = root / anchor.path
    text = _read_text(path)
    missing = [token for token in anchor.tokens if token not in text]
    return {
        "path": str(anchor.path),
        "exists": path.is_file(),
        "tokens_checked": list(anchor.tokens),
        "missing_tokens": missing,
        "passed": path.is_file() and not missing,
    }


def _blocker_result(root: Path, code: str, anchors: tuple[Anchor, ...]) -> dict[str, Any]:
    anchor_results = [_anchor_result(root, anchor) for anchor in anchors]
    passed = all(item["passed"] for item in anchor_results)
    return {
        "code": code,
        "repo_local_status": "closed_repo_local" if passed else "retained_repo_local_missing_evidence",
        "repo_local_blocker_open": not passed,
        "anchors": anchor_results,
    }


def build_report(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    blockers = [
        _blocker_result(root, code, anchors)
        for code, anchors in BLOCKER_ANCHORS.items()
    ]
    doc_anchor = _anchor_result(root, Anchor(WAVE29_DOC, WAVE29_DOC_TOKENS))
    repo_local_blockers_open = any(item["repo_local_blocker_open"] for item in blockers)
    archive_ready = not repo_local_blockers_open
    report: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "topic_slug": TOPIC_SLUG,
        "status": "passed" if archive_ready and doc_anchor["passed"] else "failed",
        "decision_marker": "wave29_repo_local_blockers_closed_external_blocked_candidate",
        "repo_local_blockers_open": repo_local_blockers_open,
        "blockers": blockers,
        "wave29_doc": doc_anchor,
        "external_retained_boundaries": list(EXTERNAL_RETAINED_BOUNDARIES),
        "archive_recommendation": ARCHIVE_RECOMMENDATION if archive_ready else "CURRENT_DEV",
        "shared_index_updates_required": archive_ready,
        "shared_indexes_edited_by_this_gate": False,
    }
    report["validation_errors"] = validate_report(report)
    report["status"] = "passed" if not report["validation_errors"] else "failed"
    return report


def validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    if report.get("topic_slug") != TOPIC_SLUG:
        errors.append("topic_slug mismatch")
    blockers = report.get("blockers") if isinstance(report.get("blockers"), list) else []
    if set(item.get("code") for item in blockers if isinstance(item, dict)) != set(BLOCKER_ANCHORS):
        errors.append("blocker set mismatch")
    for blocker in blockers:
        if not isinstance(blocker, dict):
            errors.append("blocker must be an object")
            continue
        if blocker.get("repo_local_status") != "closed_repo_local":
            errors.append(f"{blocker.get('code')}: repo-local status must be closed_repo_local")
        anchors = blocker.get("anchors") if isinstance(blocker.get("anchors"), list) else []
        if not anchors:
            errors.append(f"{blocker.get('code')}: anchors missing")
        for anchor in anchors:
            if isinstance(anchor, dict) and anchor.get("passed") is not True:
                errors.append(f"{blocker.get('code')}: anchor failed: {anchor.get('path')}")
    if report.get("repo_local_blockers_open") is not False:
        errors.append("repo_local_blockers_open must be false")
    if report.get("archive_recommendation") != ARCHIVE_RECOMMENDATION:
        errors.append(f"archive_recommendation must be {ARCHIVE_RECOMMENDATION}")
    if report.get("shared_index_updates_required") is not True:
        errors.append("shared_index_updates_required must be true for archive movement")
    if report.get("shared_indexes_edited_by_this_gate") is not False:
        errors.append("shared_indexes_edited_by_this_gate must be false")
    if not isinstance(report.get("external_retained_boundaries"), list) or len(report["external_retained_boundaries"]) < 3:
        errors.append("external_retained_boundaries must retain browser/API/live canary boundaries")
    wave29_doc = report.get("wave29_doc") if isinstance(report.get("wave29_doc"), dict) else {}
    if wave29_doc.get("passed") is not True:
        errors.append(f"Wave29 doc check failed: {wave29_doc.get('missing_tokens')}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave29 single-URL blocker alignment")
    parser.add_argument("--json", action="store_true", help="print full JSON report")
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"{report['status'].upper()} {CONTRACT_VERSION} "
            f"repo_local_blockers_open={str(report['repo_local_blockers_open']).lower()} "
            f"archive_recommendation={report['archive_recommendation']} "
            f"shared_indexes_edited=false"
        )
        if report["status"] != "passed":
            print(json.dumps(report["validation_errors"], ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
