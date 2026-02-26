from __future__ import annotations

from contextlib import nullcontext

from ..contracts import CollectRequest, CollectResult
from ..display_meta import build_display_meta
from ...job_logger import complete_job, fail_job, start_job
from ...projects import bind_project


class SourceLibraryAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        from ...source_library.resolver import run_item_by_key

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
                raw = run_item_by_key(
                    item_key=str(request.item_key or ""),
                    project_key=request.project_key,
                    override_params=dict(request.options.get("override_params") or {}),
                )
            nested = raw.get("result") if isinstance(raw, dict) else {}
            cr = CollectResult(
                channel=request.channel or "source_library",
                inserted=int((nested or {}).get("inserted") or 0),
                updated=int((nested or {}).get("updated") or 0),
                skipped=int((nested or {}).get("skipped") or 0),
                errors=[{"message": e} for e in ((nested or {}).get("errors") or []) if isinstance(e, str)],
                meta={"raw": raw},
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
            with (bind_project(request.project_key) if request.project_key else nullcontext()):
                fail_job(job_id, str(exc))
            raise


def to_source_library_response(raw_collect_result: CollectResult) -> dict:
    raw = (raw_collect_result.meta or {}).get("raw")
    if isinstance(raw, dict):
        return raw
    return {
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
