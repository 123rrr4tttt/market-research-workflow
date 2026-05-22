from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Callable, Iterable

from ..document_queries.writing_material_queries import query_source_library_material_rows
from ..resource_pool.url_utils import domain_from_url
from ..source_library.source_candidate_trust import (
    build_candidate_search_queries,
    rank_source_library_items_for_query,
)

CLUE_CHAIN_SOURCE_LIBRARY_EXPANSION_CONTRACT_VERSION = "clue_chain.source_library_expansion.v1"
SOURCE_LIBRARY_SEARCH_MODE = "source_library_search"

SourceItemLoader = Callable[[str, str], list[dict[str, Any]]]


def expand_source_library_hop(
    *,
    chain_id: str,
    project_key: str,
    frontier_query: str | None = None,
    frontier: dict[str, Any] | None = None,
    source_library_items: list[dict[str, Any]] | None = None,
    source_item_loader: SourceItemLoader | None = None,
    domains: list[str] | None = None,
    max_candidates: int = 10,
) -> dict[str, Any]:
    """Build a deterministic Clue Chain hop from Source Library candidates.

    The hop is read-only: it ranks source-library item fixtures or rows and
    returns evidence/candidates for later review. It never executes crawlers,
    writes resource-pool rows, or performs public-network search.
    """

    normalized_chain_id = _required_text(chain_id, "chain_id")
    normalized_project_key = _required_text(project_key, "project_key")
    query = _resolve_query(frontier_query=frontier_query, frontier=frontier)
    limit = _normalize_limit(max_candidates)
    domain_values = _normalize_domains(domains)
    raw_items = _load_source_items(
        project_key=normalized_project_key,
        query=query,
        source_library_items=source_library_items,
        source_item_loader=source_item_loader,
    )
    ranked_items = rank_source_library_items_for_query(
        raw_items,
        query=query,
        domains=domain_values,
        limit=limit,
    )
    search_queries = build_candidate_search_queries(query=query, domains=domain_values, limit=8)
    input_digest = _stable_digest(
        {
            "chain_id": normalized_chain_id,
            "project_key": normalized_project_key,
            "query": query,
            "domains": domain_values,
            "limit": limit,
            "source_item_keys": [str(item.get("item_key") or "") for item in raw_items],
        },
        size=16,
    )
    hop_id = f"hop_src_{input_digest}"

    evidence_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    by_item_key = {str(item.get("item_key") or "").strip(): dict(item or {}) for item in raw_items if isinstance(item, dict)}
    for index, ranked in enumerate(ranked_items, start=1):
        item_key = str(ranked.get("item_key") or "").strip()
        raw_item = by_item_key.get(item_key, {})
        evidence_id = _stable_id(
            "ev_src",
            normalized_chain_id,
            hop_id,
            query,
            item_key,
            size=18,
        )
        source_ref = _build_source_ref(
            item={**raw_item, **ranked},
            project_key=normalized_project_key,
            query=query,
            evidence_id=evidence_id,
        )
        aliases = _candidate_aliases(raw_item=raw_item, ranked_item=ranked)
        dedupe_key = _dedupe_key(
            project_key=normalized_project_key,
            item_key=item_key,
            aliases=aliases,
            source_ref=source_ref,
        )
        evidence_rows.append(
            {
                "evidence_id": evidence_id,
                "chain_id": normalized_chain_id,
                "hop_id": hop_id,
                "evidence_type": "source_library_item",
                "source_ref": source_ref,
                "query": query,
                "rank": index,
                "score": float(ranked.get("score") or 0.0),
                "title": str(ranked.get("name") or item_key),
                "summary": str(raw_item.get("description") or ""),
                "matched_tokens": list(ranked.get("matched_tokens") or []),
                "raw_item": _stable_item_snapshot(raw_item),
                "trace": {
                    "ranker": "source_candidate_trust.rank_source_library_items_for_query",
                    "network_fetch_performed": False,
                    "external_write_performed": False,
                },
            }
        )
        candidate_rows.append(
            {
                "candidate_id": _stable_id(
                    "cand_src",
                    normalized_chain_id,
                    hop_id,
                    dedupe_key,
                    size=18,
                ),
                "chain_id": normalized_chain_id,
                "hop_id": hop_id,
                "candidate_type": "source_library_item",
                "source_ref": source_ref,
                "query": query,
                "rank": index,
                "score": float(ranked.get("score") or 0.0),
                "dedupe_key": dedupe_key,
                "evidence_id": evidence_id,
                "aliases": aliases,
                "decision_status": "pending_review",
                "promote_guard": "requires_chain_decision",
            }
        )

    candidates = merge_candidate_aliases(candidate_rows)
    selected_evidence_ids = set()
    for candidate in candidates:
        selected_evidence_ids.add(str(candidate.get("evidence_id") or ""))
        for merged in candidate.get("merged_from") or []:
            if isinstance(merged, dict):
                selected_evidence_ids.add(str(merged.get("evidence_id") or ""))
    evidence = [row for row in evidence_rows if str(row.get("evidence_id") or "") in selected_evidence_ids]

    return {
        "contract_version": CLUE_CHAIN_SOURCE_LIBRARY_EXPANSION_CONTRACT_VERSION,
        "chain_id": normalized_chain_id,
        "project_key": normalized_project_key,
        "hop": {
            "hop_id": hop_id,
            "chain_id": normalized_chain_id,
            "expansion_mode": SOURCE_LIBRARY_SEARCH_MODE,
            "frontier": _stable_frontier(frontier=frontier, query=query),
            "query": query,
            "status": "candidate_ready",
            "contract_version": CLUE_CHAIN_SOURCE_LIBRARY_EXPANSION_CONTRACT_VERSION,
        },
        "evidence": evidence,
        "candidates": candidates,
        "replay_manifest": {
            "contract_version": CLUE_CHAIN_SOURCE_LIBRARY_EXPANSION_CONTRACT_VERSION,
            "expansion_mode": SOURCE_LIBRARY_SEARCH_MODE,
            "chain_id": normalized_chain_id,
            "project_key": normalized_project_key,
            "query": query,
            "domains": domain_values,
            "max_candidates": limit,
            "source_item_keys": [str(item.get("item_key") or "") for item in raw_items],
            "search_queries": search_queries,
            "fixture_required": source_library_items is not None,
            "network_fetch_performed": False,
            "external_write_performed": False,
            "input_digest": input_digest,
        },
        "trace": {
            "source_items_loaded": len(raw_items),
            "source_items_ranked": len(ranked_items),
            "candidate_count": len(candidates),
            "evidence_count": len(evidence),
            "merged_alias_count": sum(len(candidate.get("merged_from") or []) for candidate in candidates),
            "ranker": "source_candidate_trust.rank_source_library_items_for_query",
            "alias_merge": "normalized_alias_or_dedupe_key",
            "network_fetch_performed": False,
            "external_write_performed": False,
        },
    }


