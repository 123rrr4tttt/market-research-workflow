from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict

from ...project_customization import get_project_customization
from ...project_customization.interfaces import WorkflowDefinition
from ..ingest.market_web import collect_market_info
from ..ingest.news import collect_google_news, collect_reddit_discussions
from ..ingest.social import collect_user_social_sentiment
from ..ingest.policy import ingest_policy_documents
from .context import bind_project

logger = logging.getLogger(__name__)

WorkflowHandler = Callable[[Dict[str, Any]], Dict[str, Any]]

_WORKFLOW_HANDLERS: dict[str, WorkflowHandler] = {
    "ingest.reddit": lambda params: collect_reddit_discussions(
        subreddit=str(params.get("subreddit") or "Lottery"),
        limit=int(params.get("limit", 20)),
    ),
    "ingest.google_news": lambda params: collect_google_news(
        keywords=[str(x) for x in (params.get("keywords") or [])],
        limit=int(params.get("limit", 20)),
    ),
    "ingest.social_sentiment": lambda params: collect_user_social_sentiment(
        keywords=[str(x) for x in (params.get("keywords") or [])],
        platforms=[str(x) for x in (params.get("platforms") or ["reddit"])],
        limit=int(params.get("limit", 20)),
        enable_extraction=bool(params.get("enable_extraction", True)),
        enable_subreddit_discovery=bool(params.get("enable_subreddit_discovery", True)),
        base_subreddits=[str(x) for x in (params.get("base_subreddits") or ["robotics"])],
    ),
    "ingest.policy": lambda params: ingest_policy_documents(
        state=str(params.get("state") or ""),
        source_hint=params.get("source_hint"),
    ),
    "ingest.market": lambda params: collect_market_info(
        keywords=[str(x) for x in (params.get("keywords") or params.get("query_terms") or [])],
        limit=int(params.get("limit", 20)),
        enable_extraction=bool(params.get("enable_extraction", True)),
    ),
}


def _merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = _merge_dict(data[key], value)
        else:
            data[key] = value
    return data


def _resolve_workflow(project_key: str | None, workflow_name: str) -> tuple[str, WorkflowDefinition]:
    customization = get_project_customization(project_key)
    mapping = customization.get_workflow_mapping()
    workflow = mapping.get(workflow_name)
    if workflow is None:
        raise ValueError(f"workflow not found: {workflow_name}")
    return customization.project_key, workflow


def execute_project_workflow(
    *,
    workflow_name: str,
    params: Dict[str, Any] | None = None,
    project_key: str | None = None,
) -> Dict[str, Any]:
    effective_project_key, workflow = _resolve_workflow(project_key, workflow_name)
    runtime_params = params or {}

    step_results: list[dict[str, Any]] = []
    with bind_project(effective_project_key):
        for idx, step in enumerate(workflow.steps, start=1):
            if not step.enabled:
                step_results.append(
                    {
                        "index": idx,
                        "name": step.name or step.handler,
                        "handler": step.handler,
                        "status": "skipped",
                    }
                )
                continue

            handler = _WORKFLOW_HANDLERS.get(step.handler)
            if handler is None:
                raise ValueError(f"workflow handler not found: {step.handler}")

            merged_params = _merge_dict(step.params, runtime_params)
            started = time.perf_counter()
            try:
                result = handler(merged_params)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                step_results.append(
                    {
                        "index": idx,
                        "name": step.name or step.handler,
                        "handler": step.handler,
                        "status": "ok",
                        "elapsed_ms": elapsed_ms,
                        "params": merged_params,
                        "result": result,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                logger.exception(
                    "project workflow step failed",
                    extra={
                        "project_key": effective_project_key,
                        "workflow_name": workflow_name,
                        "step_handler": step.handler,
                    },
                )
                step_results.append(
                    {
                        "index": idx,
                        "name": step.name or step.handler,
                        "handler": step.handler,
                        "status": "failed",
                        "elapsed_ms": elapsed_ms,
                        "params": merged_params,
                        "error": str(exc),
                    }
                )
                break

    return {
        "project_key": effective_project_key,
        "workflow_name": workflow_name,
        "status": "ok" if all(x["status"] in ("ok", "skipped") for x in step_results) else "failed",
        "steps": step_results,
    }
