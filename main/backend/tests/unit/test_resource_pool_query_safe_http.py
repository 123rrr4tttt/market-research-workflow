from __future__ import annotations

from unittest.mock import patch

import pytest

from app.composition.resource_pool import RequestsHttpFetchPort
from app.services.ingest.adapters import http_utils
from app.services.ingest.retry_policy import RequestScope
from app.services.resource_pool import http_port
from app.services.resource_pool.http_port import (
    HttpFetchFailureReason,
    SameOriginHttpTargetPolicy,
    scoped_http_target_policy,
    set_http_fetch_port,
)
from mrw_functorial_kit.core.provider_port_failures import resource_pool_http_fetch_failures
from app.services.resource_pool.search_contract_discovery import QueryDiscoveryBudget


_PUBLIC_DNS = [(2, 1, 6, "", ("93.184.216.34", 0))]


class _Response:
    def __init__(self, status_code: int, location: str | None = None) -> None:
        self.status_code = status_code
        self.headers = {"Location": location} if location else {}
        self.text = "<html>ok</html>"
        self.content = self.text.encode()
        self.url = "https://example.com/final"


class _Session:
    headers: dict[str, str] = {}
    cookies: object = None

    def __init__(self) -> None:
        self.urls: list[str] = []
        self.request_kwargs: list[dict[str, object]] = []

    def get(self, url: str, **_kwargs: object) -> _Response:
        self.urls.append(url)
        self.request_kwargs.append(_kwargs)
        if len(self.urls) == 1:
            return _Response(302, "https://attacker.example/path")
        return _Response(200)

    def close(self) -> None:
        return None


def _policy(budget: QueryDiscoveryBudget | None = None) -> SameOriginHttpTargetPolicy:
    return SameOriginHttpTargetPolicy(
        allowed_origin="https://example.com",
        budget=budget,
    )


def test_safe_policy_rejects_private_dns_before_http_request() -> None:
    session = _Session()
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("192.168.1.10", 0))]),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(),
        )
    assert session.urls == []
    assert not outcome.ok
    assert outcome.response is None
    assert resource_pool_http_fetch_failures.matches(outcome.failures[-1])
    assert isinstance(outcome.last_exception, http_utils.UnsafeHttpTargetError)
    assert outcome.last_exception.reason_code == "unsafe_target"


def test_safe_policy_rejects_cgnat_dns_before_http_request() -> None:
    session = _Session()
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("100.64.0.1", 0))]),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(),
        )
    assert session.urls == []
    assert not outcome.ok
    assert outcome.last_exception is not None
    assert "non-public" in str(outcome.last_exception)


def test_canonical_origin_brackets_default_port_ipv6_host() -> None:
    assert (
        SameOriginHttpTargetPolicy.canonical_origin("https://[2600:db8::1]/path")
        == "https://[2600:db8::1]"
    )


def test_canonical_origin_returns_failure_for_malformed_ipv6_and_port() -> None:
    malformed_ipv6 = SameOriginHttpTargetPolicy.canonical_origin("https://2600:db8::1/path")
    malformed_port = SameOriginHttpTargetPolicy.canonical_origin("https://example.com:not-a-port")

    assert resource_pool_http_fetch_failures.matches(malformed_ipv6)
    assert malformed_ipv6.code == "unsafe_target"
    assert resource_pool_http_fetch_failures.matches(malformed_port)
    assert malformed_port.code == "unsafe_target"


def test_canonical_origin_accepts_public_http_and_ipv6_origin() -> None:
    assert SameOriginHttpTargetPolicy.canonical_origin("http://8.8.8.8/path") == "http://8.8.8.8"
    assert (
        SameOriginHttpTargetPolicy.canonical_origin("https://[2600:db8::1]:8443/path")
        == "https://[2600:db8::1]:8443"
    )


def test_safe_policy_fails_closed_when_dns_resolution_fails() -> None:
    session = _Session()
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils.socket, "getaddrinfo", side_effect=OSError("dns unavailable")),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(),
        )
    assert session.urls == []
    assert not outcome.ok
    assert isinstance(outcome.last_exception, http_utils.UnsafeHttpTargetError)
    assert "DNS resolution failed" in str(outcome.last_exception)


