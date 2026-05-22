"""URL pool channel: fetch URLs from channel or resource pool and ingest as documents."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
import logging
import os
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ...models.base import SessionLocal
from ...models.entities import Document
from ..job_logger import complete_job, fail_job, start_job
from ..collect_runtime.display_meta import build_display_meta
from ..collect_runtime.contracts import CollectRequest, CollectResult
from ..resource_pool import list_urls
from .frontdoor_rollout import is_ingest_frontdoor_enabled
from .postprocess_frontdoor import run_frontdoor_extraction
from .metrics_payload import (
    attach_metrics_payload,
    build_metrics_payload_from_summary,
    new_metrics_summary,
    record_metrics_observation,
)
from .gate_reason_codes import normalize_reason_code
from .frontdoor_router_contract import build_frontdoor_fetch_router_contract, router_contract_from_profile
from .content_cleaner import normalize_content_for_ingest
from .adapters.http_utils import make_html_parser
from .source_search_contract import build_query_url_from_contract, normalize_source_search_contract
from .url_unwrap import unwrap_url

logger = logging.getLogger(__name__)

_SOURCE_NAME = "url_pool"
_SOURCE_KIND = "url_fetch"
_DOC_TYPE = "url_fetch"
_DEFAULT_LIMIT = 50
_DEBUG_MAX_URLS = 200
_DEBUG_MAX_POOL_ITEMS = 50
_DEBUG_MAX_ERRORS = 50
_TEMPLATE_HEALTH_TOP_N = 5
_FRONTDOOR_ROUTE_PROFILE_CONTRACT_VERSION = "ingest.frontdoor_route_profile.v1"
_FRONTDOOR_STATUS_PROJECTION_CONTRACT_VERSION = "ingest.frontdoor_status_projection.v1"
_ENTRY_QUERY_KEYS = {"q", "query", "keyword", "keywords", "search", "s", "term"}
_HIGH_JS_DOMAINS = {
    "x.com",
    "twitter.com",
    "threads.net",
    "instagram.com",
    "facebook.com",
    "linkedin.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
}


def _resolve_default_parallel_workers() -> int:
    raw = os.getenv("URL_POOL_DEFAULT_PARALLEL_WORKERS", "").strip()
    if raw:
        try:
            return max(1, min(32, int(raw)))
        except Exception:
            pass
    cpu = os.cpu_count() or 4
    return max(1, min(12, int(cpu)))


_DEFAULT_PARALLEL_WORKERS = _resolve_default_parallel_workers()
_SOURCE_SEARCH_CONTRACT_FIELDS = {
    "param_key",
    "encoding",
    "lang",
    "region",
    "page",
    "page_size",
    "sort",
    "min_results_required",
    "max_candidates",
}


def _safe_exc(exc: Exception) -> str:
    msg = str(exc).strip()
    if not msg:
        msg = exc.__class__.__name__
    if exc.__class__.__name__ in msg:
        return msg
    return f"{exc.__class__.__name__}: {msg}"


def _detail(url: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"url": url}
    for k, v in extra.items():
        if v is not None:
            out[k] = v
    return out


def _apply_structured_extraction(
    extracted_data: Dict[str, Any],
    *,
    domain_str: str,
    content: str,
    url: str,
) -> None:
    """Compatibility shim for legacy tests and call sites; mainline extraction is frontdoor-owned."""
    try:
        outcome = run_frontdoor_extraction(
            title=domain_str,
            content=content or "",
            extraction_plan={
                "enabled": True,
                "mode": "url_pool_compat",
                "include_market": True,
                "include_policy": True,
                "include_sentiment": True,
                "include_company": True,
                "include_product": True,
                "include_operation": True,
            },
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("url_pool extraction failed for %s: %s", url[:80], ex)
        extracted_data["extraction_status"] = "failed"
        extracted_data["extraction_reason"] = "extractor_exception"
        extracted_data["extraction_error"] = _safe_exc(ex)
        return

    domains = outcome.get("domains") if isinstance(outcome, dict) else None
    if isinstance(domains, dict) and domains:
        extracted_data.update(domains)
        extracted_data["extraction_status"] = "ok"
        return

    extracted_data["extraction_status"] = "failed"
    extracted_data["extraction_reason"] = str((outcome or {}).get("reason") or "empty_structured_output")
    if (outcome or {}).get("error"):
        extracted_data["extraction_error"] = str((outcome or {}).get("error"))


def _normalize_url_list(urls: Any) -> List[str]:
    """Extract and normalize URL list from channel/params."""
    if isinstance(urls, list):
        return [str(u).strip() for u in urls if u and str(u).strip().startswith(("http://", "https://"))]
    return []


def _normalize_terms(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x or "").strip()]
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    return []


def _resolve_source_search_contract_for_target(
    *,
    target_url: str,
    target: Dict[str, Any] | None,
    extra_params: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    if isinstance(target, dict) and isinstance(target.get("source_search_contract"), dict):
        return dict(target.get("source_search_contract") or {})
    if not isinstance(extra_params, dict):
        return None

    direct = extra_params.get("source_search_contract")
    if isinstance(direct, dict):
        return dict(direct)

    mapped = extra_params.get("source_search_contracts")
    if isinstance(mapped, dict):
        key_exact = str(target_url or "").strip()
        key_norm = _normalize_url_no_fragment(key_exact)
        domain_key = _domain_key(key_exact)
        for key in (key_exact, key_norm, domain_key):
            if key and isinstance(mapped.get(key), dict):
                return dict(mapped.get(key) or {})

    top_level: Dict[str, Any] = {}
    for field in _SOURCE_SEARCH_CONTRACT_FIELDS:
        if field in extra_params:
            top_level[field] = extra_params.get(field)
    return top_level or None


def _search_options_for_target(
    target_url: str,
    query_terms: List[str],
    *,
    target: Dict[str, Any] | None = None,
    extra_params: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    parsed = urlparse(str(target_url or ""))
    path = str(parsed.path or "").lower()
    query_pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    query_keys = {str(k or "").strip().lower() for k, _ in query_pairs if str(k or "").strip()}
    is_search_like = bool("/search" in path or bool(query_keys & _ENTRY_QUERY_KEYS))
    raw_contract = _resolve_source_search_contract_for_target(
        target_url=target_url,
        target=target,
        extra_params=extra_params,
    )
    contract = normalize_source_search_contract(target_url, raw_contract)
    if not is_search_like and contract is None:
        return None
    limit = 1 if query_terms else 0
    max_candidates = int((contract or {}).get("max_candidates") or 6)
    min_results_required = int((contract or {}).get("min_results_required") or 6)
    return {
        "search_expand": bool(limit > 0),
        "search_expand_limit": max(1, limit) if limit > 0 else 1,
        "search_provider": "auto",
        "search_fallback_provider": "ddg_html",
        "fallback_on_insufficient": True,
        "target_candidates": max(1, max_candidates),
        "max_candidates": max(1, max_candidates),
        "min_results_required": max(1, min_results_required),
        "decode_redirect_wrappers": True,
        "filter_low_value_candidates": True,
        "source_search_contract": contract,
    }


def _domain_matches(domain: str, suffix: str) -> bool:
    domain = str(domain or "").strip().lower()
    suffix = str(suffix or "").strip().lower()
    return bool(domain and suffix and (domain == suffix or domain.endswith(f".{suffix}")))


def _frontdoor_route_profile_for_url(url: str) -> Dict[str, Any]:
    parsed = urlparse(str(url or ""))
    domain = str(parsed.netloc or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    path = str(parsed.path or "").lower()
    query_pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    query_keys = {str(k or "").strip().lower() for k, _ in query_pairs if str(k or "").strip()}
    search_like = bool("/search" in path or bool(query_keys & _ENTRY_QUERY_KEYS))
    high_js = any(_domain_matches(domain, d) for d in _HIGH_JS_DOMAINS)
    route_hint = "crawler_browse" if high_js else ("search_shell" if search_like else "static_detail")
    fetch_strategy = "browser_render" if high_js else ("search_candidate_route" if search_like else "http_fetch")
    router_contract = build_frontdoor_fetch_router_contract(
        route_hint=route_hint,
        fetch_strategy=fetch_strategy,
        render_required=high_js,
        high_js=high_js,
        search_like=search_like,
        fallback_fetch_strategy="http_fetch" if not high_js else None,
        diagnostics={"domain": domain or None, "source": "ingest.url_pool.route_profile"},
    )
    return {
        "contract_version": _FRONTDOOR_ROUTE_PROFILE_CONTRACT_VERSION,
        "route_hint": route_hint,
        "fetch_strategy": fetch_strategy,
        "domain": domain or None,
        "search_like": search_like,
        "high_js": high_js,
        "prefer_crawler": high_js,
        "prefer_search_shell": search_like,
        "render_required": high_js,
        "fallback_fetch_strategy": "http_fetch",
        "router_contract": router_contract,
    }


def _frontdoor_route_hint_for_url(url: str) -> str:
    return str(_frontdoor_route_profile_for_url(url).get("route_hint") or "static_detail")


def _apply_frontdoor_target_hint(
    *,
    search_options: Dict[str, Any] | None,
    frontdoor_options: Dict[str, Any],
    target_url: str,
) -> Dict[str, Any] | None:
    out: Dict[str, Any] = dict(search_options or {})
    if not bool((frontdoor_options or {}).get("enabled")):
        return out or search_options
    route_profile = _frontdoor_route_profile_for_url(target_url)
    route_hint = str(route_profile.get("route_hint") or "static_detail")
    out["frontdoor_route_hint"] = route_hint
    out["frontdoor_fetch_strategy"] = route_profile.get("fetch_strategy")
    out["frontdoor_render_required"] = bool(route_profile.get("render_required"))
    out["frontdoor_prefers_crawler"] = bool(route_profile.get("prefer_crawler"))
    out["frontdoor_prefers_search_shell"] = bool(route_profile.get("prefer_search_shell"))
    out["frontdoor_route_profile"] = route_profile
    if isinstance(route_profile.get("router_contract"), dict):
        out["frontdoor_router_contract"] = dict(route_profile.get("router_contract") or {})
    return out


def _resolve_repo_url_batch_path_default_mode() -> str:
    try:
        from ...settings.config import settings as _settings
    except Exception:  # noqa: BLE001
        return "batch_runtime_targets"

    raw = str(getattr(_settings, "url_batch_path_default_mode", "batch_runtime_targets") or "").strip().lower()
    if raw in {"legacy_per_url", "batch_runtime_targets"}:
        return raw
    return "batch_runtime_targets"


def _resolve_url_batch_path_mode(extra_params: Optional[Dict[str, Any]], *, dispatch_mode: str) -> str:
    if dispatch_mode == "celery_async":
        return "legacy_per_url"
    if not isinstance(extra_params, dict):
        return _resolve_repo_url_batch_path_default_mode()

    raw = str(extra_params.get("url_batch_path_mode") or "").strip().lower()
    if raw in {"legacy_per_url", "batch_runtime_targets"}:
        return raw
    if raw == "inherit":
        return _resolve_repo_url_batch_path_default_mode()
    return _resolve_repo_url_batch_path_default_mode()


def _collect_urls_from_list_with_runtime_targets(
    *,
    urls: List[str],
    raw_count: int,
    normalized_count: int,
    normalized_terms: List[str],
    project_key: Optional[str],
    extra_params: Optional[Dict[str, Any]],
    enable_extraction: bool,
    job_id: int,
    targets: List[Dict[str, Any]],
    target_mode: str,
    runtime_targets: List[Tuple[str, Dict[str, Any]]],
    dispatch_mode: str,
    strict_mode: bool,
    frontdoor_options: Dict[str, Any],
    url_batch_path_mode: str,
) -> Dict[str, Any]:
    from ..tasks import task_ingest_url_via_source_library

    inserted = 0
    inserted_valid = 0
    skipped = 0
    rejected_count = 0
    rejection_breakdown: Dict[str, int] = {}
    skipped_exists = 0
    skipped_fetch_error = 0
    details: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    seen_runtime_urls: set[str] = set()
    workflow_name = "front_door_url_routing" if bool(frontdoor_options.get("enabled")) else (
        "url_routing_async" if dispatch_mode == "celery_async" else "url_routing"
    )

    parallel_workers = _resolve_parallel_workers(extra_params=extra_params, target_count=len(runtime_targets))
    parallel_batch_size = _resolve_parallel_batch_size(extra_params=extra_params, parallel_workers=parallel_workers)
    metrics_summary = new_metrics_summary()
    source_template_health_summary = _new_source_template_health_summary()
    frontdoor_status_summary = _new_frontdoor_status_summary()
    queued = 0
    queued_tasks: List[Dict[str, Any]] = []

    def _run_single_target(target_url: str, target: Dict[str, Any]) -> Dict[str, Any]:
        try:
            search_options = _search_options_for_target(
                target_url,
                normalized_terms,
                target=target,
                extra_params=extra_params,
            )
            search_options = _apply_frontdoor_to_search_options(search_options, frontdoor_options)
            search_options = _apply_frontdoor_target_hint(
                search_options=search_options,
                frontdoor_options=frontdoor_options,
                target_url=target_url,
            )
            search_options = dict(search_options or {})
            target_frontdoor_options = dict(frontdoor_options or {})
            target_frontdoor_options["enabled"] = True
            target_frontdoor_options["route_hint"] = str(search_options.get("frontdoor_route_hint") or "")
            target_frontdoor_options["fetch_strategy"] = str(search_options.get("frontdoor_fetch_strategy") or "")
            target_frontdoor_options["render_required"] = bool(search_options.get("frontdoor_render_required"))
            if isinstance(search_options.get("frontdoor_route_profile"), dict):
                target_frontdoor_options["route_profile"] = dict(search_options.get("frontdoor_route_profile") or {})
            if isinstance(search_options.get("frontdoor_router_contract"), dict):
                target_frontdoor_options["router_contract"] = dict(search_options.get("frontdoor_router_contract") or {})
            target_frontdoor_options["prefer_crawler"] = bool(search_options.get("frontdoor_prefers_crawler"))
            target_frontdoor_options["prefer_search_shell"] = bool(
                search_options.get("frontdoor_prefers_search_shell")
            )
            return _run_source_library_frontdoor_ingress(
                url=target_url,
                project_key=project_key,
                query_terms=normalized_terms,
                search_options=search_options,
                strict_mode=strict_mode,
                frontdoor_options=target_frontdoor_options,
                entrypoint="ingest.url_pool",
                source_name="url_pool",
                enable_extraction=bool(enable_extraction),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("url_pool url_routing dispatch failed for %s: %s", target_url[:80], exc)
            return {"status": "failed", "inserted": 0, "skipped": 1, "error": _safe_exc(exc)}

    def _collect_item_result(target_url: str, target: Dict[str, Any], item_result: Dict[str, Any]) -> None:
        nonlocal inserted, inserted_valid, skipped, rejected_count, skipped_exists, skipped_fetch_error
        inserted += int(item_result.get("inserted") or 0)
        inserted_valid += int(item_result.get("inserted_valid") or 0)
        item_skipped = int(item_result.get("skipped") or 0)
        skipped += item_skipped
        rejected_count += int(item_result.get("rejected_count") or 0)
        _merge_rejection_breakdown(rejection_breakdown, item_result.get("rejection_breakdown"))
        record_metrics_observation(metrics_summary, item_result, fallback_adapter=workflow_name)
        _record_source_template_health_observation(
            source_template_health_summary,
            target=target,
            item_result=item_result,
        )
        degradation_flags = list(item_result.get("degradation_flags") or [])
        if "document_already_exists" in degradation_flags:
            skipped_exists += 1
        if "fetch_failed" in degradation_flags:
            skipped_fetch_error += 1
        if str(item_result.get("status") or "").strip().lower() == "failed" and len(errors) < _DEBUG_MAX_ERRORS:
            errors.append({"url": target_url, "error": str(item_result.get("error") or "url_routing_failed")})
        frontdoor_status = _build_frontdoor_status_projection(item_result)
        _record_frontdoor_status_observation(frontdoor_status_summary, frontdoor_status)

        context_doc_ids = _extract_doc_ids_from_ingest_result(item_result)
        _annotate_url_pool_context(
            doc_ids=context_doc_ids,
            context={
                "mode": "list",
                "project_key": project_key,
                "entry_type": target.get("entry_type"),
                "site_seed": bool(target.get("is_site_seed")),
                "domain": target.get("domain"),
                "source_url": target.get("from_url"),
            },
        )

        if len(details) < _DEBUG_MAX_URLS:
            details.append(
                _detail(
                    target_url,
                    action="inserted" if int(item_result.get("inserted") or 0) > 0 else "processed",
                    status=item_result.get("status"),
                    document_id=item_result.get("document_id"),
                    quality_score=item_result.get("quality_score"),
                    degradation_flags=degradation_flags,
                    entry_type=target.get("entry_type"),
                    site_seed=bool(target.get("is_site_seed")),
                    handler=item_result.get("handler_allocation", {}).get("handler_used")
                    if isinstance(item_result.get("handler_allocation"), dict)
                    else None,
                    matched_channel_key=item_result.get("handler_allocation", {}).get("matched_channel_key")
                    if isinstance(item_result.get("handler_allocation"), dict)
                    else None,
                    frontdoor_route=item_result.get("frontdoor_route")
                    if isinstance(item_result.get("frontdoor_route"), dict)
                    else None,
                    frontdoor_status=frontdoor_status,
                )
            )

    if dispatch_mode == "celery_async":
        for target_url, target in runtime_targets:
            search_options = _search_options_for_target(
                target_url,
                normalized_terms,
                target=target,
                extra_params=extra_params,
            )
            search_options = _apply_frontdoor_to_search_options(search_options, frontdoor_options)
            search_options = _apply_frontdoor_target_hint(
                search_options=search_options,
                frontdoor_options=frontdoor_options,
                target_url=target_url,
            )
            async_result = task_ingest_url_via_source_library.delay(
                target_url,
                normalized_terms,
                strict_mode,
                project_key,
                search_options,
            )
            queued += 1
            frontdoor_status = _build_frontdoor_status_projection(
                {
                    "status": "degraded_success",
                    "reason_code": "queued_async",
                    "inserted_valid": 0,
                    "frontdoor_router_contract": search_options.get("frontdoor_router_contract")
                    if isinstance(search_options, dict)
                    else None,
                }
            )
            _record_frontdoor_status_observation(frontdoor_status_summary, frontdoor_status)
            record_metrics_observation(
                metrics_summary,
                {
                    "inserted_valid": 0,
                    "single_write_workflow": workflow_name,
                    "reason_code": "queued_async",
                },
                fallback_adapter=workflow_name,
            )
            if len(queued_tasks) < _DEBUG_MAX_URLS:
                queued_tasks.append(
                    _detail(
                        target_url,
                        action="queued",
                        task_id=getattr(async_result, "id", None),
                        entry_type=target.get("entry_type"),
                        site_seed=bool(target.get("is_site_seed")),
                        frontdoor_status=frontdoor_status,
                    )
                )
    else:
        for batch in _batch_slice(runtime_targets, parallel_batch_size):
            if parallel_workers <= 1 or len(batch) <= 1:
                for target_url, target in batch:
                    item_result = _run_single_target(target_url, target)
                    _collect_item_result(target_url, target, item_result)
                continue
            with ThreadPoolExecutor(max_workers=min(parallel_workers, len(batch))) as executor:
                future_to_target = {
                    executor.submit(copy_context().run, _run_single_target, tu, t): (tu, t)
                    for tu, t in batch
                }
                for future in as_completed(future_to_target):
                    tu, t = future_to_target[future]
                    item_result = future.result()
                    _collect_item_result(tu, t, item_result)

    result: Dict[str, Any] = {
        "inserted": inserted,
        "inserted_valid": inserted_valid,
        "skipped": skipped,
        "rejected_count": rejected_count,
        "rejection_breakdown": rejection_breakdown,
        "urls": len(urls),
        "skipped_exists": skipped_exists,
        "skipped_fetch_error": skipped_fetch_error,
        "queued": queued,
        "single_write_workflow": workflow_name,
        "debug": {
            "mode": "list",
            "dispatch_mode": dispatch_mode,
            "url_batch_path_mode": url_batch_path_mode,
            "strict_mode": bool(strict_mode),
            "frontdoor_enabled": bool(frontdoor_options.get("enabled")),
            "disable_site_seed_expansion": bool(target_mode == "detail_only"),
            "target_mode": target_mode,
            "parallel_workers": parallel_workers,
            "parallel_batch_size": parallel_batch_size,
            "raw_url_count": raw_count,
            "normalized_url_count": normalized_count,
            "filtered_out": max(0, raw_count - normalized_count),
            "site_seed_count": len([x for x in targets if bool(x.get("is_site_seed"))]),
            "target_count": len(targets),
            "target_deduped_count": len(runtime_targets),
            "url_details": queued_tasks if dispatch_mode == "celery_async" else details,
            "url_details_truncated": len(runtime_targets) > len(queued_tasks if dispatch_mode == "celery_async" else details),
            "errors": errors,
        },
    }
    result["display_meta"] = build_display_meta(
        CollectRequest(
            channel="url_pool",
            project_key=project_key,
            urls=list(urls),
            query_terms=normalized_terms,
            limit=len(urls),
            source_context={"summary": "URL 池抓取并写入文档"},
        ),
        CollectResult(
            channel="url_pool",
            inserted=inserted,
            skipped=skipped,
            updated=0,
            status="completed",
            errors=errors,
        ),
        summary="URL 池抓取并写入文档",
    )
    metrics_payload = build_metrics_payload_from_summary(metrics_summary)
    attach_metrics_payload(result, metrics_payload)
    source_template_health = _build_source_template_health_payload(source_template_health_summary)
    _attach_source_template_health(result, source_template_health)
    frontdoor_status = _build_frontdoor_status_summary_payload(frontdoor_status_summary)
    _attach_frontdoor_status_summary(result, frontdoor_status)
    complete_job(job_id, result=result)
    return result


def _extract_text_from_html(html: str) -> str:
    """Extract main text from HTML for storage."""
    try:
        parser = make_html_parser(html)
        for selector in ("article", "main article", "[role='main'] article", "main"):
            node = parser.css_first(selector)
            if node is None:
                continue
            text = str(node.text(separator="\n", strip=True) or "").strip()
            if len(text) >= 120:
                return normalize_content_for_ingest(text, max_chars=50000)
        body = parser.body
        if body:
            text = str(body.text(separator="\n", strip=True) or "").strip()
            return normalize_content_for_ingest(text, max_chars=50000)
        return ""
    except Exception:  # noqa: BLE001
        return ""


def _build_document_candidate_from_record(record: Dict[str, Any]) -> Dict[str, Any]:
    url = str(record.get("url") or "").strip()
    parsed = urlparse(url)
    source_base_url = None
    if parsed.scheme and parsed.netloc:
        source_base_url = f"{parsed.scheme}://{parsed.netloc}"
    content_text = str(record.get("content_text") or "").strip()
    summary = str(record.get("summary") or "").strip() or None
    if not summary and content_text:
        summary = content_text[:800]
    record_meta = dict(record.get("record_meta") or {}) if isinstance(record.get("record_meta"), dict) else {}
    extracted_data_base: Dict[str, Any] = {
        "source_label": record.get("source_label"),
        "record_meta": record_meta,
    }
    author = str(record.get("author") or "").strip()
    language = str(record.get("language") or "").strip()
    if author:
        extracted_data_base["author"] = author
    if language:
        extracted_data_base["language"] = language
    return {
        "source_name": str(record.get("source_label") or "source_library_url_execution"),
        "source_kind": "url_fetch",
        "source_base_url": source_base_url,
        "state": None,
        "doc_type": "url_fetch",
        "title": str(record.get("title") or "").strip() or None,
        "summary": summary,
        "publish_date": record.get("published_at"),
        "content": content_text,
        "text_hash": None,
        "uri": url or None,
        "status": None,
        "extracted_data_base": extracted_data_base,
    }


def _run_source_library_frontdoor_ingress(
    *,
    url: str,
    project_key: Optional[str] = None,
    query_terms: Optional[List[str]] = None,
    search_options: Optional[Dict[str, Any]] = None,
    strict_mode: bool = False,
    frontdoor_options: Optional[Dict[str, Any]] = None,
    entrypoint: str = "ingest.url_pool",
    source_name: str = "url_pool",
    enable_extraction: bool = True,
) -> Dict[str, Any]:
    from ..projects import bind_project
    from ..source_library.resolver import list_effective_channels, run_item_with_url_routing
    from .frontdoor_ingress import build_frontdoor_ingress_envelope
    from .postprocess_frontdoor import run_postprocess_frontdoor

    normalized_url = str(url or "").strip()
    params: Dict[str, Any] = {
        "urls": [normalized_url],
        "query_terms": list(query_terms or []),
        "strict_mode": bool(strict_mode),
    }
    if isinstance(search_options, dict) and search_options:
        params.update(dict(search_options))
    if isinstance(frontdoor_options, dict):
        if frontdoor_options.get("prefer_crawler"):
            params["prefer_crawler_first"] = True
            params["force_url_routing_flow"] = False
        if frontdoor_options.get("route_hint"):
            params["frontdoor_route_hint"] = frontdoor_options.get("route_hint")
        if frontdoor_options.get("fetch_strategy"):
            params["frontdoor_fetch_strategy"] = frontdoor_options.get("fetch_strategy")
        if "render_required" in frontdoor_options:
            params["frontdoor_render_required"] = bool(frontdoor_options.get("render_required"))
        if isinstance(frontdoor_options.get("route_profile"), dict):
            params["frontdoor_route_profile"] = dict(frontdoor_options.get("route_profile") or {})
        if isinstance(frontdoor_options.get("router_contract"), dict):
            params["frontdoor_router_contract"] = dict(frontdoor_options.get("router_contract") or {})

    channels = list_effective_channels(scope="effective", project_key=project_key)
    channel_map = {
        str(channel.get("channel_key") or "").strip(): dict(channel)
        for channel in channels
        if isinstance(channel, dict) and str(channel.get("channel_key") or "").strip()
    }
    synthetic_item = {
        "item_key": f"{source_name}.single_url_compat",
        "channel_key": "url_pool",
        "params": {},
        "extra": {
            "item_type": "service_aggregated",
            "managed_by": "single_url_compat",
        },
    }

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        routed = run_item_with_url_routing(
            item=synthetic_item,
            params=params,
            project_key=project_key,
            channel_map=channel_map,
            execution_layer="terminal_output_only",
        )

    records = list(routed.get("records") or []) if isinstance(routed.get("records"), list) else []
    errors = [str(x) for x in (routed.get("errors") or []) if str(x or "").strip()]
    by_url = list(routed.get("by_url") or []) if isinstance(routed.get("by_url"), list) else []
    frontdoor_route = _frontdoor_route_summary_from_params(params)
    if not records:
        reason = errors[0] if errors else "source_library_fetch_empty"
        return {
            "status": "failed" if errors else "degraded_success",
            "reason_code": "fetch_failed" if errors else "source_library_fetch_empty",
            "inserted": 0,
            "inserted_valid": 0,
            "skipped": 1,
            "rejected_count": 1 if errors else 0,
            "rejection_breakdown": {"fetch_failed": 1} if errors else {},
            "degradation_flags": ["fetch_failed"] if errors else ["empty_records"],
            "document_id": None,
            "quality_score": 0.0,
            "errors": errors,
            "error": reason,
            "records": [],
            "by_url": by_url,
            "frontdoor_route": frontdoor_route,
            "single_write_workflow": "source_library_frontdoor",
            "source_library_collect_only": True,
        }

    record = dict(records[0] or {})
    document_candidate = _build_document_candidate_from_record(record)
    ingress_envelope = build_frontdoor_ingress_envelope(
        ingress_type="source_library",
        entrypoint=entrypoint,
        source_mode="url_execution",
        project_key=project_key,
        source_ref={
            "url": normalized_url,
            "locator": normalized_url,
            "frontdoor_route_hint": frontdoor_route.get("route_hint"),
            "fetch_strategy": frontdoor_route.get("fetch_strategy"),
            "render_required": True if bool(frontdoor_route.get("render_required")) else None,
            "router_state": (frontdoor_route.get("router_contract") or {}).get("router_state")
            if isinstance(frontdoor_route.get("router_contract"), dict)
            else None,
            "router_reason_code": (frontdoor_route.get("router_contract") or {}).get("reason_code")
            if isinstance(frontdoor_route.get("router_contract"), dict)
            else None,
        },
        collection_payload={
            "document_candidate": document_candidate,
            "frontdoor_route": frontdoor_route,
            "terminal_context": {
                "platform": source_name,
                "ingestion_entrypoint": entrypoint,
                "source_mode": "url_execution",
                "strict_mode": bool(strict_mode),
                "quality_score": 0.0,
                "degradation_flags": [],
                "http_status": (record.get("record_meta") or {}).get("http_status")
                if isinstance(record.get("record_meta"), dict)
                else None,
                "capability_profile": {"source_library_collect_only": True},
                "light_filter": {},
            },
            "extraction_plan": {
                "enabled": bool(enable_extraction),
                "include_market": True,
                "include_policy": True,
                "include_sentiment": True,
                "include_company": True,
                "include_product": True,
                "include_operation": True,
            },
        },
        raw_snapshot={"record": record, "routed": {"by_url": by_url, "errors": errors}},
    )
    frontdoor_result = run_postprocess_frontdoor(
        ingress_envelope=ingress_envelope,
        run_writer=True,
    )
    data = frontdoor_result.get("data") if isinstance(frontdoor_result.get("data"), dict) else {}
    writer_result = data.get("writer_result") if isinstance(data.get("writer_result"), dict) else {}
    meta = frontdoor_result.get("meta") if isinstance(frontdoor_result.get("meta"), dict) else {}
    quality_gates = data.get("quality_gates") if isinstance(data.get("quality_gates"), dict) else {}
    gate_config = quality_gates.get("gate_config") if isinstance(quality_gates.get("gate_config"), dict) else {}
    guardrail_rollout = gate_config.get("guardrail_rollout") if isinstance(gate_config.get("guardrail_rollout"), dict) else {}
    canary_handoff = data.get("canary_handoff") if isinstance(data.get("canary_handoff"), dict) else {}
    admission = str(data.get("admission") or "").strip().lower()
    inserted = int(writer_result.get("inserted") or 0)
    skipped = int(writer_result.get("skipped") or (0 if inserted > 0 else 1))
    rejected_count = 0 if admission in {"", "accept"} else 1
    reason_code = str(meta.get("reason_code") or "").strip().lower()
    degradation_flags = [reason_code] if reason_code and reason_code != "ok" else []
    result = {
        "status": "success" if inserted > 0 else ("failed" if admission == "reject" else "degraded_success"),
        "inserted": inserted,
        "inserted_valid": inserted,
        "skipped": skipped,
        "rejected_count": rejected_count,
        "rejection_breakdown": {reason_code: 1} if rejected_count > 0 and reason_code else {},
        "degradation_flags": degradation_flags,
        "document_id": writer_result.get("doc_id"),
        "quality_score": 0.0,
        "records": records,
        "by_url": by_url,
        "frontdoor_route": frontdoor_route,
        "errors": errors,
        "frontdoor_ingress": ingress_envelope,
        "postprocess_frontdoor": frontdoor_result,
        "guardrail_rollout": dict(guardrail_rollout),
        "single_write_workflow": "source_library_frontdoor",
        "source_library_collect_only": True,
    }
    if canary_handoff:
        result["canary_handoff"] = dict(canary_handoff)
    return result


def ingest_url_via_source_library_frontdoor(
    *,
    url: str,
    project_key: Optional[str] = None,
    query_terms: Optional[List[str]] = None,
    search_options: Optional[Dict[str, Any]] = None,
    strict_mode: bool = False,
    frontdoor_options: Optional[Dict[str, Any]] = None,
    entrypoint: str = "ingest.url_pool",
    source_name: str = "url_pool",
    enable_extraction: bool = True,
) -> Dict[str, Any]:
    return _run_source_library_frontdoor_ingress(
        url=url,
        project_key=project_key,
        query_terms=query_terms,
        search_options=search_options,
        strict_mode=strict_mode,
        frontdoor_options=frontdoor_options,
        entrypoint=entrypoint,
        source_name=source_name,
        enable_extraction=enable_extraction,
    )


def _normalize_url_no_fragment(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        p = urlparse(raw)
    except Exception:
        return raw
    return urlunparse((p.scheme, p.netloc, p.path, p.params, p.query, ""))


def _domain_key(url: str) -> str:
    try:
        p = urlparse(str(url or "").strip())
    except Exception:
        return ""
    netloc = str(p.netloc or "").strip().lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _build_search_template_seed(url: str) -> str | None:
    norm = _normalize_url_no_fragment(url)
    if not norm:
        return None
    try:
        p = urlparse(norm)
    except Exception:
        return None
    path_l = str(p.path or "").lower()
    pairs = parse_qsl(p.query or "", keep_blank_values=True)
    has_query_key = any(str(k or "").strip().lower() in _ENTRY_QUERY_KEYS for k, _ in pairs)
    if "/search" not in path_l and not has_query_key:
        return None
    out_pairs: list[tuple[str, str]] = []
    replaced = False
    for k, v in pairs:
        lk = str(k or "").strip().lower()
        if lk in _ENTRY_QUERY_KEYS:
            out_pairs.append((k, "{{q}}"))
            replaced = True
        elif lk in {"page", "p", "paged"} and str(v).strip():
            out_pairs.append((k, "{{page}}"))
        else:
            out_pairs.append((k, v))
    if not replaced:
        out_pairs.append(("q", "{{q}}"))
    query = urlencode(out_pairs, doseq=True)
    return urlunparse((p.scheme, p.netloc, p.path or "/search", p.params, query, ""))


def _build_site_first_targets(urls: List[str]) -> List[Dict[str, Any]]:
    seeds: List[Dict[str, Any]] = []
    seen_seed: set[str] = set()
    seen_domain_root: set[str] = set()
    for raw in urls:
        url = _normalize_url_no_fragment(raw)
        if not url:
            continue
        domain = _domain_key(url)
        if not domain:
            continue
        if domain not in seen_domain_root:
            root_url = f"https://{domain}/"
            if root_url not in seen_seed:
                seen_seed.add(root_url)
                seeds.append({"url": root_url, "entry_type": "domain_root", "domain": domain, "from_url": url})
            seen_domain_root.add(domain)

        parsed = urlparse(url)
        path_l = str(parsed.path or "").lower()
        if "sitemap" in path_l or path_l.endswith(".xml") or path_l.endswith(".xml.gz"):
            if url not in seen_seed:
                seen_seed.add(url)
                seeds.append({"url": url, "entry_type": "sitemap", "domain": domain, "from_url": url})
        elif any(x in path_l for x in ("/rss", "/feed", "atom.xml", "rss.xml", "feed.xml")):
            if url not in seen_seed:
                seen_seed.add(url)
                seeds.append({"url": url, "entry_type": "rss", "domain": domain, "from_url": url})
        else:
            template = _build_search_template_seed(url)
            if template and template not in seen_seed:
                seen_seed.add(template)
                seeds.append({"url": template, "entry_type": "search_template", "domain": domain, "from_url": url})

    targets: List[Dict[str, Any]] = []
    seen_target: set[str] = set()
    for seed in seeds:
        u = str(seed.get("url") or "")
        if u and u not in seen_target:
            seen_target.add(u)
            targets.append({**seed, "is_site_seed": True})
    for raw in urls:
        u = _normalize_url_no_fragment(raw)
        if not u or u in seen_target:
            continue
        seen_target.add(u)
        targets.append({"url": u, "entry_type": "detail", "domain": _domain_key(u), "from_url": u, "is_site_seed": False})
    return targets


def _build_detail_only_targets(urls: List[str]) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in urls:
        u = _normalize_url_no_fragment(raw)
        if not u or u in seen:
            continue
        seen.add(u)
        targets.append({"url": u, "entry_type": "detail", "domain": _domain_key(u), "from_url": u, "is_site_seed": False})
    return targets


def _build_site_only_targets(urls: List[str]) -> List[Dict[str, Any]]:
    return [x for x in _build_site_first_targets(urls) if bool(x.get("is_site_seed"))]


def _build_site_then_detail_targets(
    urls: List[str],
    *,
    per_domain_limit: int,
) -> List[Dict[str, Any]]:
    seeds = _build_site_only_targets(urls)
    details = _build_detail_only_targets(urls)
    if not details:
        return seeds

    per_domain_limit = max(1, int(per_domain_limit))
    out = list(seeds)
    domain_counts: Dict[str, int] = {}
    for detail in details:
        domain = str(detail.get("domain") or "").strip().lower()
        if not domain:
            continue
        used = int(domain_counts.get(domain) or 0)
        if used >= per_domain_limit:
            continue
        domain_counts[domain] = used + 1
        out.append(detail)
    return out


def _resolve_target_mode(extra_params: Optional[Dict[str, Any]]) -> str:
    default_mode = str(os.getenv("URL_POOL_DEFAULT_TARGET_MODE", "site_then_detail") or "site_then_detail").strip().lower()
    if default_mode not in {"site_only", "detail_only", "site_first", "site_then_detail"}:
        default_mode = "site_then_detail"
    if not isinstance(extra_params, dict):
        return default_mode
    raw = str(
        extra_params.get(
            "url_target_mode",
            extra_params.get("target_mode", default_mode),
        )
        or ""
    ).strip().lower()
    if raw in {"site_only", "site_seed_only", "seed_only"}:
        return "site_only"
    if raw in {"site_then_detail", "site_seed_then_detail", "site_2hop"}:
        return "site_then_detail"
    if raw in {"detail_only", "url_only"}:
        return "detail_only"
    return "site_first"


def _resolve_disable_site_seed_expansion(extra_params: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(extra_params, dict):
        return False
    return _as_bool(
        extra_params.get(
            "disable_site_seed_expansion",
            extra_params.get("cluster_layer_separated", False),
        ),
        False,
    )


def _resolve_runtime_targets(urls: List[str], *, extra_params: Optional[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    if _resolve_disable_site_seed_expansion(extra_params):
        return _build_detail_only_targets(urls), "detail_only"
    target_mode = _resolve_target_mode(extra_params)
    if target_mode == "site_only":
        return _build_site_only_targets(urls), "site_only"
    if target_mode == "site_then_detail":
        per_domain = 2
        if isinstance(extra_params, dict):
            per_domain = _as_int(extra_params.get("site_second_hop_per_domain"), per_domain)
        return _build_site_then_detail_targets(urls, per_domain_limit=per_domain), "site_then_detail"
    if target_mode == "detail_only":
        return _build_detail_only_targets(urls), "detail_only"
    return _build_site_first_targets(urls), "site_first"


def _resolve_target_url(
    target: Dict[str, Any],
    query_terms: List[str],
    *,
    extra_params: Dict[str, Any] | None = None,
) -> str:
    raw = str(target.get("url") or "").strip()
    if not raw:
        return raw
    raw_contract = _resolve_source_search_contract_for_target(
        target_url=raw,
        target=target,
        extra_params=extra_params,
    )
    if "{{q}}" not in raw and raw_contract is None:
        return raw
    resolved = build_query_url_from_contract(raw, query_terms, raw_contract)
    unwrapped = unwrap_url(resolved, enable_network_redirect=True)
    return str(unwrapped.url or resolved)


def _extract_doc_ids_from_ingest_result(result: Dict[str, Any]) -> List[int]:
    doc_ids: List[int] = []
    try:
        direct_id = int(result.get("document_id"))
        if direct_id > 0:
            doc_ids.append(direct_id)
    except Exception:
        pass
    crawler_dispatch = result.get("crawler_dispatch")
    if isinstance(crawler_dispatch, dict):
        for raw in crawler_dispatch.get("valid_output_doc_ids") or []:
            try:
                doc_id = int(raw)
            except Exception:
                continue
            if doc_id > 0 and doc_id not in doc_ids:
                doc_ids.append(doc_id)
    return doc_ids


def _merge_rejection_breakdown(
    merged: Dict[str, int],
    incoming: Any,
) -> None:
    if not isinstance(incoming, dict):
        return
    for key, value in incoming.items():
        reason = str(key or "").strip()
        if not reason:
            continue
        try:
            count = int(value or 0)
        except Exception:
            count = 0
        if count <= 0:
            continue
        merged[reason] = int(merged.get(reason) or 0) + count


def _new_source_template_health_summary() -> Dict[str, Any]:
    return {"groups": {}}


def _normalize_url_rollup_key(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw
    scheme = str(parsed.scheme or "").lower()
    netloc = str(parsed.netloc or "").lower()
    path = str(parsed.path or "")
    return urlunparse((scheme, netloc, path, "", "", ""))


def _source_template_rollup_key(target: Dict[str, Any]) -> str:
    template_key = str(target.get("template_key") or "").strip()
    if template_key:
        return f"template_key:{template_key}"
    source_url = _normalize_url_rollup_key(str(target.get("from_url") or ""))
    if source_url:
        return f"source_url:{source_url}"
    target_url = _normalize_url_rollup_key(str(target.get("url") or ""))
    if target_url:
        return f"target_url:{target_url}"
    return ""


def _source_template_reason_code(item_result: Dict[str, Any]) -> str:
    reason = normalize_reason_code(item_result.get("reason_code"), default="ok")
    if reason and reason != "ok":
        return reason
    breakdown = item_result.get("rejection_breakdown")
    if isinstance(breakdown, dict) and breakdown:
        top_reason = sorted(
            (
                (normalize_reason_code(key, default="unknown_rejection_reason"), _as_int(value, 0))
                for key, value in breakdown.items()
            ),
            key=lambda pair: pair[1],
            reverse=True,
        )[0][0]
        return normalize_reason_code(top_reason, default="ok")
    return "ok"


def _is_source_template_target(target: Dict[str, Any], item_result: Dict[str, Any]) -> bool:
    if str(target.get("entry_type") or "").strip().lower() == "search_template":
        return True
    capability_profile = item_result.get("capability_profile")
    if isinstance(capability_profile, dict):
        return str(capability_profile.get("entry_type") or "").strip().lower() == "search_template"
    return False


def _record_source_template_health_observation(
    summary: Dict[str, Any],
    *,
    target: Dict[str, Any],
    item_result: Dict[str, Any],
) -> None:
    if not isinstance(summary, dict) or not isinstance(target, dict) or not isinstance(item_result, dict):
        return
    if not _is_source_template_target(target, item_result):
        return
    group_key = _source_template_rollup_key(target)
    if not group_key:
        return

    groups = summary.get("groups")
    if not isinstance(groups, dict):
        groups = {}
        summary["groups"] = groups
    bucket = groups.get(group_key)
    if not isinstance(bucket, dict):
        bucket = {"success": False, "body_inserted": False, "empty_body": False, "reason_counts": {}}
        groups[group_key] = bucket

    status = str(item_result.get("status") or "").strip().lower()
    inserted = _as_int(item_result.get("inserted"), 0)
    inserted_valid = _as_int(item_result.get("inserted_valid"), 0)
    body_inserted = inserted_valid > 0 or inserted > 0
    success = bool(status in {"success", "degraded_success"} or body_inserted)
    if success:
        bucket["success"] = True
    if body_inserted:
        bucket["body_inserted"] = True

    reason_code = _source_template_reason_code(item_result)
    reason_counts = bucket.get("reason_counts")
    if not isinstance(reason_counts, dict):
        reason_counts = {}
        bucket["reason_counts"] = reason_counts
    if reason_code and reason_code != "ok":
        # Per-template health should not over-count repeated same reason inside one template bucket.
        reason_counts[reason_code] = 1
    if reason_code in {"content_empty", "fetch_failed", "search_template_results_insufficient"}:
        bucket["empty_body"] = True


def _build_source_template_health_payload(
    summary: Dict[str, Any] | None,
    *,
    top_n: int = _TEMPLATE_HEALTH_TOP_N,
) -> Dict[str, Any]:
    groups = {}
    if isinstance(summary, dict) and isinstance(summary.get("groups"), dict):
        groups = dict(summary.get("groups") or {})
    total = max(0, len(groups))
    denominator = float(total) if total > 0 else 1.0
    top_limit = max(1, _as_int(top_n, _TEMPLATE_HEALTH_TOP_N))

    success_count = 0
    body_inserted_count = 0
    empty_body_count = 0
    rejection_counts: Dict[str, int] = {}
    for bucket in groups.values():
        if not isinstance(bucket, dict):
            continue
        if bool(bucket.get("success")):
            success_count += 1
        if bool(bucket.get("body_inserted")):
            body_inserted_count += 1
        if bool(bucket.get("empty_body")):
            empty_body_count += 1
        reason_counts = bucket.get("reason_counts")
        if isinstance(reason_counts, dict):
            for reason, count in reason_counts.items():
                normalized = normalize_reason_code(reason, default="unknown_rejection_reason")
                rejection_counts[normalized] = _as_int(rejection_counts.get(normalized), 0) + _as_int(count, 0)

    top_rejections = sorted(rejection_counts.items(), key=lambda pair: pair[1], reverse=True)[:top_limit]
    return {
        "sample_size": total,
        "template_success_rate": round(float(success_count) / denominator, 6) if total > 0 else 0.0,
        "template_body_insert_rate": round(float(body_inserted_count) / denominator, 6) if total > 0 else 0.0,
        "template_empty_body_rate": round(float(empty_body_count) / denominator, 6) if total > 0 else 0.0,
        "template_rejection_top_n": [
            {
                "reason_code": reason,
                "count": count,
                "rate": round(float(count) / denominator, 6) if total > 0 else 0.0,
            }
            for reason, count in top_rejections
        ],
    }


def _attach_source_template_health(
    result: Dict[str, Any],
    payload: Dict[str, Any],
) -> None:
    meta = result.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        result["meta"] = meta
    meta["source_template_health"] = payload

    debug = result.get("debug")
    if not isinstance(debug, dict):
        debug = {}
        result["debug"] = debug
    debug["source_template_health"] = payload


def _frontdoor_route_summary_from_params(params: Dict[str, Any]) -> Dict[str, Any]:
    profile = params.get("frontdoor_route_profile") if isinstance(params, dict) else None
    router_contract = None
    if isinstance(params, dict) and isinstance(params.get("frontdoor_router_contract"), dict):
        router_contract = dict(params.get("frontdoor_router_contract") or {})
    if router_contract is None:
        router_contract = router_contract_from_profile(profile)
    return {
        "contract_version": _FRONTDOOR_ROUTE_PROFILE_CONTRACT_VERSION,
        "route_hint": str((profile or {}).get("route_hint") or params.get("frontdoor_route_hint") or "").strip()
        or None,
        "fetch_strategy": str((profile or {}).get("fetch_strategy") or params.get("frontdoor_fetch_strategy") or "").strip()
        or None,
        "render_required": bool((profile or {}).get("render_required") or params.get("frontdoor_render_required")),
        "prefer_crawler_first": bool(params.get("prefer_crawler_first")),
        "force_url_routing_flow": bool(params.get("force_url_routing_flow", False)),
        "router_contract": router_contract,
    }


def _new_frontdoor_status_summary() -> Dict[str, Any]:
    return {
        "sample_size": 0,
        "dashboard_status_counts": {},
        "admission_counts": {},
        "reason_counts": {},
    }


def _build_frontdoor_status_projection(item_result: Dict[str, Any]) -> Dict[str, Any]:
    postprocess = item_result.get("postprocess_frontdoor") if isinstance(item_result.get("postprocess_frontdoor"), dict) else {}
    data = postprocess.get("data") if isinstance(postprocess.get("data"), dict) else {}
    meta = postprocess.get("meta") if isinstance(postprocess.get("meta"), dict) else {}
    frontdoor_route = item_result.get("frontdoor_route") if isinstance(item_result.get("frontdoor_route"), dict) else {}
    router_contract = (
        frontdoor_route.get("router_contract")
        if isinstance(frontdoor_route.get("router_contract"), dict)
        else item_result.get("frontdoor_router_contract")
        if isinstance(item_result.get("frontdoor_router_contract"), dict)
        else None
    )
    outer_status = str(item_result.get("status") or "").strip().lower()
    inserted_valid = _as_int(item_result.get("inserted_valid"), 0)
    admission = str(data.get("admission") or "").strip().lower()
    if not admission:
        if outer_status == "failed":
            admission = "reject"
        elif outer_status == "success" and inserted_valid > 0:
            admission = "accept"
        else:
            admission = "defer"

    reason_code = (
        str(meta.get("reason_code") or "").strip()
        or str(item_result.get("reason_code") or "").strip()
        or str((router_contract or {}).get("reason_code") or "").strip()
        or _source_template_reason_code(item_result)
    )
    reason_code = normalize_reason_code(reason_code, default="ok")
    retryable = bool(meta.get("retryable") or item_result.get("retryable"))

    if outer_status == "failed" or admission == "reject":
        dashboard_status = "failed"
    elif outer_status == "success" and admission == "accept" and inserted_valid > 0:
        dashboard_status = "success"
    else:
        dashboard_status = "degraded_success"

    source = "postprocess_frontdoor" if postprocess else "url_pool_result"
    projection = {
        "contract_version": _FRONTDOOR_STATUS_PROJECTION_CONTRACT_VERSION,
        "dashboard_status": dashboard_status,
        "frontdoor_admission": admission,
        "outer_status": outer_status or None,
        "reason_code": reason_code,
        "retryable": retryable,
        "inserted_valid": inserted_valid,
        "source": source,
    }
    if isinstance(router_contract, dict):
        projection["router_contract"] = dict(router_contract)
        projection["router_state"] = router_contract.get("router_state")
        projection["router_reason_code"] = router_contract.get("reason_code")
        if isinstance(router_contract.get("fallback_boundary"), dict):
            projection["fallback_boundary"] = dict(router_contract.get("fallback_boundary") or {})
    return projection


def _record_frontdoor_status_observation(
    summary: Dict[str, Any],
    projection: Dict[str, Any],
) -> None:
    if not isinstance(summary, dict) or not isinstance(projection, dict):
        return
    summary["sample_size"] = _as_int(summary.get("sample_size"), 0) + 1
    for source_key, bucket_key in (
        ("dashboard_status", "dashboard_status_counts"),
        ("frontdoor_admission", "admission_counts"),
        ("reason_code", "reason_counts"),
    ):
        value = str(projection.get(source_key) or "").strip()
        if not value:
            continue
        bucket = summary.get(bucket_key)
        if not isinstance(bucket, dict):
            bucket = {}
            summary[bucket_key] = bucket
        bucket[value] = _as_int(bucket.get(value), 0) + 1


def _build_frontdoor_status_summary_payload(summary: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = summary if isinstance(summary, dict) else {}
    return {
        "contract_version": _FRONTDOOR_STATUS_PROJECTION_CONTRACT_VERSION,
        "sample_size": _as_int(raw.get("sample_size"), 0),
        "dashboard_status_counts": dict(raw.get("dashboard_status_counts") or {}),
        "admission_counts": dict(raw.get("admission_counts") or {}),
        "reason_counts": dict(raw.get("reason_counts") or {}),
    }


def _attach_frontdoor_status_summary(
    result: Dict[str, Any],
    payload: Dict[str, Any],
) -> None:
    meta = result.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        result["meta"] = meta
    meta["frontdoor_status_summary"] = payload

    debug = result.get("debug")
    if not isinstance(debug, dict):
        debug = {}
        result["debug"] = debug
    debug["frontdoor_status_summary"] = payload


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(default)


def _resolve_dispatch_mode(extra_params: Optional[Dict[str, Any]]) -> str:
    if not isinstance(extra_params, dict):
        return "sync"
    if bool(extra_params.get("url_async")):
        return "celery_async"
    raw = str(extra_params.get("url_dispatch_mode") or "").strip().lower()
    if raw in {"celery_async", "async", "queue"}:
        return "celery_async"
    if raw in {"thread", "threads", "parallel"}:
        return "thread"
    return "sync"


def _resolve_url_strict_mode(extra_params: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(extra_params, dict):
        return False
    if "url_strict_mode" in extra_params:
        return _as_bool(extra_params.get("url_strict_mode"), False)
    if "strict_mode" in extra_params:
        return _as_bool(extra_params.get("strict_mode"), False)
    return False


def _resolve_frontdoor_options(
    extra_params: Optional[Dict[str, Any]],
    *,
    project_key: str | None,
) -> Dict[str, Any]:
    if not isinstance(extra_params, dict):
        return {"enabled": False}
    requested_enabled = _as_bool(
        extra_params.get(
            "url_routing_frontdoor_enabled",
            extra_params.get("frontdoor_enabled", extra_params.get("use_frontdoor", False)),
        ),
        False,
    )
    enabled = is_ingest_frontdoor_enabled(requested_enabled=requested_enabled, project_key=project_key)
    if not enabled:
        return {"enabled": False}
    return {
        "enabled": True,
        "front_door_owner": str(extra_params.get("front_door_owner") or "url_pool").strip() or "url_pool",
        "route_decision": str(extra_params.get("frontdoor_route_decision") or "front_door_url_routing").strip()
        or "front_door_url_routing",
        "write_mode": str(extra_params.get("frontdoor_write_mode") or "front_door_url_routing").strip()
        or "front_door_url_routing",
        "execution_mode": str(extra_params.get("frontdoor_execution_mode") or "url_routing").strip() or "url_routing",
    }


def _apply_frontdoor_to_search_options(
    search_options: Dict[str, Any] | None,
    frontdoor_options: Dict[str, Any],
) -> Dict[str, Any] | None:
    if not bool((frontdoor_options or {}).get("enabled")):
        return search_options
    out: Dict[str, Any] = dict(search_options or {})
    out["frontdoor_enabled"] = True
    out["front_door_owner"] = frontdoor_options.get("front_door_owner")
    out["frontdoor_route_decision"] = frontdoor_options.get("route_decision")
    out["frontdoor_write_mode"] = frontdoor_options.get("write_mode")
    out["frontdoor_execution_mode"] = frontdoor_options.get("execution_mode")
    return out


def _resolve_parallel_workers(
    *,
    extra_params: Optional[Dict[str, Any]],
    target_count: int,
) -> int:
    default_workers = _DEFAULT_PARALLEL_WORKERS
    if not isinstance(extra_params, dict):
        return min(default_workers, target_count) if target_count > 0 else default_workers
    raw = extra_params.get(
        "url_parallel_workers",
        extra_params.get("parallel_workers", default_workers),
    )
    workers = max(1, _as_int(raw, default_workers))
    workers = min(32, workers)
    if target_count > 0:
        workers = min(workers, target_count)
    return max(1, workers)


def _resolve_parallel_batch_size(
    *,
    extra_params: Optional[Dict[str, Any]],
    parallel_workers: int,
) -> int:
    default_size = max(16, parallel_workers * 4)
    if not isinstance(extra_params, dict):
        return default_size
    raw = extra_params.get("url_parallel_batch_size", default_size)
    return max(1, _as_int(raw, default_size))


def _batch_slice(items: List[Any], size: int) -> List[List[Any]]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


def _annotate_url_pool_context(
    *,
    doc_ids: List[int],
    context: Dict[str, Any],
) -> None:
    if not doc_ids:
        return
    valid_context = {k: v for k, v in context.items() if v is not None}
    if not valid_context:
        return
    with SessionLocal() as session:
        rows = session.query(Document).filter(Document.id.in_(doc_ids)).all()
        for row in rows:
            extracted_data = row.extracted_data if isinstance(row.extracted_data, dict) else {}
            pool_ctx = extracted_data.get("url_pool_context")
            if not isinstance(pool_ctx, dict):
                pool_ctx = {}
            pool_ctx.update(valid_context)
            extracted_data["url_pool_context"] = pool_ctx
            row.extracted_data = extracted_data
        session.commit()


def collect_urls_from_list(
    urls: List[str],
    *,
    project_key: Optional[str] = None,
    query_terms: Optional[List[str]] = None,
    extra_params: Optional[Dict[str, Any]] = None,
    enable_extraction: bool = True,
) -> Dict[str, Any]:
    """
    Fetch a given list of URLs and store as Document.
    Returns { inserted, skipped, urls }.
    """
    raw_count = len(urls) if isinstance(urls, list) else 0
    urls = _normalize_url_list(urls)
    normalized_count = len(urls)
    if not urls:
        source_template_health = _build_source_template_health_payload(_new_source_template_health_summary())
        frontdoor_status = _build_frontdoor_status_summary_payload(_new_frontdoor_status_summary())
        return {
            "inserted": 0,
            "skipped": 0,
            "urls": 0,
            "meta": {
                "source_template_health": source_template_health,
                "frontdoor_status_summary": frontdoor_status,
            },
            "debug": {
                "mode": "list",
                "raw_url_count": raw_count,
                "normalized_url_count": normalized_count,
                "filtered_out": max(0, raw_count - normalized_count),
                "note": "输入 URL 列表为空或全部被过滤（仅接受 http/https）",
                "source_template_health": source_template_health,
                "frontdoor_status_summary": frontdoor_status,
            },
        }

    normalized_terms = _normalize_terms(query_terms)
    job_params: Dict[str, Any] = {
        "mode": "list",
        "url_count": len(urls),
        "raw_url_count": raw_count,
        "normalized_url_count": normalized_count,
        "filtered_out": max(0, raw_count - normalized_count),
    }
    if normalized_terms:
        job_params["query_terms"] = normalized_terms
    if isinstance(extra_params, dict) and extra_params:
        for key in ("keywords", "search_keywords", "base_keywords", "topic_keywords", "provider", "language", "scope", "source", "source_filter", "domain"):
            if key in extra_params and key not in job_params:
                job_params[key] = extra_params.get(key)
        if "url_batch_path_mode" in extra_params:
            job_params["url_batch_path_mode"] = extra_params.get("url_batch_path_mode")
    job_id = start_job("url_pool_fetch", job_params)
    targets, target_mode = _resolve_runtime_targets(urls, extra_params=extra_params)
    dispatch_mode = _resolve_dispatch_mode(extra_params)
    url_batch_path_mode = _resolve_url_batch_path_mode(extra_params, dispatch_mode=dispatch_mode)
    strict_mode = _resolve_url_strict_mode(extra_params)
    frontdoor_options = _resolve_frontdoor_options(extra_params, project_key=project_key)
    runtime_targets: List[Tuple[str, Dict[str, Any]]] = []
    seen_runtime_urls: set[str] = set()
    for target in targets:
        target_url = _resolve_target_url(target, normalized_terms, extra_params=extra_params)
        if target_url in seen_runtime_urls:
            continue
        seen_runtime_urls.add(target_url)
        runtime_targets.append((target_url, target))
    return _collect_urls_from_list_with_runtime_targets(
        urls=urls,
        raw_count=raw_count,
        normalized_count=normalized_count,
        normalized_terms=normalized_terms,
        project_key=project_key,
        extra_params=extra_params,
        enable_extraction=enable_extraction,
        job_id=job_id,
        targets=targets,
        target_mode=target_mode,
        runtime_targets=runtime_targets,
        dispatch_mode=dispatch_mode,
        strict_mode=strict_mode,
        frontdoor_options=frontdoor_options,
        url_batch_path_mode=url_batch_path_mode,
    )
def collect_urls_from_pool(
    *,
    scope: str = "effective",
    project_key: Optional[str] = None,
    domain: Optional[str] = None,
    source_filter: Optional[str] = None,
    limit: int = _DEFAULT_LIMIT,
    query_terms: Optional[List[str]] = None,
    extra_params: Optional[Dict[str, Any]] = None,
    enable_extraction: bool = True,
) -> Dict[str, Any]:
    """
    Fetch URLs from resource pool, fetch each, store as Document.
    Returns { inserted, skipped, urls }.
    Ensures schema isolation when project_key is set.
    """
    from ..projects import bind_project

    normalized_terms = _normalize_terms(query_terms)
    job_params: Dict[str, Any] = {"scope": scope, "domain": domain, "source": source_filter, "limit": limit}
    if normalized_terms:
        job_params["query_terms"] = normalized_terms
    if isinstance(extra_params, dict) and extra_params:
        for key in ("keywords", "search_keywords", "base_keywords", "topic_keywords", "provider", "language"):
            if key in extra_params and key not in job_params:
                job_params[key] = extra_params.get(key)
    job_id = start_job("url_pool_fetch", job_params)
    try:
        from ..tasks import task_ingest_url_via_source_library

        items, total = list_urls(
            scope=scope,
            project_key=project_key,
            source=source_filter,
            domain=domain,
            page=1,
            page_size=min(limit, 100),
        )
        item_by_url = {x.get("url"): x for x in items if isinstance(x, dict) and x.get("url")}
        urls = [x.get("url") for x in items if x.get("url")]
        inserted = 0
        inserted_valid = 0
        skipped = 0
        rejected_count = 0
        rejection_breakdown: Dict[str, int] = {}
        skipped_invalid_url = 0
        skipped_exists = 0
        skipped_fetch_error = 0
        details: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        normalized_urls: List[str] = []
        pool_item_by_target: Dict[str, Dict[str, Any]] = {}
        for url in urls:
            nu = _normalize_url_no_fragment(str(url or ""))
            if not nu:
                continue
            normalized_urls.append(nu)
            if nu not in pool_item_by_target:
                pool_item_by_target[nu] = item_by_url.get(url) or {}
        targets, target_mode = _resolve_runtime_targets(normalized_urls, extra_params=extra_params)
        for target in targets:
            if bool(target.get("is_site_seed")) and target_mode != "site_only":
                continue
            tu = str(target.get("url") or "")
            if tu and tu in pool_item_by_target:
                continue
            pool_item_by_target[tu] = item_by_url.get(tu) or {}
        seen_runtime_urls: set[str] = set()
        dispatch_mode = _resolve_dispatch_mode(extra_params)
        strict_mode = _resolve_url_strict_mode(extra_params)
        frontdoor_options = _resolve_frontdoor_options(extra_params, project_key=project_key)
        workflow_name = "front_door_url_routing" if bool(frontdoor_options.get("enabled")) else (
            "url_routing_async" if dispatch_mode == "celery_async" else "url_routing"
        )
        runtime_targets: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
        for target in targets:
            target_url = _resolve_target_url(target, normalized_terms, extra_params=extra_params)
            if target_url in seen_runtime_urls:
                continue
            seen_runtime_urls.add(target_url)
            pool_item = pool_item_by_target.get(str(target.get("url") or "")) or {}
            if not target_url or not str(target_url).strip().startswith(("http://", "https://")):
                skipped += 1
                skipped_invalid_url += 1
                if len(details) < _DEBUG_MAX_URLS:
                    details.append(
                        _detail(
                            str(target_url or ""),
                            action="skip_invalid_url",
                            entry_type=target.get("entry_type"),
                            site_seed=bool(target.get("is_site_seed")),
                            pool_scope=pool_item.get("scope"),
                            pool_source=pool_item.get("source"),
                            pool_domain=pool_item.get("domain"),
                            pool_source_ref=pool_item.get("source_ref"),
                        )
                    )
                continue
            runtime_targets.append((target_url, target, pool_item))

        parallel_workers = _resolve_parallel_workers(extra_params=extra_params, target_count=len(runtime_targets))
        parallel_batch_size = _resolve_parallel_batch_size(extra_params=extra_params, parallel_workers=parallel_workers)
        metrics_summary = new_metrics_summary()
        source_template_health_summary = _new_source_template_health_summary()
        frontdoor_status_summary = _new_frontdoor_status_summary()
        queued = 0
        queued_tasks: List[Dict[str, Any]] = []

        def _run_single_target(target_url: str, target: Dict[str, Any]) -> Dict[str, Any]:
            try:
                search_options = _search_options_for_target(
                    target_url,
                    normalized_terms,
                    target=target,
                    extra_params=extra_params,
                )
                search_options = _apply_frontdoor_to_search_options(search_options, frontdoor_options)
                search_options = _apply_frontdoor_target_hint(
                    search_options=search_options,
                    frontdoor_options=frontdoor_options,
                    target_url=target_url,
                )
                search_options = dict(search_options or {})
                target_frontdoor_options = dict(frontdoor_options or {})
                target_frontdoor_options["enabled"] = True
                target_frontdoor_options["route_hint"] = str(search_options.get("frontdoor_route_hint") or "")
                target_frontdoor_options["fetch_strategy"] = str(search_options.get("frontdoor_fetch_strategy") or "")
                target_frontdoor_options["render_required"] = bool(search_options.get("frontdoor_render_required"))
                if isinstance(search_options.get("frontdoor_route_profile"), dict):
                    target_frontdoor_options["route_profile"] = dict(search_options.get("frontdoor_route_profile") or {})
                if isinstance(search_options.get("frontdoor_router_contract"), dict):
                    target_frontdoor_options["router_contract"] = dict(search_options.get("frontdoor_router_contract") or {})
                target_frontdoor_options["prefer_crawler"] = bool(search_options.get("frontdoor_prefers_crawler"))
                target_frontdoor_options["prefer_search_shell"] = bool(
                    search_options.get("frontdoor_prefers_search_shell")
                )
                return _run_source_library_frontdoor_ingress(
                    url=target_url,
                    project_key=project_key,
                    query_terms=normalized_terms,
                    search_options=search_options,
                    strict_mode=strict_mode,
                    frontdoor_options=target_frontdoor_options,
                    entrypoint="ingest.url_pool",
                    source_name="url_pool",
                    enable_extraction=bool(enable_extraction),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("url_pool url_routing dispatch failed for %s: %s", str(target_url)[:80], exc)
                return {"status": "failed", "inserted": 0, "skipped": 1, "error": _safe_exc(exc)}

        def _collect_item_result(target_url: str, target: Dict[str, Any], pool_item: Dict[str, Any], item_result: Dict[str, Any]) -> None:
            nonlocal inserted, inserted_valid, skipped, rejected_count, skipped_exists, skipped_fetch_error
            inserted += int(item_result.get("inserted") or 0)
            inserted_valid += int(item_result.get("inserted_valid") or 0)
            item_skipped = int(item_result.get("skipped") or 0)
            skipped += item_skipped
            rejected_count += int(item_result.get("rejected_count") or 0)
            _merge_rejection_breakdown(rejection_breakdown, item_result.get("rejection_breakdown"))
            record_metrics_observation(metrics_summary, item_result, fallback_adapter=workflow_name)
            _record_source_template_health_observation(
                source_template_health_summary,
                target=target,
                item_result=item_result,
            )
            degradation_flags = list(item_result.get("degradation_flags") or [])
            if "document_already_exists" in degradation_flags:
                skipped_exists += 1
            if "fetch_failed" in degradation_flags:
                skipped_fetch_error += 1
            if str(item_result.get("status") or "").strip().lower() == "failed" and len(errors) < _DEBUG_MAX_ERRORS:
                errors.append({"url": target_url, "error": str(item_result.get("error") or "url_routing_failed")})
            frontdoor_status = _build_frontdoor_status_projection(item_result)
            _record_frontdoor_status_observation(frontdoor_status_summary, frontdoor_status)

            context_doc_ids = _extract_doc_ids_from_ingest_result(item_result)
            _annotate_url_pool_context(
                doc_ids=context_doc_ids,
                context={
                    "mode": "pool",
                    "project_key": project_key,
                    "entry_type": target.get("entry_type"),
                    "site_seed": bool(target.get("is_site_seed")),
                    "scope": pool_item.get("scope"),
                    "source": pool_item.get("source"),
                    "domain": pool_item.get("domain") or target.get("domain"),
                    "source_ref": pool_item.get("source_ref"),
                },
            )

            if len(details) < _DEBUG_MAX_URLS:
                details.append(
                    _detail(
                        target_url,
                        action="inserted" if int(item_result.get("inserted") or 0) > 0 else "processed",
                        status=item_result.get("status"),
                        document_id=item_result.get("document_id"),
                        quality_score=item_result.get("quality_score"),
                        degradation_flags=degradation_flags,
                        entry_type=target.get("entry_type"),
                        site_seed=bool(target.get("is_site_seed")),
                        handler=item_result.get("handler_allocation", {}).get("handler_used")
                        if isinstance(item_result.get("handler_allocation"), dict)
                        else None,
                        matched_channel_key=item_result.get("handler_allocation", {}).get("matched_channel_key")
                        if isinstance(item_result.get("handler_allocation"), dict)
                        else None,
                        pool_scope=pool_item.get("scope"),
                        pool_source=pool_item.get("source"),
                        pool_domain=pool_item.get("domain"),
                        pool_source_ref=pool_item.get("source_ref"),
                        frontdoor_route=item_result.get("frontdoor_route")
                        if isinstance(item_result.get("frontdoor_route"), dict)
                        else None,
                        frontdoor_status=frontdoor_status,
                    )
                )

        if dispatch_mode == "celery_async":
            for target_url, target, pool_item in runtime_targets:
                search_options = _search_options_for_target(
                    target_url,
                    normalized_terms,
                    target=target,
                    extra_params=extra_params,
                )
                search_options = _apply_frontdoor_to_search_options(search_options, frontdoor_options)
                search_options = _apply_frontdoor_target_hint(
                    search_options=search_options,
                    frontdoor_options=frontdoor_options,
                    target_url=target_url,
                )
                async_result = task_ingest_url_via_source_library.delay(
                    target_url,
                    normalized_terms,
                    strict_mode,
                    project_key,
                    search_options,
                )
                queued += 1
                frontdoor_status = _build_frontdoor_status_projection(
                    {
                        "status": "degraded_success",
                        "reason_code": "queued_async",
                        "inserted_valid": 0,
                        "frontdoor_router_contract": search_options.get("frontdoor_router_contract")
                        if isinstance(search_options, dict)
                        else None,
                    }
                )
                _record_frontdoor_status_observation(frontdoor_status_summary, frontdoor_status)
                record_metrics_observation(
                    metrics_summary,
                    {
                        "inserted_valid": 0,
                        "single_write_workflow": workflow_name,
                        "reason_code": "queued_async",
                    },
                    fallback_adapter=workflow_name,
                )
                if len(queued_tasks) < _DEBUG_MAX_URLS:
                    queued_tasks.append(
                        _detail(
                            target_url,
                            action="queued",
                            task_id=getattr(async_result, "id", None),
                            entry_type=target.get("entry_type"),
                            site_seed=bool(target.get("is_site_seed")),
                            pool_scope=pool_item.get("scope"),
                            pool_source=pool_item.get("source"),
                            pool_domain=pool_item.get("domain"),
                            pool_source_ref=pool_item.get("source_ref"),
                            frontdoor_status=frontdoor_status,
                        )
                    )
        else:
            for batch in _batch_slice(runtime_targets, parallel_batch_size):
                if parallel_workers <= 1 or len(batch) <= 1:
                    for target_url, target, pool_item in batch:
                        item_result = _run_single_target(target_url, target)
                        _collect_item_result(target_url, target, pool_item, item_result)
                    continue
                with ThreadPoolExecutor(max_workers=min(parallel_workers, len(batch))) as executor:
                    future_to_target = {
                        executor.submit(copy_context().run, _run_single_target, tu, t): (tu, t, p)
                        for tu, t, p in batch
                    }
                    for future in as_completed(future_to_target):
                        tu, t, p = future_to_target[future]
                        item_result = future.result()
                        _collect_item_result(tu, t, p, item_result)

        result: Dict[str, Any] = {
            "inserted": inserted,
            "inserted_valid": inserted_valid,
            "skipped": skipped,
            "rejected_count": rejected_count,
            "rejection_breakdown": rejection_breakdown,
            "urls": len(urls),
            "pool_total": int(total or 0),
            "pool_returned": len(items),
            "skipped_invalid_url": skipped_invalid_url,
            "skipped_exists": skipped_exists,
            "skipped_fetch_error": skipped_fetch_error,
            "queued": queued,
            "single_write_workflow": workflow_name,
            "debug": {
                "mode": "pool",
                "dispatch_mode": dispatch_mode,
                "strict_mode": bool(strict_mode),
                "frontdoor_enabled": bool(frontdoor_options.get("enabled")),
                "disable_site_seed_expansion": bool(target_mode == "detail_only"),
                "target_mode": target_mode,
                "parallel_workers": parallel_workers,
                "parallel_batch_size": parallel_batch_size,
                "pool_total": int(total or 0),
                "pool_returned": len(items),
                "site_seed_count": len([x for x in targets if bool(x.get("is_site_seed"))]),
                "target_count": len(targets),
                "target_deduped_count": len(runtime_targets),
                "pool_items_sample": [
                    {
                        "id": x.get("id"),
                        "url": x.get("url"),
                        "scope": x.get("scope"),
                        "source": x.get("source"),
                        "domain": x.get("domain"),
                        "source_ref": x.get("source_ref"),
                    }
                    for x in (items[:_DEBUG_MAX_POOL_ITEMS] if items else [])
                ],
                "url_details": queued_tasks if dispatch_mode == "celery_async" else details,
                "url_details_truncated": len(runtime_targets) > len(queued_tasks if dispatch_mode == "celery_async" else details),
                "errors": errors,
            },
        }
        result["display_meta"] = build_display_meta(
            CollectRequest(
                channel="url_pool",
                project_key=project_key,
                urls=list(urls),
                query_terms=normalized_terms,
                scope=scope,
                limit=limit,
                source_context={"summary": "URL 池抓取并写入文档"},
            ),
            CollectResult(
                channel="url_pool",
                inserted=inserted,
                skipped=skipped,
                updated=0,
                status="completed",
                errors=errors,
            ),
            summary="URL 池抓取并写入文档",
        )
        metrics_payload = build_metrics_payload_from_summary(metrics_summary)
        attach_metrics_payload(result, metrics_payload)
        source_template_health = _build_source_template_health_payload(source_template_health_summary)
        _attach_source_template_health(result, source_template_health)
        frontdoor_status = _build_frontdoor_status_summary_payload(frontdoor_status_summary)
        _attach_frontdoor_status_summary(result, frontdoor_status)
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, _safe_exc(exc))
        raise
