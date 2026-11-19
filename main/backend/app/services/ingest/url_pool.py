"""URL pool channel: fetch URLs from channel or resource pool and ingest as materials."""

from __future__ import annotations

import logging
import os
from contextlib import nullcontext
from importlib import import_module
from collections.abc import Callable
from typing import NoReturn, Protocol, TypeGuard
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import ingest_operation_failures

from ...models.entities import Material
from .content_extraction import locate_main_text_from_html
from .frontdoor_router_contract import build_frontdoor_fetch_router_contract, router_contract_from_profile
from .content_cleaner import normalize_content_for_ingest
from .source_search_contract import build_query_url_from_contract, normalize_source_search_contract
from .url_unwrap import unwrap_url
from app.successor_runtime.capabilities.acquisition_url import (
    UrlSingleUrlOutcome,
    UrlSingleUrlRequest,
    UrlSingleUrlStatus,
)
from app.successor_runtime.capabilities.checksum import CanonicalJsonObject, CanonicalJsonValue
from app.successor_runtime.runtime.ports import ProjectScopeRef

logger = logging.getLogger(__name__)

__all__ = ["_extract_text_from_html"]

JsonObject = dict[str, object]


class _DatabaseRow(Protocol):
    @property
    def extracted_data(self) -> object: ...
    @extracted_data.setter
    def extracted_data(self, value: object) -> None: ...


class _DatabaseQuery(Protocol):
    def filter(self, criterion: object) -> "_DatabaseQuery": ...
    def all(self) -> list[_DatabaseRow]: ...


class _DatabaseSession(Protocol):
    def query(self, entity: type[Material]) -> _DatabaseQuery: ...
    def commit(self) -> None: ...


class _DatabaseSessionContext(Protocol):
    def __enter__(self) -> _DatabaseSession: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> object: ...


def _is_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_dict(value: object) -> TypeGuard[JsonObject]:
    return _is_dict(value) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_session_factory(value: object) -> TypeGuard[Callable[[], _DatabaseSessionContext]]:
    return callable(value)


def _is_list_urls(value: object) -> TypeGuard[Callable[..., tuple[list[JsonObject], int]]]:
    return callable(value)


def _as_object_dict(value: object) -> JsonObject:
    if not _is_dict(value):
        return {}
    return {str(key): item for key, item in value.items()}


def _as_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _as_object_list(value: object) -> list[object]:
    if not _is_object_list(value):
        return []
    return list(value)


def _as_text_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [_as_text(item).strip() for item in value]