def test_safe_policy_blocks_cross_scope_redirect_before_next_request() -> None:
    session = _Session()
    budget = QueryDiscoveryBudget(max_requests=4, max_templates=4, timeout_seconds=10)
    policy = _policy(budget)
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils.socket, "getaddrinfo", return_value=_PUBLIC_DNS),
        pytest.raises(http_utils.HttpFetchError, match="outside the query target origin") as exc_info,
    ):
        http_utils.fetch_html(
            "https://example.com/search?q=test",
            retries=1,
            target_policy=policy,
        )
    assert session.urls == ["https://example.com/search?q=test"]
    assert session.request_kwargs[0]["allow_redirects"] is False
    assert budget.diagnostics["used_requests"] == 1
    assert policy.budget is budget
    assert exc_info.value.failure is not None
    assert exc_info.value.failure.code == "unsafe_target"


def test_request_budget_denial_returns_immutable_empty_result() -> None:
    session = _Session()
    budget = QueryDiscoveryBudget(max_requests=0, max_templates=3, timeout_seconds=10)
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils.socket, "getaddrinfo", return_value=_PUBLIC_DNS),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(budget),
        )

    assert session.urls == []
    assert outcome.status == "failed"
    assert outcome.response is None
    assert outcome.attempts == 1
    assert resource_pool_http_fetch_failures.matches(outcome.failures[-1])
    assert outcome.failures[-1].code == "discovery_disabled"
    assert isinstance(outcome.last_exception, http_utils.UnsafeHttpTargetError)
    assert outcome.last_exception.reason_code == "discovery_disabled"


def test_terminal_budget_failure_preserves_prior_retry_failure_history() -> None:
    class _RetrySession:
        headers: dict[str, str] = {}
        cookies: object = None
        urls: list[str] = []

        def get(self, url: str, **_kwargs: object) -> _Response:
            self.urls.append(url)
            return _Response(503)

        def close(self) -> None:
            return None

    session = _RetrySession()
    budget = QueryDiscoveryBudget(max_requests=1, max_templates=3, timeout_seconds=10)
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils.socket, "getaddrinfo", return_value=_PUBLIC_DNS),
        patch.object(http_utils.time, "sleep"),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=2,
            target_policy=_policy(budget),
        )

    assert session.urls == ["https://example.com"]
    assert len(outcome.failures) == 2
    assert outcome.failures[0].context["reason_code"] == "fetch_failed"
    assert outcome.failures[-1].code == "request_budget_exhausted"
    assert len(outcome.decisions) == 1
    assert isinstance(outcome.last_exception, http_utils.UnsafeHttpTargetError)


@pytest.mark.parametrize(
    ("max_requests", "timeout_seconds", "consume_request", "expected_reason"),
    [
        (0, 10, False, HttpFetchFailureReason.DISCOVERY_DISABLED),
        (1, 0, False, HttpFetchFailureReason.DEADLINE_EXCEEDED),
        (1, 10, True, HttpFetchFailureReason.REQUEST_BUDGET_EXHAUSTED),
    ],
)
def test_fetch_html_preserves_budget_failure_classification(
    max_requests: int,
    timeout_seconds: float,
    consume_request: bool,
    expected_reason: HttpFetchFailureReason,
) -> None:
    session = _Session()
    budget = QueryDiscoveryBudget(
        max_requests=max_requests, max_templates=3, timeout_seconds=timeout_seconds
    )
    if consume_request:
        assert budget.try_acquire_request("https://example.com") == (True, None)
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils.socket, "getaddrinfo", return_value=_PUBLIC_DNS),
        pytest.raises(http_utils.HttpFetchError) as exc_info,
    ):
        http_utils.fetch_html("https://example.com", retries=1, target_policy=_policy(budget))

    assert session.urls == []
    error = exc_info.value
    assert error.reason is expected_reason
    assert error.reason_code == expected_reason.value
    assert error.failure is not None
    assert error.failure.code == expected_reason.value
    assert error.status_code is None
    assert error.retryable is False


