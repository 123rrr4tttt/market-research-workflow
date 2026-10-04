from __future__ import annotations

import random
import time
from collections.abc import Mapping
from typing import Any

import requests
from requests import Response

from app.services.resource_pool.http_port import (
    HttpFetchError,
    HttpFetchFailureReason,
    make_html_parser,
)


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

_SESSION = requests.Session()
_SESSION.headers.update(DEFAULT_HEADERS)


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
    """Fetch HTML content with light retry/backoff handling."""

    session = _SESSION
    last_exc: Exception | None = None
    
    # 合并headers：用户提供的headers优先
    request_headers = dict(DEFAULT_HEADERS)
    if headers:
        request_headers.update(headers)
    
    # 对于Reddit API，清除可能存在的cookies，避免被识别为机器人
    # 创建临时session用于请求，避免污染全局session
    temp_session = requests.Session()
    temp_session.headers.update(request_headers)
    if cookies:
        temp_session.cookies.update(cookies)
    
    for attempt in range(max(retries, 1)):
        try:
            response = temp_session.get(
                url,
                params=params,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.RequestException as exc:  # pragma: no cover - network issues
            last_exc = exc
        else:
            # Some provider sites return branded HTML pages for certain errors. Treat
            # 4xx as fatal but retry on transient 5xx.
            if response.status_code >= 500:
                last_exc = HttpFetchError(
                    f"{response.status_code} received from {url}",
                    reason=HttpFetchFailureReason.HTTP_STATUS,
                    url=url,
                    status_code=int(response.status_code),
                    retryable=True,
                )
            else:
                try:
                    response.raise_for_status()
                except requests.HTTPError as exc:  # pragma: no cover - unlikely
                    raise HttpFetchError(
                        str(exc),
                        reason=HttpFetchFailureReason.HTTP_STATUS,
                        url=url,
                        status_code=int(response.status_code),
                        retryable=False,
                    ) from exc
                return response.text, response

        # Exponential backoff with jitter
        sleep_for = backoff ** attempt + random.uniform(0, 0.3)
        time.sleep(sleep_for)

    if isinstance(last_exc, HttpFetchError):
        raise last_exc

    raise HttpFetchError(
        f"Failed to fetch {url}",
        reason=HttpFetchFailureReason.TRANSPORT,
        url=url,
    ) from last_exc


__all__ = ["HttpFetchError", "fetch_html", "make_html_parser"]
