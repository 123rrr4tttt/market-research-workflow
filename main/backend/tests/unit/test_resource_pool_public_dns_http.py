from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import requests
import urllib3.connection

from app.services.ingest.adapters import http_utils
from app.services.ingest.retry_policy import RequestScope
from app.services.resource_pool.http_port import SameOriginHttpTargetPolicy
from app.services.resource_pool.search_contract_discovery import QueryDiscoveryBudget
from mrw_functorial_kit.core.provider_port_failures import resource_pool_http_fetch_failures


class _Response:
    def __init__(
        self,
        status_code: int,
        location: str | None = None,
        text: str = "<html>ok</html>",
        url: str = "https://example.com/final",
    ) -> None:
        self.status_code = status_code
        self.headers = {"Location": location} if location else {}
        self.text = text
        self.content = text.encode()
        self.url = url


class _UrlSession(requests.Session):
    def __init__(self, responses: list[_Response]) -> None:
        super().__init__()
        self.responses = list(responses)
        self.urls: list[str] = []
        self.sent_headers: list[dict[str, str]] = []

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.urls.append(url)
        self.last_kwargs = kwargs
        self.sent_headers.append(dict(self.headers))
        if not self.responses:
            return _Response(200)
        return self.responses.pop(0)


def _answer(address: str = "93.184.216.34", ttl: int = 300) -> http_utils._PublicDnsAnswer:
    return http_utils._PublicDnsAnswer(
        address=address,
        expires_at=http_utils.time.monotonic() + ttl,
    )


def _policy(budget: QueryDiscoveryBudget | None = None) -> SameOriginHttpTargetPolicy:
    return SameOriginHttpTargetPolicy(
        allowed_origin="https://example.com",
        budget=budget,
    )


def _public_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(http_utils.PUBLIC_DNS_MODE_ENV, "cloudflare")


def _system_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(http_utils.PUBLIC_DNS_MODE_ENV, raising=False)


@pytest.mark.parametrize(
    ("addresses", "message"),
    [
        (["198.18.0.1"], "non-public"),
        (["192.168.1.10"], "non-public"),
        (["100.64.0.1"], "non-public"),
        (["93.184.216.34", "10.0.0.1"], "non-public"),
    ],
)
def test_default_system_dns_rejects_fake_private_and_mixed_addresses(
    monkeypatch: pytest.MonkeyPatch,
    addresses: list[str],
    message: str,
) -> None:
    _system_mode(monkeypatch)
    session = _UrlSession([_Response(200)])
    dns_result = [(2, 1, 6, "", (address, 443)) for address in addresses]
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils.socket, "getaddrinfo", return_value=dns_result),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(),
        )

    assert session.urls == []
    assert not outcome.ok
    assert resource_pool_http_fetch_failures.matches(outcome.failures[-1])
    assert outcome.failures[-1].code == "unsafe_target"
    assert message in str(outcome.last_exception)


