from __future__ import annotations

from ..item_resolver import ExecutionPayload, ExecutionRequest
from ..types import SourceUrlExecutor


def run_url_execution_orchestrator(
    *,
    item: dict[str, object],
    request: ExecutionRequest,
    channel_map: dict[str, dict[str, object]],
    run_item_with_url_routing: SourceUrlExecutor,
) -> ExecutionPayload:
    result = run_item_with_url_routing(
        item=item,
        params=request.params,
        project_key=request.project_key,
        channel_map=channel_map,
        execution_layer="terminal_output_only",
    )
    result.setdefault("middle_layer_protocol", request.protocol.to_dict())
    return request.complete(result, channel_key=None)
