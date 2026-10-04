"""Frozen typed contracts for the C4 agent-batch family-local atoms.

The module owns the C4.1/C4.2/C4.3 vocabulary used by the successor program,
interpreter and substrate files: typed AgentBatchTask payloads, the exact
C2-owned source-candidate snapshot consumed read-only, batch-plan decisions,
retry-action reduction and fresh attempt intent, and durable submission
contracts using the shared STARTED/TERMINAL idempotency repository with
family-specific acceptance status kept in the typed receipt.

The module is capability-boundary only.  It never imports legacy agent-batch
services and never performs network, database, provider or credential work.
Source-mode selection and rewrite authority stay with the C2 source-library
capability; no C4-owned output carries ``source_mode``.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from app.successor_runtime.capabilities import source_library_c2_shared as c2_shared
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
    sha256_hex,
)
from app.successor_runtime.capabilities.codecs import (
    PayloadCodec,
    dataclass_codec,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)
from app.successor_runtime.language.profiles import (
    AuthorityProfile,
    ContractProfileRef,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "AGENT_BATCH_C4_OWNER",
    "AGENT_BATCH_TASK_TYPE",
    "BATCH_PLAN_OPERATION_ID",
    "BATCH_PLAN_PAYLOAD_CODEC_ID",
    "BATCH_PLAN_PAYLOAD_SCHEMA",
    "BATCH_PLAN_PAYLOAD_TYPE",
    "BATCH_PLAN_RESULT_TYPE",
    "RETRY_ACTION_TYPE",
    "RETRY_REDUCER_PAYLOAD_CODEC_ID",
    "RETRY_REDUCER_PAYLOAD_SCHEMA",
    "RETRY_REDUCER_PAYLOAD_TYPE",
    "RETRY_REDUCE_OPERATION_ID",
    "RETRY_TRANSITION_TYPE",
    "SUBMISSION_OPERATION_ID",
    "SUBMISSION_OWNER",
    "SUBMISSION_PAYLOAD_CODEC_ID",
    "AgentBatchC4CapabilityBundle",
    "AgentBatchSubmission",
    "AgentBatchSubmissionItem",
    "AgentBatchSubmissionReceipt",
    "AgentBatchTask",
    "BatchPlanPayload",
    "BatchPlanResult",
    "BranchingDecision",
    "C4AcceptanceState",
    "CriticDecision",
    "RetryAction",
    "RetryAttemptIntent",
    "RetryBudget",
    "RetryReducerInput",
    "RetryTransition",
    "SearchBrief",
    "SearchStrategyEntry",
    "SourcePreferences",
    "SupplementationDecision",
    "build_agent_batch_c4_bundle",
    "build_agent_batch_c4_catalog",
    "build_agent_batch_c4_registry",
    "build_batch_plan",
    "normalize_batch_tasks",
    "reject_source_mode",
]


AGENT_BATCH_C4_OWNER = "agent_batch.c4.v1"
SUBMISSION_OWNER = AGENT_BATCH_C4_OWNER

BATCH_PLAN_KIND = "agent_batch.build_batch_plan.v1"
BATCH_PLAN_OPERATION_ID = "agent_batch.build_batch_plan"
BATCH_PLAN_PAYLOAD_SCHEMA = "mrw.successor.agent-batch.c4-1.payload.v1"
BATCH_PLAN_PAYLOAD_CODEC_ID = "mrw.successor.agent-batch.c4-1.payload.codec.v1"
BATCH_PLAN_CATALOG_ID = "mrw.functorial-successor.agent-batch.c4-1.operations"
BATCH_PLAN_CATALOG_VERSION = "1.0.0"
BATCH_PLAN_SEMANTIC_IDENTITY = "agent-batch.build-batch-plan"
BATCH_PLAN_OBSERVATION_PROFILE = "mrw.successor.agent-batch.c4-1.observation.v1"

RETRY_REDUCE_KIND = "agent_batch.reduce_retry_action.v1"
RETRY_REDUCE_OPERATION_ID = "agent_batch.reduce_retry_action"
RETRY_REDUCER_PAYLOAD_SCHEMA = "mrw.successor.agent-batch.c4-2.payload.v1"
RETRY_REDUCER_PAYLOAD_CODEC_ID = "mrw.successor.agent-batch.c4-2.payload.codec.v1"
RETRY_REDUCE_CATALOG_ID = "mrw.functorial-successor.agent-batch.c4-2.operations"
RETRY_REDUCE_CATALOG_VERSION = "1.0.0"
RETRY_REDUCE_SEMANTIC_IDENTITY = "agent-batch.reduce-retry-action"
RETRY_REDUCE_OBSERVATION_PROFILE = "mrw.successor.agent-batch.c4-2.observation.v1"

SUBMISSION_KIND = "agent_batch.submit.v1"
SUBMISSION_OPERATION_ID = "agent_batch.submit"
SUBMISSION_CATALOG_ID = "mrw.functorial-successor.agent-batch.c4-3.operations"
SUBMISSION_CATALOG_VERSION = "1.0.0"
SUBMISSION_SEMANTIC_IDENTITY = "agent-batch.submit"
SUBMISSION_OBSERVATION_PROFILE = "mrw.successor.agent-batch.c4-3.observation.v1"

AGENT_BATCH_TASK_TYPE = ObjectType("AgentBatchTask.v1")
BATCH_PLAN_PAYLOAD_TYPE = ObjectType("BatchPlanPayload.v1")
BATCH_PLAN_RESULT_TYPE = ObjectType("BatchPlanResult.v1")
RETRY_ACTION_TYPE = ObjectType("RetryAction.v1")
RETRY_REDUCER_PAYLOAD_TYPE = ObjectType("RetryReducerInput.v1")
RETRY_TRANSITION_TYPE = ObjectType("RetryTransition.v1")
SUBMISSION_TYPE = ObjectType("AgentBatchSubmission.v1")
SUBMISSION_RECEIPT_TYPE = ObjectType("AgentBatchSubmissionReceipt.v1")

RETRIEVAL_MODE_HYBRID = "hybrid"
RETRIEVAL_MODE_SOURCE_ONLY = "source_only"
RETRIEVAL_MODE_WEB_ONLY = "web_only"
RETRIEVAL_MODES: tuple[str, ...] = (
    RETRIEVAL_MODE_HYBRID,
    RETRIEVAL_MODE_SOURCE_ONLY,
    RETRIEVAL_MODE_WEB_ONLY,
)

RETRY_ACTIONS: frozenset[str] = frozenset(
    {
        "expand_query_terms",
        "narrow_query_terms",
        "shift_time_window",
        "change_provider",
        "attach_source_library",
        "replace_source_library",
        "stop",
    }
)

# The C4 successor rewrite surface deliberately excludes source_mode.  Legacy
# compatibility observations may still prove the difference; C4 never owns it.
RETRY_REWRITE_ALLOWED_FIELDS: dict[str, tuple[str, ...]] = {
    "expand_query_terms": ("query_terms", "max_items", "override_params"),
    "narrow_query_terms": ("query_terms", "max_items", "override_params"),
    "shift_time_window": ("days_back",),
    "change_provider": ("provider", "language", "override_params"),
    "attach_source_library": (
        "item_key",
        "query_terms",
        "urls",
        "max_items",
        "provider",
        "language",
        "scope",
        "platforms",
        "override_params",
    ),
    "replace_source_library": (
        "item_key",
        "query_terms",
        "urls",
        "max_items",
        "provider",
        "language",
        "scope",
        "platforms",
        "override_params",
    ),
    "stop": (),
}
RETRY_REQUIRED_REWRITE_FIELDS: dict[str, tuple[str, ...]] = {
    "expand_query_terms": ("query_terms",),
    "narrow_query_terms": ("query_terms",),
    "shift_time_window": ("days_back",),
    "change_provider": ("provider",),
    "attach_source_library": ("item_key",),
    "replace_source_library": ("item_key",),
    "stop": (),
}

_SOURCE_ONLY_TOKENS = (
    "仅来源库",
    "只用来源库",
    "source only",
    "source_library_only",
    "fixed source only",
)
_WEB_ONLY_TOKENS = ("仅搜索", "只搜全网", "web only", "search only", "internet only")
_AXIS_HINTS = (
    ("products", ("产品", "product", "sku", "device", "terminal")),
    (
        "companies",
        ("公司", "company", "companies", "vendor", "vendors", "厂商", "enterprise"),
    ),
    ("recent_movement", ("最近", "latest", "news", "动态", "发布", "融资", "trend")),
    ("policy", ("监管", "政策", "regulation", "policy", "standard")),
    ("pricing", ("价格", "pricing", "price", "报价")),
)
_ZH_AXIS_SUFFIX = {
    "products": "产品",
    "companies": "公司 厂商",
    "recent_movement": "发布 融资 动态",
    "policy": "政策 监管",
    "pricing": "价格 报价",
}
_EN_AXIS_SUFFIX = {
    "products": "products devices",
    "companies": "companies vendors",
    "recent_movement": "launches funding news",
    "policy": "policy regulation",
    "pricing": "pricing price",
}


def _normalize_terms(value: Any) -> tuple[str, ...]:
    out: list[str] = []
    raw = value
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, (list, tuple)):
        for item in raw:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
    return tuple(out)


def _normalize_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _normalize_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(min_value, min(max_value, parsed))


def _normalize_days_back(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed < 1:
        return None
    return min(parsed, 365)


def _normalize_override_params(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return {}


def _freeze_object(value: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted((str(key), item) for key, item in value.items()))


@dataclass(frozen=True, slots=True)
class AgentBatchTask:
    """Ordered, normalized task payload owned by the agent-batch capability.

    ``source_mode`` is intentionally absent from the C4 vocabulary.  A C4 task
    may refer to a C2-owned source item by ``item_key``; source-mode selection
    and rewrite authority remain with the C2 capability.
    """

    task_id: str
    channel: str
    query_terms: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()
    max_items: int = 20
    provider: str = "auto"
    language: str = "zh"
    days_back: int | None = None
    item_key: str | None = None
    scope: str | None = None
    platforms: tuple[str, ...] = ()
    override_params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        channel = str(self.channel or "").strip().lower()
        if channel not in {"search.market", "source_library"}:
            raise ValueError(f"unsupported agent-batch channel {channel!r}")
        if channel == "search.market" and not self.query_terms:
            raise ValueError("search.market task requires query_terms")
        if channel == "source_library" and not str(self.item_key or "").strip():
            raise ValueError("source_library task requires item_key")
        object.__setattr__(self, "channel", channel)
        object.__setattr__(
            self, "query_terms", tuple(_normalize_terms(self.query_terms))
        )
        object.__setattr__(self, "urls", tuple(_normalize_string_list(self.urls)))
        object.__setattr__(
            self, "platforms", tuple(_normalize_string_list(self.platforms))
        )
        object.__setattr__(
            self,
            "max_items",
            _normalize_int(self.max_items, 20, min_value=1, max_value=100),
        )
        object.__setattr__(
            self, "provider", str(self.provider or "auto").strip() or "auto"
        )
        object.__setattr__(self, "language", str(self.language or "zh").strip() or "zh")
        object.__setattr__(self, "days_back", _normalize_days_back(self.days_back))
        item_key = str(self.item_key or "").strip() or None
        object.__setattr__(self, "item_key", item_key)
        object.__setattr__(self, "scope", str(self.scope or "").strip() or None)
        object.__setattr__(
            self, "override_params", _normalize_override_params(self.override_params)
        )

    def to_plain(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@runtime_checkable
class C2SourceCandidateView(Protocol):
    """C2-owned source candidate snapshot consumed read-only by the C4 planner.

    C4 does not define its own snapshot type.  The producer is the shared
    ``source_library_c2_shared`` vocabulary: a ``ChannelCatalogSnapshot`` plus
    an ordered tuple of ``SourceItemDefinition`` values whose content digests
    are the real C2 producer digests.
    """

    @property
    def catalog(self) -> c2_shared.ChannelCatalogSnapshot: ...

    @property
    def source_items(self) -> tuple[c2_shared.SourceItemDefinition, ...]: ...


def reject_source_mode(value: Any) -> None:
    """Recursively reject ``source_mode`` anywhere in C4-owned task/override data."""

    if isinstance(value, dict):
        if "source_mode" in value:
            raise ValueError("C4 surface must not carry source_mode")
        for item in value.values():
            reject_source_mode(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_source_mode(item)
    elif dataclasses.is_dataclass(value):
        for field_def in dataclasses.fields(value):
            reject_source_mode(getattr(value, field_def.name))


def normalize_batch_task_from_plain(
    task: dict[str, Any],
    *,
    idx: int,
    default_language: str,
) -> AgentBatchTask:
    channel = (
        str(task.get("channel") or "search.market").strip().lower() or "search.market"
    )
    if channel == "source_library":
        item_key = str(task.get("item_key") or "").strip()
        return AgentBatchTask(
            task_id=str(task.get("task_id") or f"search_{idx}"),
            channel=channel,
            query_terms=_normalize_terms(task.get("query_terms")),
            urls=_normalize_string_list(task.get("urls")),
            max_items=_normalize_int(
                task.get("max_items"), 20, min_value=1, max_value=100
            ),
            provider=str(task.get("provider") or "auto").strip() or "auto",
            language=str(task.get("language") or default_language).strip()
            or default_language,
            days_back=_normalize_days_back(task.get("days_back")),
            item_key=item_key,
            scope=str(task.get("scope") or "").strip() or None,
            platforms=_normalize_string_list(task.get("platforms")),
            override_params=_normalize_override_params(task.get("override_params")),
        )
    return AgentBatchTask(
        task_id=str(task.get("task_id") or f"search_{idx}"),
        channel="search.market",
        query_terms=_normalize_terms(task.get("query_terms")),
        urls=_normalize_string_list(task.get("urls")),
        max_items=_normalize_int(task.get("max_items"), 20, min_value=1, max_value=100),
        provider=str(task.get("provider") or "auto").strip() or "auto",
        language=str(task.get("language") or default_language).strip()
        or default_language,
        days_back=_normalize_days_back(task.get("days_back")),
        item_key=None,
        scope=str(task.get("scope") or "").strip() or None,
        platforms=_normalize_string_list(task.get("platforms")),
        override_params=_normalize_override_params(task.get("override_params")),
    )


def normalize_batch_tasks(
    tasks: Any,
    *,
    default_language: str = "zh",
) -> tuple[AgentBatchTask, ...]:
    """Deterministic ordered task normalization; malformed entries are dropped."""

    out: list[AgentBatchTask] = []
    if isinstance(tasks, tuple):
        plain_tasks = [dataclasses.asdict(item) for item in tasks]
    elif isinstance(tasks, list):
        plain_tasks = [dict(item) for item in tasks]
    else:
        plain_tasks = []
    for idx, task in enumerate(plain_tasks, start=1):
        try:
            normalized = normalize_batch_task_from_plain(
                task, idx=idx, default_language=default_language
            )
        except (TypeError, ValueError):
            continue
        out.append(normalized)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class BatchPlanPayload:
    """Exact C4.1 atom payload; raw dictionaries live only at the codec edge."""

    schema_version: Literal["mrw.successor.agent-batch.c4-1.payload.v1"]
    operation_kind: Literal["agent_batch.build_batch_plan.v1"]
    project_key: str
    registry_revision: int
    resolved_schema: str
    scope_incarnation: str
    scope_digest: str
    tasks: tuple[AgentBatchTask, ...]
    retrieval_mode: str
    command: str
    language: str
    coverage_axes: tuple[str, ...]
    candidates: C2SourceCandidateView
    limited_branching_enabled: bool
    max_source_tasks: int = 2
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != BATCH_PLAN_PAYLOAD_SCHEMA:
            raise ValueError(f"unsupported payload schema {self.schema_version!r}")
        if self.operation_kind != BATCH_PLAN_KIND:
            raise ValueError(f"unsupported operation kind {self.operation_kind!r}")
        if self.retrieval_mode not in RETRIEVAL_MODES:
            raise ValueError(f"unsupported retrieval mode {self.retrieval_mode!r}")
        if not self.project_key:
            raise ValueError("BatchPlanPayload.project_key is required")
        require_hex64(self.scope_digest, "BatchPlanPayload.scope_digest")
        object.__setattr__(
            self,
            "tasks",
            tuple(normalize_batch_tasks(self.tasks, default_language=self.language)),
        )
        object.__setattr__(
            self, "coverage_axes", tuple(_normalize_string_list(self.coverage_axes))
        )
        object.__setattr__(
            self,
            "max_source_tasks",
            _normalize_int(self.max_source_tasks, 2, min_value=0, max_value=8),
        )
        expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            require_hex64(self.payload_digest, "BatchPlanPayload.payload_digest")
            if self.payload_digest != expected:
                raise ValueError(
                    "BatchPlanPayload.payload_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True, slots=True)
class SourcePreferences:
    attach_source_library: bool
    candidate_items: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchStrategyEntry:
    label: str
    query_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchBrief:
    intent: str
    goal: str
    coverage_axes: tuple[str, ...]
    time_mode: str
    days_back: int | None
    search_strategies: tuple[SearchStrategyEntry, ...]
    source_preferences: SourcePreferences

    def to_plain(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True, slots=True)
class SupplementationDecision:
    enabled: bool
    item_keys: tuple[str, ...] = ()
    selection_mode: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BranchingDecision:
    enabled: bool
    branch_count: int = 1
    reason: str = "disabled"
    strategy_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BatchPlanResult:
    """Ordered C4.1 plan output; never carries C2 ``source_mode``."""

    schema_version: str
    tasks: tuple[AgentBatchTask, ...]
    supplementation: SupplementationDecision
    branching: BranchingDecision
    search_brief: SearchBrief
    result_digest: str = ""

    def __post_init__(self) -> None:
        if any(
            getattr(task, "item_key", None) is not None
            and "source_mode" in dataclasses.asdict(task)
            for task in self.tasks
        ):
            raise ValueError("C4 output must not carry source_mode")
        if self.result_digest == "":
            object.__setattr__(
                self,
                "result_digest",
                content_digest(self, omit_fields=("result_digest",)),
            )
        else:
            require_hex64(self.result_digest, "BatchPlanResult.result_digest")


def _detect_language(command: str) -> str:
    text = str(command or "")
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return "zh"
    if any("a" <= char.lower() <= "z" for char in text):
        return "en"
    return "zh"


def _infer_coverage_axes(
    command: str, tasks: tuple[AgentBatchTask, ...]
) -> tuple[str, ...]:
    joined = " ".join(
        [str(command or "")] + [term for task in tasks for term in task.query_terms]
    ).lower()
    axes: list[str] = []
    for label, hints in _AXIS_HINTS:
        if any(hint in joined for hint in hints):
            axes.append(label)
    if not axes:
        axes.append("market_overview")
    return tuple(axes)


def _resolve_time_strategy_mode(
    tasks: tuple[AgentBatchTask, ...],
    retrieval_mode: str,
) -> str:
    if retrieval_mode == RETRIEVAL_MODE_SOURCE_ONLY:
        return "source_only"
    days = [task.days_back for task in tasks if isinstance(task.days_back, int)]
    if any(day <= 30 for day in days):
        return "recent"
    if any(day > 30 for day in days):
        return "historical_window"
    return "recent"


def _resolve_days_back(tasks: tuple[AgentBatchTask, ...]) -> int | None:
    for task in tasks:
        if isinstance(task.days_back, int) and task.days_back > 0:
            return task.days_back
    return 30


def _build_search_strategy_entries(
    tasks: tuple[AgentBatchTask, ...],
) -> tuple[SearchStrategyEntry, ...]:
    entries: list[SearchStrategyEntry] = []
    for task in tasks:
        if task.channel == "search.market" and task.query_terms:
            label = (
                "broad"
                if not entries
                else "precision"
                if len(entries) == 1
                else f"query_{len(entries) + 1}"
            )
            entries.append(
                SearchStrategyEntry(label=label, query_terms=task.query_terms)
            )
    if entries:
        return tuple(entries)
    source_keys = tuple(
        task.item_key
        for task in tasks
        if task.channel == "source_library" and task.item_key
    )
    if source_keys:
        return (
            SearchStrategyEntry(label="source_library_only", query_terms=source_keys),
        )
    return (SearchStrategyEntry(label="broad", query_terms=("市场研究",)),)


def build_search_brief(
    *,
    command: str,
    intent: str,
    tasks: tuple[AgentBatchTask, ...],
    retrieval_mode: str,
    candidate_keys: tuple[str, ...],
    supplementation_enabled: bool,
) -> SearchBrief:
    source_keys = tuple(
        task.item_key
        for task in tasks
        if task.channel == "source_library" and task.item_key
    )
    return SearchBrief(
        intent=str(intent or "market_research_general").strip()
        or "market_research_general",
        goal=str(command or "").strip(),
        coverage_axes=_infer_coverage_axes(command, tasks),
        time_mode=_resolve_time_strategy_mode(tasks, retrieval_mode),
        days_back=_resolve_days_back(tasks),
        search_strategies=_build_search_strategy_entries(tasks),
        source_preferences=SourcePreferences(
            attach_source_library=bool(supplementation_enabled or source_keys),
            candidate_items=source_keys or candidate_keys,
        ),
    )


def _source_collect_limit(tasks: tuple[AgentBatchTask, ...]) -> int:
    limits = [
        task.max_items
        for task in tasks
        if task.channel in {"search.market", "source_library"}
    ]
    if not limits:
        return 20
    return max(1, min(100, max(limits)))


def _source_query_terms(tasks: tuple[AgentBatchTask, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for task in tasks:
        if task.channel != "search.market":
            continue
        for term in task.query_terms:
            if term and term not in out:
                out.append(term)
    return tuple(out)


def _supplement_with_source_candidates(
    tasks: tuple[AgentBatchTask, ...],
    *,
    retrieval_mode: str,
    candidates: C2SourceCandidateView,
    max_source_tasks: int,
) -> tuple[tuple[AgentBatchTask, ...], SupplementationDecision]:
    if not tasks and retrieval_mode != RETRIEVAL_MODE_SOURCE_ONLY:
        return tasks, SupplementationDecision(False, reason="empty_tasks")
    if retrieval_mode == RETRIEVAL_MODE_WEB_ONLY:
        return tasks, SupplementationDecision(False, reason="web_only_mode")
    already_planned = any(task.channel == "source_library" for task in tasks)
    if already_planned and retrieval_mode != RETRIEVAL_MODE_SOURCE_ONLY:
        return tasks, SupplementationDecision(
            False, reason="source_library_already_planned"
        )
    item_keys = tuple(
        item.item_key
        for item in candidates.source_items
        if item.enabled and str(item.item_key or "").strip()
    )[: max(0, max_source_tasks)]
    if not item_keys:
        return tasks, SupplementationDecision(False, reason="no_source_library_match")
    source_collect_limit = _source_collect_limit(tasks)
    source_query_terms = _source_query_terms(tasks)
    appended = tuple(
        AgentBatchTask(
            task_id=f"source_{idx}",
            channel="source_library",
            query_terms=source_query_terms,
            max_items=source_collect_limit,
            provider="auto",
            language="zh",
            days_back=None,
            item_key=item_key,
            scope=None,
            platforms=(),
            override_params={
                "autonomous_strategy": "mode_driven_source_library",
                "autonomous_reason": "fixed_source_mode",
            },
        )
        for idx, item_key in enumerate(item_keys, start=1)
    )
    if retrieval_mode == RETRIEVAL_MODE_SOURCE_ONLY:
        preserved = tuple(task for task in tasks if task.channel == "source_library")
        merged = preserved + appended
    else:
        merged = tasks + appended
    return merged, SupplementationDecision(
        True,
        item_keys=item_keys,
        selection_mode="goal_relevance",
    )


def _precision_retry_query_terms(
    *,
    command: str,
    tasks: tuple[AgentBatchTask, ...],
    coverage_axes: tuple[str, ...],
) -> tuple[str, ...]:
    primary = next((task for task in tasks if task.channel == "search.market"), None)
    if primary is None:
        primary = tasks[0] if tasks else None
    if primary is None:
        return ()
    base_query = " ".join(primary.query_terms).strip() or str(command or "").strip()
    if not base_query:
        return ()
    language = str(primary.language or _detect_language(command)).strip().lower()
    suffix = _ZH_AXIS_SUFFIX if language.startswith("zh") else _EN_AXIS_SUFFIX
    suffix_tokens: list[str] = []
    for axis in coverage_axes:
        token = str(suffix.get(str(axis)) or "").strip()
        if token:
            suffix_tokens.append(token)
    merged = re.sub(r"\s+", " ", " ".join([base_query] + suffix_tokens)).strip()
    return (merged,) if merged else ()


def _expand_tasks_with_limited_branching(
    tasks: tuple[AgentBatchTask, ...],
    *,
    search_brief: SearchBrief,
    retrieval_mode: str,
    enable_limited_branching: bool,
    command: str,
) -> tuple[tuple[AgentBatchTask, ...], BranchingDecision]:
    if not enable_limited_branching:
        return tasks, BranchingDecision(False, 1, "disabled")
    if retrieval_mode == RETRIEVAL_MODE_SOURCE_ONLY:
        return tasks, BranchingDecision(False, 1, "source_only_mode")
    if len(tasks) != 1:
        return tasks, BranchingDecision(False, 1, "multi_task_plan")
    primary = tasks[0]
    if primary.channel != "search.market":
        return tasks, BranchingDecision(False, 1, "non_search_market_task")
    if len(search_brief.coverage_axes) < 2:
        return tasks, BranchingDecision(False, 1, "low_ambiguity_prompt")
    precision_terms = _precision_retry_query_terms(
        command=command,
        tasks=tasks,
        coverage_axes=search_brief.coverage_axes,
    )
    if not precision_terms:
        return tasks, BranchingDecision(False, 1, "precision_variant_unavailable")
    if precision_terms == primary.query_terms:
        return tasks, BranchingDecision(False, 1, "no_distinct_precision_variant")
    broad_task = dataclasses.replace(
        primary,
        task_id=primary.task_id or "search_1",
    )
    precision_task = dataclasses.replace(
        primary,
        task_id=f"{primary.task_id or 'search_1'}_branch_precision",
        query_terms=precision_terms,
        max_items=max(1, primary.max_items),
    )
    if broad_task.query_terms == precision_task.query_terms:
        return tasks, BranchingDecision(False, 1, "precision_variant_collapsed")
    return (
        (broad_task, precision_task),
        BranchingDecision(True, 2, "high_ambiguity_prompt", ("broad", "precision")),
    )


def build_batch_plan(payload: BatchPlanPayload) -> BatchPlanResult:
    """Deterministic ordered pure batch-plan construction (C4.1).

    The planner consumes the exact C2-owned candidate snapshot without any
    source-mode write.  Ordering is supplementation before branching and broad
    before precision; every traversal is explicit and sequential in task
    order.
    """

    reject_source_mode(payload)
    tasks = normalize_batch_tasks(payload.tasks, default_language=payload.language)
    if not tasks and payload.retrieval_mode != RETRIEVAL_MODE_SOURCE_ONLY:
        raise ValueError("planner produced no executable tasks")
    tasks, supplementation = _supplement_with_source_candidates(
        tasks,
        retrieval_mode=payload.retrieval_mode,
        candidates=payload.candidates,
        max_source_tasks=payload.max_source_tasks,
    )
    pre_branch_brief = build_search_brief(
        command=payload.command,
        intent=payload.command,
        tasks=tasks,
        retrieval_mode=payload.retrieval_mode,
        candidate_keys=supplementation.item_keys,
        supplementation_enabled=supplementation.enabled,
    )
    tasks, branching = _expand_tasks_with_limited_branching(
        tasks,
        search_brief=pre_branch_brief,
        retrieval_mode=payload.retrieval_mode,
        enable_limited_branching=payload.limited_branching_enabled,
        command=payload.command,
    )
    if not tasks:
        raise ValueError("planner produced no executable tasks")
    search_brief = build_search_brief(
        command=payload.command,
        intent=payload.command,
        tasks=tasks,
        retrieval_mode=payload.retrieval_mode,
        candidate_keys=supplementation.item_keys,
        supplementation_enabled=supplementation.enabled,
    )
    return BatchPlanResult(
        schema_version="mrw.successor.agent-batch.c4-1.result.v1",
        tasks=tasks,
        supplementation=supplementation,
        branching=branching,
        search_brief=search_brief,
    )


@dataclass(frozen=True, slots=True)
class CriticDecision:
    score: float
    next_action: str
    reason_codes: tuple[str, ...] = ()
    rewrite: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reason_codes", tuple(_normalize_string_list(self.reason_codes))
        )
        object.__setattr__(self, "rewrite", _normalize_override_params(self.rewrite))


@dataclass(frozen=True, slots=True)
class RetryAction:
    action: str
    reason: str
    channel: str | None = None
    rewrite: dict[str, Any] = field(default_factory=dict)
    target_items: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        action = str(self.action or "").strip().lower()
        if action not in RETRY_ACTIONS:
            raise ValueError(f"unsupported retry action {action!r}")
        if not str(self.reason or "").strip():
            raise ValueError("retry action reason is required")
        object.__setattr__(self, "action", action)
        object.__setattr__(
            self, "channel", str(self.channel or "").strip().lower() or None
        )
        object.__setattr__(self, "rewrite", _normalize_override_params(self.rewrite))
        object.__setattr__(
            self, "target_items", tuple(_normalize_string_list(self.target_items))
        )


@dataclass(frozen=True, slots=True)
class RetryBudget:
    remaining: int
    used: int = 0
    max_rounds: int = 1

    def __post_init__(self) -> None:
        for name in ("remaining", "used", "max_rounds"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"RetryBudget.{name} must be a non-negative int")


@dataclass(frozen=True, slots=True)
class RetryReducerInput:
    """Exact C4.2 atom payload; the reducer never performs submit effects."""

    schema_version: Literal["mrw.successor.agent-batch.c4-2.payload.v1"]
    operation_kind: Literal["agent_batch.reduce_retry_action.v1"]
    project_key: str
    registry_revision: int
    resolved_schema: str
    scope_incarnation: str
    scope_digest: str
    tasks: tuple[AgentBatchTask, ...]
    critic: CriticDecision
    retry_action: RetryAction
    budget: RetryBudget
    prior_attempt_ref: str
    command: str
    retry_enabled: bool = True
    dry_run: bool = False
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != RETRY_REDUCER_PAYLOAD_SCHEMA:
            raise ValueError(f"unsupported payload schema {self.schema_version!r}")
        if self.operation_kind != RETRY_REDUCE_KIND:
            raise ValueError(f"unsupported operation kind {self.operation_kind!r}")
        require_hex64(self.scope_digest, "RetryReducerInput.scope_digest")
        object.__setattr__(self, "tasks", tuple(normalize_batch_tasks(self.tasks)))
        if not self.prior_attempt_ref:
            raise ValueError("RetryReducerInput.prior_attempt_ref is required")
        expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            require_hex64(self.payload_digest, "RetryReducerInput.payload_digest")
            if self.payload_digest != expected:
                raise ValueError(
                    "RetryReducerInput.payload_digest does not match content"
                )


def validate_retry_action(
    action: RetryAction,
) -> tuple[RetryAction, str | None, dict[str, Any]]:
    """Fail-closed typed retry-action validation for the C4 successor reducer.

    The rewrite surface is C4-owned and deliberately rejects ``source_mode``;
    only the legacy adapter may observe the legacy surface difference.
    """

    if action.action == "stop":
        return RetryAction(action="stop", reason=action.reason), None, {}
    if action.channel not in {"search.market", "source_library"}:
        return action, "retry_action_channel_invalid", {"channel": action.channel}
    allowed = set(RETRY_REWRITE_ALLOWED_FIELDS[action.action])
    required = set(RETRY_REQUIRED_REWRITE_FIELDS[action.action])
    unsupported = sorted(key for key in action.rewrite if key not in allowed)
    if unsupported:
        return (
            action,
            "retry_action_rewrite_fields_unsupported",
            {
                "unsupported_fields": unsupported,
                "allowed_fields": sorted(allowed),
            },
        )
    normalized: dict[str, Any] = {}
    for field_name in sorted(allowed):
        if field_name not in action.rewrite:
            continue
        value = _normalize_retry_rewrite_value(field_name, action.rewrite[field_name])
        if value in (None, (), {}):
            continue
        normalized[field_name] = value
    missing = sorted(
        field_name for field_name in required if field_name not in normalized
    )
    if missing:
        return (
            action,
            "retry_action_rewrite_fields_missing",
            {"missing_required_fields": missing},
        )
    return (
        RetryAction(
            action=action.action,
            reason=action.reason,
            channel=action.channel,
            rewrite=normalized,
            target_items=action.target_items,
        ),
        None,
        {},
    )


def _normalize_retry_rewrite_value(field_name: str, value: Any) -> Any:
    if field_name == "query_terms":
        terms = _normalize_terms(value)
        return list(terms)
    if field_name in {"urls", "platforms", "target_items"}:
        items = _normalize_string_list(value)
        return list(items)
    if field_name == "max_items":
        return _normalize_int(value, 20, min_value=1, max_value=100)
    if field_name == "days_back":
        return _normalize_days_back(value)
    if field_name == "override_params":
        return _normalize_override_params(value)
    text = str(value or "").strip()
    return text or None


def _apply_retry_rewrite(
    tasks: tuple[AgentBatchTask, ...],
    action: RetryAction,
    *,
    command: str,
) -> tuple[AgentBatchTask, ...]:
    if action.action == "stop":
        return tasks
    if action.action == "attach_source_library":
        item_key = str(action.rewrite.get("item_key") or "").strip()
        if not item_key:
            return tasks
        if any(
            task.channel == "source_library" and task.item_key == item_key
            for task in tasks
        ):
            return tasks
        source_query_terms = tuple(_normalize_terms(action.rewrite.get("query_terms")))
        appended = AgentBatchTask(
            task_id=f"source_{len(tasks) + 1}",
            channel="source_library",
            query_terms=source_query_terms,
            urls=tuple(_normalize_string_list(action.rewrite.get("urls"))),
            max_items=_normalize_int(
                action.rewrite.get("max_items"), 20, min_value=1, max_value=100
            ),
            provider=str(action.rewrite.get("provider") or "auto").strip() or "auto",
            language=str(
                action.rewrite.get("language") or _detect_language(command)
            ).strip()
            or _detect_language(command),
            days_back=None,
            item_key=item_key,
            scope=str(action.rewrite.get("scope") or "").strip() or None,
            platforms=tuple(_normalize_string_list(action.rewrite.get("platforms"))),
            override_params=_normalize_override_params(
                action.rewrite.get("override_params")
            ),
        )
        return tasks + (appended,)
    out: list[AgentBatchTask] = []
    for task in tasks:
        if task.channel != action.channel:
            out.append(task)
            continue
        values: dict[str, Any] = {}
        for key, value in action.rewrite.items():
            if key == "query_terms":
                values[key] = tuple(_normalize_terms(value))
            elif key in {"urls", "platforms"}:
                values[key] = tuple(_normalize_string_list(value))
            elif key == "max_items":
                values[key] = _normalize_int(
                    value, task.max_items, min_value=1, max_value=100
                )
            elif key == "days_back":
                values[key] = _normalize_days_back(value)
            elif key == "override_params":
                values[key] = _normalize_override_params(value)
            else:
                values[key] = str(value or "").strip() or None
        out.append(dataclasses.replace(task, **values))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class RetryAttemptIntent:
    """Fresh attempt identity emitted by the pure reducer for the runtime."""

    attempt_id: str
    round_index: int
    prior_attempt_ref: str
    idempotency_key: str
    attempt_intent_digest: str = ""

    def __post_init__(self) -> None:
        if (
            not self.attempt_id
            or not self.prior_attempt_ref
            or not self.idempotency_key
        ):
            raise ValueError(
                "RetryAttemptIntent requires attempt/prior/idempotency identity"
            )
        if (
            not isinstance(self.round_index, int)
            or isinstance(self.round_index, bool)
            or self.round_index < 1
        ):
            raise ValueError("RetryAttemptIntent.round_index must be a positive int")
        if self.attempt_intent_digest == "":
            object.__setattr__(
                self,
                "attempt_intent_digest",
                content_digest(self, omit_fields=("attempt_intent_digest",)),
            )
        else:
            require_hex64(
                self.attempt_intent_digest, "RetryAttemptIntent.attempt_intent_digest"
            )


@dataclass(frozen=True, slots=True)
class RetryTransition:
    kind: Literal["RETRY_SCHEDULED", "RETRY_SKIPPED", "RETRY_REJECTED"]
    tasks: tuple[AgentBatchTask, ...]
    observations: dict[str, Any]
    attempt_intent: RetryAttemptIntent | None = None
    transition_digest: str = ""

    def __post_init__(self) -> None:
        if self.kind not in {"RETRY_SCHEDULED", "RETRY_SKIPPED", "RETRY_REJECTED"}:
            raise ValueError(f"unsupported retry transition {self.kind!r}")
        object.__setattr__(
            self, "observations", _normalize_override_params(self.observations)
        )
        if self.kind == "RETRY_SCHEDULED" and self.attempt_intent is None:
            raise ValueError("RETRY_SCHEDULED requires a fresh attempt intent")
        if self.kind != "RETRY_SCHEDULED" and self.attempt_intent is not None:
            raise ValueError("only RETRY_SCHEDULED may carry an attempt intent")
        if self.transition_digest == "":
            object.__setattr__(
                self,
                "transition_digest",
                content_digest(self, omit_fields=("transition_digest",)),
            )
        else:
            require_hex64(self.transition_digest, "RetryTransition.transition_digest")


def reduce_retry_action(payload: RetryReducerInput) -> RetryTransition:
    """Pure ordered retry reducer (C4.2); submit is not part of this atom."""

    reject_source_mode(payload)
    budget = payload.budget
    observations: dict[str, Any] = {
        "retry_enabled": bool(payload.retry_enabled),
        "dry_run": bool(payload.dry_run),
        "budget_remaining": budget.remaining,
        "budget_used": budget.used,
        "max_retry_rounds": budget.max_rounds,
        "action": payload.retry_action.action,
        "task_count": len(payload.tasks),
    }
    if not payload.retry_enabled:
        observations["skip_reason"] = "bounded_retry_disabled"
        return RetryTransition(
            kind="RETRY_SKIPPED", tasks=payload.tasks, observations=observations
        )
    if payload.dry_run:
        observations["skip_reason"] = "dry_run"
        return RetryTransition(
            kind="RETRY_SKIPPED", tasks=payload.tasks, observations=observations
        )
    if (
        budget.remaining <= 0
        or budget.max_rounds <= 0
        or budget.used >= budget.max_rounds
    ):
        observations["skip_reason"] = "retry_budget_exhausted"
        return RetryTransition(
            kind="RETRY_SKIPPED", tasks=payload.tasks, observations=observations
        )
    if payload.critic.next_action == "stop":
        observations["skip_reason"] = "critic_stop"
        return RetryTransition(
            kind="RETRY_SKIPPED", tasks=payload.tasks, observations=observations
        )
    if (
        payload.critic.score >= 0.72
        and "source_backing_missing" not in payload.critic.reason_codes
    ):
        observations["skip_reason"] = "score_above_threshold"
        return RetryTransition(
            kind="RETRY_SKIPPED", tasks=payload.tasks, observations=observations
        )

    normalized, reason_code, details = validate_retry_action(payload.retry_action)
    if reason_code is not None:
        observations["validation_failure"] = reason_code
        observations["validation_details"] = details
        return RetryTransition(
            kind="RETRY_REJECTED", tasks=payload.tasks, observations=observations
        )
    retried = _apply_retry_rewrite(
        payload.tasks,
        normalized,
        command=payload.command,
    )
    if retried == payload.tasks:
        observations["skip_reason"] = "retry_action_no_effect"
        return RetryTransition(
            kind="RETRY_SKIPPED", tasks=payload.tasks, observations=observations
        )
    round_index = budget.used + 1
    intent = RetryAttemptIntent(
        attempt_id=f"attempt:{payload.project_key}:{payload.prior_attempt_ref}:retry:{round_index}",
        round_index=round_index,
        prior_attempt_ref=payload.prior_attempt_ref,
        idempotency_key=_build_retry_idempotency_key(
            prior_attempt_ref=payload.prior_attempt_ref,
            round_index=round_index,
        ),
    )
    observations.update(
        {
            "scheduled": True,
            "used": budget.used + 1,
            "budget_remaining": budget.remaining - 1,
            "round": round_index,
            "reason": normalized.reason,
            "task_count": len(retried),
        }
    )
    return RetryTransition(
        kind="RETRY_SCHEDULED",
        tasks=retried,
        observations=observations,
        attempt_intent=intent,
    )


def _build_retry_idempotency_key(*, prior_attempt_ref: str, round_index: int) -> str:
    base = str(prior_attempt_ref or "").strip() or "attempt:initial"
    return f"{base}:retry:{round_index}"


@dataclass(frozen=True, slots=True)
class AgentBatchSubmissionItem:
    job_id: str
    channel: str
    query_terms: tuple[str, ...] = ()
    urls: tuple[str, ...] = ()
    max_items: int = 20
    provider: str = "auto"
    language: str = "zh"
    days_back: int | None = None
    item_key: str | None = None
    scope: str | None = None
    platforms: tuple[str, ...] = ()
    override_params: dict[str, Any] = field(default_factory=dict)
    lane: str = "main"
    workflow_run_id: str | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if not str(self.job_id or "").strip():
            raise ValueError("AgentBatchSubmissionItem.job_id is required")
        object.__setattr__(
            self, "query_terms", tuple(_normalize_terms(self.query_terms))
        )
        object.__setattr__(self, "urls", tuple(_normalize_string_list(self.urls)))
        object.__setattr__(
            self, "platforms", tuple(_normalize_string_list(self.platforms))
        )
        object.__setattr__(
            self,
            "max_items",
            _normalize_int(self.max_items, 20, min_value=1, max_value=100),
        )
        object.__setattr__(
            self, "provider", str(self.provider or "auto").strip() or "auto"
        )
        object.__setattr__(self, "language", str(self.language or "zh").strip() or "zh")
        object.__setattr__(self, "days_back", _normalize_days_back(self.days_back))
        object.__setattr__(self, "item_key", str(self.item_key or "").strip() or None)
        object.__setattr__(self, "scope", str(self.scope or "").strip() or None)
        object.__setattr__(
            self, "override_params", _normalize_override_params(self.override_params)
        )


@dataclass(frozen=True, slots=True)
class AgentBatchSubmission:
    """Project/capability-scoped durable submission contract (C4.3)."""

    schema_version: Literal["mrw.successor.agent-batch.c4-3.payload.v1"]
    operation_kind: Literal["agent_batch.submit.v1"]
    submission_id: str
    project_key: str
    resolved_schema: str
    registry_revision: int
    scope_incarnation: str
    scope_digest: str
    capability_id: str
    logical_request_id: str
    request_digest: str
    jobs: tuple[AgentBatchSubmissionItem, ...]
    authority_snapshot_ref: str
    resource_request_ref: str
    submission_digest: str = ""
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != "mrw.successor.agent-batch.c4-3.payload.v1":
            raise ValueError("unsupported submission schema")
        if self.operation_kind != SUBMISSION_KIND:
            raise ValueError("unsupported submission operation kind")
        if not self.submission_id or not self.project_key or not self.capability_id:
            raise ValueError("submission requires id/project/capability identity")
        if not self.logical_request_id:
            raise ValueError("logical_request_id is required")
        if not self.jobs:
            raise ValueError("submission requires at least one job")
        require_hex64(self.scope_digest, "AgentBatchSubmission.scope_digest")
        require_hex64(self.request_digest, "AgentBatchSubmission.request_digest")
        expected = content_digest(
            self, omit_fields=("submission_digest", "payload_digest")
        )
        if self.submission_digest == "":
            object.__setattr__(self, "submission_digest", expected)
        else:
            require_hex64(
                self.submission_digest, "AgentBatchSubmission.submission_digest"
            )
            if self.submission_digest != expected:
                raise ValueError("AgentBatchSubmission.submission_digest mismatch")
        payload_expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", payload_expected)
        else:
            require_hex64(self.payload_digest, "AgentBatchSubmission.payload_digest")
            if self.payload_digest != payload_expected:
                raise ValueError(
                    "AgentBatchSubmission.payload_digest does not match content"
                )


# Family-specific acceptance status lives in the typed submission receipt.
# The durable DB idempotency enum stays generic STARTED/TERMINAL (shared
# substrate); C4 never duplicates acceptance status into the DB enum.
C4AcceptanceState = Literal[
    "ACCEPTED",
    "PARTIALLY_ACCEPTED",
    "REJECTED",
    "CONFLICT",
]


@dataclass(frozen=True, slots=True)
class AgentBatchSubmissionReceipt:
    submission_id: str
    job_id: str
    accepted_items: tuple[str, ...]
    rejected_items: tuple[tuple[str, str], ...]
    run_ref: str
    state: C4AcceptanceState
    created_at: str
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        if not self.submission_id or not self.job_id:
            raise ValueError("receipt requires submission and job identity")
        if not self.run_ref:
            raise ValueError("receipt requires run_ref")
        if self.receipt_digest == "":
            object.__setattr__(
                self,
                "receipt_digest",
                content_digest(self, omit_fields=("receipt_digest",)),
            )
        else:
            require_hex64(
                self.receipt_digest, "AgentBatchSubmissionReceipt.receipt_digest"
            )


def build_agent_batch_submission_digest(submission: Any) -> str:
    """Canonical request digest over batch, rules and authority inputs."""

    plain = (
        dataclasses.asdict(submission)
        if dataclasses.is_dataclass(submission)
        else dict(submission)
    )
    plain.pop("submission_digest", None)
    return sha256_hex(canonical_json(plain).encode("utf-8"))


def _profile_ref(profile: Any) -> ContractProfileRef:
    return ContractProfileRef(
        profile.profile_id,
        profile.profile_version,
        profile.profile_digest,
    )


def _semantic_profile() -> SemanticProfile:
    values = {
        "semantic_profile_id": "agent_batch.c4.plan.semantic",
        "semantic_profile_version": "1.0.0",
        "reads": (
            "AgentBatchTask.v1",
            "ChannelCatalogSnapshot.v1",
            "SourceItemDefinition.v1",
            "RetryAction.v1",
            "AgentBatchSubmission.v1",
        ),
        "creates": (
            "BatchPlanResult.v1",
            "RetryTransition.v1",
            "AgentBatchSubmissionReceipt.v1",
        ),
        "creates_relations": (),
        "declared_loss": ("legacy_dict_shapes",),
        "observation_profile_ref": BATCH_PLAN_OBSERVATION_PROFILE,
    }
    return SemanticProfile(**values, profile_digest=content_digest(values))


def _effect_profile() -> EffectProfile:
    values = {
        "effect_profile_id": "agent_batch.c4.plan.effect",
        "effect_profile_version": "1.0.0",
        "execution_class": "PURE_TRANSFORM",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": (),
        "internal_export_only": False,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "mrw.successor.agent-batch.c4.idempotency.v1",
    }
    return EffectProfile(**values, profile_digest=content_digest(values))


def _resource_profile() -> ResourceProfile:
    values = {
        "resource_profile_id": "agent_batch.c4.plan.resource",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("CPU_LIGHT",),
        "concurrency_key": "agent_batch.c4.plan",
        "budget_units": "units",
        "default_soft_limit_seconds": 5,
        "default_hard_limit_seconds": 30,
        "node_profile_selector": "any",
        "budget_ref": "mrw.functorial-successor.budget.c4.v1",
        "deadline_policy_ref": "mrw.functorial-successor.deadline.c4.v1",
        "node_profile_requirements": ("any",),
        "units": 1,
    }
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile() -> FailureProfile:
    values = {
        "failure_profile_id": "agent_batch.c4.plan.failure",
        "failure_profile_version": "1.0.0",
        "typed_failures": (
            "INVALID_PLAN",
            "SOURCE_CANDIDATE_READ_FAILED",
            "SOURCE_MODE_WRITE_FORBIDDEN",
            "RETRY_ACTION_INVALID",
            "RETRY_BUDGET_EXHAUSTED",
            "IDEMPOTENCY_CONFLICT",
            "ASSIGNMENT_BINDING_MISMATCH",
        ),
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": False,
        "readback_or_compensation": "replay",
        "failure_union_ref": "mrw.functorial-successor.failures.c4.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": None,
        "compensation_profile_ref": None,
    }
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile() -> AuthorityProfile:
    values = {
        "authority_profile_id": "agent_batch.c4.plan.authority",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": AGENT_BATCH_C4_OWNER,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile() -> InterpreterProfile:
    values = {
        "interpreter_profile_id": "successor.agent_batch.c4.pure.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (
            BATCH_PLAN_KIND,
            RETRY_REDUCE_KIND,
        ),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "successor-native.agent_batch.c4",
                "version": "1.0.0",
                "boundary": "pure ordered plan/reducer; no legacy service import",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
        "resource_profile_ref": "agent_batch.c4.plan.resource@1.0.0",
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "step_boundary",
        "idempotency_profile_ref": "logical_request_id",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": BATCH_PLAN_OBSERVATION_PROFILE,
    }
    return InterpreterProfile(**values, profile_digest=content_digest(values))


def _observation_profile() -> ObservationProfile:
    values = {
        "observation_profile_id": BATCH_PLAN_OBSERVATION_PROFILE,
        "observation_profile_version": "1.0.0",
        "dimensions": (
            "ordered_tasks",
            "supplementation",
            "branching",
            "search_brief",
            "retry_transition",
            "attempt_intent",
            "submission_receipt",
            "source_mode_absent",
        ),
        "compatible_with_legacy": True,
        "observation_schema_ref": "mrw.successor.agent-batch.c4-1.observation.v1",
    }
    return ObservationProfile(**values, profile_digest=content_digest(values))


def _make_contract(
    *,
    kind: str,
    input_type: ObjectType,
    output_type: ObjectType,
    semantic: SemanticProfile,
    effect: EffectProfile,
    resource: ResourceProfile,
    failure: FailureProfile,
    authority: AuthorityProfile,
    interpreter: InterpreterProfile,
    observation: ObservationProfile,
    owner: str,
) -> Any:
    return make_operation_contract(
        kind=kind,
        contract_version="1.0.0",
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        semantic_profile_ref=_profile_ref(semantic).to_ref_string(),
        effect_profile_ref=_profile_ref(effect).to_ref_string(),
        resource_profile_ref=_profile_ref(resource).to_ref_string(),
        failure_profile_ref=_profile_ref(failure).to_ref_string(),
        authority_profile_ref=_profile_ref(authority).to_ref_string(),
        interpreter_compatibility_ref=_profile_ref(interpreter).to_ref_string(),
        observation_profile_ref=_profile_ref(observation).to_ref_string(),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=owner,
    )


@dataclass(frozen=True, slots=True)
class AgentBatchC4CapabilityBundle:
    bundle_id: str
    operations: tuple[Any, ...]
    codecs: tuple[PayloadCodec, ...]
    profiles: dict[str, object]

    def codec_by_kind(self, kind: str) -> PayloadCodec:
        for codec in self.codecs:
            if codec.contract_ref.kind == kind:
                return codec
        raise KeyError(f"no C4 payload codec for kind {kind}")


SUBMISSION_PAYLOAD_CODEC_ID = "mrw.successor.agent-batch.c4-3.payload.codec.v1"


def _decode_nested(
    dto_cls: type,
    value: dict[str, Any],
    *,
    _seen: set[type] | None = None,
) -> Any:
    """Decode a dataclass payload while restoring nested dataclass fields."""
    import typing

    seen = _seen if _seen is not None else set()
    restored: dict[str, Any] = {}
    hints = typing.get_type_hints(dto_cls)
    for field_def in dataclasses.fields(dto_cls):
        if field_def.name not in value:
            continue
        field_type = hints.get(field_def.name, field_def.type)
        origin = typing.get_origin(field_type)
        args = typing.get_args(field_type)
        raw = value[field_def.name]
        if origin in (tuple, list):
            item_cls = args[0] if args else None
            items = tuple(raw) if isinstance(raw, (list, tuple)) else raw
            restored[field_def.name] = (
                tuple(
                    _decode_nested(item_cls, dict(item), _seen=seen)
                    if dataclasses.is_dataclass(item_cls) and isinstance(item, dict)
                    else item
                    for item in items
                )
                if origin is tuple
                else [
                    _decode_nested(item_cls, dict(item), _seen=seen)
                    if dataclasses.is_dataclass(item_cls) and isinstance(item, dict)
                    else item
                    for item in items
                ]
            )
        elif isinstance(raw, dict) and dataclasses.is_dataclass(field_type):
            restored[field_def.name] = _decode_nested(field_type, raw, _seen=seen)
        else:
            restored[field_def.name] = raw
    return dto_cls(**restored)


def _payload_codec(contract_ref: Any, dto_cls: type) -> PayloadCodec:
    kind = contract_ref.kind
    if kind == BATCH_PLAN_KIND:
        codec_id = BATCH_PLAN_PAYLOAD_CODEC_ID
        payload_type = BATCH_PLAN_PAYLOAD_TYPE
    elif kind == RETRY_REDUCE_KIND:
        codec_id = RETRY_REDUCER_PAYLOAD_CODEC_ID
        payload_type = RETRY_REDUCER_PAYLOAD_TYPE
    elif kind == SUBMISSION_KIND:
        codec_id = SUBMISSION_PAYLOAD_CODEC_ID
        payload_type = SUBMISSION_TYPE
        from app.successor_runtime.capabilities.codecs import (
            PayloadCodec,
            codec_digest,
        )

        def encode(value: Any) -> dict[str, Any]:
            if not isinstance(value, dto_cls):
                raise TypeError("submission codec expected AgentBatchSubmission")
            return dataclasses.asdict(value)

        def decode(value: dict[str, Any]) -> Any:
            return _decode_nested(dto_cls, value)

        return PayloadCodec(
            codec_id=codec_id,
            codec_version="1",
            contract_ref=contract_ref,
            payload_type_id=payload_type.type_id,
            encode=encode,
            decode=decode,
            codec_digest=codec_digest(
                codec_id=codec_id,
                codec_version="1",
                contract_ref=contract_ref,
                payload_type_id=payload_type.type_id,
            ),
        )
    else:
        raise ValueError(f"no C4 payload codec for kind {kind}")
    return dataclass_codec(
        codec_id=codec_id,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=payload_type.type_id,
        dto_cls=dto_cls,
    )


def build_agent_batch_c4_bundle() -> AgentBatchC4CapabilityBundle:
    semantic = _semantic_profile()
    effect = _effect_profile()
    resource = _resource_profile()
    failure = _failure_profile()
    authority = _authority_profile()
    interpreter = _interpreter_profile()
    observation = _observation_profile()
    plan_contract = _make_contract(
        kind=BATCH_PLAN_KIND,
        input_type=BATCH_PLAN_PAYLOAD_TYPE,
        output_type=BATCH_PLAN_RESULT_TYPE,
        semantic=semantic,
        effect=effect,
        resource=resource,
        failure=failure,
        authority=authority,
        interpreter=interpreter,
        observation=observation,
        owner=AGENT_BATCH_C4_OWNER,
    )
    retry_contract = _make_contract(
        kind=RETRY_REDUCE_KIND,
        input_type=RETRY_REDUCER_PAYLOAD_TYPE,
        output_type=RETRY_TRANSITION_TYPE,
        semantic=semantic,
        effect=effect,
        resource=resource,
        failure=failure,
        authority=authority,
        interpreter=interpreter,
        observation=observation,
        owner=AGENT_BATCH_C4_OWNER,
    )
    submit_contract = _make_contract(
        kind=SUBMISSION_KIND,
        input_type=SUBMISSION_TYPE,
        output_type=SUBMISSION_RECEIPT_TYPE,
        semantic=semantic,
        effect=effect,
        resource=resource,
        failure=failure,
        authority=authority,
        interpreter=interpreter,
        observation=observation,
        owner=SUBMISSION_OWNER,
    )
    plan_codec = _payload_codec(plan_contract.ref, BatchPlanPayload)
    retry_codec = _payload_codec(retry_contract.ref, RetryReducerInput)
    submit_codec = _payload_codec(submit_contract.ref, AgentBatchSubmission)
    return AgentBatchC4CapabilityBundle(
        bundle_id="mrw.functorial-successor.agent-batch.c4",
        operations=(plan_contract, retry_contract, submit_contract),
        codecs=(plan_codec, retry_codec, submit_codec),
        profiles={
            "semantic": semantic,
            "effect": effect,
            "resource": resource,
            "failure": failure,
            "authority": authority,
            "interpreter": interpreter,
            "observation": observation,
        },
    )


def build_agent_batch_c4_catalog(
    bundle: AgentBatchC4CapabilityBundle,
) -> OperationContractCatalogSnapshot:
    return OperationContractCatalogSnapshot(
        catalog_id=BATCH_PLAN_CATALOG_ID,
        catalog_version=BATCH_PLAN_CATALOG_VERSION,
        entries=tuple(
            (
                operation.ref.kind,
                operation.ref.contract_version,
                operation.ref.contract_digest,
                operation.owner_capability_id,
            )
            for operation in bundle.operations
        ),
    )


def build_agent_batch_c4_registry(
    bundle: AgentBatchC4CapabilityBundle,
) -> OperationContractRegistry:
    return OperationContractRegistry(
        build_agent_batch_c4_catalog(bundle),
        bundle.operations,
    )
