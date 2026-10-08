from __future__ import annotations

from ..item_resolver import ExecutionPayload, ExecutionRequest
from ..types import SourceClusterExecutor


def run_site_search_orchestrator(
    *,
    item: dict[str, object],
    request: ExecutionRequest,
    channel_map: dict[str, dict[str, object]],
    run_handler_cluster_item: SourceClusterExecutor,
) -> ExecutionPayload:
    site_item = dict(item)
    site_item["channel_key"] = "handler.cluster"
    payload = run_handler_cluster_item(
        item=site_item,
        params=request.params,
        project_key=request.project_key,
        channel_map=channel_map,
    )
    return request.attach_result(payload)
