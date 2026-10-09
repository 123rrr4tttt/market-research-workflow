"""Pure aggregation rules shared by source-library handler-cluster entrances."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping, Sequence
from typing import TypeGuard


@dataclass(frozen=True)
class HandlerCandidateLimits:
    per_keyword_limit: int
    global_max_candidates: int
    global_ingest_limit: int
    sitemap_max_depth: int
    sitemap_max_sitemaps: int


def _is_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object(value: object) -> dict[str, object]:
    return dict(value) if _is_object(value) else {}


def _object_list(value: object) -> list[object]:
    return list(value) if _is_object_list(value) else []


def normalize_query_terms(value: object) -> list[str]:
    if _is_object_list(value):
        out: list[str] = []
        for item in value:
            term = str(item or "").strip()
            if term and term not in out:
                out.append(term)
        return out
    term = str(value or "").strip()
    return [term] if term else []


def split_query_batches(terms: list[str], chunk_size: int) -> list[list[str]]:
    clean = normalize_query_terms(terms)
    if not clean:
        return [[]]
    size = max(1, int(chunk_size))
    return [clean[index : index + size] for index in range(0, len(clean), size)]


def normalize_handler_candidate_limits(params: Mapping[object, object]) -> HandlerCandidateLimits:
    raw = dict(params)
    return HandlerCandidateLimits(
        per_keyword_limit=max(1, _int(raw.get("per_keyword_limit") or raw.get("limit"), 5)),
        global_max_candidates=max(1, _int(raw.get("max_candidates"), 200)),
        global_ingest_limit=max(1, _int(raw.get("ingest_limit") or raw.get("limit"), 20)),
        sitemap_max_depth=max(0, _int(raw.get("sitemap_max_depth"), 2)),
        sitemap_max_sitemaps=max(1, _int(raw.get("sitemap_max_sitemaps"), 50)),
    )


def batch_max_candidates(limits: HandlerCandidateLimits, term_count: int) -> int:
    return min(limits.global_max_candidates, limits.per_keyword_limit * max(1, term_count))


def unique_site_entries(runs: Iterable[object]) -> list[dict[str, object]]:
    seen: set[str] = set()
    out: list[dict[str, object]] = []
    for run in runs:
        for entry_value in _object_list(getattr(run, "site_entries_used", None)):
            entry = _object(entry_value)
            key = str(entry.get("site_url") or entry.get("id") or "")
            if key and key not in seen:
                seen.add(key)
                out.append(entry)
    return out


def unique_candidates(runs: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for run in runs:
        for candidate in _object_list(getattr(run, "candidates", None)):
            value = str(candidate or "").strip()
            if value and value not in seen:
                seen.add(value)
                out.append(value)
    return out


def aggregate_written_counts(runs: Iterable[object]) -> tuple[int, int]:
    urls_new = 0
    urls_skipped = 0
    for run in runs:
        written = _object(getattr(run, "written", None))
        urls_new += _optional_int(written.get("urls_new"))
        urls_skipped += _optional_int(written.get("urls_skipped"))
    return urls_new, urls_skipped


def candidate_record_stats(
    candidates: list[str],
    records: list[dict[str, object]],
    *,
    errors: Sequence[object],
) -> dict[str, int]:
    return {
        "fetched": len(candidates),
        "normalized": len(records),
        "dropped": max(len(candidates) - len(records), 0),
        "errors": len(errors),
    }


def _optional_int(value: object) -> int:
    if not isinstance(value, int | float | str):
        return 0
    try:
        return int(value)
    except Exception:
        return 0


def _int(value: object, default: int) -> int:
    if not isinstance(value, int | float | str):
        return default
    try:
        return int(value)
    except Exception:
        return default
