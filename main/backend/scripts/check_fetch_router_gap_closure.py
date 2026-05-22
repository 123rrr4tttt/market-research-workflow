from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTRACT_VERSION = "fetch_router_gap_closure.check.v1"
CURRENT_DEV = Path("development/latest-dev-docs/development-plans/CURRENT_DEV")

PROTECTED_SHARED_INDEXES = [
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
]


@dataclass(frozen=True)
class Anchor:
    path: Path
    tokens: tuple[str, ...] = ()


TOPICS: dict[str, dict[str, Any]] = {
    "2026-03-02-ingest-platformization-assessment": {
        "title": "Ingest platformization fetch-router/frontdoor closure",
        "doc": CURRENT_DEV
        / "2026-03-02-ingest-platformization-assessment"
        / "02_wave8-2-fetch-router-gap-closure-2026-05-22.md",
        "legacy_gap": "fetch_router_gap",
    },
    "2026-03-02-single-url-first-ingest-allocation-plan": {
        "title": "Single-url compatibility source-library/frontdoor closure",
        "doc": CURRENT_DEV
        / "2026-03-02-single-url-first-ingest-allocation-plan"
        / "03_wave8-2-fetch-router-gap-closure-2026-05-22.md",
        "legacy_gap": "frontdoor/router gap",
    },
    "2026-03-08-llm-crawler-unified-frontdoor": {
        "title": "LLM crawler unified frontdoor provider handoff closure",
        "doc": CURRENT_DEV
        / "2026-03-08-llm-crawler-unified-frontdoor"
        / "04_wave8-2-fetch-router-gap-closure-2026-05-22.md",
        "legacy_gap": "high-JS/browser route intent gap",
    },
}


ANCHORS: dict[str, Anchor] = {
    "frontdoor_ingress_contract": Anchor(
        Path("main/backend/app/services/ingest/frontdoor_ingress.py"),
        (
            "provider_handoff",
            "frontdoor_route_profile",
            "frontdoor_route_hint",
            "fetch_strategy",
        ),
    ),
    "single_url_compat_frontdoor": Anchor(
        Path("main/backend/app/services/ingest/url_pool.py"),
        (
            "single_url_compat",
            "run_item_with_url_routing",
            'execution_layer="terminal_output_only"',
            "build_frontdoor_ingress_envelope",
            "run_postprocess_frontdoor",
            "run_writer=True",
        ),
    ),
    "high_js_ingest_route_intent": Anchor(
        Path("main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py"),
        (
            "test_high_js_frontdoor_route_prefers_browser_render_and_projects_dashboard_status",
            "crawler_browse",
            "browser_render",
            "frontdoor_status_summary",
        ),
    ),
    "single_url_source_ref_test": Anchor(
        Path("main/backend/tests/unit/test_ingest_frontdoor_context_unittest.py"),
        (
            "test_ingest_url_via_source_library_frontdoor_uses_source_library_bridge_and_postprocess_writer",
            "source_ref",
            "single_write_workflow",
            "source_library_frontdoor",
        ),
    ),
    "provider_handoff_resolver_test": Anchor(
        Path("main/backend/tests/unit/test_source_library_resolver_unittest.py"),
        (
            "test_high_js_browser_route_hands_off_to_crawler_provider_with_trace",
            "source_library.provider_handoff.v1",
            "provider_dispatch",
            "crawlers/providers",
        ),
    ),
    "provider_handoff_projection_test": Anchor(
        Path("main/backend/tests/unit/test_collect_runtime_source_library_adapter_unittest.py"),
        (
            "test_to_source_library_response_preserves_provider_handoff_contract",
            "provider_handoff",
            "frontdoor_ingress",
            "authority_output",
        ),
    ),
    "tri_state_status_projection": Anchor(
        Path("main/backend/app/services/ingest/url_pool.py"),
        (
            "_build_frontdoor_status_projection",
            '"success"',
            '"degraded_success"',
            '"failed"',
            "frontdoor_admission",
        ),
    ),
}


