#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "main" / "backend"
DEFAULT_OUT_DIR = (
    "development/latest-dev-docs/automation-runs/"
    "search-provider-container-replay/2026-05-22"
)
DEFAULT_SEARXNG_KEYWORDS = ["embodied ai"]
DEFAULT_YACY_KEYWORDS = ["marketworkflow sentinel"]
TRACE_FIELDS = ("provider_route", "provider_family", "provider_auto_included", "backend_trace")


def _ensure_backend_path() -> None:
    backend_path = str(BACKEND_ROOT)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)


def _run_command(cmd: list[str], *, cwd: Path, timeout: int = 30) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "ok": proc.returncode == 0,
        }
    except (subprocess.SubprocessError, TimeoutError) as exc:
        return {
            "cmd": cmd,
            "returncode": None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "stdout": "",
            "stderr": str(exc),
            "ok": False,
            "error_type": exc.__class__.__name__,
        }


def _parse_json_lines(raw: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            rows.append({"raw": text})
            continue
        if isinstance(payload, list):
            rows.extend([item for item in payload if isinstance(item, dict)])
        elif isinstance(payload, dict):
            rows.append(payload)
    return rows


def collect_docker_status(compose_file: str) -> dict[str, Any]:
    compose_cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "ps",
        "--format",
        "json",
    ]
    ps_cmd = [
        "docker",
        "ps",
        "--filter",
        "name=mrw-search-lab-",
        "--format",
        "{{json .}}",
    ]
    compose = _run_command(compose_cmd, cwd=REPO_ROOT)
    container_ps = _run_command(ps_cmd, cwd=REPO_ROOT)
    return {
        "compose_file": compose_file,
        "compose_ps": {
            **compose,
            "parsed": _parse_json_lines(compose.get("stdout") or ""),
        },
        "container_ps": {
            **container_ps,
            "parsed": _parse_json_lines(container_ps.get("stdout") or ""),
        },
    }


def _expected_trace(provider: str, *, yacy_resource: str) -> dict[str, Any]:
    if provider == "searxng":
        return {
            "provider_route": "explicit:searxng",
            "provider_family": "local_open_search",
            "provider_auto_included": False,
            "backend_trace": {
                "provider": "searxng",
                "provider_route": "explicit:searxng",
                "provider_family": "local_open_search",
                "auto_included": False,
                "pageno": "present",
            },
        }
    if provider == "yacy":
        resource = yacy_resource if yacy_resource in {"local", "global"} else "local"
        return {
            "provider_route": "explicit:yacy",
            "provider_family": "local_open_search",
            "provider_auto_included": False,
            "backend_trace": {
                "provider": "yacy",
                "provider_route": "explicit:yacy",
                "provider_family": "local_open_search",
                "auto_included": False,
                "resource": resource,
            },
        }
    raise ValueError(f"unsupported provider: {provider}")


def _trace_failures(item: dict[str, Any], provider: str, *, yacy_resource: str) -> list[str]:
    expected = _expected_trace(provider, yacy_resource=yacy_resource)
    failures: list[str] = []
    for field in TRACE_FIELDS:
        if field not in item:
            failures.append(f"missing:{field}")
    for field in ("provider_route", "provider_family", "provider_auto_included"):
        if item.get(field) != expected[field]:
            failures.append(f"{field}:expected={expected[field]!r}:actual={item.get(field)!r}")
    trace = item.get("backend_trace")
    if not isinstance(trace, dict):
        failures.append("backend_trace:not_dict")
        return failures
    expected_trace = expected["backend_trace"]
    for field, value in expected_trace.items():
        if value == "present":
            if field not in trace:
                failures.append(f"backend_trace.{field}:missing")
        elif trace.get(field) != value:
            failures.append(f"backend_trace.{field}:expected={value!r}:actual={trace.get(field)!r}")
    return failures


