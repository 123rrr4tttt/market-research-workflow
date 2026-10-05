from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Generic, TypeVar

from typing import Annotated, Any

from app.contracts.errors import ErrorCode, map_status_to_error_code
from functorial_kit import Failure
from .gate_reason_codes import normalize_reason_code

RETRY_CLASS_TRANSIENT = "transient"
RETRY_CLASS_PERMANENT = "permanent"

_REASON_CLASS_MAP: dict[str, str] = {
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


def classify_retry_reason(reason: Any) -> tuple[str, str]:
    normalized = normalize_reason_code(reason, default="unknown_retry_reason")
    mapped = _REASON_CLASS_MAP.get(normalized)
    if mapped:
        return normalized, mapped
    if any(marker in normalized for marker in _TRANSIENT_MARKERS):
        return normalized, RETRY_CLASS_TRANSIENT
    return normalized, RETRY_CLASS_PERMANENT


def build_retry_observability(payload: dict[str, Any] | None) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=retry_payload+retry_reason_contract witness=test:test_w03_ingest_ports_authority_metadata",
]:
    data = dict(payload or {})
    reason_counts: dict[str, int] = {}

    def _add(reason: Any, count: Any = 1) -> None:
        normalized, _ = classify_retry_reason(reason)
        if normalized in {"", "ok", "unknown_retry_reason"}:
            return
        try:
            parsed = int(count)
        except Exception:  # noqa: BLE001
            parsed = 0
        if parsed <= 0:
            return
        reason_counts[normalized] = int(reason_counts.get(normalized, 0)) + parsed

    existing_reason_counts = data.get("retry_count_by_reason")
    if isinstance(existing_reason_counts, dict) and existing_reason_counts:
        for reason, count in existing_reason_counts.items():
            _add(reason, count)
    else:
        retry_reasons = data.get("retry_reasons")
        if isinstance(retry_reasons, dict):
            for reason, count in retry_reasons.items():
                _add(reason, count)
        elif isinstance(retry_reasons, list):
            for reason in retry_reasons:
                _add(reason, 1)

        retry_events = data.get("retry_events")
        if isinstance(retry_events, list):
            for event in retry_events:
                if isinstance(event, dict):
                    _add(event.get("reason"), event.get("count", 1))

        rejection_breakdown = data.get("rejection_breakdown")
        if isinstance(rejection_breakdown, dict):
            for reason, count in rejection_breakdown.items():
                normalized, klass = classify_retry_reason(reason)
                if klass == RETRY_CLASS_TRANSIENT:
                    _add(normalized, count)

        crawler_dispatch = data.get("crawler_dispatch")
        if isinstance(crawler_dispatch, dict):
            attempts = int(crawler_dispatch.get("attempt_count") or 0)
            if attempts > 1:
                _add(crawler_dispatch.get("retry_reason") or "crawler_dispatch_retry", attempts - 1)

    class_counts = {
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


@dataclass(frozen=True, slots=True)
class RequestScope:
    """Identity used to attribute request policy; a gate is process-local only."""

    provider: str
    account: str | None = None
    worker: str | None = None

    def __post_init__(self) -> None:
        if not str(self.provider or "").strip():
            raise ValueError("provider is required")

    @property
    def key(self) -> tuple[str, str | None, str | None]:
        return str(self.provider), self.account, self.worker

    def context(self) -> dict[str, Any]:
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
    def status(self) -> str:
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
        raise ValueError("at least one value or failure is required")
    return result


def parse_retry_after_seconds(
    value: Any,
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
    return max(0.0, seconds)


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
    context: dict[str, Any] = {
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
    retry_class: str
    delay_seconds: float
    retry_after_seconds: float | None
    error_code: ErrorCode
    scope: RequestScope
    reason_code: str


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
    guarantee: str = "process"


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
        lock_factory: Callable[[], threading.Lock] = threading.Lock,
    ) -> None:
        if rate_limit_interval_seconds <= 0:
            raise ValueError("rate_limit_interval_seconds must be positive")
        if backoff_base_seconds <= 0:
            raise ValueError("backoff_base_seconds must be positive")
        if backoff_max_seconds < backoff_base_seconds:
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
    def guarantee(self) -> str:
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
