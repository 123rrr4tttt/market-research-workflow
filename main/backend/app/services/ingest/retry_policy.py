from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Annotated, Generic, Literal, TypeGuard, TypedDict, TypeVar

from app.contracts.errors import ErrorCode, map_status_to_error_code
from functorial_kit import Failure
from .gate_reason_codes import normalize_reason_code

RETRY_CLASS_TRANSIENT = "transient"
RETRY_CLASS_PERMANENT = "permanent"
RetryClass = Literal["transient", "permanent"]

_REASON_CLASS_MAP: dict[str, RetryClass] = {
    "ok": RETRY_CLASS_PERMANENT,
    "invalid_url": RETRY_CLASS_PERMANENT,
    "domain_blocked": RETRY_CLASS_PERMANENT,
    "robots_disallow": RETRY_CLASS_PERMANENT,
    "url_policy_blocked": RETRY_CLASS_PERMANENT,
    "url_policy_low_value_domain": RETRY_CLASS_PERMANENT,
    "url_policy_low_value_endpoint": RETRY_CLASS_PERMANENT,
    "content_empty": RETRY_CLASS_PERMANENT,
    "content_semantic_too_short": RETRY_CLASS_PERMANENT,
    "content_shell_signature": RETRY_CLASS_PERMANENT,
    "content_js_template_shell": RETRY_CLASS_PERMANENT,
    "content_navigation_shell": RETRY_CLASS_PERMANENT,
    "strict_mode_quality_gate": RETRY_CLASS_PERMANENT,
    "search_template_results_insufficient": RETRY_CLASS_PERMANENT,
    "provenance_untrusted_domain": RETRY_CLASS_PERMANENT,
    "provenance_missing_citation": RETRY_CLASS_PERMANENT,
    "provenance_gate_rejected": RETRY_CLASS_PERMANENT,
    "light_filter_rejected": RETRY_CLASS_PERMANENT,
    "rate_limited": RETRY_CLASS_TRANSIENT,
    "http_429": RETRY_CLASS_TRANSIENT,
    "fetch_failed": RETRY_CLASS_TRANSIENT,
    "unexpected_exception": RETRY_CLASS_TRANSIENT,
    "crawler_pool_dispatch_failed": RETRY_CLASS_TRANSIENT,
    "search_provider_fetch_failed": RETRY_CLASS_TRANSIENT,
    "search_fallback_fetch_failed": RETRY_CLASS_TRANSIENT,
    "crawler_dispatch_retry": RETRY_CLASS_TRANSIENT,
}

_TRANSIENT_MARKERS = (
    "timeout",
    "tempor",
    "transient",
    "connection",
    "network",
    "server_error",
    "http_5",
    "rate_limit",
)


def classify_retry_reason(reason: object) -> tuple[str, RetryClass]:
    normalized = normalize_reason_code(reason, default="unknown_retry_reason")
    mapped = _REASON_CLASS_MAP.get(normalized)
    if mapped:
        return normalized, mapped
    if any(marker in normalized for marker in _TRANSIENT_MARKERS):
        return normalized, RETRY_CLASS_TRANSIENT
    return normalized, RETRY_CLASS_PERMANENT


class RetryObservability(TypedDict):
    retry_count_by_reason: dict[str, int]
    retry_count_by_class: dict[RetryClass, int]
    retryable: bool
    reason_code_class: RetryClass


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _retry_count(value: object) -> int:
    if not isinstance(value, (str, int, float)):
        return 0
    try:
        return int(value)
    except (ValueError, OverflowError):
        return 0


