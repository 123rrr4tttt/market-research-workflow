from __future__ import annotations

from contextlib import nullcontext
from typing import Annotated

from ..contracts import (
    CollectRequest,
    CollectResult,
    CollectJsonObject,
    CollectStatus,
    CollectJsonValue,
    SourceLibraryCompatResponse,
    source_library_compat_response,
)
from ..display_meta import build_display_meta
from ...job_logger import complete_job, fail_job, start_job
from ...projects import bind_project
from ...task_readback_metadata import extract_runtime_readback_payload, merge_runtime_readback_payload
from ...ingest.frontdoor_ingress import build_source_library_ingress_envelope
from ...ingest.postprocess_frontdoor import run_postprocess_frontdoor

try:
    from ...source_library.terminal_output import build_source_library_terminal_output
except Exception:  # pragma: no cover - optional compatibility import
    def build_source_library_terminal_output(
        *,
        result_payload: CollectJsonObject | None,
        collect_result: CollectResult,
    ) -> CollectJsonObject:
        payload = result_payload if isinstance(result_payload, dict) else {}
        nested = _json_object(payload.get("result"))
        errors = nested.get("errors")
        if not isinstance(errors, list):
            errors = _json_list([_failure_message(error) for error in collect_result.errors])

        fetched = int(collect_result.inserted or 0) + int(collect_result.updated or 0) + int(collect_result.skipped or 0)

        limits: CollectJsonObject = {
            "limit": None,
            "max_items": None,
            "per_keyword_limit": None,
            "max_candidates": None,
            "ingest_limit": None,
        }
        raw_result_keys: list[CollectJsonValue] = _json_list(sorted(nested.keys()))
        meta: CollectJsonObject = {
            "reason_code": "fetch_errors" if errors else "empty",
            "retryable": False,
            "provider": None,
            "provider_job_id": None,
            "trace_id": None,
            "warnings": [],
            "raw_result_keys": raw_result_keys,
        }
        response: CollectJsonObject = {
            "contract_version": "source_library.terminal_output.v1",
            "status": "partial" if errors else "ok",
            "source_mode": "protocol_search",
            "item": {
                "item_key": str(payload.get("item_key") or ""),
                "item_type": None,
                "managed_by": None,
            },
            "request": {
                "project_key": None,
                "query_terms": [],
                "time_window": {"days_back": None, "start_time": None, "end_time": None},
                "paging": {"page": None, "start_offset": None, "cursor": None},
                "limits": limits,
            },
            "results": {
                "records": [],
                "stats": {"fetched": fetched, "normalized": 0, "dropped": fetched, "errors": len(errors)},
            },
            "errors": errors,
            "meta": meta,
            "raw_snapshot": dict(payload),
        }
        return response


AUTHORITY_OUTPUT_CONTRACT_VERSION = "source_library.authority_output.v1"
COMPAT_PROJECTION_CONTRACT_VERSION = "source_library.compat_projection.v1"


def _json_object(value: object) -> CollectJsonObject:
    validated = source_library_compat_response({"value": value}).get("value")
    return validated if isinstance(validated, dict) else {}


def _json_object_list(value: object) -> list[CollectJsonObject]:
    validated = source_library_compat_response({"value": value}).get("value")
    if not isinstance(validated, list):
        return []
    return [_json_object(item) for item in validated]


def _optional_json_object(value: object) -> CollectJsonObject | None:
    validated = source_library_compat_response({"value": value}).get("value")
    return validated if isinstance(validated, dict) else None


def _json_list(value: object) -> list[CollectJsonValue]:
    validated = source_library_compat_response({"value": value}).get("value")
    return validated if isinstance(validated, list) else []


def _json_int(value: object) -> int:
    if value is None or value is False:
        return 0
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError("value is not integer-compatible")


def _failure_message(value: object) -> CollectJsonValue:
    return _json_object(value).get("message")


