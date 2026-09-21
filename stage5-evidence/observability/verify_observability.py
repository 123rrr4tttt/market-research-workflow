#!/usr/bin/env python3
"""Collect focused Stage 5 scrape and existing-alert evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request_json(url: str, token: str | None = None) -> tuple[int, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def request_text(url: str, token: str) -> tuple[int, str]:
    req = Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def parse_counter_lines(metrics: str, name: str) -> list[dict[str, Any]]:
    pattern = re.compile(rf"^{re.escape(name)}\{{([^}}]*)\}}\s+([0-9.eE+-]+)$", re.M)
    rows: list[dict[str, Any]] = []
    for match in pattern.finditer(metrics):
        labels = {}
        for item in re.finditer(r'(\w+)="([^"]*)"', match.group(1)):
            labels[item.group(1)] = item.group(2)
        rows.append({"labels": labels, "value": float(match.group(2))})
    return rows


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_private_env(path: str) -> dict[str, str]:
    """Read only task-owned KEY=VALUE entries; never echo values."""

    values: dict[str, str] = {}
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:18380")
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:18390")
    parser.add_argument("--token-env", default="STAGE5_METRICS_TOKEN")
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--compose-file", required=True)
    parser.add_argument("--project", default="mrw-stage5-observability")
    args = parser.parse_args()

    token = os.environ.get(args.token_env, "")
    private_env = load_private_env(args.env_file)
    if not token:
        token = private_env.get(args.token_env, "")
    if not token:
        parser.error(f"{args.token_env} is required")
    required_private_keys = (
        "STAGE5_POSTGRES_PASSWORD",
        "STAGE5_ELASTIC_PASSWORD",
        "STAGE5_REDIS_PASSWORD",
        "STAGE5_METRICS_TOKEN",
        "STAGE5_METRICS_TOKEN_FILE",
        "STAGE5_CODEX_AUTH_TOKEN",
    )
    missing_private_keys = [key for key in required_private_keys if not private_env.get(key)]
    if missing_private_keys:
        parser.error(f"env-file missing keys: {missing_private_keys}")
    if not Path(private_env["STAGE5_METRICS_TOKEN_FILE"]).is_file():
        parser.error("STAGE5_METRICS_TOKEN_FILE does not exist")
    os.environ.update(private_env)
    if not token:
        parser.error(f"{args.token_env} is required")
    started = datetime.now(UTC).isoformat()
    result: dict[str, Any] = {
        "schema": "mrw.stage5.observability.focused.v1",
        "authoritative": False,
        "started_at": started,
        "backend_url": args.backend_url,
        "prometheus_url": args.prometheus_url,
        "commands": [],
        "checks": [],
        "alert_boundary": {
            "configured_rules": [
                "domain.rejection_rate",
                "route.error_rate",
                "release_version.error_rate",
                "stage5-local-queue",
                "stage5-local-db-connection",
                "stage5-local-provider-failure",
                "stage5-local-authority-mismatch",
                "stage5-local-projection-drift",
                "stage5-local-request-latency",
            ],
            "missing_source_producers": [],
            "runtime_rule_validation": "deep-health samples Redis LLEN, DB SELECT 1/pool and runtime bindings; provider failure is explicitly simulated; all observations remain non-authoritative",
        },
    }

    health_code, health = request_json(f"{args.backend_url}/api/v1/health", token)
    result["checks"].append({"name": "backend_health", "exit_code": 0 if health_code == 200 else 1, "http_status": health_code, "payload": health})
    metrics_code, metrics = request_text(f"{args.backend_url}/metrics", token)
    Path(args.output).with_suffix(".metrics").write_text(metrics, encoding="utf-8")
    result["checks"].append({"name": "backend_metrics_scrape", "exit_code": 0 if metrics_code == 200 else 1, "http_status": metrics_code})
    runtime_health_declared = (
        "# HELP market_api_production_observability_runtime_health " in metrics
        and "# TYPE market_api_production_observability_runtime_health gauge" in metrics
    )
    alert_state_declared = (
        "# HELP market_api_production_observability_alert_state " in metrics
        and "# TYPE market_api_production_observability_alert_state gauge" in metrics
    )
    result["checks"].append({
        "name": "backend_observability_gauges_declared",
        "exit_code": 0 if metrics_code == 200 and runtime_health_declared and alert_state_declared else 1,
        "runtime_health_declared": runtime_health_declared,
        "alert_state_declared": alert_state_declared,
        "note": "runtime-health samples are event-driven; alert-state is exported one-hot for all configured rules",
    })

    scrape_url = (
        f"{args.prometheus_url}/api/v1/query?query="
        + "up{job=\"mrw-stage5-backend\"}"
    )
    scrape_code, scrape = request_json(scrape_url)
    result["checks"].append({"name": "prometheus_up_query", "exit_code": 0 if scrape_code == 200 and scrape.get("status") == "success" else 1, "http_status": scrape_code, "payload": scrape})

    alert_series_code, alert_series = request_json(
        f"{args.prometheus_url}/api/v1/query?query=count%28market_api_production_observability_alert_state%29"
    )
    alert_series_count = 0
    try:
        alert_series_count = int(float(alert_series["data"]["result"][0]["value"][1]))
    except (KeyError, IndexError, TypeError, ValueError):
        alert_series_count = 0
    result["checks"].append({
        "name": "prometheus_alert_state_series",
        "exit_code": 0 if alert_series_code == 200 and alert_series.get("status") == "success" and alert_series_count >= 27 else 1,
        "http_status": alert_series_code,
        "series_count": alert_series_count,
        "expected_minimum": 27,
        "note": "9 configured rules x unknown/triggered/recovered one-hot states",
    })

    prod_code, prod_metrics = request_text(f"{args.backend_url}/metrics", token)
    counters = parse_counter_lines(prod_metrics, "market_api_production_requests_total")
    release_versions = sorted({row["labels"].get("release_version") for row in counters if row["labels"].get("release_version")})
    result["checks"].append({
        "name": "production_request_metrics",
        "exit_code": 0 if prod_code == 200 and counters and len(release_versions) == 1 else 1,
        "release_binding": {
            "source": "dynamic /metrics label readback",
            "release_versions": release_versions,
            "unique_release_versions": len(release_versions),
        },
        "counter_labels": [row["labels"] for row in counters],
        "counter_values": [row["value"] for row in counters],
    })

    build_cmd = [
        "docker", "compose", "-f", args.compose_file, "-p", args.project,
        "ps", "--format", "json",
    ]
    ps_proc = subprocess.run(build_cmd, capture_output=True, text=True, check=False)
    result["commands"].append({"command": build_cmd, "exit_code": ps_proc.returncode, "stdout": ps_proc.stdout, "stderr": ps_proc.stderr})
    result["completed_at"] = datetime.now(UTC).isoformat()
    result["exit_code"] = 0 if all(item["exit_code"] == 0 for item in result["checks"]) and ps_proc.returncode == 0 else 1
    output = Path(args.output)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
