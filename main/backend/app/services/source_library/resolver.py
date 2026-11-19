from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field
import logging
from functools import partial
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, NoReturn, TypeGuard, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import (
    source_library_contract_failures,
)

from ...models.base import SessionLocal
from ...models.entities import (
    IngestChannel,
    SharedIngestChannel,
    SharedSourceLibraryItem,
    SourceLibraryItem,
)
from ..ingest_config.service import get_config as get_ingest_config
from ..projects import bind_project, bind_schema
from .external_project import EXTERNAL_PROJECT_CHANNEL_KEY, normalize_bounded_int
from .candidate_aggregation import (
    HandlerCandidateLimits,
    batch_max_candidates,
    candidate_record_stats,
    normalize_handler_candidate_limits,
)
from .item_resolver import (
    ExecutionPayload,
    ItemResolver,
    normalize_item_taxonomy as _normalize_item_taxonomy,
    channel_default_params,
    item_mapping_fields,
    terminal_output_params,
)
from .item_plan import build_item_definition_view, build_item_execution_plan
from .orchestrators import (
    run_protocol_search_orchestrator,
    run_provider_harvest_orchestrator,
    run_single_channel_orchestrator,
    run_site_search_orchestrator,
    run_url_execution_orchestrator,
)
from .orchestrators.site_search import fold_search_observations
from .relevance_review import annotate_records_with_relevance_review_queue
from .relevance_review import merge_relevance_review_queues
from .loader import load_project_library_files
from .runner import RunnerObject, is_runner_mapping, run_channel
from .single_source_guard import build_single_source_execution_fact, validate_single_source_guard
from .types import (
    ExecutionLayer,
    FrontDoorExecutionProtocol,
    RoutingObservation,
    RoutingSummary,
    build_source_concurrency_plan,
    derive_source_tiering,
    source_concurrency_plan_to_dict,
)
from .url_router import resolve_channel_for_url

if TYPE_CHECKING:
    from ..resource_pool.search_contract_discovery import QueryDiscoveryBudget
    from ..resource_pool.unified_search import UnifiedSearchResult

logger = logging.getLogger(__name__)

PROVIDER_HANDOFF_CONTRACT_VERSION = "source_library.provider_handoff.v1"
SMOKE_ONLY_CONTRACT_VERSION = "source_library.smoke_only.v1"
_FAILURE_WITNESS = "test:test_source_configuration_and_report_export_failures"
_Key = TypeVar("_Key")


def _is_object(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object(value: object) -> dict[object, object]:
    return dict(value) if _is_object(value) else {}


def object_list(value: object) -> list[object]:
    return list(value) if _is_object_list(value) else []


def as_runner_object(value: object) -> RunnerObject:
    if not is_runner_mapping(value):
        raise_resolver_failure(
            resolver_failure(
                "routing_value_invalid",
                "source-library routing value is not a runner object",
                site="_as_runner_object.value",
                actual_type=type(value).__name__,
            )
        )
    return dict(value)


def optional_runner_object(value: object) -> RunnerObject | None:
    return dict(value) if is_runner_mapping(value) else None


def resolver_failure(code: str, message: str, *, site: str, **details: object) -> Failure:
    public_exception = "TypeError" if code == "routing_value_invalid" else "ValueError"
    context: dict[str, object] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": source_library_contract_failures.name,
        "operation": "source_library.resolver",
        "owner": "source_library.resolver",
        "public_exception": public_exception,
        "public_message": message,
        "site": site,
        "witness": _FAILURE_WITNESS,
    }
    context.update(details)
    return source_library_contract_failures.fail(code, message, context)


def raise_resolver_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    expected_public_exception = "TypeError" if failure.code == "routing_value_invalid" else "ValueError"
    required = {"boundary_class", "failure_family", "operation", "owner", "public_exception", "public_message", "site", "witness"}
    if (
        not source_library_contract_failures.matches(failure)
        or required - set(context)
        or context.get("failure_family") != source_library_contract_failures.name
        or context.get("boundary_class") != "PURE_CONTRACT_FAILURE"
        or context.get("public_exception") != expected_public_exception
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=source_library.resolver.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_source_configuration_and_report_export_failures
        raise TypeError("source-library resolver failure lift context is incomplete or inconsistent")
    message = str(context["public_message"])
    if expected_public_exception == "TypeError":
        # kit:boundary owner=source_library.resolver.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.contract_failure witness=test:test_source_configuration_and_report_export_failures
        raise TypeError(message)
    # kit:boundary owner=source_library.resolver.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.contract_failure witness=test:test_source_configuration_and_report_export_failures
    raise ValueError(message)


def _as_list(value: object) -> list[object]:
    if _is_object_list(value):
        return list(value)
    if value is None:
        return []
    return [value]


def _as_dict(value: object) -> dict[object, object]:
    return _object(value)


def as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value or "").strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_terms(value: object) -> list[str]:
    if _is_object_list(value):
        out: list[str] = []
        for item in value:
            s = str(item or "").strip()
            if s and s not in out:
                out.append(s)
        return out
    s = str(value or "").strip()
    return [s] if s else []


def as_optional_int(value: object, *, min_value: int | None = None, max_value: int | None = None) -> int | None:
    try:
        if not isinstance(value, int | float | str):
            return None
        parsed = int(value)
    except Exception:
        return None
    if min_value is not None and parsed < min_value:
        return None
    if max_value is not None and parsed > max_value:
        return None
    return parsed


