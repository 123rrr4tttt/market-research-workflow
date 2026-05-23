#!/usr/bin/env python3
"""Offline gate for source-library taxonomy and review readiness boundaries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.resource_pool.search_template_adapters import (  # noqa: E402
    apply_search_template_adapter_plan,
)
from app.services.resource_pool.search_template_adapters import (  # noqa: E402
    resolve_search_template_adapter_plan,
)
from app.services.source_library.item_resolver import ItemResolver  # noqa: E402
from app.services.source_library.relevance_review import CONTRACT_VERSION as REVIEW_QUEUE_CONTRACT_VERSION  # noqa: E402
from app.services.source_library.relevance_review import TAXONOMY_REVIEW_READINESS_CONTRACT_VERSION  # noqa: E402
from app.services.source_library.relevance_review import build_relevance_review_queue  # noqa: E402
from app.services.source_library.relevance_review import build_taxonomy_review_readiness  # noqa: E402
from app.services.source_library.types import FrontDoorExecutionProtocol  # noqa: E402


CURRENT_DEV_ROOT = Path("development/latest-dev-docs/development-plans/CURRENT_DEV")
ARCHIVE_EXTERNAL_BLOCKED_ROOT = Path("development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED")
ARCHIVE_CLOSED_ROOT = Path("docs/development/development-plans/ARCHIVE_CLOSED")


def _evidence_doc_candidates(topic_dir: str, filename: str) -> tuple[Path, ...]:
    return (
        ARCHIVE_CLOSED_ROOT / topic_dir / filename,
        ARCHIVE_EXTERNAL_BLOCKED_ROOT / topic_dir / filename,
        CURRENT_DEV_ROOT / topic_dir / filename,
    )


EVIDENCE_DOCS = [
    _evidence_doc_candidates(
        "2026-03-11-source-library-three-lane-architecture",
        "09_wave14-taxonomy-review-readiness-2026-05-22.md",
    ),
    _evidence_doc_candidates(
        "2026-03-14-search-chain-source-library-mounting-audit",
        "05_wave14-taxonomy-review-readiness-2026-05-22.md",
    ),
    _evidence_doc_candidates(
        "2026-03-14-source-library-adapter-capability-remediation",
        "15_wave14-taxonomy-review-readiness-2026-05-22.md",
    ),
]
FORBIDDEN_SHARED_INDEXES = {
    "development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/STATUS_AUDIT_2026-04-07.md",
    "development/latest-dev-docs/development-plans/INDEX.md",
    "development/latest-dev-docs/README.md",
    "development/latest-dev-docs/MERGED_OVERVIEW.md",
}


def _read(root: Path, relative: Path | str) -> str:
    path = root / relative
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _resolve_existing_relative(root: Path, candidates: tuple[Path, ...]) -> Path:
    for relative in candidates:
        if (root / relative).is_file():
            return relative
    return candidates[0]


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _protocol(
    *,
    item_key: str,
    item_channel_key: str,
    project_key: str | None,
    query_terms: list[str] | None = None,
    site_entries: list[str] | None = None,
    candidate_urls: list[str] | None = None,
    expected_entry_type: str | None = None,
) -> FrontDoorExecutionProtocol:
    return FrontDoorExecutionProtocol(
        item_key=item_key,
        item_channel_key=item_channel_key,
        project_key=project_key,
        front_door_owner="source_library",
        execution_mode="test",
        write_mode="terminal_output_only",
        route_decision="taxonomy_review_readiness_fixture",
        query_terms=list(query_terms or []),
        site_entries=list(site_entries or []),
        candidate_urls=list(candidate_urls or []),
        expected_entry_type=expected_entry_type,
        write_to_pool=False,
        auto_ingest=False,
        ingest_limit=5,
        force_url_routing_flow=False,
        prefer_crawler_first=False,
        search_parallelism=1,
        routing_parallelism=1,
        concurrency_plan={},
        source_tier="tier_1_baseline_platform",
        onboarding_priority="p0_now",
    )


def _resolver_fixture(
    *,
    case_id: str,
    item: dict[str, Any],
    params: dict[str, Any],
    project_key: str | None = "demo_proj",
) -> dict[str, Any]:
    channel_key = str(item.get("channel_key") or "").strip()
    channel_map = {
        "handler.cluster": {"channel_key": "handler.cluster", "provider": "handler", "provider_type": "cluster"},
        "generic_web.search_template": {
            "channel_key": "generic_web.search_template",
            "provider": "generic_web",
            "provider_type": "tool",
        },
        "url_pool": {"channel_key": "url_pool", "provider": "url_pool", "provider_type": "urls"},
        channel_key: {
            "channel_key": channel_key,
            "provider": item.get("provider") or "",
            "provider_type": item.get("provider_type") or "",
        },
    }

    def _build_frontdoor_protocol(
        *,
        item: dict[str, Any],
        params: dict[str, Any],
        project_key: str | None,
    ) -> FrontDoorExecutionProtocol:
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        expected_entry_type = str(params.get("expected_entry_type") or extra.get("expected_entry_type") or "").strip() or None
        query_terms = params.get("query_terms") if isinstance(params.get("query_terms"), list) else []
        site_entries = params.get("site_entries") if isinstance(params.get("site_entries"), list) else []
        candidate_urls = params.get("urls") if isinstance(params.get("urls"), list) else []
        return _protocol(
            item_key=str(item.get("item_key") or ""),
            item_channel_key=str(item.get("channel_key") or ""),
            project_key=project_key,
            query_terms=[str(term) for term in query_terms],
            site_entries=[str(url) for url in site_entries],
            candidate_urls=[str(url) for url in candidate_urls],
            expected_entry_type=expected_entry_type,
        )

    request = ItemResolver.resolve(
        item=item,
        params=params,
        project_key=project_key,
        channel_map=channel_map,
        build_frontdoor_protocol=_build_frontdoor_protocol,
        is_handler_cluster_item=lambda row: bool(((row or {}).get("extra") or {}).get("stable_handler_cluster"))
        or str((row or {}).get("channel_key") or "").strip().lower() == "handler.cluster",
        has_site_entries=lambda row: bool((row or {}).get("site_entries")),
    )
    return {
        "case_id": case_id,
        "item_key": request.item_key,
        "item_channel_key": request.item_channel_key,
        "source_mode": request.source_mode,
        "warnings": list(request.warnings),
        "taxonomy": dict(request.taxonomy),
    }


def _build_taxonomy_cases(errors: list[str]) -> list[dict[str, Any]]:
    cases = [
        _resolver_fixture(
            case_id="handler_cluster_site_search_taxonomy",
            item={
                "item_key": "handler.cluster.search_template",
                "channel_key": "handler.cluster",
                "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
            },
            params={
                "query_terms": ["robotics funding"],
                "source_mode": "protocol_search",
                "site_entries": ["https://example.com/search?q={{q}}"],
            },
        ),
        _resolver_fixture(
            case_id="generic_web_internal_site_search_taxonomy",
            item={
                "item_key": "generic_web.search_template.fixture",
                "channel_key": "generic_web.search_template",
                "extra": {"expected_entry_type": "search_template"},
            },
            params={"query_terms": ["robotics funding"], "template": "https://example.com/search?q={{q}}"},
        ),
        _resolver_fixture(
            case_id="crawler_provider_harvest_taxonomy",
            item={
                "item_key": "crawler.demo_proj.fixture",
                "channel_key": "crawler.demo_proj",
                "provider_type": "scrapy",
            },
            params={"query_terms": ["robotics funding"]},
        ),
        _resolver_fixture(
            case_id="candidate_url_execution_taxonomy",
            item={
                "item_key": "handler.cluster.url_probe",
                "channel_key": "handler.cluster",
                "extra": {"stable_handler_cluster": True},
            },
            params={"query_terms": ["robotics funding"], "urls": ["https://example.com/posts/robotics-review"]},
        ),
    ]
    by_id = {row["case_id"]: row for row in cases}

    _require(by_id["handler_cluster_site_search_taxonomy"]["source_mode"] == "site_search", errors, "handler cluster taxonomy must resolve site_search")
    _require(
        "source_mode_coerced_by_site_search_taxonomy:protocol_search->site_search"
        in by_id["handler_cluster_site_search_taxonomy"]["warnings"],
        errors,
        "handler cluster taxonomy must preserve explicit-mode coercion warning",
    )
    _require(
        by_id["generic_web_internal_site_search_taxonomy"]["taxonomy"].get("internal_adapter_only") is True,
        errors,
        "generic_web taxonomy must stay marked internal_adapter_only",
    )
    _require(by_id["crawler_provider_harvest_taxonomy"]["source_mode"] == "provider_harvest", errors, "crawler taxonomy must resolve provider_harvest")
    _require(by_id["candidate_url_execution_taxonomy"]["source_mode"] == "url_execution", errors, "candidate URL taxonomy must resolve url_execution")
    return cases


def _build_review_queue() -> dict[str, Any]:
    return build_relevance_review_queue(
        project_key="demo_proj",
        item_key="handler.cluster.search_template",
        query_terms=["robotics funding"],
        candidates=[
            "https://example.com/posts/robotics-review",
            "https://safe.example/posts/high-confidence",
        ],
        candidate_refs={
            "https://example.com/posts/robotics-review": {
                "site_entry_url": "https://example.com/search?q={{q}}",
                "entry_type": "search_template",
                "domain": "example.com",
                "entry_domain": "example.com",
                "candidate_source": "search_template",
                "site_policy": "keep",
                "search_service": "basic",
                "matched_by": "none",
                "route_kind": "page",
                "candidate_quality": "low",
                "usable_for_search": False,
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "candidate_review_state": "relevance_review",
                "relevance_review_required": True,
            },
            "https://safe.example/posts/high-confidence": {
                "site_entry_url": "https://safe.example/search?q={{q}}",
                "entry_type": "search_template",
                "domain": "safe.example",
                "entry_domain": "safe.example",
                "candidate_source": "search_template",
                "site_policy": "keep",
                "search_service": "basic",
                "matched_by": "title",
                "route_kind": "article",
                "candidate_quality": "high",
                "usable_for_search": True,
                "adapter_capability_status": "allow",
                "parser_profile_resolved": "site_adaptive",
                "relevance_review_required": False,
            },
        },
        runtime_diagnostics=[
            {
                "site_url": "https://example.com/search?q={{q}}",
                "domain": "example.com",
                "site_policy": "keep",
                "search_service": "basic",
                "adapter_capability_status": "review",
                "adapter_capability_reason": "low_confidence_anchor_only_profile",
                "parser_profile_resolved": "fallback_anchor_only",
                "relevance_review_required": True,
                "relevance_review_reason": "term_fallback_candidates",
            }
        ],
        errors=[
            {
                "site_url": "https://example.com/search?q={{q}}",
                "error": "url_term_filter_empty_fallback_used",
                "search_service_used": "basic",
            }
        ],
        source_surface="taxonomy_review_readiness.fixture",
    )


def _adapter_capability_case(site_url: str, entry_domain: str | None, params: dict[str, Any]) -> dict[str, Any]:
    plan = resolve_search_template_adapter_plan(
        site_url=site_url,
        entry_domain=entry_domain,
        params=params,
    )
    routed = apply_search_template_adapter_plan(plan=plan, params=params)
    return {
        "site_url": site_url,
        "entry_domain": entry_domain,
        "adapter_key": plan.adapter_key,
        "parser_profile_requested": routed.get("parser_profile_requested"),
        "parser_profile_resolved": routed.get("parser_profile_resolved"),
        "adapter_capability_status": routed.get("adapter_capability_status"),
        "adapter_capability_reason": routed.get("adapter_capability_reason"),
        "candidate_relevance_review_required": bool(routed.get("candidate_relevance_review_required")),
    }


def _build_adapter_capability_check(errors: list[str]) -> dict[str, Any]:
    cases = {
        "validated_domain_profile": _adapter_capability_case("https://www.pymnts.com/?s={{q}}", "www.pymnts.com", {}),
        "unknown_profile_downgraded": _adapter_capability_case(
            "https://example.com/search?q={{q}}",
            "example.com",
            {"parser_profile": "site_adaptive.missing_custom_profile"},
        ),
        "anchor_only_requires_review": _adapter_capability_case(
            "https://example.com/search?q={{q}}",
            "example.com",
            {"parser_profile": "fallback_anchor_only"},
        ),
    }
    _require(cases["validated_domain_profile"]["adapter_capability_status"] == "allow", errors, "known parser profile must be allowed")
    _require(cases["unknown_profile_downgraded"]["adapter_capability_status"] == "downgrade", errors, "unknown parser profile must downgrade")
    _require(cases["anchor_only_requires_review"]["adapter_capability_status"] == "review", errors, "anchor-only profile must require review")
    _require(
        cases["anchor_only_requires_review"]["candidate_relevance_review_required"] is True,
        errors,
        "anchor-only profile must mark candidate relevance review required",
    )
    return {"cases": cases}


def _build_doc_check(root: Path, errors: list[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for candidates in EVIDENCE_DOCS:
        relative = _resolve_existing_relative(root, candidates)
        text = _read(root, relative)
        exists = bool(text)
        has_contract = TAXONOMY_REVIEW_READINESS_CONTRACT_VERSION in text
        has_queue = REVIEW_QUEUE_CONTRACT_VERSION in text
        has_markers = (
            "taxonomy_readiness=ready" in text
            and "review_queue_ready=true" in text
            and "human_review_completed=false" in text
        )
        rows.append(
            {
                "path": relative.as_posix(),
                "candidate_paths": [path.as_posix() for path in candidates],
                "exists": exists,
                "taxonomy_contract_mentioned": has_contract,
                "review_queue_contract_mentioned": has_queue,
                "readiness_markers_present": has_markers,
            }
        )
        _require(exists, errors, f"missing topic evidence doc: {relative.as_posix()}")
        _require(has_contract, errors, f"evidence doc missing taxonomy readiness contract: {relative.as_posix()}")
        _require(has_queue, errors, f"evidence doc missing review queue contract: {relative.as_posix()}")
        _require(has_markers, errors, f"evidence doc missing readiness/non-closure markers: {relative.as_posix()}")
    return {"docs": rows, "forbidden_shared_indexes": sorted(FORBIDDEN_SHARED_INDEXES)}


def _load_human_review_evidence(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("--human-review-evidence must contain a JSON array")
    return [row for row in payload if isinstance(row, dict)]


def build_check(
    repo_root: Path | str | None = None,
    *,
    human_review_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()
    errors: list[str] = []

    taxonomy_cases = _build_taxonomy_cases(errors)
    review_queue = _build_review_queue()
    readiness = build_taxonomy_review_readiness(
        taxonomy_cases=taxonomy_cases,
        review_queue=review_queue,
        human_review_evidence=human_review_evidence or [],
        source_surface="check_source_library_taxonomy_review_readiness",
    )
    adapter_capability = _build_adapter_capability_check(errors)
    docs = _build_doc_check(root, errors)

    _require(readiness["taxonomy"]["ready"] is True, errors, "live source taxonomy readiness must be ready")
    _require(readiness["review_queue"]["ready_for_review"] is True, errors, "review queue must be ready_for_review")
    _require(
        readiness["human_review"]["completed"] is False or bool(human_review_evidence),
        errors,
        "human_review_completed=true requires explicit evidence input",
    )

    return {
        "contract_version": TAXONOMY_REVIEW_READINESS_CONTRACT_VERSION,
        "repo_root": str(root),
        "taxonomy_review_readiness": readiness,
        "adapter_capability": adapter_capability,
        "evidence_docs": docs,
        "governance_scope": {
            "public_network_required": False,
            "taxonomy_readiness": readiness["readiness"]["taxonomy_readiness"],
            "review_queue_ready": readiness["readiness"]["review_queue_ready"],
            "human_review_completed": readiness["readiness"]["human_review_completed"],
            "claims_human_review_complete_without_evidence": False,
            "shared_indexes_edited": False,
        },
        "validation": {
            "passed": not errors,
            "errors": errors,
            "public_network_attempted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check source-library taxonomy/review readiness without public network access.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--human-review-evidence", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    human_review_evidence = _load_human_review_evidence(args.human_review_evidence)
    result = build_check(args.repo_root, human_review_evidence=human_review_evidence)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
