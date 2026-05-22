#!/usr/bin/env python3
"""Offline governance gate for source-library search-chain mounting.

The checker intentionally avoids public network access. It verifies that the
search chain still mounts into the source-library front door, that site-search
adapter capability/profile downgrades are visible, and that public replay /
relevance-review gaps remain explicit blockers rather than closure claims.
"""

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
from app.services.source_library.types import FrontDoorExecutionProtocol  # noqa: E402
from scripts.check_source_library_public_replay_a5_gate import (  # noqa: E402
    build_check as build_public_replay_a5_check,
)


CONTRACT_VERSION = "source_library.search_chain_governance.v1"
PUBLIC_REPLAY_NON_CLOSURE_STATUSES = {
    "deterministic_replay_gate_closed_external_public_replay_blocked",
    "full_public_replay_artifact_present_review_required",
}


def _read_text(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def _text_has(root: Path, relative: str, snippet: str) -> bool:
    return snippet in _read_text(root, relative)


def _route_row(
    *,
    root: Path,
    route_id: str,
    method: str,
    public_path: str,
    source_file: str,
    evidence_snippets: list[str],
    governance_role: str,
    expected_status: str,
) -> dict[str, Any]:
    text = _read_text(root, source_file)
    found = bool(text) and all(snippet in text for snippet in evidence_snippets)
    return {
        "route_id": route_id,
        "method": method,
        "public_path": public_path,
        "source_file": source_file,
        "governance_role": governance_role,
        "expected_status": expected_status,
        "present": found,
        "evidence_snippets": evidence_snippets,
    }


def _build_mount_routes_check(root: Path, errors: list[str]) -> dict[str, Any]:
    api_prefix_present = _text_has(
        root,
        "main/backend/app/main.py",
        'app.include_router(api_router, prefix="/api/v1")',
    )
    router_includes = {
        "ingest": _text_has(root, "main/backend/app/api/__init__.py", "router.include_router(ingest_router)"),
        "source_library": _text_has(
            root,
            "main/backend/app/api/__init__.py",
            "router.include_router(source_library_router)",
        ),
        "agent_batch": _text_has(
            root,
            "main/backend/app/api/__init__.py",
            "router.include_router(agent_batch_router)",
        ),
        "process": _text_has(root, "main/backend/app/api/__init__.py", "router.include_router(process_router)"),
        "resource_pool": _text_has(
            root,
            "main/backend/app/api/__init__.py",
            "router.include_router(resource_pool_router)",
        ),
    }
    routes = [
        _route_row(
            root=root,
            route_id="source_library_authoritative_sync",
            method="POST",
            public_path="/api/v1/ingest/source-library/run",
            source_file="main/backend/app/api/ingest.py",
            evidence_snippets=['@router.post("/source-library/run"', "run_source_library_item_compat"],
            governance_role="authoritative_sync_frontdoor",
            expected_status="active",
        ),
        _route_row(
            root=root,
            route_id="source_library_legacy_item_run",
            method="POST",
            public_path="/api/v1/source_library/items/{item_key}/run",
            source_file="main/backend/app/api/source_library.py",
            evidence_snippets=[
                '@router.post("/items/{item_key}/run")',
                '"legacy_status": "410_gone"',
                '"runs_source_library_item": False',
                '"/api/v1/ingest/source-library/run"',
            ],
            governance_role="deprecated_guard",
            expected_status="410_gone_no_execution",
        ),
        _route_row(
            root=root,
            route_id="agent_batch_source_library_async",
            method="POST",
            public_path="/api/v1/agent-batch/jobs",
            source_file="main/backend/app/api/agent_batch.py",
            evidence_snippets=[
                '@router.post("/jobs")',
                "build_source_library_override_params",
                "_submit_source_library_job",
                "_submit_source_item",
            ],
            governance_role="async_orchestration_entry",
            expected_status="active",
        ),
        _route_row(
            root=root,
            route_id="process_retry_source_library_bypass",
            method="POST",
            public_path="/api/v1/process/{task_id}/retry",
            source_file="main/backend/app/api/process.py",
            evidence_snippets=[
                '@router.post("/{task_id}/retry")',
                '"source_library_run"',
                '"agent_batch.dispatch.source_library_item"',
                '"process.retry_task.api"',
            ],
            governance_role="known_bypass_entry",
            expected_status="active_bypass_requires_metadata_governance",
        ),
        _route_row(
            root=root,
            route_id="resource_pool_unified_search",
            method="POST",
            public_path="/api/v1/resource_pool/unified-search",
            source_file="main/backend/app/api/resource_pool.py",
            evidence_snippets=['"/unified-search"', "def unified_search_api", "unified_search_by_item"],
            governance_role="capability_endpoint_not_source_library_frontdoor",
            expected_status="capability_only",
        ),
    ]

    _require(api_prefix_present, errors, "API router must stay mounted at /api/v1")
    for name, present in sorted(router_includes.items()):
        _require(present, errors, f"api router include missing: {name}")
    for route in routes:
        _require(bool(route["present"]), errors, f"route governance evidence missing: {route['route_id']}")

    return {
        "api_prefix_present": api_prefix_present,
        "router_includes": router_includes,
        "routes": routes,
    }


def _protocol(
    *,
    item_key: str,
    item_channel_key: str,
    project_key: str | None,
    query_terms: list[str] | None = None,
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
        route_decision="governance_fixture",
        query_terms=list(query_terms or []),
        site_entries=[],
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
        channel_key: {"channel_key": channel_key, "provider": item.get("provider") or "", "provider_type": item.get("provider_type") or ""},
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
        candidate_urls = params.get("urls") if isinstance(params.get("urls"), list) else []
        return _protocol(
            item_key=str(item.get("item_key") or ""),
            item_channel_key=str(item.get("channel_key") or ""),
            project_key=project_key,
            query_terms=[str(term) for term in query_terms],
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
        "source_mode": request.source_mode,
        "warnings": list(request.warnings),
        "taxonomy": dict(request.taxonomy),
        "item_channel_key": request.item_channel_key,
    }


def _build_resolver_check(root: Path, errors: list[str]) -> dict[str, Any]:
    cases = {
        "handler_cluster_forces_site_search": _resolver_fixture(
            item={
                "item_key": "handler.cluster.search_template",
                "channel_key": "handler.cluster",
                "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
            },
            params={"query_terms": ["openai pricing"], "source_mode": "protocol_search"},
        ),
        "candidate_urls_override_to_url_execution": _resolver_fixture(
            item={
                "item_key": "handler.cluster.search_template",
                "channel_key": "handler.cluster",
                "extra": {"stable_handler_cluster": True, "expected_entry_type": "search_template"},
            },
            params={"query_terms": ["openai pricing"], "urls": ["https://example.com/article"]},
        ),
        "generic_web_stays_internal_site_search": _resolver_fixture(
            item={
                "item_key": "generic_web.search_template.fixture",
                "channel_key": "generic_web.search_template",
                "extra": {"expected_entry_type": "search_template"},
            },
            params={"query_terms": ["openai pricing"]},
        ),
    }

    _require(
        cases["handler_cluster_forces_site_search"]["source_mode"] == "site_search",
        errors,
        "handler.cluster source items must resolve to site_search",
    )
    _require(
        "source_mode_coerced_by_site_search_taxonomy:protocol_search->site_search"
        in cases["handler_cluster_forces_site_search"]["warnings"],
        errors,
        "site_search authoritative taxonomy must override explicit protocol_search",
    )
    _require(
        cases["candidate_urls_override_to_url_execution"]["source_mode"] == "url_execution",
        errors,
        "candidate URLs must override source-library execution to url_execution",
    )
    _require(
        cases["generic_web_stays_internal_site_search"]["source_mode"] == "site_search",
        errors,
        "generic_web.* internal adapter items must resolve to site_search",
    )
    _require(
        "generic_web_internal_adapter_detected" in cases["generic_web_stays_internal_site_search"]["warnings"],
        errors,
        "generic_web.* internal adapter warning must stay visible",
    )

    static_contracts = {
        "site_search_orchestrator_forces_handler_cluster": _text_has(
            root,
            "main/backend/app/services/source_library/orchestrators/site_search.py",
            'site_item["channel_key"] = "handler.cluster"',
        )
        and _text_has(
            root,
            "main/backend/app/services/source_library/orchestrators/site_search.py",
            "run_handler_cluster_item",
        ),
        "handler_cluster_uses_unified_search": _text_has(
            root,
            "main/backend/app/services/source_library/resolver.py",
            "unified_search_by_item_payload",
        )
        and _text_has(
            root,
            "main/backend/app/services/source_library/resolver.py",
            '"candidate_sources_are_fetch_targets": False',
        ),
        "generic_web_direct_item_execution_blocked": _text_has(
            root,
            "main/backend/app/services/source_library/resolver.py",
            "generic_web.* direct item execution is disabled",
        ),
        "collect_runtime_source_library_adapter_registered": _text_has(
            root,
            "main/backend/app/services/collect_runtime/runtime.py",
            '"source_library": SourceLibraryAdapter()',
        ),
    }
    for key, value in static_contracts.items():
        _require(bool(value), errors, f"resolver static governance missing: {key}")

    return {
        "cases": cases,
        "static_contracts": static_contracts,
    }


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


def _build_adapter_capability_check(root: Path, errors: list[str]) -> dict[str, Any]:
    cases = {
        "validated_domain_profile": _adapter_capability_case(
            "https://www.pymnts.com/?s={{q}}",
            "www.pymnts.com",
            {},
        ),
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
    _require(
        cases["validated_domain_profile"]["adapter_capability_status"] == "allow",
        errors,
        "known parser profile must be allowed",
    )
    _require(
        cases["unknown_profile_downgraded"]["adapter_capability_status"] == "downgrade",
        errors,
        "unknown parser profile must be downgraded",
    )
    _require(
        cases["anchor_only_requires_review"]["adapter_capability_status"] == "review",
        errors,
        "anchor-only parser profile must require review",
    )
    _require(
        bool(cases["anchor_only_requires_review"]["candidate_relevance_review_required"]),
        errors,
        "anchor-only parser profile must mark candidate relevance review required",
    )

    handler_registry_contracts = {
        "handler_cluster_registered": _text_has(
            root,
            "main/backend/app/services/source_library/adapters/__init__.py",
            'register("handler", "cluster", handle_handler_cluster)',
        ),
        "generic_web_search_template_registered": _text_has(
            root,
            "main/backend/app/services/source_library/adapters/__init__.py",
            'register("generic_web", "search_template", handle_generic_web_search_template)',
        ),
        "generic_adapter_emits_capability_profile": _text_has(
            root,
            "main/backend/app/services/source_library/adapters/generic_web.py",
            '"capability_profile": capability_profile',
        ),
        "handler_cluster_emits_capability_profile": _text_has(
            root,
            "main/backend/app/services/source_library/adapters/handler_cluster.py",
            '"capability_profile"',
        ),
    }
    for key, value in handler_registry_contracts.items():
        _require(bool(value), errors, f"adapter capability static governance missing: {key}")

    return {
        "cases": cases,
        "handler_registry_contracts": handler_registry_contracts,
    }


def _build_public_replay_gap_check(root: Path, errors: list[str]) -> dict[str, Any]:
    public_gate = build_public_replay_a5_check(root)
    validation = public_gate.get("validation") if isinstance(public_gate.get("validation"), dict) else {}
    replay_status = str(public_gate.get("a5_status") or "")
    relevance_review = (
        public_gate.get("term_fallback_relevance_review")
        if isinstance(public_gate.get("term_fallback_relevance_review"), dict)
        else {}
    )
    external_blocker = public_gate.get("external_blocker") if isinstance(public_gate.get("external_blocker"), dict) else {}

    _require(bool(validation.get("passed")), errors, "public replay deterministic A5 gate must pass")
    _require(
        replay_status in PUBLIC_REPLAY_NON_CLOSURE_STATUSES,
        errors,
        "public replay status must remain a non-closure status",
    )
    _require(
        bool(validation.get("public_network_attempted")) is False,
        errors,
        "governance checker must not attempt public network",
    )
    _require(
        relevance_review.get("status") == "review_required_not_full_closure",
        errors,
        "term-fallback relevance review must remain review_required_not_full_closure",
    )
    _require(
        int(relevance_review.get("review_target_count") or 0) >= 1,
        errors,
        "governance checker must preserve at least one relevance-review blocker",
    )

    return {
        "a5_status": replay_status,
        "public_network_attempted": bool(validation.get("public_network_attempted")),
        "external_blocker": {
            "status": external_blocker.get("status"),
            "blocker_type": external_blocker.get("blocker_type"),
            "path": external_blocker.get("path"),
        },
        "term_fallback_relevance_review": relevance_review,
        "validation_errors": list(validation.get("errors") or []),
    }


def build_check(repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    root = root.resolve()
    errors: list[str] = []

    mount_routes = _build_mount_routes_check(root, errors)
    resolver = _build_resolver_check(root, errors)
    adapter_capability = _build_adapter_capability_check(root, errors)
    public_replay_gaps = _build_public_replay_gap_check(root, errors)

    return {
        "contract_version": CONTRACT_VERSION,
        "repo_root": str(root),
        "governance_scope": {
            "public_network_required": False,
            "claims_full_45_site_public_replay": False,
            "claims_human_relevance_review_complete": False,
            "shared_indexes_edited": False,
        },
        "mount_routes": mount_routes,
        "resolver": resolver,
        "adapter_capability": adapter_capability,
        "public_replay_gaps": public_replay_gaps,
        "validation": {
            "passed": not errors,
            "errors": errors,
            "public_network_attempted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check source-library search-chain governance without public network access.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_check(args.repo_root)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
