from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any, Dict, Literal, NotRequired, Protocol, TypedDict

if TYPE_CHECKING:
    from .item_resolver import ExecutionPayload, ExecutionRequest
    from .runner import RunnerObject



SourceMode = Literal["protocol_search", "provider_harvest", "site_search", "url_execution"]
ExecutionLayer = Literal["execute", "terminal_output_only"]
TerminalStatus = Literal["ok", "partial", "error", "accepted", "completed", "failed", "cancelled"]


class TerminalCollectResult(Protocol):
    @property
    def status(self) -> str: ...


class TerminalItemView(TypedDict):
    item_key: str
    item_type: str | None
    managed_by: str | None
    external_manifest: dict[str, object] | None


class TerminalTimeWindowView(TypedDict):
    days_back: int | None
    start_time: str | None
    end_time: str | None


class TerminalPagingView(TypedDict):
    page: int | None
    start_offset: int | None
    cursor: str | None


class TerminalLimitsView(TypedDict):
    limit: int | None
    max_items: int | None
    per_keyword_limit: int | None
    max_candidates: int | None
    ingest_limit: int | None


class TerminalRequestView(TypedDict):
    project_key: str | None
    query_terms: list[str]
    time_window: TerminalTimeWindowView
    paging: TerminalPagingView
    limits: TerminalLimitsView


class TerminalErrorView(TypedDict, total=False):
    source: str
    message: str
    url: str | None
    channel_key: str | None


class TerminalStatsView(TypedDict):
    fetched: int
    normalized: int
    dropped: int
    errors: int


class TerminalRecordView(TypedDict):
    record_id: str
    url: str | None
    title: str | None
    content_text: str | None
    summary: str | None
    published_at: str | None
    author: str | None
    language: str | None
    source_label: str | None
    record_meta: dict[str, object]
    raw_ref: dict[str, object]


class TerminalResultsView(TypedDict):
    records: list[TerminalRecordView]
    stats: TerminalStatsView


class TerminalMetaView(TypedDict):
    reason_code: str
    retryable: bool
    provider: str | None
    provider_job_id: str | None
    trace_id: str | None
    warnings: list[str]
    provider_handoff: dict[str, object] | None
    frontdoor_route_profile: dict[str, object] | None
    frontdoor_router_contract: dict[str, object] | None
    terminal_readback: dict[str, object] | None
    outcome_unknown: dict[str, object] | None
    raw_result_keys: list[str]


class TerminalOutputDto(TypedDict):
    contract_version: str
    status: TerminalStatus
    source_mode: SourceMode
    item: TerminalItemView
    request: TerminalRequestView
    results: TerminalResultsView
    errors: list[TerminalErrorView]
    meta: TerminalMetaView
    raw_snapshot: dict[str, object]


class RoutingStageObservation(TypedDict):
    budget: int
    parallelism: int
    fail_fast: bool
    timeout_seconds: float | None
    tasks_total: int
    timed_out: int


class RoutingDiagnostics(TypedDict):
    concurrency_plan: dict[str, object]
    url_stage: RoutingStageObservation


class RoutingObservation(TypedDict, total=False):
    by_url: list[RunnerObject]
    records: list[RunnerObject]
    stats: dict[str, int]
    legacy_counts: dict[str, int]
    errors: list[str]
    middle_layer_protocol: dict[str, object]
    url_routing_parallelism: int
    diagnostics: RoutingDiagnostics
    execution_layer: str
    inserted: NotRequired[int]
    updated: NotRequired[int]
    skipped: NotRequired[int]


class RoutingLegacyCounts(TypedDict):
    inserted: int
    updated: int
    skipped: int
    inserted_valid: int
    rejected_count: int
    rejection_breakdown: dict[str, int]


class RoutingSummary(TypedDict):
    inserted: int
    updated: int
    skipped: int
    errors: list[str]
    error_details: list[RunnerObject]
    channels_used: list[str]
    by_url: list[RunnerObject]
    records: list[RunnerObject]
    stats: dict[str, int]
    legacy_counts: RoutingLegacyCounts


class SourceChannelExecutor(Protocol):
    def __call__(
        self, *, channel: Mapping[str, object], params: Mapping[object, object],
        project_key: str | None, item_key: str | None,
    ) -> RunnerObject: ...


class SourceItemExecutor(Protocol):
    def __call__(
        self, *, item: dict[str, object], request: ExecutionRequest,
        channel_map: dict[str, dict[str, object]],
    ) -> ExecutionPayload: ...


