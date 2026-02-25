from __future__ import annotations

import random
import time
from typing import Any, Mapping

import requests
from requests import Response
from selectolax.parser import HTMLParser


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


class HttpFetchError(RuntimeError):
    """Raised when HTTP fetching fails after retries."""


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
    for attempt in range(max(retries, 1)):
        try:
            response = session.get(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=timeout,
                allow_redirects=True,
            )
        except requests.RequestException as exc:  # pragma: no cover - network issues
            last_exc = exc
        else:
            # Some lottery sites return branded HTML pages for certain errors. Treat
            # 4xx as fatal but retry on transient 5xx.
            if response.status_code >= 500:
                last_exc = HttpFetchError(
                    f"{response.status_code} received from {url}"
                )
            else:
                try:
                    response.raise_for_status()
                except requests.HTTPError as exc:  # pragma: no cover - unlikely
                    raise HttpFetchError(str(exc)) from exc
                return response.text, response

        # Exponential backoff with jitter
        sleep_for = backoff ** attempt + random.uniform(0, 0.3)
        time.sleep(sleep_for)

    raise HttpFetchError(f"Failed to fetch {url}") from last_exc


def make_html_parser(html: str) -> HTMLParser:
    """Create a Selectolax parser from raw HTML."""

    return HTMLParser(html)


