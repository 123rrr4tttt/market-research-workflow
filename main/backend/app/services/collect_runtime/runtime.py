from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from dataclasses import replace
from math import ceil
from typing import Any

from .contracts import CollectRequest, CollectResult, FLOW_SOURCE_COLLECT
from .adapters.search_market import SearchMarketAdapter
from .adapters.search_policy import SearchPolicyAdapter
from .adapters.source_library import SourceLibraryAdapter, to_source_library_response
from .adapters.url_pool import UrlPoolAdapter
from .adapters.crawler_scrapy import CrawlerScrapyAdapter
from ..agent_batch.task_contract import parse_source_library_runtime_params


_ADAPTERS = {
    "search.market": SearchMarketAdapter(),
    "search.policy": SearchPolicyAdapter(),
    "source_library": SourceLibraryAdapter(),
    "url_pool": UrlPoolAdapter(),
    "crawler.scrapy": CrawlerScrapyAdapter(),
}

_AUTO_BATCH_CHANNELS = {"search.market", "search.policy"}
_DEFAULT_AUTO_BATCH_PARALLELISM = 1

_SKILL_REGISTRY: dict[str, Any] = {}


def _bootstrap_skill_registry() -> None:
    if _SKILL_REGISTRY:
        return
    for channel, adapter in _ADAPTERS.items():
        _SKILL_REGISTRY[channel] = adapter
        _SKILL_REGISTRY[f"collect.{channel}"] = adapter
        _SKILL_REGISTRY[f"skill.collect.{channel}"] = adapter


def register_collect_skill(skill_id: str, adapter: Any) -> None:
    sid = str(skill_id or "").strip()
    if not sid:
        raise ValueError("skill_id is required")
    _SKILL_REGISTRY[sid] = adapter


def list_collect_skills() -> list[str]:
    _bootstrap_skill_registry()
    return sorted(_SKILL_REGISTRY.keys())


def _resolve_collect_adapter(channel: str):
    _bootstrap_skill_registry()
    candidates = [
        str(channel or "").strip(),
        f"collect.{str(channel or '').strip()}",
        f"skill.collect.{str(channel or '').strip()}",
    ]
    for key in candidates:
        if key and key in _SKILL_REGISTRY:
            return _SKILL_REGISTRY[key]
    return None

# Environment-driven workflow boundary switch.
# - INGEST_WORKFLOW_ADAPTER: off|legacy -> legacy path (default)
# - INGEST_WORKFLOW_ADAPTER: on|workflow|canary -> use WorkflowRoutingAdapter boundary
# Read env directly (no settings dependency) and keep return types unchanged.
def _resolve_workflow_mode() -> str:
    # Local import for unit-safety and to avoid global side effects.
    import os  # unit-safe import

    raw = str(os.environ.get("INGEST_WORKFLOW_ADAPTER", "off") or "off").strip().lower()
    if raw in {"on", "workflow", "canary"}:
        return "workflow"
    # Treat anything else as legacy for safe rollback.
    return "legacy"


class WorkflowRoutingAdapter:
    """Adapter boundary for workflow-based routing.

    Thin indirection that preserves existing adapter return semantics while
    allowing future orchestration (Temporal/Dagster/etc.) behind an env switch.
    """

    def run(self, request: CollectRequest) -> CollectResult:
        adapter = _resolve_collect_adapter(request.channel)
        if adapter is None:
            raise ValueError(f"unsupported collect channel: {request.channel}")
        # Delegate to existing channel adapter. Keep result types and display_meta.
        return adapter.run(request)


def run_collect(request: CollectRequest) -> CollectResult:
    """Runtime entry.

    Routes to legacy adapter path or the workflow boundary based on
    INGEST_WORKFLOW_ADAPTER. Defaults to legacy for safe rollback.
    Auto-batch behavior and display_meta building are preserved.
    """
    mode = _resolve_workflow_mode()

    if mode == "legacy":
        # Legacy path (default): existing auto-batch + direct adapter dispatch.
        batched = _maybe_run_auto_batched(request)
        if batched is not None:
            return batched
        return _run_collect_no_batch(request)

    # Workflow boundary path: reuse the same batching rules, but delegate each
    # execution to WorkflowRoutingAdapter. Return types remain CollectResult.
    wr = WorkflowRoutingAdapter()
    batch_result = _run_auto_batch(request, wr.run)
    if batch_result is not None:
        return batch_result

    # No auto-batch; single-run through workflow boundary.
    return wr.run(request)


