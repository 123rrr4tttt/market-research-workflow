"""Skill-runtime adapters over the same project retrieval service as HTTP."""
from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from app.services.projects.context import current_project_key
from .failures import retrieval_failure
from .contracts import RetrievalJsonObject
from .service import ProjectRetrievalService, RetrievalError


def _project(payload: Mapping[str, object]) -> str:
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


def current(payload: Mapping[str, object]) -> RetrievalJsonObject:
    return ProjectRetrievalService().current(_project(payload))


def preview(payload: Mapping[str, object]) -> RetrievalJsonObject:
    project = _project(payload)
    query_ids_value = payload.get("query_ids")
    query_ids = [str(value) for value in cast(list[object], query_ids_value)] if isinstance(query_ids_value, list) else None
    limits_value = payload.get("limits")
    if isinstance(limits_value, Mapping):
        raw_limits = cast(Mapping[object, object], limits_value)
        limits = {
            str(key): value
            for key, value in raw_limits.items()
            if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool)
        }
        if len(limits) != len(raw_limits):
            limits = {"__invalid__": 0}
    else:
        limits = None
    return ProjectRetrievalService().preview(
        project, route_id=str(payload.get("route_id") or ""),
        query_ids=query_ids, limits=limits,
    )


def start(payload: Mapping[str, object]) -> RetrievalJsonObject:
    project = _project(payload)
    return ProjectRetrievalService().start(
        project, plan_id=str(payload.get("plan_id") or ""),
        idempotency_key=str(payload.get("idempotency_key") or ""),
    )


def read_run(payload: Mapping[str, object]) -> RetrievalJsonObject:
    return ProjectRetrievalService().read_run(
        _project(payload), str(payload.get("run_id") or ""),
    )


def continue_saved_frontier(payload: Mapping[str, object]) -> RetrievalJsonObject:
    """Run one source-closed, persisted frontier through the fixed executor."""

    budget = payload.get("remaining_followup_budget")
    normalized_budget = budget if isinstance(budget, int) and not isinstance(budget, bool) else 0
    return ProjectRetrievalService().continue_saved_frontier(
        _project(payload),
        plan_id=str(payload.get("plan_id") or ""),
        proposal_id=str(payload.get("proposal_id") or ""),
        proposal_version=str(payload.get("proposal_version") or ""),
        frontier_id=str(payload.get("frontier_id") or ""),
        remaining_followup_budget=normalized_budget,
    )
