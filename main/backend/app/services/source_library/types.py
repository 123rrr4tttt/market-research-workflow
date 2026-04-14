from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class SourceTier(str, Enum):
    TIER_1_BASELINE = "tier_1_baseline_platform"
    TIER_2_DIRECTED = "tier_2_directed_high_value"
    TIER_3_EXPERIMENTAL = "tier_3_experimental_augmentation"


class SourceOnboardingPriority(str, Enum):
    P0 = "p0_now"
    P1 = "p1_next"
    P2 = "p2_experimental"


class SourceBoundaryOwner(str, Enum):
    SOURCE_LIBRARY = "source_library"
    COLLECT_RUNTIME = "collect_runtime"
    CRAWLER_PROVIDERS = "crawlers/providers"
    DISCOVERY = "discovery"
    INGEST = "ingest"


@dataclass(slots=True)
class SourceTiering:
    tier: SourceTier
    onboarding_priority: SourceOnboardingPriority
    reason: str


@dataclass(slots=True)
class SourceLayerBoundary:
    source_catalog: SourceBoundaryOwner
    normalized_execution: SourceBoundaryOwner
    provider_dispatch: SourceBoundaryOwner | None
    discovery: SourceBoundaryOwner
    downstream_handoff: SourceBoundaryOwner


def normalize_source_tier(value: Any) -> SourceTier | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    alias_map = {
        "tier_1": SourceTier.TIER_1_BASELINE,
        "tier_1_baseline": SourceTier.TIER_1_BASELINE,
        "tier_1_baseline_platform": SourceTier.TIER_1_BASELINE,
        "baseline": SourceTier.TIER_1_BASELINE,
        "platform": SourceTier.TIER_1_BASELINE,
        "tier_2": SourceTier.TIER_2_DIRECTED,
        "tier_2_directed": SourceTier.TIER_2_DIRECTED,
        "tier_2_directed_high_value": SourceTier.TIER_2_DIRECTED,
        "directed": SourceTier.TIER_2_DIRECTED,
        "high_value": SourceTier.TIER_2_DIRECTED,
        "tier_3": SourceTier.TIER_3_EXPERIMENTAL,
        "tier_3_experimental": SourceTier.TIER_3_EXPERIMENTAL,
        "tier_3_experimental_augmentation": SourceTier.TIER_3_EXPERIMENTAL,
        "experimental": SourceTier.TIER_3_EXPERIMENTAL,
        "augmentation": SourceTier.TIER_3_EXPERIMENTAL,
    }
    return alias_map.get(raw)


def normalize_onboarding_priority(value: Any) -> SourceOnboardingPriority | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    alias_map = {
        "p0": SourceOnboardingPriority.P0,
        "p0_now": SourceOnboardingPriority.P0,
        "now": SourceOnboardingPriority.P0,
        "high": SourceOnboardingPriority.P0,
        "p1": SourceOnboardingPriority.P1,
        "p1_next": SourceOnboardingPriority.P1,
        "next": SourceOnboardingPriority.P1,
        "medium": SourceOnboardingPriority.P1,
        "p2": SourceOnboardingPriority.P2,
        "p2_experimental": SourceOnboardingPriority.P2,
        "experimental": SourceOnboardingPriority.P2,
        "low": SourceOnboardingPriority.P2,
    }
    return alias_map.get(raw)


def derive_source_tiering(
    *,
    provider: Any,
    provider_type: Any,
    explicit_tier: Any = None,
    explicit_priority: Any = None,
) -> SourceTiering:
    tier = normalize_source_tier(explicit_tier)
    priority = normalize_onboarding_priority(explicit_priority)

    provider_norm = str(provider or "").strip().lower()
    provider_type_norm = str(provider_type or "").strip().lower()
    is_crawler_provider = provider_type_norm in {"scrapy", "crawlee", "meltano"}
    is_experimental_provider = provider_norm in {"special_web"} or provider_type_norm in {"llm_crawler"}
    is_directed_provider = provider_norm in {"official_access", "market"}

    if tier is None:
        if is_experimental_provider:
            tier = SourceTier.TIER_3_EXPERIMENTAL
        elif is_directed_provider or is_crawler_provider:
            tier = SourceTier.TIER_2_DIRECTED
        else:
            tier = SourceTier.TIER_1_BASELINE

    if priority is None:
        if tier == SourceTier.TIER_1_BASELINE:
            priority = SourceOnboardingPriority.P0
        elif tier == SourceTier.TIER_2_DIRECTED:
            priority = SourceOnboardingPriority.P1
        else:
            priority = SourceOnboardingPriority.P2

    if is_experimental_provider:
        reason = "experimental provider path"
    elif is_crawler_provider:
        reason = "crawler provider path"
    elif is_directed_provider:
        reason = "directed high-value provider path"
    else:
        reason = "baseline platform provider path"

    return SourceTiering(
        tier=tier,
        onboarding_priority=priority,
        reason=reason,
    )


