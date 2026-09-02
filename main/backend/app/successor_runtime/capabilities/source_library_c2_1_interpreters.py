"""Successor-native pure interpreter for the C2.1 resolve atom.

The interpreter is a deterministic rewrite of the legacy
``item_resolver.ItemResolver.resolve``, ``resolver._normalize_search_params``
and ``resolver._build_frontdoor_protocol`` precedence rules.  It performs no
network, database, provider or credential work, and it never imports
legacy service packages.  The legacy path is exercised only by the sibling
``successor_migration.legacy_source_library`` adapter.

All typed outputs are constructed directly from the single canonical DTO
vocabulary in ``source_library_c2_1.py``; this module keeps no parallel
observation/request types.  Inputs are read through lightweight structural
protocols so the interpreter stays independent of one concrete DTO class.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import (
    Any,
    Generic,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

from app.successor_runtime.capabilities import source_library_c2_1 as c2_1
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.language.plan import with_plan_digest
from app.successor_runtime.research.codec import is_sha256_hex

__all__ = [
    "SOURCE_LIBRARY_C2_1_KIND",
    "SOURCE_LIBRARY_C2_1_LEGACY_INTERPRETER_ID",
    "SOURCE_LIBRARY_C2_1_OWNER",
    "SOURCE_LIBRARY_C2_1_SUCCESSOR_INTERPRETER_ID",
    "CatalogSnapshotView",
    "InterpreterFailure",
    "InterpreterOutcome",
    "InterpreterSuccess",
    "ItemView",
    "PayloadView",
    "ProjectScopeView",
    "ResolutionBindingMismatch",
    "SourceLibraryC2_1SuccessorInterpreter",
    "authority_requirement_digest",
    "legacy_interpreter_profile_digest",
    "normalize_item_taxonomy_dict",
    "normalize_search_params",
    "require_exact_resolution_binding",
    "require_resource_ceiling",
    "resolve_source_execution_request",
    "successor_interpreter_profile_digest",
]


SOURCE_LIBRARY_C2_1_KIND = c2_1.SOURCE_LIBRARY_C2_1_KIND
SOURCE_LIBRARY_C2_1_OWNER = c2_1.SOURCE_LIBRARY_C2_1_OWNER
SOURCE_LIBRARY_C2_1_LEGACY_INTERPRETER_ID = "legacy.source_library.c2_1.resolve.v1"
SOURCE_LIBRARY_C2_1_SUCCESSOR_INTERPRETER_ID = (
    "successor.source_library.c2_1.resolve.v1"
)
_SOURCE_MODES = c2_1.SOURCE_MODES
_WARNING_CODES = c2_1.SOURCE_WARNING_CODES

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class InterpreterSuccess(Generic[T]):
    value: T
    disposition: Literal["SUCCEEDED"] = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class InterpreterFailure:
    code: str
    message: str
    retryable: bool = False
    disposition: Literal["FAILED"] = "FAILED"


InterpreterOutcome: TypeAlias = InterpreterSuccess[T] | InterpreterFailure


@runtime_checkable
class ProjectScopeView(Protocol):
    project_key: str
    registry_revision: int
    incarnation: str
    scope_digest: str


@runtime_checkable
class CatalogEntryView(Protocol):
    channel_key: str
    provider: str
    provider_type: str
    enabled: bool
    extra: Any


@runtime_checkable
class CatalogSnapshotView(Protocol):
    schema_version: str
    revision: int
    incarnation: str
    digest: str
    entries: tuple[Any, ...]


@runtime_checkable
class ItemView(Protocol):
    item_key: str
    channel_key: str
    enabled: bool
    item_type: str | None
    managed_by: str | None
    params: Any
    extra: Any


@runtime_checkable
class PayloadView(Protocol):
    schema_version: str
    operation_kind: str
    project_scope: ProjectScopeView
    catalog: CatalogSnapshotView
    item: ItemView
    params: Any
    payload_digest: str


def _thaw(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        if value and all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            for item in value
        ):
            return {str(key): _thaw(item) for key, item in value}
        if not value:
            return {}
        return [_thaw(item) for item in value]
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    return value


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _clamp_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(min_value, min(max_value, parsed))


def _as_optional_int(
    value: Any,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if min_value is not None and parsed < min_value:
        return None
    if max_value is not None and parsed > max_value:
        return None
    return parsed


def _as_optional_ymd(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = raw.split("-")
    if (
        len(parts) != 3
        or not (parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit())
        or len(parts[0]) != 4
        or len(parts[1]) != 2
        or len(parts[2]) != 2
    ):
        return None
    return raw


def _as_optional_float(value: Any, *, min_value: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if min_value is not None and parsed < min_value:
        return None
    return parsed


def _normalize_terms(value: Any) -> tuple[str, ...]:
    out: list[str] = []
    if isinstance(value, (list, tuple)):
        for item in value:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
    else:
        text = str(value or "").strip()
        if text:
            out.append(text)
    return tuple(out)


def _normalize_site_entries(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_entries: Any = [value]
    elif isinstance(value, (list, tuple)):
        raw_entries = value
    else:
        return ()
    out: list[str] = []
    for entry in raw_entries:
        site_url = str(entry or "").strip()
        if site_url and site_url not in out:
            out.append(site_url)
    return tuple(out)


def _split_batches(
    terms: tuple[str, ...] | list[str], chunk_size: int
) -> list[list[str]]:
    clean = list(_normalize_terms(list(terms) if isinstance(terms, tuple) else terms))
    if not clean:
        return [[]]
    size = max(1, int(chunk_size))
    return [clean[index : index + size] for index in range(0, len(clean), size)]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def normalize_search_params(raw: dict[str, Any]) -> dict[str, Any]:
    """Deterministic rewrite of legacy ``resolver._normalize_search_params``."""

    normalized = dict(raw)

    query_terms = list(
        _normalize_terms(
            normalized.get("query_terms")
            or normalized.get("keywords")
            or normalized.get("search_keywords")
            or normalized.get("base_keywords")
            or normalized.get("topic_keywords")
            or []
        )
    )
    if query_terms:
        normalized["query_terms"] = query_terms

    max_items = _as_optional_int(
        normalized.get("max_items")
        if normalized.get("max_items") is not None
        else normalized.get("limit"),
        min_value=1,
        max_value=5000,
    )
    if max_items is not None:
        normalized["max_items"] = max_items
        normalized.setdefault("limit", max_items)

    per_keyword_limit = _as_optional_int(
        normalized.get("per_keyword_limit")
        if normalized.get("per_keyword_limit") is not None
        else normalized.get("limit"),
        min_value=1,
        max_value=5000,
    )
    if per_keyword_limit is not None:
        normalized["per_keyword_limit"] = per_keyword_limit

    max_candidates = _as_optional_int(
        normalized.get("max_candidates"), min_value=1, max_value=20000
    )
    if max_candidates is None and max_items is not None:
        max_candidates = max_items
    if max_candidates is not None:
        normalized["max_candidates"] = max_candidates

    ingest_limit = _as_optional_int(
        normalized.get("ingest_limit")
        if normalized.get("ingest_limit") is not None
        else normalized.get("max_items"),
        min_value=1,
        max_value=5000,
    )
    if ingest_limit is not None:
        normalized["ingest_limit"] = ingest_limit

    page = _as_optional_int(
        normalized.get("page")
        if normalized.get("page") is not None
        else normalized.get("paged"),
        min_value=1,
        max_value=10000,
    )
    if page is not None:
        normalized["page"] = page

    page_size = _as_optional_int(
        normalized.get("page_size")
        if normalized.get("page_size") is not None
        else normalized.get("per_page"),
        min_value=1,
        max_value=1000,
    )
    if page_size is not None:
        normalized["page_size"] = page_size

    max_pages = _as_optional_int(
        normalized.get("max_pages")
        if normalized.get("max_pages") is not None
        else normalized.get("pages"),
        min_value=1,
        max_value=100,
    )
    if max_pages is not None:
        normalized["max_pages"] = max_pages

    days_back = _as_optional_int(
        normalized.get("days_back"), min_value=1, max_value=3650
    )
    if days_back is not None:
        normalized["days_back"] = days_back

    start_offset = _as_optional_int(
        normalized.get("start_offset"), min_value=1, max_value=10000
    )
    if start_offset is not None:
        normalized["start_offset"] = start_offset

    start_time = _as_optional_ymd(
        normalized.get("start_time")
        if normalized.get("start_time") is not None
        else normalized.get("date_from")
    )
    end_time = _as_optional_ymd(
        normalized.get("end_time")
        if normalized.get("end_time") is not None
        else normalized.get("date_to")
    )
    if start_time:
        normalized["start_time"] = start_time
        normalized["date_from"] = start_time
    if end_time:
        normalized["end_time"] = end_time
        normalized["date_to"] = end_time

    return normalized


def _scalar_over_limit(value: Any, limit: int) -> bool:
    if isinstance(value, str):
        return len(value) > limit
    if isinstance(value, dict):
        return any(_scalar_over_limit(item, limit) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_scalar_over_limit(item, limit) for item in value)
    return False


def require_resource_ceiling(payload: PayloadView) -> str | None:
    """Return a rejection message when the bounded envelope is exceeded."""

    ceiling = c2_1.RESOURCE_CEILING
    if len(payload.catalog.entries) > ceiling.max_catalog_entries:
        return (
            f"catalog entries {len(payload.catalog.entries)} exceed ceiling "
            f"{ceiling.max_catalog_entries}"
        )
    payload_bytes = len(canonical_json(dataclasses.asdict(payload)).encode("utf-8"))
    if payload_bytes > ceiling.max_payload_bytes:
        return (
            f"canonical payload bytes {payload_bytes} exceed ceiling "
            f"{ceiling.max_payload_bytes}"
        )
    merged = _deep_merge(_thaw(payload.item.params), _thaw(payload.params))
    terms = list(
        _normalize_terms(
            merged.get("query_terms")
            or merged.get("keywords")
            or merged.get("search_keywords")
            or merged.get("base_keywords")
            or merged.get("topic_keywords")
            or []
        )
    )
    if len(terms) > ceiling.max_query_terms:
        return f"query terms {len(terms)} exceed ceiling {ceiling.max_query_terms}"
    urls = list(_normalize_site_entries(merged.get("urls")))
    if len(urls) > ceiling.max_urls:
        return f"urls {len(urls)} exceed ceiling {ceiling.max_urls}"
    site_entries = list(
        _normalize_site_entries(
            merged.get("site_entries")
            or merged.get("site_entry_urls")
            or merged.get("official_access_site_entries")
        )
    )
    if len(site_entries) > ceiling.max_site_entries:
        return (
            f"site entries {len(site_entries)} exceed ceiling "
            f"{ceiling.max_site_entries}"
        )
    if _scalar_over_limit(dataclasses.asdict(payload), ceiling.max_scalar_length):
        return f"scalar length exceeds ceiling {ceiling.max_scalar_length}"
    return None


def _resolve_item_type(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("item_type") or "").strip().lower()
    if explicit in {"user_defined", "service_aggregated"}:
        return explicit
    extra = _thaw(payload.get("extra"))
    from_extra = str(extra.get("item_type") or "").strip().lower()
    if from_extra in {"user_defined", "service_aggregated"}:
        return from_extra
    channel_key = str(payload.get("channel_key") or "").strip().lower()
    item_key = str(payload.get("item_key") or "").strip().lower()
    if (
        channel_key == "handler.cluster"
        or channel_key.startswith("crawler.")
        or item_key.startswith("handler.cluster.")
        or item_key == "url_pool.default"
        or bool(extra.get("stable_handler_cluster"))
        or str(extra.get("creation_handler") or "")
        .strip()
        .lower()
        .startswith("handler.")
        or str(extra.get("crawler_provider") or "").strip()
    ):
        return "service_aggregated"
    return "user_defined"


def _resolve_managed_by(payload: dict[str, Any], item_type: str) -> str:
    explicit = str(payload.get("managed_by") or "").strip().lower()
    if explicit in {"user", "system"}:
        return explicit
    extra = _thaw(payload.get("extra"))
    from_extra = str(extra.get("managed_by") or "").strip().lower()
    if from_extra in {"user", "system"}:
        return from_extra
    return "system" if item_type == "service_aggregated" else "user"


def normalize_item_taxonomy_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministic rewrite of legacy ``item_resolver.normalize_item_taxonomy``."""

    out = dict(payload or {})
    extra = _thaw(out.get("extra"))
    item_type = _resolve_item_type({**out, "extra": extra})
    managed_by = _resolve_managed_by({**out, "extra": extra}, item_type)
    out["item_type"] = item_type
    out["managed_by"] = managed_by
    extra.setdefault("item_type", item_type)
    extra.setdefault("managed_by", managed_by)
    out["extra"] = extra
    return out


