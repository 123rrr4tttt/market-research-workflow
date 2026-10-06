from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

import requests
from app.services.ingest.retry_policy import (
    RateGate,
    RateGateDecision,
    RequestRetryDecision,
    RequestScope,
    decide_request_retry,
    make_request_failure,
)
from app.services.resource_pool.http_port import (
    HttpFetchError,
    HttpFetchFailureReason,
    make_html_parser,
)
from functorial_kit import Failure
from requests import Response


DEFAULT_HEADERS: Mapping[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}
DEFAULT_TIMEOUT = 30.0
LEGACY_FETCH_SCOPE = RequestScope(provider="legacy_http_fetch")


@dataclass(frozen=True, slots=True)
class RequestOutcome:
    text: str = ""
    response: Response | None = None
    failures: tuple[Failure, ...] = ()
    decisions: tuple[RequestRetryDecision, ...] = ()
    attempts: int = 0
    last_exception: Exception | None = None

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def status(self) -> Literal["ok", "failed"]:
        return "failed" if self.failures else "ok"


def _default_client_factory() -> requests.Session:
    return requests.Session()


def _default_sleep(seconds: float) -> None:
    time.sleep(seconds)


def _gate_denial_decision(
    gate_decision: RateGateDecision,
    *,
    attempt: int,
) -> RequestRetryDecision:
    retry_after = gate_decision.retry_after_seconds
    base = decide_request_retry(
        reason_code="rate_limited",
        scope=gate_decision.scope,
        attempt=attempt,
    )
    failure = make_request_failure(
        reason_code="rate_limited",
        scope=gate_decision.scope,
        retryable=True,
        retry_after_seconds=retry_after,
        attempt=attempt,
    )
    return RequestRetryDecision(
        failure=failure,
        retryable=True,
        retry_class=base.retry_class,
        delay_seconds=float(retry_after or 0.0),
        retry_after_seconds=retry_after,
        error_code=base.error_code,
        scope=gate_decision.scope,
        reason_code="rate_limited",
    )


def _lower_headers(response: Response) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in response.headers.items()}


def request_html(
    url: str,
    *,
    scope: RequestScope,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    cookies: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 3,
    backoff_seconds: float = 1.5,
    jitter_seconds: float = 0.0,
    retry_gate: RateGate | None = None,
    sleeper: Callable[[float], None] = _default_sleep,
    client_factory: Callable[[], requests.Session] | None = None,
) -> RequestOutcome:
    """Fetch one public HTTP resource with explicit request policy."""

    request_headers = dict(DEFAULT_HEADERS)
    if headers:
        request_headers.update(headers)

    session = (client_factory or _default_client_factory)()
    session_headers = getattr(session, "headers", None)
    if session_headers is not None:
        session_headers.update(request_headers)
    if cookies:
        session_cookies = getattr(session, "cookies", None)
        if session_cookies is not None:
            session_cookies.update(cookies)
    failures: list[Failure] = []
    decisions: list[RequestRetryDecision] = []
    last_exc: Exception | None = None
    attempt_count = max(int(retries), 1)

    try:
        for attempt in range(attempt_count):
            gate_decision = (
                retry_gate.acquire(scope)
                if retry_gate is not None
                else RateGateDecision(True, scope, 0.0, None)
            )
            if not gate_decision.acquired:
                decision = _gate_denial_decision(gate_decision, attempt=attempt)
                failures.append(decision.failure)
                decisions.append(decision)
                return RequestOutcome(
                    failures=tuple(failures),
                    decisions=tuple(decisions),
                    attempts=attempt + 1,
                    last_exception=last_exc,
                )

            try:
                response = session.get(
                    url,
                    params=params,
                    timeout=timeout,
                    allow_redirects=True,
                )
            except requests.RequestException as exc:
                last_exc = exc
                decision = decide_request_retry(
                    reason_code="fetch_failed",
                    scope=scope,
                    transport_error=True,
                    attempt=attempt,
                    backoff_seconds=backoff_seconds,
                )
                failures.append(decision.failure)
                decisions.append(decision)
                if not decision.retryable or attempt == attempt_count - 1:
                    return RequestOutcome(
                        failures=tuple(failures),
                        decisions=tuple(decisions),
                        attempts=attempt + 1,
                        last_exception=last_exc,
                    )
            else:
                status_code = int(response.status_code)
                if status_code == 429:
                    decision = decide_request_retry(
                        reason_code="rate_limited",
                        status_code=status_code,
                        headers=_lower_headers(response),
                        scope=scope,
                        attempt=attempt,
                        backoff_seconds=backoff_seconds,
                    )
                    if retry_gate is not None:
                        retry_gate.record_throttle(
                            scope,
                            retry_after_seconds=decision.retry_after_seconds,
                        )
                    failures.append(decision.failure)
                    decisions.append(decision)
                elif status_code >= 500:
                    decision = decide_request_retry(
                        reason_code="fetch_failed",
                        status_code=status_code,
                        scope=scope,
                        attempt=attempt,
                        backoff_seconds=backoff_seconds,
                    )
                    failures.append(decision.failure)
                    decisions.append(decision)
                elif status_code >= 400:
                    try:
                        response.raise_for_status()
                    except requests.HTTPError as exc:
                        last_exc = exc

                    decision = decide_request_retry(
                        reason_code="fetch_failed",
                        status_code=status_code,
                        scope=scope,
                        attempt=attempt,
                        backoff_seconds=backoff_seconds,
                    )
                    failures.append(decision.failure)
                    decisions.append(decision)
                else:
                    if retry_gate is not None:
                        retry_gate.record_success(scope)
                    return RequestOutcome(
                        text=response.text,
                        response=response,
                        attempts=attempt + 1,
                    )

                if not decision.retryable or attempt == attempt_count - 1:
                    return RequestOutcome(
                        response=response,
                        failures=tuple(failures),
                        decisions=tuple(decisions),
                        attempts=attempt + 1,
                        last_exception=last_exc,
                    )

            if decisions and decisions[-1].retryable:
                jitter = random.uniform(0, max(0.0, float(jitter_seconds)))
                sleeper(max(0.0, decisions[-1].delay_seconds + jitter))

        raise AssertionError
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()


def fetch_html(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, Any] | None = None,
    cookies: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 3,
    backoff: float = 1.5,
) -> tuple[str, Response]:
    """Backward-compatible projection from the explicit request entry."""

    outcome = request_html(
        url,
        scope=LEGACY_FETCH_SCOPE,
        headers=headers,
        params=params,
        cookies=cookies,
        timeout=timeout,
        retries=retries,
        backoff_seconds=backoff,
        jitter_seconds=0.3,
    )
    if outcome.ok and outcome.response is not None:
        return outcome.text, outcome.response

    decision = outcome.decisions[-1]
    failure_context = decision.failure.context or {}
    raw_status = failure_context.get("status_code")
    status_code = (
        raw_status
        if isinstance(raw_status, int) and not isinstance(raw_status, bool)
        else None
    )
    reason = (
        HttpFetchFailureReason.HTTP_STATUS
        if status_code is not None
        else HttpFetchFailureReason.TRANSPORT
    )
    raise HttpFetchError(
        decision.failure.message,
        reason=reason,
        url=url,
        status_code=status_code,
        retryable=bool(decision.retryable),
    ) from outcome.last_exception


__all__ = [
    "HttpFetchError",
    "RequestOutcome",
    "fetch_html",
    "make_html_parser",
    "request_html",
]