def default_source_layer_boundary(*, has_provider_dispatch: bool) -> SourceLayerBoundary:
    return SourceLayerBoundary(
        source_catalog=SourceBoundaryOwner.SOURCE_LIBRARY,
        normalized_execution=SourceBoundaryOwner.COLLECT_RUNTIME,
        provider_dispatch=SourceBoundaryOwner.CRAWLER_PROVIDERS if has_provider_dispatch else None,
        discovery=SourceBoundaryOwner.DISCOVERY,
        downstream_handoff=SourceBoundaryOwner.INGEST,
    )


@dataclass(slots=True)
class ChannelRecord:
    channel_key: str
    name: str
    kind: str
    provider: str
    provider_type: str
    provider_config: Dict[str, Any]
    execution_policy: Dict[str, Any]
    description: str | None
    credential_refs: list[str]
    default_params: Dict[str, Any]
    param_schema: Dict[str, Any]
    extends_channel_key: str | None
    enabled: bool
    extra: Dict[str, Any]
    scope: str


@dataclass(slots=True)
class SourceItemRecord:
    item_key: str
    name: str
    channel_key: str
    description: str | None
    params: Dict[str, Any]
    tags: list[str]
    schedule: str | None
    extends_item_key: str | None
    enabled: bool
    extra: Dict[str, Any]
    scope: str


@dataclass(slots=True)
class FrontDoorExecutionProtocol:
    item_key: str
    item_channel_key: str
    project_key: str | None
    front_door_owner: str
    execution_mode: str
    write_mode: str
    route_decision: str
    query_terms: list[str]
    site_entries: list[str]
    candidate_urls: list[str]
    expected_entry_type: str | None
    write_to_pool: bool
    auto_ingest: bool
    ingest_limit: int
    force_url_routing_flow: bool
    prefer_crawler_first: bool
    search_parallelism: int
    routing_parallelism: int
    concurrency_plan: Dict[str, Any]
    source_tier: str
    onboarding_priority: str


@dataclass(slots=True, frozen=True)
class ConcurrencyStagePlan:
    stage: str
    tasks_total: int
    requested_parallelism: int
    parallelism: int
    budget: int
    fail_fast: bool
    timeout_seconds: float | None


@dataclass(slots=True, frozen=True)
class SourceConcurrencyPlan:
    batch_size: int
    shared_budget: int
    search: ConcurrencyStagePlan
    url: ConcurrencyStagePlan


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _clamp_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(min_value, min(max_value, parsed))


def _as_optional_float(value: Any, *, min_value: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if min_value is not None and parsed < min_value:
        return None
    return parsed


def source_concurrency_plan_to_dict(plan: SourceConcurrencyPlan) -> Dict[str, Any]:
    return {
        "batch_size": plan.batch_size,
        "shared_budget": plan.shared_budget,
        "search": {
            "stage": plan.search.stage,
            "tasks_total": plan.search.tasks_total,
            "requested_parallelism": plan.search.requested_parallelism,
            "parallelism": plan.search.parallelism,
            "budget": plan.search.budget,
            "fail_fast": plan.search.fail_fast,
            "timeout_seconds": plan.search.timeout_seconds,
        },
        "url": {
            "stage": plan.url.stage,
            "tasks_total": plan.url.tasks_total,
            "requested_parallelism": plan.url.requested_parallelism,
            "parallelism": plan.url.parallelism,
            "budget": plan.url.budget,
            "fail_fast": plan.url.fail_fast,
            "timeout_seconds": plan.url.timeout_seconds,
        },
    }


def build_source_concurrency_plan(
    *,
    params: Dict[str, Any] | None,
    total_search_tasks: int,
    total_url_tasks: int,
) -> SourceConcurrencyPlan:
    raw = dict(params or {})
    batch_size = _clamp_int(
        raw.get("keyword_batch_size") if raw.get("keyword_batch_size") is not None else raw.get("batch_size", raw.get("batch")),
        4,
        min_value=1,
        max_value=100,
    )
    shared_budget = _clamp_int(
        raw.get("concurrency_budget") if raw.get("concurrency_budget") is not None else raw.get("budget"),
        4,
        min_value=1,
        max_value=64,
    )
    requested_search = _clamp_int(
        raw.get("search_parallelism") if raw.get("search_parallelism") is not None else raw.get("search", shared_budget),
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
    search_timeout = _as_optional_float(raw.get("search_timeout"), min_value=0.001) or shared_timeout
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
    search_parallelism = min(search_budget, requested_search, max(1, total_search_tasks or 1))
    url_parallelism = min(url_budget, requested_url, max(1, total_url_tasks or 1))
    return SourceConcurrencyPlan(
        batch_size=batch_size,
        shared_budget=shared_budget,
        search=ConcurrencyStagePlan(
            stage="search",
            tasks_total=max(0, total_search_tasks),
            requested_parallelism=requested_search,
            parallelism=max(1, search_parallelism),
            budget=search_budget,
            fail_fast=fail_fast,
            timeout_seconds=search_timeout,
        ),
        url=ConcurrencyStagePlan(
            stage="url",
            tasks_total=max(0, total_url_tasks),
            requested_parallelism=requested_url,
            parallelism=max(1, url_parallelism),
            budget=url_budget,
            fail_fast=fail_fast,
            timeout_seconds=url_timeout,
        ),
    )