def build_retry_observability(payload: Mapping[str, object] | None) -> Annotated[
    RetryObservability,
    "kit:non-authoritative derived_as=view fact_source=retry_payload+retry_reason_contract witness=test:test_ingest_ports_declare_sources_and_effect_authority",
]:
    data = dict(payload or {})
    reason_counts: dict[str, int] = {}

    def _add(reason: object, count: object = 1) -> None:
        normalized, _ = classify_retry_reason(reason)
        if normalized in {"", "ok", "unknown_retry_reason"}:
            return
        parsed = _retry_count(count)
        if parsed <= 0:
            return
        reason_counts[normalized] = int(reason_counts.get(normalized, 0)) + parsed

    existing_reason_counts = data.get("retry_count_by_reason")
    if _is_object_mapping(existing_reason_counts) and existing_reason_counts:
        for reason, count in existing_reason_counts.items():
            _add(reason, count)
    else:
        retry_reasons = data.get("retry_reasons")
        if _is_object_mapping(retry_reasons):
            for reason, count in retry_reasons.items():
                _add(reason, count)
        elif _is_object_list(retry_reasons):
            for reason in retry_reasons:
                _add(reason, 1)

        retry_events = data.get("retry_events")
        if _is_object_list(retry_events):
            for event in retry_events:
                if _is_object_mapping(event):
                    _add(event.get("reason"), event.get("count", 1))

        rejection_breakdown = data.get("rejection_breakdown")
        if _is_object_mapping(rejection_breakdown):
            for reason, count in rejection_breakdown.items():
                normalized, klass = classify_retry_reason(reason)
                if klass == RETRY_CLASS_TRANSIENT:
                    _add(normalized, count)

        crawler_dispatch = data.get("crawler_dispatch")
        if _is_object_mapping(crawler_dispatch):
            attempts = _retry_count(crawler_dispatch.get("attempt_count"))
            if attempts > 1:
                _add(crawler_dispatch.get("retry_reason") or "crawler_dispatch_retry", attempts - 1)

    class_counts: dict[RetryClass, int] = {
        RETRY_CLASS_TRANSIENT: 0,
        RETRY_CLASS_PERMANENT: 0,
    }
    for reason, count in reason_counts.items():
        _, klass = classify_retry_reason(reason)
        class_counts[klass] += int(count)

    reason_code = data.get("reason_code")
    _, reason_code_class = classify_retry_reason(reason_code)
    retryable = bool(reason_code_class == RETRY_CLASS_TRANSIENT or class_counts[RETRY_CLASS_TRANSIENT] > 0)

    return {
        "retry_count_by_reason": reason_counts,
        "retry_count_by_class": class_counts,
        "retryable": retryable,
        "reason_code_class": reason_code_class,
    }


__all__ = [
    "RETRY_CLASS_PERMANENT",
    "RETRY_CLASS_TRANSIENT",
    "build_retry_observability",
    "classify_retry_reason",
]


REQUEST_FAILURE_FAMILY = "public_request"
_MAX_RETRY_BACKOFF_SECONDS = 60.0

_T = TypeVar("_T")


def _validate_scope_field(name: str, value: object, *, required: bool = False) -> None:
    if required and (not isinstance(value, str) or not value.strip()):
        # kit:boundary owner=ingest.retry_policy.request_scope class=PROGRAMMER_DEFECT failure_family=none witness=test:test_request_scope_rejects_blank_provider
        raise ValueError(f"{name} is required")
    if value is not None and not isinstance(value, str):
        # kit:boundary owner=ingest.retry_policy.request_scope class=PROGRAMMER_DEFECT failure_family=none witness=test:test_request_scope_rejects_non_string_identity_fields
        raise ValueError(f"{name} must be a string")