def test_fetch_html_lifts_terminal_budget_failure_after_http_retry() -> None:
    class _RetrySession(_Session):
        def get(self, url: str, **_kwargs: object) -> _Response:
            self.urls.append(url)
            return _Response(503)

    session = _RetrySession()
    budget = QueryDiscoveryBudget(max_requests=1, max_templates=3, timeout_seconds=10)
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils.socket, "getaddrinfo", return_value=_PUBLIC_DNS),
        patch.object(http_utils.time, "sleep"),
        pytest.raises(http_utils.HttpFetchError) as exc_info,
    ):
        http_utils.fetch_html("https://example.com", retries=2, target_policy=_policy(budget))

    assert session.urls == ["https://example.com"]
    error = exc_info.value
    assert error.reason is HttpFetchFailureReason.REQUEST_BUDGET_EXHAUSTED
    assert error.reason_code == "request_budget_exhausted"
    assert error.failure is not None
    assert error.failure.code == "request_budget_exhausted"
    assert error.status_code is None
    assert error.retryable is False
    assert isinstance(error.__cause__, http_utils.UnsafeHttpTargetError)


def test_safe_policy_counts_each_same_origin_redirect_as_a_request() -> None:
    session = _Session()
    budget = QueryDiscoveryBudget(max_requests=4, max_templates=4, timeout_seconds=10)

    class _SameOriginSession(_Session):
        def get(self, url: str, **kwargs: object) -> _Response:
            self.urls.append(url)
            if len(self.urls) == 1:
                return _Response(302, "https://example.com/final")
            return _Response(200)

    same_origin_session = _SameOriginSession()
    with (
        patch.object(http_utils.requests, "Session", return_value=same_origin_session),
        patch.object(http_utils.socket, "getaddrinfo", return_value=_PUBLIC_DNS),
    ):
        text, response = http_utils.fetch_html(
            "https://example.com/search?q=test",
            retries=1,
            target_policy=_policy(budget),
        )

    assert text == "<html>ok</html>"
    assert response.status_code == 200
    assert same_origin_session.urls == [
        "https://example.com/search?q=test",
        "https://example.com/final",
    ]
    assert budget.diagnostics["used_requests"] == 2


def test_http_port_reports_target_policy_unavailable_without_calling_legacy_port() -> None:
    class _LegacyPort:
        def fetch_html(self, url: str, **kwargs: object) -> tuple[str, object]:
            raise AssertionError("legacy port must not be called with a target policy")

    original_port = http_port._http_fetch_port
    set_http_fetch_port(_LegacyPort())
    try:
        with (
            scoped_http_target_policy(_policy()),
            pytest.raises(http_port.HttpFetchError) as exc_info,
        ):
            http_port.fetch_html("https://example.com")
    finally:
        set_http_fetch_port(original_port)

    assert exc_info.value.reason is HttpFetchFailureReason.TARGET_POLICY_UNAVAILABLE
    assert exc_info.value.reason_code == "target_policy_unavailable"
    assert resource_pool_http_fetch_failures.matches(exc_info.value.failure)


def test_requests_fetch_port_carries_optional_policy_and_old_call_remains_compatible() -> None:
    class _Response:
        text = "<html>ok</html>"
        content = b"<html>ok</html>"
        headers = {"Content-Type": "text/html"}
        status_code = 200
        url = "https://example.com/final"

    port = RequestsHttpFetchPort()
    with patch.object(
        http_utils,
        "fetch_html",
        return_value=("<html>ok</html>", _Response()),
    ) as mocked:
        text, projected = port.fetch_html(
            "https://example.com",
            timeout=2.0,
            retries=1,
            target_policy=_policy(),
        )

    mocked.assert_called_once_with(
        "https://example.com",
        headers=None,
        params=None,
        cookies=None,
        timeout=2.0,
        retries=1,
        backoff=1.5,
        target_policy=mocked.call_args.kwargs["target_policy"],
    )
    assert text == "<html>ok</html>"
    assert projected.final_url == "https://example.com/final"
