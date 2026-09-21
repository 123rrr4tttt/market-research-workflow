from __future__ import annotations

from typing import Any

from ...settings.config import settings
from mrw_functorial_kit.core.agent_service_semantics import agent_batch_failures

from .task_contract import _raise_legacy_agent_batch_failure

ALLOWED_LANES = {"main", "subagent", "system"}


def validate_lane(raw_lane: str | None, *, fallback: str | None = None) -> str:
    lane = str(raw_lane or fallback or "").strip().lower()
    if lane not in ALLOWED_LANES:
        _raise_legacy_agent_batch_failure(
            agent_batch_failures.fail(
                "lane_invalid",
                "lane is required and must be one of: main, subagent, system",
                {"lane": lane},
            )
        )
    return lane


def resolve_queue_for_lane(lane: str) -> str:
    normalized = validate_lane(lane)
    if normalized == "subagent":
        return str(getattr(settings, "agent_batch_lane_subagent_queue", "celery") or "celery")
    if normalized == "system":
        return str(getattr(settings, "agent_batch_lane_system_queue", "celery") or "celery")
    return str(getattr(settings, "agent_batch_lane_main_queue", "celery") or "celery")


def apply_async_or_delay(task_func: Any, args: tuple[Any, ...], kwargs: dict[str, Any], lane: str) -> Any:
    normalized = validate_lane(lane)
    queue_name = resolve_queue_for_lane(normalized)
    routing_key = f"agent_batch.{normalized}"
    if hasattr(task_func, "apply_async"):
        return task_func.apply_async(args=args, kwargs=kwargs, queue=queue_name, routing_key=routing_key)
    return task_func.delay(*args, **kwargs)
