from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..contracts import success_response
from ..services.ingest_config import get_config, upsert_config
from ..project_customization import get_project_customization
from ..services.graph.doc_types import (
    resolve_graph_doc_types,
    resolve_graph_edge_types,
    resolve_graph_field_labels,
    resolve_graph_node_labels,
    resolve_graph_node_types,
    resolve_graph_relation_labels,
    resolve_graph_type_labels,
)
from ..services.projects.workflow import (
    WORKFLOW_PLATFORM_CONFIG_KEY,
    dump_workflow_definition,
    execute_project_workflow,
    load_custom_workflow_board_layout,
    load_custom_workflow_definition,
)

router = APIRouter(prefix="/project-customization", tags=["project-customization"])


class WorkflowRunPayload(BaseModel):
    project_key: str | None = None
    params: dict = Field(default_factory=dict)


class WorkflowStepPayload(BaseModel):
    handler: str
    params: dict = Field(default_factory=dict)
    enabled: bool = Field(default=True)
    name: str | None = Field(default=None)


class WorkflowTemplatePayload(BaseModel):
    project_key: str | None = None
    steps: list[WorkflowStepPayload] = Field(default_factory=list)
    board_layout: dict = Field(default_factory=dict)


def _coerce_workflow_payload(raw_payload: dict | None) -> tuple[dict[str, dict], dict[str, dict], int]:
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    workflows = payload.get("workflows")
    boards = payload.get("boards")
    version_raw = payload.get("version", 0)
    try:
        version = int(version_raw) if version_raw is not None else 0
    except (TypeError, ValueError):
        version = 0
    return (
        workflows if isinstance(workflows, dict) else {},
        boards if isinstance(boards, dict) else {},
        version if version >= 0 else 0,
    )


def _infer_node_module_from_handler(handler: str) -> str:
    handler = str(handler or "").strip()
    if handler == "ingest.market":
        return "search_market"
    if handler == "ingest.policy":
        return "search_policy"
    if handler == "ingest.social_sentiment":
        return "search_social"
    if handler == "ingest.google_news":
        return "search_news"
    if handler == "ingest.reddit":
        return "search_reddit"
    return "custom"


def _build_default_graph_from_steps(steps: list[dict]) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    for idx, step in enumerate(steps, start=1):
        node_id = f"n{idx}"
        nodes.append(
            {
                "id": node_id,
                "module_key": _infer_node_module_from_handler(step.get("handler") or ""),
                "title": step.get("name") or step.get("handler") or node_id,
                "data_type": "market_info",
                "params": step.get("params") if isinstance(step.get("params"), dict) else {},
            }
        )
        if idx > 1:
            edges.append(
                {
                    "id": f"e{idx - 1}",
                    "source": f"n{idx - 1}",
                    "target": node_id,
                    "mapping": {"count_rule": "", "field_map": []},
                }
            )
    return {"nodes": nodes, "edges": edges}


def _normalize_board_layout(board_layout: dict, steps: list[dict]) -> dict:
    layout = board_layout if isinstance(board_layout, dict) else {}
    design = layout.get("design")
    design = design if isinstance(design, dict) else {}
    graph = layout.get("graph")
    graph = graph if isinstance(graph, dict) else {}
    graph_nodes = graph.get("nodes")
    graph_edges = graph.get("edges")
    graph_nodes = graph_nodes if isinstance(graph_nodes, list) else []
    graph_edges = graph_edges if isinstance(graph_edges, list) else []
    if not graph_nodes:
        fallback = _build_default_graph_from_steps(steps)
        graph_nodes = fallback["nodes"]
        graph_edges = fallback["edges"] if not graph_edges else graph_edges

    edge_mappings = layout.get("edge_mappings")
    if not isinstance(edge_mappings, list):
        edge_mappings = []
    adapter_nodes = layout.get("adapter_nodes")
    if not isinstance(adapter_nodes, list):
        adapter_nodes = []
    data_flow = layout.get("data_flow")
    if not isinstance(data_flow, list):
        data_flow = ["documents", "extracted_data", "visualization"]

    normalized_design = {
        "global_data_type": str(design.get("global_data_type") or "market_info"),
        "node_overrides": design.get("node_overrides") if isinstance(design.get("node_overrides"), dict) else {},
        "llm_policy": str(design.get("llm_policy") or "auto"),
        "visualization_module": str(design.get("visualization_module") or layout.get("layout") or "trend"),
    }

    return {
        **layout,
        "layout": str(layout.get("layout") or "trend"),
        "auto_interface": bool(layout.get("auto_interface", True)),
        "data_flow": data_flow,
        "design": normalized_design,
        "graph": {"nodes": graph_nodes, "edges": graph_edges},
        "edge_mappings": [x for x in edge_mappings if isinstance(x, dict)],
        "adapter_nodes": [x for x in adapter_nodes if isinstance(x, dict)],
    }


