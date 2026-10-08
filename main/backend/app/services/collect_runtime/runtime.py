from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Literal, NoReturn, SupportsIndex, SupportsInt, TypeGuard

from functorial_kit.core.failure import Failure

from mrw_functorial_kit.core.provider_port_failures import collect_runtime_failures

from ..agent_batch.task_contract import parse_source_library_runtime_params
from app.successor_runtime.capabilities import acquisition_batch as acquisition
from app.successor_runtime.language.sync import interpret_ordered_sync

from .contracts import (
    FLOW_SOURCE_COLLECT,
    CollectEffectGateway,
    CollectBatchCounts as _CollectDeliveryCounts,
    CollectBatchRow as _CollectDeliveryRow,
    CollectFailure,
    CollectJsonObject,
    CollectJsonValue,
    CollectRequest,
    CollectResult,
    SourceLibraryCompatResponse,
    SourceLibraryCompatProjector,
    collect_failure_to_plain,
    fold_collect_batch_rows,
)
from .delivery import DeliveryObservation, observe_delivery

_source_library_compat_projector: SourceLibraryCompatProjector | None = None
_successor_effect_gateway: CollectEffectGateway | None = None


def _collect_contract_failure(code: str, message: str, *, site: str) -> Failure:
    return collect_runtime_failures.fail(
        code,
        message,
        {"operation": "collect.runtime", "site": site},
    )


def _raise_collect_contract(failure: Failure, exception_type: type[Exception] = ValueError) -> NoReturn:
    # kit:boundary owner=collect.runtime.contract_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=collect.runtime.failure witness=test:test_w03_collect_contract_failures
    raise exception_type(failure.message)


def register_source_library_compat_projector(projector: SourceLibraryCompatProjector) -> None:
    """Inject the legacy source-library response projection at composition time."""

    global _source_library_compat_projector
    if not callable(projector):
        _raise_collect_contract(
            _collect_contract_failure(
                "compat_projector_contract_invalid",
                "source-library compatibility projector must be callable",
                site="register_source_library_compat_projector.projector",
            ),
            TypeError,
        )
    _source_library_compat_projector = projector


def register_successor_collect_effect_gateway(gateway: CollectEffectGateway) -> None:
    """Inject the effectful successor gateway; it is separate from legacy adapters."""

    global _successor_effect_gateway
    if not callable(gateway):
        _raise_collect_contract(
            _collect_contract_failure(
                "successor_effect_gateway_invalid",
                "successor collect effect gateway must be callable",
                site="register_successor_collect_effect_gateway.gateway",
            ),
            TypeError,
        )
    _successor_effect_gateway = gateway


def reset_successor_collect_effect_gateway() -> None:
    global _successor_effect_gateway

    _successor_effect_gateway = None



def run_collect(request: CollectRequest) -> CollectResult:
    """Dispatch every collect through the one typed adapter-effect gateway."""

    batched = _run_successor_collect(request)
    if batched is not None:
        return _attach_delivery_observation(batched)
    return _run_collect_no_batch(request)


@dataclass(slots=True)
class _CollectDeliveryView:
    status: str | None
    provider_job_id: str | None
    provider_type: str | None
    provider_status: str | None
    meta: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class _CollectChild:
    element_id: str
    input_index: int
    request: CollectRequest


def _collect_delivery_observation(
    result: CollectResult, *, expected_delivery: str = "unknown"
) -> DeliveryObservation:
    meta = result.meta
    raw = _json_object(meta.get("raw"))
    raw_result = _json_object(raw.get("result"))
    terminal_output = _json_object(meta.get("terminal_output"))
    terminal_meta = _json_object(terminal_output.get("meta"))
    handoff = _json_object(terminal_meta.get("provider_handoff"))
    readback = (
        meta.get("terminal_readback") or raw.get("terminal_readback")
        or raw_result.get("terminal_readback") or terminal_meta.get("terminal_readback")
    )
    provider_job_id = result.provider_job_id or raw.get("provider_job_id") or raw_result.get("provider_job_id") or terminal_meta.get("provider_job_id") or handoff.get("provider_job_id")
    return observe_delivery(_CollectDeliveryView(
        status=result.status,
        provider_job_id=_optional_text(provider_job_id),
        provider_type=_optional_text(result.provider_type or raw.get("provider_type") or raw_result.get("provider_type") or handoff.get("provider_type")),
        provider_status=_optional_text(result.provider_status or raw.get("provider_status") or raw_result.get("provider_status") or handoff.get("provider_status") or terminal_output.get("status")),
        meta={"terminal_readback": readback},
    ), expected_delivery=expected_delivery)


