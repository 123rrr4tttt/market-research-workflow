from __future__ import annotations

# Structured architecture-boundary markers intentionally exceed the line limit.
# ruff: noqa: E501

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, NoReturn, TypedDict, cast

from ...project_customization import get_project_customization
from ...project_customization.interfaces import WorkflowDefinition, WorkflowStep
from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import project_operation_failures
from app.successor_runtime.language.sync import interpret_ordered_sync
from ..agent_core.contracts import (
    AgentCoreRequest,
    CoreEvent,
    CoreToolCall,
    CoreToolResult,
    CoreToolSpec,
    json_object,
)
from ..agent_core.registry import CoreToolRegistry
from ..ingest_config import get_config  # pyright: ignore[reportUnknownVariableType]
from ..ingest.market_web import collect_market_info
from ..ingest.news import collect_google_news, collect_reddit_discussions
from ..ingest.social import collect_user_social_sentiment
from .context import bind_project

logger = logging.getLogger(__name__)


_PROJECT_WORKFLOW_FAILURE_WITNESS = "test:test_w01_project_identity_failures"
_PROJECT_WORKFLOW_FAILURE_CONTEXT_KEYS = frozenset(
    {
        "boundary_class",
        "failure_family",
        "operation",
        "owner",
        "public_exception",
        "public_message",
        "site",
        "witness",
    }
)


def _workflow_failure(code: str, message: str, *, operation: str, site: str) -> Failure:
    return project_operation_failures.fail(
        code,
        message,
        {
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "failure_family": project_operation_failures.name,
            "operation": operation,
            "owner": site,
            "public_exception": "ValueError",
            "public_message": message,
            "site": site,
            "witness": _PROJECT_WORKFLOW_FAILURE_WITNESS,
        },
    )


def _raise_workflow_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    if (
        not project_operation_failures.matches(failure)
        or _PROJECT_WORKFLOW_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("public_exception") != "ValueError"
    ):
        # kit:boundary owner=projects.workflow.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_project_context_and_workflow_lifts_preserve_public_messages
        raise TypeError(  # noqa: TRY003
            "project workflow failure lift context is incomplete"
        )
    # kit:boundary owner=projects.workflow.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=project.operation.failure witness=test:test_w01_project_context_and_workflow_lifts_preserve_public_messages
    raise ValueError(str(context["public_message"]))

ProjectWorkflowKernel = Callable[[dict[str, Any]], dict[str, Any]]


def _string_list(value: object, *, default: tuple[str, ...] = ()) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return list(default)
    items = cast(list[object] | tuple[object, ...], value)
    return [str(item) for item in items]


def _collect_reddit(params: dict[str, Any]) -> dict[str, Any]:
    return collect_reddit_discussions(
        subreddit=str(params.get("subreddit") or "news"),
        limit=int(params.get("limit", 20)),
    )


def _collect_google_news(params: dict[str, Any]) -> dict[str, Any]:
    return collect_google_news(
        keywords=_string_list(params.get("keywords")),
        limit=int(params.get("limit", 20)),
    )


def _collect_data_api(params: dict[str, Any]) -> dict[str, Any]:
    return collect_user_social_sentiment(
        keywords=_string_list(params.get("keywords")),
        platforms=_string_list(params.get("platforms"), default=("reddit",)),
        limit=int(params.get("limit", 20)),
        enable_extraction=bool(params.get("enable_extraction", True)),
        enable_subreddit_discovery=bool(params.get("enable_subreddit_discovery", True)),
        base_subreddits=_string_list(
            params.get("base_subreddits"), default=("robotics",)
        ),
    )


def _collect_market(params: dict[str, Any]) -> dict[str, Any]:
    return collect_market_info(
        keywords=_string_list(params.get("keywords") or params.get("query_terms")),
        limit=int(params.get("limit", 20)),
        enable_extraction=bool(params.get("enable_extraction", True)),
    )


def _register_project_workflow_kernel(
    registry: CoreToolRegistry,
    *,
    name: str,
    kernel: ProjectWorkflowKernel,
) -> None:
    spec = CoreToolSpec(
        name=name,
        title=name,
        description_for_model=f"Execute the project workflow operation {name}.",
        input_schema={"type": "object", "additionalProperties": True},
        output_schema={"type": "object", "additionalProperties": True},
        source="project",
        risk="write_shared",
        permission="allow",
        concurrency="serial",
        timeout_seconds=120,
        project_service_id="project-customization.workflow",
    )

    def handler(
        tool_call: CoreToolCall,
        _tool_spec: CoreToolSpec,
        _request: AgentCoreRequest,
        _emit: Callable[[CoreEvent], None],
    ) -> CoreToolResult:
        try:
            output = kernel(dict(tool_call.arguments or {}))
        except Exception as exc:  # noqa: BLE001
            logger.exception("project workflow tool failed", extra={"tool_name": name})
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=name,
                status="failed",
                model_summary=str(exc),
                error={"code": "project_workflow_failed", "message": str(exc)},
            )
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=name,
            status="completed",
            model_summary=f"completed {name}",
            structured_content=json_object(output),
        )

    registration_failure = registry.register(spec, handler)
    if isinstance(registration_failure, Failure):
        # kit:boundary owner=projects.workflow.registry_registration class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=agent.runtime.failure witness=test:test_project_workflow_registration_failure_preserves_value_error
        raise ValueError(registration_failure.message)  # noqa: TRY004