def _as_bool_value(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


_DEFAULT_LIMIT = 50
_DEBUG_MAX_POOL_ITEMS = 50
_FRONTDOOR_ROUTE_PROFILE_CONTRACT_VERSION = "ingest.frontdoor_route_profile.v1"
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


def _open_session() -> _DatabaseSessionContext:
    module = import_module("app.models.base")
    factory = getattr(module, "SessionLocal")
    if not _is_session_factory(factory):
        # kit:boundary owner=ingest.url_pool.dynamic_ports class=PROGRAMMER_DEFECT failure_family=none witness=test:test_url_pool_dynamic_database_ports_reject_incompatible_bindings
        raise TypeError("SessionLocal has an incompatible callable contract")
    return factory()


def list_urls(
    *,
    scope: str = "effective",
    project_key: str | None = None,
    source: str | None = None,
    domain: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[JsonObject], int]:
    module = import_module("app.services.resource_pool.resolver")
    list_urls = getattr(module, "list_urls")
    if not _is_list_urls(list_urls):
        # kit:boundary owner=ingest.url_pool.dynamic_ports class=PROGRAMMER_DEFECT failure_family=none witness=test:test_url_pool_dynamic_database_ports_reject_incompatible_bindings
        raise TypeError("list_urls has an incompatible callable contract")
    result: tuple[list[JsonObject], int] = list_urls(
        scope=scope,
        project_key=project_key,
        source=source,
        domain=domain,
        page=page,
        page_size=page_size,
    )
    return result


def _normalize_url_list(urls: object) -> List[str]:
    """Extract and normalize URL list from channel/params."""
    return [u for u in _as_text_list(urls) if u.startswith(("http://", "https://"))]
    return []


def _normalize_terms(value: object) -> List[str]:
    return [x for x in _as_text_list(value) if x]
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    return []


def _resolve_source_search_contract_for_target(
    *,
    target_url: str,
    target: JsonObject | None,
    extra_params: JsonObject | None,
) -> JsonObject | None:
    if isinstance(target, dict) and _is_object_dict(target.get("source_search_contract")):
        return _as_object_dict(target.get("source_search_contract"))
    if not _is_object_dict(extra_params):
        return None

    direct = extra_params.get("source_search_contract")
    if _is_object_dict(direct):
        return _as_object_dict(direct)

    mapped = extra_params.get("source_search_contracts")
    if _is_object_dict(mapped):
        key_exact = str(target_url or "").strip()
        key_norm = _normalize_url_no_fragment(key_exact)
        domain_key = _domain_key(key_exact)
        for key in (key_exact, key_norm, domain_key):
            if key and _is_object_dict(mapped.get(key)):
                return _as_object_dict(mapped.get(key))

    top_level: JsonObject = {}
    for field in _SOURCE_SEARCH_CONTRACT_FIELDS:
        if field in extra_params:
            top_level[field] = extra_params.get(field)
    return top_level or None


def _search_options_for_target(
    target_url: str,
    query_terms: List[str],
    *,
    target: JsonObject | None = None,
    extra_params: JsonObject | None = None,
) -> JsonObject | None:
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
    max_candidates = _as_int((contract or {}).get("max_candidates"), 6)
    min_results_required = _as_int((contract or {}).get("min_results_required"), 6)
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


def _frontdoor_route_profile_for_url(url: str) -> JsonObject:
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


def _apply_frontdoor_target_hint(
    *,
    search_options: JsonObject | None,
    frontdoor_options: JsonObject,
    target_url: str,
) -> JsonObject | None:
    out: JsonObject = dict(search_options or {})
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
        out["frontdoor_router_contract"] = _as_object_dict(route_profile.get("router_contract"))
    return out


def execute_single_url_kernel(
    *,
    url: str,
    project_key: Optional[str] = None,
    query_terms: Optional[List[str]] = None,
    extra_params: Optional[JsonObject] = None,
    enable_extraction: bool = True,
    target: Optional[JsonObject] = None,
    context: Optional[JsonObject] = None,
) -> JsonObject:
    """Execute one prepared URL through fetch and the Material writer."""
    target_url = str(url or "").strip()
    default_target: JsonObject = {
        "url": target_url,
        "entry_type": "detail",
        "domain": _domain_key(target_url),
        "from_url": target_url,
        "is_site_seed": False,
    }
    target_metadata = target if _is_object_dict(target) else default_target
    normalized_terms = _normalize_terms(query_terms)
    strict_mode = _resolve_url_strict_mode(extra_params)
    frontdoor_options = _resolve_frontdoor_options(extra_params)
    try:
        search_options = _search_options_for_target(
            target_url,
            normalized_terms,
            target=target_metadata,
            extra_params=extra_params,
        )
        search_options = _apply_frontdoor_to_search_options(search_options, frontdoor_options)
        search_options = _apply_frontdoor_target_hint(
            search_options=search_options,
            frontdoor_options=frontdoor_options,
            target_url=target_url,
        )
        search_options = _as_object_dict(search_options)
        target_frontdoor_options = _as_object_dict(frontdoor_options)
        target_frontdoor_options["enabled"] = True
        target_frontdoor_options["route_hint"] = str(search_options.get("frontdoor_route_hint") or "")
        target_frontdoor_options["fetch_strategy"] = str(search_options.get("frontdoor_fetch_strategy") or "")
        target_frontdoor_options["render_required"] = bool(search_options.get("frontdoor_render_required"))
        if isinstance(search_options.get("frontdoor_route_profile"), dict):
            target_frontdoor_options["route_profile"] = _as_object_dict(search_options.get("frontdoor_route_profile"))
        if isinstance(search_options.get("frontdoor_router_contract"), dict):
            target_frontdoor_options["router_contract"] = _as_object_dict(search_options.get("frontdoor_router_contract"))
        target_frontdoor_options["prefer_crawler"] = bool(search_options.get("frontdoor_prefers_crawler"))
        target_frontdoor_options["prefer_search_shell"] = bool(
            search_options.get("frontdoor_prefers_search_shell")
        )
        result = _run_source_library_frontdoor_ingress(
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
    _annotate_url_pool_context(
        material_ids=_extract_material_ids_from_ingest_result(result),
        context=context if _is_object_dict(context) else {},
    )
    return result


def invoke_url_single_url(request: UrlSingleUrlRequest) -> UrlSingleUrlOutcome:
    """Bind one prepared single-URL request to the existing Material kernel."""

    result = execute_single_url_kernel(
        url=request.url,
        project_key=request.project_key,
        query_terms=list(request.query_terms),
        extra_params=dict(request.extra_params),
        enable_extraction=request.enable_extraction,
        target=dict(request.target) if request.target else None,
        context=dict(request.context) if request.context else None,
    )
    return UrlSingleUrlOutcome(
        status=_url_single_url_status(result.get("status")),
        inserted=_as_int(result.get("inserted")),
        updated=_as_int(result.get("updated")),
        skipped=_as_int(result.get("skipped")),
        material_id=_as_int(result.get("material_id")) or None,
        error=_as_text(result.get("error")) or None,
        task_id=_url_single_url_task_id(result),
        readback=_url_single_url_readback(result),
    )


def _url_single_url_status(value: object) -> UrlSingleUrlStatus:
    raw = _as_text(value).strip().lower()
    if raw == "failed":
        return "failed"
    if raw == "cancelled":
        return "cancelled"
    if raw == "accepted":
        return "accepted"
    if raw == "partial":
        return "partial"
    if raw == "degraded_success":
        return "partial"
    if raw in {"success", "completed"}:
        return "completed"
    return "unknown"


def _url_single_url_task_id(result: JsonObject) -> str | None:
    canary = _as_object_dict(result.get("canary_handoff"))
    frontdoor_run = _as_object_dict(canary.get("frontdoor_run"))
    trace_id = frontdoor_run.get("trace_id")
    return trace_id if isinstance(trace_id, str) and trace_id else None


def _url_single_url_readback(result: JsonObject) -> CanonicalJsonObject:
    readback: dict[str, CanonicalJsonValue] = {}
    canary = _as_object_dict(result.get("canary_handoff"))
    handoff_state = canary.get("handoff_state")
    if isinstance(handoff_state, str):
        readback["handoff_state"] = handoff_state
    closure_claim = canary.get("closure_claim")
    if isinstance(closure_claim, bool):
        readback["closure_claim"] = closure_claim
    frontdoor_run = _as_object_dict(canary.get("frontdoor_run"))
    trace_id = frontdoor_run.get("trace_id")
    if isinstance(trace_id, str):
        readback["trace_id"] = trace_id
    reason_code = result.get("reason_code")
    if isinstance(reason_code, str):
        readback["reason_code"] = reason_code
    return readback


def _url_single_url_input_failure(
    request: UrlSingleUrlRequest,
    scope: ProjectScopeRef,
    capability_id: str,
) -> Failure | None:
    """Return the typed failure for an invalid installed single-URL binding."""

    from app.successor_runtime.capabilities.acquisition_url import URL_SINGLE_URL_OWNER

    if request.project_key != scope.project_key:
        reason_code = "project_scope_mismatch"
        message = "URL single-URL request crosses the installed project scope"
    elif capability_id != URL_SINGLE_URL_OWNER:
        reason_code = "capability_drift"
        message = "URL single-URL request capability drift"
    else:
        return None
    return ingest_operation_failures.fail(
        "url_pool_collection_failed",
        message,
        {
            "operation": "ingest.url_pool.validate_single_url_input",
            "reason_code": reason_code,
            "request_project_key": request.project_key,
            "scope_project_key": scope.project_key,
            "capability_id": capability_id,
            "expected_capability_id": URL_SINGLE_URL_OWNER,
            "public_exception": "ValueError",
            "public_message": message,
        },
    )


def _raise_url_single_url_input_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    required = {
        "operation",
        "reason_code",
        "request_project_key",
        "scope_project_key",
        "capability_id",
        "expected_capability_id",
        "public_exception",
        "public_message",
    }
    if (
        not ingest_operation_failures.matches(failure)
        or failure.code != "url_pool_collection_failed"
        or required - set(context)
        or context.get("public_exception") != "ValueError"
    ):
        # kit:boundary owner=ingest.url_pool.single_url_input class=PROGRAMMER_DEFECT failure_family=none witness=test:test_url_single_url_input_validation_preserves_typed_scope_and_capability_failures
        raise TypeError("URL single-URL input failure lift context is invalid")
    # kit:boundary owner=ingest.url_pool.single_url_input class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=ingest.operation.failure witness=test:test_url_single_url_input_validation_preserves_typed_scope_and_capability_failures
    raise ValueError(str(context["public_message"]))


def validate_url_single_url_input(
    request: UrlSingleUrlRequest,
    scope: ProjectScopeRef,
    capability_id: str,
) -> None:
    """Reject a single-URL request that crosses the installed project scope."""

    failure = _url_single_url_input_failure(request, scope, capability_id)
    if failure is not None:
        _raise_url_single_url_input_failure(failure)


def _extract_text_from_html(html: str) -> str:
    """Extract main text from HTML for storage."""
    try:
        return locate_main_text_from_html(
            html,
            selectors=("article", "main article", "[role='main'] article", "main"),
            transform=lambda text: normalize_content_for_ingest(text, max_chars=50000),
        )
    except Exception:  # noqa: BLE001
        return ""


def _build_material_candidate_from_record(record: JsonObject) -> JsonObject:
    url = str(record.get("url") or "").strip()
    parsed = urlparse(url)
    source_base_url = None
    if parsed.scheme and parsed.netloc:
        source_base_url = f"{parsed.scheme}://{parsed.netloc}"
    content_text = str(record.get("content_text") or "").strip()
    summary = str(record.get("summary") or "").strip() or None
    if not summary and content_text:
        summary = content_text[:800]
    record_meta = _as_object_dict(record.get("record_meta"))
    extracted_data_base: JsonObject = {
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
        "material_type": "url_fetch",
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
    search_options: Optional[JsonObject] = None,
    strict_mode: bool = False,
    frontdoor_options: Optional[JsonObject] = None,
    entrypoint: str = "ingest.url_pool",
    source_name: str = "url_pool",
    enable_extraction: bool = True,
) -> JsonObject:
    from ..projects import bind_project
    from ..source_library.orchestrators.url_execution import fetch_routed_targets
    from ..source_library.resolver import as_optional_int, list_effective_channels
    from ..source_library.types import (
        FrontDoorExecutionProtocol,
        build_source_concurrency_plan,
        source_concurrency_plan_to_dict,
    )
    from .frontdoor_ingress import build_frontdoor_ingress_envelope
    from .postprocess_frontdoor import run_postprocess_frontdoor

    normalized_url = str(url or "").strip()
    params: JsonObject = {
        "urls": [normalized_url],
        "query_terms": list(query_terms or []),
        "strict_mode": bool(strict_mode),
    }
    if _is_object_dict(search_options) and search_options:
        params.update(_as_object_dict(search_options))
    if _is_object_dict(frontdoor_options):
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
            params["frontdoor_route_profile"] = _as_object_dict(frontdoor_options.get("route_profile"))
        if isinstance(frontdoor_options.get("router_contract"), dict):
            params["frontdoor_router_contract"] = _as_object_dict(frontdoor_options.get("router_contract"))

    channels: list[JsonObject] = list_effective_channels(scope="effective", project_key=project_key)
    channel_map = {
        _as_text(channel.get("channel_key")).strip(): _as_object_dict(channel)
        for channel in channels
        if channel.get("channel_key")
    }

    concurrency_plan = build_source_concurrency_plan(
        params={key: value for key, value in params.items()},
        total_search_tasks=0,
        total_url_tasks=1,
    )
    protocol = FrontDoorExecutionProtocol(
        item_key=source_name or "url_pool",
        item_channel_key="url_pool",
        project_key=project_key,
        front_door_owner="run_item_payload",
        execution_mode="url_routing",
        write_mode="front_door_url_routing",
        route_decision="front_door_url_routing",
        query_terms=list(query_terms or []),
        site_entries=[],
        candidate_urls=[normalized_url],
        expected_entry_type=None,
        write_to_pool=_as_bool(params.get("write_to_pool"), True),
        auto_ingest=_as_bool(params.get("auto_ingest"), True),
        ingest_limit=max(
            1,
            as_optional_int(params.get("ingest_limit") or params.get("limit")) or 20,
        ),
        force_url_routing_flow=_as_bool(params.get("force_url_routing_flow"), True),
        prefer_crawler_first=_as_bool(params.get("prefer_crawler_first"), False) and not _as_bool(
            params.get("force_url_routing_flow"), True
        ),
        search_parallelism=concurrency_plan.search.parallelism,
        routing_parallelism=concurrency_plan.url.parallelism,
        concurrency_plan=source_concurrency_plan_to_dict(concurrency_plan),
        source_tier="",
        onboarding_priority="",
    )

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        open_params: dict[object, object] = {key: value for key, value in params.items()}
        routed = fetch_routed_targets(
            protocol=protocol,
            item_channel_key=protocol.item_channel_key,
            params=open_params,
            project_key=project_key,
            channel_map=channel_map,
            runtime_targets=[(normalized_url, {"source": "params.urls", "index": 0})],
            execution_layer="terminal_output_only",
        )

    records = _as_object_list(routed.get("records"))
    errors = [_as_text(x) for x in _as_object_list(routed.get("errors")) if _as_text(x).strip()]
    by_url = _as_object_list(routed.get("by_url"))
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
            "material_id": None,
            "quality_score": 0.0,
            "errors": errors,
            "error": reason,
            "records": [],
            "by_url": by_url,
            "frontdoor_route": frontdoor_route,
            "single_write_workflow": "source_library_frontdoor",
            "source_library_collect_only": True,
        }

    record = _as_object_dict(records[0])
    material_candidate = _build_material_candidate_from_record(record)
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
            "router_state": _as_object_dict(frontdoor_route.get("router_contract")).get("router_state"),
            "router_reason_code": _as_object_dict(frontdoor_route.get("router_contract")).get("reason_code"),
        },
        collection_payload={
            "material_candidate": material_candidate,
            "frontdoor_route": frontdoor_route,
            "terminal_context": {
                "platform": source_name,
                "ingestion_entrypoint": entrypoint,
                "source_mode": "url_execution",
                "strict_mode": bool(strict_mode),
                "quality_score": 0.0,
                "degradation_flags": [],
                "http_status": _as_object_dict(record.get("record_meta")).get("http_status"),
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
    data = _as_object_dict(frontdoor_result.get("data"))
    writer_result = _as_object_dict(data.get("writer_result"))
    meta = _as_object_dict(frontdoor_result.get("meta"))
    quality_gates = _as_object_dict(data.get("quality_gates"))
    gate_config = _as_object_dict(quality_gates.get("gate_config"))
    guardrail_rollout = _as_object_dict(gate_config.get("guardrail_rollout"))
    canary_handoff = _as_object_dict(data.get("canary_handoff"))
    admission = _as_text(data.get("admission")).strip().lower()
    inserted = _as_int(writer_result.get("inserted"))
    skipped = _as_int(writer_result.get("skipped"), 0 if inserted > 0 else 1)
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
        "material_id": writer_result.get("material_id"),
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
    search_options: Optional[JsonObject] = None,
    strict_mode: bool = False,
    frontdoor_options: Optional[JsonObject] = None,
    entrypoint: str = "ingest.url_pool",
    source_name: str = "url_pool",
    enable_extraction: bool = True,
) -> JsonObject:
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


def _build_site_first_targets(urls: List[str]) -> list[JsonObject]:
    seeds: list[JsonObject] = []
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

    targets: list[JsonObject] = []
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


def _build_detail_only_targets(urls: List[str]) -> list[JsonObject]:
    targets: list[JsonObject] = []
    seen: set[str] = set()
    for raw in urls:
        u = _normalize_url_no_fragment(raw)
        if not u or u in seen:
            continue
        seen.add(u)
        targets.append({"url": u, "entry_type": "detail", "domain": _domain_key(u), "from_url": u, "is_site_seed": False})
    return targets


def _build_site_only_targets(urls: List[str]) -> list[JsonObject]:
    return [x for x in _build_site_first_targets(urls) if bool(x.get("is_site_seed"))]


def _build_site_then_detail_targets(
    urls: List[str],
    *,
    per_domain_limit: int,
) -> list[JsonObject]:
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
        used = _as_int(domain_counts.get(domain))
        if used >= per_domain_limit:
            continue
        domain_counts[domain] = used + 1
        out.append(detail)
    return out


def _resolve_target_mode(extra_params: Optional[JsonObject]) -> str:
    default_mode = str(os.getenv("URL_POOL_DEFAULT_TARGET_MODE", "site_then_detail") or "site_then_detail").strip().lower()
    if default_mode not in {"site_only", "detail_only", "site_first", "site_then_detail"}:
        default_mode = "site_then_detail"
    if not _is_object_dict(extra_params):
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


def _resolve_disable_site_seed_expansion(extra_params: Optional[JsonObject]) -> bool:
    if not _is_object_dict(extra_params):
        return False
    return _as_bool(
        extra_params.get(
            "disable_site_seed_expansion",
            extra_params.get("cluster_layer_separated", False),
        ),
        False,
    )


def _resolve_runtime_targets(urls: List[str], *, extra_params: Optional[JsonObject]) -> Tuple[list[JsonObject], str]:
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
    target: JsonObject,
    query_terms: List[str],
    *,
    extra_params: JsonObject | None = None,
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


def prepare_url_list_targets(
    *,
    urls: List[str],
    query_terms: Optional[List[str]] = None,
    extra_params: Optional[JsonObject] = None,
) -> tuple[list[tuple[str, JsonObject]], JsonObject]:
    normalized_urls = _normalize_url_list(urls)
    normalized_terms = _normalize_terms(query_terms)
    targets, target_mode = _resolve_runtime_targets(normalized_urls, extra_params=extra_params)
    runtime_targets: list[tuple[str, JsonObject]] = []
    seen_runtime_urls: set[str] = set()
    for target in targets:
        target_url = _resolve_target_url(target, normalized_terms, extra_params=extra_params)
        if target_url in seen_runtime_urls:
            continue
        seen_runtime_urls.add(target_url)
        runtime_targets.append((target_url, target))
    diagnostics: JsonObject = {
        "raw_url_count": len(urls),
        "normalized_url_count": len(normalized_urls),
        "filtered_out": max(0, len(urls) - len(normalized_urls)),
        "target_mode": target_mode,
        "target_count": len(targets),
        "target_deduped_count": len(runtime_targets),
    }
    return runtime_targets, diagnostics


def prepare_url_pool_targets(
    *,
    scope: str = "effective",
    project_key: Optional[str] = None,
    domain: Optional[str] = None,
    source_filter: Optional[str] = None,
    limit: int = _DEFAULT_LIMIT,
    query_terms: Optional[List[str]] = None,
    extra_params: Optional[JsonObject] = None,
) -> tuple[list[tuple[str, JsonObject, JsonObject]], JsonObject]:
    normalized_terms = _normalize_terms(query_terms)
    items, total = list_urls(
        scope=scope,
        project_key=project_key,
        source=source_filter,
        domain=domain,
        page=1,
        page_size=min(limit, 100),
    )
    item_by_url = {_as_text(x.get("url")): _as_object_dict(x) for x in items if x.get("url")}
    urls = [_as_text(x.get("url")) for x in items if x.get("url")]
    normalized_urls: List[str] = []
    pool_item_by_target: Dict[str, JsonObject] = {}
    for url in urls:
        normalized = _normalize_url_no_fragment(str(url or ""))
        if not normalized:
            continue
        normalized_urls.append(normalized)
        if normalized not in pool_item_by_target:
            pool_item_by_target[normalized] = item_by_url.get(url) or {}
    targets, target_mode = _resolve_runtime_targets(normalized_urls, extra_params=extra_params)
    for target in targets:
        if bool(target.get("is_site_seed")) and target_mode != "site_only":
            continue
        target_url = str(target.get("url") or "")
        if target_url and target_url not in pool_item_by_target:
            pool_item_by_target[target_url] = item_by_url.get(target_url) or {}
    runtime_targets: list[tuple[str, JsonObject, JsonObject]] = []
    seen_runtime_urls: set[str] = set()
    invalid_target_count = 0
    for target in targets:
        target_url = _resolve_target_url(target, normalized_terms, extra_params=extra_params)
        if target_url in seen_runtime_urls:
            continue
        seen_runtime_urls.add(target_url)
        if not target_url or not str(target_url).strip().startswith(("http://", "https://")):
            invalid_target_count += 1
            continue
        pool_item = pool_item_by_target.get(str(target.get("url") or "")) or {}
        runtime_targets.append((target_url, target, pool_item))
    diagnostics: JsonObject = {
        "pool_total": int(total or 0),
        "pool_returned": len(items),
        "target_mode": target_mode,
        "site_seed_count": len([x for x in targets if bool(x.get("is_site_seed"))]),
        "target_count": len(targets),
        "target_deduped_count": len(runtime_targets) + invalid_target_count,
        "invalid_target_count": invalid_target_count,
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
    }
    return runtime_targets, diagnostics


def _extract_material_ids_from_ingest_result(result: JsonObject) -> List[int]:
    material_ids: List[int] = []
    try:
        direct_id = _as_int(result.get("material_id"))
        if direct_id > 0:
            material_ids.append(direct_id)
    except Exception:
        pass
    crawler_dispatch = result.get("crawler_dispatch")
    if _is_object_dict(crawler_dispatch):
        for raw in _as_object_list(crawler_dispatch.get("valid_output_material_ids")):
            try:
                material_id = _as_int(raw)
            except Exception:
                continue
            if material_id > 0 and material_id not in material_ids:
                material_ids.append(material_id)
    return material_ids


def _frontdoor_route_summary_from_params(params: JsonObject) -> JsonObject:
    profile = _as_object_dict(params.get("frontdoor_route_profile"))
    direct_router_contract = _as_object_dict(params.get("frontdoor_router_contract"))
    router_contract = direct_router_contract or router_contract_from_profile(profile)
    return {
        "contract_version": _FRONTDOOR_ROUTE_PROFILE_CONTRACT_VERSION,
        "route_hint": str(profile.get("route_hint") or params.get("frontdoor_route_hint") or "").strip()
        or None,
        "fetch_strategy": str(profile.get("fetch_strategy") or params.get("frontdoor_fetch_strategy") or "").strip()
        or None,
        "render_required": bool(profile.get("render_required") or params.get("frontdoor_render_required")),
        "prefer_crawler_first": bool(params.get("prefer_crawler_first")),
        "force_url_routing_flow": bool(params.get("force_url_routing_flow", False)),
        "router_contract": router_contract,
    }


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return int(default)
    return int(default)


def _as_bool(value: object, default: bool = False) -> bool:
    return _as_bool_value(value, default)


def _resolve_url_strict_mode(extra_params: Optional[JsonObject]) -> bool:
    if not _is_object_dict(extra_params):
        return False
    if "url_strict_mode" in extra_params:
        return _as_bool(extra_params.get("url_strict_mode"), False)
    if "strict_mode" in extra_params:
        return _as_bool(extra_params.get("strict_mode"), False)
    return False


def _resolve_frontdoor_options(
    extra_params: Optional[JsonObject],
) -> JsonObject:
    params = extra_params if isinstance(extra_params, dict) else {}
    return {
        "enabled": True,
        "front_door_owner": str(params.get("front_door_owner") or "url_pool").strip() or "url_pool",
        "route_decision": str(params.get("frontdoor_route_decision") or "front_door_url_routing").strip()
        or "front_door_url_routing",
        "write_mode": str(params.get("frontdoor_write_mode") or "front_door_url_routing").strip()
        or "front_door_url_routing",
        "execution_mode": str(params.get("frontdoor_execution_mode") or "url_routing").strip() or "url_routing",
    }


def _apply_frontdoor_to_search_options(
    search_options: JsonObject | None,
    frontdoor_options: JsonObject,
) -> JsonObject | None:
    if not bool((frontdoor_options or {}).get("enabled")):
        return search_options
    out: JsonObject = dict(search_options or {})
    out["frontdoor_enabled"] = True
    out["front_door_owner"] = frontdoor_options.get("front_door_owner")
    out["frontdoor_route_decision"] = frontdoor_options.get("route_decision")
    out["frontdoor_write_mode"] = frontdoor_options.get("write_mode")
    out["frontdoor_execution_mode"] = frontdoor_options.get("execution_mode")
    return out


def _annotate_url_pool_context(
    *,
    material_ids: List[int],
    context: JsonObject,
) -> None:
    if not material_ids:
        return
    valid_context = {k: v for k, v in context.items() if v is not None}
    if not valid_context:
        return
    with _open_session() as session:
        id_column = getattr(Material, "id")
        in_operator = getattr(id_column, "in_")
        rows = session.query(Material).filter(in_operator(material_ids)).all()
        for row in rows:
            extracted_data = _as_object_dict(row.extracted_data)
            pool_ctx = _as_object_dict(extracted_data.get("url_pool_context"))
            pool_ctx.update(valid_context)
            extracted_data["url_pool_context"] = pool_ctx
            row.extracted_data = extracted_data
        session.commit()
