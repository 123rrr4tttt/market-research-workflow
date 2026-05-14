#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${YACY_BASE_URL:-http://127.0.0.1:8090}"
OUT_DIR="${SEARCH_LAB_OUT_DIR:-development/latest-dev-docs/automation-runs/search-provider-lab/2026-05-14}"
mkdir -p "$OUT_DIR"

python3 - "$BASE_URL" "$OUT_DIR/yacy_smoke.json" "${YACY_ADMIN_USER:-}" "${YACY_ADMIN_PASSWORD:-}" <<'PY'
import json
import shlex
import sys
import subprocess
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

base_url = sys.argv[1].rstrip("/")
out_path = sys.argv[2]
admin_user = sys.argv[3]
admin_password = sys.argv[4]
query = "embodied ai"
local_query = "marketworkflow sentinel"
local_query_terms = local_query.lower().split()
local_url_id = "http://nowhere.cc/mrw-search-lab-local-test.txt"
local_doc = "marketworkflow sentinel official YaCy push API document"


def fetch(url, timeout=15):
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


def push_document(url, fields, timeout=20):
    started = time.perf_counter()
    params = urllib.parse.urlencode(fields)
    request_url = f"{url}?{params}"
    if admin_user and admin_password:
        cmd = ["curl", "-sS", "--anyauth", "-u", f"{admin_user}:{admin_password}", "-w", "\n%{http_code}", request_url]
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
            output = proc.stdout or ""
            body, _, status_text = output.rpartition("\n")
            status = int(status_text.strip()) if status_text.strip().isdigit() else None
            return {
                "ok": bool(proc.returncode == 0 and status and 200 <= status < 300),
                "status": status,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "body": body,
                "error_type": None if proc.returncode == 0 and status and 200 <= status < 300 else "CurlError",
                "error": (proc.stderr or "").strip() or (None if status and 200 <= status < 300 else f"curl exit={proc.returncode} status={status}"),
            }
        except (subprocess.SubprocessError, TimeoutError) as exc:
            return {
                "ok": False,
                "status": None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "body": "",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
    req = urllib.request.Request(request_url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_body = resp.read().decode("utf-8", errors="replace")
            return {
                "ok": 200 <= resp.status < 300,
                "status": resp.status,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "body": response_body,
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


def push_document_with_fallback(url, fields, timeout=20):
    result = push_document(url, fields, timeout=timeout)
    if result["ok"]:
        return result
    container = "mrw-search-lab-yacy"
    encoded = urllib.parse.urlencode(fields)
    inner_url = f"http://127.0.0.1:8090/api/push_p.json?{encoded}"
    cmd = ["docker", "exec", container, "sh", "-lc", f"wget -qO- {shlex.quote(inner_url)}"]
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0:
            return {
                "ok": True,
                "status": 200,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "body": proc.stdout,
                "error_type": None,
                "error": None,
            }
        return {
            "ok": False,
            "status": result.get("status"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "body": proc.stdout or result.get("body", ""),
            "error_type": result.get("error_type") or "DockerExecError",
            "error": (proc.stderr or "").strip() or result.get("error"),
        }
    except (subprocess.SubprocessError, TimeoutError) as exc:
        return {
            "ok": False,
            "status": result.get("status"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "body": result.get("body", ""),
            "error_type": result.get("error_type") or exc.__class__.__name__,
            "error": result.get("error") or str(exc),
        }


def parse_items(body):
    payload = json.loads(body)
    rows = []
    channels = payload.get("channels")
    if isinstance(channels, list) and channels and isinstance(channels[0], dict):
        rows = channels[0].get("items") or channels[0].get("results") or []
    if not rows:
        rows = payload.get("items") or payload.get("results") or []
    return [
        {"title": item.get("title"), "link": item.get("link") or item.get("url")}
        for item in rows
        if isinstance(item, dict)
    ]


root = fetch(base_url + "/")
global_url = f"{base_url}/yacysearch.json?{urllib.parse.urlencode({'query': query, 'resource': 'global', 'maximumRecords': 10, 'urlmaskfilter': '.*', 'prefermaskfilter': '', 'nav': 'none'})}"
global_search = fetch(global_url)
global_parse_error = None
global_results = []
if global_search["body"]:
    try:
        global_results = parse_items(global_search["body"])
    except Exception as exc:
        global_parse_error = exc.__class__.__name__

push_params = [
    ("count", "1"),
    ("url-0", local_url_id),
    ("data-0$file", local_doc),
    ("contentType-0", "text/plain"),
    ("responseHeader-0", "Content-Type:text/plain"),
    ("collection-0", "mrw-search-lab"),
    ("synchronous", "false"),
    ("commit", "false"),
]
push = push_document_with_fallback(f"{base_url}/api/push_p.json", push_params)
push_parse_error = None
push_payload = {}
if push["body"]:
    try:
        push_payload = json.loads(push["body"])
    except Exception as exc:
        push_parse_error = exc.__class__.__name__

local_url = f"{base_url}/yacysearch.json?{urllib.parse.urlencode({'query': local_query, 'resource': 'local', 'maximumRecords': 10, 'urlmaskfilter': '.*', 'prefermaskfilter': '', 'nav': 'none'})}"
local_search = fetch(local_url)
local_parse_error = None
local_results = []


def contains_local_document(items):
    for item in items:
        haystack = json.dumps(item, ensure_ascii=False).lower()
        if local_url_id.lower() in haystack or all(term in haystack for term in local_query_terms):
            return True
    return False


for _ in range(30):
    local_parse_error = None
    local_results = []
    if local_search["body"]:
        try:
            local_results = parse_items(local_search["body"])
        except Exception as exc:
            local_parse_error = exc.__class__.__name__
    if contains_local_document(local_results):
        break
    time.sleep(2)
    local_search = fetch(local_url)

report = {
    "provider": "yacy",
    "base_url": base_url,
    "global_query": query,
    "local_query": local_query,
    "root_status": root["status"],
    "global_status": global_search["status"],
    "push_status": push["status"],
    "local_status": local_search["status"],
    "ok": bool(
        root["ok"]
        and global_search["ok"]
        and push["ok"]
        and local_search["ok"]
        and not global_parse_error
        and not push_parse_error
        and not local_parse_error
        and str(push_payload.get("successall") or "").lower() == "true"
        and contains_local_document(local_results)
    ),
    "global_result_count": len(global_results),
    "local_result_count": len(local_results),
    "local_push_record": push_payload,
    "local_push_success": str(push_payload.get("successall") or "").lower() == "true",
    "local_hit": contains_local_document(local_results),
    "latency_ms": global_search["latency_ms"],
    "error_type": global_parse_error or push_parse_error or local_parse_error or global_search["error_type"] or push["error_type"] or local_search["error_type"],
    "error": global_search["error"] or push["error"] or local_search["error"],
    "global_results": global_results[:10],
    "local_results": local_results[:10],
}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False))
sys.exit(0 if report["ok"] else 1)
PY
