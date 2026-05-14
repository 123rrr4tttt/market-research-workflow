#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError


DEFAULT_KEYWORDS = [
    "embodied ai supply chain",
    "robotics policy",
    "humanoid robot market size",
    "robot foundation model survey",
    "具身智能 政策",
    "embodied intelligence industrial policy",
    "robotics national strategy",
    "humanoid robotics investment",
    "physical ai manufacturing",
    "embodied ai safety standards",
    "robot learning foundation models",
    "具身智能 产业链",
    "robotics regulation united states",
    "china humanoid robot policy",
    "industrial robot adoption report",
    "embodied ai venture funding",
    "robotics workforce automation policy",
    "multimodal robot policy",
    "embodied ai benchmark",
    "robotics supply chain semiconductor",
]


def fetch_json(url: str, params: dict[str, object], timeout: int) -> tuple[dict | None, str | None, str | None]:
    request_url = f"{url}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(request_url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace")), None, None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return None, exc.__class__.__name__, f"{exc}; {body}"
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, exc.__class__.__name__, str(exc)


def normalize_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw
    tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "gclid", "fbclid"}
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if k.lower() not in tracking]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urllib.parse.urlencode(query), ""))


def fetch_searxng(keyword: str, *, base_url: str, limit: int, max_pages: int, timeout: int) -> tuple[list[dict], str | None, str | None]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "search")
    desired_pages = max(1, min(max_pages, math.ceil(max(1, limit) / 10)))
    rows: list[dict] = []
    for page_no in range(1, desired_pages + 1):
        data, error_type, error = fetch_json(
            url,
            {"q": keyword, "format": "json", "language": "en", "pageno": page_no},
            timeout,
        )
        if data is None:
            return rows, error_type, error
        page_rows = list(data.get("results") or [])
        if not page_rows:
            break
        for row in page_rows:
            if not isinstance(row, dict):
                continue
            link = normalize_url(row.get("url") or row.get("link"))
            rows.append(
                {
                    "rank": len(rows) + 1,
                    "title": row.get("title"),
                    "link": link,
                    "snippet": row.get("content") or row.get("snippet") or row.get("description"),
                    "source": "searxng",
                    "raw": {
                        "engine": row.get("engine"),
                        "engines": row.get("engines"),
                        "category": row.get("category"),
                        "pageno": page_no,
                    },
                }
            )
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    return rows, None, None


def row_for_keyword(keyword: str, *, base_url: str, limit: int, max_pages: int, timeout: int) -> dict:
    started = time.perf_counter()
    results, error_type, error = fetch_searxng(keyword, base_url=base_url, limit=limit, max_pages=max_pages, timeout=timeout)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    links = [r.get("link") for r in results if r.get("link")]
    counts = Counter(links)
    domains = {
        urllib.parse.urlparse(link).netloc.lower()
        for link in links
        if urllib.parse.urlparse(link).netloc
    }
    usable_url_count = sum(1 for r in results if r.get("title") and r.get("link"))
    return {
        "provider": "searxng",
        "keyword": keyword,
        "ok": error_type is None,
        "requested_limit": limit,
        "result_count": len(results),
        "unique_domain_count": len(domains),
        "usable_url_count": usable_url_count,
        "duplicate_url_count": sum(count - 1 for count in counts.values() if count > 1),
        "latency_ms": latency_ms,
        "error_type": error_type,
        "error": error,
        "results": results,
    }


def write_summary(rows: list[dict], out_path: Path) -> None:
    latencies = [float(r["latency_ms"]) for r in rows if r.get("ok")]
    result_counts = [int(r["result_count"]) for r in rows]
    empty_count = sum(1 for r in rows if not r.get("result_count"))
    p50 = statistics.median(latencies) if latencies else None
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else (max(latencies) if latencies else None)
    ok_count = sum(1 for r in rows if r.get("ok"))
    lines = [
        "# SearXNG External Search Benchmark Summary",
        "",
        "## Scope",
        "",
        "- Provider: `searxng`",
        "- Purpose: external web discovery pipeline benchmark.",
        "- Boundary: does not modify `source_library`; source_library remains a specific source database.",
        "",
        "## Aggregate",
        "",
        f"- Queries: {len(rows)}",
        f"- Successful queries: {ok_count}",
        f"- Empty-result queries: {empty_count}",
        f"- Empty rate: {round(empty_count / max(1, len(rows)), 3)}",
        f"- Result count min/median/max: {min(result_counts) if result_counts else 0} / {statistics.median(result_counts) if result_counts else 0} / {max(result_counts) if result_counts else 0}",
        f"- Latency p50 ms: {round(p50, 2) if p50 is not None else 'n/a'}",
        f"- Latency p95 ms: {round(p95, 2) if p95 is not None else 'n/a'}",
        "",
        "## Gate Read",
        "",
        "- `max_results=30` benchmark is the evidence target for expanded SearXNG retrieval.",
        "- `precision@10` still requires manual review; this run records machine metrics and candidate results for review.",
        "- Recommendation: keep SearXNG as an explicit external-search provider until manual precision and larger stability runs pass.",
        "",
        "## Per Query",
        "",
        "| keyword | ok | result_count | usable_url_count | unique_domain_count | duplicate_url_count | latency_ms | error_type |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {keyword} | {ok} | {result_count} | {usable_url_count} | {unique_domain_count} | {duplicate_url_count} | {latency_ms} | {error_type} |".format(
                keyword=str(row["keyword"]).replace("|", "\\|"),
                ok=str(row["ok"]).lower(),
                result_count=row["result_count"],
                usable_url_count=row["usable_url_count"],
                unique_domain_count=row["unique_domain_count"],
                duplicate_url_count=row["duplicate_url_count"],
                latency_ms=row["latency_ms"],
                error_type=row["error_type"] or "",
            )
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", nargs="*", default=DEFAULT_KEYWORDS)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("SEARXNG_MAX_PAGES", "5")))
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--base-url", default=os.getenv("SEARXNG_BASE_URL", "http://127.0.0.1:8088"))
    parser.add_argument("--out-dir", default="development/latest-dev-docs/automation-runs/search-provider-benchmark/2026-05-14")
    args = parser.parse_args()

    if len(args.keywords) < 20:
        raise SystemExit("at least 20 keywords are required for this benchmark")
    max_pages = max(1, min(10, args.max_pages))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        row_for_keyword(keyword, base_url=args.base_url, limit=args.limit, max_pages=max_pages, timeout=args.timeout)
        for keyword in args.keywords
    ]

    jsonl_path = out_dir / "searxng_benchmark.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    readme = out_dir / "README.md"
    readme.write_text(
        "# Search Provider Benchmark\n\n"
        "This run benchmarks SearXNG as an explicit external web discovery provider. "
        "It does not modify or reinterpret `source_library`.\n\n"
        f"- Provider: searxng\n- Requested limit: {args.limit}\n- Max pages: {max_pages}\n- Query count: {len(rows)}\n",
        encoding="utf-8",
    )
    write_summary(rows, out_dir / "searxng_benchmark_summary.md")
    print(json.dumps({"out_dir": str(out_dir), "rows": len(rows), "ok": sum(1 for r in rows if r["ok"])}, ensure_ascii=False))
    return 0 if any(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