def build_project_workflow_tool_registry() -> Annotated[
    CoreToolRegistry,
    (
        "kit:prepared-command effect_boundary=CoreToolRegistry.execute_tool "
        "witness=test:test_project_workflow_uses_core_registry_and_preserves_disabled_and_merge"
    ),
]:
    """Declare the supported kernels through the authoritative Core registry."""

    registry = CoreToolRegistry()
    _register_project_workflow_kernel(registry, name="ingest.reddit", kernel=_collect_reddit)
    _register_project_workflow_kernel(
        registry, name="ingest.google_news", kernel=_collect_google_news
    )
    _register_project_workflow_kernel(registry, name="ingest.data_api", kernel=_collect_data_api)
    _register_project_workflow_kernel(registry, name="ingest.market", kernel=_collect_market)
    return registry


def available_project_workflow_handlers() -> frozenset[str]:
    registry = build_project_workflow_tool_registry()
    return frozenset(spec.name for spec in registry.list_specs())


@dataclass(frozen=True, slots=True)
class _ProjectWorkflowStepResult:
    index: int
    step: WorkflowStep
    params: dict[str, Any]
    result: CoreToolResult | None
    elapsed_ms: int


WORKFLOW_PLATFORM_CONFIG_KEY = "workflow_platform"


class _WorkflowPayload(TypedDict):
    version: int
    workflows: dict[str, object]
    boards: dict[str, object]


def _coerce_workflow_steps(raw_steps: object) -> list[WorkflowStep]:
    """Build workflow steps from serialized JSON, with safe coercion."""

    if not isinstance(raw_steps, list):
        return []
    out: list[WorkflowStep] = []
    for raw_item in cast(list[object], raw_steps):
        item = cast(dict[str, object], raw_item) if isinstance(raw_item, dict) else None
        if item is None:
            continue
        handler = str(item.get("handler") or "").strip()
        if not handler:
            continue
        raw_params = item.get("params")
        params = cast(dict[str, Any], raw_params) if isinstance(raw_params, dict) else {}
        out.append(
            WorkflowStep(
                handler=handler,
                params=params,
                enabled=bool(item.get("enabled", True)),
                name=str(item.get("name")).strip() if item.get("name") is not None else None,
            )
        )
    return out


def _coerce_workflow_payload(payload: object) -> _WorkflowPayload:
    if not isinstance(payload, dict):
        return {"version": 0, "workflows": {}, "boards": {}}
    payload_object = cast(dict[str, object], payload)
    workflows = payload_object.get("workflows")
    boards = payload_object.get("boards")
    version = payload_object.get("version")
    try:
        normalized_version = int(version) if isinstance(version, (str, int, float)) else 0
    except (TypeError, ValueError):
        normalized_version = 0
    return {
        "version": normalized_version if normalized_version >= 0 else 0,
        "workflows": cast(dict[str, object], workflows) if isinstance(workflows, dict) else {},
        "boards": cast(dict[str, object], boards) if isinstance(boards, dict) else {},
    }


def load_custom_workflow_definition(project_key: str, workflow_name: str) -> WorkflowDefinition | None:
    config_record = cast(
        dict[str, Any] | None,
        get_config(project_key, WORKFLOW_PLATFORM_CONFIG_KEY),
    )
    if not config_record:
        return None
    payload = _coerce_workflow_payload(config_record.get("payload"))
    workflow_payload = payload["workflows"].get(workflow_name)
    if not isinstance(workflow_payload, dict):
        return None
    workflow_object = cast(dict[str, object], workflow_payload)
    steps = _coerce_workflow_steps(workflow_object.get("steps"))
    if not steps:
        return None
    return WorkflowDefinition(steps=steps)


