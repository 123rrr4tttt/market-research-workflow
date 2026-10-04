from __future__ import annotations

from typing import Any, Callable


def run_url_execution_orchestrator(
    *,
    item: dict[str, Any],
    request: Any,
    channel_map: dict[str, dict[str, Any]],
    run_item_with_url_routing: Callable[..., dict[str, Any]],
    protocol_to_dict: Callable[[Any], dict[str, Any]],
    execution_request_to_dict: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    result = run_item_with_url_routing(
        item=item,
        params=request.params,
        project_key=request.project_key,
        channel_map=channel_map,
        execution_layer="terminal_output_only",
    )
    if isinstance(result, dict):
        result.setdefault("middle_layer_protocol", protocol_to_dict(request.protocol))
        result.setdefault("execution_request", execution_request_to_dict(request))
    return {
        "item_key": request.item_key,
        "channel_key": None,
        "params": request.params,
        "result": result,
    }
