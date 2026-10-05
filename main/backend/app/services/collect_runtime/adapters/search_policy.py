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
    raise TypeError("policy collection count must be an integer")


class _PolicyCollector(Protocol):
    def __call__(
        self,
        keywords: list[str],
        *,
        limit: int = 20,
        enable_extraction: bool = True,
        provider: str = "google",
        start_offset: int | None = None,
        days_back: int | None = None,
        language: str = "en",
        project_key: str | None = None,
    ) -> object:
        ...


def _optional_int(value: CollectJsonValue | None) -> int | None:
    return value if isinstance(value, int) else None


class SearchPolicyAdapter:
    def run(self, request: CollectRequest) -> CollectResult:
        from ...ingest.social import collect_policy_and_regulation

        collect_policy: _PolicyCollector = collect_policy_and_regulation
        raw_result = collect_policy(
            keywords=request.query_terms,
            limit=int(request.limit or 20),
            enable_extraction=bool(request.options.get("enable_extraction", True)),
            provider=str(request.provider or "auto"),
            start_offset=_optional_int(request.options.get("start_offset")),
            days_back=_optional_int(request.options.get("days_back")),
            language=str(request.language or "en"),
            project_key=request.project_key,
        )
        result = _json_object(raw_result)
        cr = CollectResult(
            channel=request.channel or "search.policy",
            inserted=_integer_value(result.get("inserted") or 0),
            updated=_integer_value(result.get("updated") or 0),
            skipped=_integer_value(result.get("skipped") or 0),
            meta={"raw": result},
        )
        cr.display_meta = build_display_meta(request, cr, summary="法规来源")
        return cr
