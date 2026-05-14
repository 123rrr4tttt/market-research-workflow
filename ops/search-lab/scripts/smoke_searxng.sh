#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${SEARXNG_BASE_URL:-http://127.0.0.1:8088}"
OUT_DIR="${SEARCH_LAB_OUT_DIR:-development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14}"
mkdir -p "$OUT_DIR"

python3 - "$BASE_URL" "$OUT_DIR/searxng_smoke.json" <<'PY'
import json
import sys
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

base_url = sys.argv[1].rstrip("/")
out_path = sys.argv[2]
query = "embodied ai"


def fetch(url, timeout=12):
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "ok": 200 <= resp.status < 300,
                "status": resp.status,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "body": body,
                "error_type": None,
                "error": None,
            }
    except HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "body": exc.read().decode("utf-8", errors="replace"),
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
    except URLError as exc:
        return {
            "ok": False,
            "status": None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "body": "",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }


root = fetch(base_url + "/")
search_url = f"{base_url}/search?{urllib.parse.urlencode({'q': query, 'format': 'json', 'language': 'en', 'pageno': 1})}"
search = fetch(search_url)
results = []
parse_error = None
if search["body"]:
    try:
        payload = json.loads(search["body"])
        for item in payload.get("results", []):
            if item.get("title") and (item.get("url") or item.get("link")):
                results.append({
                    "title": item.get("title"),
                    "link": item.get("url") or item.get("link"),
                    "engine": item.get("engine"),
                })
    except Exception as exc:
        parse_error = exc.__class__.__name__

report = {
    "provider": "searxng",
    "base_url": base_url,
    "query": query,
    "root_status": root["status"],
    "search_status": search["status"],
    "ok": bool(root["ok"] and search["ok"] and not parse_error),
    "result_count": len(results),
    "latency_ms": search["latency_ms"],
    "error_type": parse_error or search["error_type"],
    "error": search["error"],
    "results": results[:10],
}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False))
sys.exit(0 if report["ok"] else 1)
PY