def _derive_source_library_status(
    *,
    raw: CollectJsonObject,
    terminal_output: CollectJsonObject,
) -> CollectStatus:
    """Keep provider ACK/readback states visible at the collect boundary."""

    terminal_status = str(terminal_output.get("status") or "").strip().lower()
    raw_status = str(raw.get("status") or "").strip().lower()
    if terminal_status == "accepted":
        return "accepted"
    if terminal_status == "failed":
        return "failed"
    if terminal_status == "cancelled":
        return "cancelled"
    if raw_status == "accepted":
        return "accepted"
    if raw_status == "failed":
        return "failed"
    if raw_status == "cancelled":
        return "cancelled"
    return "completed"


class SourceLibraryAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        from ...source_library.resolver import (
            list_effective_channels,
            list_effective_items,
            run_item_payload,
        )

        job_id = None
        runtime_options: object = request.options
        override_params = _json_object(_json_object(runtime_options).get("override_params"))
        runtime_readback = _json_object(extract_runtime_readback_payload(
            request.source_context,
            request.options,
            _optional_json_object(override_params),
        ))
        try:
            with (bind_project(request.project_key) if request.project_key else nullcontext()):
                job_id = start_job(
                    "source_library_run",
                    {
                        "item_key": request.item_key,
                        "project_key": request.project_key,
                        **({"runtime_readback": runtime_readback} if runtime_readback else {}),
                        "display_meta": build_display_meta(request, None, summary=f"执行来源项 {request.item_key or '-'}"),
                    },
                )
                override_params = _json_object(request.options.get("override_params"))
                item_key = str(request.item_key or "").strip()
                channels = _json_object_list(list_effective_channels(scope="effective", project_key=request.project_key))
                items = _json_object_list(list_effective_items(scope="effective", project_key=request.project_key))
                item_map = {str(x.get("item_key") or ""): x for x in items}
                item = item_map.get(item_key)
                if item is None:
                    raise ValueError(f"source item not found: {item_key}")
                raw_response: object = run_item_payload(
                    item=item,
                    channels=channels,
                    project_key=request.project_key,
                    override_params=override_params,
                )
            raw = _json_object(raw_response)
            nested = _json_object(raw.get("result"))
            terminal_output = build_source_library_terminal_output(
                result_payload=raw,
                collect_result=CollectResult(channel=request.channel or "source_library"),
            )
            terminal_output = _json_object(terminal_output)
            collection_status = _derive_source_library_status(
                raw=raw,
                terminal_output=terminal_output,
            )
            terminal_results = _json_object(terminal_output.get("results"))
            stats = _json_object(terminal_results.get("stats"))
            records = terminal_results.get("records")
            has_clean_signal = bool(records) or any(
                _json_int(stats.get(key)) > 0 for key in ("fetched", "normalized", "dropped", "errors")
            )
            cr = CollectResult(
                channel=request.channel or "source_library",
                status=collection_status,
                inserted=0 if has_clean_signal else _json_int(nested.get("inserted")),
                updated=0 if has_clean_signal else _json_int(nested.get("updated")),
                skipped=0 if has_clean_signal else _json_int(nested.get("skipped")),
                errors=[
                    {"message": e}
                    for e in _json_list(nested.get("errors"))
                    if isinstance(e, str)
                ],
                meta={
                    "raw": raw,
                    "terminal_output": terminal_output,
                },
            )
            cr.display_meta = build_display_meta(request, cr, summary=f"执行来源项 {request.item_key or '-'}")
            with (bind_project(request.project_key) if request.project_key else nullcontext()):
                complete_result = {
                    "inserted": cr.inserted,
                    "updated": cr.updated,
                    "skipped": cr.skipped,
                    "display_meta": cr.display_meta,
                }
                if runtime_readback:
                    complete_result["runtime_readback"] = merge_runtime_readback_payload(
                        runtime_readback,
                        runtime_readback,
                        status=cr.status,
                        event=cr.status if cr.status in {"completed", "failed", "cancelled"} else None,
                        event_source="collect_adapter",
                    )
                if cr.status == "accepted":
                    # Dispatch was accepted but no authoritative terminal
                    # readback exists yet.  Leave the ETL job open for
                    # reconciliation; never rewrite ACK as completion.
                    pass
                elif cr.status == "failed":
                    error_text = "; ".join(
                        message
                        for message in (_failure_message(item) for item in cr.errors)
                        if isinstance(message, str) and message.strip()
                    ) or "source-library provider failed"
                    fail_job(job_id, error_text)
                else:
                    complete_job(job_id, status=cr.status, result=complete_result)
            return cr
        except Exception as exc:  # noqa: BLE001
            if job_id is not None:
                with (bind_project(request.project_key) if request.project_key else nullcontext()):
                    fail_job(job_id, str(exc))
            raise


