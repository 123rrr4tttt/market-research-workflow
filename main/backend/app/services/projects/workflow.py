from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict

from ...project_customization import get_project_customization
from ...project_customization.interfaces import WorkflowDefinition, WorkflowStep
from ..ingest_config import get_config
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


WORKFLOW_PLATFORM_CONFIG_KEY = "workflow_platform"


def _coerce_workflow_steps(raw_steps: Any) -> list[WorkflowStep]:
    """Build workflow steps from serialized JSON, with safe coercion."""

    if not isinstance(raw_steps, list):
        return []
    out: list[WorkflowStep] = []
    for item in raw_steps:
        if not isinstance(item, dict):
            continue
        handler = str(item.get("handler") or "").strip()
        if not handler:
            continue
        params = item.get("params")
        if not isinstance(params, dict):
            params = {}
        out.append(
            WorkflowStep(
                handler=handler,
                params=params,
                enabled=bool(item.get("enabled", True)),
                name=str(item.get("name")).strip() if item.get("name") is not None else None,
            )
        )
    return out


def _coerce_workflow_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"version": 0, "workflows": {}, "boards": {}}
    workflows = payload.get("workflows")
    boards = payload.get("boards")
    version = payload.get("version")
    try:
        version = int(version) if version is not None else 0
    except (TypeError, ValueError):
        version = 0
    return {
        "version": version if version >= 0 else 0,
        "workflows": workflows if isinstance(workflows, dict) else {},
        "boards": boards if isinstance(boards, dict) else {},
    }


def load_custom_workflow_definition(project_key: str, workflow_name: str) -> WorkflowDefinition | None:
    config_record = get_config(project_key, WORKFLOW_PLATFORM_CONFIG_KEY)
    if not config_record:
        return None
    payload = _coerce_workflow_payload(config_record.get("payload"))
    workflow_payload = payload["workflows"].get(workflow_name)
    if not isinstance(workflow_payload, dict):
        return None
    steps = _coerce_workflow_steps(workflow_payload.get("steps"))
    if not steps:
        return None
    return WorkflowDefinition(steps=steps)


def load_custom_workflow_board_layout(project_key: str, workflow_name: str) -> dict[str, Any]:
    config_record = get_config(project_key, WORKFLOW_PLATFORM_CONFIG_KEY)
    if not config_record:
        return {}
    payload = _coerce_workflow_payload(config_record.get("payload"))
    board_payload = payload["boards"].get(workflow_name)
    if isinstance(board_payload, dict):
        return board_payload
    workflow_payload = payload["workflows"].get(workflow_name)
    if isinstance(workflow_payload, dict):
        raw_board = workflow_payload.get("board_layout")
        if isinstance(raw_board, dict):
            return raw_board
    return {}


def dump_workflow_definition(steps: list[WorkflowStep]) -> list[dict[str, Any]]:
    return [
        {
            "handler": s.handler,
            "params": s.params,
            "enabled": s.enabled,
            "name": s.name,
        }
        for s in steps
    ]


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
    effective_project_key = customization.project_key
    overridden = load_custom_workflow_definition(effective_project_key, workflow_name)
    if overridden is not None:
        return effective_project_key, overridden

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
    runtime_diagnostics: list[dict[str, Any]] = []
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
                runtime_diagnostics.append(
                    {
                        "kind": "runtime_api_error",
                        "phase": "runtime",
                        "index": idx,
                        "handler": step.handler,
                        "message": f"workflow handler not found: {step.handler}",
                    }
                )
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
                runtime_diagnostics.append(
                    {
                        "kind": "runtime_api_error",
                        "phase": "runtime",
                        "index": idx,
                        "handler": step.handler,
                        "message": str(exc),
                    }
                )
                break

    return {
        "project_key": effective_project_key,
        "workflow_name": workflow_name,
        "status": "ok" if all(x["status"] in ("ok", "skipped") for x in step_results) else "failed",
        "steps": step_results,
        "diagnostics": {
            "compile": [],
            "runtime": runtime_diagnostics,
        },
    }