def test_default_mode_does_not_enter_public_dns_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    _system_mode(monkeypatch)
    session = _UrlSession([_Response(200)])
    session.verify = False
    session.proxies = {"https": "http://127.0.0.1:7892"}
    with patch.object(http_utils.requests, "Session", return_value=session):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
        )

    assert outcome.ok
    assert session.urls == ["https://example.com"]
    assert session.last_kwargs["allow_redirects"] is True
    assert session.trust_env is True


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"Status": 3, "Question": [{"name": "example.com.", "type": 1}]}, "NOERROR"),
        (
            {
                "Status": 0,
                "Question": [{"name": "other.example.", "type": 1}],
                "Answer": [{"name": "other.example.", "type": 1, "TTL": 30, "data": "93.184.216.34"}],
            },
            "does not match",
        ),
        (
            {
                "Status": 0,
                "Question": [{"name": "example.com.", "type": 28}],
                "Answer": [{"name": "example.com.", "type": 1, "TTL": 30, "data": "93.184.216.34"}],
            },
            "type is not A",
        ),
        (
            {
                "Status": 0,
                "Question": [{"name": "example.com.", "type": 1}],
                "Answer": [{"name": "example.com.", "type": 1, "TTL": 30, "data": "198.18.0.1"}],
            },
            "non-global",
        ),
        (
            {
                "Status": 0,
                "Question": [{"name": "example.com.", "type": 1}],
                "Answer": [
                    {"name": "example.com.", "type": 1, "TTL": 30, "data": "93.184.216.34"},
                    {"name": "example.com.", "type": 1, "TTL": 30, "data": "192.168.1.1"},
                ],
            },
            "non-global",
        ),
        (
            {
                "Status": 0,
                "Question": [{"name": "example.com.", "type": 1}],
                "Answer": [{"name": "example.com.", "type": 5, "TTL": 30, "data": "www.example.com."}],
            },
            "no A answer",
        ),
        (
            {
                "Status": 0,
                "Question": [{"name": "a.example.", "type": 1}],
                "Answer": [
                    {"name": "a.example.", "type": 5, "TTL": 30, "data": "b.example."},
                    {"name": "b.example.", "type": 5, "TTL": 30, "data": "a.example."},
                ],
            },
            "cycle",
        ),
        (
            {
                "Status": 0,
                "Question": [{"name": "example.com.", "type": 1}],
                "Answer": [{"name": "example.com.", "type": 1, "TTL": -1, "data": "93.184.216.34"}],
            },
            "negative",
        ),
        (
            {
                "Status": 0,
                "Question": [{"name": "example.com.", "type": 1}],
                "Answer": [
                    {"name": "example.com.", "type": 5, "TTL": 30, "data": "www.example."},
                    {"name": "other.example.", "type": 1, "TTL": 30, "data": "93.184.216.34"},
                ],
            },
            "outside the CNAME chain",
        ),
    ],
)
def test_public_doh_answer_parser_rejects_untrusted_answers(
    payload: dict[str, Any],
    message: str,
) -> None:
    question = (
        "a.example" if payload["Question"][0]["name"] == "a.example." else "example.com"
    )
    address, ttl, error = http_utils._parse_public_doh_answer(payload, question)

    assert address is None
    assert ttl is None
    assert message in error


def test_public_doh_answer_parser_follows_cname_and_keeps_minimum_ttl() -> None:
    payload = {
        "Status": 0,
        "Question": [{"name": "example.com.", "type": 1}],
        "Answer": [
            {"name": "example.com.", "type": 5, "TTL": 30, "data": "www.example.com."},
            {"name": "www.example.com.", "type": 1, "TTL": 120, "data": "93.184.216.34"},
        ],
    }

    address, ttl, error = http_utils._parse_public_doh_answer(payload, "example.com")

    assert address is not None
    assert address.compressed == "93.184.216.34"
    assert ttl == 30
    assert error == ""


def test_public_dns_charges_doh_and_target_from_one_budget_without_same_origin_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession([_Response(200)])
    budget = QueryDiscoveryBudget(max_requests=2, max_templates=4, timeout_seconds=10)
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils._PublicDnsResolver, "_query", return_value=_answer()),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(budget),
        )

    assert outcome.ok
    assert session.urls == ["https://example.com"]
    assert budget.diagnostics["used_requests"] == 2
    assert session.last_kwargs["allow_redirects"] is False
    assert isinstance(session.adapters["https://"], http_utils._PinnedHTTPAdapter)
    assert session.adapters["https://"].pins[("https", "example.com", 443)] == "93.184.216.34"


def test_public_dns_target_budget_denial_keeps_doh_charge(monkeypatch: pytest.MonkeyPatch) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession([_Response(200)])
    budget = QueryDiscoveryBudget(max_requests=1, max_templates=4, timeout_seconds=10)
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils._PublicDnsResolver, "_query", return_value=_answer()),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(budget),
        )

    assert session.urls == []
    assert not outcome.ok
    assert outcome.failures[-1].code == "request_budget_exhausted"
    assert budget.diagnostics["used_requests"] == 1


def test_public_dns_deadline_checks_doh_step(monkeypatch: pytest.MonkeyPatch) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession([_Response(200)])
    budget = QueryDiscoveryBudget(max_requests=2, max_templates=4, timeout_seconds=0)
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(
            http_utils._PublicDnsResolver,
            "_query",
            side_effect=AssertionError("deadline must deny before DoH"),
        ),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(budget),
        )

    assert session.urls == []
    assert outcome.failures[-1].code == "deadline_exceeded"