def to_source_library_response(raw_collect_result: CollectResult) -> SourceLibraryCompatResponse:
    raw = (raw_collect_result.meta or {}).get("raw")
    legacy_result: CollectJsonObject
    if isinstance(raw, dict):
        legacy_result = _json_object(raw)
    else:
        legacy_result = {
            "item_key": None,
            "channel_key": None,
            "params": {},
            "result": {
                "inserted": raw_collect_result.inserted,
                "updated": raw_collect_result.updated,
                "skipped": raw_collect_result.skipped,
                "errors": [_failure_message(error) for error in raw_collect_result.errors],
            },
            "display_meta": raw_collect_result.display_meta,
        }

    response: CollectJsonObject = dict(legacy_result)
    terminal_output = (raw_collect_result.meta or {}).get("terminal_output")
    if not isinstance(terminal_output, dict):
        terminal_output = build_source_library_terminal_output(
            result_payload=legacy_result,
            collect_result=raw_collect_result,
        )
    terminal_output = _json_object(terminal_output)
    frontdoor_ingress = build_source_library_ingress_envelope(
        terminal_output=terminal_output,
        legacy_result=legacy_result,
    )
    frontdoor_ingress = _json_object(frontdoor_ingress)
    postprocess_frontdoor = run_postprocess_frontdoor(
        ingress_envelope=frontdoor_ingress,
        run_writer=False,
    )
    postprocess_frontdoor = _json_object(postprocess_frontdoor)
    authority_output = build_source_library_authority_output(
        terminal_output=terminal_output,
        frontdoor_ingress=frontdoor_ingress,
        postprocess_frontdoor=postprocess_frontdoor,
        legacy_result=legacy_result,
    )
    compat_projection = build_source_library_compat_projection(
        legacy_result=legacy_result,
        authority_output=authority_output,
    )
    response["terminal_output"] = terminal_output
    response["frontdoor_ingress"] = frontdoor_ingress
    response["postprocess_frontdoor"] = postprocess_frontdoor
    response["authority_output"] = authority_output
    response["compat_projection"] = compat_projection
    response["legacy_result"] = legacy_result
    response["legacy_result_is_deprecated"] = True
    return source_library_compat_response(response)


