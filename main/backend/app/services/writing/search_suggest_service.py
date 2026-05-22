from __future__ import annotations

from typing import Any

from ...contracts.schemas.writing import SuggestItem, SuggestRequest, SuggestResponse
from ..document_queries import query_source_library_material_rows
from ..keyword_memory import list_keyword_history, normalize_keyword

_COMMAND_ITEMS = [
    ("insert_quote", "Insert Quote", "Insert a cited quote block"),
    ("insert_summary", "Insert Summary", "Insert a source-backed summary"),
    ("open_material", "Open Material", "Open the selected related material"),
    ("run_rewrite", "Run Rewrite", "Rewrite current selection with LLM"),
]

_TEMPLATE_ITEMS = [
    ("market_weekly", "Market Weekly", "Weekly market report template"),
    ("policy_brief", "Policy Brief", "Policy brief template"),
    ("company_deep_dive", "Company Deep Dive", "Company research template"),
]


def _score(label: str, query: str) -> float:
    normalized = normalize_keyword(query)
    lowered = label.lower()
    if not normalized:
        return 0.0
    if lowered == normalized:
        return 1.0
    if lowered.startswith(normalized):
        return 0.9
    if normalized in lowered:
        return 0.75
    return 0.5


def _keyword_items(query: str, limit: int) -> list[SuggestItem]:
    rows = list_keyword_history(limit=limit, q=query)
    items: list[SuggestItem] = []
    for row in rows[:limit]:
        items.append(
            SuggestItem(
                kind="keyword",
                id=str(row.id),
                label=row.keyword,
                snippet=f"search_count={int(row.search_count or 0)} hit_count={int(row.hit_count or 0)}",
                score=_score(row.keyword, query),
                extra={"normalized_keyword": row.normalized_keyword},
            )
        )
    return items


def _template_items(query: str, limit: int) -> list[SuggestItem]:
    normalized = normalize_keyword(query)
    items: list[SuggestItem] = []
    for template_key, label, snippet in _TEMPLATE_ITEMS:
        blob = f"{template_key} {label}".lower()
        if normalized and normalized not in blob:
            continue
        items.append(
            SuggestItem(
                kind="template",
                id=template_key,
                label=label,
                snippet=snippet,
                score=_score(blob, normalized),
                extra={"template_key": template_key},
            )
        )
    return items[:limit]


def _material_items(project_key: str, query: str, limit: int) -> list[SuggestItem]:
    normalized = normalize_keyword(query)
    items: list[SuggestItem] = []
    for row in query_source_library_material_rows(project_key, query=query):
        blob = " ".join([str(row.get("item_key") or ""), str(row.get("name") or ""), str(row.get("description") or "")]).lower()
        if normalized and normalized not in blob:
            continue
        label = str(row.get("name") or row.get("item_key") or "Material").strip()
        items.append(
            SuggestItem(
                kind="material",
                id=str(row.get("item_key") or label),
                label=label,
                snippet=str(row.get("description") or row.get("channel_key") or "").strip() or None,
                score=_score(blob, normalized),
                extra={"channel_key": row.get("channel_key")},
            )
        )
        if len(items) >= limit:
            break
    return items


def _command_items(query: str, limit: int) -> list[SuggestItem]:
    normalized = normalize_keyword(query)
    items: list[SuggestItem] = []
    for command_id, label, snippet in _COMMAND_ITEMS:
        blob = f"{command_id} {label}".lower()
        if normalized and normalized not in blob:
            continue
        items.append(
            SuggestItem(
                kind="command",
                id=command_id,
                label=label,
                snippet=snippet,
                score=_score(blob, normalized),
                extra={},
            )
        )
    return items[:limit]


def suggest(payload: SuggestRequest) -> SuggestResponse:
    query = payload.query.strip()
    mode = payload.mode
    items: list[SuggestItem]
    sources: list[str]

    if mode == "keyword":
        items = _keyword_items(query, payload.limit)
        sources = ["keyword_history"]
    elif mode == "template":
        items = _template_items(query, payload.limit)
        sources = ["builtin_templates"]
    elif mode == "material":
        items = _material_items(payload.project_key, query, payload.limit)
        sources = ["source_library"]
    else:
        items = _command_items(query, payload.limit)
        sources = ["builtin_commands"]

    return SuggestResponse(
        items=items,
        suggest_type=mode,
        query=query,
        source=sources,
        query_rewrite=normalize_keyword(query),
        selection_hash=None,
    )
