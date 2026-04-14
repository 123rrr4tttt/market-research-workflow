from __future__ import annotations

import base64
import html
import ipaddress
import re
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse, urlunparse, unquote

import requests


_TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
    "ref_src",
    "ref_url",
    "spm",
    "_hsenc",
    "_hsmi",
    "oc",
}

_WRAPPED_URL_QUERY_KEYS = (
    "q",
    "url",
    "u",
    "target",
    "dest",
    "destination",
    "redirect",
    "redirect_url",
    "r",
    "to",
    "uddg",
)

_HTTP_URL_IN_TEXT_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_GOOGLE_NEWS_SIG_RE = re.compile(r"data-n-a-sg=(?:\"([^\"]+)\"|'([^']+)')")
_GOOGLE_NEWS_TS_RE = re.compile(r"data-n-a-ts=(?:\"([^\"]+)\"|'([^']+)')")
_GOOGLE_NEWS_BATCH_RESULT_RES = (
    re.compile(r'\\\\"garturlres\\\\",\\\\"(.*?)\\\\",'),
    re.compile(r'\["garturlres","(.*?)",'),
)
_GOOGLE_NEWS_BATCH_CACHE: dict[str, str] = {}
_GOOGLE_NEWS_BATCH_CACHE_EXPIRES_AT: dict[str, float] = {}
_GOOGLE_NEWS_BATCH_NEGATIVE_CACHE_EXPIRES_AT: dict[str, float] = {}
_GOOGLE_NEWS_BATCH_CACHE_TTL_SECONDS = 24 * 60 * 60
_GOOGLE_NEWS_BATCH_NEGATIVE_CACHE_TTL_SECONDS = 5 * 60
_GOOGLE_NEWS_RATE_LIMIT_RPS = 1.5
_GOOGLE_NEWS_RATE_LIMIT_INTERVAL_SECONDS = 1.0 / _GOOGLE_NEWS_RATE_LIMIT_RPS
_GOOGLE_NEWS_BACKOFF_BASE_SECONDS = 2.0
_GOOGLE_NEWS_BACKOFF_MAX_SECONDS = 120.0
_GOOGLE_NEWS_NETWORK_NEXT_AT = 0.0
_GOOGLE_NEWS_BACKOFF_FAILURES = 0
_GOOGLE_NEWS_CIRCUIT_OPEN_UNTIL = 0.0
_GOOGLE_NEWS_BATCH_GUARD_LOCK = threading.Lock()


@dataclass(slots=True)
class UrlUnwrapResult:
    url: str
    changed: bool
    steps: list[str]


@dataclass(slots=True)
class UrlUnwrapAdapter:
    name: str
    applies: Callable[[ParseResult], bool]
    unwrap: Callable[[str, ParseResult], tuple[str, bool]]


@dataclass(slots=True)
class GoogleNewsDecodeResult:
    url: str
    changed: bool
    reason: str
    retryable: bool


def _safe_url(raw: str | None) -> str:
    candidate = str(raw or "").strip()
    if candidate.startswith(("http://", "https://")):
        return candidate
    return ""


def _normalize_no_fragment(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, ""))


def _extract_first_http_url(text: str) -> str:
    if not text:
        return ""
    match = _HTTP_URL_IN_TEXT_RE.search(text)
    if not match:
        return ""
    return _safe_url(match.group(0))


def _clean_tracking_query(url: str) -> tuple[str, bool]:
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    cleaned_pairs = [(k, v) for k, v in pairs if str(k or "").strip().lower() not in _TRACKING_QUERY_KEYS]
    changed = cleaned_pairs != pairs
    if not changed:
        return url, False
    query = urlencode(cleaned_pairs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment)), True


def _decode_wrapped_query_url(url: str) -> tuple[str, bool]:
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query or "", keep_blank_values=True)
    for key, value in pairs:
        lowered = str(key or "").strip().lower()
        if lowered not in _WRAPPED_URL_QUERY_KEYS:
            continue
        decoded = unquote(str(value or "").strip())
        decoded_url = _safe_url(decoded)
        if decoded_url:
            return decoded_url, True
        # Base64-url encoded destination is common on some wrappers.
        try:
            padded = decoded + "=" * ((4 - len(decoded) % 4) % 4)
            raw_bytes = base64.urlsafe_b64decode(padded.encode("utf-8"))
            b64_decoded = _safe_url(raw_bytes.decode("utf-8", errors="ignore"))
            if b64_decoded:
                return b64_decoded, True
        except Exception:
            continue
    return url, False


