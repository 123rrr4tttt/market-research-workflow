"""Skill-runtime adapters over the same project retrieval service as HTTP."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.projects.context import current_project_key
from .failures import retrieval_failure
from .service import ProjectRetrievalService, RetrievalError


def _project(payload: Mapping[str, Any]) -> str:
    active = current_project_key()
    claimed = payload.get("project_key")
    if claimed is not None and claimed != active:
        failure = retrieval_failure(
            "PROJECT_MISMATCH", "skill payload belongs to another project",
            site="skill.project_context", claimed_project=claimed, active_project=active,
        )
        # kit:boundary owner=project_retrieval.skill.project_context class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=project_retrieval.failure witness=test:test_skill_adapter_rejects_cross_project_key
        raise RetrievalError(failure.code, failure.message, 404)
    return active


def current(payload: Mapping[str, Any]) -> dict[str, Any]:
    return ProjectRetrievalService().current(_project(payload))


def preview(payload: Mapping[str, Any]) -> dict[str, Any]:
    project = _project(payload)
    return ProjectRetrievalService().preview(
        project, route_id=str(payload.get("route_id") or ""),
        query_ids=payload.get("query_ids"), limits=payload.get("limits"),
    )


def start(payload: Mapping[str, Any]) -> dict[str, Any]:
    project = _project(payload)
    return ProjectRetrievalService().start(
        project, plan_id=str(payload.get("plan_id") or ""),
        idempotency_key=str(payload.get("idempotency_key") or ""),
    )


def read_run(payload: Mapping[str, Any]) -> dict[str, Any]:
    return ProjectRetrievalService().read_run(
        _project(payload), str(payload.get("run_id") or ""),
    )


def continue_saved_frontier(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run one source-closed, persisted frontier through the fixed executor."""

    return ProjectRetrievalService().continue_saved_frontier(
        _project(payload),
        plan_id=str(payload.get("plan_id") or ""),
        proposal_id=str(payload.get("proposal_id") or ""),
        proposal_version=str(payload.get("proposal_version") or ""),
        frontier_id=str(payload.get("frontier_id") or ""),
        remaining_followup_budget=payload.get("remaining_followup_budget"),
    )