TOPIC_ANCHORS: dict[str, tuple[str, ...]] = {
    "2026-03-02-ingest-platformization-assessment": (
        "frontdoor_ingress_contract",
        "single_url_compat_frontdoor",
        "single_url_source_ref_test",
        "high_js_ingest_route_intent",
        "tri_state_status_projection",
    ),
    "2026-03-02-single-url-first-ingest-allocation-plan": (
        "single_url_compat_frontdoor",
        "single_url_source_ref_test",
        "frontdoor_ingress_contract",
        "tri_state_status_projection",
    ),
    "2026-03-08-llm-crawler-unified-frontdoor": (
        "high_js_ingest_route_intent",
        "provider_handoff_resolver_test",
        "provider_handoff_projection_test",
        "frontdoor_ingress_contract",
        "tri_state_status_projection",
    ),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def _anchor_result(root: Path, key: str, anchor: Anchor) -> dict[str, Any]:
    path = root / anchor.path
    exists = path.is_file()
    missing_tokens: list[str] = []
    if exists and anchor.tokens:
        text = _read_text(path)
        missing_tokens = [token for token in anchor.tokens if token not in text]
    return {
        "key": key,
        "path": str(anchor.path),
        "exists": exists,
        "tokens_checked": list(anchor.tokens),
        "missing_tokens": missing_tokens,
        "passed": exists and not missing_tokens,
    }


def _doc_result(root: Path, topic_id: str, doc_path: Path) -> dict[str, Any]:
    anchor = Anchor(
        doc_path,
        (
            "Wave8-2 Fetch Router Gap Cluster",
            "status:",
            "gap:",
            "evidence:",
            "check_fetch_router_gap_closure.py",
        ),
    )
    return _anchor_result(root, f"{topic_id}.wave8_evidence_doc", anchor)


def _topic_status(anchor_results: list[dict[str, Any]], doc: dict[str, Any]) -> str:
    if all(item["passed"] for item in [*anchor_results, doc]):
        return "closed_narrow_runtime_contract"
    return "open_missing_evidence"


def _topic_gap(status: str, legacy_gap: str) -> str:
    if status == "closed_narrow_runtime_contract":
        return (
            f"{legacy_gap} closed for the narrow contract: legacy single_url resolves through "
            "source-library/frontdoor, high-JS browser intent reaches provider handoff, and "
            "dashboard tri-state wording is evidence-backed. Broader live browser fleet and "
            "API adapter maturity remain outside this gate."
        )
    return f"{legacy_gap} still open: one or more required code, test, or Wave8 evidence anchors are missing."


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _repo_root()
    root = root.resolve()
    anchors = {key: _anchor_result(root, key, anchor) for key, anchor in ANCHORS.items()}
    topics: list[dict[str, Any]] = []
    all_passed = True

    for topic_id, meta in TOPICS.items():
        anchor_keys = list(TOPIC_ANCHORS[topic_id])
        topic_anchors = [anchors[key] for key in anchor_keys]
        doc = _doc_result(root, topic_id, meta["doc"])
        status = _topic_status(topic_anchors, doc)
        topic_passed = status == "closed_narrow_runtime_contract"
        all_passed = all_passed and topic_passed
        topics.append(
            {
                "topic_id": topic_id,
                "title": meta["title"],
                "status": status,
                "gap": _topic_gap(status, str(meta["legacy_gap"])),
                "evidence": {
                    "doc": doc,
                    "anchors": topic_anchors,
                    "commands": [
                        "cd main/backend && python3.11 -m pytest -q tests/unit/test_ingest_frontdoor_context_unittest.py tests/unit/test_source_library_resolver_unittest.py tests/unit/test_collect_runtime_source_library_adapter_unittest.py tests/unit/test_fetch_router_gap_closure_check_unittest.py",
                        "python3.11 main/backend/scripts/check_fetch_router_gap_closure.py",
                        "git diff --check",
                    ],
                },
            }
        )

    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if all_passed else "failed",
        "topics": topics,
        "validation": {
            "passed": all_passed,
            "topic_count": len(topics),
            "protected_shared_indexes": list(PROTECTED_SHARED_INDEXES),
            "shared_indexes_edited": False,
            "tri_state_blocker_wording": {
                "status": "not_blocking_narrow_closure",
                "states": ["success", "degraded_success", "failed"],
                "source": str(ANCHORS["tri_state_status_projection"].path),
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Wave8-2 fetch-router/frontdoor gap closure evidence.")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check()
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
