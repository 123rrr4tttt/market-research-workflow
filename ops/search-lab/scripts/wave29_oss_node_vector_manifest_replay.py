#!/usr/bin/env python3
"""Wave29 OSS-node vector manifest replay gate.

This gate proves the repo-local node layer can consume the Wave19 vector
provider manifest through the workflow graph compiler/runtime/event readback
path. It is deterministic and does not call live providers, tenant DBs, or UI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_DIR = "development/latest-dev-docs/automation-runs/wave29-oss-node-vector-manifest-replay/2026-05-23"
DEFAULT_PROVIDER_MANIFEST = (
    REPO_ROOT
    / "development/latest-dev-docs/automation-runs/wave19-vectorization-provider-manifest/2026-05-22/provider_manifest_readback.json"
)
TARGET_TOPIC = (
    "development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/"
    "2026-03-05-oss-node-platform-io-plan"
)

REQUIRED_MODES = ("keyword", "vector", "hybrid")
REQUIRED_PROVIDER_GAP_CODES = {
    "external_embedding_provider_live_not_verified",
    "local_open_search_live_quality_not_sealed",
    "oss_node_platform_io_sla_not_closed",
    "provider_auto_promotion_not_allowed",
    "semantic_embedding_quality_not_proven",
}
PLATFORM_IO_LIVE_SLA_CONDITION = "live_scheduler_tenant_db_ui_sla_not_proven"
PROVIDER_EXTERNAL_CONDITIONS = (
    "external_embedding_provider_live_not_verified",
    "local_open_search_live_quality_not_sealed",
    "semantic_embedding_quality_not_proven",
)
TARGET_EXTERNAL_CONDITIONS = (*PROVIDER_EXTERNAL_CONDITIONS, PLATFORM_IO_LIVE_SLA_CONDITION)
REPO_LOCAL_BLOCKERS_CLOSED = (
    "node_schema_runtime_persistence_platformization_scope_not_closed",
    "vector_search_node_manifest_consumption_not_live_replayed",
)
WAVE55_PLATFORM_IO_CONTRACT_VERSION = "wave55-oss-node-platform-io-sla-readback.v1"
FRONTEND_WORKFLOW_API_PATH = REPO_ROOT / "main/frontend-modern/src/lib/api/domains/graph-workflow.ts"
FRONTEND_LLM_DESIGNER_PATH = REPO_ROOT / "main/frontend-modern/src/pages/LlmDesignerPage.tsx"
FRONTEND_ENDPOINTS_PATH = REPO_ROOT / "main/frontend-modern/src/lib/api/endpoints.ts"
FRONTEND_REQUIRED_MARKERS = {
    "graph_workflow_domain": (
        "compileWorkflowGraph",
        "runWorkflowGraph",
        "getWorkflowGraphRun",
        "getWorkflowGraphRunEvents",
        "replayWorkflowGraphRun",
    ),
    "llm_designer_consumer": (
        "compileWorkflowGraph",
        "runWorkflowGraph",
        "getWorkflowGraphRun",
        "getWorkflowGraphRunEvents",
        "getCompiledWorkflowGraph",
    ),
    "workflow_endpoints": (
        "/workflow-graph/compile",
        "/workflow-graph/run",
        "/workflow-graph/runs/",
        "/workflow-graph/compiled/",
    ),
}


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    row: dict[str, Any] = {
        "path": display_path(path),
        "exists": path.exists(),
        "status": "running",
        "failures": [],
    }
    if not path.exists():
        row["status"] = "missing"
        row["failures"].append(f"provider manifest missing: {display_path(path)}")
        return {}, row
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        row["status"] = "failed"
        row["failures"].append(f"provider manifest invalid JSON: {exc}")
        return {}, row
    row["status"] = "loaded"
    return data, row


def _manifest_rows_by_mode(provider_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = provider_manifest.get("provider_manifest", {}).get("modes") or []
    return {str(row.get("mode")): dict(row) for row in rows if row.get("mode") in REQUIRED_MODES}


def _validate_provider_manifest(provider_manifest: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    if provider_manifest.get("contract_version") != "wave19-vectorization-provider-manifest.v1":
        failures.append(
            "provider manifest contract_version expected "
            "'wave19-vectorization-provider-manifest.v1'"
        )
    if provider_manifest.get("status") != "passed":
        failures.append(f"provider manifest status expected 'passed', got {provider_manifest.get('status')!r}")
    if provider_manifest.get("closure_claim_allowed") is not False:
        failures.append("provider manifest closure_claim_allowed must remain false")
    if provider_manifest.get("provider_live_closure_claim_allowed") is not False:
        failures.append("provider_live_closure_claim_allowed must remain false")
    if provider_manifest.get("semantic_quality_claim_allowed") is not False:
        failures.append("semantic_quality_claim_allowed must remain false")

    rows_by_mode = _manifest_rows_by_mode(provider_manifest)
    missing_modes = sorted(set(REQUIRED_MODES) - set(rows_by_mode))
    if missing_modes:
        failures.append(f"provider manifest missing modes: {missing_modes}")

    boundary = provider_manifest.get("external_provider_boundary") or {}
    gap_codes = {str(code) for code in boundary.get("gap_codes") or []}
    missing_gaps = sorted(REQUIRED_PROVIDER_GAP_CODES - gap_codes)
    if missing_gaps:
        failures.append(f"provider manifest missing external gap codes: {missing_gaps}")

    for mode in REQUIRED_MODES:
        row = rows_by_mode.get(mode) or {}
        if not row:
            continue
        if row.get("provider_id") != f"local_index.{mode}":
            failures.append(f"{mode}: provider_id mismatch")
        if row.get("closure_claim_allowed") is not False:
            failures.append(f"{mode}: closure_claim_allowed must remain false")
        capabilities = row.get("capabilities") or {}
        if capabilities.get("live_provider_verified") is not False:
            failures.append(f"{mode}: live_provider_verified must remain false")
        if capabilities.get("semantic_quality_claim_allowed") is not False:
            failures.append(f"{mode}: semantic_quality_claim_allowed must remain false")
        trace_quality = row.get("trace_quality") or {}
        if trace_quality.get("status") != "passed":
            failures.append(f"{mode}: trace_quality.status expected 'passed'")
        if trace_quality.get("provider_live_verified") is not False:
            failures.append(f"{mode}: trace_quality.provider_live_verified must remain false")
        if trace_quality.get("semantic_quality_claim_allowed") is not False:
            failures.append(f"{mode}: trace_quality.semantic_quality_claim_allowed must remain false")

    return (
        {
            "status": "passed" if not failures else "failed",
            "contract_version": provider_manifest.get("contract_version"),
            "manifest_status": provider_manifest.get("status"),
            "modes": sorted(rows_by_mode),
            "gap_codes": sorted(gap_codes),
            "closure_claim_allowed": provider_manifest.get("closure_claim_allowed"),
            "provider_live_closure_claim_allowed": provider_manifest.get("provider_live_closure_claim_allowed"),
            "semantic_quality_claim_allowed": provider_manifest.get("semantic_quality_claim_allowed"),
        },
        failures,
    )


def _run_node_manifest_replay(provider_manifest: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    from app.services.workflow_graph import WorkflowGraphCompilerService
    from app.services.workflow_graph.executors.base import BaseNodeExecutor, NodeExecutionContext
    from app.services.workflow_graph.runtime import WorkflowGraphRuntime
    from app.services.workflow_graph.store import InMemoryCompiledGraphStore, InMemoryRunStore

    rows_by_mode = _manifest_rows_by_mode(provider_manifest)
    gap_codes = sorted(
        set(provider_manifest.get("external_provider_boundary", {}).get("gap_codes") or [])
        | set(TARGET_EXTERNAL_CONDITIONS)
    )

    class ManifestReplayVectorExecutor(BaseNodeExecutor):
        node_type = "vector_search"

        def execute(self, node: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
            params = dict(node.get("params") or {})
            manifest_row = dict(params.get("provider_manifest") or {})
            mode = str(params.get("mode") or manifest_row.get("mode") or "").strip()
            capabilities = manifest_row.get("capabilities") or {}
            trace_quality = manifest_row.get("trace_quality") or {}
            replay_failures: list[str] = []

            if mode not in REQUIRED_MODES:
                replay_failures.append(f"unsupported replay mode: {mode!r}")
            if manifest_row.get("provider_id") != f"local_index.{mode}":
                replay_failures.append("provider_id does not match mode")
            if manifest_row.get("closure_claim_allowed") is not False:
                replay_failures.append("closure_claim_allowed must remain false")
            if capabilities.get("live_provider_verified") is not False:
                replay_failures.append("live_provider_verified must remain false")
            if capabilities.get("semantic_quality_claim_allowed") is not False:
                replay_failures.append("semantic_quality_claim_allowed must remain false")
            if trace_quality.get("status") != "passed":
                replay_failures.append("trace_quality.status must be passed")

            query = str(context.inputs.get("query") or "").strip()
            return {
                "node_type": self.node_type,
                "query": query,
                "retrieval_mode": mode,
                "provider_id": manifest_row.get("provider_id"),
                "provider_family": manifest_row.get("provider_family"),
                "manifest_consumed": not replay_failures,
                "manifest_replay_failures": replay_failures,
                "hits": [
                    {
                        "document_id": f"wave29-{mode}-fixture-hit-0",
                        "score": 1.0,
                        "title": f"Wave29 {mode} node replay fixture",
                        "mode": mode,
                        "backend": "repo_fixture",
                    }
                ],
                "trace": {
                    "requested_mode": mode,
                    "executed_mode": mode,
                    "provider_manifest": {
                        "contract_version": provider_manifest.get("contract_version"),
                        "provider_id": manifest_row.get("provider_id"),
                        "mode": mode,
                        "fallback": manifest_row.get("fallback") or {},
                        "trace_quality": trace_quality,
                    },
                    "closure_claim_allowed": False,
                    "live_provider_verified": False,
                    "semantic_quality_claim_allowed": False,
                    "unsupported_claim_codes": gap_codes,
                },
                "meta": {
                    "node_manifest_replay": {
                        "contract_version": "wave29-oss-node-vector-manifest-replay.v1",
                        "source_contract_version": provider_manifest.get("contract_version"),
                        "status": "passed" if not replay_failures else "failed",
                    }
                },
            }

    dsl = {
        "version": "1.0",
        "options": {
            "strict": True,
            "fixture": "wave29_oss_node_vector_manifest_replay",
        },
        "nodes": [
            {
                "node_id": f"vector_{mode}",
                "node_type": "vector_search",
                "config": {
                    "mode": mode,
                    "provider_manifest": rows_by_mode.get(mode) or {},
                    "gap_codes": gap_codes,
                    "input_vars": [
                        {"name": "query", "source": "input", "required": True},
                        {
                            "name": "project_id",
                            "source": "constant",
                            "default_value": "wave29-oss-node-fixture",
                        },
                        {
                            "name": "provider_manifest_version",
                            "source": "constant",
                            "default_value": str(provider_manifest.get("contract_version") or ""),
                        },
                    ],
                },
            }
            for mode in REQUIRED_MODES
        ],
        "edges": [],
    }

    compiler = WorkflowGraphCompilerService(store=InMemoryCompiledGraphStore())
    compile_response = compiler.compile(
        {
            "graph_id": "wave29-oss-node-vector-manifest-replay",
            "dsl": dsl,
        }
    )
    compiled = compiler.get_compiled(str(compile_response["graph_id"]))
    workflow = {
        "workflow_id": compiled["graph_id"],
        "topo_order": list(compiled.get("topo_order") or []),
        "nodes": dict(compiled.get("nodes") or {}),
    }
    runtime = WorkflowGraphRuntime(
        store=InMemoryRunStore(),
        executors=[ManifestReplayVectorExecutor()],
    )
    snapshot = runtime.run(
        workflow,
        inputs={"query": "wave29 node vector manifest replay"},
        run_id="wave29-oss-node-vector-manifest-replay-run",
    )
    consistency = _event_replay_consistency(snapshot)

    failures: list[str] = []
    run = snapshot.get("run") or {}
    results = snapshot.get("results") or {}
    if run.get("status") != "succeeded":
        failures.append(f"workflow run status expected 'succeeded', got {run.get('status')!r}")
    if list(compiled.get("topo_order") or []) != [f"vector_{mode}" for mode in REQUIRED_MODES]:
        failures.append("compiled topo_order does not match required manifest modes")
    if not consistency["consistent"]:
        failures.append("event replay consistency failed")

    mode_results = []
    for mode in REQUIRED_MODES:
        node_id = f"vector_{mode}"
        result = results.get(node_id) or {}
        trace = result.get("trace") or {}
        io_trace = result.get("io_trace") or {}
        node_failures = list(result.get("manifest_replay_failures") or [])
        if result.get("manifest_consumed") is not True:
            node_failures.append("manifest_consumed must be true")
        if result.get("data", {}).get("retrieval_mode") != mode:
            node_failures.append("normalized data.retrieval_mode mismatch")
        if trace.get("closure_claim_allowed") is not False:
            node_failures.append("trace.closure_claim_allowed must remain false")
        if trace.get("live_provider_verified") is not False:
            node_failures.append("trace.live_provider_verified must remain false")
        if trace.get("semantic_quality_claim_allowed") is not False:
            node_failures.append("trace.semantic_quality_claim_allowed must remain false")
        unsupported_claim_codes = set(str(code) for code in trace.get("unsupported_claim_codes") or [])
        missing_gap_codes = sorted(REQUIRED_PROVIDER_GAP_CODES - unsupported_claim_codes)
        if missing_gap_codes:
            node_failures.append(f"unsupported_claim_codes missing provider gaps: {missing_gap_codes}")
        for key in ("query", "project_id", "provider_manifest_version"):
            if key not in io_trace:
                node_failures.append(f"io_trace missing {key!r}")
        failures.extend(f"{node_id}: {failure}" for failure in node_failures)
        mode_results.append(
            {
                "mode": mode,
                "node_id": node_id,
                "status": "passed" if not node_failures else "failed",
                "provider_id": result.get("provider_id"),
                "manifest_consumed": result.get("manifest_consumed"),
                "closure_claim_allowed": trace.get("closure_claim_allowed"),
                "live_provider_verified": trace.get("live_provider_verified"),
                "semantic_quality_claim_allowed": trace.get("semantic_quality_claim_allowed"),
                "unsupported_claim_codes": sorted(unsupported_claim_codes),
                "io_trace_keys": sorted(io_trace),
                "failures": node_failures,
            }
        )

    return (
        {
            "status": "passed" if not failures else "failed",
            "workflow_graph": {
                "graph_id": compiled.get("graph_id"),
                "version": compiled.get("version"),
                "checksum": compiled.get("checksum"),
                "topo_order": compiled.get("topo_order"),
                "node_count": len(compiled.get("nodes") or {}),
            },
            "run": {
                "run_id": run.get("run_id"),
                "status": run.get("status"),
                "node_statuses": run.get("node_statuses") or {},
                "events_count": len(snapshot.get("events") or []),
                "results_count": len(results),
            },
            "event_replay_consistency": consistency,
            "mode_results": mode_results,
        },
        failures,
    )


def _event_replay_consistency(snapshot: dict[str, Any]) -> dict[str, Any]:
    run = snapshot.get("run") or {}
    events = list(snapshot.get("events") or [])
    replayed_status = "queued"
    replayed_nodes: dict[str, str] = {}
    for event in events:
        event_type = str(event.get("type") or "")
        node_id = str(event.get("node_id") or "").strip()
        if event_type == "run.running":
            replayed_status = "running"
        elif event_type == "run.succeeded":
            replayed_status = "succeeded"
        elif event_type == "run.failed":
            replayed_status = "failed"
        elif event_type == "node.running" and node_id:
            replayed_nodes[node_id] = "running"
        elif event_type == "node.succeeded" and node_id:
            replayed_nodes[node_id] = "succeeded"
        elif event_type == "node.failed" and node_id:
            replayed_nodes[node_id] = "failed"

    stored_status = str(run.get("status") or "queued")
    stored_nodes = {str(key): str(value) for key, value in (run.get("node_statuses") or {}).items()}
    issues = []
    if stored_status != replayed_status:
        issues.append(
            {
                "code": "run_status_mismatch",
                "stored": stored_status,
                "replayed": replayed_status,
            }
        )
    for node_id in sorted(set(stored_nodes) | set(replayed_nodes)):
        if stored_nodes.get(node_id) != replayed_nodes.get(node_id):
            issues.append(
                {
                    "code": "node_status_mismatch",
                    "node_id": node_id,
                    "stored": stored_nodes.get(node_id),
                    "replayed": replayed_nodes.get(node_id),
                }
            )
    return {
        "contract_version": "workflow_graph.replay_consistency.v1",
        "consistent": not issues,
        "issue_count": len(issues),
        "stored_status": stored_status,
        "replayed_status": replayed_status,
        "issues": issues,
    }


def _source_marker_check(path: Path, markers: tuple[str, ...]) -> dict[str, Any]:
    row = {
        "path": display_path(path),
        "exists": path.exists(),
        "markers": list(markers),
        "missing_markers": list(markers),
        "status": "missing",
    }
    if not path.exists():
        return row
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        row["status"] = "failed"
        row["failures"] = [str(exc)]
        return row
    missing = [marker for marker in markers if marker not in text]
    row["missing_markers"] = missing
    row["status"] = "passed" if not missing else "failed"
    return row


def _api_envelope_readback(node_replay: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        from app.api import workflow_graph as workflow_graph_api
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed",
            "failures": [f"workflow_graph API normalizers unavailable: {exc}"],
            "rows": rows,
        }

    run = node_replay.get("run") or {}
    node_statuses = dict(run.get("node_statuses") or {})
    samples = {
        "compile": workflow_graph_api._normalize_compile(  # noqa: SLF001
            {
                "graph_id": node_replay.get("workflow_graph", {}).get("graph_id"),
                "version": node_replay.get("workflow_graph", {}).get("version"),
                "checksum": node_replay.get("workflow_graph", {}).get("checksum"),
                "topo_order": node_replay.get("workflow_graph", {}).get("topo_order"),
                "warnings": [],
            }
        ),
        "run": workflow_graph_api._normalize_run(  # noqa: SLF001
            {
                "run_id": run.get("run_id"),
                "status": run.get("status"),
                "node_statuses": node_statuses,
                "session_id": "wave55-repo-local-session",
                "current_phase": "verification",
                "compat_mode": False,
            }
        ),
        "run_detail": workflow_graph_api._normalize_run_detail(  # noqa: SLF001
            {
                "run_id": run.get("run_id"),
                "status": run.get("status"),
                "node_statuses": node_statuses,
                "replay_mode": "stateful",
            }
        ),
        "run_events": workflow_graph_api._normalize_run_events(  # noqa: SLF001
            {
                "items": [{"type": "run.succeeded", "node_id": None}],
                "session_id": "wave55-repo-local-session",
            }
        ),
    }

    for name, sample in samples.items():
        status = "passed"
        sample_failures: list[str] = []
        if sample.get("contract_version") != "workflow_graph.v2":
            sample_failures.append("contract_version expected workflow_graph.v2")
        if name in {"run", "run_detail"} and sample.get("nodes") != node_statuses:
            sample_failures.append("nodes alias must mirror node_statuses")
        if name == "run_events" and sample.get("total") != len(sample.get("items") or []):
            sample_failures.append("run_events.total must mirror items length")
        if sample_failures:
            status = "failed"
            failures.extend(f"{name}: {failure}" for failure in sample_failures)
        rows.append(
            {
                "name": name,
                "status": status,
                "contract_version": sample.get("contract_version"),
                "failures": sample_failures,
            }
        )
    return {
        "status": "passed" if not failures else "failed",
        "failures": failures,
        "rows": rows,
    }


def _repo_local_platform_io_contract_readback(node_replay: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    run = node_replay.get("run") or {}
    workflow_graph = node_replay.get("workflow_graph") or {}
    mode_results = list(node_replay.get("mode_results") or [])
    event_consistency = node_replay.get("event_replay_consistency") or {}

    if node_replay.get("status") != "passed":
        failures.append("node manifest replay must pass before platform IO SLA readback")
    if run.get("status") != "succeeded":
        failures.append(f"run.status expected succeeded, got {run.get('status')!r}")
    if event_consistency.get("consistent") is not True:
        failures.append("event replay consistency must be true")
    expected_event_floor = 3 + (2 * len(REQUIRED_MODES))
    if int(run.get("events_count") or 0) < expected_event_floor:
        failures.append(f"run.events_count below scheduler/event floor {expected_event_floor}")
    if workflow_graph.get("node_count") != len(REQUIRED_MODES):
        failures.append("workflow graph node_count must match required manifest modes")

    tenant_rows: list[dict[str, Any]] = []
    for row in mode_results:
        mode = str(row.get("mode") or "")
        io_keys = set(str(key) for key in (row.get("io_trace_keys") or []))
        row_failures: list[str] = []
        for key in ("project_id", "provider_manifest_version", "query"):
            if key not in io_keys:
                row_failures.append(f"io_trace missing {key}")
        if row.get("manifest_consumed") is not True:
            row_failures.append("manifest_consumed must be true")
        if row_failures:
            failures.extend(f"{mode}: {failure}" for failure in row_failures)
        tenant_rows.append(
            {
                "mode": mode,
                "status": "passed" if not row_failures else "failed",
                "tenant_project_scope_readback": "project_id" in io_keys,
                "provider_manifest_version_readback": "provider_manifest_version" in io_keys,
                "failures": row_failures,
            }
        )

    api_envelope = _api_envelope_readback(node_replay)
    failures.extend(f"api_envelope_readback: {failure}" for failure in api_envelope.get("failures") or [])

    source_checks = {
        "graph_workflow_domain": _source_marker_check(
            FRONTEND_WORKFLOW_API_PATH,
            FRONTEND_REQUIRED_MARKERS["graph_workflow_domain"],
        ),
        "llm_designer_consumer": _source_marker_check(
            FRONTEND_LLM_DESIGNER_PATH,
            FRONTEND_REQUIRED_MARKERS["llm_designer_consumer"],
        ),
        "workflow_endpoints": _source_marker_check(
            FRONTEND_ENDPOINTS_PATH,
            FRONTEND_REQUIRED_MARKERS["workflow_endpoints"],
        ),
    }
    for name, row in source_checks.items():
        if row.get("status") != "passed":
            missing = ", ".join(row.get("missing_markers") or [])
            failures.append(f"frontend_source_check:{name}: missing {missing or 'source file'}")

    return {
        "contract_version": "wave55-oss-node-platform-io-local-contract.v1",
        "status": "passed" if not failures else "failed",
        "scheduler_run_store_readback": {
            "run_id": run.get("run_id"),
            "run_status": run.get("status"),
            "events_count": run.get("events_count"),
            "event_replay_consistent": event_consistency.get("consistent"),
            "event_floor": expected_event_floor,
        },
        "tenant_project_scope_rows": tenant_rows,
        "api_envelope_readback": api_envelope,
        "frontend_source_checks": source_checks,
        "failures": failures,
    }


def _join_url(base: str, path: str) -> str:
    return f"{str(base).rstrip('/')}/{path.lstrip('/')}"


def _http_json(
    *,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json", **dict(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=request_headers, method=method.upper())
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local validation URL is operator supplied.
        status_code = int(response.getcode())
        raw = response.read().decode("utf-8")
    return status_code, json.loads(raw or "{}")


def _http_text(*, url: str, timeout: float) -> tuple[int, str]:
    request = Request(url, headers={"Accept": "text/html,application/xhtml+xml"}, method="GET")
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - local validation URL is operator supplied.
        status_code = int(response.getcode())
        raw = response.read().decode("utf-8", errors="replace")
    return status_code, raw


def _run_live_platform_probe(
    *,
    live_api_base: str | None,
    live_ui_base: str | None,
    timeout: float,
) -> dict[str, Any]:
    api_base = str(live_api_base or "").strip()
    ui_base = str(live_ui_base or "").strip()
    if not api_base and not ui_base:
        return {
            "status": "not_requested",
            "platform_io_live_sla_closed": False,
            "failures": [],
            "api_base": None,
            "ui_base": None,
        }
    failures: list[str] = []
    if not api_base:
        failures.append("live_api_base is required for live platform SLA closure")
    if not ui_base:
        failures.append("live_ui_base is required for live platform SLA closure")
    if failures:
        return {
            "status": "failed",
            "platform_io_live_sla_closed": False,
            "failures": failures,
            "api_base": api_base or None,
            "ui_base": ui_base or None,
        }

    headers = {
        "X-Project-Key": "wave55_oss_node_platform_io",
        "X-Request-Id": "wave55-oss-node-platform-io-sla",
    }
    graph_id = "wave55-oss-node-platform-io-live-sla"
    run_id = "wave55-oss-node-platform-io-live-sla-run"
    compile_payload = {
        "graph_id": graph_id,
        "dsl": {
            "version": "1.0",
            "options": {"source": "wave55_live_platform_probe"},
            "nodes": [
                {
                    "node_id": "vector_live_probe",
                    "node_type": "vector_search",
                    "config": {
                        "query": "wave55 oss node platform io live sla",
                        "top_k": 1,
                        "input_vars": [
                            {"name": "query", "source": "input", "required": True},
                            {
                                "name": "project_id",
                                "source": "constant",
                                "default_value": "wave55_oss_node_platform_io",
                            },
                        ],
                    },
                }
            ],
            "edges": [],
        },
    }
    run_payload = {
        "graph_id": graph_id,
        "run_id": run_id,
        "project_key": "wave55_oss_node_platform_io",
        "input": {"query": "wave55 oss node platform io live sla", "state": "CA"},
    }

    api_rows: list[dict[str, Any]] = []
    ui_validated = False
    try:
        compile_code, compile_body = _http_json(
            method="POST",
            url=_join_url(api_base, "workflow-graph/compile"),
            payload=compile_payload,
            headers=headers,
            timeout=timeout,
        )
        api_rows.append({"step": "compile", "status_code": compile_code, "status": compile_body.get("status")})
        compiled_graph_id = str((compile_body.get("data") or {}).get("graph_id") or "")
        if compile_code != 200 or compile_body.get("status") != "ok" or compiled_graph_id != graph_id:
            failures.append("live compile envelope did not return expected graph_id/status")

        run_code, run_body = _http_json(
            method="POST",
            url=_join_url(api_base, "workflow-graph/run"),
            payload=run_payload,
            headers=headers,
            timeout=timeout,
        )
        run_data = run_body.get("data") or {}
        api_rows.append(
            {
                "step": "run",
                "status_code": run_code,
                "status": run_body.get("status"),
                "run_status": run_data.get("status"),
                "session_id_present": bool(run_data.get("session_id")),
            }
        )
        if run_code != 200 or run_body.get("status") != "ok" or run_data.get("status") != "succeeded":
            failures.append("live run envelope did not return succeeded status")
        if not run_data.get("session_id"):
            failures.append("live run did not project a workflow_graph agent session")

        detail_code, detail_body = _http_json(
            method="GET",
            url=_join_url(api_base, f"workflow-graph/runs/{run_id}"),
            headers=headers,
            timeout=timeout,
        )
        detail_data = detail_body.get("data") or {}
        api_rows.append(
            {
                "step": "get_run",
                "status_code": detail_code,
                "status": detail_body.get("status"),
                "run_status": detail_data.get("status"),
                "session_id_present": bool(detail_data.get("session_id")),
            }
        )
        if detail_code != 200 or detail_body.get("status") != "ok" or detail_data.get("status") != "succeeded":
            failures.append("live run detail readback failed")
        if not detail_data.get("session_id"):
            failures.append("live run detail missing session_id readback")

        events_code, events_body = _http_json(
            method="GET",
            url=_join_url(api_base, f"workflow-graph/runs/{run_id}/events"),
            headers=headers,
            timeout=timeout,
        )
        events_data = events_body.get("data") or {}
        events = list(events_data.get("items") or [])
        api_rows.append(
            {
                "step": "get_events",
                "status_code": events_code,
                "status": events_body.get("status"),
                "events_count": len(events),
            }
        )
        if events_code != 200 or events_body.get("status") != "ok" or not events:
            failures.append("live run events readback failed")

        replay_code, replay_body = _http_json(
            method="GET",
            url=_join_url(api_base, f"workflow-graph/runs/{run_id}/replay?replay_mode=stateful"),
            headers=headers,
            timeout=timeout,
        )
        replay_data = replay_body.get("data") or {}
        replay_consistency = replay_data.get("replay_consistency") or {}
        api_rows.append(
            {
                "step": "replay_stateful",
                "status_code": replay_code,
                "status": replay_body.get("status"),
                "run_status": replay_data.get("status"),
                "replay_consistent": replay_consistency.get("consistent"),
            }
        )
        if replay_code != 200 or replay_body.get("status") != "ok" or replay_data.get("status") != "succeeded":
            failures.append("live replay readback failed")
        if replay_consistency.get("consistent") is not True:
            failures.append("live replay consistency failed")

        compiled_code, compiled_body = _http_json(
            method="GET",
            url=_join_url(api_base, f"workflow-graph/compiled/{graph_id}"),
            headers=headers,
            timeout=timeout,
        )
        api_rows.append(
            {
                "step": "get_compiled",
                "status_code": compiled_code,
                "status": compiled_body.get("status"),
                "graph_id": (compiled_body.get("data") or {}).get("graph_id"),
            }
        )
        if compiled_code != 200 or compiled_body.get("status") != "ok":
            failures.append("live compiled graph readback failed")

        ui_code, ui_text = _http_text(url=ui_base, timeout=timeout)
        ui_markers = ("id=\"root\"", "type=\"module\"", "/src/")
        missing_ui_markers = [marker for marker in ui_markers if marker not in ui_text]
        if ui_code != 200:
            failures.append(f"live UI returned HTTP {ui_code}")
        if missing_ui_markers:
            failures.append(f"live UI missing markers: {missing_ui_markers}")
        ui_validated = ui_code == 200 and not missing_ui_markers
    except HTTPError as exc:
        failures.append(f"HTTP {exc.code} while probing live platform: {exc.reason}")
    except URLError as exc:
        failures.append(f"URL error while probing live platform: {exc.reason}")
    except TimeoutError as exc:
        failures.append(f"timeout while probing live platform: {exc}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"unexpected live platform probe error: {exc}")

    return {
        "contract_version": "wave55-oss-node-platform-io-live-probe.v1",
        "status": "passed" if not failures else "failed",
        "platform_io_live_sla_closed": not failures,
        "api_base": api_base,
        "ui_base": ui_base,
        "api_rows": api_rows,
        "ui_probe": {
            "url": ui_base,
            "validated": ui_validated,
        },
        "failures": failures,
    }


def _run_platform_io_sla_readback(
    node_replay: dict[str, Any],
    *,
    live_api_base: str | None = None,
    live_ui_base: str | None = None,
    live_probe_timeout: float = 2.0,
) -> tuple[dict[str, Any], list[str]]:
    repo_local = _repo_local_platform_io_contract_readback(node_replay)
    live_probe = _run_live_platform_probe(
        live_api_base=live_api_base,
        live_ui_base=live_ui_base,
        timeout=live_probe_timeout,
    )
    failures = [f"repo_local_contract: {failure}" for failure in repo_local.get("failures") or []]
    live_probe_requested = live_probe.get("status") != "not_requested"
    if live_probe_requested:
        failures.extend(f"live_probe: {failure}" for failure in live_probe.get("failures") or [])
    platform_io_live_sla_closed = bool(
        repo_local.get("status") == "passed" and live_probe.get("platform_io_live_sla_closed") is True
    )
    return (
        {
            "contract_version": WAVE55_PLATFORM_IO_CONTRACT_VERSION,
            "status": "passed" if not failures else "failed",
            "repo_local_contract": repo_local,
            "live_probe": live_probe,
            "live_probe_requested": live_probe_requested,
            "platform_io_live_sla_closed": platform_io_live_sla_closed,
            "closed_condition": PLATFORM_IO_LIVE_SLA_CONDITION if platform_io_live_sla_closed else None,
            "closure_position": (
                "scheduler_tenant_db_ui_live_sla_validated"
                if platform_io_live_sla_closed
                else "repo_local_platform_io_readback_ready_live_probe_not_closed"
            ),
            "failures": failures,
        },
        failures,
    )


def _retained_external_conditions(*, platform_io_live_sla_closed: bool) -> list[str]:
    retained = list(PROVIDER_EXTERNAL_CONDITIONS)
    if not platform_io_live_sla_closed:
        retained.append(PLATFORM_IO_LIVE_SLA_CONDITION)
    return retained


def build_contract(
    *,
    provider_manifest_path: Path | None = None,
    live_api_base: str | None = None,
    live_ui_base: str | None = None,
    live_probe_timeout: float = 2.0,
) -> dict[str, Any]:
    resolved_manifest_path = provider_manifest_path or DEFAULT_PROVIDER_MANIFEST
    provider_manifest, source_row = _load_json(resolved_manifest_path)
    failures = list(source_row.get("failures") or [])

    provider_manifest_check, manifest_failures = _validate_provider_manifest(provider_manifest)
    failures.extend(f"provider_manifest_check: {failure}" for failure in manifest_failures)

    node_replay, replay_failures = _run_node_manifest_replay(provider_manifest) if not manifest_failures else ({}, [])
    failures.extend(f"node_manifest_replay: {failure}" for failure in replay_failures)
    platform_io_sla_readback, platform_failures = (
        _run_platform_io_sla_readback(
            node_replay,
            live_api_base=live_api_base,
            live_ui_base=live_ui_base,
            live_probe_timeout=live_probe_timeout,
        )
        if node_replay
        else ({}, [])
    )
    failures.extend(f"platform_io_sla_readback: {failure}" for failure in platform_failures)

    topic_path = REPO_ROOT / TARGET_TOPIC
    if not topic_path.exists():
        failures.append(f"target topic missing: {TARGET_TOPIC}")

    status = "passed" if not failures else "failed"
    archive_external_blocked_candidate = status == "passed"
    platform_io_live_sla_closed = bool(platform_io_sla_readback.get("platform_io_live_sla_closed"))
    external_conditions_retained = _retained_external_conditions(
        platform_io_live_sla_closed=platform_io_live_sla_closed
    )
    return {
        "contract_version": "wave29-oss-node-vector-manifest-replay.v1",
        "generated_by": "ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py",
        "status": status,
        "scope": "oss_node_vector_manifest_replay_with_wave55_platform_io_sla_readback",
        "target_topic": {
            "path": TARGET_TOPIC,
            "exists": topic_path.exists(),
        },
        "source_provider_manifest": source_row,
        "provider_manifest_check": provider_manifest_check,
        "node_manifest_replay": node_replay,
        "platform_io_sla_readback": platform_io_sla_readback,
        "repo_local_closure": {
            "repo_local_blockers_closed": list(REPO_LOCAL_BLOCKERS_CLOSED) if status == "passed" else [],
            "remaining_repo_local_blockers": [] if status == "passed" else list(REPO_LOCAL_BLOCKERS_CLOSED),
            "archive_external_blocked_candidate": archive_external_blocked_candidate,
            "platform_io_sla_readback_attached": (
                platform_io_sla_readback.get("repo_local_contract", {}).get("status") == "passed"
            ),
            "platform_io_live_sla_closed": platform_io_live_sla_closed,
        },
        "external_conditions_retained": external_conditions_retained,
        "gate_semantics": {
            "status_passed_means": (
                "the workflow graph compiler, node runtime, normalized result envelope, event log, "
                "event replay, tenant project-scope IO trace, workflow API envelope, and frontend "
                "workflow client binding can consume all keyword/vector/hybrid provider manifest rows; "
                "when live API/UI bases are supplied, the live workflow run/readback/UI asset probe also passed"
            ),
            "status_passed_does_not_mean": (
                "external embedding provider quality, local open-search relevance, or production semantic "
                "quality are closed; if live API/UI bases were omitted, scheduler/tenant DB/UI live SLA "
                "closure is not claimed"
            ),
        },
        "archive_recommendation": (
            "move this topic to ARCHIVE_EXTERNAL_BLOCKED in the supervisor/index lane"
            if archive_external_blocked_candidate
            else "retain in CURRENT_DEV with the listed repo-local blockers"
        ),
        "failures": failures,
    }


def write_outputs(out_dir: Path, contract: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "oss_node_vector_manifest_replay.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    mode_rows = []
    for row in contract.get("node_manifest_replay", {}).get("mode_results", []):
        mode_rows.append(
            "| {mode} | {status} | {provider_id} | {manifest_consumed} | {closure} | {live} | {semantic} |".format(
                mode=row.get("mode"),
                status=f"`{row.get('status')}`",
                provider_id=f"`{row.get('provider_id')}`",
                manifest_consumed=str(bool(row.get("manifest_consumed"))).lower(),
                closure=str(bool(row.get("closure_claim_allowed"))).lower(),
                live=str(bool(row.get("live_provider_verified"))).lower(),
                semantic=str(bool(row.get("semantic_quality_claim_allowed"))).lower(),
            )
        )

    closed_rows = [
        f"- `{code}`"
        for code in contract.get("repo_local_closure", {}).get("repo_local_blockers_closed", [])
    ]
    external_rows = [f"- `{code}`" for code in contract.get("external_conditions_retained", [])]
    if not external_rows:
        external_rows = ["- none"]
    platform_readback = contract.get("platform_io_sla_readback", {}) or {}
    repo_local_platform = platform_readback.get("repo_local_contract", {}) or {}
    live_probe = platform_readback.get("live_probe", {}) or {}

    readme = [
        "# Wave29 OSS Node Vector Manifest Replay",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- archive_external_blocked_candidate: `{str(bool(contract['repo_local_closure']['archive_external_blocked_candidate'])).lower()}`",
        f"- platform_io_live_sla_closed: `{str(bool(contract['repo_local_closure'].get('platform_io_live_sla_closed'))).lower()}`",
        "",
        "## Node Replay Matrix",
        "",
        "| mode | status | provider_id | manifest_consumed | closure_claim_allowed | live_provider_verified | semantic_quality_claim_allowed |",
        "|---|---|---|---:|---:|---:|---:|",
        *mode_rows,
        "",
        "## Repo-Local Blockers Closed",
        "",
        *closed_rows,
        "",
        "## Wave55 Platform IO SLA Readback",
        "",
        f"- contract_version: `{platform_readback.get('contract_version')}`",
        f"- status: `{platform_readback.get('status')}`",
        f"- repo_local_contract: `{repo_local_platform.get('status')}`",
        f"- live_probe: `{live_probe.get('status')}`",
        f"- live_probe_requested: `{str(bool(platform_readback.get('live_probe_requested'))).lower()}`",
        f"- platform_io_live_sla_closed: `{str(bool(platform_readback.get('platform_io_live_sla_closed'))).lower()}`",
        f"- closure_position: `{platform_readback.get('closure_position')}`",
        "",
        "## External Conditions Retained",
        "",
        *external_rows,
        "",
        "## Gate Semantics",
        "",
        f"- status passed means: {contract['gate_semantics']['status_passed_means']}",
        f"- status passed does not mean: {contract['gate_semantics']['status_passed_does_not_mean']}",
        "",
        "## Rerun",
        "",
        "```bash",
        f"PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py --out-dir {display_path(out_dir)}",
        f"PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py --out-dir {display_path(out_dir)} --live-api-base http://127.0.0.1:8000/api/v1 --live-ui-base http://127.0.0.1:5173/",
        "PYTHONPATH=main/backend /Users/wangyiliang/.local/bin/python3.11 -m pytest -q main/backend/tests/unit/test_wave29_oss_node_vector_manifest_replay_unittest.py",
        "```",
        "",
        "Full deterministic output is in `oss_node_vector_manifest_replay.json`.",
        "",
    ]
    (out_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-manifest", default=str(DEFAULT_PROVIDER_MANIFEST))
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--live-api-base", default="")
    parser.add_argument("--live-ui-base", default="")
    parser.add_argument("--live-probe-timeout", type=float, default=2.0)
    args = parser.parse_args()

    provider_manifest_path = Path(args.provider_manifest)
    if not provider_manifest_path.is_absolute():
        provider_manifest_path = REPO_ROOT / provider_manifest_path
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir

    contract = build_contract(
        provider_manifest_path=provider_manifest_path,
        live_api_base=args.live_api_base,
        live_ui_base=args.live_ui_base,
        live_probe_timeout=args.live_probe_timeout,
    )
    write_outputs(out_dir, contract)
    print(
        json.dumps(
            {
                "status": contract["status"],
                "contract_version": contract["contract_version"],
                "archive_external_blocked_candidate": contract["repo_local_closure"][
                    "archive_external_blocked_candidate"
                ],
                "closed_repo_local_blockers": contract["repo_local_closure"]["repo_local_blockers_closed"],
                "platform_io_live_sla_closed": contract["repo_local_closure"]["platform_io_live_sla_closed"],
                "external_conditions_retained": contract["external_conditions_retained"],
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