def _should_auto_batch(request: CollectRequest) -> bool:
    if request.channel not in _AUTO_BATCH_CHANNELS:
        return False
    qn = len([x for x in (request.query_terms or []) if str(x).strip()])
    lim = int(request.limit or 0)
    return qn >= 6 or lim >= 60


def _split_query_terms(terms: list[str]) -> list[list[str]]:
    clean = [str(x).strip() for x in (terms or []) if str(x).strip()]
    if not clean:
        return [[]]
    chunk_size = 4 if len(clean) >= 8 else 5
    return [clean[i : i + chunk_size] for i in range(0, len(clean), chunk_size)]


def _merge_collect_results(parent_request: CollectRequest, batch_results: list[tuple[list[str], CollectResult]]) -> CollectResult:
    out = CollectResult(channel=parent_request.channel, status="completed")
    links_seen: set[str] = set()
    merged_links: list[str] = []
    raw_batches: list[dict[str, Any]] = []
    provider_types: set[str] = set()
    provider_statuses: list[str] = []
    provider_job_ids: list[str] = []
    provider_jobs_seen: set[str] = set()
    attempts_total = 0
    has_attempt_count = False
    batches_failed = 0
    for terms, cr in batch_results:
        out.inserted += int(cr.inserted or 0)
        out.updated += int(cr.updated or 0)
        out.skipped += int(cr.skipped or 0)
        out.errors.extend(cr.errors or [])
        if str(cr.status or "").lower() == "failed":
            batches_failed += 1
        raw = dict((cr.meta or {}).get("raw") or {})
        batch_meta: dict[str, Any] = {"query_terms": terms, "result": raw}
        if cr.provider_job_id:
            batch_meta["provider_job_id"] = cr.provider_job_id
        if cr.provider_type:
            batch_meta["provider_type"] = cr.provider_type
            provider_types.add(cr.provider_type)
        if cr.provider_status:
            batch_meta["provider_status"] = cr.provider_status
            provider_statuses.append(cr.provider_status)
        if cr.attempt_count is not None:
            batch_meta["attempt_count"] = int(cr.attempt_count)
            attempts_total += int(cr.attempt_count)
            has_attempt_count = True
        if cr.provider_job_id and cr.provider_job_id not in provider_jobs_seen:
            provider_jobs_seen.add(cr.provider_job_id)
            provider_job_ids.append(cr.provider_job_id)
        raw_batches.append(batch_meta)
        for link in (raw.get("links") or []):
            s = str(link or "").strip()
            if s and s not in links_seen:
                links_seen.add(s)
                merged_links.append(s)
    raw_merged = {
        "inserted": out.inserted,
        "updated": out.updated,
        "skipped": out.skipped,
        "errors": out.errors,
        "auto_batched": True,
        "batches_total": len(batch_results),
        "batches_completed": len(batch_results),
        "batches_failed": batches_failed,
        "batches_succeeded": max(0, len(batch_results) - batches_failed),
        "batch_results": raw_batches,
    }
    if merged_links:
        raw_merged["links"] = merged_links
    if provider_job_ids:
        raw_merged["provider_job_ids"] = provider_job_ids
    if provider_types:
        raw_merged["provider_types"] = sorted(provider_types)
    if provider_statuses:
        raw_merged["provider_statuses"] = provider_statuses
    if has_attempt_count:
        raw_merged["attempt_count_total"] = attempts_total
    out.meta = {
        "raw": raw_merged,
        "auto_batched": True,
        "batches_total": len(batch_results),
        "batches_failed": batches_failed,
        "batches_succeeded": max(0, len(batch_results) - batches_failed),
        "query_term_batches": [terms for terms, _ in batch_results],
    }
    # Adapter-specific summary stays same; display_meta builder will fill standard stats.
    from .display_meta import build_display_meta
    summary = (parent_request.source_context or {}).get("summary")
    if len(provider_job_ids) == 1:
        out.provider_job_id = provider_job_ids[0]
    if len(provider_types) == 1:
        out.provider_type = next(iter(provider_types))
    if provider_statuses:
        unique_statuses = set(provider_statuses)
        out.provider_status = provider_statuses[0] if len(unique_statuses) == 1 else "mixed"
    if has_attempt_count:
        out.attempt_count = attempts_total
    out.display_meta = build_display_meta(parent_request, out, summary=summary)
    return out


