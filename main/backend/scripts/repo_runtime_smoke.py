#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_TIMEOUT = 60
DEFAULT_PROJECT_KEY = "demo_proj"
DEFAULT_SOURCE_ITEM_CANDIDATES = [
    "report1.high_value_urls",
    "report1.root_site_search",
]


class SmokeFailure(RuntimeError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class ResponseEnvelope:
    status: int
    headers: dict[str, str]
    body: Any


class SmokeClient:
    def __init__(self, base_url: str, *, project_key: str, timeout: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.default_headers = {
            "Accept": "application/json",
            "X-Project-Key": project_key,
            "X-Request-Id": f"repo-runtime-smoke-{int(time.time())}",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Any | None = None,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
    ) -> ResponseEnvelope:
        merged_headers = dict(self.default_headers)
        if headers:
            merged_headers.update(headers)
        data: bytes | None = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            merged_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(f"{self.base_url}{path}", method=method, headers=merged_headers)
        opener = urllib.request.build_opener() if follow_redirects else urllib.request.build_opener(_NoRedirectHandler)
        try:
            with opener.open(request, data=data, timeout=self.timeout) as response:
                return ResponseEnvelope(
                    status=response.status,
                    headers={k.lower(): v for k, v in response.headers.items()},
                    body=_decode_response_body(response.read()),
                )
        except urllib.error.HTTPError as exc:
            return ResponseEnvelope(
                status=exc.code,
                headers={k.lower(): v for k, v in exc.headers.items()},
                body=_decode_response_body(exc.read()),
            )


def _decode_response_body(raw: bytes) -> Any:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _unwrap_data(body: Any) -> Any:
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        return body["data"]
    return body


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _pick_source_item(items: list[dict[str, Any]], explicit_item_key: str | None) -> str:
    if explicit_item_key:
        return explicit_item_key
    keys = {str(item.get("item_key") or "") for item in items if isinstance(item, dict)}
    for candidate in DEFAULT_SOURCE_ITEM_CANDIDATES:
        if candidate in keys:
            return candidate
    for item in items:
        item_key = str(item.get("item_key") or "").strip()
        if item_key:
            return item_key
    raise SmokeFailure("source_library/items returned no usable item_key")


def _poll_until(
    fn,
    *,
    timeout_seconds: int,
    interval_seconds: float,
    description: str,
):
    deadline = time.time() + timeout_seconds
    last_value = None
    while time.time() < deadline:
        last_value = fn()
        if last_value:
            return last_value
        time.sleep(interval_seconds)
    raise SmokeFailure(f"timed out waiting for {description}")


def _run_normal_backend_checks(client: SmokeClient, *, project_key: str, source_item_key: str | None, poll_seconds: int) -> None:
    print(f"[backend] smoke against {client.base_url}")

    health = client.request("GET", "/api/v1/health")
    _require(health.status == 200, f"/health expected 200, got {health.status}")
    _require(health.headers.get("x-project-key-resolved") == project_key, "health missing resolved project key header")
    _require(bool(health.headers.get("x-project-key-enforcement-mode")), "health missing enforcement header")
    print("[pass] GET /api/v1/health")

    deep_health = client.request("GET", "/api/v1/health/deep")
    _require(deep_health.status == 200, f"/health/deep expected 200, got {deep_health.status}")
    print("[pass] GET /api/v1/health/deep")

    projects = client.request("GET", "/api/v1/projects")
    _require(projects.status == 200, f"/projects expected 200, got {projects.status}")
    print("[pass] GET /api/v1/projects")

    graph_id = f"runtime-smoke-{int(time.time())}"
    workflow_compile = client.request(
        "POST",
        "/api/v1/workflow-graph/compile",
        payload={
            "graph_id": graph_id,
            "dsl": {
                "version": "1.0",
                "nodes": [
                    {
                        "node_id": "n1",
                        "node_type": "vector_search",
                        "config": {
                            "input_vars": [{"name": "query", "source": "input", "required": True}],
                            "top_k": 2,
                            "output_vars": [{"name": "hits"}],
                        },
                    }
                ],
                "edges": [],
            },
        },
    )
    _require(workflow_compile.status == 200, f"/workflow-graph/compile expected 200, got {workflow_compile.status}")
    compile_data = _unwrap_data(workflow_compile.body)
    compiled_graph_id = str(compile_data.get("graph_id") or "")
    _require(compiled_graph_id == graph_id, "workflow compile did not return expected graph_id")
    print("[pass] POST /api/v1/workflow-graph/compile")

    workflow_run = client.request(
        "POST",
        "/api/v1/workflow-graph/run",
        payload={"graph_id": compiled_graph_id, "input": {"query": "market research"}},
    )
    _require(workflow_run.status == 200, f"/workflow-graph/run expected 200, got {workflow_run.status}")
    run_data = _unwrap_data(workflow_run.body)
    run_id = str(run_data.get("run_id") or "")
    _require(run_id, "workflow run missing run_id")
    print("[pass] POST /api/v1/workflow-graph/run")

    def _workflow_done():
        current = client.request("GET", f"/api/v1/workflow-graph/runs/{urllib.parse.quote(run_id)}")
        _require(current.status == 200, f"/workflow-graph/runs/{{run_id}} expected 200, got {current.status}")
        current_data = _unwrap_data(current.body)
        status = str(current_data.get("status") or "")
        if status == "succeeded":
            return current_data
        return None

    _poll_until(_workflow_done, timeout_seconds=poll_seconds, interval_seconds=1.0, description="workflow graph success")
    workflow_events = client.request("GET", f"/api/v1/workflow-graph/runs/{urllib.parse.quote(run_id)}/events")
    _require(workflow_events.status == 200, f"/workflow-graph/runs/{{run_id}}/events expected 200, got {workflow_events.status}")
    compiled_fetch = client.request("GET", f"/api/v1/workflow-graph/compiled/{urllib.parse.quote(compiled_graph_id)}")
    _require(compiled_fetch.status == 200, f"/workflow-graph/compiled/{{graph_id}} expected 200, got {compiled_fetch.status}")
    print("[pass] workflow_graph compile -> run -> status -> events -> compiled")

    llm_report = client.request(
        "POST",
        "/api/v1/llm-report/generate",
        payload={
            "topic": "market growth",
            "sources": [
                {
                    "id": "SRC-1",
                    "title": "Runtime Smoke Source",
                    "url": "https://example.com/runtime-smoke-source",
                    "publisher": "runtime_smoke",
                    "evidence": "Runtime smoke evidence",
                }
            ],
        },
    )
    _require(llm_report.status == 200, f"/llm-report/generate expected 200, got {llm_report.status}")
    llm_report_data = _unwrap_data(llm_report.body)
    capability_truth = (llm_report_data.get("capability_truth") or {}) if isinstance(llm_report_data, dict) else {}
    _require(bool(capability_truth.get("implementation_kind")), "llm report missing capability_truth")
    print("[pass] POST /api/v1/llm-report/generate")

    template_validate = client.request(
        "POST",
        "/api/v1/writing/templates/validate",
        payload={
            "project_key": project_key,
            "template_key": "market_weekly",
            "sample_payload": {"project_key": project_key},
            "strict": True,
        },
    )
    _require(template_validate.status == 200, f"/writing/templates/validate expected 200, got {template_validate.status}")
    validate_data = _unwrap_data(template_validate.body)
    _require(isinstance(validate_data, dict) and "valid" in validate_data, "template validate missing valid field")
    print("[pass] POST /api/v1/writing/templates/validate")

    llm_action = client.request(
        "POST",
        "/api/v1/writing/llm-actions",
        payload={
            "project_key": project_key,
            "action_id": "selection_rewrite",
            "input_markdown": "Draft paragraph for runtime smoke.",
            "selection_text": "Draft paragraph",
            "async": False,
        },
    )
    _require(llm_action.status == 200, f"/writing/llm-actions expected 200, got {llm_action.status}")
    llm_action_data = _unwrap_data(llm_action.body)
    action_capability_truth = (llm_action_data.get("capability_truth") or {}) if isinstance(llm_action_data, dict) else {}
    _require(bool(action_capability_truth.get("implementation_kind")), "writing llm action missing capability_truth")
    print("[pass] POST /api/v1/writing/llm-actions")

    ingest_market = client.request(
        "POST",
        "/api/v1/ingest/market",
        payload={
            "project_key": project_key,
            "query_terms": ["market research"],
            "max_items": 1,
            "async_mode": True,
        },
    )
    _require(ingest_market.status == 200, f"/ingest/market expected 200, got {ingest_market.status}")
    print("[pass] POST /api/v1/ingest/market")

    source_sync = client.request("POST", "/api/v1/ingest/source-library/sync", payload={"project_key": project_key})
    _require(source_sync.status == 200, f"/ingest/source-library/sync expected 200, got {source_sync.status}")
    print("[pass] POST /api/v1/ingest/source-library/sync")

    graph_collect = client.request(
        "POST",
        "/api/v1/ingest/graph/structured-search",
        payload={
            "selected_nodes": [{"type": "market", "entry_id": "n-1", "label": "ACME"}],
            "dashboard": {"project_key": project_key, "async_mode": False},
            "flow_type": "collect",
        },
    )
    _require(graph_collect.status == 200, f"/ingest/graph/structured-search expected 200, got {graph_collect.status}")
    graph_collect_data = _unwrap_data(graph_collect.body)
    summary = (graph_collect_data.get("summary") or {}) if isinstance(graph_collect_data, dict) else {}
    _require(int(summary.get("batch_count") or 0) >= 1, "structured-search missing batch_count")
    print("[pass] POST /api/v1/ingest/graph/structured-search")

    items_path = f"/api/v1/source_library/items?project_key={urllib.parse.quote(project_key)}"
    source_items = client.request("GET", items_path)
    _require(source_items.status == 200, f"/source_library/items expected 200, got {source_items.status}")
    source_items_data = _unwrap_data(source_items.body)
    items = source_items_data.get("items") if isinstance(source_items_data, dict) else None
    _require(isinstance(items, list), "source_library/items missing items list")
    effective_item_key = _pick_source_item(items, source_item_key)
    print(f"[info] source item_key={effective_item_key}")

    source_run = client.request(
        "POST",
        "/api/v1/ingest/source-library/run",
        payload={
            "project_key": project_key,
            "item_key": effective_item_key,
            "async_mode": False,
            "override_params": {"max_items": 2},
        },
    )
    _require(source_run.status == 200, f"/ingest/source-library/run expected 200, got {source_run.status}")
    source_run_data = _unwrap_data(source_run.body)
    if isinstance(source_run_data, dict):
        authority_output = source_run_data.get("authority_output")
        compat_projection = source_run_data.get("compat_projection")
        terminal_output = source_run_data.get("terminal_output")
        _require(
            bool(authority_output or compat_projection or terminal_output),
            "source-library run missing authority_output/compat_projection/terminal_output",
        )
    print("[pass] POST /api/v1/ingest/source-library/run")

    agent_submit = client.request(
        "POST",
        "/api/v1/agent-batch/jobs",
        payload={
            "project_key": project_key,
            "batch": {
                "jobs": [
                    {
                        "item_id": "runtime-smoke-1",
                        "item_key": effective_item_key,
                    }
                ]
            },
        },
    )
    _require(agent_submit.status == 200, f"/agent-batch/jobs expected 200, got {agent_submit.status}")
    agent_submit_data = _unwrap_data(agent_submit.body)
    job_id = str(agent_submit_data.get("job_id") or "")
    _require(job_id, "agent-batch submit missing job_id")
    print("[pass] POST /api/v1/agent-batch/jobs")

    def _job_done():
        current = client.request("GET", f"/api/v1/agent-batch/jobs/{urllib.parse.quote(job_id)}")
        _require(current.status == 200, f"/agent-batch/jobs/{{job_id}} expected 200, got {current.status}")
        current_data = _unwrap_data(current.body)
        status = str(current_data.get("status") or "")
        if status == "completed":
            progress = current_data.get("progress") or {}
            _require(int(progress.get("succeeded") or 0) >= 1, "agent batch completed without succeeded count")
            return current_data
        if status == "failed":
            raise SmokeFailure(f"agent batch job failed: {json.dumps(current.body, ensure_ascii=False)}")
        return None

    _poll_until(_job_done, timeout_seconds=poll_seconds, interval_seconds=1.0, description="agent-batch success")
    agent_items = client.request("GET", f"/api/v1/agent-batch/jobs/{urllib.parse.quote(job_id)}/items")
    _require(agent_items.status == 200, f"/agent-batch/jobs/{{job_id}}/items expected 200, got {agent_items.status}")
    agent_items_data = _unwrap_data(agent_items.body)
    items_payload = agent_items_data.get("items") if isinstance(agent_items_data, dict) else None
    _require(isinstance(items_payload, list) and items_payload, "agent batch items missing")
    first_item = items_payload[0]
    _require(str(first_item.get("status") or "") == "success", "agent batch item did not finish with success")
    agent_events = client.request("GET", f"/api/v1/agent-batch/jobs/{urllib.parse.quote(job_id)}/events")
    _require(agent_events.status == 200, f"/agent-batch/jobs/{{job_id}}/events expected 200, got {agent_events.status}")
    print("[pass] agent_batch submit -> poll -> items -> events")

    session_id = str(agent_submit_data.get("session_id") or "")
    if session_id:
        def _session_done():
            current = client.request("GET", f"/api/v1/agent-sessions/{urllib.parse.quote(session_id)}")
            _require(current.status == 200, f"/agent-sessions/{{session_id}} expected 200, got {current.status}")
            session_data = _unwrap_data(current.body)
            session_record = session_data.get("session") if isinstance(session_data, dict) else None
            if not isinstance(session_record, dict):
                raise SmokeFailure(f"agent session detail missing session record: {json.dumps(current.body, ensure_ascii=False)}")
            status = str(session_record.get("status") or "")
            if status == "completed":
                return session_record
            if status == "failed":
                raise SmokeFailure(f"agent session failed: {json.dumps(current.body, ensure_ascii=False)}")
            return None

        _poll_until(_session_done, timeout_seconds=poll_seconds, interval_seconds=1.0, description="agent session completion")
        print("[pass] GET /api/v1/agent-sessions/{session_id}")

    for path, expected_suffix in (
        ("/", "/"),
        ("/app", "/"),
        ("/graph.html?type=market", "/#graph.html%3Ftype%3Dmarket"),
    ):
        redirect_resp = client.request("GET", path, follow_redirects=False)
        _require(300 <= redirect_resp.status < 400, f"{path} expected redirect, got {redirect_resp.status}")
        location = str(redirect_resp.headers.get("location") or "")
        _require(location.endswith(expected_suffix), f"{path} redirect mismatch: {location}")
        print(f"[pass] redirect {path} -> {location}")


def _run_require_mode_checks(require_client: SmokeClient) -> None:
    print(f"[require-mode] smoke against {require_client.base_url}")
    health = require_client.request("GET", "/api/v1/health")
    _require(health.status == 200, f"require-mode /health expected 200, got {health.status}")
    _require(health.headers.get("x-project-key-enforcement-mode") == "require", "require-mode header mismatch")
    _require(health.headers.get("x-project-key-fallback-allowed") == "false", "require-mode fallback header mismatch")
    print("[pass] require-mode GET /api/v1/health")

    missing_project = require_client.request(
        "POST",
        "/api/v1/ingest/source-library/run",
        payload={"item_key": "demo-item", "async_mode": False, "override_params": {}},
        headers={"X-Project-Key": ""},
    )
    _require(missing_project.status == 400, f"require-mode missing project_key expected 400, got {missing_project.status}")
    body = missing_project.body
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        error_code = ((detail.get("error") or {}).get("code") or "")
        _require(error_code == "PROJECT_KEY_REQUIRED", f"unexpected require-mode error code: {error_code}")
    else:
        raise SmokeFailure(f"require-mode missing project_key did not return error envelope: {body}")
    print("[pass] require-mode POST /api/v1/ingest/source-library/run without project_key")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repo-level runtime smoke checks against a live local stack.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--require-base-url", default="")
    parser.add_argument("--project-key", default=DEFAULT_PROJECT_KEY)
    parser.add_argument("--source-item-key", default="")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--poll-seconds", type=int, default=20)
    args = parser.parse_args()

    try:
        client = SmokeClient(args.base_url, project_key=args.project_key, timeout=args.timeout)
        _run_normal_backend_checks(
            client,
            project_key=args.project_key,
            source_item_key=args.source_item_key or None,
            poll_seconds=args.poll_seconds,
        )
        if args.require_base_url.strip():
            require_client = SmokeClient(args.require_base_url, project_key=args.project_key, timeout=args.timeout)
            _run_require_mode_checks(require_client)
        print("RUNTIME_SMOKE_PASS")
        return 0
    except SmokeFailure as exc:
        print(f"RUNTIME_SMOKE_FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