def _sample_result(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": item.get("rank"),
        "title": item.get("title"),
        "link": item.get("link"),
        "source": item.get("source"),
        "provider_route": item.get("provider_route"),
        "provider_family": item.get("provider_family"),
        "provider_auto_included": item.get("provider_auto_included"),
        "backend_trace": item.get("backend_trace"),
        "raw": item.get("raw"),
    }


def replay_provider(
    *,
    provider: str,
    keyword: str,
    limit: int,
    language: str,
    yacy_resource: str,
) -> dict[str, Any]:
    _ensure_backend_path()
    from app.services.search import web

    original_generate_keywords = web.generate_keywords
    web.generate_keywords = lambda topic, language="en": [topic]
    started = time.perf_counter()
    try:
        results = web.search_sources(
            keyword,
            language=language,
            max_results=limit,
            provider=provider,
            exclude_existing=False,
        )
        error_type = None
        error = None
    except Exception as exc:  # noqa: BLE001 - replay artifact records the real blocker.
        results = []
        error_type = exc.__class__.__name__
        error = str(exc)
    finally:
        web.generate_keywords = original_generate_keywords

    trace_failures: list[dict[str, Any]] = []
    for index, item in enumerate(results):
        failures = _trace_failures(item, provider, yacy_resource=yacy_resource)
        if failures:
            trace_failures.append({"result_index": index, "failures": failures})

    trace_contract_ok = bool(results) and not trace_failures and error_type is None
    if not results and error_type is None:
        error_type = "NoResults"
        error = "Provider returned no normalized backend search results; trace fields cannot be proven."

    return {
        "provider": provider,
        "keyword": keyword,
        "ok": trace_contract_ok,
        "trace_contract_ok": trace_contract_ok,
        "requested_limit": limit,
        "result_count": len(results),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "error_type": error_type,
        "error": error,
        "expected_trace": _expected_trace(provider, yacy_resource=yacy_resource),
        "trace_failure_count": len(trace_failures),
        "trace_failures": trace_failures,
        "sample_results": [_sample_result(item) for item in results[: min(5, len(results))]],
    }