@router.get("/menu")
def get_menu_config(project_key: str | None = Query(default=None)):
    customization = get_project_customization(project_key)
    return success_response(
        {
            "project_key": customization.project_key,
            "menu": customization.get_menu_config(),
        }
    )


@router.get("/workflows")
def list_workflows(project_key: str | None = Query(default=None)):
    customization = get_project_customization(project_key)
    workflow_mapping = customization.get_workflow_mapping()
    custom_record = get_config(customization.project_key, WORKFLOW_PLATFORM_CONFIG_KEY) or {}
    custom_payload = custom_record.get("payload") if isinstance(custom_record.get("payload"), dict) else {}
    custom_workflows, _, _ = _coerce_workflow_payload(custom_payload)
    merged = set(workflow_mapping.keys()) | set(custom_workflows.keys())
    return success_response(
        {
            "project_key": customization.project_key,
            "items": sorted(merged),
        }
    )


def _read_workflow_template(project_key: str | None, workflow_name: str) -> tuple[str, list[dict], dict[str, str], dict]:
    customization = get_project_customization(project_key)
    effective_project_key = customization.project_key
    normalized_workflow_name = workflow_name.strip()
    if not normalized_workflow_name:
        raise HTTPException(status_code=400, detail="workflow_name is required.")

    custom_definition = load_custom_workflow_definition(effective_project_key, normalized_workflow_name)
    if custom_definition is not None:
        steps = dump_workflow_definition(custom_definition.steps)
        board_layout = _normalize_board_layout(
            load_custom_workflow_board_layout(effective_project_key, normalized_workflow_name),
            steps,
        )
        return (
            effective_project_key,
            steps,
            {"source": "custom"},
            board_layout,
        )

    workflow_mapping = customization.get_workflow_mapping()
    workflow = workflow_mapping.get(normalized_workflow_name)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"workflow not found: {normalized_workflow_name}")
    steps = dump_workflow_definition(workflow.steps)
    board_layout = _normalize_board_layout(
        load_custom_workflow_board_layout(effective_project_key, normalized_workflow_name),
        steps,
    )
    return (
        effective_project_key,
        steps,
        {"source": "builtin"},
        board_layout,
    )


@router.get("/workflows/{workflow_name}/template")
def get_workflow_template(workflow_name: str, project_key: str | None = Query(default=None)):
    effective_project_key, steps, meta, board_layout = _read_workflow_template(project_key, workflow_name)
    return success_response(
        {
            "project_key": effective_project_key,
            "workflow_name": workflow_name,
            "steps": steps,
            "board_layout": board_layout,
            "meta": meta,
        }
    )