def _google_news_token_candidates(parsed: ParseResult) -> list[str]:
    parts = [p for p in str(parsed.path or "").split("/") if p]
    if len(parts) < 2:
        return []
    if parts[0] not in {"articles", "read", "rss"}:
        return []
    if parts[0] == "rss" and len(parts) >= 3 and parts[1] == "articles":
        return [parts[2]]
    return [parts[-1]]


def _decode_google_news_token(url: str, parsed: ParseResult) -> tuple[str, bool]:
    host = str(parsed.netloc or "").lower()
    if host != "news.google.com":
        return url, False
    for token in _google_news_token_candidates(parsed):
        if not token:
            continue
        for raw in (token, unquote(token)):
            for candidate in (raw, raw + "=" * ((4 - len(raw) % 4) % 4)):
                try:
                    decoded = base64.urlsafe_b64decode(candidate.encode("utf-8")).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                embedded_url = _extract_first_http_url(decoded)
                if embedded_url:
                    return embedded_url, True
    return url, False


def _decode_google_news_batch_execute(url: str) -> tuple[str, bool]:
    parsed = urlparse(url)
    if not _is_google_news_url(parsed):
        return url, False

    token_candidates = _google_news_token_candidates(parsed)
    if not token_candidates:
        return url, False
    gn_art_id = str(token_candidates[0] or "").strip()
    if not gn_art_id:
        return url, False

    cached = _google_news_batch_cache_get(gn_art_id)
    if cached is not None:
        if cached:
            return cached, cached != url
        return url, False

    if not _google_news_batch_acquire_network_slot():
        _google_news_batch_cache_put_negative(gn_art_id)
        return url, False

    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://news.google.com/"}
    try:
        response = requests.get(
            f"https://news.google.com/articles/{gn_art_id}",
            timeout=8.0,
            headers=headers,
        )
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code in {403, 429}:
            _google_news_batch_record_throttle()
            _google_news_batch_cache_put_negative(gn_art_id)
            return url, False
        if status_code >= 400:
            _google_news_batch_cache_put_negative(gn_art_id)
            return url, False
        article_html = str(getattr(response, "text", "") or "")
    except Exception:
        _google_news_batch_cache_put_negative(gn_art_id)
        return url, False
    _google_news_batch_record_success()

    sig_match = _GOOGLE_NEWS_SIG_RE.search(article_html)
    ts_match = _GOOGLE_NEWS_TS_RE.search(article_html)
    if sig_match is None or ts_match is None:
        _google_news_batch_cache_put_negative(gn_art_id)
        return url, False

    signature = html.unescape(str(sig_match.group(1) or sig_match.group(2) or "").strip())
    timestamp = str(ts_match.group(1) or ts_match.group(2) or "").strip()
    if not signature or not timestamp.isdigit():
        _google_news_batch_cache_put_negative(gn_art_id)
        return url, False

    # Community-proven batchexecute payload for RSS/read article-id to source URL resolution.
    inner = (
        '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
        '"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
        f'"{gn_art_id}",{int(timestamp)},"{signature}"]'
    )
    escaped_inner = inner.replace('"', '\\"')
    f_req = '[[["Fbv4je","' + escaped_inner + '",null,"generic"]]]'
    if not _google_news_batch_acquire_network_slot():
        _google_news_batch_cache_put_negative(gn_art_id)
        return url, False
    try:
        batch_response = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                "Referer": "https://news.google.com/",
                "User-Agent": "Mozilla/5.0",
            },
            data={"f.req": f_req},
            timeout=8.0,
        )
        status_code = int(getattr(batch_response, "status_code", 0) or 0)
        if status_code in {403, 429}:
            _google_news_batch_record_throttle()
            _google_news_batch_cache_put_negative(gn_art_id)
            return url, False
        if status_code >= 400:
            _google_news_batch_cache_put_negative(gn_art_id)
            return url, False
    except Exception:
        _google_news_batch_cache_put_negative(gn_art_id)
        return url, False
    _google_news_batch_record_success()

    payload = str(getattr(batch_response, "text", "") or "")
    match = None
    for pattern in _GOOGLE_NEWS_BATCH_RESULT_RES:
        match = pattern.search(payload)
        if match is not None:
            break
    if match is None:
        _google_news_batch_cache_put_negative(gn_art_id)
        return url, False

    decoded = html.unescape(str(match.group(1) or "").strip().replace("\\/", "/"))
    decoded_url = _safe_url(decoded)
    if not decoded_url:
        _google_news_batch_cache_put_negative(gn_art_id)
        return url, False
    if not _is_safe_redirect_target(decoded_url):
        _google_news_batch_cache_put_negative(gn_art_id)
        return url, False
    if decoded_url == url:
        _google_news_batch_cache_put_negative(gn_art_id)
        return url, False
    _google_news_batch_cache_put(gn_art_id, decoded_url)
    return decoded_url, True


