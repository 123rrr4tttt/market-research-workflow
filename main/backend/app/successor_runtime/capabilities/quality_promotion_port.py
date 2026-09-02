"""Successor agent-batch quality-gate and promotion-readback port.

Movement binding: ALL-SM-013 (quality-promotion readback line) | successor
target port for the agent-batch C4 quality boundary.

This module is a self-contained, provider-independent successor port.  It
never imports legacy agent-batch services, broker workers, or runtime adapters,
and it never starts a live provider or writes a canonical record.  Promotion
is derived only from explicit typed readback evidence: fixture replay
readback, executor health readback, live provider replay rows, operator review
status and rollout policy.  Caller-supplied closure flags or promotion claims
never become promotion authority.

The gate is layered so that health, fixture quality and promotion remain
separate verdicts.  A missing or abnormal health readback fails the gate
closed even when fixture and live-provider evidence are present.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = [
    "QUALITY_PROMOTION_PORT_SCHEMA",
    "QUALITY_PROMOTION_PORT_SCOPE",
    "BoundedRetryReadback",
    "CriticScoreReadback",
    "EffectCounters",
    "ExecutorHealthEvidence",
    "FixtureQualityReadback",
    "HealthLayerVerdict",
    "InputPromotionClaim",
    "LiveProviderReplayReadback",
    "LiveProviderRowEvidence",
    "LiveQualityThresholds",
    "PromotionAuthorityState",
    "PromotionDecision",
    "PromotionDecisionReadback",
    "PromotionLayerVerdict",
    "ProviderRolloutPolicyEvidence",
    "QualityGateEvidence",
    "QualityGateFailure",
    "QualityGateResult",
    "QualityLayerVerdict",
    "RetryBoundaryObservation",
    "evaluate_quality_promotion_gate",
    "redact_broker_url",
]

QUALITY_PROMOTION_PORT_SCHEMA = "mrw.successor.agent-batch.quality-promotion-port.v1"
QUALITY_PROMOTION_PORT_SCOPE = (
    "successor.provider_independent_quality_gate_and_promotion_readback"
)

FIXTURE_QUALITY_REPLAY_TYPE = "deterministic_no_network_symbolic_search_quality_replay"
LIVE_PROVIDER_QUALITY_REPLAY_TYPE = "live_provider_quality_replay"
CRITIC_SCORE_SOURCE = "search_critic.score"

_SENSITIVE_QUERY_KEYS = frozenset(
    {"password", "pass", "pwd", "token", "secret", "access_token"}
)


def _as_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{name} must be bool")


def _as_text(value: Any, name: str) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _as_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _as_float(
    value: Any,
    name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return number


def _as_tuple(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be a sequence of strings")
    items = tuple(str(item).strip() for item in value)
    if any(not item for item in items):
        raise ValueError(f"{name} cannot contain blank items")
    return items


def _stable_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CriticScoreReadback:
    """Readback of one fixture critic score and its source binding."""

    case_id: str
    score: float
    score_threshold: float = 0.72
    next_action: str = "stop"
    reason_codes: tuple[str, ...] = ()
    diagnosis: str = ""
    retry_score_source: str = CRITIC_SCORE_SOURCE

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _as_text(self.case_id, "case_id"))
        if not self.case_id:
            raise ValueError("CriticScoreReadback.case_id is required")
        object.__setattr__(
            self,
            "score",
            _as_float(self.score, "score", minimum=0.0, maximum=1.0),
        )
        object.__setattr__(
            self,
            "score_threshold",
            _as_float(
                self.score_threshold,
                "score_threshold",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        object.__setattr__(
            self, "next_action", _as_text(self.next_action, "next_action") or "stop"
        )
        object.__setattr__(
            self, "reason_codes", _as_tuple(self.reason_codes, "reason_codes")
        )
        object.__setattr__(self, "diagnosis", _as_text(self.diagnosis, "diagnosis"))
        object.__setattr__(
            self,
            "retry_score_source",
            _as_text(self.retry_score_source, "retry_score_source")
            or CRITIC_SCORE_SOURCE,
        )


@dataclass(frozen=True, slots=True)
class RetryBoundaryObservation:
    """One typed bounded-retry boundary observation from a replay trace."""

    case_id: str
    expected_decision: str
    decision: str
    critic_score: float = 0.0
    replay_score_is_observational: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _as_text(self.case_id, "case_id"))
        if not self.case_id:
            raise ValueError("RetryBoundaryObservation.case_id is required")
        object.__setattr__(
            self,
            "expected_decision",
            _as_text(self.expected_decision, "expected_decision"),
        )
        object.__setattr__(self, "decision", _as_text(self.decision, "decision"))
        if not self.expected_decision or not self.decision:
            raise ValueError("retry boundary observation requires decisions")
        object.__setattr__(
            self,
            "critic_score",
            _as_float(self.critic_score, "critic_score", minimum=0.0, maximum=1.0),
        )
        object.__setattr__(
            self,
            "replay_score_is_observational",
            _as_bool(
                self.replay_score_is_observational,
                "replay_score_is_observational",
            ),
        )


@dataclass(frozen=True, slots=True)
class BoundedRetryReadback:
    """Explicit bounded-retry trace readback; score is observational only."""

    observations: tuple[RetryBoundaryObservation, ...] = ()
    enabled: bool = True
    retry_budget: int = 1
    max_retry_rounds: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observations",
            tuple(
                item
                if isinstance(item, RetryBoundaryObservation)
                else RetryBoundaryObservation(**item)
                for item in self.observations
            ),
        )
        object.__setattr__(self, "enabled", _as_bool(self.enabled, "enabled"))
        object.__setattr__(
            self,
            "retry_budget",
            _as_int(self.retry_budget, "retry_budget", minimum=0),
        )
        object.__setattr__(
            self,
            "max_retry_rounds",
            _as_int(self.max_retry_rounds, "max_retry_rounds", minimum=0),
        )

    @property
    def trace_count(self) -> int:
        return len(self.observations)

    @property
    def retry_allowed_count(self) -> int:
        return sum(1 for item in self.observations if item.decision == "retry_allowed")

    @property
    def retry_blocked_count(self) -> int:
        return sum(1 for item in self.observations if item.decision == "retry_blocked")

    @property
    def replay_score_is_observational(self) -> bool:
        return bool(self.observations) and all(
            item.replay_score_is_observational for item in self.observations
        )


@dataclass(frozen=True, slots=True)
class FixtureQualityReadback:
    """Readback evidence produced by a deterministic fixture replay."""

    case_count: int
    critic: CriticScoreReadback
    retry: BoundedRetryReadback
    fixture_threshold_status: str = "passed"
    replay_type: str = FIXTURE_QUALITY_REPLAY_TYPE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "case_count",
            _as_int(self.case_count, "case_count", minimum=0),
        )
        if not isinstance(self.critic, CriticScoreReadback):
            raise TypeError("FixtureQualityReadback.critic must be typed")
        if not isinstance(self.retry, BoundedRetryReadback):
            raise TypeError("FixtureQualityReadback.retry must be typed")
        object.__setattr__(
            self,
            "fixture_threshold_status",
            _as_text(
                self.fixture_threshold_status,
                "fixture_threshold_status",
            )
            or "passed",
        )
        object.__setattr__(
            self,
            "replay_type",
            _as_text(self.replay_type, "replay_type") or FIXTURE_QUALITY_REPLAY_TYPE,
        )


@dataclass(frozen=True, slots=True)
class ExecutorHealthEvidence:
    """Typed executor health readback; never obtained by this port itself."""

    worker_online: bool = False
    workers: tuple[str, ...] = ()
    inspect_performed: bool = True
    inspect_ok: bool = True
    broker_url_masked: str = ""
    observed_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "worker_online", _as_bool(self.worker_online, "worker_online")
        )
        object.__setattr__(self, "workers", _as_tuple(self.workers, "workers"))
        object.__setattr__(
            self,
            "inspect_performed",
            _as_bool(self.inspect_performed, "inspect_performed"),
        )
        object.__setattr__(self, "inspect_ok", _as_bool(self.inspect_ok, "inspect_ok"))
        object.__setattr__(
            self,
            "broker_url_masked",
            _as_text(self.broker_url_masked, "broker_url_masked"),
        )
        object.__setattr__(
            self, "observed_at", _as_text(self.observed_at, "observed_at")
        )
        if self.worker_online and not self.workers:
            raise ValueError("online executor health requires worker identities")
        if not self.worker_online and self.workers:
            raise ValueError("offline executor health cannot name workers")

    @property
    def worker_count(self) -> int:
        return len(self.workers)


@dataclass(frozen=True, slots=True)
class LiveProviderRowEvidence:
    """One provider replay row with measured quality, not an input claim."""

    provider: str
    replay_status: str
    result_count: int = 0
    source_domains: tuple[str, ...] = ()
    relevance_score: float = 0.0
    freshness_score: float = 0.0
    duplicate_rate: float = 0.0
    timeout_rate: float = 0.0
    p95_latency_ms: float = 0.0
    review_sample_count: int = 0
    review_visible_sample_count: int = 0
    trace_success: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _as_text(self.provider, "provider"))
        if not self.provider:
            raise ValueError("LiveProviderRowEvidence.provider is required")
        status = _as_text(self.replay_status, "replay_status")
        if status not in {"passed", "failed", "not_run"}:
            raise ValueError(f"unsupported replay_status {status!r}")
        object.__setattr__(self, "replay_status", status)
        object.__setattr__(
            self,
            "result_count",
            _as_int(self.result_count, "result_count", minimum=0),
        )
        object.__setattr__(
            self,
            "source_domains",
            _as_tuple(self.source_domains, "source_domains"),
        )
        object.__setattr__(
            self,
            "relevance_score",
            _as_float(
                self.relevance_score,
                "relevance_score",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        object.__setattr__(
            self,
            "freshness_score",
            _as_float(
                self.freshness_score,
                "freshness_score",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        object.__setattr__(
            self,
            "duplicate_rate",
            _as_float(
                self.duplicate_rate,
                "duplicate_rate",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        object.__setattr__(
            self,
            "timeout_rate",
            _as_float(
                self.timeout_rate,
                "timeout_rate",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        object.__setattr__(
            self,
            "p95_latency_ms",
            _as_float(
                self.p95_latency_ms,
                "p95_latency_ms",
                minimum=0.0,
            ),
        )
        object.__setattr__(
            self,
            "review_sample_count",
            _as_int(self.review_sample_count, "review_sample_count", minimum=0),
        )
        object.__setattr__(
            self,
            "review_visible_sample_count",
            _as_int(
                self.review_visible_sample_count,
                "review_visible_sample_count",
                minimum=0,
            ),
        )
        if self.review_visible_sample_count > self.review_sample_count:
            raise ValueError(
                "review_visible_sample_count cannot exceed review_sample_count"
            )
        object.__setattr__(
            self,
            "trace_success",
            _as_bool(self.trace_success, "trace_success"),
        )


@dataclass(frozen=True, slots=True)
class LiveProviderReplayReadback:
    """Explicit post-run live provider replay artifact and threshold rows."""

    readback_artifact_ref: str
    provider_rows: tuple[LiveProviderRowEvidence, ...] = ()
    operator_review_status: str = "not_run"
    replay_type: str = LIVE_PROVIDER_QUALITY_REPLAY_TYPE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "readback_artifact_ref",
            _as_text(self.readback_artifact_ref, "readback_artifact_ref"),
        )
        if not self.readback_artifact_ref:
            raise ValueError("live replay readback artifact ref is required")
        object.__setattr__(
            self,
            "provider_rows",
            tuple(
                item
                if isinstance(item, LiveProviderRowEvidence)
                else LiveProviderRowEvidence(**item)
                for item in self.provider_rows
            ),
        )
        object.__setattr__(
            self,
            "operator_review_status",
            _as_text(self.operator_review_status, "operator_review_status")
            or "not_run",
        )
        object.__setattr__(
            self,
            "replay_type",
            _as_text(self.replay_type, "replay_type")
            or LIVE_PROVIDER_QUALITY_REPLAY_TYPE,
        )


@dataclass(frozen=True, slots=True)
class LiveQualityThresholds:
    """Threshold contract used to evaluate explicit provider replay rows."""

    threshold_version: str = "successor.agent_batch.live_quality_thresholds.v1"
    required_providers: tuple[str, ...] = ("searxng", "yacy", "web")
    min_results_per_provider: int = 3
    min_source_domains: int = 2
    min_relevance_score: float = 0.72
    min_freshness_score: float = 0.65
    max_duplicate_rate: float = 0.25
    max_timeout_rate: float = 0.10
    max_p95_latency_ms: float = 4000.0
    min_review_sample_count: int = 3
    require_trace_success: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "threshold_version",
            _as_text(self.threshold_version, "threshold_version"),
        )
        if not self.threshold_version:
            raise ValueError("threshold_version is required")
        object.__setattr__(
            self,
            "required_providers",
            _as_tuple(self.required_providers, "required_providers"),
        )
        object.__setattr__(
            self,
            "min_results_per_provider",
            _as_int(
                self.min_results_per_provider,
                "min_results_per_provider",
                minimum=1,
            ),
        )
        object.__setattr__(
            self,
            "min_source_domains",
            _as_int(self.min_source_domains, "min_source_domains", minimum=1),
        )
        for name in ("min_relevance_score", "min_freshness_score"):
            object.__setattr__(
                self,
                name,
                _as_float(
                    getattr(self, name),
                    name,
                    minimum=0.0,
                    maximum=1.0,
                ),
            )
        for name in ("max_duplicate_rate", "max_timeout_rate"):
            object.__setattr__(
                self,
                name,
                _as_float(
                    getattr(self, name),
                    name,
                    minimum=0.0,
                    maximum=1.0,
                ),
            )
        object.__setattr__(
            self,
            "max_p95_latency_ms",
            _as_float(self.max_p95_latency_ms, "max_p95_latency_ms", minimum=1.0),
        )
        object.__setattr__(
            self,
            "min_review_sample_count",
            _as_int(
                self.min_review_sample_count,
                "min_review_sample_count",
                minimum=0,
            ),
        )
        object.__setattr__(
            self,
            "require_trace_success",
            _as_bool(self.require_trace_success, "require_trace_success"),
        )


@dataclass(frozen=True, slots=True)
class ProviderRolloutPolicyEvidence:
    """Operator-approved rollout policy readback; never amended here."""

    approval_status: str = "not_approved"
    approved_providers: tuple[str, ...] = ()
    rollback_criteria: tuple[str, ...] = ()
    monitoring_requirements: tuple[str, ...] = ()
    manual_review_artifact: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "approval_status",
            _as_text(self.approval_status, "approval_status") or "not_approved",
        )
        object.__setattr__(
            self,
            "approved_providers",
            _as_tuple(self.approved_providers, "approved_providers"),
        )
        object.__setattr__(
            self,
            "rollback_criteria",
            _as_tuple(self.rollback_criteria, "rollback_criteria"),
        )
        object.__setattr__(
            self,
            "monitoring_requirements",
            _as_tuple(self.monitoring_requirements, "monitoring_requirements"),
        )
        object.__setattr__(
            self,
            "manual_review_artifact",
            _as_text(self.manual_review_artifact, "manual_review_artifact") or None,
        )

    @property
    def approved(self) -> bool:
        return (
            self.approval_status == "approved"
            and bool(self.approved_providers)
            and bool(self.rollback_criteria)
            and bool(self.monitoring_requirements)
            and bool(self.manual_review_artifact)
        )


@dataclass(frozen=True, slots=True)
class InputPromotionClaim:
    """Caller-supplied claim; the gate recomputes and may reject it."""

    decision: str = ""
    promotion_allowed: bool = False
    provider_auto_promotion_allowed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", _as_text(self.decision, "decision"))
        object.__setattr__(
            self,
            "promotion_allowed",
            _as_bool(self.promotion_allowed, "promotion_allowed"),
        )
        object.__setattr__(
            self,
            "provider_auto_promotion_allowed",
            _as_bool(
                self.provider_auto_promotion_allowed,
                "provider_auto_promotion_allowed",
            ),
        )

    @property
    def claims_promotion(self) -> bool:
        return (
            self.promotion_allowed
            or self.provider_auto_promotion_allowed
            or self.decision.lower().startswith("promote")
        )


@dataclass(frozen=True, slots=True)
class QualityGateEvidence:
    """All explicit typed evidence consumed by the promotion gate."""

    fixture_replay: FixtureQualityReadback | None = None
    executor_health: ExecutorHealthEvidence | None = None
    live_replay: LiveProviderReplayReadback | None = None
    rollout_policy: ProviderRolloutPolicyEvidence | None = None
    input_promotion_claim: InputPromotionClaim | None = None
    thresholds: LiveQualityThresholds = field(default_factory=LiveQualityThresholds)

    def __post_init__(self) -> None:
        if self.fixture_replay is not None and not isinstance(
            self.fixture_replay, FixtureQualityReadback
        ):
            raise ValueError("fixture_replay must be typed or None")
        if self.executor_health is not None and not isinstance(
            self.executor_health, ExecutorHealthEvidence
        ):
            raise ValueError("executor_health must be typed or None")
        if self.live_replay is not None and not isinstance(
            self.live_replay, LiveProviderReplayReadback
        ):
            raise ValueError("live_replay must be typed or None")
        if self.rollout_policy is not None and not isinstance(
            self.rollout_policy, ProviderRolloutPolicyEvidence
        ):
            raise ValueError("rollout_policy must be typed or None")
        if self.input_promotion_claim is not None and not isinstance(
            self.input_promotion_claim, InputPromotionClaim
        ):
            raise ValueError("input_promotion_claim must be typed or None")
        if not isinstance(self.thresholds, LiveQualityThresholds):
            raise TypeError("thresholds must be typed")


@dataclass(frozen=True, slots=True)
class HealthLayerVerdict:
    passed: bool
    state: str
    failures: tuple[str, ...]
    worker_count: int = 0
    broker_url_masked: str = ""


@dataclass(frozen=True, slots=True)
class QualityLayerVerdict:
    passed: bool
    state: str
    failures: tuple[str, ...]
    fixture_case_count: int = 0
    critic_score_source: str = ""
    retry_allowed_count: int = 0
    retry_blocked_count: int = 0
    replay_score_is_observational: bool = False
    fixture_threshold_status: str = ""


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """Semantic promotion decision derived from evidence, not authority."""

    decision_id: str
    decision: Literal["promote_provider_auto", "hold_provider_auto_promotion"]
    promotion_allowed: bool
    provider_auto_promotion_allowed: bool
    quality_promotion_state: str
    reason_codes: tuple[str, ...]
    required_next_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PromotionDecisionReadback:
    readback_performed: Literal[True] = True
    decision_digest: str = ""
    readback_digest: str = ""
    readback_matches_decision: bool = False
    promotion_allowed: bool = False
    provider_auto_promotion_allowed: bool = False
    input_promotion_claim_rejected: bool = False
    input_decision: str | None = None


@dataclass(frozen=True, slots=True)
class PromotionLayerVerdict:
    passed: bool
    decision: PromotionDecision


@dataclass(frozen=True, slots=True)
class PromotionAuthorityState:
    """Authority remains false on this horizontal port by construction."""

    authority_granted: Literal[False] = False
    provider_auto_promotion_authorized: Literal[False] = False
    live_provider_call_authorized: Literal[False] = False
    rollout_change_authorized: Literal[False] = False
    canonical_write_authorized: Literal[False] = False
    credential_read_authorized: Literal[False] = False


@dataclass(frozen=True, slots=True)
class EffectCounters:
    provider_calls: int = 0
    store_writes: int = 0
    canonical_writes: int = 0
    export_calls: int = 0


@dataclass(frozen=True, slots=True)
class QualityGateFailure:
    code: str
    reason: str
    required_next_evidence: str = ""


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    schema_version: str
    scope: str
    status: Literal["passed", "failed"]
    gate_state: str
    health: HealthLayerVerdict
    quality: QualityLayerVerdict
    promotion: PromotionLayerVerdict
    readback: PromotionDecisionReadback
    authority: PromotionAuthorityState
    effect_counts: EffectCounters
    failures: tuple[str, ...]
    remaining_gaps: tuple[QualityGateFailure, ...]
    unsupported_claims: tuple[QualityGateFailure, ...]


def redact_broker_url(raw_url: Any) -> str:
    """Return a broker URL with userinfo and sensitive query values masked."""

    text = str(raw_url or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
        if not parsed.scheme or not parsed.netloc:
            return "***"
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port is not None else ""
        if parsed.username is not None or parsed.password is not None:
            username = parsed.username or "user"
            userinfo = f"{username}:***"
            netloc = f"{userinfo}@{host}{port}"
        else:
            netloc = f"{host}{port}"
        if parsed.query:
            pairs = parse_qsl(parsed.query, keep_blank_values=True)
            masked_query = urlencode(
                [
                    (
                        key,
                        "***"
                        if str(key or "").lower() in _SENSITIVE_QUERY_KEYS
                        else value,
                    )
                    for key, value in pairs
                ]
            )
        else:
            masked_query = ""
        return urlunsplit(
            (parsed.scheme, netloc, parsed.path, masked_query, parsed.fragment)
        )
    except Exception:  # noqa: BLE001 - redaction must never fail open
        return "***"


def _evaluate_health_layer(
    evidence: ExecutorHealthEvidence | None,
) -> HealthLayerVerdict:
    if evidence is None:
        return HealthLayerVerdict(
            passed=False,
            state="executor_health_not_observed",
            failures=("executor_health_evidence_missing",),
        )
    failures: list[str] = []
    if not evidence.inspect_performed:
        failures.append("executor_health_inspect_not_performed")
    elif not evidence.inspect_ok:
        failures.append("executor_health_inspect_failed")
    if not evidence.worker_online:
        failures.append("executor_health_no_online_worker")
    state = (
        "executor_health_observed_online" if not failures else "executor_health_failed"
    )
    return HealthLayerVerdict(
        passed=not failures,
        state=state,
        failures=tuple(failures),
        worker_count=evidence.worker_count,
        broker_url_masked=evidence.broker_url_masked,
    )


def _evaluate_quality_layer(
    readback: FixtureQualityReadback | None,
) -> QualityLayerVerdict:
    failures: list[str] = []
    if readback is None:
        return QualityLayerVerdict(
            passed=False,
            state="fixture_quality_readback_missing",
            failures=("fixture_quality_readback_missing",),
        )
    if readback.replay_type != FIXTURE_QUALITY_REPLAY_TYPE:
        failures.append("fixture_quality_replay_type_invalid")
    if readback.case_count < 1:
        failures.append("fixture_quality_case_count_zero")
    if readback.critic.retry_score_source != CRITIC_SCORE_SOURCE:
        failures.append("critic_score_source_drifted")
    if readback.fixture_threshold_status != "passed":
        failures.append("fixture_quality_threshold_not_passed")
    if not readback.retry.enabled:
        failures.append("bounded_retry_disabled")
    if readback.retry.retry_budget < 1 or readback.retry.max_retry_rounds < 1:
        failures.append("bounded_retry_budget_unavailable")
    if readback.retry.trace_count < 1:
        failures.append("bounded_retry_trace_missing")
    if not readback.retry.replay_score_is_observational:
        failures.append("bounded_retry_replay_score_not_observational")
    if readback.retry.retry_allowed_count < 1:
        failures.append("retry_allowed_trace_missing")
    if readback.retry.retry_blocked_count < 1:
        failures.append("retry_blocked_trace_missing")
    return QualityLayerVerdict(
        passed=not failures,
        state=(
            "fixture_quality_replay_passed"
            if not failures
            else "fixture_quality_replay_failed"
        ),
        failures=tuple(failures),
        fixture_case_count=readback.case_count,
        critic_score_source=readback.critic.retry_score_source,
        retry_allowed_count=readback.retry.retry_allowed_count,
        retry_blocked_count=readback.retry.retry_blocked_count,
        replay_score_is_observational=readback.retry.replay_score_is_observational,
        fixture_threshold_status=readback.fixture_threshold_status,
    )


def _row_failure_codes(
    row: LiveProviderRowEvidence,
    thresholds: LiveQualityThresholds,
) -> list[str]:
    codes: list[str] = []
    if row.replay_status != "passed":
        codes.append(f"{row.provider}_replay_not_passed")
    if row.result_count < thresholds.min_results_per_provider:
        codes.append(f"{row.provider}_result_count_below_minimum")
    if len(row.source_domains) < thresholds.min_source_domains:
        codes.append(f"{row.provider}_source_domains_below_minimum")
    if row.relevance_score < thresholds.min_relevance_score:
        codes.append(f"{row.provider}_relevance_below_minimum")
    if row.freshness_score < thresholds.min_freshness_score:
        codes.append(f"{row.provider}_freshness_below_minimum")
    if row.duplicate_rate > thresholds.max_duplicate_rate:
        codes.append(f"{row.provider}_duplicate_rate_above_maximum")
    if row.timeout_rate > thresholds.max_timeout_rate:
        codes.append(f"{row.provider}_timeout_rate_above_maximum")
    if row.p95_latency_ms > thresholds.max_p95_latency_ms:
        codes.append(f"{row.provider}_p95_latency_above_maximum")
    if row.review_sample_count < thresholds.min_review_sample_count:
        codes.append(f"{row.provider}_review_sample_count_below_minimum")
    if thresholds.require_trace_success and not row.trace_success:
        codes.append(f"{row.provider}_trace_not_successful")
    return codes


def _live_replay_gap_codes(
    live_replay: LiveProviderReplayReadback | None,
    thresholds: LiveQualityThresholds,
) -> tuple[list[str], bool]:
    """Return gap codes and whether explicit live readback closes quality."""

    gaps: list[str] = []
    if live_replay is None:
        return gaps, False
    if live_replay.replay_type != LIVE_PROVIDER_QUALITY_REPLAY_TYPE:
        gaps.append("live_provider_replay_type_invalid")
    rows_by_provider = {row.provider: row for row in live_replay.provider_rows}
    for provider in thresholds.required_providers:
        row = rows_by_provider.get(provider)
        if row is None:
            gaps.append(f"{provider}_readback_missing")
            continue
        gaps.extend(_row_failure_codes(row, thresholds))
    if live_replay.operator_review_status != "approved":
        gaps.append("operator_review_not_approved")
    return list(dict.fromkeys(gaps)), not gaps


def _promotion_decision(
    *,
    quality: QualityLayerVerdict,
    health: HealthLayerVerdict,
    live_gap_codes: tuple[str, ...],
    live_closed: bool,
    policy: ProviderRolloutPolicyEvidence | None,
) -> PromotionDecision:
    policy_approved = bool(policy) and policy.approved
    promotion_allowed = (
        quality.passed and health.passed and live_closed and policy_approved
    )
    if promotion_allowed:
        return PromotionDecision(
            decision_id="successor.agent-batch.quality-promotion:provider-auto:promote",
            decision="promote_provider_auto",
            promotion_allowed=True,
            provider_auto_promotion_allowed=True,
            quality_promotion_state="live_quality_readback_closed_policy_approved",
            reason_codes=(
                "fixture_quality_replay_passed",
                "executor_health_observed",
                "live_provider_replay_readback_closed",
                "operator_review_approved",
                "provider_auto_rollout_policy_approved",
            ),
            required_next_evidence=(),
        )

    reason_codes: list[str] = []
    if not quality.passed:
        reason_codes.append("fixture_quality_replay_gate_not_passed")
    if not health.passed:
        reason_codes.append("executor_health_gate_not_passed")
    if live_gap_codes:
        if "operator_review_not_approved" not in live_gap_codes:
            reason_codes.append("live_provider_replay_gaps_open")
        else:
            reason_codes.append("operator_review_not_approved")
    elif not live_closed:
        reason_codes.append("live_provider_replay_readback_missing")
    if not policy_approved:
        reason_codes.append("provider_auto_rollout_policy_not_approved")
    if not reason_codes:
        reason_codes.append("provider_independent_promotion_hold")
    return PromotionDecision(
        decision_id="successor.agent-batch.quality-promotion:provider-auto:hold",
        decision="hold_provider_auto_promotion",
        promotion_allowed=False,
        provider_auto_promotion_allowed=False,
        quality_promotion_state="provider_independent_quality_promotion_held",
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        required_next_evidence=(
            "executor_health_evidence",
            "fixture_quality_replay_readback",
            "live_provider_quality_replay_readback",
            "operator_review_approval",
            "provider_auto_rollout_policy",
        ),
    )


def _build_readback(
    decision: PromotionDecision,
    input_claim: InputPromotionClaim | None,
) -> PromotionDecisionReadback:
    decision_digest = _stable_digest(
        {
            "decision_id": decision.decision_id,
            "decision": decision.decision,
            "promotion_allowed": decision.promotion_allowed,
            "provider_auto_promotion_allowed": (
                decision.provider_auto_promotion_allowed
            ),
            "quality_promotion_state": decision.quality_promotion_state,
            "reason_codes": decision.reason_codes,
        }
    )
    return PromotionDecisionReadback(
        readback_performed=True,
        decision_digest=decision_digest,
        readback_digest=decision_digest,
        readback_matches_decision=True,
        promotion_allowed=decision.promotion_allowed,
        provider_auto_promotion_allowed=decision.provider_auto_promotion_allowed,
        input_promotion_claim_rejected=bool(input_claim)
        and input_claim.claims_promotion
        and not decision.promotion_allowed,
        input_decision=input_claim.decision if input_claim else None,
    )


def _gap_record(code: str, reason: str, required: str) -> QualityGateFailure:
    return QualityGateFailure(
        code=code,
        reason=reason,
        required_next_evidence=required,
    )


def evaluate_quality_promotion_gate(
    evidence: QualityGateEvidence | None = None,
) -> QualityGateResult:
    """Evaluate layered quality, health and promotion readback evidence."""

    gate_evidence = evidence if evidence is not None else QualityGateEvidence()
    health = _evaluate_health_layer(gate_evidence.executor_health)
    quality = _evaluate_quality_layer(gate_evidence.fixture_replay)
    live_gap_codes, live_closed = _live_replay_gap_codes(
        gate_evidence.live_replay,
        gate_evidence.thresholds,
    )
    decision = _promotion_decision(
        quality=quality,
        health=health,
        live_gap_codes=tuple(live_gap_codes),
        live_closed=live_closed,
        policy=gate_evidence.rollout_policy,
    )
    readback = _build_readback(decision, gate_evidence.input_promotion_claim)

    layer_failures: list[str] = []
    layer_failures.extend(health.failures)
    layer_failures.extend(quality.failures)
    if not readback.readback_matches_decision:
        layer_failures.append("promotion_decision_readback_mismatch")
    failures = tuple(dict.fromkeys(layer_failures))
    status = "passed" if not failures else "failed"
    if failures:
        gate_state = "quality_promotion_gate_failed"
    elif decision.promotion_allowed:
        gate_state = "promotion_decision_approved_readback_only"
    else:
        gate_state = "provider_independent_quality_promotion_held_live_gap_open"

    remaining_gaps: list[QualityGateFailure] = []
    if health.failures:
        remaining_gaps.append(
            _gap_record(
                "executor_health_blocked",
                "executor health readback is missing or abnormal",
                "fresh executor health readback with online worker",
            )
        )
    if quality.failures:
        remaining_gaps.append(
            _gap_record(
                "fixture_quality_gate_blocked",
                "deterministic fixture quality readback is incomplete",
                "valid critic/bounded-retry fixture replay readback",
            )
        )
    if gate_evidence.live_replay is None:
        remaining_gaps.append(
            _gap_record(
                "live_provider_replay_readback_missing",
                "no explicit live provider replay readback was attached",
                "live provider replay artifact with measured threshold rows",
            )
        )
    else:
        for code in live_gap_codes:
            remaining_gaps.append(
                _gap_record(
                    code,
                    "live provider replay readback did not close every threshold",
                    "provider row threshold pass plus operator approval",
                )
            )
    if not gate_evidence.rollout_policy or not gate_evidence.rollout_policy.approved:
        remaining_gaps.append(
            _gap_record(
                "provider_auto_rollout_policy_not_approved",
                "provider=auto rollout policy is not approved",
                "operator-approved rollout, rollback and monitoring policy",
            )
        )
    if (
        gate_evidence.live_replay is not None
        and gate_evidence.rollout_policy is not None
        and gate_evidence.rollout_policy.approved
        and not live_gap_codes
        and not decision.promotion_allowed
    ):
        remaining_gaps.append(
            _gap_record(
                "quality_gate_or_health_blocked",
                "quality or health layer blocked promotion",
                "passing fixture quality and executor health layers",
            )
        )

    unsupported_claims: list[QualityGateFailure] = []
    if (
        gate_evidence.input_promotion_claim is not None
        and gate_evidence.input_promotion_claim.claims_promotion
        and not decision.promotion_allowed
    ):
        unsupported_claims.append(
            _gap_record(
                "input_promotion_decision_claim_rejected",
                "caller-supplied promotion claim cannot authorize provider=auto",
                "gate-computed promotion from explicit readback evidence",
            )
        )
    if gate_evidence.fixture_replay is not None and not live_closed:
        unsupported_claims.append(
            _gap_record(
                "fixture_replay_provider_auto_promotion_not_supported",
                "fixture replay is not live provider quality evidence",
                "live provider replay readback and operator-approved policy",
            )
        )

    return QualityGateResult(
        schema_version=QUALITY_PROMOTION_PORT_SCHEMA,
        scope=QUALITY_PROMOTION_PORT_SCOPE,
        status=status,
        gate_state=gate_state,
        health=health,
        quality=quality,
        promotion=PromotionLayerVerdict(
            passed=decision.promotion_allowed, decision=decision
        ),
        readback=readback,
        authority=PromotionAuthorityState(),
        effect_counts=EffectCounters(),
        failures=failures,
        remaining_gaps=tuple(remaining_gaps),
        unsupported_claims=tuple(unsupported_claims),
    )