def _attach_delivery_observation(result: CollectResult) -> CollectResult:
    observation = _collect_delivery_observation(result)
    result.meta = dict(result.meta or {})
    result.meta["delivery_observation"] = asdict(observation)
    raw = result.meta.get("raw")
    if isinstance(raw, dict):
        result.meta["raw"] = {**raw, "delivery_observation": asdict(observation)}
    return result


def _outcome_unknown_result(request: CollectRequest) -> CollectResult:
    """Fail closed when no explicit collect effect gateway is bound."""

    result = CollectResult(
        flow=request.flow,
        channel=request.channel,
        status="unknown",
        errors=[{
            "code": "successor_effect_gateway_unavailable",
            "message": "collect requires an explicit effect gateway",
        }],
        meta={
            "raw": {
                "outcome": "OutcomeUnknown",
                "reason": "effect_gateway_unavailable",
            }
        },
    )
    from .display_meta import build_display_meta

    result.display_meta = build_display_meta(request, result)
    return result


def _json_object(value: CollectJsonValue) -> CollectJsonObject:
    return value if isinstance(value, dict) else {}


def _json_link_values(value: CollectJsonValue) -> list[CollectJsonValue] | dict[str, CollectJsonValue] | str | tuple[()]:
    # JSON arrays and strings are the iterable legacy link shapes.
    if not value:
        return ()
    if isinstance(value, (list, dict, str)):
        return value
    _raise_collect_contract(
        _collect_contract_failure(
            "auto_batch_execution_failed",
            f"'{type(value).__name__}' object is not iterable",
            site="collect_result_to_element_outcome.links",
        ),
        TypeError,
    )


def _json_links(value: CollectJsonValue) -> tuple[str, ...]:
    return tuple(str(link).strip() for link in _json_link_values(value) if str(link).strip())


def _attempt_receipt(
    result: CollectResult, observation: DeliveryObservation, raw: CollectJsonObject
) -> acquisition.CollectAttemptReceipt | None:
    from app.successor_runtime.capabilities.checksum import content_digest

    if not observation.provider_job_id:
        return None
    authoritative = observation.state == "delivered"
    return acquisition.CollectAttemptReceipt(
        schema_version=acquisition.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
        receipt_kind="AUTHORITATIVE_READBACK" if authoritative else "DISPATCH_ACKNOWLEDGEMENT",
        provider_type=str(result.provider_type or "unknown"),
        provider_job_id=observation.provider_job_id,
        provider_status=None if result.provider_status is None else str(result.provider_status),
        attempt_count=int(result.attempt_count or 0),
        observed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        raw_digest=content_digest(raw),
        authoritative_readback=authoritative,
        receipt_digest="",
    )


def _execution_error(message: str, exception_type: str | None = None) -> CollectFailure:
    return {"code": "auto_batch_execution_failed", "message": message, "exception_type": exception_type}


def _run_collect_child(child: _CollectChild, gateway: CollectEffectGateway) -> _CollectDeliveryRow:
    try:
        result = gateway(child.request)
    except Exception as exc:  # noqa: BLE001 - the gateway produced no inspectable result
        return _CollectDeliveryRow(
            child.element_id, child.input_index, tuple(child.request.query_terms), observe_delivery(None),
            _CollectDeliveryCounts(0, 0, 0), errors=(_execution_error(str(exc) or exc.__class__.__name__, exc.__class__.__name__),),
            execution_state="attempted_unknown",
        )

    raw = dict(_json_object(result.meta.get("raw")))
    observation = _collect_delivery_observation(result)
    execution_state: Literal["attempted", "attempted_unknown"] = (
        "attempted_unknown"
        if observation.state == observation.provider_state == "unknown"
        else "attempted"
    )
    projection_errors: list[CollectFailure] = []
    counts: _CollectDeliveryCounts | None
    try:
        counts = _CollectDeliveryCounts(int(result.inserted or 0), int(result.updated or 0), int(result.skipped or 0))
    except Exception as exc:  # noqa: BLE001 - preserve provider observation on invalid counts
        counts = None
        projection_errors.append(
            _execution_error(str(exc) or exc.__class__.__name__, exc.__class__.__name__)
        )
    if counts is not None and min(counts.inserted, counts.updated, counts.skipped) < 0:
        projection_errors.append(
            _execution_error("collect counts must be non-negative", "ValueError")
        )
    links: tuple[str, ...] = ()
    try:
        links = _json_links(raw.get("links"))
    except Exception as exc:  # noqa: BLE001 - retain independent effect facts
        projection_errors.append(
            _execution_error(str(exc) or exc.__class__.__name__, exc.__class__.__name__)
        )
    receipt = None
    try:
        receipt = _attempt_receipt(result, observation, raw)
    except Exception as exc:  # noqa: BLE001 - preserve observed job and counts
        projection_errors.append(
            _execution_error(str(exc) or exc.__class__.__name__, exc.__class__.__name__)
        )
    succeeded = (
        result.status in {"completed", "accepted"}
        and not result.errors
        and not projection_errors
    )
    first = (result.errors or [{}])[0]
    code = first.get("code")
    normalized = code if code in {"element_rejected", "runner_unavailable"} else "auto_batch_execution_failed"
    result_errors: tuple[CollectFailure, ...] = () if not result.errors else ({
        **first,
        "code": normalized,
        "message": str(first.get("message") or "target delivery readback is required for successor completion"),
        "query_terms": tuple(child.request.query_terms),
    },)
    errors = (*projection_errors, *result_errors)
    return _CollectDeliveryRow(
        child.element_id, child.input_index, tuple(child.request.query_terms), observation,
        counts, links, errors, receipt, "succeeded" if succeeded else "failed", execution_state,
    )


