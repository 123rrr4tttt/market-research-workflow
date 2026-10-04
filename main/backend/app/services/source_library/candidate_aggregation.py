"""Pure aggregation rules shared by source-library handler-cluster entrances."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class HandlerCandidateLimits:
    per_keyword_limit: int
    global_max_candidates: int
    global_ingest_limit: int
    sitemap_max_depth: int
    sitemap_max_sitemaps: int


def normalize_query_terms(value: Any) -> list[str]:
    if isinstance(value, list):
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


def normalize_handler_candidate_limits(params: Mapping[str, Any]) -> HandlerCandidateLimits:
    raw = dict(params or {})
    return HandlerCandidateLimits(
        per_keyword_limit=max(1, int(raw.get("per_keyword_limit") or raw.get("limit") or 5)),
        global_max_candidates=max(1, int(raw.get("max_candidates") or 200)),
        global_ingest_limit=max(1, int(raw.get("ingest_limit") or raw.get("limit") or 20)),
        sitemap_max_depth=max(0, int(raw.get("sitemap_max_depth") or 2)),
        sitemap_max_sitemaps=max(1, int(raw.get("sitemap_max_sitemaps") or 50)),
    )


def batch_max_candidates(limits: HandlerCandidateLimits, term_count: int) -> int:
    return min(limits.global_max_candidates, limits.per_keyword_limit * max(1, term_count))


def unique_site_entries(runs: Iterable[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for run in runs:
        for entry in run.site_entries_used or []:
            key = str(entry.get("site_url") or entry.get("id") or "")
            if key and key not in seen:
                seen.add(key)
                out.append(entry)
    return out


def unique_candidates(runs: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for run in runs:
        for candidate in run.candidates or []:
            value = str(candidate or "").strip()
            if value and value not in seen:
                seen.add(value)
                out.append(value)
    return out


def aggregate_written_counts(runs: Iterable[Any]) -> tuple[int, int]:
    urls_new = 0
    urls_skipped = 0
    for run in runs:
        written = run.written or {}
        urls_new += int(written.get("urls_new") or 0)
        urls_skipped += int(written.get("urls_skipped") or 0)
    return urls_new, urls_skipped


def candidate_record_stats(
    candidates: list[str],
    records: list[dict[str, Any]],
    *,
    errors: list[Any],
) -> dict[str, int]:
    return {
        "fetched": len(candidates),
        "normalized": len(records),
        "dropped": max(len(candidates) - len(records), 0),
        "errors": len(errors),
    }
