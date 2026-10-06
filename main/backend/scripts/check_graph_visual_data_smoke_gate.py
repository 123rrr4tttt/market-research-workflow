#!/usr/bin/env python3
"""Gate Graph 3D visual data smoke boundaries without live UI closure claims."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Annotated, Any


CONTRACT_VERSION = "graph.visual_data_smoke_gate.v1"

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ROOT = REPO_ROOT / "main" / "frontend-modern"
BACKEND_ROOT = REPO_ROOT / "main" / "backend"

BACKEND_DATA_EVIDENCE_FIELDS = (
    "backend_data_visual_smoke_validated",
    "backend_data_source_live",
    "response_envelope_success",
    "nodes_nonempty",
    "edges_nonempty",
    "graph_schema_version_present",
)

LIVE_UI_EVIDENCE_FIELDS = (
    "live_ui_smoke_validated",
    "backend_data_source_live",
    "graphpage_loaded_from_backend_endpoint",
    "force3d_canvas_nonblank",
    "force3d_scene_nodes_match_data",
    "graph3d_debug_stats_captured",
)


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_evidence_read_error": str(exc)}
    return data if isinstance(data, dict) else {"_evidence_read_error": "evidence JSON must be an object"}


def _contains_all(source: str, needles: tuple[str, ...]) -> bool:
    return all(needle in source for needle in needles)


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _python_functions(source: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _called_paths(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    return {
        _qualified_name(node.func)
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and _qualified_name(node.func)
    }


def _string_constants(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    return {
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _route_paths(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    paths: set[str] = set()
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call) or _qualified_name(decorator.func) != "router.get":
            continue
        if decorator.args and isinstance(decorator.args[0], ast.Constant) and isinstance(decorator.args[0].value, str):
            paths.add(decorator.args[0].value)
    return paths


def _admin_graph_routes_delegate_to_owner(admin_source: str) -> bool:
    functions = _python_functions(admin_source)
    expected = {
        "get_market_graph": ("/market-graph", "document_admin.get_admin_market_graph"),
        "get_policy_graph": ("/policy-graph", "document_admin.get_admin_policy_graph"),
        "get_content_graph": ("/content-graph", "document_admin.get_admin_content_graph"),
    }
    return all(
        (function := functions.get(name)) is not None
        and route_path in _route_paths(function)
        and owner_call in _called_paths(function)
        for name, (route_path, owner_call) in expected.items()
    )


def _document_admin_keeps_b_read_fallback(owner_source: str) -> bool:
    functions = _python_functions(owner_source)
    finalize = functions.get("_finalize_admin_graph")
    if finalize is None:
        return False
    calls = _called_paths(finalize)
    messages = _string_constants(finalize)
    consumers = ("get_admin_content_graph", "get_admin_market_graph", "get_admin_policy_graph")
    return (
        "GraphNodeReader" in calls
        and "_rollback_graph_session" in calls
        and "_export_graph" in calls
        and any("graph_b_read_fallback_to_a" in message for message in messages)
        and all(
            (consumer := functions.get(name)) is not None
            and "_finalize_admin_graph" in _called_paths(consumer)
            for name in consumers
        )
    )


def _fixture_graph_payload() -> dict[str, Any]:
    return {
        "graph_schema_version": "v1",
        "nodes": [
            {"type": "Post", "id": "42", "properties": {"title": "Projection Fixture"}},
            {"type": "Entity", "id": "ACME Corp", "properties": {"name": "ACME Corp"}},
            {"type": "Keyword", "id": "Graph 3D", "properties": {"label": "Graph 3D"}},
        ],
        "edges": [
            {
                "type": "MENTIONS_ENTITY",
                "from": {"type": "Post", "id": "42"},
                "to": {"type": "Entity", "id": "ACME Corp"},
                "properties": {"weight": 1.0},
            },
            {
                "type": "MENTIONS_KEYWORD",
                "from": {"type": "Post", "id": "42"},
                "to": {"type": "Keyword", "id": "Graph 3D"},
                "properties": {"weight": 1.0},
            },
        ],
    }


def _node_key(node: dict[str, Any]) -> str:
    return f"{str(node.get('type') or '').strip()}:{str(node.get('id') or '').strip()}"


def _edge_endpoint_key(edge: dict[str, Any], endpoint: str) -> str:
    raw = edge.get(endpoint)
    if not isinstance(raw, dict):
        return ""
    return _node_key(raw)


def validate_visual_graph_payload(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["graph payload must be an object"]

    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not nodes:
        failures.append("graph payload must include nonempty nodes")
        nodes = []
    if not isinstance(edges, list) or not edges:
        failures.append("graph payload must include nonempty edges")
        edges = []
    if not str(payload.get("graph_schema_version") or "").strip():
        failures.append("graph payload must include graph_schema_version")

    node_keys: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            failures.append(f"nodes[{index}] must be an object")
            continue
        key = _node_key(node)
        if key == ":":
            failures.append(f"nodes[{index}] must include type and id")
            continue
        if key in node_keys:
            failures.append(f"duplicate visual node key: {key}")
        node_keys.add(key)

    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            failures.append(f"edges[{index}] must be an object")
            continue
        if not str(edge.get("type") or "").strip():
            failures.append(f"edges[{index}] must include type")
        from_key = _edge_endpoint_key(edge, "from")
        to_key = _edge_endpoint_key(edge, "to")
        if from_key not in node_keys:
            failures.append(f"edges[{index}] unresolved from endpoint: {from_key or '<missing>'}")
        if to_key not in node_keys:
            failures.append(f"edges[{index}] unresolved to endpoint: {to_key or '<missing>'}")
    return failures


def _extract_graph_payload(evidence: dict[str, Any] | None) -> dict[str, Any] | None:
    if not evidence:
        return None
    for key in ("graph_payload", "payload", "data"):
        value = evidence.get(key)
        if isinstance(value, dict):
            return value
    response = evidence.get("response")
    if isinstance(response, dict):
        data = response.get("data")
        if isinstance(data, dict):
            return data
    return None


def _missing_true_fields(evidence: dict[str, Any] | None, fields: tuple[str, ...]) -> list[str]:
    if not evidence:
        return list(fields)
    return [field for field in fields if evidence.get(field) is not True]


def _failed_check_names(checks: dict[str, bool]) -> list[str]:
    return sorted(name for name, passed in checks.items() if not passed)


def backend_data_static_checks(repo_root: Path = REPO_ROOT) -> dict[str, bool]:
    admin_source = _read_file(repo_root / "main" / "backend" / "app" / "api" / "admin.py")
    document_admin_source = _read_file(
        repo_root / "main" / "backend" / "app" / "services" / "document_admin.py"
    )
    endpoints_source = _read_file(repo_root / "main" / "frontend-modern" / "src" / "lib" / "api" / "endpoints.ts")
    graph_api_source = _read_file(
        repo_root / "main" / "frontend-modern" / "src" / "lib" / "api" / "domains" / "graph-workflow.ts"
    )
    graph_page_source = _read_file(repo_root / "main" / "frontend-modern" / "src" / "pages" / "GraphPage.tsx")
    topology_source = _read_file(
        repo_root / "main" / "frontend-modern" / "src" / "pages" / "graph" / "domain" / "topology.ts"
    )
    force3d_objects_source = _read_file(
        repo_root / "main" / "frontend-modern" / "src" / "pages" / "graph" / "renderers" / "force3dObjects.ts"
    )
    return {
        "admin_backend_graph_routes_exist": _admin_graph_routes_delegate_to_owner(admin_source),
        "admin_graph_routes_keep_b_read_fallback": _document_admin_keeps_b_read_fallback(
            document_admin_source
        ),
        "frontend_backend_data_endpoints_exist": _contains_all(
            endpoints_source,
            (
                "marketGraph:",
                "policyGraph:",
                "contentGraph:",
                "/admin/market-graph",
                "/admin/policy-graph",
                "/admin/content-graph",
            ),
        ),
        "frontend_backend_data_wrappers_exist": _contains_all(
            graph_api_source,
            (
                "export async function getMarketGraph",
                "export async function getPolicyGraph",
                "export async function getSocialGraph",
                "endpoints.admin.marketGraph",
                "endpoints.admin.policyGraph",
                "endpoints.admin.contentGraph",
            ),
        ),
        "graphpage_maps_backend_nodes_to_force3d_data": _contains_all(
            topology_source,
            (
                "export function computeVisibleSubgraph",
                "connectedNodes",
                "connectedEdges",
                "edgeResolvedKeyMap",
            ),
        )
        and _contains_all(
            force3d_objects_source,
            ("export function createForceNodeObject", "export function linkEnds"),
        )
        and _contains_all(
            graph_page_source,
            (
                "from './graph/domain/topology'",
                "computeVisibleSubgraph({",
                "from './graph/renderers/force3dObjects'",
                "topology.connectedNodes.map",
                "graphData={forceGraphData}",
            ),
        ),
    }


def live_ui_static_checks(frontend_root: Path = FRONTEND_ROOT) -> dict[str, bool]:
    package_source = _read_file(frontend_root / "package.json")
    force_checker_source = _read_file(frontend_root / "scripts" / "check_graph_force3d_frontend_contract.mjs")
    e2e_source = _read_file(frontend_root / "tests" / "e2e" / "graphpage.spec.ts")
    graph_page_source = _read_file(frontend_root / "src" / "pages" / "GraphPage.tsx")
    return {
        "force3d_frontend_contract_script_registered": _contains_all(
            package_source,
            (
                '"check:graph-force3d-frontend-contract"',
                "check_graph_force3d_frontend_contract.mjs",
            ),
        ),
        "force3d_frontend_contract_checker_exists": _contains_all(
            force_checker_source,
            (
                "Graph force3d frontend contract check passed",
                "graph-force3d-canvas-host",
                "__graph3dDebug",
            ),
        ),
        "graphpage_exposes_force3d_live_debug_boundary": _contains_all(
            graph_page_source,
            (
                "window.__graph3dDebug = debugApi",
                "getVisibilityStats: () => force3DVisibilityStatsGetterRef.current()",
                'data-testid="graph-force3d-canvas-host"',
                "collectForce3DVisibilityStats",
            ),
        ),
        "mocked_force3d_e2e_is_present_but_not_live": _contains_all(
            e2e_source,
            (
                "graph page renders force3d canvas backed by graph scene nodes",
                "graph-force3d-canvas-host",
                "__graph3dDebug",
            ),
        ),
    }


def _stage(
    *,
    name: str,
    status: str,
    passed: bool,
    validated: bool,
    detail: str,
    gaps: list[str],
    evidence_required: tuple[str, ...] | list[str] = (),
    failures: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "passed": passed,
        "validated": validated,
        "detail": detail,
        "gaps": gaps,
        "evidence_required": list(evidence_required),
        "failures": failures or [],
    }


def _build_fixture_stage() -> dict[str, Any]:
    payload = _fixture_graph_payload()
    failures = validate_visual_graph_payload(payload)
    return _stage(
        name="fixture_visual_data_smoke",
        status="validated" if not failures else "failed",
        passed=not failures,
        validated=not failures,
        detail=f"repo fixture visual payload nodes={len(payload['nodes'])} edges={len(payload['edges'])}",
        gaps=[] if not failures else ["fixture visual graph payload is invalid"],
        failures=failures,
    )


def _build_backend_data_stage(
    *,
    static_checks: dict[str, bool],
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    static_failures = _failed_check_names(static_checks)
    if static_failures:
        return _stage(
            name="backend_data_visual_smoke",
            status="blocked",
            passed=False,
            validated=False,
            detail=f"static backend-data prerequisites failed: {', '.join(static_failures)}",
            gaps=["backend-data visual smoke is not ready to run"],
            evidence_required=BACKEND_DATA_EVIDENCE_FIELDS,
            failures=static_failures,
        )

    if evidence:
        missing = _missing_true_fields(evidence, BACKEND_DATA_EVIDENCE_FIELDS)
        payload = _extract_graph_payload(evidence)
        payload_failures = (
            validate_visual_graph_payload(payload)
            if isinstance(payload, dict)
            else ["backend-data evidence must include graph_payload, payload, data, or response.data"]
        )
        if not missing and not payload_failures:
            return _stage(
                name="backend_data_visual_smoke",
                status="validated",
                passed=True,
                validated=True,
                detail="backend graph endpoint evidence contains live nonempty nodes/edges visual payload",
                gaps=[],
                evidence_required=BACKEND_DATA_EVIDENCE_FIELDS,
            )
        failures = [*(f"missing_true:{field}" for field in missing), *payload_failures]
        return _stage(
            name="backend_data_visual_smoke",
            status="failed_evidence",
            passed=False,
            validated=False,
            detail="backend-data visual smoke evidence is present but incomplete",
            gaps=[
                "backend-data graph endpoint smoke evidence is incomplete",
                "do not treat fixture payloads as backend-data visual validation",
            ],
            evidence_required=BACKEND_DATA_EVIDENCE_FIELDS,
            failures=failures,
        )

    return _stage(
        name="backend_data_visual_smoke",
        status="ready_not_run",
        passed=True,
        validated=False,
        detail=(
            "admin routes delegate to document_admin, frontend wrappers consume declared endpoints, and GraphPage "
            "consumes native topology/force3d modules; live backend-data payload smoke was not supplied"
        ),
        gaps=[
            "run an admin graph endpoint against nonempty backend data and capture the response payload",
            "prove nodes/edges come from backend data, not only repo fixture data",
        ],
        evidence_required=BACKEND_DATA_EVIDENCE_FIELDS,
    )


def _build_live_ui_stage(
    *,
    static_checks: dict[str, bool],
    backend_stage: dict[str, Any],
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    static_failures = _failed_check_names(static_checks)
    if static_failures:
        return _stage(
            name="live_ui_force3d_smoke",
            status="blocked",
            passed=False,
            validated=False,
            detail=f"static live-UI prerequisites failed: {', '.join(static_failures)}",
            gaps=["live UI force3d smoke is not ready to run"],
            evidence_required=LIVE_UI_EVIDENCE_FIELDS,
            failures=static_failures,
        )

    if evidence:
        missing = _missing_true_fields(evidence, LIVE_UI_EVIDENCE_FIELDS)
        debug_stats = evidence.get("debug_stats")
        debug_failures: list[str] = []
        if isinstance(debug_stats, dict):
            data_nodes = int(debug_stats.get("dataNodes") or 0)
            scene_node_objects = int(debug_stats.get("sceneNodeObjects") or 0)
            if data_nodes <= 0:
                debug_failures.append("debug_stats.dataNodes must be > 0")
            if scene_node_objects < data_nodes:
                debug_failures.append("debug_stats.sceneNodeObjects must be >= dataNodes")
        if not missing and not debug_failures:
            return _stage(
                name="live_ui_force3d_smoke",
                status="validated",
                passed=True,
                validated=True,
                detail="live UI evidence captured nonblank force3d canvas and debug stats from backend data",
                gaps=[],
                evidence_required=LIVE_UI_EVIDENCE_FIELDS,
            )
        failures = [*(f"missing_true:{field}" for field in missing), *debug_failures]
        return _stage(
            name="live_ui_force3d_smoke",
            status="failed_evidence",
            passed=False,
            validated=False,
            detail="live UI evidence is present but incomplete",
            gaps=[
                "live GraphPage force3d evidence is incomplete",
                "do not claim visual closure from backend-data payload alone",
            ],
            evidence_required=LIVE_UI_EVIDENCE_FIELDS,
            failures=failures,
        )

    status = "ready_not_run" if backend_stage["validated"] else "not_run"
    return _stage(
        name="live_ui_force3d_smoke",
        status=status,
        passed=True,
        validated=False,
        detail="live browser GraphPage force3d smoke was not supplied",
        gaps=[
            "run GraphPage in projection3d mode against backend-data graph endpoints",
            "capture nonblank canvas evidence and window.__graph3dDebug visibility stats",
            "unrun live UI smoke keeps this gate partial and non-closing",
        ],
        evidence_required=LIVE_UI_EVIDENCE_FIELDS,
    )


def build_gate_snapshot(
    *,
    repo_root: Path = REPO_ROOT,
    backend_data_evidence: dict[str, Any] | None = None,
    live_ui_evidence: dict[str, Any] | None = None,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence fact_source=visual_data_fixture_smoke+backend_data_static_checks+graphpage_ui_static_checks+backend_data_evidence+live_ui_evidence witness=test:test_c13_cli_graph_workflow_metadata_preserves_abi",
]:
    fixture_stage = _build_fixture_stage()
    backend_stage = _build_backend_data_stage(
        static_checks=backend_data_static_checks(repo_root),
        evidence=backend_data_evidence,
    )
    live_ui_stage = _build_live_ui_stage(
        static_checks=live_ui_static_checks(repo_root / "main" / "frontend-modern"),
        backend_stage=backend_stage,
        evidence=live_ui_evidence,
    )
    stages = [fixture_stage, backend_stage, live_ui_stage]
    hard_failures = [failure for stage in stages if not stage["passed"] for failure in stage["failures"]]
    readiness_state = "live_ui_validated_non_closing" if live_ui_stage["validated"] else "partial"
    boundary = (
        "partial/live-smoke boundary: fixture visual data smoke is deterministic; "
        f"backend-data visual smoke={backend_stage['status']}; "
        f"live UI smoke={live_ui_stage['status']}; "
        "closure_claim=false unless a separate supervisor closure gate archives the topic"
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "passed" if not hard_failures else "failed",
        "readiness_state": readiness_state,
        "closure_claim": False,
        "fixture_smoke_validated": fixture_stage["validated"],
        "backend_data_visual_smoke_validated": backend_stage["validated"],
        "live_ui_smoke_validated": live_ui_stage["validated"],
        "boundary": boundary,
        "stages": stages,
        "remaining_gaps": [gap for stage in stages if not stage["validated"] for gap in stage["gaps"]],
        "hard_failures": hard_failures,
    }


def validate_gate_snapshot(snapshot: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if snapshot.get("contract_version") != CONTRACT_VERSION:
        failures.append("unexpected contract_version")
    if snapshot.get("closure_claim") is not False:
        failures.append("closure_claim must remain false")
    if snapshot.get("fixture_smoke_validated") is not True:
        failures.append("fixture visual smoke must be validated")
    if snapshot.get("live_ui_smoke_validated") is not True and snapshot.get("readiness_state") != "partial":
        failures.append("unvalidated live UI smoke must keep readiness_state=partial")
    if "partial/live-smoke boundary" not in str(snapshot.get("boundary") or ""):
        failures.append("boundary must explicitly mention partial/live-smoke boundary")
    for failure in snapshot.get("hard_failures") or []:
        failures.append(str(failure))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Graph 3D visual data smoke boundaries without treating unrun live UI as closure"
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--backend-data-evidence-json", default="")
    parser.add_argument("--live-ui-evidence-json", default="")
    args = parser.parse_args()

    snapshot = build_gate_snapshot(
        backend_data_evidence=_read_json(args.backend_data_evidence_json),
        live_ui_evidence=_read_json(args.live_ui_evidence_json),
    )
    validation_failures = validate_gate_snapshot(snapshot)
    if validation_failures:
        snapshot = {**snapshot, "status": "failed", "validation_failures": validation_failures}

    if args.format == "json":
        print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
    else:
        print(f"status={snapshot['status']}")
        print(f"readiness_state={snapshot['readiness_state']}")
        print(f"closure_claim={snapshot['closure_claim']}")
        print(snapshot["boundary"])
        for stage in snapshot["stages"]:
            print(f"{stage['name']}={stage['status']} passed={stage['passed']} validated={stage['validated']}")
        if snapshot["remaining_gaps"]:
            print("remaining_gaps:")
            for gap in snapshot["remaining_gaps"]:
                print(f"- {gap}")
        if validation_failures:
            print("validation_failures:")
            for failure in validation_failures:
                print(f"- {failure}")

    return 0 if snapshot["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