def _enrich_item_dict(payload: PayloadView) -> dict[str, Any]:
    item_key = str(payload.item.item_key or "").strip() or "_anonymous"
    channel_key = str(payload.item.channel_key or "").strip()
    extra = _thaw(payload.item.extra)
    entry = next(
        (
            candidate
            for candidate in payload.catalog.entries
            if candidate.channel_key == channel_key
        ),
        None,
    )
    if entry is not None:
        if not str(extra.get("source_tier") or "").strip():
            extra["source_tier"] = str(getattr(entry, "source_tier", "") or "").strip()
        if not str(extra.get("onboarding_priority") or "").strip():
            extra["onboarding_priority"] = str(
                getattr(entry, "onboarding_priority", "") or ""
            ).strip()
        entry_extra = _thaw(getattr(entry, "extra", None))
        source_tiering = entry_extra.get("source_tiering")
        if isinstance(source_tiering, dict) and not isinstance(
            extra.get("source_tiering"), dict
        ):
            extra["source_tiering"] = dict(source_tiering)
    return {
        "item_key": item_key,
        "channel_key": channel_key,
        "enabled": bool(payload.item.enabled),
        "item_type": payload.item.item_type,
        "managed_by": payload.item.managed_by,
        "params": _thaw(payload.item.params),
        "extra": extra,
    }


