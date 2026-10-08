from __future__ import annotations

from dataclasses import replace
from ..item_resolver import ExecutionPayload, ExecutionRequest
from ..types import SourceItemExecutor


def _attach_protocol_search_metadata(payload: ExecutionPayload, request: ExecutionRequest) -> ExecutionPayload:
    result = payload["result"]
    result.setdefault(
        "orchestrator",
        {
            "lane": "protocol_search",
            "strategy": "single_channel_protocol_search",
            "query_terms": list(request.protocol.query_terms or []),
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
    item: dict[str, object],
    request: ExecutionRequest,
    channel_map: dict[str, dict[str, object]],
    run_single_channel_orchestrator: SourceItemExecutor,
) -> ExecutionPayload:
    protocol_params = dict(request.params)
    protocol_params.setdefault("query_terms", list(request.protocol.query_terms or []))
    protocol_request = replace(request, params=protocol_params)
    payload = run_single_channel_orchestrator(
        item=item,
        request=protocol_request,
        channel_map=channel_map,
    )
    return _attach_protocol_search_metadata(payload, protocol_request)