def merge_candidate_aliases(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge candidates with matching dedupe keys or normalized aliases."""

    merged: list[dict[str, Any]] = []
    index_by_key: dict[str, int] = {}

    for candidate in candidates:
        row = dict(candidate or {})
        aliases = _normalize_aliases(row.get("aliases"))
        row["aliases"] = aliases
        candidate_keys = _candidate_merge_keys(row, aliases)
        target_index = _find_merge_target(candidate_keys, index_by_key)
        if target_index is None:
            index_by_key.update({key: len(merged) for key in candidate_keys})
            row.setdefault("merged_from", [])
            merged.append(row)
            continue

        existing = merged[target_index]
        existing["aliases"] = _dedupe_text([*list(existing.get("aliases") or []), *aliases])
        existing["score"] = max(float(existing.get("score") or 0.0), float(row.get("score") or 0.0))
        existing["rank"] = min(int(existing.get("rank") or 999_999), int(row.get("rank") or 999_999))
        existing.setdefault("merged_from", [])
        existing["merged_from"].append(
            {
                "candidate_id": row.get("candidate_id"),
                "dedupe_key": row.get("dedupe_key"),
                "evidence_id": row.get("evidence_id"),
                "rank": row.get("rank"),
                "score": row.get("score"),
            }
        )
        for key in candidate_keys:
            index_by_key[key] = target_index

    merged.sort(key=lambda row: (int(row.get("rank") or 999_999), str(row.get("dedupe_key") or "")))
    for index, row in enumerate(merged, start=1):
        row["rank"] = index
    return merged


def _load_source_items(
    *,
    project_key: str,
    query: str,
    source_library_items: list[dict[str, Any]] | None,
    source_item_loader: SourceItemLoader | None,
) -> list[dict[str, Any]]:
    if source_library_items is not None:
        return [dict(item or {}) for item in source_library_items if isinstance(item, dict)]
    if source_item_loader is not None:
        loaded_items = source_item_loader(project_key, query)
    else:
        loaded_items = query_source_library_material_rows(project_key, query=query)
    return [dict(item or {}) for item in loaded_items if isinstance(item, dict)]


def _resolve_query(*, frontier_query: str | None, frontier: dict[str, Any] | None) -> str:
    candidates = [
        frontier_query,
        (frontier or {}).get("query") if isinstance(frontier, dict) else None,
        (frontier or {}).get("label") if isinstance(frontier, dict) else None,
        (frontier or {}).get("name") if isinstance(frontier, dict) else None,
    ]
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    raise ValueError("frontier_query or frontier.query is required")


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _normalize_limit(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = 10
    return max(1, min(50, parsed))


def _normalize_domains(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []
    domains: list[str] = []
    for raw in raw_values:
        text = str(raw or "").strip().lower()
        if not text:
            continue
        if "://" in text:
            text = str(domain_from_url(text) or "").strip().lower()
        text = text.split("/", 1)[0].strip().lstrip(".")
        if text.startswith("www."):
            text = text[4:]
        if text and text not in domains:
            domains.append(text)
    return domains


def _build_source_ref(
    *,
    item: dict[str, Any],
    project_key: str,
    query: str,
    evidence_id: str,
) -> dict[str, Any]:
    item_key = str(item.get("item_key") or "").strip()
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    locator = _first_text(
        item_key,
        item.get("locator"),
        params.get("template"),
        params.get("site_url"),
        params.get("url"),
    )
    return {
        "tool": "clue_chain.source_library_search",
        "entrypoint": "clue_chains.source_library_expansion",
        "source_mode": SOURCE_LIBRARY_SEARCH_MODE,
        "project_key": project_key,
        "query": query,
        "query_terms": [query],
        "locator": locator,
        "item_key": item_key,
        "channel_key": _first_text(item.get("channel_key"), None),
        "item_type": _first_text(item.get("item_type"), extra.get("item_type"), None),
        "managed_by": _first_text(item.get("managed_by"), extra.get("managed_by"), None),
        "entry_type": _first_text(extra.get("expected_entry_type"), params.get("expected_entry_type"), None),
        "source_family": "source_library",
        "evidence_id": evidence_id,
    }


def _candidate_aliases(*, raw_item: dict[str, Any], ranked_item: dict[str, Any]) -> list[str]:
    tags = raw_item.get("tags") if isinstance(raw_item.get("tags"), list) else []
    params = raw_item.get("params") if isinstance(raw_item.get("params"), dict) else {}
    aliases = [
        ranked_item.get("item_key"),
        ranked_item.get("name"),
        raw_item.get("name"),
        params.get("domain"),
        params.get("site_url"),
        *tags,
    ]
    return _normalize_aliases(aliases)


def _normalize_aliases(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_values = [values]
    elif isinstance(values, Iterable):
        raw_values = list(values)
    else:
        raw_values = []
    return _dedupe_text(str(value or "").strip() for value in raw_values if str(value or "").strip())


def _dedupe_key(
    *,
    project_key: str,
    item_key: str,
    aliases: list[str],
    source_ref: dict[str, Any],
) -> str:
    normalized_item_key = _normalize_alias(item_key)
    if normalized_item_key:
        return f"source_library:{project_key}:{normalized_item_key}"
    alias = _normalize_alias(aliases[0] if aliases else "")
    locator = _normalize_alias(str(source_ref.get("locator") or ""))
    return f"source_library:{project_key}:{alias or locator}"


def _candidate_merge_keys(row: dict[str, Any], aliases: list[str]) -> list[str]:
    keys = []
    dedupe_key = str(row.get("dedupe_key") or "").strip()
    if dedupe_key:
        keys.append(f"dedupe:{dedupe_key}")
    keys.extend(f"alias:{_normalize_alias(alias)}" for alias in aliases if _normalize_alias(alias))
    return _dedupe_text(keys)


def _find_merge_target(keys: list[str], index_by_key: dict[str, int]) -> int | None:
    for key in keys:
        if key in index_by_key:
            return index_by_key[key]
    return None


def _stable_frontier(*, frontier: dict[str, Any] | None, query: str) -> dict[str, Any]:
    payload = dict(frontier or {}) if isinstance(frontier, dict) else {}
    return {
        "node_id": _first_text(payload.get("node_id"), payload.get("id"), None),
        "label": _first_text(payload.get("label"), payload.get("name"), query),
        "query": query,
    }


def _stable_item_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_key": item.get("item_key"),
        "name": item.get("name"),
        "channel_key": item.get("channel_key"),
        "description": item.get("description"),
        "tags": list(item.get("tags") or []) if isinstance(item.get("tags"), list) else [],
        "scope": item.get("scope"),
        "enabled": bool(item.get("enabled", True)),
        "extra": dict(item.get("extra") or {}) if isinstance(item.get("extra"), dict) else {},
    }


def _stable_id(prefix: str, *parts: str, size: int = 16) -> str:
    return f"{prefix}_{_stable_digest(list(parts), size=size)}"


def _stable_digest(value: Any, *, size: int = 16) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()[:size]


def _normalize_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _dedupe_text(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out