def _resolve_channel_family(
    *, item_channel_key: str, provider: str, provider_type: str
) -> str:
    channel_key = str(item_channel_key or "").strip().lower()
    if channel_key == "handler.cluster":
        return "handler_cluster"
    if channel_key.startswith("generic_web.") or provider == "generic_web":
        return "generic_web"
    if channel_key.startswith("crawler.") or provider_type in {
        "scrapy",
        "crawlee",
        "meltano",
    }:
        return "crawler_provider"
    if channel_key == "url_pool":
        return "url_pool"
    return provider or "single_channel"


def _is_handler_cluster_item(item: dict[str, Any] | None) -> bool:
    extra = _thaw((item or {}).get("extra"))
    return bool(
        extra.get("stable_handler_cluster")
        or str(extra.get("creation_handler") or "").startswith("handler.entry_type")
    )


def _has_site_entries(params: dict[str, Any] | None) -> bool:
    if not isinstance(params, dict):
        return False
    for key in ("site_entries", "site_entry_urls", "official_access_site_entries"):
        raw = params.get(key)
        if isinstance(raw, (list, tuple)) and any(
            str(item or "").strip() for item in raw
        ):
            return True
    return False


def _is_site_search_authoritative(
    *,
    item: dict[str, Any],
    params: dict[str, Any],
    item_channel_key: str,
    channel_family: str,
    expected_entry_type: str,
) -> bool:
    if channel_family in {"handler_cluster", "generic_web"}:
        return True
    if _is_handler_cluster_item(item):
        return True
    if _has_site_entries(params):
        return True
    return bool(expected_entry_type)