def _collect_fail_fast_stop(row: _CollectDeliveryRow) -> bool:
    """Preserve the collect consumer's target-delivery fail-fast boundary."""

    return (
        row.result_status == "failed"
        or row.observation is None
        or row.observation.state != "delivered"
    )


def _expand_collect_children(request: CollectRequest) -> tuple[_CollectChild, ...]:
    from app.successor_runtime.capabilities.checksum import content_digest

    batches = acquisition.split_query_terms(request.query_terms)
    per_limit = acquisition.per_batch_limit_for(request.limit, len(batches))
    request_id = content_digest({
        "flow": request.flow, "channel": request.channel, "project_key": request.project_key,
        "query_terms": request.query_terms, "urls": request.urls, "limit": request.limit,
        "provider": request.provider, "language": request.language, "scope": request.scope,
        "item_key": request.item_key, "options": request.options, "source_context": request.source_context,
    })
    return tuple(_CollectChild(
        f"collect-sync:collect:{request_id}:element:{index}", index,
        replace(request, query_terms=list(terms), limit=per_limit, source_context={**request.source_context, "auto_batched_child": True}),
    ) for index, terms in enumerate(batches))


def _project_collect_rows(
    request: CollectRequest, rows: tuple[_CollectDeliveryRow, ...], requested: int,
    cancellation: acquisition.CollectCancellationReceipt | None,
) -> CollectResult:
    folded = fold_collect_batch_rows(rows, cancellation=cancellation)
    attempted = tuple(row for row in folded.rows if row.execution_state != "not_attempted")
    counts, links = folded.counts, folded.links
    errors: list[CollectFailure] = []
    receipts = folded.receipts
    batch_results: list[CollectJsonValue] = []
    for row in attempted:
        target_status = "failed" if _collect_fail_fast_stop(row) else "succeeded"
        target_errors = row.errors
        if target_status == "failed" and not target_errors:
            fallback: CollectFailure = {
                "code": "runner_unavailable",
                "message": "target delivery readback is required for successor completion",
                "query_terms": row.query_terms,
            }
            target_errors = (fallback,)
        errors.extend(target_errors)
        item: CollectJsonObject = {"query_terms": list(row.query_terms), "result": {
            "status": target_status,
            "inserted": row.counts.inserted if row.counts else 0,
            "updated": row.counts.updated if row.counts else 0,
            "skipped": row.counts.skipped if row.counts else 0,
            "errors": [collect_failure_to_plain(error) for error in target_errors], "links": list(row.links),
        }}
        if row.receipt:
            item.update({"provider_job_id": row.receipt.provider_job_id, "provider_type": row.receipt.provider_type,
                         "provider_status": row.receipt.provider_status, "attempt_count": row.receipt.attempt_count})
        batch_results.append(item)
    states = [
        row.observation.state
        for row in attempted
        if row.execution_state == "attempted" and row.observation is not None
    ]
    pending = any(state in {"waiting", "unknown"} for state in states)
    provider_cancelled = any(state == "cancelled" for state in states)
    failed = sum(_collect_fail_fast_stop(row) for row in attempted)
    if pending or provider_cancelled:
        status: Literal["unknown", "cancelled", "completed", "accepted", "partial", "failed"] = "unknown" if pending else "cancelled"
    elif folded.receipt_conflict:
        status = "failed"
        errors.append(_execution_error("duplicate provider_job_id has divergent receipt identity"))
    elif cancellation:
        status = "cancelled"
    elif not failed:
        status = "completed" if receipts and all(acquisition.receipt_implies_completed(item) for item in receipts) else "accepted"
    else:
        status = "partial" if failed < len(attempted) else "failed"
    delivery: list[CollectJsonValue] = [row.to_plain() for row in rows]
    raw: CollectJsonObject = {
        "inserted": counts.inserted, "updated": counts.updated, "skipped": counts.skipped,
        "links": list(links), "auto_batched": True, "batches_total": len(rows),
        "batch_parallelism": 1, "batch_parallelism_requested": requested,
        "batch_independence_policy_explicit": False, "batch_results": batch_results,
        "delivery_observations": delivery,
    }
    if pending or provider_cancelled:
        raw.update({"outcome": "OutcomeUnknown" if pending else "Cancelled", "reason": (
            "target_delivery_readback_required" if any(
                row.observation is not None
                and row.observation.state == "unknown"
                and row.observation.provider_state == "delivered"
                for row in attempted
            )
            else "provider_readback_pending" if pending else "provider_cancelled"
        )})
        errors = []
    if cancellation:
        raw["cancellation_receipt"] = cancellation.to_plain()
    if receipts:
        raw["receipts"] = [item.to_plain() for item in receipts]
        raw["provider_job_ids"] = [item.provider_job_id for item in receipts]
    result = CollectResult(
        flow=request.flow, channel=request.channel, status=status,
        inserted=counts.inserted, updated=counts.updated, skipped=counts.skipped, errors=errors,
        meta={"raw": raw, "delivery_observations": delivery, "batch_parallelism": 1,
              "batch_parallelism_requested": requested, "batch_independence_policy_explicit": False},
    )
    if len(receipts) == 1:
        receipt = receipts[0]
        result.provider_job_id, result.provider_type = receipt.provider_job_id, receipt.provider_type
        result.provider_status, result.attempt_count = receipt.provider_status, receipt.attempt_count
    from .display_meta import build_display_meta
    summary = request.source_context.get("summary")
    result.display_meta = build_display_meta(request, result, summary=summary if isinstance(summary, str) else None)
    return result


