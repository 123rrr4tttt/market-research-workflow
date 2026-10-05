from __future__ import annotations

from typing import Protocol

from ..contracts import CollectJsonObject, CollectJsonValue, CollectRequest, CollectResult
from ..display_meta import build_display_meta


def _json_object(value: object) -> CollectJsonObject:
    from ..contracts import source_library_compat_response

    return source_library_compat_response(value)


def _integer_value(value: object) -> int:
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError("URL pool collection count must be an integer")


def _optional_text(value: CollectJsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


class _UrlPoolListCollector(Protocol):
    def __call__(
        self,
        urls: list[str],
        *,
        project_key: str | None = None,
        query_terms: list[str] | None = None,
        extra_params: dict[str, object] | None = None,
        enable_extraction: bool = True,
    ) -> object:
        ...


class _UrlPoolCollector(Protocol):
    def __call__(
        self,
        *,
        scope: str = "effective",
        project_key: str | None = None,
        domain: str | None = None,
        source_filter: str | None = None,
        limit: int = 50,
        query_terms: list[str] | None = None,
        extra_params: dict[str, object] | None = None,
        enable_extraction: bool = True,
    ) -> object:
        ...


class UrlPoolAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        from ...ingest.url_pool import collect_urls_from_list, collect_urls_from_pool

        query_terms = list(request.query_terms or [])
        extra_params: dict[str, object] = dict(request.options or {})
        if request.urls:
            collect_list: _UrlPoolListCollector = collect_urls_from_list
            raw_result = collect_list(
                request.urls,
                project_key=request.project_key,
                query_terms=query_terms,
                extra_params=extra_params,
                enable_extraction=bool(request.options.get("enable_extraction", True)),
            )
            result = _json_object(raw_result)
        else:
            collect_pool: _UrlPoolCollector = collect_urls_from_pool
            raw_result = collect_pool(
                scope=str(request.scope or "effective"),
                project_key=request.project_key,
                domain=_optional_text(request.options.get("domain")),
                source_filter=(
                    _optional_text(request.options.get("source_filter"))
                    or _optional_text(request.options.get("source"))
                ),
                limit=int(request.limit or 50),
                query_terms=query_terms,
                extra_params=extra_params,
                enable_extraction=bool(request.options.get("enable_extraction", True)),
            )
            result = _json_object(raw_result)
        cr = CollectResult(
            channel=request.channel or "url_pool",
            inserted=_integer_value(result.get("inserted") or 0),
            updated=_integer_value(result.get("updated") or 0),
            skipped=_integer_value(result.get("skipped") or 0),
            meta={"raw": result},
        )
        cr.display_meta = build_display_meta(request, cr, summary="URL 池抓取并写入文档")
        return cr