def _expected_entry_type(*, params: dict[str, Any], item: dict[str, Any]) -> str:
    return (
        str(
            params.get("expected_entry_type")
            or _thaw(item.get("extra")).get("expected_entry_type")
            or _thaw(item.get("params")).get("expected_entry_type")
            or ""
        )
        .strip()
        .lower()
    )


def _build_concurrency_plan(
    *,
    params: dict[str, Any],
    total_search_tasks: int,
    total_url_tasks: int,
) -> c2_1.FrontDoorConcurrencyPlan:
    raw = dict(params)
    batch_size = _clamp_int(
        raw.get("keyword_batch_size")
        if raw.get("keyword_batch_size") is not None
        else raw.get("batch_size", raw.get("batch")),
        4,
        min_value=1,
        max_value=100,
    )
    shared_budget = _clamp_int(
        raw.get("concurrency_budget")
        if raw.get("concurrency_budget") is not None
        else raw.get("budget"),
        4,
        min_value=1,
        max_value=64,
    )
    requested_search = _clamp_int(
        raw.get("search_parallelism")
        if raw.get("search_parallelism") is not None
        else raw.get("search", shared_budget),
        min(3, max(1, total_search_tasks or 1)),
        min_value=1,
        max_value=64,
    )
    requested_url = _clamp_int(
        raw.get("url_routing_parallelism")
        if raw.get("url_routing_parallelism") is not None
        else raw.get("routing_parallelism", raw.get("url", shared_budget)),
        min(4, max(1, total_url_tasks or 1)),
        min_value=1,
        max_value=64,
    )
    fail_fast = _as_bool(raw.get("fail_fast"), False)
    shared_timeout = _as_optional_float(raw.get("timeout"), min_value=0.001)
    search_timeout = (
        _as_optional_float(raw.get("search_timeout"), min_value=0.001) or shared_timeout
    )
    url_timeout = (
        _as_optional_float(raw.get("url_timeout_seconds"), min_value=0.001)
        or _as_optional_float(raw.get("url_timeout"), min_value=0.001)
        or _as_optional_float(raw.get("per_url_timeout_seconds"), min_value=0.001)
        or shared_timeout
    )
    if url_timeout is None:
        url_timeout = _as_optional_float(raw.get("probe_timeout"), min_value=0.001)
    search_budget = min(shared_budget, max(1, total_search_tasks or 1))
    url_budget = min(shared_budget, max(1, total_url_tasks or 1))
    search_parallelism = min(
        search_budget, requested_search, max(1, total_search_tasks or 1)
    )
    url_parallelism = min(url_budget, requested_url, max(1, total_url_tasks or 1))
    return c2_1.FrontDoorConcurrencyPlan(
        batch_size=batch_size,
        shared_budget=shared_budget,
        search=c2_1.FrontDoorConcurrencyStage(
            stage="search",
            tasks_total=max(0, total_search_tasks),
            requested_parallelism=requested_search,
            parallelism=max(1, search_parallelism),
            budget=search_budget,
            fail_fast=fail_fast,
            timeout_seconds=search_timeout,
        ),
        url=c2_1.FrontDoorConcurrencyStage(
            stage="url",
            tasks_total=max(0, total_url_tasks),
            requested_parallelism=requested_url,
            parallelism=max(1, url_parallelism),
            budget=url_budget,
            fail_fast=fail_fast,
            timeout_seconds=url_timeout,
        ),
    )