def _decode_google_news_batch_execute_diagnostic(url: str) -> GoogleNewsDecodeResult:
    parsed = urlparse(url)
    if not _is_google_news_url(parsed):
        return GoogleNewsDecodeResult(url=url, changed=False, reason="not_google_news_url", retryable=False)

    token_candidates = _google_news_token_candidates(parsed)
    if not token_candidates:
        return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_missing_token", retryable=False)
    gn_art_id = str(token_candidates[0] or "").strip()
    if not gn_art_id:
        return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_missing_token", retryable=False)

    cached = _google_news_batch_cache_get(gn_art_id)
    if cached is not None:
        if cached:
            return GoogleNewsDecodeResult(url=cached, changed=cached != url, reason="ok", retryable=False)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_negative_cached", retryable=True)

    if not _google_news_batch_acquire_network_slot():
        _google_news_batch_cache_put_negative(gn_art_id)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="rate_limited", retryable=True)

    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://news.google.com/"}
    try:
        response = requests.get(
            f"https://news.google.com/articles/{gn_art_id}",
            timeout=8.0,
            headers=headers,
        )
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code in {403, 429}:
            _google_news_batch_record_throttle()
            _google_news_batch_cache_put_negative(gn_art_id)
            return GoogleNewsDecodeResult(url=url, changed=False, reason="rate_limited", retryable=True)
        if status_code >= 500:
            _google_news_batch_cache_put_negative(gn_art_id)
            return GoogleNewsDecodeResult(url=url, changed=False, reason="fetch_failed", retryable=True)
        if status_code >= 400:
            _google_news_batch_cache_put_negative(gn_art_id)
            return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_article_http_error", retryable=False)
        article_html = str(getattr(response, "text", "") or "")
    except Exception:
        _google_news_batch_cache_put_negative(gn_art_id)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="fetch_failed", retryable=True)
    _google_news_batch_record_success()

    sig_match = _GOOGLE_NEWS_SIG_RE.search(article_html)
    ts_match = _GOOGLE_NEWS_TS_RE.search(article_html)
    if sig_match is None or ts_match is None:
        _google_news_batch_cache_put_negative(gn_art_id)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_missing_signature", retryable=False)

    signature = html.unescape(str(sig_match.group(1) or sig_match.group(2) or "").strip())
    timestamp = str(ts_match.group(1) or ts_match.group(2) or "").strip()
    if not signature or not timestamp.isdigit():
        _google_news_batch_cache_put_negative(gn_art_id)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_invalid_signature", retryable=False)

    inner = (
        '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
        '"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
        f'"{gn_art_id}",{int(timestamp)},"{signature}"]'
    )
    escaped_inner = inner.replace('"', '\\"')
    f_req = '[[["Fbv4je","' + escaped_inner + '",null,"generic"]]]'
    if not _google_news_batch_acquire_network_slot():
        _google_news_batch_cache_put_negative(gn_art_id)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="rate_limited", retryable=True)
    try:
        batch_response = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                "Referer": "https://news.google.com/",
                "User-Agent": "Mozilla/5.0",
            },
            data={"f.req": f_req},
            timeout=8.0,
        )
        status_code = int(getattr(batch_response, "status_code", 0) or 0)
        if status_code in {403, 429}:
            _google_news_batch_record_throttle()
            _google_news_batch_cache_put_negative(gn_art_id)
            return GoogleNewsDecodeResult(url=url, changed=False, reason="rate_limited", retryable=True)
        if status_code >= 500:
            _google_news_batch_cache_put_negative(gn_art_id)
            return GoogleNewsDecodeResult(url=url, changed=False, reason="fetch_failed", retryable=True)
        if status_code >= 400:
            _google_news_batch_cache_put_negative(gn_art_id)
            return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_batch_http_error", retryable=False)
    except Exception:
        _google_news_batch_cache_put_negative(gn_art_id)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="fetch_failed", retryable=True)
    _google_news_batch_record_success()

    payload = str(getattr(batch_response, "text", "") or "")
    match = None
    for pattern in _GOOGLE_NEWS_BATCH_RESULT_RES:
        match = pattern.search(payload)
        if match is not None:
            break
    if match is None:
        _google_news_batch_cache_put_negative(gn_art_id)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_batch_parse_failed", retryable=False)

    decoded = html.unescape(str(match.group(1) or "").strip().replace("\\/", "/"))
    decoded_url = _safe_url(decoded)
    if not decoded_url:
        _google_news_batch_cache_put_negative(gn_art_id)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_batch_parse_failed", retryable=False)
    if not _is_safe_redirect_target(decoded_url):
        _google_news_batch_cache_put_negative(gn_art_id)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_unsafe_redirect_target", retryable=False)
    if decoded_url == url:
        _google_news_batch_cache_put_negative(gn_art_id)
        return GoogleNewsDecodeResult(url=url, changed=False, reason="google_news_decode_unchanged", retryable=False)
    _google_news_batch_cache_put(gn_art_id, decoded_url)
    return GoogleNewsDecodeResult(url=decoded_url, changed=True, reason="ok", retryable=False)


