from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable


def _attach_protocol_search_metadata(payload: dict[str, Any], request: Any) -> dict[str, Any]:
    result = payload.get("result")
    if isinstance(result, dict):
        result.setdefault(
            "orchestrator",
            {
                "lane": "protocol_search",
                "strategy": "single_channel_protocol_search",
                "query_terms": list(getattr(request, "protocol").query_terms or []),
            },
        )
        result.setdefault("lane", "protocol_search")
    payload.setdefault(
        "orchestrator",
        {
            "lane": "protocol_search",
            "strategy": "single_channel_protocol_search",
        },
    )
    return payload


def run_protocol_search_orchestrator(
    *,
    item: dict[str, Any],
    request: Any,
    channel_map: dict[str, dict[str, Any]],
    run_single_channel_orchestrator: Callable[..., dict[str, Any]],
    deep_merge: Callable[..., dict[str, Any]],
    bind_project: Callable[..., Any],
    run_channel: Callable[..., dict[str, Any]],
    execution_request_to_dict: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    protocol_params = dict(request.params)
    protocol_params.setdefault("query_terms", list(getattr(request, "protocol").query_terms or []))
    protocol_request = replace(request, params=protocol_params)
    payload = run_single_channel_orchestrator(
        item=item,
        request=protocol_request,
        channel_map=channel_map,
        deep_merge=deep_merge,
        bind_project=bind_project,
        run_channel=run_channel,
        execution_request_to_dict=execution_request_to_dict,
    )
    return _attach_protocol_search_metadata(payload, protocol_request)