def _build_frontdoor_protocol(
    *,
    item: dict[str, Any],
    params: dict[str, Any],
    project_key: str | None,
) -> c2_1.FrontDoorProtocol:
    item_key = str(item.get("item_key") or "").strip() or "_anonymous"
    item_channel_key = str(item.get("channel_key") or "").strip()
    item_params = _thaw(item.get("params"))
    item_extra = _thaw(item.get("extra"))
    source_tier = str(item_extra.get("source_tier") or "").strip()
    onboarding_priority = str(item_extra.get("onboarding_priority") or "").strip()
    source_tiering = item_extra.get("source_tiering")
    if isinstance(source_tiering, dict):
        source_tier = str(source_tiering.get("tier") or source_tier).strip()
        onboarding_priority = str(
            source_tiering.get("onboarding_priority") or onboarding_priority
        ).strip()
    query_terms = list(
        _normalize_terms(
            params.get("query_terms")
            or params.get("keywords")
            or params.get("search_keywords")
            or params.get("base_keywords")
            or params.get("topic_keywords")
            or []
        )
    )
    site_entries = list(
        _normalize_site_entries(
            params.get("site_entries")
            or params.get("site_entry_urls")
            or params.get("official_access_site_entries")
            or item_params.get("site_entries")
            or item_params.get("site_entry_urls")
            or item_params.get("official_access_site_entries")
        )
    )
    routed_urls = list(_normalize_site_entries(params.get("urls")))
    query_batch_size = _clamp_int(
        params.get("keyword_batch_size")
        or params.get("batch_size")
        or params.get("batch"),
        4,
        min_value=1,
        max_value=100,
    )
    total_search_tasks = len(_split_batches(query_terms, query_batch_size))
    total_url_tasks = len(routed_urls) if routed_urls else len(site_entries)
    concurrency_plan = _build_concurrency_plan(
        params=params,
        total_search_tasks=total_search_tasks,
        total_url_tasks=total_url_tasks,
    )
    write_to_pool = _as_bool(params.get("write_to_pool"), True)
    auto_ingest = _as_bool(params.get("auto_ingest"), True)
    default_force_url_routing_flow = (
        item_channel_key.lower() == "url_pool"
        or item_key.lower().startswith("url_pool.")
    )
    force_url_routing_flow = _as_bool(
        params.get("force_url_routing_flow"), default_force_url_routing_flow
    )
    prefer_crawler_first = (
        _as_bool(params.get("prefer_crawler_first"), False)
        and not force_url_routing_flow
    )
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

    return c2_1.FrontDoorProtocol(
        item_key=item_key,
        item_channel_key=item_channel_key,
        project_key=str(project_key or "").strip() or None,
        front_door_owner="run_item_payload",
        execution_mode=execution_mode,
        write_mode=write_mode,
        route_decision=route_decision,
        query_terms=tuple(query_terms),
        site_entries=tuple(site_entries),
        candidate_urls=tuple(routed_urls),
        expected_entry_type=str(
            item_extra.get("expected_entry_type")
            or item_params.get("expected_entry_type")
            or ""
        ).strip()
        or None,
        write_to_pool=write_to_pool,
        auto_ingest=auto_ingest,
        ingest_limit=max(
            1, int(params.get("ingest_limit") or params.get("limit") or 20)
        ),
        force_url_routing_flow=force_url_routing_flow,
        prefer_crawler_first=prefer_crawler_first,
        search_parallelism=concurrency_plan.search.parallelism,
        routing_parallelism=concurrency_plan.url.parallelism,
        concurrency_plan=concurrency_plan,
        source_tier=source_tier,
        onboarding_priority=onboarding_priority,
    )


def _build_taxonomy(
    *,
    channel_family: str,
    item: dict[str, Any],
    expected_entry_type: str,
    site_search_authoritative: bool,
) -> c2_1.SourceTaxonomy:
    return c2_1.SourceTaxonomy(
        channel_family=channel_family,
        item_type=str(item.get("item_type") or ""),
        managed_by=str(item.get("managed_by") or ""),
        expected_entry_type=expected_entry_type or None,
        internal_adapter_only=channel_family == "generic_web",
        site_search_authoritative=site_search_authoritative,
    )


