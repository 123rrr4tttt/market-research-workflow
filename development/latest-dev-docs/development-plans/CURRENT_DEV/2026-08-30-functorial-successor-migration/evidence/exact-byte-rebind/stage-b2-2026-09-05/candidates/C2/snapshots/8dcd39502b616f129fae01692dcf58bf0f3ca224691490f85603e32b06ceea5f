from __future__ import annotations

from typing import Any, Callable


def run_site_search_orchestrator(
    *,
    item: dict[str, Any],
    request: Any,
    channel_map: dict[str, dict[str, Any]],
    run_handler_cluster_item: Callable[..., dict[str, Any]],
    execution_request_to_dict: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    site_item = dict(item)
    site_item["channel_key"] = "handler.cluster"
    payload = run_handler_cluster_item(
        item=site_item,
        params=request.params,
        project_key=request.project_key,
        channel_map=channel_map,
    )
    result = payload.get("result")
    if isinstance(result, dict):
        result.setdefault("execution_request", execution_request_to_dict(request))
    return payload
