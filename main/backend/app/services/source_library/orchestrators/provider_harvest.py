from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable


def _attach_provider_harvest_metadata(payload: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if isinstance(result, dict):
        result.setdefault(
            "orchestrator",
            {
                "lane": "provider_harvest",
                "strategy": "single_channel_provider_harvest",
                "channel_key": str(item.get("channel_key") or "").strip() or None,
            },
        )
        result.setdefault("lane", "provider_harvest")
    payload.setdefault(
        "orchestrator",
        {
            "lane": "provider_harvest",
            "strategy": "single_channel_provider_harvest",
        },
    )
    return payload


def run_provider_harvest_orchestrator(
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
    provider_params = dict(request.params)
    provider_params.setdefault("prefer_crawler_first", True)
    provider_params.setdefault("provider_harvest_mode", "terminal_output_only")
    provider_request = replace(request, params=provider_params)
    payload = run_single_channel_orchestrator(
        item=item,
        request=provider_request,
        channel_map=channel_map,
        deep_merge=deep_merge,
        bind_project=bind_project,
        run_channel=run_channel,
        execution_request_to_dict=execution_request_to_dict,
    )
    return _attach_provider_harvest_metadata(payload, item)