def _google_news_batch_cache_get(gn_art_id: str) -> str | None:
    now = time.monotonic()
    with _GOOGLE_NEWS_BATCH_GUARD_LOCK:
        negative_expires_at = _GOOGLE_NEWS_BATCH_NEGATIVE_CACHE_EXPIRES_AT.get(gn_art_id)
        if negative_expires_at is not None:
            if negative_expires_at > now:
                return ""
            _GOOGLE_NEWS_BATCH_NEGATIVE_CACHE_EXPIRES_AT.pop(gn_art_id, None)

        cached = _GOOGLE_NEWS_BATCH_CACHE.get(gn_art_id)
        if not cached:
            return None

        expires_at = _GOOGLE_NEWS_BATCH_CACHE_EXPIRES_AT.get(gn_art_id)
        if expires_at is None:
            _GOOGLE_NEWS_BATCH_CACHE_EXPIRES_AT[gn_art_id] = now + _GOOGLE_NEWS_BATCH_CACHE_TTL_SECONDS
            return cached
        if expires_at <= now:
            _GOOGLE_NEWS_BATCH_CACHE.pop(gn_art_id, None)
            _GOOGLE_NEWS_BATCH_CACHE_EXPIRES_AT.pop(gn_art_id, None)
            return None
        return cached


def _google_news_batch_cache_put(gn_art_id: str, publisher_url: str) -> None:
    now = time.monotonic()
    with _GOOGLE_NEWS_BATCH_GUARD_LOCK:
        _GOOGLE_NEWS_BATCH_CACHE[gn_art_id] = publisher_url
        _GOOGLE_NEWS_BATCH_CACHE_EXPIRES_AT[gn_art_id] = now + _GOOGLE_NEWS_BATCH_CACHE_TTL_SECONDS
        _GOOGLE_NEWS_BATCH_NEGATIVE_CACHE_EXPIRES_AT.pop(gn_art_id, None)


