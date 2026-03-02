"""URL pool channel: fetch URLs from channel or resource pool and ingest as documents."""

from __future__ import annotations

import logging
from contextlib import nullcontext
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

from ...models.base import SessionLocal
from ...models.entities import Document
from ..job_logger import complete_job, fail_job, start_job
from ..collect_runtime.display_meta import build_display_meta
from ..collect_runtime.contracts import CollectRequest, CollectResult
from ..resource_pool import list_urls
from ..extraction.application import ExtractionApplicationService
from .meaningful_gate import normalize_content_for_ingest
from .adapters.http_utils import make_html_parser

logger = logging.getLogger(__name__)

_SOURCE_NAME = "url_pool"
_SOURCE_KIND = "url_fetch"
_DOC_TYPE = "url_fetch"
_DEFAULT_LIMIT = 50
_DEBUG_MAX_URLS = 200
_DEBUG_MAX_POOL_ITEMS = 50
_DEBUG_MAX_ERRORS = 50
_EXTRACTION_APP = ExtractionApplicationService()
_ENTRY_QUERY_KEYS = {"q", "query", "keyword", "keywords", "search", "s", "term"}


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
    enriched = None
    try:
        enriched = _EXTRACTION_APP.extract_structured_enriched(
            "\n\n".join([x for x in [domain_str, content or ""] if x]),
            include_market=True,
            include_policy=True,
            include_sentiment=True,
            include_company=True,
            include_product=True,
            include_operation=True,
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("url_pool extraction failed for %s: %s", url[:80], ex)
        extracted_data["extraction_status"] = "failed"
        extracted_data["extraction_reason"] = "extractor_exception"
        extracted_data["extraction_error"] = _safe_exc(ex)
        return

    if isinstance(enriched, dict) and enriched:
        extracted_data.update(enriched)
        extracted_data["extraction_status"] = "ok"
        return

    extracted_data["extraction_status"] = "failed"
    extracted_data["extraction_reason"] = "empty_structured_output"


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


def _search_options_for_target(target_url: str, query_terms: List[str]) -> Dict[str, Any] | None:
    parsed = urlparse(str(target_url or ""))
    path = str(parsed.path or "").lower()
    query_pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    query_keys = {str(k or "").strip().lower() for k, _ in query_pairs if str(k or "").strip()}
    is_search_like = bool("/search" in path or bool(query_keys & _ENTRY_QUERY_KEYS))
    if not is_search_like:
        return None
    limit = 1 if query_terms else 0
    return {
        "search_expand": bool(limit > 0),
        "search_expand_limit": max(1, limit) if limit > 0 else 1,
        "search_provider": "auto",
        "search_fallback_provider": "ddg_html",
        "fallback_on_insufficient": True,
        "target_candidates": 6,
        "min_results_required": 6,
        "decode_redirect_wrappers": True,
        "filter_low_value_candidates": True,
    }


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


def _resolve_target_url(target: Dict[str, Any], query_terms: List[str]) -> str:
    raw = str(target.get("url") or "").strip()
    if not raw:
        return raw
    if "{{q}}" not in raw:
        return raw
    first_term = ""
    if isinstance(query_terms, list) and query_terms:
        first_term = str(query_terms[0] or "").strip()
    encoded = quote_plus(first_term) if first_term else ""
    return raw.replace("{{q}}", encoded)


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
        return {
            "inserted": 0,
            "skipped": 0,
            "urls": 0,
            "debug": {
                "mode": "list",
                "raw_url_count": raw_count,
                "normalized_url_count": normalized_count,
                "filtered_out": max(0, raw_count - normalized_count),
                "note": "输入 URL 列表为空或全部被过滤（仅接受 http/https）",
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
    job_id = start_job("url_pool_fetch", job_params)
    try:
        from ..projects import bind_project
        from .single_url import ingest_single_url

        inserted = 0
        skipped = 0
        skipped_exists = 0
        skipped_fetch_error = 0
        details: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        targets = _build_site_first_targets(urls)
        seen_runtime_urls: set[str] = set()

        ctx = bind_project(project_key) if project_key else nullcontext()
        with ctx:
            for target in targets:
                target_url = _resolve_target_url(target, normalized_terms)
                if target_url in seen_runtime_urls:
                    continue
                seen_runtime_urls.add(target_url)
                try:
                    search_options = _search_options_for_target(target_url, normalized_terms)
                    item_result = ingest_single_url(
                        url=target_url,
                        query_terms=normalized_terms,
                        strict_mode=False,
                        search_options=search_options,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("url_pool single_url dispatch failed for %s: %s", target_url[:80], exc)
                    item_result = {"status": "failed", "inserted": 0, "skipped": 1, "error": _safe_exc(exc)}

                inserted += int(item_result.get("inserted") or 0)
                item_skipped = int(item_result.get("skipped") or 0)
                skipped += item_skipped
                degradation_flags = list(item_result.get("degradation_flags") or [])
                if "document_already_exists" in degradation_flags:
                    skipped_exists += 1
                if "fetch_failed" in degradation_flags:
                    skipped_fetch_error += 1
                if str(item_result.get("status") or "").strip().lower() == "failed" and len(errors) < _DEBUG_MAX_ERRORS:
                    errors.append({"url": target_url, "error": str(item_result.get("error") or "single_url_failed")})

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
                        )
                    )

        result: Dict[str, Any] = {
            "inserted": inserted,
            "skipped": skipped,
            "urls": len(urls),
            "skipped_exists": skipped_exists,
            "skipped_fetch_error": skipped_fetch_error,
            "debug": {
                "mode": "list",
                "raw_url_count": raw_count,
                "normalized_url_count": normalized_count,
                "filtered_out": max(0, raw_count - normalized_count),
                "site_seed_count": len([x for x in targets if bool(x.get("is_site_seed"))]),
                "target_count": len(targets),
                "url_details": details,
                "url_details_truncated": len(targets) > len(details),
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
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, _safe_exc(exc))
        raise


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
        from .single_url import ingest_single_url

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
        skipped = 0
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
        targets = _build_site_first_targets(normalized_urls)
        for target in targets:
            if bool(target.get("is_site_seed")):
                continue
            tu = str(target.get("url") or "")
            if tu and tu in pool_item_by_target:
                continue
            pool_item_by_target[tu] = item_by_url.get(tu) or {}
        seen_runtime_urls: set[str] = set()

        ctx = bind_project(project_key) if project_key else nullcontext()
        with ctx:
            for target in targets:
                target_url = _resolve_target_url(target, normalized_terms)
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

                try:
                    search_options = _search_options_for_target(target_url, normalized_terms)
                    item_result = ingest_single_url(
                        url=target_url,
                        query_terms=normalized_terms,
                        strict_mode=False,
                        search_options=search_options,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("url_pool single_url dispatch failed for %s: %s", str(target_url)[:80], exc)
                    item_result = {"status": "failed", "inserted": 0, "skipped": 1, "error": _safe_exc(exc)}

                inserted += int(item_result.get("inserted") or 0)
                item_skipped = int(item_result.get("skipped") or 0)
                skipped += item_skipped
                degradation_flags = list(item_result.get("degradation_flags") or [])
                if "document_already_exists" in degradation_flags:
                    skipped_exists += 1
                if "fetch_failed" in degradation_flags:
                    skipped_fetch_error += 1
                if str(item_result.get("status") or "").strip().lower() == "failed" and len(errors) < _DEBUG_MAX_ERRORS:
                    errors.append({"url": target_url, "error": str(item_result.get("error") or "single_url_failed")})

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
                        )
                    )

        result: Dict[str, Any] = {
            "inserted": inserted,
            "skipped": skipped,
            "urls": len(urls),
            "pool_total": int(total or 0),
            "pool_returned": len(items),
            "skipped_invalid_url": skipped_invalid_url,
            "skipped_exists": skipped_exists,
            "skipped_fetch_error": skipped_fetch_error,
            "debug": {
                "mode": "pool",
                "pool_total": int(total or 0),
                "pool_returned": len(items),
                "site_seed_count": len([x for x in targets if bool(x.get("is_site_seed"))]),
                "target_count": len(targets),
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
                "url_details": details,
                "url_details_truncated": len(targets) > len(details),
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
        complete_job(job_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, _safe_exc(exc))
        raise