def resolve_source_execution_request(
    payload: PayloadView,
) -> c2_1.SourceResolutionResult:
    """Successor-native rewrite of the legacy resolve front door."""

    item_key = str(payload.item.item_key or "").strip() or "_anonymous"
    item_channel_key = str(payload.item.channel_key or "").strip()
    if not payload.item.enabled:
        return c2_1.RejectedResolution(
            c2_1.SourceRejection(
                code="DISABLED_ITEM",
                version="1",
                message=f"source item disabled: {item_key}",
            )
        )
    if (
        not item_key
        and not item_channel_key
        and not _thaw(payload.item.params)
        and not _thaw(payload.params)
    ):
        return c2_1.RejectedResolution(
            c2_1.SourceRejection(
                code="INVALID_ITEM",
                version="1",
                message="source item has no identity, channel or parameters",
            )
        )
    ceiling_message = require_resource_ceiling(payload)
    if ceiling_message is not None:
        return c2_1.RejectedResolution(
            c2_1.SourceRejection(
                code="RESOURCE_CEILING_EXCEEDED",
                version="1",
                message=ceiling_message,
            )
        )

    item = normalize_item_taxonomy_dict(_enrich_item_dict(payload))
    merged_raw = _deep_merge(_thaw(payload.item.params), _thaw(payload.params))
    normalized_raw = normalize_search_params(merged_raw)

    channel = next(
        (
            candidate
            for candidate in payload.catalog.entries
            if candidate.channel_key == item_channel_key
        ),
        None,
    )
    provider = str(getattr(channel, "provider", "") or "").strip().lower()
    provider_type = str(getattr(channel, "provider_type", "") or "").strip().lower()
    channel_family = _resolve_channel_family(
        item_channel_key=item_channel_key,
        provider=provider,
        provider_type=provider_type,
    )

    item_type = str(item.get("item_type") or "").strip().lower()
    managed_by = str(item.get("managed_by") or "").strip().lower()
    generic_web_internal_item = (
        item_type == "service_aggregated" and managed_by == "system"
    )
    if (
        item_channel_key.lower().startswith("generic_web.")
        and not generic_web_internal_item
    ):
        return c2_1.RejectedResolution(
            c2_1.SourceRejection(
                code="FORBIDDEN_INTERNAL_ADAPTER",
                version="1",
                message=(
                    "generic_web.* direct item execution is disabled; "
                    "use site_search(handler.cluster) entry"
                ),
            )
        )

    if item_channel_key.lower() == "url_pool" or item_key.lower().startswith(
        "url_pool."
    ):
        allow_legacy_url_list = _as_bool(
            normalized_raw.get("enable_legacy_url_list"), True
        )
        if not allow_legacy_url_list and isinstance(normalized_raw.get("urls"), list):
            normalized_raw = dict(normalized_raw)
            normalized_raw.pop("urls", None)
            normalized_raw["legacy_url_list_frozen"] = True

    expected_entry_type = _expected_entry_type(params=normalized_raw, item=item)
    site_search_authoritative = _is_site_search_authoritative(
        item=item,
        params=normalized_raw,
        item_channel_key=item_channel_key,
        channel_family=channel_family,
        expected_entry_type=expected_entry_type,
    )
    protocol = _build_frontdoor_protocol(
        item=item,
        params=normalized_raw,
        project_key=payload.project_scope.project_key,
    )

    source_mode: str = "protocol_search"
    if protocol.candidate_urls:
        source_mode = "url_execution"
    elif site_search_authoritative:
        source_mode = "site_search"
    elif provider_type in {"scrapy", "crawlee", "meltano"} or (
        item_channel_key.lower().startswith("crawler.")
    ):
        source_mode = "provider_harvest"

    warnings: list[c2_1.VersionedWarning] = []
    explicit_mode = str(normalized_raw.get("source_mode") or "").strip().lower()
    if explicit_mode:
        if explicit_mode in _SOURCE_MODES:
            source_mode = explicit_mode
        else:
            warnings.append(
                c2_1.VersionedWarning(
                    "SOURCE_MODE_INVALID_IGNORED", "1", (explicit_mode,)
                )
            )

    if protocol.candidate_urls and source_mode != "url_execution":
        warnings.append(
            c2_1.VersionedWarning(
                "SOURCE_MODE_OVERRIDDEN_BY_URLS",
                "1",
                (source_mode, "url_execution"),
            )
        )
        source_mode = "url_execution"

    if site_search_authoritative and source_mode not in {
        "site_search",
        "url_execution",
    }:
        warnings.append(
            c2_1.VersionedWarning(
                "SOURCE_MODE_COERCED_BY_SITE_SEARCH",
                "1",
                (source_mode, "site_search"),
            )
        )
        source_mode = "site_search"

    if source_mode == "site_search" and item_channel_key.lower() != "handler.cluster":
        warnings.append(
            c2_1.VersionedWarning(
                "SITE_SEARCH_FORCED_HANDLER_CLUSTER",
                "1",
                (item_channel_key or "<empty>",),
            )
        )

    if channel_family == "generic_web":
        warnings.append(
            c2_1.VersionedWarning("GENERIC_WEB_INTERNAL_ADAPTER_DETECTED", "1", ())
        )
        if source_mode not in {"site_search", "url_execution"}:
            warnings.append(
                c2_1.VersionedWarning(
                    "GENERIC_WEB_MODE_COERCED",
                    "1",
                    (source_mode, "site_search"),
                )
            )
            source_mode = "site_search"

    taxonomy = _build_taxonomy(
        channel_family=channel_family,
        item=item,
        expected_entry_type=expected_entry_type,
        site_search_authoritative=site_search_authoritative,
    )
    params_snapshot = c2_1.NormalizedParamsSnapshot.from_dict(normalized_raw)
    request = c2_1.SourceExecutionRequest(
        source_mode=c2_1.SourceMode(source_mode),
        item_key=item_key,
        item_channel_key=item_channel_key,
        project_key=str(payload.project_scope.project_key or "").strip() or None,
        project_scope=payload.project_scope,
        item_revision=payload.item.revision,
        item_incarnation=payload.item.incarnation,
        item_content_digest=payload.item.content_digest,
        catalog_revision=payload.catalog.revision,
        catalog_incarnation=payload.catalog.incarnation,
        catalog_digest=payload.catalog.digest,
        params=params_snapshot,
        protocol=protocol,
        warnings=tuple(warnings),
        taxonomy=taxonomy,
    )
    observation = c2_1.SourceResolutionObservation(
        observation_profile=c2_1.SOURCE_RESOLUTION_OBSERVATION_PROFILE,
        project_scope=payload.project_scope,
        item_revision=payload.item.revision,
        item_incarnation=payload.item.incarnation,
        item_content_digest=payload.item.content_digest,
        catalog_revision=payload.catalog.revision,
        catalog_incarnation=payload.catalog.incarnation,
        catalog_digest=payload.catalog.digest,
        normalized_params=params_snapshot,
        source_mode=request.source_mode,
        taxonomy=taxonomy,
        warnings=tuple(warnings),
        protocol=protocol,
        observation_digest="",
    )
    return c2_1.ResolvedResolution(
        request=request,
        observation_digest=observation.observation_digest,
    )