def _validate_delay(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        # kit:boundary owner=ingest.retry_policy.request_decision class=PROGRAMMER_DEFECT failure_family=none witness=test:test_request_retry_decision_rejects_unassociated_values
        raise ValueError(f"{name} must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class RequestScope:
    """Identity used to attribute request policy; a gate is process-local only."""

    provider: str
    account: str | None = None
    worker: str | None = None

    def __post_init__(self) -> None:
        _validate_scope_field("provider", self.provider, required=True)
        _validate_scope_field("account", self.account)
        _validate_scope_field("worker", self.worker)

    @property
    def key(self) -> tuple[str, str | None, str | None]:
        return self.provider, self.account, self.worker

    def context(self) -> dict[str, str | None]:
        return {
            "provider": self.provider,
            "account": self.account,
            "worker": self.worker,
        }


@dataclass(frozen=True, slots=True)
class RequestBatchResult(Generic[_T]):
    values: tuple[_T, ...]
    failures: tuple[Failure, ...]

    @property
    def status(self) -> Literal["partial", "failed", "ok"]:
        if self.failures and self.values:
            return "partial"
        if self.failures:
            return "failed"
        return "ok"


def combine_request_outcomes(
    values: Sequence[_T],
    failures: Sequence[Failure],
) -> RequestBatchResult[_T]:
    result = RequestBatchResult(tuple(values), tuple(failures))
    if not result.values and not result.failures:
        # kit:boundary owner=ingest.retry_policy.request_batch class=PROGRAMMER_DEFECT failure_family=none witness=test:test_combine_request_outcomes_rejects_empty_outcome
        raise ValueError("at least one value or failure is required")
    return result


def parse_retry_after_seconds(
    value: object,
    *,
    now: Callable[[], datetime] | None = None,
) -> float | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        seconds = float(raw)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        current = (now or _utcnow)()
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - current).total_seconds())
    return max(0.0, seconds) if math.isfinite(seconds) else None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _error_code_for_request(
    *,
    reason_code: str,
    status_code: int | None,
    transport_error: bool,
    retryable: bool,
) -> ErrorCode:
    if status_code == 429:
        return ErrorCode.RATE_LIMITED
    if status_code is not None:
        return map_status_to_error_code(status_code)
    if reason_code == "invalid_url":
        return ErrorCode.INVALID_INPUT
    if reason_code == "rate_limited":
        return ErrorCode.RATE_LIMITED
    if transport_error or reason_code in {
        "fetch_failed",
        "search_provider_fetch_failed",
        "search_fallback_fetch_failed",
        "crawler_pool_dispatch_failed",
    }:
        return ErrorCode.UPSTREAM_ERROR
    if retryable:
        return ErrorCode.UPSTREAM_ERROR
    return ErrorCode.INTERNAL_ERROR


def make_request_failure(
    *,
    reason_code: str,
    status_code: int | None = None,
    scope: RequestScope | None = None,
    retryable: bool | None = None,
    retry_after_seconds: float | None = None,
    transport_error: bool = False,
    attempt: int | None = None,
    message: str | None = None,
) -> Failure:
    normalized = normalize_reason_code(reason_code, default="fetch_failed")
    if retryable is None:
        _, retry_class = classify_retry_reason(normalized)
        retryable_value = retry_class == RETRY_CLASS_TRANSIENT
    else:
        retryable_value = bool(retryable)
    error_code = _error_code_for_request(
        reason_code=normalized,
        status_code=status_code,
        transport_error=transport_error,
        retryable=retryable_value,
    )
    context: dict[str, str | bool | int | float | None] = {
        "reason_code": normalized,
        "error_code": error_code.value,
        "retryable": retryable_value,
        "transport_error": bool(transport_error),
    }
    if status_code is not None:
        context["status_code"] = int(status_code)
    if retry_after_seconds is not None:
        context["retry_after_seconds"] = float(retry_after_seconds)
    if attempt is not None:
        context["attempt"] = int(attempt)
    if scope is not None:
        context.update(scope.context())
    return Failure(
        family=REQUEST_FAILURE_FAMILY,
        code=error_code.value,
        message=message or f"public request failed: {normalized}",
        context=context,
    )