def _run_successor_collect(request: CollectRequest) -> CollectResult | None:
    """Expand a collect request and fold actual delivery facts once."""
    if request.channel not in acquisition.COLLECT_AUTO_BATCH_CHANNELS or not request.project_key or not acquisition.should_auto_batch(request):
        return None
    gateway = _successor_effect_gateway
    if gateway is None:
        return _outcome_unknown_result(request)
    children = _expand_collect_children(request)
    fail_fast = acquisition.resolve_auto_batch_fail_fast(request)
    rows = interpret_ordered_sync(
        children, initial_value=None, invoke=lambda child, _previous: _run_collect_child(child, gateway),
        continue_after=lambda row: not (fail_fast and _collect_fail_fast_stop(row)), output_value=lambda _row: None,
    )
    attempted = {row.input_index for row in rows}
    rows += tuple(_CollectDeliveryRow(
        child.element_id, child.input_index, tuple(child.request.query_terms), observe_delivery(None)
    ) for child in children if child.input_index not in attempted)
    stopped = next((
        row for row in rows
        if row.execution_state != "not_attempted" and _collect_fail_fast_stop(row)
    ), None)
    cancellation = None
    if fail_fast and stopped:
        cancellation = acquisition.CollectCancellationReceipt(
            schema_version=acquisition.COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF,
            code="FAIL_FAST_CANCELLED", message=str(
                (stopped.errors[0].get("message") if stopped.errors else None)
                or (stopped.observation.state if stopped.observation is not None else "failed")
            ),
            trigger_input_index=stopped.input_index, observed="SERIAL_EXECUTION", receipt_digest="",
        )
    return _project_collect_rows(request, rows, acquisition.resolve_auto_batch_parallelism(request), cancellation)


def _run_collect_no_batch(request: CollectRequest) -> CollectResult:
    if _successor_effect_gateway is None:
        return _attach_delivery_observation(_outcome_unknown_result(request))
    return _attach_delivery_observation(_successor_effect_gateway(request))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def normalize_query_terms(value: object) -> list[str]:
    if value is None:
        return []
    if _is_object_list(value):
        return [str(x).strip() for x in value if str(x).strip()]
    s = str(value).strip()
    return [s] if s else []


