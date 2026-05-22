#!/usr/bin/env python3
"""Deterministic AT-EXT contract gate for source-library ingest migration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.collect_runtime.adapters.source_library import to_source_library_response
from app.services.collect_runtime.contracts import CollectResult
from app.services.source_library import external_project_registration
from app.services.source_library.adapters.external_project import handle_external_project_manifest
from app.services.source_library.external_project import (
    EXTERNAL_PROJECT_CHANNEL_KEY,
    EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION,
    EXTERNAL_PROJECT_MANIFEST_KEY,
    build_external_project_summary,
    normalize_external_project_extra,
    normalize_external_project_manifest,
)
from app.services.source_library.external_project_registry import list_external_project_provider_bindings
from app.services.source_library.item_plan import build_item_definition_view, build_item_execution_plan


CONTRACT_VERSION = "source-library-ingest-at-ext-current-contract.v1"
SUPPORTED_NARROW_MODES = ("rss_feed", "sitemap", "http_api", "article_extractor")

REMAINING_GAPS = [
    {
        "code": "live_article_extraction_stack_replay_not_run",
        "at_ext": ["AT-EXT-05", "AT-EXT-06", "AT-EXT-08", "AT-EXT-09"],
        "reason": "Fixture-backed article-body extraction runner and fallback states are proven, but no live Fundus/news-please style third-party replay is claimed.",
    },
    {
        "code": "python_library_cli_container_runners_not_enabled",
        "at_ext": ["AT-EXT-05", "AT-EXT-08", "AT-EXT-09"],
        "reason": "The provider registry intentionally exposes rss_feed/sitemap/http_api only; python_library and cli_or_container remain outside this narrow v1 gate.",
    },
    {
        "code": "live_external_project_replay_not_run",
        "at_ext": ["AT-EXT-08", "AT-EXT-09"],
        "reason": "This gate uses patched deterministic runtime evidence and does not probe a live third-party RSS/API/project endpoint.",
    },
]


def _manifest(*, execution_mode: str = "http_api") -> dict[str, Any]:
    runner_ref = "https://api.example.invalid/search"
    source_kind = "api_provider"
    capabilities = {
        "candidate_urls": True,
        "article_metadata": True,
        "article_body": False,
        "pdf_artifact": True,
    }
    accepted_inputs = {
        "query_terms": True,
        "urls": False,
        "domains": True,
        "date_range": True,
        "max_items": True,
    }
    runtime_config: dict[str, Any] = {
        "method": "GET",
        "query_param_map": {
            "query_terms": "q",
            "domains": "domains",
            "max_items": "limit",
            "date_from": "from",
            "date_to": "to",
        },
        "records_path": "items",
        "record_mapping": {
            "url": "url",
            "title": "title",
            "summary": "summary",
            "artifact_url": "pdf_url",
        },
    }

    if execution_mode == "rss_feed":
        runner_ref = "https://feeds.example.invalid/rss.xml"
        source_kind = "feed_aggregator"
        capabilities["pdf_artifact"] = False
        accepted_inputs["domains"] = False
        accepted_inputs["date_range"] = False
        runtime_config = {}
    elif execution_mode == "sitemap":
        runner_ref = "https://site.example.invalid/sitemap.xml"
        source_kind = "site_extractor"
        capabilities["pdf_artifact"] = False
        accepted_inputs["domains"] = False
        accepted_inputs["date_range"] = False
        runtime_config = {}
    elif execution_mode == "article_extractor":
        runner_ref = "article-extractor://trafilatura-or-heuristic"
        source_kind = "article_extraction_stack"
        capabilities["article_body"] = True
        capabilities["pdf_artifact"] = False
        accepted_inputs["urls"] = True
        accepted_inputs["domains"] = False
        accepted_inputs["date_range"] = False
        runtime_config = {
            "parser": "heuristic.main_content.v1",
        }

    payload: dict[str, Any] = {
        "contract_version": EXTERNAL_PROJECT_MANIFEST_CONTRACT_VERSION,
        "item_key": "external.demo.item",
        "display_name": "External Demo Item",
        "project_link": "https://github.example.invalid/example/external-demo",
        "source_kind": source_kind,
        "source_scope": "finance_news",
        "capabilities": capabilities,
        "accepted_inputs": accepted_inputs,
        "execution_mode": execution_mode,
        "runner_ref": runner_ref,
        "normalization": {
            "record_kind": "article_metadata",
            "frontdoor_strategy": "records_only_defer",
        },
        "limits": {
            "default_max_items": 2,
            "max_items_cap": 10,
            "request_timeout_ms": 5000,
        },
        "refresh_policy": {
            "manifest_ttl_minutes": 60,
            "probe_ttl_minutes": 1440,
        },
        "provenance": {
            "discovered_by": "contract_gate",
            "source_refs": ["https://github.example.invalid/example/external-demo"],
        },
    }
    if runtime_config:
        payload["runtime_config"] = runtime_config
    if execution_mode == "article_extractor":
        payload["normalization"] = {
            "record_kind": "document_candidate",
            "frontdoor_strategy": "records_allow_extract",
        }
    return payload


def _external_item(*, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "item_key": "external.demo.item",
        "name": "External Demo Item",
        "channel_key": EXTERNAL_PROJECT_CHANNEL_KEY,
        "item_type": "user_defined",
        "managed_by": "user",
        "enabled": True,
        "params": {},
        "extra": {
            EXTERNAL_PROJECT_MANIFEST_KEY: manifest or _manifest(),
        },
    }


def _record_step(status: dict[str, Any], task: str, state: str, evidence: list[str]) -> None:
    status[task] = {
        "status": state,
        "evidence": evidence,
    }


def _prove_boundary_contract() -> dict[str, Any]:
    normalized = normalize_external_project_extra(
        {EXTERNAL_PROJECT_MANIFEST_KEY: _manifest(execution_mode="rss_feed")},
        item_key="external.demo.item",
        display_name="External Demo Item",
        channel_key=EXTERNAL_PROJECT_CHANNEL_KEY,
    )
    try:
        normalize_external_project_extra(
            {EXTERNAL_PROJECT_MANIFEST_KEY: _manifest(execution_mode="rss_feed")},
            item_key="external.demo.item",
            display_name="External Demo Item",
            channel_key="market.general",
        )
    except ValueError as exc:
        mismatch_rejected = "requires channel_key=external_project.manifest" in str(exc)
    else:
        mismatch_rejected = False

    manifest = normalized[EXTERNAL_PROJECT_MANIFEST_KEY]
    return {
        "channel_key": EXTERNAL_PROJECT_CHANNEL_KEY,
        "manifest_key": EXTERNAL_PROJECT_MANIFEST_KEY,
        "manifest_contract_version": manifest["contract_version"],
        "channel_mismatch_rejected": mismatch_rejected,
        "project_link_seed_only": bool(manifest.get("project_link") and manifest.get("runner_ref")),
    }


def _prove_manifest_and_registry_contract() -> dict[str, Any]:
    manifests = {
        mode: normalize_external_project_manifest(
            _manifest(execution_mode=mode),
            item_key="external.demo.item",
            display_name="External Demo Item",
        )
        for mode in SUPPORTED_NARROW_MODES
    }
    bindings = list_external_project_provider_bindings()
    by_mode = {entry["execution_mode"]: entry for entry in bindings}
    return {
        "supported_modes": sorted(manifests),
        "provider_registry_modes": sorted(by_mode),
        "provider_keys": {mode: by_mode[mode]["provider_key"] for mode in sorted(by_mode)},
        "http_api_accepts_date_range": manifests["http_api"]["accepted_inputs"]["date_range"],
        "http_api_supports_pdf_artifact": manifests["http_api"]["capabilities"]["pdf_artifact"],
    }


def _prove_manifest_builder_contract() -> dict[str, Any]:
    project_context = {
        "source": "github",
        "evidence": [{"kind": "readme", "content": "See https://feeds.example.invalid/rss.xml"}],
        "endpoint_candidates": [
            {
                "execution_mode": "rss_feed",
                "runner_ref": "https://feeds.example.invalid/rss.xml",
                "reason": "explicit_readme_feed_marker",
                "confidence": "high",
            }
        ],
    }
    with patch.object(external_project_registration, "invoke_skill") as invoke_skill:
        manifest = external_project_registration.synthesize_external_project_manifest(
            project_link="https://github.example.invalid/example/external-demo",
            item_key="external.demo.item",
            display_name="External Demo Item",
            project_context=project_context,
            hints=None,
        )
    return {
        "used_deterministic_context_probe": not invoke_skill.called,
        "execution_mode": manifest["execution_mode"],
        "runner_ref": manifest["runner_ref"],
        "provider_key": manifest["provider_binding"]["provider_key"],
        "provenance": manifest["provenance"]["discovered_by"],
    }


def _prove_item_surface_contract() -> dict[str, Any]:
    item = _external_item()
    plan = build_item_execution_plan(item)
    definition = build_item_definition_view(item, include_execution_plan=True)
    return {
        "execution_family": plan["plan_meta"]["execution_family"],
        "default_params_empty": definition["params"] == {},
        "execution_plan_opt_in": "execution_plan" in definition,
        "route_bucket_total": plan["route_bucket_counts"]["total"],
        "external_summary_provider_key": plan["plan_meta"]["external_project"]["provider_binding"]["provider_key"],
    }


def _prove_runner_and_frontdoor_contract() -> dict[str, Any]:
    item = _external_item()
    params = {
        "_source_library_item": item,
        "query_terms": ["fintech"],
        "domains": ["example.invalid"],
        "max_items": 1,
        "date_from": "2026-01-01",
        "date_to": "2026-01-31",
    }
    fake_payload = {
        "items": [
            {
                "url": "https://example.invalid/post/1",
                "title": "External API Record",
                "summary": "API summary",
                "pdf_url": "https://example.invalid/post/1.pdf",
            }
        ]
    }
    with patch(
        "app.services.source_library.adapters.external_project.default_http_client.get_json",
        return_value=fake_payload,
    ) as get_json:
        result = handle_external_project_manifest(params, project_key="demo_proj")

    legacy_result = {
        **item,
        "project_key": "demo_proj",
        "params": {"query_terms": ["fintech"], "max_items": 1},
        "result": result,
    }
    response = to_source_library_response(CollectResult(channel="source_library", meta={"raw": legacy_result}))
    record = result["records"][0]
    return {
        "http_api_called": get_json.called,
        "runner_provider": result["provider"],
        "runner_status": result["status"],
        "record_count": len(result["records"]),
        "artifact_ref_present": bool((record.get("record_meta") or {}).get("artifact_ref")),
        "frontdoor_source_kind": response["frontdoor_ingress"]["source_ref"]["source_kind"],
        "frontdoor_execution_mode": response["frontdoor_ingress"]["source_ref"]["execution_mode"],
        "authority_normalized_records": response["authority_output"]["summary"]["record_stats"]["normalized"],
        "external_manifest_summary": build_external_project_summary(item["extra"][EXTERNAL_PROJECT_MANIFEST_KEY]),
    }


def _prove_article_extraction_runner_contract() -> dict[str, Any]:
    item = _external_item(manifest=_manifest(execution_mode="article_extractor"))
    params = {
        "_source_library_item": item,
        "urls": ["https://example.invalid/article/body", "https://example.invalid/article/empty"],
        "max_items": 2,
    }
    body_text = " ".join(["Deterministic article body"] * 50)
    extraction_results = [
        SimpleNamespace(
            title="Fixture Body",
            content=body_text,
            extractor="heuristic.main_content.v1",
            confidence="medium",
            meta={"fixture": True},
        ),
        SimpleNamespace(
            title=None,
            content="",
            extractor="heuristic.main_content.v1",
            confidence="low",
            meta={"fixture": True},
        ),
    ]
    with (
        patch(
            "app.services.source_library.adapters.external_project.default_http_client.get_text",
            return_value="<article>fixture</article>",
        ) as get_text,
        patch(
            "app.services.source_library.adapters.external_project.extract_article_content_from_html",
            side_effect=extraction_results,
        ) as extractor,
    ):
        result = handle_external_project_manifest(params, project_key="demo_proj")

    legacy_result = {
        **item,
        "project_key": "demo_proj",
        "params": {"urls": params["urls"], "max_items": 2},
        "result": result,
    }
    response = to_source_library_response(CollectResult(channel="source_library", meta={"raw": legacy_result}))
    diagnostics = result["runtime_diagnostics"]["diagnostics"]
    states = [entry["state"] for entry in diagnostics["fallback_states"]]
    return {
        "http_text_called": get_text.call_count,
        "parser_called": extractor.call_count,
        "runner_status": result["status"],
        "provider_key": result["provider_binding"]["provider_key"],
        "parser_capability": diagnostics["parser_capability"],
        "fallback_states": states,
        "article_body_record_state": result["records"][0]["record_meta"]["article_extraction"]["state"],
        "metadata_fallback_record_state": result["records"][1]["record_meta"]["article_extraction"]["state"],
        "frontdoor_has_document_candidate": bool(response["frontdoor_ingress"]["collection_payload"].get("document_candidate")),
        "frontdoor_dispatch_reason": response["frontdoor_ingress"]["collection_payload"]["dispatch_plan"]["reason"],
        "frontdoor_run_extraction": response["frontdoor_ingress"]["collection_payload"]["dispatch_plan"]["run_extraction"],
    }


def build_contract() -> dict[str, Any]:
    failures: list[str] = []
    evidence: dict[str, Any] = {}

    checks = {
        "boundary": _prove_boundary_contract,
        "manifest_registry": _prove_manifest_and_registry_contract,
        "manifest_builder": _prove_manifest_builder_contract,
        "item_surface": _prove_item_surface_contract,
        "runner_frontdoor": _prove_runner_and_frontdoor_contract,
        "article_extraction_runner": _prove_article_extraction_runner_contract,
    }
    for name, check in checks.items():
        try:
            evidence[name] = check()
        except Exception as exc:  # noqa: BLE001 - checker must report every deterministic failure.
            evidence[name] = {"status": "failed", "error": str(exc), "exception_type": exc.__class__.__name__}
            failures.append(f"{name}: {exc}")

    at_ext_status: dict[str, Any] = {}
    _record_step(
        at_ext_status,
        "AT-EXT-01",
        "closed_narrow_v1",
        ["external_project.manifest channel requires a normalized extra.external_project_manifest"],
    )
    _record_step(
        at_ext_status,
        "AT-EXT-02",
        "closed_narrow_v1",
        ["external_item.manifest.v1 is normalized for rss_feed, sitemap, http_api, and article_extractor"],
    )
    _record_step(
        at_ext_status,
        "AT-EXT-03",
        "closed_narrow_v1",
        ["provider registry exposes bounded rss_feed/sitemap/http_api/article_extractor adapter bindings"],
    )
    _record_step(
        at_ext_status,
        "AT-EXT-04",
        "closed_narrow_v1",
        ["high-confidence endpoint candidates synthesize a stable manifest without per-query LLM routing"],
    )
    _record_step(
        at_ext_status,
        "AT-EXT-05",
        "partial_narrow_v1",
        ["bounded provider runner executes http_api/article_extractor and has registered rss_feed/sitemap runners"],
    )
    _record_step(
        at_ext_status,
        "AT-EXT-06",
        "closed_narrow_v1",
        ["runner records and article-body document candidates map into terminal_output -> frontdoor_ingress -> postprocess_frontdoor authority path"],
    )
    _record_step(
        at_ext_status,
        "AT-EXT-07",
        "closed_narrow_v1",
        ["external items retain definition-first listing semantics and expose execution_plan only by opt-in"],
    )
    _record_step(
        at_ext_status,
        "AT-EXT-08",
        "partial_narrow_v1",
        ["registered manifest-backed items are runnable through the external_project adapter with deterministic patched runtime evidence"],
    )
    _record_step(
        at_ext_status,
        "AT-EXT-09",
        "partial_pending_external_replay",
        ["validation closure has current-state evidence plus explicit remaining gaps"],
    )

    if evidence.get("boundary", {}).get("channel_mismatch_rejected") is not True:
        failures.append("boundary: channel mismatch was not rejected")
    if evidence.get("manifest_registry", {}).get("supported_modes") != sorted(SUPPORTED_NARROW_MODES):
        failures.append("manifest_registry: supported modes mismatch")
    if evidence.get("manifest_builder", {}).get("used_deterministic_context_probe") is not True:
        failures.append("manifest_builder: deterministic high-confidence probe used LLM fallback")
    if evidence.get("item_surface", {}).get("execution_family") != "external_project":
        failures.append("item_surface: external project execution family missing")
    if evidence.get("runner_frontdoor", {}).get("artifact_ref_present") is not True:
        failures.append("runner_frontdoor: artifact_ref was not preserved")
    if evidence.get("runner_frontdoor", {}).get("frontdoor_execution_mode") != "http_api":
        failures.append("runner_frontdoor: frontdoor execution_mode was not preserved")
    article_runner = evidence.get("article_extraction_runner", {})
    if article_runner.get("provider_key") != "external_project.article_extractor":
        failures.append("article_extraction_runner: provider binding missing")
    if article_runner.get("fallback_states") != ["article_body_extracted", "metadata_only_fallback"]:
        failures.append("article_extraction_runner: fallback states mismatch")
    if article_runner.get("frontdoor_has_document_candidate") is not True:
        failures.append("article_extraction_runner: frontdoor document candidate missing")
    if article_runner.get("frontdoor_run_extraction") is not False:
        failures.append("article_extraction_runner: frontdoor structured extraction should remain disabled")

    return {
        "contract_version": CONTRACT_VERSION,
        "scope": "deterministic_current_state_no_live_external_probe",
        "status": "failed" if failures else "passed_with_known_gaps",
        "at_ext_status": at_ext_status,
        "evidence": evidence,
        "remaining_gaps": REMAINING_GAPS,
        "failures": failures,
    }


def main() -> int:
    contract = build_contract()
    print(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if contract["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