def _as_optional_float(value: object) -> float | None:
    if not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _as_optional_ymd(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = raw.split("-")
    if len(parts) != 3:
        return None
    if not (parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit()):
        return None
    if len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
        return None
    return raw


def _normalize_search_params(params: Mapping[object, object]) -> dict[object, object]:
    normalized = dict(params or {})

    query_terms = _normalize_terms(
        normalized.get("query_terms")
        or normalized.get("keywords")
        or normalized.get("search_keywords")
        or normalized.get("base_keywords")
        or normalized.get("topic_keywords")
        or []
    )
    if query_terms:
        normalized["query_terms"] = query_terms

    max_items = as_optional_int(
        normalized.get("max_items") if normalized.get("max_items") is not None else normalized.get("limit"),
        min_value=1,
        max_value=5000,
    )
    if max_items is not None:
        normalized["max_items"] = max_items
        normalized.setdefault("limit", max_items)

    per_keyword_limit = as_optional_int(
        normalized.get("per_keyword_limit") if normalized.get("per_keyword_limit") is not None else normalized.get("limit"),
        min_value=1,
        max_value=5000,
    )
    if per_keyword_limit is not None:
        normalized["per_keyword_limit"] = per_keyword_limit

    max_candidates = as_optional_int(normalized.get("max_candidates"), min_value=1, max_value=20000)
    if max_candidates is None and max_items is not None:
        max_candidates = max_items
    if max_candidates is not None:
        normalized["max_candidates"] = max_candidates

    ingest_limit = as_optional_int(
        normalized.get("ingest_limit") if normalized.get("ingest_limit") is not None else normalized.get("max_items"),
        min_value=1,
        max_value=5000,
    )
    if ingest_limit is not None:
        normalized["ingest_limit"] = ingest_limit

    page = as_optional_int(
        normalized.get("page") if normalized.get("page") is not None else normalized.get("paged"),
        min_value=1,
        max_value=10000,
    )
    if page is not None:
        normalized["page"] = page

    page_size = as_optional_int(
        normalized.get("page_size") if normalized.get("page_size") is not None else normalized.get("per_page"),
        min_value=1,
        max_value=1000,
    )
    if page_size is not None:
        normalized["page_size"] = page_size

    max_pages = as_optional_int(
        normalized.get("max_pages") if normalized.get("max_pages") is not None else normalized.get("pages"),
        min_value=1,
        max_value=100,
    )
    if max_pages is not None:
        normalized["max_pages"] = max_pages

    days_back = as_optional_int(normalized.get("days_back"), min_value=1, max_value=3650)
    if days_back is not None:
        normalized["days_back"] = days_back

    start_offset = as_optional_int(normalized.get("start_offset"), min_value=1, max_value=10000)
    if start_offset is not None:
        normalized["start_offset"] = start_offset

    start_time = _as_optional_ymd(
        normalized.get("start_time") if normalized.get("start_time") is not None else normalized.get("date_from")
    )
    end_time = _as_optional_ymd(
        normalized.get("end_time") if normalized.get("end_time") is not None else normalized.get("date_to")
    )
    if start_time:
        normalized["start_time"] = start_time
        normalized["date_from"] = start_time
    if end_time:
        normalized["end_time"] = end_time
        normalized["date_to"] = end_time

    return normalized


def _split_batches(terms: list[str], chunk_size: int) -> list[list[str]]:
    clean = _normalize_terms(terms)
    if not clean:
        return [[]]
    size = max(1, int(chunk_size))
    return [clean[i : i + size] for i in range(0, len(clean), size)]


def _deep_merge(
    base: Mapping[_Key, object], override: Mapping[_Key, object],
) -> dict[_Key, object]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if _is_object(value) and _is_object(current):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _inject_url_params_for_channel(
    *,
    channel: dict[str, object],
    per_url_params: dict[object, object],
    url_str: str,
) -> dict[object, object]:
    """Map a routed URL into channel-specific params for tool channels."""
    provider = str(channel.get("provider") or "").strip().lower()
    kind = str(channel.get("kind") or "").strip().lower()

    # Preserve raw URL for adapters that directly consume url/urls.
    per_url_params.setdefault("url", url_str)
    per_url_params["urls"] = [url_str]

    # Crawler providers consume runtime payload from params.arguments.
    provider_type = str(channel.get("provider_type") or "").strip().lower()
    if provider_type in {"scrapy", "crawlee", "meltano"}:
        arguments = _as_dict(per_url_params.get("arguments"))
        arguments.setdefault("url", url_str)
        arguments.setdefault("urls", [url_str])
        route_profile = _as_dict(per_url_params.get("frontdoor_route_profile"))
        router_contract = _as_dict(per_url_params.get("frontdoor_router_contract"))
        if not router_contract and _is_object(route_profile.get("router_contract")):
            router_contract = _as_dict(route_profile.get("router_contract"))
        if route_profile:
            arguments.setdefault("frontdoor_route_profile", route_profile)
        if router_contract:
            arguments.setdefault("frontdoor_router_contract", router_contract)
        if per_url_params.get("frontdoor_route_hint") is not None:
            arguments.setdefault("frontdoor_route_hint", per_url_params.get("frontdoor_route_hint"))
        if per_url_params.get("frontdoor_fetch_strategy") is not None:
            arguments.setdefault("frontdoor_fetch_strategy", per_url_params.get("frontdoor_fetch_strategy"))
        if per_url_params.get("frontdoor_render_required") is not None:
            arguments.setdefault("frontdoor_render_required", bool(per_url_params.get("frontdoor_render_required")))
        per_url_params["arguments"] = arguments

    if provider == "generic_web":
        per_url_params.setdefault("site_url", url_str)
        if kind == "rss":
            per_url_params.setdefault("feed_url", url_str)
        elif kind == "sitemap":
            per_url_params.setdefault("sitemap_url", url_str)
        elif kind == "search_template":
            # Search template usually needs a {{q}} template string; only infer when obvious.
            if "{{q}}" in url_str and "template" not in per_url_params:
                per_url_params["template"] = url_str
    return per_url_params


def _extract_source_tiering_from_extra(extra: Mapping[object, object]) -> tuple[object, object]:
    tier = extra.get("source_tier")
    priority = extra.get("onboarding_priority")
    source_tiering = extra.get("source_tiering")
    source_tiering_payload = _object(source_tiering)
    if source_tiering_payload:
        if source_tiering_payload.get("tier") is not None:
            tier = source_tiering_payload.get("tier")
        if source_tiering_payload.get("onboarding_priority") is not None:
            priority = source_tiering_payload.get("onboarding_priority")
    return tier, priority


def _attach_source_tiering(channel: dict[str, object]) -> dict[str, object]:
    normalized = dict(channel)
    extra = _as_dict(normalized.get("extra"))
    explicit_tier, explicit_priority = _extract_source_tiering_from_extra(extra)
    tiering = derive_source_tiering(
        provider=normalized.get("provider"),
        provider_type=normalized.get("provider_type"),
        explicit_tier=explicit_tier,
        explicit_priority=explicit_priority,
    )
    tiering_payload = {
        "tier": tiering.tier.value,
        "onboarding_priority": tiering.onboarding_priority.value,
        "reason": tiering.reason,
    }
    extra["source_tiering"] = tiering_payload
    extra.setdefault("source_tier", tiering.tier.value)
    extra.setdefault("onboarding_priority", tiering.onboarding_priority.value)
    normalized["extra"] = extra
    normalized["source_tier"] = tiering.tier.value
    normalized["onboarding_priority"] = tiering.onboarding_priority.value
    return normalized


def is_crawler_channel(channel: dict[str, object] | None) -> bool:
    if not isinstance(channel, dict):
        return False
    provider_type = str(channel.get("provider_type") or "").strip().lower()
    return provider_type in {"scrapy", "crawlee", "meltano"}


def prefer_crawler_channel_key(
    *,
    channel_map: dict[str, dict[str, object]],
    project_key: str | None,
) -> str | None:
    candidates: list[str] = []
    for channel_key, channel in channel_map.items():
        if not channel.get("enabled", True):
            continue
        if is_crawler_channel(channel):
            candidates.append(str(channel_key))
    if not candidates:
        return None

    pk = str(project_key or "").strip().lower()

    def _score(key: str) -> tuple[int, str]:
        lowered = key.lower()
        if pk and lowered == f"crawler.{pk}":
            return (0, lowered)
        if pk and lowered.startswith(f"crawler.{pk}."):
            return (1, lowered)
        if lowered.startswith("crawler."):
            return (2, lowered)
        return (3, lowered)

    return sorted(candidates, key=_score)[0]


def _is_retryable_crawler_runtime_error(exc: Exception) -> bool:
    message = str(exc or "").strip().lower()
    if not message:
        return False
    return (
        "crawler provider '" in message and " is unavailable" in message
    ) or ("unsupported crawler provider_type" in message)


def _build_provider_handoff(
    *,
    channel: dict[str, object],
    channel_key: str,
    params: Mapping[object, object],
    result: Mapping[str, object] | None,
    execution_layer: ExecutionLayer,
    force_url_routing_flow: bool,
    fallback_from_channel_key: str | None = None,
    fallback_reason: str | None = None,
) -> RunnerObject:
    provider_type = str(channel.get("provider_type") or "").strip().lower() or None
    provider = str(channel.get("provider") or "").strip().lower() or None
    route_profile = _as_dict(params.get("frontdoor_route_profile"))
    router_contract = _as_dict(params.get("frontdoor_router_contract"))
    if not router_contract and isinstance(route_profile.get("router_contract"), dict):
        router_contract = _as_dict(route_profile.get("router_contract"))
    result_payload = dict(result) if result is not None else {}
    route_hint = (
        str(route_profile.get("route_hint") or params.get("frontdoor_route_hint") or "").strip()
        or None
    )
    fetch_strategy = (
        str(route_profile.get("fetch_strategy") or params.get("frontdoor_fetch_strategy") or "").strip()
        or None
    )
    render_required = bool(route_profile.get("render_required") or params.get("frontdoor_render_required"))
    is_crawler = is_crawler_channel(channel)
    out: dict[str, object] = {
        "contract_version": PROVIDER_HANDOFF_CONTRACT_VERSION,
        "handoff_kind": "crawler_provider" if is_crawler else "mechanical_fetch",
        "channel_key": channel_key or None,
        "provider": provider,
        "provider_type": provider_type,
        "provider_dispatch": "crawlers/providers" if is_crawler else None,
        "downstream_handoff": "ingest",
        "execution_layer": execution_layer,
        "route_hint": route_hint,
        "fetch_strategy": fetch_strategy,
        "render_required": render_required,
        "prefer_crawler_first": bool(params.get("prefer_crawler_first")),
        "force_url_routing_flow": bool(force_url_routing_flow),
        "provider_job_id": result_payload.get("provider_job_id"),
        "provider_status": result_payload.get("provider_status"),
        "attempt_count": result_payload.get("attempt_count"),
        "fallback_from_channel_key": fallback_from_channel_key,
        "fallback_reason": fallback_reason,
    }
    if route_profile:
        out["frontdoor_route_profile"] = route_profile
    if router_contract:
        out["router_contract"] = router_contract
        out["router_state"] = router_contract.get("router_state")
        out["router_reason_code"] = router_contract.get("reason_code")
        fallback_boundary = _object(router_contract.get("fallback_boundary"))
        if fallback_boundary:
            out["fallback_boundary"] = fallback_boundary
    return as_runner_object({key: value for key, value in out.items() if value is not None})


def _is_handler_cluster_item(item: dict[str, object] | None) -> bool:
    extra = _object((item or {}).get("extra"))
    if not extra:
        return False
    return bool(
        extra.get("stable_handler_cluster")
        or str(extra.get("creation_handler") or "").startswith("handler.entry_type")
    )


def _has_site_entries(params: Mapping[object, object] | None) -> bool:
    if params is None:
        return False
    for key in ("site_entries", "site_entry_urls", "official_access_site_entries"):
        raw = params.get(key)
        if _is_object_list(raw) and any(str(x or "").strip() for x in raw):
            return True
    return False


def _is_source_library_smoke_only(params: Mapping[object, object] | None) -> bool:
    if params is None:
        return False
    return as_bool(params.get("_source_library_smoke_only"), False)


def _build_source_library_smoke_payload(
    *,
    item: dict[str, object],
    params: Mapping[object, object],
    project_key: str | None,
) -> dict[str, object]:
    item_key = str(item.get("item_key") or "").strip()
    channel_key = str(item.get("channel_key") or "").strip()
    runtime_readback = _object(params.get("runtime_readback"))
    result: dict[str, object] = {
        "status": "ok",
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "records": [],
        "execution_request": {
            "item_key": item_key,
            "project_key": project_key,
            "source_mode": "smoke_only",
            "params": dict(params),
            "warnings": [],
        },
        "smoke_only": {
            "contract_version": SMOKE_ONLY_CONTRACT_VERSION,
            "reason": "worker_readback_smoke",
            "resolver_short_circuit": True,
            "handler_dispatched": False,
        },
    }
    if runtime_readback:
        result["runtime_readback"] = dict(runtime_readback)
    payload: dict[str, object] = {
        "contract_version": SMOKE_ONLY_CONTRACT_VERSION,
        "status": "ok",
        "source_mode": "smoke_only",
        "smoke_only": True,
        "item_key": item_key,
        "channel_key": channel_key,
        "project_key": project_key,
        "params": dict(params),
        "result": result,
        "item_type": item.get("item_type"),
        "managed_by": item.get("managed_by"),
        "name": item.get("name"),
        "extra": _as_dict(item.get("extra")),
    }
    if runtime_readback:
        payload["runtime_readback"] = dict(runtime_readback)
    return payload


def _normalize_site_entries(value: object) -> list[str]:
    if isinstance(value, str):
        raw_entries: list[object] = [value]
    elif _is_object_list(value):
        raw_entries = list(value)
    else:
        return []
    out: list[str] = []
    for entry in raw_entries:
        site_url = str(entry or "").strip()
        if site_url and site_url not in out:
            out.append(site_url)
    return out


def _build_frontdoor_protocol(
    *,
    item: dict[str, object],
    params: Mapping[object, object],
    project_key: str | None,
    candidate_urls: list[str] | None = None,
) -> FrontDoorExecutionProtocol:
    item_key = str(item.get("item_key") or "").strip() or "_anonymous"
    item_channel_key = str(item.get("channel_key") or "").strip()
    item_params = _as_dict(item.get("params"))
    item_extra = _as_dict(item.get("extra"))
    source_tier = str(item_extra.get("source_tier") or "").strip()
    onboarding_priority = str(item_extra.get("onboarding_priority") or "").strip()
    source_tiering = item_extra.get("source_tiering")
    source_tiering_payload = _object(source_tiering)
    if source_tiering_payload:
        source_tier = str(source_tiering_payload.get("tier") or source_tier).strip()
        onboarding_priority = str(source_tiering_payload.get("onboarding_priority") or onboarding_priority).strip()
    query_terms = _normalize_terms(
        params.get("query_terms")
        or params.get("keywords")
        or params.get("search_keywords")
        or params.get("base_keywords")
        or params.get("topic_keywords")
        or []
    )
    site_entries = _normalize_site_entries(
        params.get("site_entries")
        or params.get("site_entry_urls")
        or params.get("official_access_site_entries")
        or item_params.get("site_entries")
        or item_params.get("site_entry_urls")
        or item_params.get("official_access_site_entries")
    )
    routed_urls = _normalize_site_entries(candidate_urls if candidate_urls is not None else params.get("urls"))
    query_batch_size = normalize_bounded_int(
        params.get("keyword_batch_size") or params.get("batch_size") or params.get("batch"),
        default=4,
        min_value=1,
        max_value=100,
    )
    total_search_tasks = len(_split_batches(query_terms, query_batch_size))
    total_url_tasks = len(routed_urls) if routed_urls else len(site_entries)
    concurrency_plan = build_source_concurrency_plan(
        params=params,
        total_search_tasks=total_search_tasks,
        total_url_tasks=total_url_tasks,
    )
    write_to_pool = as_bool(params.get("write_to_pool"), True)
    auto_ingest = as_bool(params.get("auto_ingest"), True)
    default_force_url_routing_flow = item_channel_key.lower() == "url_pool" or item_key.lower().startswith("url_pool.")
    force_url_routing_flow = as_bool(params.get("force_url_routing_flow"), default_force_url_routing_flow)
    prefer_crawler_first = as_bool(params.get("prefer_crawler_first"), False) and not force_url_routing_flow
    search_parallelism = concurrency_plan.search.parallelism
    routing_parallelism = concurrency_plan.url.parallelism
    execution_mode = "single_channel"
    route_decision = "channel_direct"
    write_mode = "channel_direct"
    if routed_urls:
        execution_mode = "url_routing"
        route_decision = "front_door_url_routing"
        write_mode = "front_door_url_routing"
    elif _is_handler_cluster_item(item) or site_entries:
        execution_mode = "search_then_route"
        route_decision = "handler_cluster_search"
        write_mode = "front_door_url_routing"

    return FrontDoorExecutionProtocol(
        item_key=item_key,
        item_channel_key=item_channel_key,
        project_key=str(project_key or "").strip() or None,
        front_door_owner="run_item_payload",
        execution_mode=execution_mode,
        write_mode=write_mode,
        route_decision=route_decision,
        query_terms=query_terms,
        site_entries=site_entries,
        candidate_urls=routed_urls,
        expected_entry_type=str(item_extra.get("expected_entry_type") or item_params.get("expected_entry_type") or "").strip() or None,
        write_to_pool=write_to_pool,
        auto_ingest=auto_ingest,
        ingest_limit=max(1, as_optional_int(params.get("ingest_limit") or params.get("limit")) or 20),
        force_url_routing_flow=force_url_routing_flow,
        prefer_crawler_first=prefer_crawler_first,
        search_parallelism=search_parallelism,
        routing_parallelism=routing_parallelism,
        concurrency_plan=source_concurrency_plan_to_dict(concurrency_plan),
        source_tier=source_tier,
        onboarding_priority=onboarding_priority,
    )


def _select_routed_channel(
    *, url: str, project_key: str | None, channel_map: dict[str, dict[str, object]],
    has_query_terms: bool, force_url_routing_flow: bool,
    preferred_crawler_channel_key: str | None,
) -> tuple[str, str, dict[str, object] | None]:
    default_key = "url_pool" if force_url_routing_flow else resolve_channel_for_url(
        url, project_key, has_query_terms=has_query_terms,
    )
    channel_key = "url_pool" if force_url_routing_flow else (
        preferred_crawler_channel_key or default_key
    )
    channel = channel_map.get(channel_key)
    if channel is None and channel_map.get("url_pool") is not None:
        channel_key, channel = "url_pool", channel_map["url_pool"]
    return default_key, channel_key, channel


def _routed_channel_params(
    channel: dict[str, object], params: Mapping[object, object], url: str, execution_layer: ExecutionLayer,
) -> dict[object, object]:
    per_url = _deep_merge(channel_default_params(channel.get("default_params") or {}), params)
    per_url.pop("urls", None)
    per_url = _inject_url_params_for_channel(
        channel=channel, per_url_params=per_url, url_str=url,
    )
    return terminal_output_params(per_url) if execution_layer == "terminal_output_only" else per_url


def _execute_routed_channel(
    channel: dict[str, object], params: Mapping[object, object], project_key: str | None, item_key: str | None,
) -> RunnerObject:
    with (bind_project(project_key) if project_key else nullcontext()):
        return run_channel(
            channel=channel, params=params, project_key=project_key, item_key=item_key,
        )


def _routed_channel_observation(
    *, url: str, channel_key: str, channel: dict[str, object], params: Mapping[object, object],
    result: RunnerObject | None, execution_layer: ExecutionLayer, force_url_routing_flow: bool,
    fallback_from_channel_key: str | None = None, fallback_reason: str | None = None,
    error: str | None = None,
) -> RunnerObject:
    handoff = _build_provider_handoff(
        channel=channel, channel_key=channel_key, params=params,
        result=result,
        execution_layer=execution_layer, force_url_routing_flow=force_url_routing_flow,
        fallback_from_channel_key=fallback_from_channel_key, fallback_reason=fallback_reason,
    )
    row: RunnerObject = {
        "url": url, "channel_key": channel_key, "error": error, "result": result,
        "provider_handoff": handoff, "frontdoor_route_profile": handoff.get("frontdoor_route_profile"),
    }
    if fallback_from_channel_key is not None:
        row["fallback_from_channel_key"] = fallback_from_channel_key
        row["fallback_reason"] = fallback_reason
    return row


def run_routed_target(
    *, url: object, item_key: str | None, params: Mapping[object, object], project_key: str | None,
    channel_map: dict[str, dict[str, object]], has_query_terms: bool, force_url_routing_flow: bool,
    preferred_crawler_channel_key: str | None, fallback_crawler_channel_key: str | None,
    force_crawler_fallback_on_empty: bool, execution_layer: ExecutionLayer = "execute",
) -> RunnerObject:
    url_str = str(url).strip() if url else ""
    if not url_str or not url_str.startswith(("http://", "https://")):
        return {"url": url_str or str(url), "channel_key": None, "error": "invalid url", "result": None}
    default_key, channel_key, channel = _select_routed_channel(
        url=url_str, project_key=project_key, channel_map=channel_map,
        has_query_terms=has_query_terms, force_url_routing_flow=force_url_routing_flow,
        preferred_crawler_channel_key=preferred_crawler_channel_key,
    )
    if channel is None:
        return {"url": url_str, "channel_key": channel_key, "error": "channel not found", "result": None}
    if not channel.get("enabled", True):
        return {"url": url_str, "channel_key": channel_key, "error": "channel disabled", "result": None}
    per_url = _routed_channel_params(channel, params, url_str, execution_layer)
    observe = partial(
        _routed_channel_observation, url=url_str, execution_layer=execution_layer,
        force_url_routing_flow=force_url_routing_flow,
    )
    try:
        result = _execute_routed_channel(channel, per_url, project_key, item_key)
        if (
            force_crawler_fallback_on_empty
            and not is_crawler_channel(channel) and not _result_has_material_output(result)
            and fallback_crawler_channel_key and fallback_crawler_channel_key != channel_key
        ):
            fallback_channel = channel_map.get(fallback_crawler_channel_key)
            if fallback_channel is not None and fallback_channel.get("enabled", True):
                fallback_params = _routed_channel_params(fallback_channel, params, url_str, execution_layer)
                try:
                    fallback_result = _execute_routed_channel(fallback_channel, fallback_params, project_key, item_key)
                    return observe(
                        channel_key=fallback_crawler_channel_key, channel=fallback_channel,
                        params=fallback_params, result=fallback_result,
                        fallback_from_channel_key=channel_key, fallback_reason="mechanical_no_results",
                    )
                except Exception:
                    pass
        return observe(channel_key=channel_key, channel=channel, params=per_url, result=result)
    except Exception as exc:
        if (
            preferred_crawler_channel_key and channel_key == preferred_crawler_channel_key
            and default_key and default_key != channel_key and _is_retryable_crawler_runtime_error(exc)
        ):
            fallback_channel = channel_map.get(default_key)
            if fallback_channel is not None and fallback_channel.get("enabled", True):
                fallback_params = _routed_channel_params(fallback_channel, params, url_str, execution_layer)
                try:
                    fallback_result = _execute_routed_channel(fallback_channel, fallback_params, project_key, item_key)
                    return observe(
                        channel_key=default_key, channel=fallback_channel, params=fallback_params,
                        result=fallback_result, fallback_from_channel_key=channel_key, fallback_reason=str(exc),
                    )
                except Exception:
                    pass
        return observe(
            channel_key=channel_key, channel=channel, params=per_url,
            result=None, fallback_reason=str(exc), error=str(exc),
        )


def _result_has_material_output(result: object) -> bool:
    payload = _object(result)
    if not payload:
        return False
    records = object_list(payload.get("records"))
    if records:
        return True
    if (as_optional_int(payload.get("fetched")) or 0) > 0:
        return True
    if (as_optional_int(payload.get("inserted")) or 0) + (as_optional_int(payload.get("updated")) or 0) > 0:
        return True
    by_url = object_list(payload.get("by_url"))
    for row in by_url:
        nested = _object(row).get("result")
        nested_payload = _object(nested)
        if nested_payload and (
            nested_payload.get("title")
            or nested_payload.get("content_text")
            or nested_payload.get("content_preview")
            or nested_payload.get("excerpt")
            or nested_payload.get("status") == "fetched"
        ):
            return True
    return False


def _channel_row_to_dict(
    row: SharedIngestChannel | IngestChannel,
    scope: str,
) -> dict[str, object]:
    return _attach_source_tiering({
        "channel_key": row.channel_key,
        "name": row.name,
        "kind": row.kind,
        "provider": row.provider,
        "provider_type": str(getattr(row, "provider_type", None) or "native"),
        "provider_config": _as_dict(getattr(row, "provider_config", None)),
        "execution_policy": _as_dict(getattr(row, "execution_policy", None)),
        "description": row.description,
        "credential_refs": _as_list(row.credential_refs),
        "default_params": _as_dict(row.default_params),
        "param_schema": _as_dict(row.param_schema),
        "extends_channel_key": row.extends_channel_key,
        "enabled": bool(row.enabled),
        "extra": _as_dict(row.extra),
        "scope": scope,
    })


def _item_row_to_dict(
    row: SharedSourceLibraryItem | SourceLibraryItem,
    scope: str,
) -> dict[str, object]:
    payload = {
        "item_key": row.item_key,
        "name": row.name,
        "channel_key": row.channel_key,
        "description": row.description,
        "params": _as_dict(row.params),
        "tags": _as_list(row.tags),
        "schedule": row.schedule,
        "extends_item_key": row.extends_item_key,
        "item_type": str(getattr(row, "item_type", "") or "").strip() or None,
        "managed_by": str(getattr(row, "managed_by", "") or "").strip() or None,
        "enabled": bool(row.enabled),
        "extra": _as_dict(row.extra),
        "scope": scope,
    }
    return _normalize_item_taxonomy(payload)


def _load_shared_channels() -> list[dict[str, object]]:
    try:
        with bind_schema("public"):
            with SessionLocal() as session:
                rows = session.execute(select(SharedIngestChannel).order_by(SharedIngestChannel.id.asc())).scalars().all()
                return [_channel_row_to_dict(row, "shared") for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("source_library_shared_channels_degraded error=%s", exc.__class__.__name__)
        return []


def _load_project_channels(project_key: str | None) -> list[dict[str, object]]:
    file_rows: list[dict[str, object]] = []
    file_data = load_project_library_files(project_key)
    for payload in file_data.get("channels", []):
        channel_key = str(payload.get("channel_key", "")).strip()
        if not channel_key:
            continue
        file_rows.append(
            _attach_source_tiering(
                {
                    "channel_key": channel_key,
                    "name": str(payload.get("name") or channel_key),
                    "kind": str(payload.get("kind") or "unknown"),
                    "provider": str(payload.get("provider") or "unknown"),
                    "provider_type": str(payload.get("provider_type") or "native"),
                    "provider_config": _as_dict(payload.get("provider_config")),
                    "execution_policy": _as_dict(payload.get("execution_policy")),
                    "description": payload.get("description"),
                    "credential_refs": _as_list(payload.get("credential_refs")),
                    "default_params": _as_dict(payload.get("default_params")),
                    "param_schema": _as_dict(payload.get("param_schema")),
                    "extends_channel_key": payload.get("extends_channel_key"),
                    "enabled": bool(payload.get("enabled", True)),
                    "extra": _as_dict(payload.get("extra")),
                    "scope": "project",
                }
            )
        )
    if not project_key:
        return file_rows
    try:
        with bind_project(project_key):
            with SessionLocal() as session:
                rows = session.execute(select(IngestChannel).order_by(IngestChannel.id.asc())).scalars().all()
                db_rows = [_channel_row_to_dict(row, "project") for row in rows]
                return [*file_rows, *db_rows]
    except SQLAlchemyError as exc:
        logger.warning(
            "source_library_project_channels_degraded project_key=%s error=%s",
            project_key,
            exc.__class__.__name__,
        )
        return file_rows


def _load_shared_items() -> list[dict[str, object]]:
    try:
        with bind_schema("public"):
            with SessionLocal() as session:
                rows = session.execute(
                    select(SharedSourceLibraryItem).order_by(SharedSourceLibraryItem.id.asc())
                ).scalars().all()
                return [_item_row_to_dict(row, "shared") for row in rows]
    except SQLAlchemyError as exc:
        logger.warning("source_library_shared_items_degraded error=%s", exc.__class__.__name__)
        return []


def _load_project_items(project_key: str | None) -> list[dict[str, object]]:
    file_rows: list[dict[str, object]] = []
    file_data = load_project_library_files(project_key)
    for payload in file_data.get("items", []):
        item_key = str(payload.get("item_key", "")).strip()
        channel_key = str(payload.get("channel_key", "")).strip()
        if not item_key or not channel_key:
            continue
        file_rows.append(
            _normalize_item_taxonomy(
                {
                "item_key": item_key,
                "name": str(payload.get("name") or item_key),
                "channel_key": channel_key,
                "description": payload.get("description"),
                "params": _as_dict(payload.get("params")),
                "tags": _as_list(payload.get("tags")),
                "schedule": payload.get("schedule"),
                "extends_item_key": payload.get("extends_item_key"),
                "item_type": payload.get("item_type"),
                "managed_by": payload.get("managed_by"),
                "enabled": bool(payload.get("enabled", True)),
                "extra": _as_dict(payload.get("extra")),
                "scope": "project",
                }
            )
        )
    if not project_key:
        return file_rows
    try:
        with bind_project(project_key):
            with SessionLocal() as session:
                rows = session.execute(select(SourceLibraryItem).order_by(SourceLibraryItem.id.asc())).scalars().all()
                db_rows = [_item_row_to_dict(row, "project") for row in rows]
                return [*file_rows, *db_rows]
    except SQLAlchemyError as exc:
        logger.warning(
            "source_library_project_items_degraded project_key=%s error=%s",
            project_key,
            exc.__class__.__name__,
        )
        return file_rows


def _merge_channels(
    shared_channels: list[dict[str, object]],
    project_channels: list[dict[str, object]],
) -> list[dict[str, object]]:
    shared_map = {x["channel_key"]: x for x in shared_channels}
    effective = dict(shared_map)

    for pch in project_channels:
        base_key = pch.get("extends_channel_key") or pch["channel_key"]
        base = effective.get(base_key, {})
        merged = _deep_merge(base, pch) if base else dict(pch)
        merged["channel_key"] = pch["channel_key"]
        merged["scope"] = "project"
        effective[pch["channel_key"]] = merged

    return list(effective.values())


def _merge_items(
    shared_items: list[dict[str, object]],
    project_items: list[dict[str, object]],
) -> list[dict[str, object]]:
    shared_map = {x["item_key"]: x for x in shared_items}
    effective = dict(shared_map)

    for pit in project_items:
        base_key = pit.get("extends_item_key") or pit["item_key"]
        base = effective.get(base_key, {})
        merged = _deep_merge(base, pit) if base else dict(pit)
        merged["item_key"] = pit["item_key"]
        merged["scope"] = "project"
        effective[pit["item_key"]] = merged

    return list(effective.values())


def _normalize_effective_item(
    item: dict[str, object],
    *,
    include_execution_plan: bool = False,
) -> dict[str, object]:
    return build_item_definition_view(item, include_execution_plan=include_execution_plan)


_URL_POOL_CHANNEL: dict[str, object] = {
    "channel_key": "url_pool",
    "name": "URL 资源池",
    "kind": "urls",
    "provider": "url_pool",
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "从 URL 资源池取 URL 抓取入库，params: scope, domain, source, limit",
    "credential_refs": [],
    "default_params": {"scope": "effective", "limit": 50},
    "param_schema": {},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_GENERIC_WEB_RSS_CHANNEL: dict[str, object] = {
    "channel_key": "generic_web.rss",
    "name": "Generic Web RSS",
    "kind": "rss",
    "provider": "generic_web",
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "Tool channel: fetch RSS/Atom feed and emit candidate URLs.",
    "credential_refs": [],
    "default_params": {"probe_timeout": 10, "write_to_pool": False, "pool_scope": "project"},
    "param_schema": {"required": ["feed_url"]},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_GENERIC_WEB_SITEMAP_CHANNEL: dict[str, object] = {
    "channel_key": "generic_web.sitemap",
    "name": "Generic Web Sitemap",
    "kind": "sitemap",
    "provider": "generic_web",
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "Tool channel: parse sitemap/sitemapindex and emit candidate URLs.",
    "credential_refs": [],
    "default_params": {"probe_timeout": 10, "max_depth": 2, "max_sitemaps": 30, "write_to_pool": False, "pool_scope": "project"},
    "param_schema": {"required": ["sitemap_url"]},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_GENERIC_WEB_SEARCH_TEMPLATE_CHANNEL: dict[str, object] = {
    "channel_key": "generic_web.search_template",
    "name": "Generic Web Search Template",
    "kind": "search_template",
    "provider": "generic_web",
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "Tool channel: render template with {{q}}/{{page}} and parse result links.",
    "credential_refs": [],
    "default_params": {"probe_timeout": 10, "page": 1, "write_to_pool": False, "pool_scope": "project"},
    "param_schema": {"required": ["template", "query_terms"]},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_HANDLER_CLUSTER_CHANNEL: dict[str, object] = {
    "channel_key": "handler.cluster",
    "name": "Handler Cluster",
    "kind": "cluster",
    "provider": "handler",
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "Front-door channel for resource-pool handler clusters (search_template/rss/sitemap).",
    "credential_refs": [],
    "default_params": {
        "probe_timeout": 10,
        "pool_scope": "project",
        "write_to_pool": True,
        "auto_ingest": True,
        "enable_extraction": True,
        "allow_term_fallback": False,
        "prefer_crawler_first": False,
        "keyword_batch_size": 4,
        "search_parallelism": 3,
        "url_routing_parallelism": 4,
        "limit": 20,
        "max_candidates": 200,
        "ingest_limit": 20,
        "sitemap_max_depth": 2,
        "sitemap_max_sitemaps": 50,
    },
    "param_schema": {"required": ["site_entries", "expected_entry_type"]},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_OFFICIAL_ACCESS_API_CHANNEL: dict[str, object] = {
    "channel_key": "official_access.api",
    "name": "Official Access API",
    "kind": "api",
    "provider": "official_access",
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "Tool channel placeholder for official APIs. Project customization can override.",
    "credential_refs": [],
    "default_params": {},
    "param_schema": {},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_EXTERNAL_PROJECT_MANIFEST_CHANNEL: dict[str, object] = {
    "channel_key": EXTERNAL_PROJECT_CHANNEL_KEY,
    "name": "External Project Manifest",
    "kind": "manifest",
    "provider": "external_project",
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "Bounded runner for registered external-project manifests.",
    "credential_refs": [],
    "default_params": {},
    "param_schema": {},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_SPECIAL_WEB_JS_RENDER_CHANNEL: dict[str, object] = {
    "channel_key": "special_web.js_render",
    "name": "Special Web JS Render",
    "kind": "js_render",
    "provider": "special_web",
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "Tool channel placeholder for JS-rendered pages. Handler not implemented yet.",
    "credential_refs": [],
    "default_params": {},
    "param_schema": {},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_SPECIAL_WEB_ANTI_BOT_CHANNEL: dict[str, object] = {
    "channel_key": "special_web.anti_bot",
    "name": "Special Web Anti-Bot",
    "kind": "anti_bot",
    "provider": "special_web",
    "provider_type": "native",
    "provider_config": {},
    "execution_policy": {},
    "description": "Tool channel placeholder for anti-bot protected pages. Handler not implemented yet.",
    "credential_refs": [],
    "default_params": {},
    "param_schema": {},
    "extends_channel_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}

_BUILTIN_TOOL_CHANNELS: list[dict[str, object]] = [
    _URL_POOL_CHANNEL,
    _GENERIC_WEB_RSS_CHANNEL,
    _GENERIC_WEB_SITEMAP_CHANNEL,
    _GENERIC_WEB_SEARCH_TEMPLATE_CHANNEL,
    _HANDLER_CLUSTER_CHANNEL,
    _OFFICIAL_ACCESS_API_CHANNEL,
    _EXTERNAL_PROJECT_MANIFEST_CHANNEL,
    _SPECIAL_WEB_JS_RENDER_CHANNEL,
    _SPECIAL_WEB_ANTI_BOT_CHANNEL,
]


def list_effective_channels(scope: str = "effective", project_key: str | None = None) -> list[dict[str, object]]:
    shared_channels = _load_shared_channels()
    project_channels = _load_project_channels(project_key)

    # Inject built-in tool channels if not present (unified channels list)
    shared_keys = {x["channel_key"] for x in shared_channels}
    for ch in _BUILTIN_TOOL_CHANNELS:
        if ch["channel_key"] not in shared_keys:
            shared_channels = [*shared_channels, dict(ch)]
            shared_keys.add(ch["channel_key"])

    if scope == "shared":
        return [_attach_source_tiering(x) for x in shared_channels]
    if scope == "project":
        return [_attach_source_tiering(x) for x in project_channels]

    return [_attach_source_tiering(x) for x in _merge_channels(shared_channels, project_channels)]


_URL_POOL_DEFAULT_ITEM: dict[str, object] = {
    "item_key": "url_pool.default",
    "name": "URL 资源池（默认）",
    "channel_key": "url_pool",
    "description": "从 effective 范围抓取 URL 池中的 URL",
    "params": {"scope": "effective", "limit": 50},
    "tags": [],
    "schedule": None,
    "extends_item_key": None,
    "enabled": True,
    "extra": {},
    "scope": "builtin",
}


def list_items_by_symbol(scope: str = "effective", project_key: str | None = None) -> dict[str, list[dict[str, object]]]:
    """Group items by tag (symbol). Items with no tags go under '_untagged'."""
    items = list_effective_items(scope=scope, project_key=project_key)
    grouped: dict[str, list[dict[str, object]]] = {}
    for it in items:
        tags = _as_list(it.get("tags"))
        if not tags:
            key = "_untagged"
        else:
            for t in tags:
                key = str(t).strip()
                if not key:
                    continue
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(it)
        if not tags:
            if "_untagged" not in grouped:
                grouped["_untagged"] = []
            grouped["_untagged"].append(it)
    return grouped


def list_channels_grouped_by_provider(scope: str = "effective", project_key: str | None = None) -> dict[str, list[dict[str, object]]]:
    """Group channels by provider (tool type: url_pool, generic_web, official_access, special_web, etc.)."""
    channels = list_effective_channels(scope=scope, project_key=project_key)
    grouped: dict[str, list[dict[str, object]]] = {}
    for ch in channels:
        prov = str(ch.get("provider") or "unknown").strip()
        if prov not in grouped:
            grouped[prov] = []
        grouped[prov].append(ch)
    return grouped


def list_items_grouped_by_channel(scope: str = "effective", project_key: str | None = None) -> dict[str, list[dict[str, object]]]:
    """Group items by handler key (provider/kind), fallback channel_key."""
    items = list_effective_items(scope=scope, project_key=project_key)
    channels = list_effective_channels(scope=scope, project_key=project_key)
    channel_map = {str(ch.get("channel_key") or "").strip(): ch for ch in channels}
    grouped: dict[str, list[dict[str, object]]] = {}
    for it in items:
        channel_key = str(it.get("channel_key") or "").strip()
        ch = channel_map.get(channel_key) or {}
        provider = str(ch.get("provider") or "").strip().lower()
        kind = str(ch.get("kind") or "").strip().lower()
        if provider and kind:
            handler_key = f"{provider}/{kind}"
        else:
            handler_key = str(channel_key or "unknown").strip() or "unknown"
        if handler_key not in grouped:
            grouped[handler_key] = []
        grouped[handler_key].append(it)
    return grouped


def list_effective_items(
    scope: str = "effective",
    project_key: str | None = None,
    *,
    include_execution_plan: bool = False,
) -> list[dict[str, object]]:
    shared_items = _load_shared_items()
    project_items = _load_project_items(project_key)

    # Inject built-in url_pool.default item if channel exists and no url_pool item present
    shared_keys = {x["item_key"] for x in shared_items}
    project_keys = {x["item_key"] for x in project_items}
    if "url_pool.default" not in shared_keys and "url_pool.default" not in project_keys:
        shared_items = [*shared_items, dict(_URL_POOL_DEFAULT_ITEM)]

    if scope == "shared":
        return [_normalize_effective_item(item, include_execution_plan=include_execution_plan) for item in shared_items]
    if scope == "project":
        return [_normalize_effective_item(item, include_execution_plan=include_execution_plan) for item in project_items]

    return [
        _normalize_effective_item(item, include_execution_plan=include_execution_plan)
        for item in _merge_items(shared_items, project_items)
    ]


def run_item_with_url_routing(
    *,
    item: dict[str, object],
    params: Mapping[object, object],
    project_key: str | None,
    channel_map: dict[str, dict[str, object]],
    execution_layer: ExecutionLayer = "execute",
) -> RoutingObservation:
    """
    Run item with per-URL channel routing. Resolves channel per URL via url_router.
    Returns aggregated { inserted, skipped, by_url }.
    """
    urls = params.get("urls")
    url_values = object_list(urls)
    if not url_values:
        raise_resolver_failure(
            resolver_failure(
                "url_routing_urls_required",
                "params.urls must be a non-empty list for URL routing",
                site="run_item_with_url_routing.params.urls",
            )
        )

    runtime_targets: list[tuple[str, dict[str, object]]] = [
        (str(url or "").strip(), {"source": "params.urls", "index": idx}) for idx, url in enumerate(url_values)
    ]
    return _run_url_routing_materialization(
        item=item,
        params=params,
        project_key=project_key,
        channel_map=channel_map,
        runtime_targets=runtime_targets,
        execution_layer=execution_layer,
    )


def _run_url_routing_materialization(
    *,
    item: dict[str, object],
    params: Mapping[object, object],
    project_key: str | None,
    channel_map: dict[str, dict[str, object]],
    runtime_targets: Sequence[tuple[str, dict[str, object]]],
    execution_layer: ExecutionLayer = "execute",
) -> RoutingObservation:
    from .orchestrators.url_execution import fetch_routed_targets

    protocol = _build_frontdoor_protocol(item=item, params=params, project_key=project_key)
    return fetch_routed_targets(
        protocol=protocol,
        item_channel_key=str(item.get("channel_key") or "").strip(),
        params=params,
        project_key=project_key,
        channel_map=channel_map,
        runtime_targets=runtime_targets,
        execution_layer=execution_layer,
    )


def _summarize_routed_results(routed: RoutingObservation) -> RoutingSummary:
    legacy_counts = _object(routed.get("legacy_counts"))
    inserted = as_optional_int(legacy_counts.get("inserted")) or as_optional_int(routed.get("inserted")) or 0
    updated = as_optional_int(legacy_counts.get("updated")) or as_optional_int(routed.get("updated")) or 0
    skipped = as_optional_int(legacy_counts.get("skipped")) or as_optional_int(routed.get("skipped")) or 0
    errors = [str(x) for x in object_list(routed.get("errors")) if str(x or "").strip()]
    by_url = routed.get("by_url") or []

    inserted_valid = 0
    rejected_count = 0
    rejection_breakdown: dict[str, int] = {}
    error_details: list[RunnerObject] = []
    channels_used: list[str] = []
    records: list[RunnerObject] = []

    for row in by_url:
        channel_key = str(row.get("channel_key") or "").strip()
        if channel_key and channel_key not in channels_used:
            channels_used.append(channel_key)
        if row.get("error"):
            error_details.append(
                as_runner_object(
                    {
                    "url": str(row.get("url") or ""),
                    "channel_key": channel_key or None,
                    "error": str(row.get("error") or ""),
                    }
                )
            )
        result = optional_runner_object(row.get("result"))
        if not result:
            continue
        records.extend(
            extract_records_from_routed_row(
                row=row,
                result=result,
                channel_key=channel_key,
                start_index=len(records),
            )
        )
        valid = as_optional_int(result.get("inserted_valid")) or 0
        inserted_valid += valid if valid > 0 else as_optional_int(result.get("inserted")) or 0
        rejected_count += as_optional_int(result.get("rejected_count")) or 0
        rb = _object(result.get("rejection_breakdown"))
        for key, value in rb.items():
            reason = str(key or "").strip()
            if not reason:
                continue
            count = as_optional_int(value) or 0
            if count <= 0:
                continue
            rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + count

    if inserted_valid <= 0:
        inserted_valid = inserted

    fetch_stats = _object(routed.get("stats"))

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "error_details": error_details,
        "channels_used": channels_used,
        "by_url": by_url,
        "records": records,
        "stats": {
            "fetched": as_optional_int(fetch_stats.get("fetched")) or len(by_url),
            "normalized": as_optional_int(fetch_stats.get("normalized")) or len(records),
            "dropped": as_optional_int(fetch_stats.get("dropped")) or max(len(by_url) - len(records), 0),
            "errors": as_optional_int(fetch_stats.get("errors")) or len(errors),
        },
        "legacy_counts": {
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "inserted_valid": inserted_valid,
            "rejected_count": rejected_count,
            "rejection_breakdown": rejection_breakdown,
        },
    }


def extract_records_from_routed_row(
    *,
    row: RunnerObject,
    result: RunnerObject,
    channel_key: str,
    start_index: int,
) -> list[RunnerObject]:
    extracted: list[RunnerObject] = []
    record_url = str(row.get("url") or "").strip() or None
    nested_records = object_list(result.get("records"))
    if nested_records:
        for offset, nested_value in enumerate(nested_records):
            if not _is_object(nested_value):
                continue
            nested = dict(nested_value)
            nested_url = str(nested.get("url") or record_url or "").strip() or None
            record_meta = _object(nested.get("record_meta"))
            record_meta.setdefault("channel_key", channel_key or None)
            record_meta.setdefault("fallback_from_channel_key", row.get("fallback_from_channel_key"))
            record_meta.setdefault("fallback_reason", row.get("fallback_reason"))
            provider_handoff = _object(row.get("provider_handoff"))
            if provider_handoff:
                record_meta.setdefault("provider_handoff", provider_handoff)
            route_profile = _object(row.get("frontdoor_route_profile"))
            if route_profile:
                record_meta.setdefault("frontdoor_route_profile", route_profile)
            extracted.append(
                as_runner_object({
                    "record_id": str(nested.get("record_id") or nested_url or f"record:{start_index + offset}"),
                    "url": nested_url,
                    "title": str(nested.get("title") or "").strip() or None,
                    "content_text": str(nested.get("content_text") or nested.get("content_preview") or "").strip() or None,
                    "summary": str(nested.get("summary") or "").strip() or None,
                    "published_at": str(nested.get("published_at") or "").strip() or None,
                    "author": str(nested.get("author") or "").strip() or None,
                    "language": str(nested.get("language") or "").strip() or None,
                    "source_label": str(nested.get("source_label") or channel_key or "").strip() or None,
                    "record_meta": record_meta,
                    "raw_ref": {"source": "result.by_url", "url": nested_url},
                })
            )
        return extracted

    if result.get("title") or result.get("content_text") or result.get("content_preview"):
        record_meta = _object(result.get("record_meta"))
        record_meta.setdefault("channel_key", channel_key or None)
        record_meta["http_status"] = result.get("http_status")
        record_meta["execution_layer"] = result.get("execution_layer")
        record_meta["fallback_from_channel_key"] = row.get("fallback_from_channel_key")
        record_meta["fallback_reason"] = row.get("fallback_reason")
        provider_handoff = _object(row.get("provider_handoff"))
        if provider_handoff:
            record_meta["provider_handoff"] = provider_handoff
        route_profile = _object(row.get("frontdoor_route_profile"))
        if route_profile:
            record_meta["frontdoor_route_profile"] = route_profile
        extracted.append(
            as_runner_object({
                "record_id": str(result.get("record_id") or record_url or f"record:{start_index}"),
                "url": record_url,
                "title": str(result.get("title") or "").strip() or None,
                "content_text": str(result.get("content_text") or result.get("content_preview") or "").strip() or None,
                "summary": str(result.get("summary") or "").strip() or None,
                "published_at": str(result.get("published_at") or "").strip() or None,
                "author": str(result.get("author") or "").strip() or None,
                "language": str(result.get("language") or "").strip() or None,
                "source_label": str(result.get("source_label") or channel_key or "").strip() or None,
                "record_meta": record_meta,
                "raw_ref": {"source": "result.by_url", "url": record_url},
            })
        )
    return extracted


def _should_refetch_candidate_only_results(
    *,
    merged_candidates: Sequence[str],
    routed_summary: RoutingSummary,
) -> bool:
    if not merged_candidates:
        return False
    records = routed_summary["records"]
    legacy_counts = routed_summary["legacy_counts"]
    inserted_valid = int(legacy_counts.get("inserted_valid") or legacy_counts.get("inserted") or 0)
    if inserted_valid > 0:
        return False
    return len(records) <= 0


def _run_single_handler_search_batch(
    *,
    project_key: str | None,
    merged_search_item: dict[str, object],
    execution_plan: dict[str, object],
    term_batch: list[str],
    candidate_limits: HandlerCandidateLimits,
    params: Mapping[object, object],
    query_discovery_budget: "QueryDiscoveryBudget | None" = None,
) -> UnifiedSearchResult:
    from ..resource_pool.unified_search import unified_search_by_item_payload

    return unified_search_by_item_payload(
        project_key=str(project_key or ""),
        item=merged_search_item,
        execution_plan=execution_plan,
        query_terms=term_batch,
        max_candidates=batch_max_candidates(candidate_limits, len(term_batch)),
        write_to_pool=bool(params.get("write_to_pool", True)),
        pool_scope=str(params.get("pool_scope") or "project"),
        probe_timeout=_as_optional_float(params.get("probe_timeout")) or 10.0,
        sitemap_max_depth=candidate_limits.sitemap_max_depth,
        sitemap_max_sitemaps=candidate_limits.sitemap_max_sitemaps,
        auto_ingest=False,
        ingest_limit=candidate_limits.global_ingest_limit,
        enable_extraction=bool(params.get("enable_extraction", True)),
        allow_term_fallback=bool(params.get("allow_term_fallback", False)),
        query_discovery_budget=query_discovery_budget,
    )


@dataclass
class _HandlerSearchFailure:
    site_entries_used: list[RunnerObject]
    candidates: list[str]
    written: dict[str, int]
    ingest_result: RunnerObject
    errors: list[RunnerObject]
    runtime_diagnostics: list[RunnerObject] = field(default_factory=list[RunnerObject])
    relevance_review_queue: RunnerObject | None = None


def _run_handler_search_atom(
    *, item: dict[str, object], params: Mapping[object, object], query_terms: list[str],
    project_key: str | None, candidate_limits: HandlerCandidateLimits,
) -> UnifiedSearchResult | _HandlerSearchFailure:
    merged_search_item: dict[str, object] = {
        **item,
        "params": {**item_mapping_fields(item.get("params") or {}), **params},
        "extra": {
            **item_mapping_fields(item.get("extra") or {}),
            **{key: value for key, value in params.items() if key == "allow_deprioritized_site_entries"},
        },
    }
    execution_plan = build_item_execution_plan(merged_search_item)
    merged_runtime_params: dict[str, object] = {}
    for key, value in item_mapping_fields(item.get("params") or {}).items():
        if isinstance(key, str):
            merged_runtime_params[key] = value
    for key, value in params.items():
        if isinstance(key, str):
            merged_runtime_params[key] = value
    from ..resource_pool.search_contract_discovery import (
        QueryDiscoveryBudget as QueryDiscoveryBudgetImplementation,
    )

    query_discovery_budget: QueryDiscoveryBudget = (
        QueryDiscoveryBudgetImplementation.from_params(merged_runtime_params)
    )
    try:
        return _run_single_handler_search_batch(
            project_key=project_key, merged_search_item=merged_search_item,
            execution_plan=execution_plan,
            term_batch=query_terms, candidate_limits=candidate_limits, params=params,
            query_discovery_budget=query_discovery_budget,
        )
    except Exception as exc:
        return _HandlerSearchFailure(
            site_entries_used=[], candidates=[], written={"urls_new": 0, "urls_skipped": 0},
            ingest_result={
                "inserted": 0, "updated": 0, "skipped": 0, "inserted_valid": 0,
                "rejected_count": 0, "rejection_breakdown": {},
            },
            errors=[{"error": str(exc), "query_terms": list(query_terms)}],
        )


def _fetch_handler_candidates(
    *, item: dict[str, object], params: Mapping[object, object], project_key: str | None,
    channel_map: dict[str, dict[str, object]], candidates: list[str],
) -> tuple[RoutingObservation, RoutingSummary, FrontDoorExecutionProtocol]:
    routing_params: dict[object, object] = {
        **params, "urls": list(candidates),
        "disable_site_seed_expansion": True, "cluster_layer_separated": True,
    }
    protocol = _build_frontdoor_protocol(
        item=item, params=routing_params, project_key=project_key, candidate_urls=candidates,
    )
    routed = run_item_with_url_routing(
        item=item, params=routing_params, project_key=project_key,
        channel_map=channel_map, execution_layer="terminal_output_only",
    )
    summary = _summarize_routed_results(routed)
    if _should_refetch_candidate_only_results(merged_candidates=candidates, routed_summary=summary):
        refetch = run_item_with_url_routing(
            item=item,
            params={
                **routing_params, "force_url_routing_flow": True, "prefer_crawler_first": False,
                "force_crawler_fallback_on_empty": False,
            },
            project_key=project_key, channel_map=channel_map, execution_layer="terminal_output_only",
        )
        refetch_summary = _summarize_routed_results(refetch)
        if refetch_summary.get("records"):
            routed, summary = refetch, refetch_summary
    return routed, summary, protocol


def _summarize_query_contract(
    runtime_rows: Sequence[Mapping[str, object]],
    *,
    final_budget: Mapping[str, object] | None = None,
) -> dict[str, object]:
    statuses: list[str] = []
    reason_codes: list[str] = []
    exploration_requests: list[dict[str, object]] = []
    def _string_object_view(value: dict[object, object]) -> dict[str, object]:
        return {key: item for key, item in value.items() if isinstance(key, str)}

    for row in runtime_rows:
        query_contract = _object(row.get("query_contract"))
        if not query_contract:
            continue
        status = str(query_contract.get("status") or "").strip()
        if status and status not in statuses:
            statuses.append(status)
        diagnostics = _object(query_contract.get("diagnostics"))
        raw_reason_codes = diagnostics.get("reason_codes")
        reason_values = raw_reason_codes if _is_object_list(raw_reason_codes) else []
        for reason_value in reason_values:
            reason = str(reason_value or "").strip()
            if reason and reason not in reason_codes:
                reason_codes.append(reason)
        exploration = _object(query_contract.get("exploration_request"))
        if exploration:
            exploration_requests.append(_string_object_view(exploration))
    budget = dict(final_budget or {})
    return {
        "observation_kind": "query_contract_plan_and_execution",
        "claims_content_acquired": False,
        "statuses": statuses,
        "reason_codes": reason_codes,
        "exploration_requests": exploration_requests,
        "discovery_budget": budget,
    }


def _run_handler_cluster_item(
    *,
    item: dict[str, object],
    params: Mapping[object, object],
    project_key: str | None,
    channel_map: dict[str, dict[str, object]],
) -> ExecutionPayload:
    item_extra = _object((item or {}).get("extra"))
    item_params = _object((item or {}).get("params"))
    protocol = _build_frontdoor_protocol(item=item, params=params, project_key=project_key)
    q = list(protocol.query_terms)
    term_batches = [q]
    search_parallelism = 1
    candidate_limits = normalize_handler_candidate_limits(params)
    per_keyword_limit = candidate_limits.per_keyword_limit
    search = _run_handler_search_atom(
        item=item, params=params, query_terms=q, project_key=project_key,
        candidate_limits=candidate_limits,
    )

    observations = fold_search_observations([search], deduplicate_error_messages=True)
    merged_site_entries = observations.site_entries_used
    merged_candidates = observations.candidates
    written_urls_new = observations.written_urls_new
    written_urls_skipped = observations.written_urls_skipped
    merged_runtime_diagnostics = observations.runtime_diagnostics
    merged_review_queues = observations.relevance_review_queues
    merged_error_details: list[Mapping[str, object]] = list(observations.error_details)
    merged_errors = observations.errors

    routed_result: RoutingObservation = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "by_url": [],
    }
    routing_protocol = protocol
    routed_summary = _summarize_routed_results(routed_result)
    if merged_candidates:
        routed_result, routed_summary, routing_protocol = _fetch_handler_candidates(
            item=item, params=params, project_key=project_key,
            channel_map=channel_map, candidates=merged_candidates,
        )
        for detail in routed_summary["error_details"]:
            if detail not in merged_error_details:
                merged_error_details.append(detail)
        for msg in routed_summary["errors"]:
            if msg not in merged_errors:
                merged_errors.append(msg)

    result_records = list(routed_summary.get("records") or [])
    if not result_records:
        result_records = [
            {
                "record_id": f"candidate:{idx}:{url}",
                "url": url,
                "title": None,
                "content_text": None,
                "summary": None,
                "published_at": None,
                "author": None,
                "language": None,
                "source_label": "candidate_url",
                "record_meta": {"origin": "handler_cluster.candidate"},
                "raw_ref": {"source": "result.candidates", "index": idx},
            }
            for idx, url in enumerate(merged_candidates)
            if str(url or "").strip()
        ]
    relevance_review_queue = merge_relevance_review_queues(
        merged_review_queues,
        project_key=project_key,
        item_key=str(item.get("item_key") or ""),
        query_terms=q,
        source_surface="source_library.handler_cluster_frontdoor",
    )
    result_records = annotate_records_with_relevance_review_queue(
        list(result_records),
        relevance_review_queue,
    )
    result_stats = candidate_record_stats(merged_candidates, result_records, errors=merged_errors)
    routing_diagnostics = routed_result.get("diagnostics")
    url_stage = routing_diagnostics.get("url_stage") if routing_diagnostics else None
    candidate_source_types = sorted(
        {
            str(entry.get("entry_type") or "").strip().lower()
            for entry in merged_site_entries
            if str(entry.get("entry_type") or "").strip()
        }
    )
    search_service_breakdown: dict[str, int] = {}
    policy_breakdown: dict[str, int] = {}
    error_class_breakdown: dict[str, int] = {}
    slow_lane_reasons: dict[str, int] = {}
    slow_lane_deferred_count = 0
    for entry in merged_runtime_diagnostics:
        service = str(entry.get("search_service") or "").strip().lower()
        if service:
            search_service_breakdown[service] = int(search_service_breakdown.get(service) or 0) + 1
        policy = str(entry.get("site_policy") or "").strip().lower()
        if policy:
            policy_breakdown[policy] = int(policy_breakdown.get(policy) or 0) + 1
        if bool(entry.get("browser_candidate_deferred")):
            slow_lane_deferred_count += 1
            reason = str(entry.get("browser_candidate_reason") or "unknown").strip().lower()
            slow_lane_reasons[reason] = int(slow_lane_reasons.get(reason) or 0) + 1
    for detail in merged_error_details:
        error_class = str(detail.get("error_class") or "").strip().lower()
        if error_class:
            error_class_breakdown[error_class] = int(error_class_breakdown.get(error_class) or 0) + 1
        if bool(detail.get("browser_candidate_enqueued")):
            slow_lane_deferred_count += 0
            reason = str(detail.get("browser_candidate_reason") or "unknown").strip().lower()
            slow_lane_reasons[reason] = int(slow_lane_reasons.get(reason) or 0) + 1
    candidate_pipeline = {
        "mode": "query_search_candidate_fetch",
        "query_terms": q,
        "query_batches": len(term_batches),
        "search_route": {
            "service_chain": ["primary", "fallback", "slow_lane"],
            "service_chain_observation": "plan_only_not_execution_proof",
            "service_chain_execution_observed": sorted(search_service_breakdown.keys()),
            "search_service_requested": "policy_driven",
            "search_service_used": sorted(search_service_breakdown.keys()),
            "search_service_fallbacks": int(sum(1 for detail in merged_error_details if str(detail.get("error") or "").strip() == "external_search_fallback_used")),
            "slow_lane_enabled": bool(params.get("enable_external_search_slowlane", True)),
            "slow_lane": {
                "deferred_count": slow_lane_deferred_count,
                "reasons": slow_lane_reasons,
            },
            "degraded_to_static": bool(slow_lane_deferred_count and not merged_candidates),
        },
        "candidate_generation": {
            "source_types": candidate_source_types,
            "site_entry_count": len(merged_site_entries),
            "candidate_count": len(merged_candidates),
            "candidate_sources_are_fetch_targets": False,
            "site_policy_breakdown": policy_breakdown,
            "search_service_breakdown": search_service_breakdown,
            "error_class_breakdown": error_class_breakdown,
            "slow_lane_deferred_count": slow_lane_deferred_count,
            "slow_lane_reasons": slow_lane_reasons,
        },
        "relevance_review": {
            "contract_version": relevance_review_queue["contract_version"],
            "queue_state": relevance_review_queue["queue_state"],
            "queued_count": relevance_review_queue["summary"]["queued_count"],
            "fail_closed": relevance_review_queue["summary"]["fail_closed"],
            "claims_human_relevance_review_complete": False,
            "claims_live_public_replay_complete": False,
        },
        "detail_fetch": {
            "enabled": bool(merged_candidates),
            "fetch_target_count": len(merged_candidates),
            "fetch_targets_from": "candidate_urls",
            "execution_layer": "terminal_output_only",
        },
        "query_contract": _summarize_query_contract(
            merged_runtime_diagnostics,
            final_budget=getattr(search, "query_discovery_budget", None),
        ),
    }

    return {
        "item_key": str(item.get("item_key") or ""),
        "channel_key": "handler.cluster",
        "params": dict(params),
        "result": {
            "errors": merged_errors,
            "item_key": str(item.get("item_key") or ""),
            "query_terms": q,
            "per_keyword_limit": per_keyword_limit,
            "query_term_batches": term_batches,
            "batches_total": len(term_batches),
            "search_parallelism": search_parallelism,
            "concurrency_plan": dict(protocol.concurrency_plan),
            "site_entries_used": merged_site_entries,
            "runtime_diagnostics": merged_runtime_diagnostics,
            "site_entry_count": len(merged_site_entries),
            "candidates": merged_candidates,
            "records": result_records,
            "stats": result_stats,
            "relevance_review_queue": relevance_review_queue,
            "candidate_pipeline": candidate_pipeline,
            "single_write_workflow": protocol.write_mode,
            "channels_used": routed_summary["channels_used"],
            "middle_layer_protocol": (routing_protocol if merged_candidates else protocol).to_dict(),
            "url_routing_parallelism": int(routed_result.get("url_routing_parallelism") or protocol.routing_parallelism),
            "fetch_diagnostics": {
                "urls_new": written_urls_new,
                "urls_skipped": written_urls_skipped,
                "legacy_counts": dict(routed_summary.get("legacy_counts") or {}),
                "concurrency": {
                    "search": {
                        "budget": 1,
                        "parallelism": 1,
                        "fail_fast": False,
                        "timeout_seconds": None,
                        "tasks_total": len(term_batches),
                    },
                    "url": {
                        "budget": int((url_stage.get("budget") if url_stage else 0) or protocol.routing_parallelism),
                        "parallelism": int(routed_result.get("url_routing_parallelism") or protocol.routing_parallelism),
                        "fail_fast": bool(url_stage.get("fail_fast") if url_stage else False),
                        "timeout_seconds": url_stage.get("timeout_seconds") if url_stage else None,
                        "tasks_total": len(merged_candidates),
                        "timed_out": int((url_stage.get("timed_out") if url_stage else 0) or 0),
                    },
                },
            },
            "routing_result": routed_result,
            "error_details": merged_error_details,
            "handler_key": str((item_extra or {}).get("expected_entry_type") or (item_params or {}).get("expected_entry_type") or ""),
        },
    }


def _enrich_item_with_channel_tiering(
    *,
    item: dict[str, object],
    channel_map: dict[str, dict[str, object]],
) -> dict[str, object]:
    enriched = dict(item)
    extra = _as_dict(enriched.get("extra"))
    channel_key = str(enriched.get("channel_key") or "").strip()
    channel = channel_map.get(channel_key) or {}
    if not str(extra.get("source_tier") or "").strip():
        extra["source_tier"] = str(channel.get("source_tier") or "").strip()
    if not str(extra.get("onboarding_priority") or "").strip():
        extra["onboarding_priority"] = str(channel.get("onboarding_priority") or "").strip()
    source_tiering = _object(_object(channel.get("extra")).get("source_tiering"))
    if source_tiering and not _object(extra.get("source_tiering")):
        extra["source_tiering"] = source_tiering
    enriched["extra"] = extra
    return enriched

def run_item_payload(
    *,
    item: dict[str, object],
    channels: list[dict[str, object]] | None = None,
    project_key: str | None = None,
    override_params: Mapping[object, object] | None = None,
) -> dict[str, object]:
    if not item.get("enabled", True):
        raise_resolver_failure(
            resolver_failure(
                "source_item_disabled",
                f"source item disabled: {item.get('item_key')}",
                site="run_item_payload.item_disabled",
                item_key=item.get("item_key"),
            )
        )

    channels = channels if channels is not None else list_effective_channels(scope="effective", project_key=project_key)
    channel_map = {str(x["channel_key"]): x for x in channels}
    item = _enrich_item_with_channel_tiering(item=item, channel_map=channel_map)
    item = _normalize_item_taxonomy(item)
    # Base params: item.params + ingest_config + override (no channel yet)
    params = _object(item.get("params"))
    if project_key:
        config = get_ingest_config(project_key, "social_forum")
        payload = _object(config.get("payload")) if config is not None else {}
        if payload:
            params = _deep_merge(params, payload)
    if override_params:
        params = _deep_merge(params, override_params)
    single_source_guard = validate_single_source_guard(params)
    params = _normalize_search_params(params)

    # generic_web.* is internal plugin capability for site_search orchestration only.
    # Direct item execution should be blocked unless explicitly opened by internal call sites.
    item_channel_key_lower = str(item.get("channel_key") or "").strip().lower()
    generic_web_internal_item = (
        str(item.get("item_type") or "").strip().lower() == "service_aggregated"
        and str(item.get("managed_by") or "").strip().lower() == "system"
    )
    if (
        item_channel_key_lower.startswith("generic_web.")
        and not generic_web_internal_item
        and not as_bool(params.get("_allow_internal_generic_web"), False)
    ):
        raise_resolver_failure(
            resolver_failure(
                "frontdoor_entrypoint_rejected",
                "generic_web.* direct item execution is disabled; use site_search(handler.cluster) entry",
                site="run_item_payload.generic_web_direct",
                item_key=item.get("item_key"),
            )
        )

    # Keep static URL-list items on the same front-door path as runtime-provided URLs.
    # Operators can still explicitly freeze legacy fixed lists when needed.
    item_key_lower = str(item.get("item_key") or "").strip().lower()
    if item_channel_key_lower == "url_pool" or item_key_lower.startswith("url_pool."):
        allow_legacy_url_list = as_bool(params.get("enable_legacy_url_list"), True)
        if not allow_legacy_url_list and isinstance(params.get("urls"), list):
            params = dict(params)
            params.pop("urls", None)
            params["legacy_url_list_frozen"] = True

    if _is_source_library_smoke_only(params):
        return _build_source_library_smoke_payload(item=item, params=params, project_key=project_key)

    request = ItemResolver.resolve(
        item=item,
        params=params,
        project_key=project_key,
        channel_map=channel_map,
        build_frontdoor_protocol=_build_frontdoor_protocol,
        is_handler_cluster_item=_is_handler_cluster_item,
        has_site_entries=_has_site_entries,
    )
    for warning in request.warnings:
        logger.warning("source_library_execution_request_warning item=%s warning=%s", request.item_key, warning)

    if request.source_mode == "url_execution":
        payload = run_url_execution_orchestrator(
            request=request, channel_map=channel_map,
        )
    elif request.source_mode == "site_search":
        payload = run_site_search_orchestrator(
            item=item, request=request, channel_map=channel_map,
            run_handler_cluster_item=_run_handler_cluster_item,
        )
    else:
        orchestrator = (
            run_provider_harvest_orchestrator
            if request.source_mode == "provider_harvest"
            else run_protocol_search_orchestrator
        )
        payload = orchestrator(
            item=item, request=request, channel_map=channel_map,
            run_single_channel_orchestrator=partial(
                run_single_channel_orchestrator,
                deep_merge=_deep_merge, bind_project=bind_project, run_channel=run_channel,
            ),
        )

    payload_view = dict(payload)
    payload_view.setdefault("item_type", item.get("item_type"))
    payload_view.setdefault("managed_by", item.get("managed_by"))
    payload_view.setdefault("name", item.get("name"))
    payload_view.setdefault("project_key", project_key)
    payload_view.setdefault("extra", item_mapping_fields(item.get("extra") or {}))
    if single_source_guard:
        payload_view.setdefault("single_source_guard", single_source_guard)
        payload_view.setdefault("strict_source", single_source_guard)
        payload_view.setdefault(
            "execution_fact", build_single_source_execution_fact(
                single_source_guard,
                item_key=str(item.get("item_key") or "").strip() or None,
                project_key=project_key,
            ),
        )
    return payload_view
