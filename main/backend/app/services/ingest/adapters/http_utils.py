from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import ipaddress
import os
import socket
from typing import Any, Literal, cast
from urllib.parse import quote, urljoin, urlsplit

import requests
from requests import PreparedRequest
from requests.adapters import HTTPAdapter
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
    SameOriginHttpTargetPolicy,
    make_html_parser,
)
from functorial_kit import Failure
from mrw_functorial_kit.core.provider_port_failures import resource_pool_http_fetch_failures
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
PUBLIC_DNS_MODE_ENV = "MRW_HTTP_PUBLIC_DNS"
CLOUDFLARE_PUBLIC_DNS_MODE = "cloudflare"
CLOUDFLARE_DOH_URL = "https://1.1.1.1/dns-query"
NO_POLICY_MAX_REDIRECTS = 30
LEGACY_FETCH_SCOPE = RequestScope(provider="legacy_http_fetch")


@dataclass(frozen=True, slots=True)
class _TargetEndpoint:
    url: str
    scheme: str
    host: str
    port: int


class UnsafeHttpTargetError(RuntimeError):
    reason_code: str
    url: str
    failure: Failure

    def __init__(self, message: str, *, reason_code: str, url: str, failure: Failure) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.url = url
        self.failure = failure


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


def _unsafe_target_failure(
    message: str,
    *,
    url: str,
    reason_code: str = "unsafe_target",
    resolver_stage: str = "",
    target_host: str = "",
) -> Failure:
    code: Literal["unsafe_target"] = "unsafe_target"
    return _target_policy_failure(
        code,
        message,
        url=url,
        reason_code=reason_code,
        resolver_stage=resolver_stage,
        target_host=target_host,
    )


def _budget_target_failure(
    message: str,
    *,
    url: str,
    reason_code: str,
    resolver_stage: str = "",
    target_host: str = "",
) -> Failure:
    normalized_reason = reason_code if reason_code in {
        "discovery_disabled",
        "deadline_exceeded",
        "request_budget_exhausted",
    } else "request_budget_exhausted"
    code: Literal["discovery_disabled", "deadline_exceeded", "request_budget_exhausted"]
    if normalized_reason == "discovery_disabled":
        code = "discovery_disabled"
    elif normalized_reason == "deadline_exceeded":
        code = "deadline_exceeded"
    else:
        code = "request_budget_exhausted"
    return _target_policy_failure(
        code,
        message,
        url=url,
        reason_code=normalized_reason,
        resolver_stage=resolver_stage,
        target_host=target_host,
    )


def _target_policy_failure(
    code: Literal[
        "unsafe_target",
        "request_budget_exhausted",
        "deadline_exceeded",
        "discovery_disabled",
    ],
    message: str,
    *,
    url: str,
    reason_code: str,
    resolver_stage: str = "",
    target_host: str = "",
) -> Failure:
    context: dict[str, str] = {
        "boundary_class": "PROVIDER_PORT_FAILURE",
        "failure_family": resource_pool_http_fetch_failures.name,
        "operation": "ingest.http_utils.target_policy",
        "owner": "resource_pool.http_fetch",
        "reason_code": reason_code,
        "url": url,
    }
    if resolver_stage:
        context["resolver_stage"] = resolver_stage
    if target_host:
        context["target_host"] = target_host
    return resource_pool_http_fetch_failures.fail(code, message, context)


def _unsafe_ip(value: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        not value.is_global
        or value.is_private
        or value.is_loopback
        or value.is_link_local
        or value.is_reserved
        or value.is_multicast
        or value.is_unspecified
    )


def _unsafe_target(
    message: str,
    *,
    url: str,
    resolver_stage: str = "",
    target_host: str = "",
) -> UnsafeHttpTargetError:
    failure = _unsafe_target_failure(
        message,
        url=url,
        resolver_stage=resolver_stage,
        target_host=target_host,
    )
    return UnsafeHttpTargetError(
        str(failure.message),
        reason_code="unsafe_target",
        url=url,
        failure=failure,
    )


