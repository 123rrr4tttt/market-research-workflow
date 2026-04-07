from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from ..contracts import CollectRequest, CollectResult
from ..display_meta import build_display_meta
from ...job_logger import complete_job, fail_job, start_job
from ...projects import bind_project
from ...ingest.frontdoor_ingress import build_source_library_ingress_envelope
from ...ingest.postprocess_frontdoor import run_postprocess_frontdoor

try:
    from ...source_library.terminal_output import build_source_library_terminal_output
except Exception:  # pragma: no cover - optional compatibility import
    def build_source_library_terminal_output(
        *,
        result_payload: dict[str, Any] | None,
        collect_result: CollectResult,
    ) -> dict[str, Any]:
        payload = result_payload if isinstance(result_payload, dict) else {}
        nested = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        errors = nested.get("errors")
        if not isinstance(errors, list):
            errors = [e.get("message") for e in (collect_result.errors or []) if isinstance(e, dict)]

        fetched = int(collect_result.inserted or 0) + int(collect_result.updated or 0) + int(collect_result.skipped or 0)

        return {
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
                "limits": {
                    "limit": None,
                    "max_items": None,
                    "per_keyword_limit": None,
                    "max_candidates": None,
                    "ingest_limit": None,
                },
            },
            "results": {
                "records": [],
                "stats": {"fetched": fetched, "normalized": 0, "dropped": fetched, "errors": len(errors)},
            },
            "errors": errors,
            "meta": {
                "reason_code": "fetch_errors" if errors else "empty",
                "retryable": False,
                "provider": None,
                "provider_job_id": None,
                "trace_id": None,
                "warnings": [],
                "raw_result_keys": sorted(nested.keys()),
            },
            "raw_snapshot": dict(payload),
        }

class SourceLibraryAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        from ...source_library.resolver import (
            list_effective_channels,
            list_effective_items,
            run_item_payload,
        )

        job_id = None
        try:
            with (bind_project(request.project_key) if request.project_key else nullcontext()):
                job_id = start_job(
                    "source_library_run",
                    {
                        "item_key": request.item_key,
                        "project_key": request.project_key,
                        "display_meta": build_display_meta(request, None, summary=f"执行来源项 {request.item_key or '-'}"),
                    },
                )
                override_params = dict(request.options.get("override_params") or {})
                item_key = str(request.item_key or "").strip()
                channels = list_effective_channels(scope="effective", project_key=request.project_key)
                items = list_effective_items(scope="effective", project_key=request.project_key)
                item_map = {str(x.get("item_key") or ""): x for x in items}
                item = item_map.get(item_key)
                if item is None:
                    raise ValueError(f"source item not found: {item_key}")
                raw = run_item_payload(
                    item=item,
                    channels=channels,
                    project_key=request.project_key,
                    override_params=override_params,
                )
            nested = raw.get("result") if isinstance(raw, dict) else {}
            terminal_output = build_source_library_terminal_output(
                result_payload=raw if isinstance(raw, dict) else None,
                collect_result=CollectResult(channel=request.channel or "source_library"),
            )
            stats = (terminal_output.get("results") or {}).get("stats") if isinstance(terminal_output, dict) else {}
            records = (terminal_output.get("results") or {}).get("records") if isinstance(terminal_output, dict) else []
            has_clean_signal = bool(records) or any(
                int((stats or {}).get(key) or 0) > 0 for key in ("fetched", "normalized", "dropped", "errors")
            )
            cr = CollectResult(
                channel=request.channel or "source_library",
                inserted=0 if has_clean_signal else int((nested or {}).get("inserted") or 0),
                updated=0 if has_clean_signal else int((nested or {}).get("updated") or 0),
                skipped=0 if has_clean_signal else int((nested or {}).get("skipped") or 0),
                errors=[{"message": e} for e in ((nested or {}).get("errors") or []) if isinstance(e, str)],
                meta={
                    "raw": raw,
                    "terminal_output": terminal_output,
                },
            )
            cr.display_meta = build_display_meta(request, cr, summary=f"执行来源项 {request.item_key or '-'}")
            with (bind_project(request.project_key) if request.project_key else nullcontext()):
                complete_job(job_id, result={
                    "inserted": cr.inserted,
                    "updated": cr.updated,
                    "skipped": cr.skipped,
                    "display_meta": cr.display_meta,
                })
            return cr
        except Exception as exc:  # noqa: BLE001
            if job_id is not None:
                with (bind_project(request.project_key) if request.project_key else nullcontext()):
                    fail_job(job_id, str(exc))
            raise


def to_source_library_response(raw_collect_result: CollectResult) -> dict:
    raw = (raw_collect_result.meta or {}).get("raw")
    legacy_result: dict[str, Any]
    if isinstance(raw, dict):
        legacy_result = dict(raw)
    else:
        legacy_result = {
            "item_key": None,
            "channel_key": None,
            "params": {},
            "result": {
                "inserted": raw_collect_result.inserted,
                "updated": raw_collect_result.updated,
                "skipped": raw_collect_result.skipped,
                "errors": [e.get("message") for e in raw_collect_result.errors if isinstance(e, dict)],
            },
            "display_meta": raw_collect_result.display_meta,
        }

    response = dict(legacy_result)
    terminal_output = (raw_collect_result.meta or {}).get("terminal_output")
    if not isinstance(terminal_output, dict):
        terminal_output = build_source_library_terminal_output(
            result_payload=legacy_result if isinstance(legacy_result, dict) else None,
            collect_result=raw_collect_result,
        )
    frontdoor_ingress = build_source_library_ingress_envelope(
        terminal_output=terminal_output,
        legacy_result=legacy_result if isinstance(legacy_result, dict) else None,
    )
    postprocess_frontdoor = run_postprocess_frontdoor(
        ingress_envelope=frontdoor_ingress,
        run_writer=False,
    )
    response["terminal_output"] = terminal_output
    response["frontdoor_ingress"] = frontdoor_ingress
    response["postprocess_frontdoor"] = postprocess_frontdoor
    response["legacy_result"] = legacy_result
    response["legacy_result_is_deprecated"] = True
    return response