class SourceClusterExecutor(Protocol):
    def __call__(
        self, *, item: dict[str, object], params: Mapping[object, object],
        project_key: str | None, channel_map: dict[str, dict[str, object]],
    ) -> ExecutionPayload: ...


class SourceUrlExecutor(Protocol):
    def __call__(
        self, *, item: dict[str, object], params: Mapping[object, object],
        project_key: str | None, channel_map: dict[str, dict[str, object]],
        execution_layer: Literal["execute", "terminal_output_only"],
    ) -> RoutingObservation: ...

ItemType = Literal["user_defined", "service_aggregated"]
ManagedBy = Literal["user", "system"]


def _taxonomy_marker_text(value: object) -> str:
    return str(value or "").strip().lower()


def _item_type_marker(value: object) -> ItemType | None:
    normalized = _taxonomy_marker_text(value)
    if normalized == "user_defined":
        return "user_defined"
    if normalized == "service_aggregated":
        return "service_aggregated"
    return None


def _managed_by_marker(value: object) -> ManagedBy | None:
    normalized = _taxonomy_marker_text(value)
    if normalized == "user":
        return "user"
    if normalized == "system":
        return "system"
    return None


def resolve_source_library_item_markers(
    *,
    item_type: object = None,
    managed_by: object = None,
    item_key: object = None,
    channel_key: object = None,
    extra: Mapping[str, object] | None = None,
) -> tuple[ItemType, ManagedBy]:
    """Resolve the canonical owner markers, including legacy system identities."""
    marker_extra: Mapping[str, object] = extra or {}
    resolved_item_type = _item_type_marker(item_type)
    if resolved_item_type is None:
        resolved_item_type = _item_type_marker(marker_extra.get("item_type"))
    if resolved_item_type is None:
        normalized_channel_key = _taxonomy_marker_text(channel_key)
        normalized_item_key = _taxonomy_marker_text(item_key)
        if (
            normalized_channel_key == "handler.cluster"
            or normalized_channel_key.startswith("crawler.")
            or normalized_item_key.startswith("handler.cluster.")
            or normalized_item_key == "url_pool.default"
            or bool(marker_extra.get("stable_handler_cluster"))
            or _taxonomy_marker_text(marker_extra.get("creation_handler")).startswith(
                "handler."
            )
            or bool(_taxonomy_marker_text(marker_extra.get("crawler_provider")))
        ):
            resolved_item_type = "service_aggregated"
        else:
            resolved_item_type = "user_defined"

    resolved_managed_by = _managed_by_marker(managed_by)
    if resolved_managed_by is None:
        resolved_managed_by = _managed_by_marker(marker_extra.get("managed_by"))
    if resolved_managed_by is None:
        resolved_managed_by = (
            "system" if resolved_item_type == "service_aggregated" else "user"
        )

    return resolved_item_type, resolved_managed_by


def is_system_managed_source_library_item(
    *,
    item_type: object = None,
    managed_by: object = None,
    item_key: object = None,
    channel_key: object = None,
    extra: Mapping[str, object] | None = None,
) -> bool:
    resolved_item_type, resolved_managed_by = resolve_source_library_item_markers(
        item_type=item_type,
        managed_by=managed_by,
        item_key=item_key,
        channel_key=channel_key,
        extra=extra,
    )
    return (
        resolved_item_type == "service_aggregated"
        or resolved_managed_by == "system"
    )


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

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {field.name: getattr(self, field.name) for field in fields(self)}
        payload["query_terms"] = list(self.query_terms)
        payload["site_entries"] = list(self.site_entries)
        payload["candidate_urls"] = list(self.candidate_urls)
        payload["concurrency_plan"] = dict(self.concurrency_plan)
        pipeline_mode = {
            "search_then_route": "query_search_candidate_fetch",
            "url_routing": "candidate_fetch",
        }.get(self.execution_mode, "single_channel_execute")
        payload["pipeline"] = {
            "mode": pipeline_mode,
            "query_stage": bool(self.query_terms) and self.execution_mode == "search_then_route",
            "search_stage": self.execution_mode == "search_then_route",
            "candidate_stage": self.execution_mode in {"search_then_route", "url_routing"},
            "detail_fetch_stage": self.write_mode == "front_door_url_routing",
            "candidate_source_count": len(self.site_entries),
        }
        return payload


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
    params: Mapping[object, object] | None,
    total_search_tasks: int,
    total_url_tasks: int,
) -> Annotated[
    SourceConcurrencyPlan,
    "kit:prepared-command effect_boundary=source_library.concurrency witness=test:test_derived_service_annotations_match_fact_sources",
]:
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