def _run_collect_no_batch(request: CollectRequest) -> CollectResult:
    adapter = _resolve_collect_adapter(request.channel)
    if adapter is None:
        raise ValueError(f"unsupported collect channel: {request.channel}")
    return adapter.run(request)


def _maybe_run_auto_batched(request: CollectRequest) -> CollectResult | None:
    return _run_auto_batch(request, _run_collect_no_batch)


def _run_auto_batch(
    request: CollectRequest,
    runner: Any,
) -> CollectResult | None:
    if not _should_auto_batch(request):
        return None
    term_batches = _split_query_terms(request.query_terms)
    if len(term_batches) <= 1:
        return None
    per_batch_limit = max(10, int(ceil(max(1, int(request.limit or 20)) / len(term_batches))))
    fail_fast = _resolve_auto_batch_fail_fast(request)
    max_workers = min(len(term_batches), _resolve_auto_batch_parallelism(request))
    batch_results = _execute_auto_batch(request, term_batches, per_batch_limit, runner, max_workers=max_workers, fail_fast=fail_fast)
    merged = _merge_collect_results(request, batch_results)
    merged.meta = {
        **(merged.meta or {}),
        "batch_parallelism": max_workers,
        "batch_parallelism_requested": _resolve_auto_batch_parallelism(request),
        "batch_fail_fast": fail_fast,
    }
    raw_meta = dict((merged.meta or {}).get("raw") or {})
    raw_meta.update(
        {
            "batch_parallelism": max_workers,
            "batch_parallelism_requested": _resolve_auto_batch_parallelism(request),
            "batch_fail_fast": fail_fast,
        }
    )
    merged.meta["raw"] = raw_meta
    return merged


def _execute_auto_batch(
    request: CollectRequest,
    term_batches: list[list[str]],
    per_batch_limit: int,
    runner: Any,
    *,
    max_workers: int,
    fail_fast: bool,
) -> list[tuple[list[str], CollectResult]]:
    indexed_results: list[tuple[int, list[str], CollectResult]] = []
    if max_workers <= 1:
        for idx, terms in enumerate(term_batches):
            indexed_results.append((idx, terms, _run_single_auto_batch(request, terms, per_batch_limit, runner, fail_fast=fail_fast)))
        return [(terms, result) for idx, terms, result in sorted(indexed_results, key=lambda item: item[0])]

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="collect-auto-batch") as executor:
        future_map = {
            executor.submit(copy_context().run, _run_single_auto_batch, request, terms, per_batch_limit, runner, fail_fast): (idx, terms)
            for idx, terms in enumerate(term_batches)
        }
        for future in as_completed(future_map):
            idx, terms = future_map[future]
            indexed_results.append((idx, terms, future.result()))
    return [(terms, result) for idx, terms, result in sorted(indexed_results, key=lambda item: item[0])]


def _run_single_auto_batch(
    request: CollectRequest,
    terms: list[str],
    per_batch_limit: int,
    runner: Any,
    fail_fast: bool = False,
) -> CollectResult:
    sub = replace(
        request,
        query_terms=terms,
        limit=per_batch_limit,
        source_context={**(request.source_context or {}), "auto_batched_child": True},
    )
    try:
        return runner(sub)
    except Exception as exc:
        if fail_fast:
            raise
        return CollectResult(
            channel=request.channel,
            status="failed",
            errors=[
                {
                    "code": "auto_batch_execution_failed",
                    "message": str(exc) or exc.__class__.__name__,
                    "query_terms": list(terms),
                }
            ],
            meta={
                "raw": {
                    "auto_batched": True,
                    "query_terms": list(terms),
                    "exception_type": exc.__class__.__name__,
                    "failed": True,
                }
            },
        )


def _resolve_auto_batch_parallelism(request: CollectRequest) -> int:
    options = request.options if isinstance(request.options, dict) else {}
    source_context = request.source_context if isinstance(request.source_context, dict) else {}
    raw = options.get("batch_parallelism", source_context.get("batch_parallelism", _DEFAULT_AUTO_BATCH_PARALLELISM))
    try:
        return max(1, int(raw))
    except Exception:
        return _DEFAULT_AUTO_BATCH_PARALLELISM


