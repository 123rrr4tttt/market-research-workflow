from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..contracts import success_response
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
from ..services.projects.workflow import execute_project_workflow

router = APIRouter(prefix="/project-customization", tags=["project-customization"])


class WorkflowRunPayload(BaseModel):
    project_key: str | None = None
    params: dict = Field(default_factory=dict)


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
    return success_response(
        {
            "project_key": customization.project_key,
            "items": list(workflow_mapping.keys()),
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