def _target_endpoint(url: str) -> _TargetEndpoint:
    raw = str(url or "").strip()
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        raise _unsafe_target("target URL port is invalid", url=raw) from exc
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise _unsafe_target("target URL must use http or https", url=raw)
    if parts.username or parts.password:
        raise _unsafe_target("target URL cannot contain userinfo", url=raw)
    host = str(parts.hostname or "").strip().lower()
    if not host or host.rstrip(".") == "localhost" or host.rstrip(".").endswith((".localhost", ".local")):
        raise _unsafe_target("target URL host is required", url=raw)
    return _TargetEndpoint(
        url=raw,
        scheme=scheme,
        host=host,
        port=port or (443 if scheme == "https" else 80),
    )


def _validate_policy_target(
    policy: SameOriginHttpTargetPolicy,
    url: str,
) -> _TargetEndpoint:
    endpoint = _target_endpoint(url)
    origin = policy.canonical_origin(endpoint.url)
    if isinstance(origin, Failure):
        raise UnsafeHttpTargetError(
            str(origin.message),
            reason_code="unsafe_target",
            url=endpoint.url,
            failure=origin,
        )
    if origin != policy.allowed_origin:
        raise _unsafe_target(
            "target URL is outside the query target origin",
            url=endpoint.url,
        )
    return endpoint


def _acquire_target_budget(
    budget: Any | None,
    url: str,
    resolver_stage: str = "",
    target_host: str = "",
) -> None:
    if budget is None:
        return
    acquired, denial_reason_value = budget.try_acquire_request(url)
    if acquired:
        return
    denial_reason = denial_reason_value or "request_budget_exhausted"
    budget.record_denial(denial_reason)
    failure = _budget_target_failure(
        f"query discovery budget denied request: {denial_reason}",
        url=url,
        reason_code=denial_reason,
        resolver_stage=resolver_stage,
        target_host=target_host,
    )
    raise UnsafeHttpTargetError(
        str(failure.message),
        reason_code=denial_reason,
        url=url,
        failure=failure,
    )


def _policy_rejection(exc: UnsafeHttpTargetError) -> Failure:
    return exc.failure


def _dns_name(value: object) -> str:
    return str(value or "").strip().rstrip(".").lower()


def _parse_public_doh_answer(
    payload: object,
    question_host: str,
) -> tuple[ipaddress.IPv4Address | None, int | None, str]:
    question = _dns_name(question_host)
    if not isinstance(payload, dict):
        return None, None, "DoH response is not an object"
    response_data = cast(dict[str, object], payload)
    if response_data.get("Status") != 0:
        return None, None, "DoH response status is not NOERROR"
    questions = response_data.get("Question")
    if not isinstance(questions, list):
        return None, None, "DoH response must contain exactly one question"
    question_rows = cast(list[object], questions)
    if len(question_rows) != 1:
        return None, None, "DoH response must contain exactly one question"
    question_row = question_rows[0]
    if not isinstance(question_row, dict):
        return None, None, "DoH question is invalid"
    dns_question = cast(dict[str, object], question_row)
    if _dns_name(dns_question.get("name")) != question:
        return None, None, "DoH question name does not match the target"
    if dns_question.get("type") != 1:
        return None, None, "DoH question type is not A"

    answers = response_data.get("Answer")
    if not isinstance(answers, list) or not answers:
        return None, None, "DoH response has no answers"
    cnames: dict[str, str] = {}
    a_answers: dict[str, list[tuple[int, str]]] = {}
    answer_ttls: list[int] = []
    for answer_row in cast(list[object], answers):
        if not isinstance(answer_row, dict):
            return None, None, "DoH answer is invalid"
        answer = cast(dict[str, object], answer_row)
        ttl = answer.get("TTL")
        if not isinstance(ttl, int) or isinstance(ttl, bool):
            return None, None, "DoH answer TTL is invalid"
        if ttl < 0:
            return None, None, "DoH answer TTL is negative"
        name = _dns_name(answer.get("name"))
        record_type = answer.get("type")
        data = str(answer.get("data") or "").strip()
        if not name or not data:
            return None, None, "DoH answer name or data is missing"
        answer_ttls.append(ttl)
        if record_type == 5:
            target = _dns_name(data)
            if not target:
                return None, None, "DoH CNAME target is invalid"
            previous = cnames.setdefault(name, target)
            if previous != target:
                return None, None, "DoH CNAME chain is ambiguous"
        elif record_type == 1:
            a_answers.setdefault(name, []).append((ttl, data))
        else:
            return None, None, "DoH answer type is not A or CNAME"

    current = question
    visited = {question}
    while current in cnames:
        current = cnames[current]
        if current in visited:
            return None, None, "DoH CNAME chain contains a cycle"
        visited.add(current)
    for alias in cnames:
        if alias in a_answers:
            return None, None, "DoH alias has both CNAME and A answers"
    extra_cnames = set(cnames) - visited
    if extra_cnames:
        return None, None, "DoH response contains a CNAME answer outside the question chain"
    unexpected_aliases = set(a_answers) - {current}
    if unexpected_aliases:
        return None, None, "DoH response contains an A answer outside the CNAME chain"
    final_answers = a_answers.get(current)
    if not final_answers:
        return None, None, "DoH CNAME chain has no A answer"

    addresses: list[ipaddress.IPv4Address] = []
    for ttl, data in final_answers:
        try:
            address = ipaddress.ip_address(data)
        except ValueError:
            return None, None, "DoH A answer is invalid"
        if not isinstance(address, ipaddress.IPv4Address):
            return None, None, "DoH A answer is not IPv4"
        if _unsafe_ip(address):
            return None, None, "DoH A answer is private, reserved, or non-global"
        addresses.append(address)
    if not addresses:
        return None, None, "DoH response has no A answer"
    return addresses[0], min(answer_ttls), ""