def test_public_dns_reuses_positive_ttl_across_target_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession([_Response(503), _Response(503)])
    budget = QueryDiscoveryBudget(max_requests=3, max_templates=4, timeout_seconds=10)
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils._PublicDnsResolver, "_query", return_value=_answer()),
        patch.object(http_utils.time, "sleep"),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=2,
            backoff_seconds=0,
            jitter_seconds=0,
            target_policy=_policy(budget),
        )

    assert not outcome.ok
    assert session.urls == ["https://example.com", "https://example.com"]
    assert budget.diagnostics["used_requests"] == 3
    assert outcome.attempts == 2


def test_public_dns_pin_prevents_system_dns_rebinding(monkeypatch: pytest.MonkeyPatch) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession([_Response(200)])
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils._PublicDnsResolver, "_query", return_value=_answer()),
        patch.object(
            http_utils.socket,
            "getaddrinfo",
            side_effect=AssertionError("target must not use system DNS"),
        ),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(),
        )

    assert outcome.ok
    assert session.urls == ["https://example.com"]
    assert session.trust_env is False
    assert session.adapters["https://"].pins[("https", "example.com", 443)] == "93.184.216.34"


def test_public_dns_redirects_are_checked_before_each_send(monkeypatch: pytest.MonkeyPatch) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession(
        [_Response(302, "https://example.com/final"), _Response(200)],
    )
    budget = QueryDiscoveryBudget(max_requests=4, max_templates=4, timeout_seconds=10)
    answers = [
        _answer("93.184.216.34", ttl=0),
        _answer("104.16.132.229", ttl=0),
    ]
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils._PublicDnsResolver, "_query", side_effect=answers),
    ):
        outcome = http_utils.request_html(
            "https://example.com/search",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(budget),
        )

    assert outcome.ok
    assert session.urls == ["https://example.com/search", "https://example.com/final"]
    assert budget.diagnostics["used_requests"] == 4
    assert session.adapters["https://"].pins[("https", "example.com", 443)] == "104.16.132.229"


def test_public_dns_policy_rejects_cross_origin_redirect_before_doh_and_next_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession([_Response(302, "https://attacker.example/path"), _Response(200)])
    budget = QueryDiscoveryBudget(max_requests=4, max_templates=4, timeout_seconds=10)
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils._PublicDnsResolver, "_query", return_value=_answer()),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(budget),
        )

    assert session.urls == ["https://example.com"]
    assert not outcome.ok
    assert outcome.failures[-1].code == "unsafe_target"
    assert budget.diagnostics["used_requests"] == 2


def test_public_dns_policy_rejects_private_redirect_answer_before_next_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession([_Response(302, "https://example.com/final"), _Response(200)])
    answers = [_answer("93.184.216.34", ttl=0), _answer("192.168.1.1", ttl=0)]
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils._PublicDnsResolver, "_query", side_effect=answers),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
            target_policy=_policy(),
        )

    assert session.urls == ["https://example.com"]
    assert not outcome.ok
    assert "non-global" in str(outcome.last_exception)


def test_public_dns_no_policy_follows_cross_origin_redirect_with_each_hop_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession(
        [
            _Response(302, "https://other.example/final", url="https://other.example/final"),
            _Response(200, url="https://other.example/final"),
        ],
    )
    answers = [_answer("93.184.216.34", ttl=0), _answer("104.16.132.229", ttl=0)]
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils._PublicDnsResolver, "_query", side_effect=answers),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
        )

    assert outcome.ok
    assert session.urls == ["https://example.com", "https://other.example/final"]
    assert session.last_kwargs["allow_redirects"] is False
    assert session.adapters["https://"].pins[("https", "other.example", 443)] == "104.16.132.229"


def test_public_dns_no_policy_rejects_private_redirect_answer_before_next_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession([_Response(302, "https://other.example/final"), _Response(200)])
    answers = [_answer("93.184.216.34", ttl=0), _answer("198.18.0.1", ttl=0)]
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils._PublicDnsResolver, "_query", side_effect=answers),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
        )

    assert session.urls == ["https://example.com"]
    assert not outcome.ok
    assert "non-global" in str(outcome.last_exception)


