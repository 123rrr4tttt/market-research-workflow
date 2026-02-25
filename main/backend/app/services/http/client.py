from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, Optional

import httpx


logger = logging.getLogger(__name__)


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float = 20.0,
        max_retries: int = 2,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.Client(
            timeout=timeout,
            proxies=self._build_proxies(),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
                )
            },
        )

    @staticmethod
    def _build_proxies() -> Optional[Dict[str, str]]:
        http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
        proxies: Dict[str, str] = {}
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy
        return proxies or None

    def get_json(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.get(url, params=params, **kwargs)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "http.get_json failed url=%s attempt=%d err=%s", url, attempt, exc
                )
                time.sleep(min(2 ** attempt, 3))
        raise last_exc  # type: ignore[misc]

    def get_text(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.get(url, params=params, **kwargs)
                resp.raise_for_status()
                return resp.text
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "http.get_text failed url=%s attempt=%d err=%s", url, attempt, exc
                )
                time.sleep(min(2 ** attempt, 3))
        raise last_exc  # type: ignore[misc]


default_http_client = HttpClient()