@dataclass(frozen=True, slots=True)
class RequestRetryDecision:
    failure: Failure
    retryable: bool
    retry_class: RetryClass
    delay_seconds: float
    retry_after_seconds: float | None
    error_code: ErrorCode
    scope: RequestScope
    reason_code: str

    def __post_init__(self) -> None:
        _validate_delay("delay_seconds", self.delay_seconds)
        if self.retry_after_seconds is not None:
            _validate_delay("retry_after_seconds", self.retry_after_seconds)
        expected_class = RETRY_CLASS_TRANSIENT if self.retryable else RETRY_CLASS_PERMANENT
        if self.retry_class != expected_class or (not self.retryable and self.delay_seconds != 0):
            # kit:boundary owner=ingest.retry_policy.request_decision class=PROGRAMMER_DEFECT failure_family=none witness=test:test_request_retry_decision_rejects_unassociated_values
            raise ValueError("retry class and delay must match retryable")
        context: Mapping[str, object] = self.failure.context or {}
        if (
            self.failure.family != REQUEST_FAILURE_FAMILY
            or context.get("reason_code") != self.reason_code
            or context.get("retryable") != self.retryable
            or context.get("retry_after_seconds") != self.retry_after_seconds
            or any(context.get(key) != value for key, value in self.scope.context().items())
        ):
            # kit:boundary owner=ingest.retry_policy.request_decision class=PROGRAMMER_DEFECT failure_family=none witness=test:test_request_retry_decision_rejects_unassociated_values
            raise ValueError("failure context must match retry decision and scope")


def decide_request_retry(
    *,
    reason_code: str,
    status_code: int | None = None,
    headers: Mapping[str, str] | None = None,
    scope: RequestScope,
    transport_error: bool = False,
    attempt: int = 0,
    backoff_seconds: float = 1.5,
) -> RequestRetryDecision:
    normalized = normalize_reason_code(reason_code, default="fetch_failed")
    if status_code == 429:
        normalized = "rate_limited"
    lower_headers = {str(key).lower(): str(value) for key, value in (headers or {}).items()}
    retry_after = parse_retry_after_seconds(lower_headers.get("retry-after"))
    is_rate_limited = normalized == "rate_limited" or status_code == 429

    if is_rate_limited:
        retryable = True
        retry_class = RETRY_CLASS_TRANSIENT
        error_code = ErrorCode.RATE_LIMITED
    elif transport_error or (status_code is not None and status_code >= 500):
        retryable = True
        retry_class = RETRY_CLASS_TRANSIENT
        error_code = ErrorCode.UPSTREAM_ERROR
    elif status_code is not None:
        retryable = False
        retry_class = RETRY_CLASS_PERMANENT
        error_code = map_status_to_error_code(status_code)
    else:
        _, retry_class = classify_retry_reason(normalized)
        retryable = retry_class == RETRY_CLASS_TRANSIENT
        error_code = _error_code_for_request(
            reason_code=normalized,
            status_code=None,
            transport_error=transport_error,
            retryable=retryable,
        )

    if not retryable:
        delay = 0.0
    elif is_rate_limited and retry_after is not None:
        delay = retry_after
    else:
        delay = min(_MAX_RETRY_BACKOFF_SECONDS, max(0.0, float(backoff_seconds)) ** max(0, int(attempt)))

    failure = make_request_failure(
        reason_code=normalized,
        status_code=status_code,
        scope=scope,
        retryable=retryable,
        retry_after_seconds=retry_after,
        transport_error=transport_error,
        attempt=attempt,
        message=f"public request failed: {normalized}",
    )
    return RequestRetryDecision(
        failure=failure,
        retryable=retryable,
        retry_class=retry_class,
        delay_seconds=float(delay),
        retry_after_seconds=retry_after,
        error_code=error_code,
        scope=scope,
        reason_code=normalized,
    )


@dataclass(slots=True)
class _RateGateState:
    next_at: float = 0.0
    circuit_open_until: float = 0.0
    failures: int = 0


@dataclass(frozen=True, slots=True)
class RateGateDecision:
    acquired: bool
    scope: RequestScope
    waited_seconds: float
    retry_after_seconds: float | None
    guarantee: Literal["process"] = "process"

    def __post_init__(self) -> None:
        _validate_delay("waited_seconds", self.waited_seconds)
        if self.retry_after_seconds is not None:
            _validate_delay("retry_after_seconds", self.retry_after_seconds)
        if self.acquired == (self.retry_after_seconds is not None):
            # kit:boundary owner=ingest.retry_policy.rate_gate class=PROGRAMMER_DEFECT failure_family=none witness=test:test_rate_gate_decision_rejects_inconsistent_acquisition
            raise ValueError("retry_after_seconds must describe a denied acquisition")
        if not self.acquired and self.waited_seconds != 0:
            # kit:boundary owner=ingest.retry_policy.rate_gate class=PROGRAMMER_DEFECT failure_family=none witness=test:test_rate_gate_decision_rejects_inconsistent_acquisition
            raise ValueError("denied acquisition cannot have waited_seconds")


