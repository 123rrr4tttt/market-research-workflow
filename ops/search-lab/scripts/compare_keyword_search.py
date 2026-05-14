#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError


def fetch_json(url: str, *, params: dict | None = None, headers: dict | None = None, timeout: int = 20) -> tuple[dict | None, str | None, str | None]:
    request_url = url
    if params:
        request_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(request_url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace")), None, None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return None, exc.__class__.__name__, f"{exc}; {body}"
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, exc.__class__.__name__, str(exc)


def fetch_serper(keyword: str, limit: int) -> tuple[list[dict], str | None, str | None]:
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return [], "MissingConfig", "SERPER_API_KEY is not configured"
    payload = json.dumps({"q": keyword, "num": limit, "hl": "en"}).encode("utf-8")
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=payload,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except HTTPError as exc:
        return [], exc.__class__.__name__, str(exc)
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [], exc.__class__.__name__, str(exc)
    rows = []
    for rank, row in enumerate((data.get("organic") or [])[:limit], start=1):
        rows.append({
            "rank": rank,
            "title": row.get("title"),
            "link": row.get("link"),
            "snippet": row.get("snippet") or row.get("description"),
            "source": "serper",
        })
    return rows, None, None


def fetch_searxng(keyword: str, limit: int) -> tuple[list[dict], str | None, str | None]:
    base_url = os.getenv("SEARXNG_BASE_URL", "http://127.0.0.1:8088").rstrip("/")
    rows = []
    try:
        max_pages = max(1, min(10, int(os.getenv("SEARXNG_MAX_PAGES", "5"))))
    except ValueError:
        max_pages = 5
    desired_pages = max(1, min(max_pages, math.ceil(max(1, limit) / 10)))
    for page_no in range(1, desired_pages + 1):
        data, error_type, error = fetch_json(
            f"{base_url}/search",
            params={"q": keyword, "format": "json", "language": "en", "pageno": page_no},
        )
        if data is None:
            return rows, error_type, error
        page_rows = list(data.get("results") or [])
        if not page_rows:
            break
        for row in page_rows:
            rows.append({
                "rank": len(rows) + 1,
                "title": row.get("title"),
                "link": row.get("url") or row.get("link"),
                "snippet": row.get("content") or row.get("snippet"),
                "source": "searxng",
                "raw": {"engine": row.get("engine"), "engines": row.get("engines"), "pageno": page_no},
            })
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    return rows, None, None


def fetch_yacy(keyword: str, limit: int) -> tuple[list[dict], str | None, str | None]:
    base_url = os.getenv("YACY_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
    resource = os.getenv("YACY_RESOURCE_MODE", "local")
    data, error_type, error = fetch_json(
        f"{base_url}/yacysearch.json",
        params={"query": keyword, "resource": resource, "maximumRecords": limit, "urlmaskfilter": ".*", "prefermaskfilter": "", "nav": "none"},
    )
    if data is None:
        return [], error_type, error
    rows = []
    items = []
    channels = data.get("channels")
    if isinstance(channels, list) and channels and isinstance(channels[0], dict):
        items = list(channels[0].get("items") or channels[0].get("results") or [])
    if not items:
        items = list(data.get("items") or data.get("results") or [])
    for rank, row in enumerate(items[:limit], start=1):
        if isinstance(row, dict):
            rows.append({
                "rank": rank,
                "title": row.get("title"),
                "link": row.get("link") or row.get("url"),
                "snippet": row.get("description") or row.get("snippet"),
                "source": "yacy",
                "raw": {"resource": resource, "origin": row.get("publisher") or row.get("host")},
            })
    return rows, None, None


FETCHERS = {
    "serper": fetch_serper,
    "searxng": fetch_searxng,
    "yacy": fetch_yacy,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", nargs="+", required=True)
    parser.add_argument("--providers", default="serper,searxng,yacy")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    unknown = [p for p in providers if p not in FETCHERS]
    if unknown:
        raise SystemExit(f"unknown provider(s): {', '.join(unknown)}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for keyword in args.keywords:
            for provider in providers:
                started = time.perf_counter()
                results, error_type, error = FETCHERS[provider](keyword, args.limit)
                row = {
                    "provider": provider,
                    "keyword": keyword,
                    "ok": error_type is None,
                    "result_count": len(results),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "error_type": error_type,
                    "error": error,
                    "results": results,
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
