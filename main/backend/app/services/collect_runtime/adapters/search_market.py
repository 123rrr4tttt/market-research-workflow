from __future__ import annotations

import importlib
from collections.abc import Callable

from ..contracts import CollectRequest, CollectResult, CollectJsonValue, source_library_compat_response
from ..display_meta import build_display_meta
from ...task_readback_metadata import extract_runtime_readback_payload


def _json_int(value: CollectJsonValue) -> int | None:
    if isinstance(value, bool | int | float):
        return int(value)
    return None


def _json_dict(value: CollectJsonValue) -> dict[str, CollectJsonValue]:
    return value if isinstance(value, dict) else {}


def _market_collect() -> Callable[..., object]:
    module = importlib.import_module("app.services.ingest.market_web")
    function: object = getattr(module, "collect_market_info")
    if not callable(function):
        raise TypeError("market collection entrypoint must be callable")
    return function


class SearchMarketAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        start_offset = _json_int(_json_dict(request.options).get("start_offset", None))
        days_back = _json_int(_json_dict(request.options).get("days_back", None))
        kwargs: dict[str, object] = dict(
            keywords=request.query_terms,
            limit=int(request.limit or 20),
            enable_extraction=bool(request.options.get("enable_extraction", True)),
            provider=str(request.provider or "auto"),
            start_offset=start_offset,
            days_back=days_back,
            language=str(request.language or "en"),
            runtime_readback=extract_runtime_readback_payload(request.source_context, request.options),
        )
        if request.project_key:
            kwargs["project_key"] = request.project_key
        collect = _market_collect()
        result: object = collect(**kwargs)
        raw = source_library_compat_response(result)
        cr = CollectResult(
            channel=request.channel or "search.market",
            inserted=_json_int(raw.get("inserted", 0)) or 0,
            updated=_json_int(raw.get("updated", 0)) or 0,
            skipped=_json_int(raw.get("skipped", 0)) or 0,
            items=None,
            meta={"raw": raw},
        )
        cr.display_meta = build_display_meta(request, cr, summary="市场信息采集")
        return cr