class _PinnedHTTPAdapter(HTTPAdapter):
    def __init__(self) -> None:
        self.pins: dict[tuple[str, str, int], str] = {}
        super().__init__(max_retries=0)

    def build_connection_pool_key_attributes(
        self,
        request: PreparedRequest,
        verify: bool | str,
        cert: str | tuple[str, str] | None = None,
    ):
        host_params, pool_kwargs = super().build_connection_pool_key_attributes(
            request,
            verify,
            cert=cert,
        )
        parts = urlsplit(str(request.url))
        host = str(parts.hostname or "").strip().lower()
        scheme = parts.scheme.lower()
        try:
            port = parts.port or (443 if scheme == "https" else 80)
        except ValueError as exc:
            raise _unsafe_target("target URL port is invalid", url=str(request.url)) from exc
        try:
            connection_ip = self.pins[(scheme, host, port)]
        except KeyError as exc:
            raise _unsafe_target(
                "public DNS mode has no verified address for the target",
                url=str(request.url),
            ) from exc

        default_port = 443 if scheme == "https" else 80
        host_for_header = f"[{host}]" if ":" in host else host
        host_header = host_for_header if port == default_port else f"{host_for_header}:{port}"
        request.headers["Host"] = host_header
        host_params["host"] = connection_ip
        # urllib3 accepts these pool keys beyond requests' TLS-only type stub.
        pinned_pool_kwargs = cast(dict[str, Any], pool_kwargs)
        pinned_pool_kwargs["headers"] = {"Host": host_header}
        if scheme == "https":
            pinned_pool_kwargs["server_hostname"] = host
            pinned_pool_kwargs["assert_hostname"] = host
        return host_params, pool_kwargs

    def get_connection_with_tls_context(
        self,
        request: PreparedRequest,
        verify: bool | str | None,
        proxies: Mapping[str, str] | None = None,
        cert: Any = None,
    ) -> Any:
        if any(bool(value) for value in (proxies or {}).values()):
            raise _unsafe_target("proxies are forbidden in public DNS mode", url=str(request.url))
        if verify is False:
            raise _unsafe_target("TLS verification cannot be disabled in public DNS mode", url=str(request.url))
        return super().get_connection_with_tls_context(
            request,
            True if verify is None else verify,
            proxies={},
            cert=cert,
        )


@dataclass(frozen=True, slots=True)
class _PublicDnsAnswer:
    address: str
    expires_at: float