def write_summary(
    *,
    out_dir: Path,
    rows: list[dict[str, Any]],
    docker_status: dict[str, Any],
    commands: list[str],
    env_snapshot: dict[str, str],
) -> None:
    ok_count = sum(1 for row in rows if row.get("ok"))
    lines = [
        "# Search Provider Container Trace Replay",
        "",
        "日期：2026-05-22 PST",
        "",
        "## Scope",
        "",
        "- Providers: `searxng`, `yacy`.",
        "- Replay path: real local container endpoints through backend `search_sources(provider=...)` adapters.",
        "- Contract: every normalized result must expose `provider_route`, `provider_family`, `provider_auto_included`, and `backend_trace`.",
        "- Keyword generation is pinned to the exact replay keyword so this evidence does not depend on LLM credentials.",
        "",
        "## Result",
        "",
        f"- Rows: {len(rows)}",
        f"- Passed rows: {ok_count}",
        f"- Failed rows: {len(rows) - ok_count}",
        "",
        "| provider | keyword | ok | result_count | trace_failure_count | latency_ms | error_type |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {provider} | {keyword} | {ok} | {result_count} | {trace_failure_count} | {latency_ms} | {error_type} |".format(
                provider=row.get("provider"),
                keyword=str(row.get("keyword", "")).replace("|", "\\|"),
                ok=str(bool(row.get("ok"))).lower(),
                result_count=row.get("result_count"),
                trace_failure_count=row.get("trace_failure_count"),
                latency_ms=row.get("latency_ms"),
                error_type=row.get("error_type") or "",
            )
        )
    lines.extend(
        [
            "",
            "## Docker Service State",
            "",
            f"- Compose status command ok: `{str(bool(docker_status.get('compose_ps', {}).get('ok'))).lower()}`",
            f"- Matching search-lab containers: `{len(docker_status.get('container_ps', {}).get('parsed') or [])}`",
            "",
            "See `docker_status.json` for raw `docker compose ps` and `docker ps` output.",
            "",
            "## Re-run Commands",
            "",
            "```bash",
            *commands,
            "```",
            "",
            "## Environment",
            "",
            "```json",
            json.dumps(env_snapshot, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Artifacts",
            "",
            "- `provider_trace_replay.jsonl`: per-provider replay rows.",
            "- `provider_trace_replay_summary.json`: aggregate replay status and environment.",
            "- `docker_status.json`: Docker service evidence.",
        ]
    )
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--compose-file", default="ops/search-lab/docker-compose.yml")
    parser.add_argument("--providers", default="searxng,yacy")
    parser.add_argument("--searxng-keywords", nargs="*", default=DEFAULT_SEARXNG_KEYWORDS)
    parser.add_argument("--yacy-keywords", nargs="*", default=DEFAULT_YACY_KEYWORDS)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    providers = [provider.strip() for provider in args.providers.split(",") if provider.strip()]
    unsupported = [provider for provider in providers if provider not in {"searxng", "yacy"}]
    if unsupported:
        raise SystemExit(f"unsupported provider(s): {', '.join(unsupported)}")

    out_dir = REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    yacy_resource = os.getenv("YACY_RESOURCE_MODE", "local").strip() or "local"
    rows: list[dict[str, Any]] = []
    for provider in providers:
        keywords = args.searxng_keywords if provider == "searxng" else args.yacy_keywords
        for keyword in keywords:
            rows.append(
                replay_provider(
                    provider=provider,
                    keyword=keyword,
                    limit=args.limit,
                    language=args.language,
                    yacy_resource=yacy_resource,
                )
            )

    jsonl_path = out_dir / "provider_trace_replay.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    docker_status = collect_docker_status(args.compose_file)
    (out_dir / "docker_status.json").write_text(
        json.dumps(docker_status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    env_snapshot = {
        "SEARXNG_BASE_URL": os.getenv("SEARXNG_BASE_URL", "http://127.0.0.1:8088"),
        "YACY_BASE_URL": os.getenv("YACY_BASE_URL", "http://127.0.0.1:8090"),
        "YACY_RESOURCE_MODE": yacy_resource,
        "SEARXNG_MAX_PAGES": os.getenv("SEARXNG_MAX_PAGES", "5"),
        "PYTHONPATH_NOTE": "script prepends main/backend to sys.path",
    }
    commands = [
        f"docker compose -f {args.compose_file} up -d searxng yacy",
        f"SEARCH_LAB_OUT_DIR={args.out_dir} bash ops/search-lab/scripts/smoke_searxng.sh",
        f"SEARCH_LAB_OUT_DIR={args.out_dir} YACY_ADMIN_USER=admin YACY_ADMIN_PASSWORD=\"${{YACY_ADMIN_PASSWORD:-mrwlabpass}}\" bash ops/search-lab/scripts/smoke_yacy.sh",
        f"SEARXNG_BASE_URL={env_snapshot['SEARXNG_BASE_URL']} YACY_BASE_URL={env_snapshot['YACY_BASE_URL']} YACY_RESOURCE_MODE={yacy_resource} main/backend/.venv311/bin/python ops/search-lab/scripts/replay_provider_trace.py --out-dir {args.out_dir}",
    ]
    summary = {
        "out_dir": str(out_dir.relative_to(REPO_ROOT)),
        "ok": bool(rows) and all(row.get("ok") for row in rows),
        "rows": len(rows),
        "passed_rows": sum(1 for row in rows if row.get("ok")),
        "failed_rows": sum(1 for row in rows if not row.get("ok")),
        "env": env_snapshot,
        "docker_compose_ok": bool(docker_status.get("compose_ps", {}).get("ok")),
        "docker_container_count": len(docker_status.get("container_ps", {}).get("parsed") or []),
        "commands": commands,
    }
    (out_dir / "provider_trace_replay_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_summary(
        out_dir=out_dir,
        rows=rows,
        docker_status=docker_status,
        commands=commands,
        env_snapshot=env_snapshot,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
