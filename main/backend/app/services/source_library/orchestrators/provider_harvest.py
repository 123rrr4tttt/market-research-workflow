from __future__ import annotations

from dataclasses import replace
from ..item_resolver import ExecutionPayload, ExecutionRequest
from ..types import SourceItemExecutor


def _attach_provider_harvest_metadata(payload: ExecutionPayload, item: dict[str, object]) -> ExecutionPayload:
    result = payload["result"]
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
    item: dict[str, object],
    request: ExecutionRequest,
    channel_map: dict[str, dict[str, object]],
    run_single_channel_orchestrator: SourceItemExecutor,
) -> ExecutionPayload:
    provider_params = dict(request.params)
    provider_params.setdefault("prefer_crawler_first", True)
    provider_params.setdefault("provider_harvest_mode", "terminal_output_only")
    provider_request = replace(request, params=provider_params)
    payload = run_single_channel_orchestrator(
        item=item,
        request=provider_request,
        channel_map=channel_map,
    )
    return _attach_provider_harvest_metadata(payload, item)