def load_custom_workflow_board_layout(project_key: str, workflow_name: str) -> dict[str, Any]:
    config_record = cast(
        dict[str, Any] | None,
        get_config(project_key, WORKFLOW_PLATFORM_CONFIG_KEY),
    )
    if not config_record:
        return {}
    payload = _coerce_workflow_payload(config_record.get("payload"))
    board_payload = payload["boards"].get(workflow_name)
    if isinstance(board_payload, dict):
        return cast(dict[str, Any], board_payload)
    workflow_payload = payload["workflows"].get(workflow_name)
    if isinstance(workflow_payload, dict):
        workflow_object = cast(dict[str, object], workflow_payload)
        raw_board = workflow_object.get("board_layout")
        if isinstance(raw_board, dict):
            return cast(dict[str, Any], raw_board)
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


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    data = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = _merge_dict(
                cast(dict[str, Any], data[key]),
                cast(dict[str, Any], value),
            )
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
        _raise_workflow_failure(
            _workflow_failure(
                "workflow_not_found",
                f"workflow not found: {workflow_name}",
                operation="resolve_workflow",
                site="app.services.projects.workflow._resolve_workflow",
            )
        )
    return customization.project_key, workflow


def execute_project_workflow(
    *,
    workflow_name: str,
    params: dict[str, Any] | None = None,
    project_key: str | None = None,
) -> dict[str, Any]:
    effective_project_key, workflow = _resolve_workflow(project_key, workflow_name)
    runtime_params = params or {}
    registry = build_project_workflow_tool_registry()
    request = AgentCoreRequest(
        message="",
        session_id=f"run-{uuid.uuid4().hex[:16]}",
        project_key=effective_project_key,
        turn_id=f"turn-{uuid.uuid4().hex[:16]}",
    )

    def invoke_step(
        indexed_step: tuple[int, WorkflowStep],
        _previous_output: dict[str, Any],
    ) -> _ProjectWorkflowStepResult:
        index, step = indexed_step
        if not step.enabled:
            return _ProjectWorkflowStepResult(index, step, {}, None, 0)
        merged_params = _merge_dict(step.params, runtime_params)
        if registry.get(step.handler) is None:
            _raise_workflow_failure(
                _workflow_failure(
                    "workflow_handler_not_found",
                    f"workflow handler not found: {step.handler}",
                    operation="execute_project_workflow",
                    site="app.services.projects.workflow.execute_project_workflow",
                )
            )
        call = CoreToolCall(
            call_id=f"run-{uuid.uuid4().hex[:16]}",
            tool_name=step.handler,
            arguments=merged_params,
            reason="project-customization-workflow",
        )
        started = time.perf_counter()
        result = registry.execute_tool(
            tool_call=call,
            request=request,
            emit=lambda _event: None,
        )
        return _ProjectWorkflowStepResult(
            index=index,
            step=step,
            params=merged_params,
            result=result,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    with bind_project(effective_project_key):
        interpreted = interpret_ordered_sync(
            enumerate(workflow.steps, start=1),
            initial_value=dict(runtime_params),
            invoke=invoke_step,
            continue_after=lambda outcome: (
                outcome.result is None or outcome.result.status == "completed"
            ),
            output_value=lambda outcome: (
                dict(outcome.result.structured_content or {})
                if outcome.result is not None
                else {}
            ),
        )

    step_results: list[dict[str, Any]] = []
    runtime_diagnostics: list[dict[str, Any]] = []
    for outcome in interpreted:
        step = outcome.step
        if outcome.result is None:
            step_results.append(
                {
                    "index": outcome.index,
                    "name": step.name or step.handler,
                    "handler": step.handler,
                    "status": "skipped",
                }
            )
            continue
        result = outcome.result
        if result.status == "completed":
            step_results.append(
                {
                    "index": outcome.index,
                    "name": step.name or step.handler,
                    "handler": step.handler,
                    "status": "ok",
                    "tool_status": result.status,
                    "elapsed_ms": outcome.elapsed_ms,
                    "params": outcome.params,
                    "result": dict(result.structured_content or {}),
                }
            )
            continue
        public_status = (
            "blocked" if result.status in {"needs_approval", "deferred"} else "failed"
        )
        message = str((result.error or {}).get("message") or result.model_summary or result.status)
        step_results.append(
            {
                "index": outcome.index,
                "name": step.name or step.handler,
                "handler": step.handler,
                "status": public_status,
                "tool_status": result.status,
                "elapsed_ms": outcome.elapsed_ms,
                "params": outcome.params,
                "error": message,
                "retry_hint": result.retry_hint,
            }
        )
        runtime_diagnostics.append(
            {
                "kind": "runtime_api_error",
                "phase": "runtime",
                "index": outcome.index,
                "handler": step.handler,
                "status": result.status,
                "message": message,
            }
        )

    terminal_status = next(
        (
            item["status"]
            for item in reversed(step_results)
            if item["status"] not in {"ok", "skipped"}
        ),
        "ok",
    )

    return {
        "project_key": effective_project_key,
        "workflow_name": workflow_name,
        "status": terminal_status,
        "steps": step_results,
        "diagnostics": {
            "compile": [],
            "runtime": runtime_diagnostics,
        },
    }