def _google_news_batch_cache_put_negative(gn_art_id: str) -> None:
    now = time.monotonic()
    with _GOOGLE_NEWS_BATCH_GUARD_LOCK:
        _GOOGLE_NEWS_BATCH_CACHE.pop(gn_art_id, None)
        _GOOGLE_NEWS_BATCH_CACHE_EXPIRES_AT.pop(gn_art_id, None)
        _GOOGLE_NEWS_BATCH_NEGATIVE_CACHE_EXPIRES_AT[gn_art_id] = now + _GOOGLE_NEWS_BATCH_NEGATIVE_CACHE_TTL_SECONDS


def _google_news_batch_acquire_network_slot() -> bool:
    global _GOOGLE_NEWS_NETWORK_NEXT_AT
    now = time.monotonic()
    with _GOOGLE_NEWS_BATCH_GUARD_LOCK:
        if now < _GOOGLE_NEWS_CIRCUIT_OPEN_UNTIL:
            return False
        scheduled = max(now, _GOOGLE_NEWS_NETWORK_NEXT_AT)
        _GOOGLE_NEWS_NETWORK_NEXT_AT = scheduled + _GOOGLE_NEWS_RATE_LIMIT_INTERVAL_SECONDS
    wait_seconds = max(0.0, scheduled - now)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    return True


def _google_news_batch_record_throttle() -> None:
    global _GOOGLE_NEWS_BACKOFF_FAILURES, _GOOGLE_NEWS_CIRCUIT_OPEN_UNTIL
    now = time.monotonic()
    with _GOOGLE_NEWS_BATCH_GUARD_LOCK:
        _GOOGLE_NEWS_BACKOFF_FAILURES += 1
        delay = min(
            _GOOGLE_NEWS_BACKOFF_MAX_SECONDS,
            _GOOGLE_NEWS_BACKOFF_BASE_SECONDS * (2 ** (_GOOGLE_NEWS_BACKOFF_FAILURES - 1)),
        )
        _GOOGLE_NEWS_CIRCUIT_OPEN_UNTIL = max(_GOOGLE_NEWS_CIRCUIT_OPEN_UNTIL, now + delay)


def _google_news_batch_record_success() -> None:
    global _GOOGLE_NEWS_BACKOFF_FAILURES
    with _GOOGLE_NEWS_BATCH_GUARD_LOCK:
        _GOOGLE_NEWS_BACKOFF_FAILURES = 0


def _apply_query_wrapper(url: str, _parsed: ParseResult) -> tuple[str, bool]:
    return _decode_wrapped_query_url(url)


def _is_google_news_url(parsed: ParseResult) -> bool:
    host = str(parsed.netloc or "").lower()
    if host != "news.google.com":
        return False
    path = str(parsed.path or "")
    return path.startswith("/articles/") or path.startswith("/rss/articles/") or path.startswith("/read/")


def _has_wrapped_query(parsed: ParseResult) -> bool:
    for key, _ in parse_qsl(parsed.query or "", keep_blank_values=True):
        if str(key or "").strip().lower() in _WRAPPED_URL_QUERY_KEYS:
            return True
    return False


_UNWRAP_ADAPTER_POOL: tuple[UrlUnwrapAdapter, ...] = (
    UrlUnwrapAdapter(
        name="query_wrapped_url",
        applies=_has_wrapped_query,
        unwrap=_apply_query_wrapper,
    ),
    UrlUnwrapAdapter(
        name="google_news_token",
        applies=_is_google_news_url,
        unwrap=_decode_google_news_token,
    ),
)


def list_unwrap_adapters() -> list[str]:
    return [adapter.name for adapter in _UNWRAP_ADAPTER_POOL]


def _apply_adapter_pool(url: str) -> tuple[str, list[str]]:
    current = _safe_url(url)
    if not current:
        return str(url or ""), []

    applied_steps: list[str] = []
    for _ in range(3):
        parsed = urlparse(current)
        changed = False
        for adapter in _UNWRAP_ADAPTER_POOL:
            if not adapter.applies(parsed):
                continue
            next_url, did_change = adapter.unwrap(current, parsed)
            normalized_next = _safe_url(next_url)
            if not did_change or not normalized_next or normalized_next == current:
                continue
            current = normalized_next
            applied_steps.append(adapter.name)
            changed = True
            break
        if not changed:
            break
    return current, applied_steps