def normalize_urls(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    out: list[str] = []
    for x in value:
        s = str(x or "").strip()
        if s.startswith(("http://", "https://")):
            out.append(s)
    return out


def normalize_limit(value: object, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, memoryview):
        value = value.tobytes()
    if not isinstance(value, (str, bytes, bytearray, SupportsInt, SupportsIndex)):
        return default
    try:
        return max(1, int(value))
    except Exception:
        return default


def normalize_language(value: object) -> str | None:
    s = str(value or "").strip().lower()
    return s or None


def normalize_provider(value: object) -> str | None:
    s = str(value or "").strip().lower()
    return s or None


def _optional_text(value: CollectJsonValue) -> str | None:
    return None if value is None else str(value)


def collect_request_from_market_api(*, query_terms: list[str], max_items: int, project_key: str | None, provider: str | None = None, language: str | None = None, start_offset: int | None = None, days_back: int | None = None, enable_extraction: bool = True) -> CollectRequest:
    return CollectRequest(
        channel="search.market",
        project_key=project_key,
        query_terms=normalize_query_terms(query_terms),
        limit=normalize_limit(max_items, 20),
        provider=normalize_provider(provider),
        language=normalize_language(language) or "en",
        options={"start_offset": start_offset, "days_back": days_back, "enable_extraction": enable_extraction},
        source_context={"summary": "市场信息采集"},
    )


def collect_request_from_policy_api(*, query_terms: list[str], max_items: int, project_key: str | None, provider: str | None = None, language: str | None = None, start_offset: int | None = None, days_back: int | None = None, enable_extraction: bool = True) -> CollectRequest:
    return CollectRequest(
        channel="search.policy",
        project_key=project_key,
        query_terms=normalize_query_terms(query_terms),
        limit=normalize_limit(max_items, 20),
        provider=normalize_provider(provider),
        language=normalize_language(language) or "en",
        options={"start_offset": start_offset, "days_back": days_back, "enable_extraction": enable_extraction},
        source_context={"summary": "法规来源"},
    )


def collect_request_from_source_library_api(
    *,
    item_key: str,
    project_key: str | None,
    override_params: CollectJsonObject | None = None,
) -> CollectRequest:
    parsed: CollectJsonObject = parse_source_library_runtime_params(override_params)
    platforms = parsed.get("platforms")
    return CollectRequest(
        flow=FLOW_SOURCE_COLLECT,
        channel="source_library",
        project_key=project_key,
        item_key=str(item_key or "").strip() or None,
        query_terms=normalize_query_terms(parsed.get("query_terms")),
        urls=normalize_urls(parsed.get("urls")),
        limit=normalize_limit(parsed.get("limit")),
        provider=normalize_provider(parsed.get("provider")),
        language=normalize_language(parsed.get("language")),
        scope=_optional_text(parsed.get("scope")),
        platforms=(normalize_query_terms(platforms) if platforms is not None else None),
        options={"override_params": dict(_json_object(parsed.get("override_params")))},
        source_context={"summary": f"执行来源项 {item_key}"},
    )


def collect_request_from_url_pool(
    *,
    project_key: str | None,
    urls: list[str] | None = None,
    scope: str | None = None,
    limit: int | None = None,
    source_filter: str | None = None,
    domain: str | None = None,
    query_terms: list[str] | None = None,
    options: CollectJsonObject | None = None,
) -> CollectRequest:
    extra_options = dict(options or {})
    if source_filter is not None:
        extra_options["source_filter"] = source_filter
    if domain is not None:
        extra_options["domain"] = domain
    return CollectRequest(
        channel="url_pool",
        project_key=project_key,
        urls=normalize_urls(urls or []),
        query_terms=normalize_query_terms(query_terms or []),
        scope=(str(scope).strip() if scope else None),
        limit=normalize_limit(limit, 50),
        options=extra_options,
        source_context={"summary": "URL 池抓取并写入文档"},
    )


def run_source_library_item_compat(
    *,
    item_key: str,
    project_key: str | None = None,
    override_params: CollectJsonObject | None = None,
) -> SourceLibraryCompatResponse:
    request = collect_request_from_source_library_api(
        item_key=item_key,
        project_key=project_key,
        override_params=override_params,
    )
    result = run_collect(request)
    if _source_library_compat_projector is None:
        # kit:boundary owner=collect.runtime.compat_projector class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w03_collect_programmer_defect_boundary
        raise RuntimeError("source-library compatibility projector is not configured")
    response = _source_library_compat_projector(result)
    response.setdefault("display_meta", result.display_meta)
    return response
