from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..runner import RunnerObject
from ..types import ExecutionLayer, FrontDoorExecutionProtocol, RoutingObservation

from ..item_resolver import ExecutionPayload, ExecutionRequest


def run_url_execution_orchestrator(
    *,
    request: ExecutionRequest,
    channel_map: dict[str, dict[str, object]],
) -> ExecutionPayload:
    result = fetch_routed_targets(
        protocol=request.protocol,
        item_channel_key=request.item_channel_key,
        params=request.params,
        project_key=request.project_key,
        channel_map=channel_map,
        runtime_targets=[
            (url, {"source": "params.urls", "index": index})
            for index, url in enumerate(request.protocol.candidate_urls)
        ],
        execution_layer="terminal_output_only",
    )
    return request.complete(result, channel_key=None)


def fetch_routed_targets(
    *,
    protocol: FrontDoorExecutionProtocol,
    item_channel_key: str,
    params: Mapping[object, object],
    project_key: str | None,
    channel_map: dict[str, dict[str, object]],
    runtime_targets: Sequence[tuple[str, dict[str, object]]],
    execution_layer: ExecutionLayer = "execute",
) -> RoutingObservation:
    """Fetch prepared targets without constructing a source-library item."""
    from ..resolver import (
        as_bool, as_optional_int, as_runner_object,
        extract_records_from_routed_row, is_crawler_channel,
        object_list, optional_runner_object, prefer_crawler_channel_key,
        raise_resolver_failure, resolver_failure, run_routed_target,
    )
    if not runtime_targets:
        raise_resolver_failure(
            resolver_failure(
                "frontdoor_runtime_targets_invalid",
                "runtime_targets must be a non-empty sequence for URL routing",
                site="_run_url_routing_materialization.runtime_targets",
            )
        )

    normalized_runtime_targets: list[tuple[str, dict[str, object]]] = []
    for idx, target in enumerate(runtime_targets):
        if len(target) < 1:
            raise_resolver_failure(
                resolver_failure(
                    "frontdoor_runtime_targets_invalid",
                    "runtime_targets entries must contain a url and optional metadata",
                    site="_run_url_routing_materialization.runtime_targets.entry",
                    index=idx,
                )
            )
        url_str = str(target[0] or "").strip()
        target_meta = target[1] if len(target) > 1 else {}
        normalized_runtime_targets.append((url_str, target_meta))

    urls = [url for url, _meta in normalized_runtime_targets]

    inserted_total = 0
    updated_total = 0
    skipped_total = 0
    by_url: list[RunnerObject] = []
    errors: list[str] = []
    records: list[RunnerObject] = []
    has_query_terms = bool(protocol.query_terms)
    force_url_routing_flow = protocol.force_url_routing_flow
    preferred_crawler_channel_key: str | None = None
    fallback_crawler_channel_key: str | None = None
    force_crawler_fallback_on_empty = as_bool(params.get("force_crawler_fallback_on_empty"), True)
    prefer_crawler_first = protocol.prefer_crawler_first
    if prefer_crawler_first:
        item_channel = channel_map.get(item_channel_key)
        if item_channel_key and item_channel and item_channel.get("enabled", True) and is_crawler_channel(item_channel):
            preferred_crawler_channel_key = item_channel_key
        else:
            preferred_crawler_channel_key = prefer_crawler_channel_key(
                channel_map=channel_map,
                project_key=project_key,
            )
    if force_crawler_fallback_on_empty:
        fallback_crawler_channel_key = prefer_crawler_channel_key(
            channel_map=channel_map,
            project_key=project_key,
        )

    rows: list[RunnerObject] = []
    for url in urls:
        try:
            rows.append(
                run_routed_target(
                    url=url,
                    item_key=protocol.item_key or None,
                    params=params,
                    project_key=project_key,
                    channel_map=channel_map,
                    has_query_terms=has_query_terms,
                    force_url_routing_flow=force_url_routing_flow,
                    preferred_crawler_channel_key=preferred_crawler_channel_key,
                    fallback_crawler_channel_key=fallback_crawler_channel_key,
                    force_crawler_fallback_on_empty=force_crawler_fallback_on_empty,
                    execution_layer=execution_layer,
                )
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                as_runner_object(
                    {"url": str(url or ""), "channel_key": None, "error": str(exc), "result": None}
                )
            )

    for row in rows:
        result = optional_runner_object(row.get("result"))
        if result:
            inserted_total += as_optional_int(result.get("inserted")) or 0
            updated_total += as_optional_int(result.get("updated")) or 0
            skipped_total += as_optional_int(result.get("skipped")) or 0
            for error_value in object_list(result.get("errors")):
                error_text = str(error_value or "").strip()
                if error_text:
                    errors.append(error_text)
            records.extend(
                extract_records_from_routed_row(
                    row=row,
                    result=result,
                    channel_key=str(row.get("channel_key") or "").strip(),
                    start_index=len(records),
                )
            )
        else:
            error_text = str(row.get("error") or "").strip()
            if error_text:
                errors.append(f"{str(row.get('url') or '')[:80]}: {error_text}")
        by_url.append(row)

    fetched_total = len(by_url)
    normalized_total = len(records)
    dropped_total = max(fetched_total - normalized_total, 0)
    response: RoutingObservation = {
        "by_url": by_url,
        "records": records,
        "stats": {
            "fetched": fetched_total,
            "normalized": normalized_total,
            "dropped": dropped_total,
            "errors": len(errors),
        },
        "legacy_counts": {
            "inserted": inserted_total,
            "updated": updated_total,
            "skipped": skipped_total,
        },
        "errors": errors,
        "middle_layer_protocol": protocol.to_dict(),
        "url_routing_parallelism": 1,
        "diagnostics": {
            "concurrency_plan": dict(protocol.concurrency_plan),
            "url_stage": {
                "budget": len(urls),
                "parallelism": 1,
                "fail_fast": False,
                "timeout_seconds": None,
                "tasks_total": len(urls),
                "timed_out": sum(1 for row in by_url if row.get("timeout")),
            },
        },
        "execution_layer": execution_layer,
    }
    if execution_layer != "terminal_output_only":
        response["inserted"] = inserted_total
        response["updated"] = updated_total
        response["skipped"] = skipped_total
    return response
