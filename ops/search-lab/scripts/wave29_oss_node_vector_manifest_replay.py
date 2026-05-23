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
TARGET_EXTERNAL_CONDITIONS = (
    "external_embedding_provider_live_not_verified",
    "local_open_search_live_quality_not_sealed",
    "semantic_embedding_quality_not_proven",
    "live_scheduler_tenant_db_ui_sla_not_proven",
)
REPO_LOCAL_BLOCKERS_CLOSED = (
    "node_schema_runtime_persistence_platformization_scope_not_closed",
    "vector_search_node_manifest_consumption_not_live_replayed",
)


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


def build_contract(*, provider_manifest_path: Path | None = None) -> dict[str, Any]:
    resolved_manifest_path = provider_manifest_path or DEFAULT_PROVIDER_MANIFEST
    provider_manifest, source_row = _load_json(resolved_manifest_path)
    failures = list(source_row.get("failures") or [])

    provider_manifest_check, manifest_failures = _validate_provider_manifest(provider_manifest)
    failures.extend(f"provider_manifest_check: {failure}" for failure in manifest_failures)

    node_replay, replay_failures = _run_node_manifest_replay(provider_manifest) if not manifest_failures else ({}, [])
    failures.extend(f"node_manifest_replay: {failure}" for failure in replay_failures)

    topic_path = REPO_ROOT / TARGET_TOPIC
    if not topic_path.exists():
        failures.append(f"target topic missing: {TARGET_TOPIC}")

    status = "passed" if not failures else "failed"
    archive_external_blocked_candidate = status == "passed"
    return {
        "contract_version": "wave29-oss-node-vector-manifest-replay.v1",
        "generated_by": "ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py",
        "status": status,
        "scope": "oss_node_vector_manifest_fixture_replay_no_live_provider_no_tenant_runtime",
        "target_topic": {
            "path": TARGET_TOPIC,
            "exists": topic_path.exists(),
        },
        "source_provider_manifest": source_row,
        "provider_manifest_check": provider_manifest_check,
        "node_manifest_replay": node_replay,
        "repo_local_closure": {
            "repo_local_blockers_closed": list(REPO_LOCAL_BLOCKERS_CLOSED) if status == "passed" else [],
            "remaining_repo_local_blockers": [] if status == "passed" else list(REPO_LOCAL_BLOCKERS_CLOSED),
            "archive_external_blocked_candidate": archive_external_blocked_candidate,
        },
        "external_conditions_retained": list(TARGET_EXTERNAL_CONDITIONS),
        "gate_semantics": {
            "status_passed_means": (
                "the workflow graph compiler, node runtime, normalized result envelope, event log, "
                "and event replay can consume all keyword/vector/hybrid provider manifest rows while "
                "preserving unsupported closure claims"
            ),
            "status_passed_does_not_mean": (
                "external embedding providers, local open-search live quality, semantic relevance, "
                "tenant DB persistence, scheduler SLA, or browser UI SLA are closed"
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

    readme = [
        "# Wave29 OSS Node Vector Manifest Replay",
        "",
        f"- status: `{contract['status']}`",
        f"- contract_version: `{contract['contract_version']}`",
        f"- scope: `{contract['scope']}`",
        f"- archive_external_blocked_candidate: `{str(bool(contract['repo_local_closure']['archive_external_blocked_candidate'])).lower()}`",
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
    args = parser.parse_args()

    provider_manifest_path = Path(args.provider_manifest)
    if not provider_manifest_path.is_absolute():
        provider_manifest_path = REPO_ROOT / provider_manifest_path
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir

    contract = build_contract(provider_manifest_path=provider_manifest_path)
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
                "out_dir": display_path(out_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