def test_public_dns_rejects_disabled_tls_and_configured_proxy_before_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public_mode(monkeypatch)
    unsafe_session = _UrlSession([_Response(200)])
    unsafe_session.verify = False
    proxy_session = _UrlSession([_Response(200)])
    proxy_session.proxies = {"https": "http://127.0.0.1:7892"}

    with patch.object(http_utils.requests, "Session", return_value=unsafe_session):
        tls_outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
        )
    with patch.object(http_utils.requests, "Session", return_value=proxy_session):
        proxy_outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            retries=1,
        )

    assert unsafe_session.urls == []
    assert tls_outcome.failures[-1].code == "unsafe_target"
    assert "TLS verification" in str(tls_outcome.last_exception)
    assert proxy_session.urls == []
    assert proxy_outcome.failures[-1].code == "unsafe_target"
    assert "proxies are forbidden" in str(proxy_outcome.last_exception)


def test_pinned_adapter_preserves_request_host_tls_name_and_isolates_pools() -> None:
    adapter = http_utils._PinnedHTTPAdapter()
    request = requests.Request("GET", "https://example.com/path").prepare()
    adapter.pins[("https", "example.com", 443)] = "93.184.216.34"

    host_params, pool_kwargs = adapter.build_connection_pool_key_attributes(
        request,
        verify=True,
    )
    assert host_params["host"] == "93.184.216.34"
    assert pool_kwargs["server_hostname"] == "example.com"
    assert pool_kwargs["assert_hostname"] == "example.com"

    with patch.object(
        urllib3.connection.connection,
        "create_connection",
        return_value=object(),
    ) as connect:
        pool = adapter.get_connection_with_tls_context(request, True, proxies={})
        assert pool.host == "93.184.216.34"
        connection = pool._new_conn()
        connection._new_conn()

        adapter.pins[("https", "example.com", 443)] = "104.16.132.229"
        second_pool = adapter.get_connection_with_tls_context(request, True, proxies={})

    connect.assert_called_once()
    assert connect.call_args.args[0] == ("93.184.216.34", 443)
    assert request.url == "https://example.com/path"
    assert request.headers["Host"] == "example.com"
    assert connection.host == "93.184.216.34"
    assert connection.server_hostname == "example.com"
    assert connection.assert_hostname == "example.com"
    assert second_pool is not pool
    assert any(key.key_host == "93.184.216.34" for key in adapter.poolmanager.pools.keys())
    assert any(key.key_host == "104.16.132.229" for key in adapter.poolmanager.pools.keys())
    adapter.close()


def test_public_dns_cross_origin_redirect_drops_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _public_mode(monkeypatch)
    session = _UrlSession([_Response(302, "https://other.example/path"), _Response(200)])
    session.cookies.set("session", "private-cookie")
    session.auth = ("private-user", "private-password")
    with (
        patch.object(http_utils.requests, "Session", return_value=session),
        patch.object(http_utils._PublicDnsResolver, "_query", return_value=_answer()),
    ):
        outcome = http_utils.request_html(
            "https://example.com",
            scope=RequestScope(provider="test"),
            headers={"Authorization": "private-token", "Cookie": "session=private-cookie"},
            retries=1,
        )
    assert outcome.ok
    assert session.sent_headers[0]["Authorization"] == "private-token"
    assert "Authorization" not in session.sent_headers[1]
    assert "Cookie" not in session.sent_headers[1]
    assert not session.cookies
    assert session.auth is None


def test_pinned_adapter_rejects_proxy_before_connection_pool_creation() -> None:
    adapter = http_utils._PinnedHTTPAdapter()
    request = requests.Request("GET", "https://example.com").prepare()
    adapter.pins[("https", "example.com", 443)] = "93.184.216.34"

    with pytest.raises(http_utils.UnsafeHttpTargetError, match="proxies are forbidden"):
        adapter.get_connection_with_tls_context(
            request,
            True,
            proxies={"https": "http://127.0.0.1:7892"},
        )