class _PublicDnsResolver:
    def __init__(
        self,
        session: requests.Session,
        adapter: _PinnedHTTPAdapter,
        budget: Any | None,
    ) -> None:
        self._session = session
        self._adapter = adapter
        self._budget = budget
        self._doh_adapter = HTTPAdapter(max_retries=0)
        self._cache: dict[str, _PublicDnsAnswer] = {}

    def _query(self, host: str, timeout: float) -> _PublicDnsAnswer:
        doh_url = (
            f"{CLOUDFLARE_DOH_URL}?name={quote(host)}&type=A"
        )
        stage = {"resolver_stage": "cloudflare_doh", "target_host": host}
        request = requests.Request(
            "GET",
            CLOUDFLARE_DOH_URL,
            params={"name": host, "type": "A"},
            headers={"Accept": "application/dns-json"},
        )
        prepared = request.prepare()
        response: requests.Response | None = None
        try:
            response = self._doh_adapter.send(
                prepared,
                timeout=max(0.001, min(5.0, float(timeout))),
                verify=True if self._session.verify is None else self._session.verify,
                proxies={},
                stream=True,
            )
            if response.status_code != 200:
                raise ValueError(f"DoH endpoint returned HTTP {response.status_code}")
            payload = response.json()
        except requests.RequestException as exc:
            unsafe = _unsafe_target(
                f"public DoH request failed: {exc}",
                url=doh_url,
                **stage,
            )
            raise unsafe from exc
        except (TypeError, ValueError) as exc:
            unsafe = _unsafe_target(
                f"public DoH response is invalid: {exc}",
                url=doh_url,
                **stage,
            )
            raise unsafe from exc
        finally:
            if response is not None:
                response.close()
        address, ttl, error = _parse_public_doh_answer(payload, host)
        if address is None or ttl is None:
            raise _unsafe_target(
                error or "public DoH response is invalid",
                url=doh_url,
                **stage,
            )
        answer = _PublicDnsAnswer(
            address=address.compressed,
            expires_at=time.monotonic() + max(0, ttl),
        )
        return answer

    def resolve(self, host: str, timeout: float) -> str:
        cached = self._cache.get(host)
        if cached is not None and cached.expires_at > time.monotonic():
            return cached.address
        _acquire_target_budget(
            self._budget,
            f"{CLOUDFLARE_DOH_URL}?name={quote(host)}&type=A",
            resolver_stage="cloudflare_doh",
            target_host=host,
        )
        answer = self._query(host, timeout)
        if _unsafe_ip(ipaddress.ip_address(answer.address)):
            raise _unsafe_target(
                "DoH A answer is private, reserved, or non-global",
                url=host,
                resolver_stage="cloudflare_doh",
                target_host=host,
            )
        self._cache[host] = answer
        return answer.address

    def prepare_target(
        self,
        url: str,
        *,
        target_policy: SameOriginHttpTargetPolicy | None,
        timeout: float,
    ) -> str:
        if target_policy is not None:
            endpoint = _validate_policy_target(target_policy, url)
        else:
            endpoint = _target_endpoint(url)
        try:
            literal = ipaddress.ip_address(endpoint.host)
        except ValueError:
            connection_ip = self.resolve(
                endpoint.host,
                min(timeout, self._remaining_seconds(timeout)),
            )
        else:
            if _unsafe_ip(literal):
                raise _unsafe_target(
                    "target IP is private, reserved, or non-global",
                    url=endpoint.url,
                )
            connection_ip = literal.compressed

        if target_policy is not None:
            _acquire_target_budget(target_policy.budget, endpoint.url)
        self._adapter.pins[(endpoint.scheme, endpoint.host, endpoint.port)] = connection_ip
        return endpoint.url

    def _remaining_seconds(self, timeout: float) -> float:
        if self._budget is None:
            return timeout
        return min(timeout, self._budget.remaining_seconds)

    def close(self) -> None:
        self._doh_adapter.close()


def _public_dns_requested() -> bool:
    return os.environ.get(PUBLIC_DNS_MODE_ENV) == CLOUDFLARE_PUBLIC_DNS_MODE


def _configure_public_dns_session(
    session: requests.Session,
    budget: Any | None,
) -> _PublicDnsResolver:
    if session.verify is False:
        raise _unsafe_target("TLS verification cannot be disabled in public DNS mode", url="")
    if any(bool(proxy) for proxy in (session.proxies or {}).values()):
        raise _unsafe_target("proxies are forbidden in public DNS mode", url="")
    session.trust_env = False
    if session.verify is True or session.verify is None:
        session.verify = (
            os.environ.get("REQUESTS_CA_BUNDLE")
            or os.environ.get("CURL_CA_BUNDLE")
            or True
        )
    adapter = _PinnedHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return _PublicDnsResolver(session, adapter, budget)