class ResolutionBindingMismatch(ValueError):
    """Raised when Program/Plan/payload/project/catalog/binding drift."""


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and is_sha256_hex(value)


def require_exact_resolution_binding(
    *,
    program: Any,
    plan: Any,
    contract_ref: OperationContractRef,
    payload_ref: Any,
    payload: PayloadView,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: Any,
    expected_interpreter_profile_digest: str | None = None,
) -> dict[str, str]:
    """Fail closed unless the complete C2.1 closure is exact."""

    failures: list[str] = []
    if payload.operation_kind != SOURCE_LIBRARY_C2_1_KIND:
        failures.append("payload operation_kind")
    if program.project_key != project_scope.project_key:
        failures.append("program/project key")
    if program.project_registry_revision != project_scope.registry_revision:
        failures.append("program/registry revision")
    if program.project_scope_digest != project_scope.scope_digest:
        failures.append("program/scope digest")
    if payload.project_scope.project_key != project_scope.project_key:
        failures.append("payload/scope project key")
    if payload.project_scope.registry_revision != project_scope.registry_revision:
        failures.append("payload/scope registry revision")
    if payload.project_scope.scope_digest != project_scope.scope_digest:
        failures.append("payload/scope digest")

    program_metadata = dict(program.metadata)
    if program_metadata.get("catalog_digest") != payload.catalog.digest:
        failures.append("program metadata/catalog digest")
    if program_metadata.get("catalog_revision") != payload.catalog.revision:
        failures.append("program metadata/catalog revision")
    if program_metadata.get("catalog_incarnation") != payload.catalog.incarnation:
        failures.append("program metadata/catalog incarnation")
    if program_metadata.get("resolved_schema") != project_scope.resolved_schema:
        failures.append("program metadata/resolved schema")
    if program_metadata.get("project_scope_incarnation") != project_scope.incarnation:
        failures.append("program metadata/scope incarnation")
    if program_metadata.get("item_revision") != payload.item.revision:
        failures.append("program metadata/item revision")
    if program_metadata.get("item_incarnation") != payload.item.incarnation:
        failures.append("program metadata/item incarnation")
    if program_metadata.get("item_content_digest") != payload.item.content_digest:
        failures.append("program metadata/item content digest")

    if program.program_digest != program.digest():
        failures.append("program digest")
    if plan.program_id != program.program_id:
        failures.append("plan/program id")
    if plan.program_digest != program.program_digest:
        failures.append("plan/program digest")
    if not _is_hex64(plan.plan_digest):
        failures.append("plan digest")
    if with_plan_digest(plan).plan_digest != plan.plan_digest:
        failures.append("plan digest forged")
    if (
        getattr(plan.input_type, "type_id", None)
        != c2_1.SOURCE_LIBRARY_C2_1_PAYLOAD_TYPE.type_id
    ):
        failures.append("plan input type")
    if (
        getattr(plan.output_type, "type_id", None)
        != c2_1.SOURCE_LIBRARY_C2_1_RESULT_TYPE.type_id
    ):
        failures.append("plan output type")

    effect_steps = tuple(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    if len(effect_steps) != 1:
        failures.append("plan effect steps")
    else:
        step_ref = effect_steps[0].operation_contract_ref
        if (
            step_ref.kind != contract_ref.kind
            or step_ref.contract_version != contract_ref.contract_version
            or step_ref.contract_digest != contract_ref.contract_digest
        ):
            failures.append("plan/contract ref")
    if any(step.step_kind == "ADMISSION" for step in plan.ordered_steps):
        failures.append("plan admission step")

    if contract_ref.kind != SOURCE_LIBRARY_C2_1_KIND:
        failures.append("contract kind")
    if not _is_hex64(contract_ref.contract_digest):
        failures.append("contract digest")
    catalog_ref = catalog.lookup(contract_ref)
    if (
        catalog_ref is None
        or catalog_ref.contract_digest != contract_ref.contract_digest
    ):
        failures.append("catalog/contract ref")

    plain = dataclasses.asdict(payload)
    expected_content_digest = sha256_hex(canonical_json(plain).encode("utf-8"))
    if payload_ref.content_digest != expected_content_digest:
        failures.append("payload ref content digest")
    if payload_ref.project_key != project_scope.project_key:
        failures.append("payload ref project key")
    if (
        getattr(payload_ref.object_type, "type_id", None)
        != c2_1.SOURCE_LIBRARY_C2_1_PAYLOAD_TYPE.type_id
    ):
        failures.append("payload ref object type")
    if not _is_hex64(payload_ref.provenance_digest):
        failures.append("payload ref provenance digest")

    if not _is_hex64(binding.binding_digest):
        failures.append("binding digest")
    if (
        getattr(binding, "operation_contract_digest", None)
        != contract_ref.contract_digest
    ):
        failures.append("binding/contract digest")
    if getattr(binding, "project_scope_digest", None) != project_scope.scope_digest:
        failures.append("binding/scope digest")
    if not _is_hex64(deployment_catalog_digest):
        failures.append("deployment catalog digest")
    if getattr(binding, "deployment_catalog_digest", None) != deployment_catalog_digest:
        failures.append("binding/deployment catalog digest")
    if (
        expected_interpreter_profile_digest is not None
        and getattr(binding, "interpreter_profile_digest", None)
        != expected_interpreter_profile_digest
    ):
        failures.append("binding/interpreter profile")

    if failures:
        raise ResolutionBindingMismatch(
            "C2.1 resolution binding drift: " + ", ".join(sorted(set(failures)))
        )
    return {
        "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest,
        "contract_digest": contract_ref.contract_digest,
        "payload_content_digest": payload_ref.content_digest,
        "binding_digest": binding.binding_digest,
    }


def legacy_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": SOURCE_LIBRARY_C2_1_LEGACY_INTERPRETER_ID,
            "version": "1.0.0",
            "donor": "item_resolver.resolve+_normalize_search_params+_build_frontdoor_protocol",
        }
    )


def successor_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": SOURCE_LIBRARY_C2_1_SUCCESSOR_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "successor-native pure source-library C2.1 algebra",
        }
    )


def authority_requirement_digest() -> str:
    return content_digest(
        {
            "schema": "mrw.successor.source-library.c2-1.authority.v1",
            "canonical_owner": SOURCE_LIBRARY_C2_1_OWNER,
            "authority": "read-only resolve_execution_request",
            "grant_scope": "project",
        }
    )


class SourceLibraryC2_1SuccessorInterpreter:
    """Bound successor interpreter validating the exact Program/Plan binding."""

    interpreter_id = SOURCE_LIBRARY_C2_1_SUCCESSOR_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: OperationContractRef,
        payload_ref: Any,
        payload: PayloadView,
        project_scope: ProjectScopeView,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: Any,
    ) -> InterpreterOutcome[c2_1.SourceResolutionResult]:
        try:
            require_exact_resolution_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    successor_interpreter_profile_digest()
                ),
            )
        except ResolutionBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )
        return InterpreterSuccess(resolve_source_execution_request(payload))