def build_source_library_authority_output(
    *,
    terminal_output: CollectJsonObject,
    frontdoor_ingress: CollectJsonObject,
    postprocess_frontdoor: CollectJsonObject,
    legacy_result: CollectJsonObject,
) -> Annotated[
    CollectJsonObject,
    "kit:non-authoritative derived_as=view fact_source=terminal_output+frontdoor_ingress+postprocess_frontdoor+legacy_result witness=test:test_w03_ingest_ports_authority_metadata",
]:
    terminal_results = _json_object(terminal_output.get("results"))
    terminal_meta = _json_object(terminal_output.get("meta"))
    provider_handoff = _json_object(terminal_meta.get("provider_handoff"))
    route_profile = _json_object(terminal_meta.get("frontdoor_route_profile"))
    router_contract = _json_object(terminal_meta.get("frontdoor_router_contract"))
    if not router_contract:
        router_contract = _json_object(route_profile.get("router_contract"))
    if not router_contract:
        router_contract = _json_object(provider_handoff.get("router_contract"))
    record_stats = _json_object(terminal_results.get("stats"))
    postprocess_data = _json_object(postprocess_frontdoor.get("data"))
    dispatch_plan = _json_object(postprocess_data.get("dispatch_plan"))
    legacy_nested = _json_object(legacy_result.get("result"))
    write_effects_errors = _json_list(legacy_nested.get("errors"))

    normalized_records = _json_int(record_stats.get("normalized"))
    write_inserted = _json_int(legacy_nested.get("inserted"))
    write_updated = _json_int(legacy_nested.get("updated"))
    write_skipped = _json_int(legacy_nested.get("skipped"))
    write_error_count = sum(1 for item in write_effects_errors if str(item or "").strip())
    bootstrap_required = normalized_records + write_inserted + write_updated == 0 and write_error_count == 0

    return {
        "contract_version": AUTHORITY_OUTPUT_CONTRACT_VERSION,
        "authority_path": "terminal_output -> frontdoor_ingress -> postprocess_frontdoor",
        "authority_fields": [
            "terminal_output",
            "frontdoor_ingress",
            "postprocess_frontdoor",
            "summary.record_stats",
            "summary.handoff",
            "summary.write_effects",
        ],
        "terminal_output": dict(terminal_output),
        "frontdoor_ingress": dict(frontdoor_ingress),
        "postprocess_frontdoor": dict(postprocess_frontdoor),
        "summary": {
            "status": str(terminal_output.get("status") or "ok"),
            "source_mode": str(terminal_output.get("source_mode") or "protocol_search"),
            "record_stats": {
                "fetched": _json_int(record_stats.get("fetched")),
                "normalized": normalized_records,
                "dropped": _json_int(record_stats.get("dropped")),
                "errors": _json_int(record_stats.get("errors")),
                "source": "terminal_output.results.stats",
            },
            "handoff": {
                "admission": str(postprocess_data.get("admission") or "reject"),
                "run_extraction": bool(dispatch_plan.get("run_extraction")),
                "run_writer": bool(dispatch_plan.get("run_writer")),
                "writer_result": postprocess_data.get("writer_result"),
                "source": "postprocess_frontdoor.data",
            },
            "provider_handoff": {
                "present": bool(provider_handoff),
                "handoff_kind": provider_handoff.get("handoff_kind"),
                "channel_key": provider_handoff.get("channel_key"),
                "provider": provider_handoff.get("provider"),
                "provider_type": provider_handoff.get("provider_type"),
                "provider_dispatch": provider_handoff.get("provider_dispatch"),
                "provider_job_id": provider_handoff.get("provider_job_id"),
                "provider_status": provider_handoff.get("provider_status"),
                "route_hint": route_profile.get("route_hint") or provider_handoff.get("route_hint"),
                "fetch_strategy": route_profile.get("fetch_strategy") or provider_handoff.get("fetch_strategy"),
                "render_required": bool(route_profile.get("render_required") or provider_handoff.get("render_required")),
                "router_state": router_contract.get("router_state"),
                "router_reason_code": router_contract.get("reason_code"),
                "fallback_boundary": _json_object(router_contract.get("fallback_boundary")),
                "source": "terminal_output.meta.provider_handoff",
            },
            "write_effects": {
                "inserted": write_inserted,
                "updated": write_updated,
                "skipped": write_skipped,
                "errors": list(write_effects_errors),
                "source": "legacy_result.result",
            },
            "bootstrap_required": bootstrap_required,
        },
    }


def build_source_library_compat_projection(
    *,
    legacy_result: CollectJsonObject,
    authority_output: CollectJsonObject,
) -> Annotated[
    CollectJsonObject,
    "kit:non-authoritative derived_as=view fact_source=authority_output witness=test:test_w03_ingest_ports_authority_metadata",
]:
    return {
        "contract_version": COMPAT_PROJECTION_CONTRACT_VERSION,
        "status": "retained_compat",
        "observed_status": str(_json_object(authority_output.get("summary")).get("status") or "unknown"),
        "deprecated": True,
        "authority_reference": {
            "authority_output": "authority_output",
            "terminal_output": "authority_output.terminal_output",
            "frontdoor_ingress": "authority_output.frontdoor_ingress",
            "postprocess_frontdoor": "authority_output.postprocess_frontdoor",
        },
        "deprecated_fields": ["legacy_result"],
        "removal_gates": [
            "caller matrix + source_collect consumers migrated to authority_output",
            "source-library core contract and smoke pack green with authority_output assertions",
            "closure note records retained compat lifecycle and rollback handle",
        ],
        "legacy_result": dict(legacy_result),
        "legacy_result_is_deprecated": True,
        "authority_summary": _json_object(authority_output.get("summary")),
    }