class RateGate:
    """A deterministic request spacing gate scoped inside one process."""

    def __init__(
        self,
        *,
        rate_limit_interval_seconds: float,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        lock_factory: Callable[[], AbstractContextManager[object]] = threading.Lock,
    ) -> None:
        if not math.isfinite(rate_limit_interval_seconds) or rate_limit_interval_seconds <= 0:
            # kit:boundary owner=ingest.retry_policy.rate_gate class=PROGRAMMER_DEFECT failure_family=none witness=test:test_rate_gate_rejects_invalid_numeric_intervals
            raise ValueError("rate_limit_interval_seconds must be positive")
        if not math.isfinite(backoff_base_seconds) or backoff_base_seconds <= 0:
            # kit:boundary owner=ingest.retry_policy.rate_gate class=PROGRAMMER_DEFECT failure_family=none witness=test:test_rate_gate_rejects_invalid_numeric_intervals
            raise ValueError("backoff_base_seconds must be positive")
        if not math.isfinite(backoff_max_seconds) or backoff_max_seconds < backoff_base_seconds:
            # kit:boundary owner=ingest.retry_policy.rate_gate class=PROGRAMMER_DEFECT failure_family=none witness=test:test_rate_gate_rejects_invalid_numeric_intervals
            raise ValueError("backoff_max_seconds must be at least backoff_base_seconds")
        self._interval = float(rate_limit_interval_seconds)
        self._backoff_base = float(backoff_base_seconds)
        self._backoff_max = float(backoff_max_seconds)
        self._clock = clock
        self._sleeper = sleeper
        self._lock = lock_factory()
        self._states: dict[tuple[str, str | None, str | None], _RateGateState] = {}

    def acquire(self, scope: RequestScope) -> RateGateDecision:
        now = self._clock()
        with self._lock:
            state = self._states.setdefault(scope.key, _RateGateState())
            if now < state.circuit_open_until:
                return RateGateDecision(
                    acquired=False,
                    scope=scope,
                    waited_seconds=0.0,
                    retry_after_seconds=state.circuit_open_until - now,
                )
            scheduled = max(float(now), state.next_at)
            state.next_at = scheduled + self._interval
        wait_seconds = max(0.0, scheduled - now)
        if wait_seconds > 0:
            self._sleeper(wait_seconds)
        return RateGateDecision(
            acquired=True,
            scope=scope,
            waited_seconds=wait_seconds,
            retry_after_seconds=None,
        )

    def record_throttle(
        self,
        scope: RequestScope,
        *,
        retry_after_seconds: float | None = None,
    ) -> float:
        now = self._clock()
        with self._lock:
            state = self._states.setdefault(scope.key, _RateGateState())
            state.failures += 1
            backoff = min(
                self._backoff_max,
                self._backoff_base * (2 ** (state.failures - 1)),
            )
            provider_delay = max(0.0, float(retry_after_seconds or 0.0))
            delay = max(backoff, provider_delay)
            state.circuit_open_until = max(state.circuit_open_until, now + delay)
            return delay

    def record_success(self, scope: RequestScope) -> None:
        with self._lock:
            self._states.setdefault(scope.key, _RateGateState()).failures = 0

    @property
    def guarantee(self) -> Literal["process"]:
        return "process"


__all__.extend(
    [
        "REQUEST_FAILURE_FAMILY",
        "RateGate",
        "RateGateDecision",
        "RequestBatchResult",
        "RequestRetryDecision",
        "RequestScope",
        "combine_request_outcomes",
        "decide_request_retry",
        "make_request_failure",
        "parse_retry_after_seconds",
    ]
)