def _resolve_auto_batch_fail_fast(request: CollectRequest) -> bool:
    options = request.options if isinstance(request.options, dict) else {}
    source_context = request.source_context if isinstance(request.source_context, dict) else {}
    raw = options.get("batch_fail_fast", source_context.get("batch_fail_fast", False))
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_query_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


def normalize_urls(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for x in value:
        s = str(x or "").strip()
        if s.startswith(("http://", "https://")):
            out.append(s)
    return out


def normalize_limit(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return max(1, int(value))
    except Exception:
        return default


def normalize_language(value: Any) -> str | None:
    s = str(value or "").strip().lower()
    return s or None


def normalize_provider(value: Any) -> str | None:
    s = str(value or "").strip().lower()
    return s or None


def collect_request_from_market_api(*, query_terms: list[str], max_items: int, project_key: str | None, provider: str | None = None, language: str | None = None, start_offset: int | None = None, days_back: int | None = None, enable_extraction: bool = True) -> CollectRequest:
    return CollectRequest(
        channel="search.market",
        project_key=project_key,
        query_terms=normalize_query_terms(query_terms),
        limit=normalize_limit(max_items, 20),
        provider=normalize_provider(provider),
        language=normalize_language(language) or "en",
        options={"start_offset": start_offset, "days_back": days_back, "enable_extraction": enable_extraction},
        source_context={"summary": "市场信息采集"},
    )


def collect_request_from_policy_api(*, query_terms: list[str], max_items: int, project_key: str | None, provider: str | None = None, language: str | None = None, start_offset: int | None = None, days_back: int | None = None, enable_extraction: bool = True) -> CollectRequest:
    return CollectRequest(
        channel="search.policy",
        project_key=project_key,
        query_terms=normalize_query_terms(query_terms),
        limit=normalize_limit(max_items, 20),
        provider=normalize_provider(provider),
        language=normalize_language(language) or "en",
        options={"start_offset": start_offset, "days_back": days_back, "enable_extraction": enable_extraction},
        source_context={"summary": "法规来源"},
    )


def collect_request_from_source_library_api(*, item_key: str, project_key: str | None, override_params: dict | None = None) -> CollectRequest:
    parsed = parse_source_library_runtime_params(override_params)
    return CollectRequest(
        flow=FLOW_SOURCE_COLLECT,
        channel="source_library",
        project_key=project_key,
        item_key=str(item_key or "").strip() or None,
        query_terms=list(parsed.get("query_terms") or []),
        urls=list(parsed.get("urls") or []),
        limit=parsed.get("limit"),
        provider=parsed.get("provider"),
        language=parsed.get("language"),
        scope=parsed.get("scope"),
        platforms=parsed.get("platforms"),
        options={"override_params": dict(parsed.get("override_params") or {})},
        source_context={"summary": f"执行来源项 {item_key}"},
    )


def collect_request_from_url_pool(
    *,
    project_key: str | None,
    urls: list[str] | None = None,
    scope: str | None = None,
    limit: int | None = None,
    source_filter: str | None = None,
    domain: str | None = None,
    query_terms: list[str] | None = None,
    options: dict[str, Any] | None = None,
) -> CollectRequest:
    extra_options = dict(options or {})
    if source_filter is not None:
        extra_options["source_filter"] = source_filter
    if domain is not None:
        extra_options["domain"] = domain
    return CollectRequest(
        channel="url_pool",
        project_key=project_key,
        urls=normalize_urls(urls or []),
        query_terms=normalize_query_terms(query_terms or []),
        scope=(str(scope).strip() if scope else None),
        limit=normalize_limit(limit, 50),
        options=extra_options,
        source_context={"summary": "URL 池抓取并写入文档"},
    )


def run_source_library_item_compat(*, item_key: str, project_key: str | None = None, override_params: dict | None = None) -> dict:
    req = collect_request_from_source_library_api(item_key=item_key, project_key=project_key, override_params=override_params)
    result = run_collect(req)
    response = to_source_library_response(result)
    if isinstance(response, dict):
        response.setdefault("display_meta", result.display_meta)
    return response