def validate_target_request_url(policy: SameOriginHttpTargetPolicy, url: str) -> str:
    """Validate DNS, target scope, and request budget immediately before send."""

    raw = str(url or "").strip()
    origin = policy.canonical_origin(raw)
    if isinstance(origin, Failure):
        raise UnsafeHttpTargetError(
            str(origin.message),
            reason_code="unsafe_target",
            url=raw,
            failure=origin,
        )
    if origin != policy.allowed_origin:
        failure = _unsafe_target_failure("target URL is outside the query target origin", url=raw)
        raise UnsafeHttpTargetError(
            str(failure.message),
            reason_code="unsafe_target",
            url=raw,
            failure=failure,
        )

    parts = urlsplit(raw)
    host = str(parts.hostname or "").strip().lower()
    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            failure = _unsafe_target_failure("target DNS resolution failed", url=raw)
            raise UnsafeHttpTargetError(
                str(failure.message),
                reason_code="unsafe_target",
                url=raw,
                failure=failure,
            ) from exc
        resolved: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        for info in infos:
            sockaddr = info[4] if len(info) > 4 else None
            candidate = str((sockaddr or (None,))[0] or "").strip()
            if not candidate:
                continue
            try:
                resolved.add(ipaddress.ip_address(candidate))
            except ValueError:
                continue
        if not resolved or any(_unsafe_ip(value) for value in resolved):
            failure = _unsafe_target_failure(
                "target DNS resolves to a non-public address",
                url=raw,
            )
            raise UnsafeHttpTargetError(
                str(failure.message),
                reason_code="unsafe_target",
                url=raw,
                failure=failure,
            )
    else:
        if _unsafe_ip(literal):
            failure = _unsafe_target_failure(
                "target IP is private, reserved, or non-global",
                url=raw,
            )
            raise UnsafeHttpTargetError(
                str(failure.message),
                reason_code="unsafe_target",
                url=raw,
                failure=failure,
            )

    if policy.budget is not None:
        acquired, denial_reason_value = policy.budget.try_acquire_request(raw)
        if not acquired:
            denial_reason = denial_reason_value or "request_budget_exhausted"
            policy.budget.record_denial(denial_reason)
            failure = _budget_target_failure(
                f"query discovery budget denied request: {denial_reason}",
                url=raw,
                reason_code=denial_reason,
            )
            raise UnsafeHttpTargetError(
                str(failure.message),
                reason_code=denial_reason,
                url=raw,
                failure=failure,
            )
    return raw