def decode_google_news_url_for_dispatch(url: str) -> dict[str, Any]:
    original = str(url or "").strip()
    current = _safe_url(original)
    if not current:
        return {"url": original, "changed": False, "reason": "invalid_url", "retryable": False}

    pooled_url, _ = _apply_adapter_pool(current)
    current = _safe_url(pooled_url) or current

    cleaned, _ = _clean_tracking_query(current)
    current = cleaned
    current = _normalize_no_fragment(current)

    parsed = urlparse(current)
    if not _is_google_news_url(parsed):
        return {"url": current, "changed": current != original, "reason": "ok", "retryable": False}

    diag = _decode_google_news_batch_execute_diagnostic(current)
    final_url = _safe_url(diag.url) or current
    return {
        "url": final_url,
        "changed": bool(diag.changed),
        "reason": str(diag.reason or "google_news_decode_failed"),
        "retryable": bool(diag.retryable),
    }


def _resolve_http_redirect(url: str, *, timeout_seconds: float = 6.0) -> tuple[str, bool]:
    try:
        response = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout_seconds,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except Exception:
        return url, False
    final_url = _safe_url(getattr(response, "url", None))
    if final_url and not _is_safe_redirect_target(final_url):
        return url, False
    if final_url and final_url != url:
        return final_url, True
    return url, False


def _is_safe_redirect_target(url: str) -> bool:
    parsed = urlparse(url)
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return False

    def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except OSError:
            return True
        resolved_ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        for info in infos:
            sockaddr = info[4]
            if not sockaddr:
                continue
            raw_ip = str(sockaddr[0] or "").strip()
            if not raw_ip:
                continue
            try:
                resolved_ips.add(ipaddress.ip_address(raw_ip))
            except ValueError:
                continue
        if not resolved_ips:
            return True
        return not any(_is_unsafe_ip(resolved_ip) for resolved_ip in resolved_ips)
    return not _is_unsafe_ip(ip)


def unwrap_url(
    url: str,
    *,
    enable_network_redirect: bool = True,
    max_steps: int = 3,
) -> UrlUnwrapResult:
    current = _safe_url(url)
    if not current:
        return UrlUnwrapResult(url=str(url or ""), changed=False, steps=[])

    steps: list[str] = []
    for _ in range(max(1, int(max_steps))):
        changed = False

        pooled_url, pooled_steps = _apply_adapter_pool(current)
        if pooled_steps and pooled_url != current:
            current = pooled_url
            steps.extend(pooled_steps)
            changed = True

        cleaned, cleaned_changed = _clean_tracking_query(current)
        if cleaned_changed:
            current = cleaned
            steps.append("strip_tracking_query")
            changed = True

        normalized = _normalize_no_fragment(current)
        if normalized != current:
            current = normalized
            steps.append("strip_fragment")
            changed = True

        if enable_network_redirect:
            batch_decoded, batch_changed = _decode_google_news_batch_execute(current)
            if batch_changed:
                current = batch_decoded
                steps.append("google_news_batch_execute")
                changed = True

        if enable_network_redirect:
            redirected, redirected_changed = _resolve_http_redirect(current)
            if redirected_changed:
                current = redirected
                steps.append("http_redirect")
                changed = True

        if not changed:
            break

    return UrlUnwrapResult(url=current, changed=bool(steps), steps=steps)


def unwrap_urls(urls: Iterable[str], *, enable_network_redirect: bool = True) -> tuple[list[str], dict[str, UrlUnwrapResult]]:
    out: list[str] = []
    trace: dict[str, UrlUnwrapResult] = {}
    seen: set[str] = set()
    for raw in urls:
        original = str(raw or "").strip()
        if not original:
            continue
        result = unwrap_url(original, enable_network_redirect=enable_network_redirect)
        final = _safe_url(result.url) or original
        trace[original] = result
        if final in seen:
            continue
        seen.add(final)
        out.append(final)
    return out, trace


__all__ = [
    "GoogleNewsDecodeResult",
    "UrlUnwrapAdapter",
    "UrlUnwrapResult",
    "decode_google_news_url_for_dispatch",
    "list_unwrap_adapters",
    "unwrap_url",
    "unwrap_urls",
]
