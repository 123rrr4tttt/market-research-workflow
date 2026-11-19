from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeGuard

from ..item_resolver import ExecutionPayload, ExecutionRequest
from ..candidate_aggregation import (
    aggregate_written_counts,
    unique_candidates,
    unique_site_entries,
)
from ..types import SourceClusterExecutor

_BENIGN_ERROR_MARKERS = frozenset(
    {"url_term_filter_empty_fallback_used", "url_term_filter_empty_no_fallback"}
)


class SearchObservationResult(Protocol):
    @property
    def site_entries_used(self) -> Sequence[Mapping[str, object]]: ...

    @property
    def candidates(self) -> Sequence[str]: ...

    @property
    def written(self) -> Mapping[str, object] | None: ...

    @property
    def errors(self) -> Sequence[Mapping[str, object]] | None: ...


@dataclass(frozen=True)
class FoldedSearchObservations:
    site_entries_used: list[dict[str, object]]
    candidates: list[str]
    written_urls_new: int
    written_urls_skipped: int
    runtime_diagnostics: list[dict[str, object]]
    relevance_review_queues: list[dict[str, object]]
    error_details: list[dict[str, object]]
    errors: list[str]


def _is_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object_view(value: object) -> dict[str, object]:
    return dict(value) if _is_object(value) else {}


def _object_views(value: object) -> list[dict[str, object]]:
    if not _is_object_list(value):
        return []
    return [_object_view(item) for item in value]


def fold_search_observations(
    results: Sequence[SearchObservationResult],
    *,
    deduplicate_error_messages: bool,
) -> FoldedSearchObservations:
    runtime_diagnostics: list[dict[str, object]] = []
    relevance_review_queues: list[dict[str, object]] = []
    error_details: list[dict[str, object]] = []
    errors: list[str] = []
    seen_runtime: set[str] = set()

    for result in results:
        runtime_rows = _object_views(getattr(result, "runtime_diagnostics", None))
        if not runtime_rows:
            runtime_rows = _object_views(getattr(result, "site_entries_used", None))
        for diagnostic in runtime_rows:
            key = str(diagnostic.get("site_url") or diagnostic.get("id") or "")
            if key and key not in seen_runtime:
                seen_runtime.add(key)
                runtime_diagnostics.append(diagnostic)

        review_queue = _object_view(getattr(result, "relevance_review_queue", None))
        if review_queue:
            relevance_review_queues.append(review_queue)

        for raw_error in result.errors or []:
            error = _object_view(raw_error)
            error_details.append(error)
            message = str(error.get("error") or "").strip()
            if not message or message in _BENIGN_ERROR_MARKERS:
                continue
            if not deduplicate_error_messages or message not in errors:
                errors.append(message)

    written_urls_new, written_urls_skipped = aggregate_written_counts(results)
    return FoldedSearchObservations(
        site_entries_used=unique_site_entries(results),
        candidates=unique_candidates(results),
        written_urls_new=written_urls_new,
        written_urls_skipped=written_urls_skipped,
        runtime_diagnostics=runtime_diagnostics,
        relevance_review_queues=relevance_review_queues,
        error_details=error_details,
        errors=errors,
    )


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