def validate_target_redirect(
    policy: SameOriginHttpTargetPolicy,
    current_url: str,
    response: Response,
) -> str:
    """Resolve and scope-check one redirect without consuming request budget."""

    current = str(current_url or "").strip()
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code not in {301, 302, 303, 307, 308}:
        return current
    headers = getattr(response, "headers", {}) or {}
    location = str(headers.get("location") or headers.get("Location") or "").strip()
    if not location:
        return current
    target = urljoin(current, location)
    origin = policy.canonical_origin(target)
    if isinstance(origin, Failure):
        raise UnsafeHttpTargetError(
            str(origin.message),
            reason_code="unsafe_target",
            url=target,
            failure=origin,
        )
    if origin != policy.allowed_origin:
        failure = _unsafe_target_failure(
            "redirect URL is outside the query target origin",
            url=target,
        )
        raise UnsafeHttpTargetError(
            str(failure.message),
            reason_code="unsafe_target",
            url=target,
            failure=failure,
        )
    return target


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
    target_policy: SameOriginHttpTargetPolicy | None = None,
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
    public_dns_mode = _public_dns_requested()
    public_dns_resolver: _PublicDnsResolver | None = None

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
                if public_dns_mode and public_dns_resolver is None:
                    public_dns_resolver = _configure_public_dns_session(
                        session,
                        target_policy.budget if target_policy else None,
                    )
                current_url = str(url or "").strip()
                redirect_count = 0
                first_request = True
                follow_redirects_manually = public_dns_mode and target_policy is None
                while True:
                    if target_policy is not None:
                        if public_dns_resolver is not None:
                            current_url = public_dns_resolver.prepare_target(
                                current_url,
                                target_policy=target_policy,
                                timeout=timeout,
                            )
                        else:
                            current_url = validate_target_request_url(target_policy, current_url)
                    elif public_dns_resolver is not None:
                        current_url = public_dns_resolver.prepare_target(
                            current_url,
                            target_policy=None,
                            timeout=timeout,
                        )
                    effective_timeout = timeout
                    if target_policy is not None and target_policy.budget is not None:
                        effective_timeout = min(timeout, max(0.001, target_policy.budget.remaining_seconds))
                    response = session.get(
                        current_url,
                        params=params if first_request else None,
                        timeout=effective_timeout,
                        allow_redirects=target_policy is None and not public_dns_mode,
                    )
                    first_request = False
                    if target_policy is None and not follow_redirects_manually:
                        break
                    if int(response.status_code) not in {301, 302, 303, 307, 308}:
                        break
                    redirect_headers = getattr(response, "headers", {}) or {}
                    if target_policy is None:
                        location = str(
                            redirect_headers.get("location")
                            or redirect_headers.get("Location")
                            or ""
                        ).strip()
                        if not location:
                            break
                        if redirect_count >= NO_POLICY_MAX_REDIRECTS:
                            raise requests.TooManyRedirects(
                                f"exceeded {NO_POLICY_MAX_REDIRECTS} redirects"
                            )
                        next_url = urljoin(current_url, location)
                        if (
                            SameOriginHttpTargetPolicy.canonical_origin(current_url)
                            != SameOriginHttpTargetPolicy.canonical_origin(next_url)
                        ):
                            for header in ("Authorization", "Proxy-Authorization", "Cookie", "Host"):
                                session.headers.pop(header, None)
                            session.auth = None
                            session.cookies.clear()
                        current_url = next_url
                        redirect_count += 1
                        continue
                    has_location = bool(
                        str(
                            redirect_headers.get("location")
                            or redirect_headers.get("Location")
                            or ""
                        ).strip()
                    )
                    if not has_location or redirect_count >= max(0, int(target_policy.max_redirects)):
                        failure = _unsafe_target_failure(
                            "HTTP target policy redirect limit or missing Location exceeded",
                            url=current_url,
                        )
                        raise UnsafeHttpTargetError(
                            str(failure.message),
                            reason_code="unsafe_target",
                            url=current_url,
                            failure=failure,
                        )
                    current_url = validate_target_redirect(target_policy, current_url, response)
                    redirect_count += 1
            except UnsafeHttpTargetError as exc:
                return RequestOutcome(
                    failures=tuple(failures) + (_policy_rejection(exc),),
                    decisions=tuple(decisions),
                    attempts=attempt + 1,
                    last_exception=exc,
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
                delay_seconds = max(0.0, decisions[-1].delay_seconds + jitter)
                if target_policy is not None and target_policy.budget is not None:
                    delay_seconds = min(delay_seconds, max(0.0, target_policy.budget.remaining_seconds))
                sleeper(delay_seconds)

        raise AssertionError
    finally:
        if public_dns_resolver is not None:
            public_dns_resolver.close()
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
    target_policy: SameOriginHttpTargetPolicy | None = None,
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
        target_policy=target_policy,
    )
    if outcome.ok and outcome.response is not None:
        return outcome.text, outcome.response

    if outcome.failures and resource_pool_http_fetch_failures.matches(outcome.failures[-1]):
        failure = outcome.failures[-1]
        context = failure.context or {}
        reason_code = str(context.get("reason_code") or failure.code)
        reason = {member.value: member for member in HttpFetchFailureReason}.get(
            str(failure.code), HttpFetchFailureReason.TRANSPORT
        )
        # kit:boundary owner=resource_pool.http_fetch.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=resource_pool.http_fetch.failure witness=test:test_safe_policy_blocks_cross_scope_redirect_before_next_request
        raise HttpFetchError(
            str(failure.message),
            reason=reason,
            url=str(context.get("url") or url),
            retryable=False,
            reason_code=reason_code,
            failure=failure,
        ) from outcome.last_exception

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
    "UnsafeHttpTargetError",
    "RequestOutcome",
    "fetch_html",
    "make_html_parser",
    "request_html",
]