@router.post("/workflows/{workflow_name}/template")
def upsert_workflow_template(workflow_name: str, payload: WorkflowTemplatePayload):
    effective_project_key = (payload.project_key or "").strip() or get_project_customization().project_key
    if not effective_project_key:
        raise HTTPException(status_code=400, detail="project_key is required. Please select a project first.")

    normalized_workflow_name = workflow_name.strip()
    if not normalized_workflow_name:
        raise HTTPException(status_code=400, detail="workflow_name is required.")

    if not isinstance(payload.steps, list) or not payload.steps:
        raise HTTPException(status_code=400, detail="steps is required and must be a non-empty array.")
    for idx, step in enumerate(payload.steps, start=1):
        if not step.handler or not str(step.handler).strip():
            raise HTTPException(status_code=400, detail=f"steps[{idx}].handler is required.")

    existing_record = get_config(effective_project_key, WORKFLOW_PLATFORM_CONFIG_KEY)
    existing_payload = (existing_record or {}).get("payload")
    workflows, boards, version = _coerce_workflow_payload(existing_payload if isinstance(existing_payload, dict) else {})

    serialized_steps = [
        {
            "handler": step.handler,
            "params": step.params,
            "enabled": step.enabled,
            "name": step.name,
        }
        for step in payload.steps
    ]

    workflows[normalized_workflow_name] = {
        "steps": [
            x for x in serialized_steps
        ],
    }
    boards[normalized_workflow_name] = _normalize_board_layout(payload.board_layout, serialized_steps)

    next_payload = {
        "version": version + 1,
        "workflows": workflows,
        "boards": boards,
    }
    data = upsert_config(
        project_key=effective_project_key,
        config_key=WORKFLOW_PLATFORM_CONFIG_KEY,
        config_type=WORKFLOW_PLATFORM_CONFIG_KEY,
        payload=next_payload,
    )

    return success_response(
        {
            "project_key": data["project_key"],
            "workflow_name": normalized_workflow_name,
            "saved": True,
            "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
            "config": data["payload"],
        }
    )


@router.delete("/workflows/{workflow_name}/template")
def delete_workflow_template(workflow_name: str, project_key: str | None = Query(default=None)):
    effective_project_key = (project_key or "").strip() or get_project_customization().project_key
    if not effective_project_key:
        raise HTTPException(status_code=400, detail="project_key is required. Please select a project first.")

    normalized_workflow_name = workflow_name.strip()
    if not normalized_workflow_name:
        raise HTTPException(status_code=400, detail="workflow_name is required.")

    record = get_config(effective_project_key, WORKFLOW_PLATFORM_CONFIG_KEY) or {}
    existing_payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    workflows, boards, version = _coerce_workflow_payload(existing_payload)
    if normalized_workflow_name not in workflows:
        raise HTTPException(status_code=404, detail=f"custom workflow not found: {normalized_workflow_name}")

    workflows.pop(normalized_workflow_name, None)
    boards.pop(normalized_workflow_name, None)

    data = upsert_config(
        project_key=effective_project_key,
        config_key=WORKFLOW_PLATFORM_CONFIG_KEY,
        config_type=WORKFLOW_PLATFORM_CONFIG_KEY,
        payload={"version": version + 1, "workflows": workflows, "boards": boards},
    )

    return success_response(
        {
            "project_key": data["project_key"],
            "workflow_name": normalized_workflow_name,
            "deleted": True,
            "config_key": WORKFLOW_PLATFORM_CONFIG_KEY,
            "config": data["payload"],
        }
    )


@router.get("/llm-mapping")
def get_llm_mapping(project_key: str | None = Query(default=None)):
    customization = get_project_customization(project_key)
    return success_response(
        {
            "project_key": customization.project_key,
            "llm_mapping": customization.get_llm_mapping(),
        }
    )


@router.get("/graph-config")
def get_graph_config(project_key: str | None = Query(default=None)):
    customization = get_project_customization(project_key)
    return success_response(
        {
            "project_key": customization.project_key,
            "graph_doc_types": resolve_graph_doc_types(customization.project_key),
            "graph_type_labels": resolve_graph_type_labels(customization.project_key),
            "graph_node_types": resolve_graph_node_types(customization.project_key),
            "graph_node_labels": resolve_graph_node_labels(customization.project_key),
            "graph_field_labels": resolve_graph_field_labels(customization.project_key),
            "graph_edge_types": resolve_graph_edge_types(customization.project_key),
            "graph_relation_labels": resolve_graph_relation_labels(customization.project_key),
        }
    )


@router.post("/workflows/{workflow_name}/run")
def run_workflow(workflow_name: str, payload: WorkflowRunPayload):
    try:
        project_key = (payload.project_key or "").strip()
        if not project_key:
            raise HTTPException(status_code=400, detail="project_key is required. Please select a project first.")
        result = execute_project_workflow(
            workflow_name=workflow_name,
            params=payload.params or {},
            project_key=project_key,
        )
        return success_response(result)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
