from __future__ import annotations

from contextlib import nullcontext
from typing import Any, Callable


def run_single_channel_orchestrator(
    *,
    item: dict[str, Any],
    request: Any,
    channel_map: dict[str, dict[str, Any]],
    deep_merge: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    bind_project: Callable[[str | None], Any],
    run_channel: Callable[..., dict[str, Any]],
    execution_request_to_dict: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    channel_key = str(item.get("channel_key") or "").strip()
    channel = channel_map.get(channel_key)
    if channel is None:
        raise ValueError(f"channel not found for item {request.item_key}: {channel_key}")
    if not channel.get("enabled", True):
        raise ValueError(f"channel disabled for item {request.item_key}: {channel_key}")

    params = deep_merge(channel.get("default_params") or {}, request.params)
    params = dict(params)
    params["_source_library_execution_layer"] = "terminal_output_only"
    params["_source_library_terminal_output_only"] = True
    params["source_library_execution_layer"] = "terminal_output_only"
    params["source_library_terminal_output_only"] = True
    params["_source_library_item"] = {
        "item_key": request.item_key,
        "channel_key": channel_key,
        "name": item.get("name"),
        "extra": dict(item.get("extra") or {}) if isinstance(item.get("extra"), dict) else {},
    }
    if channel_key == "handler.cluster":
        params.setdefault("_item_key", request.item_key)

    with (bind_project(request.project_key) if request.project_key else nullcontext()):
        result = run_channel(
            channel=channel,
            params=params,
            project_key=request.project_key,
            item_key=request.item_key,
        )
    if isinstance(result, dict):
        result.setdefault("execution_request", execution_request_to_dict(request))

    return {
        "item_key": request.item_key,
        "channel_key": channel_key,
        "params": params,
        "result": result,
    }
