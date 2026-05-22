from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json
import re
from typing import Any, Callable

from sqlalchemy import Text, cast, func, or_, select

from app.models.base import SessionLocal
from app.models.entities import (
    Document,
    GraphNodeRecord,
    KeywordHistory,
    KeywordPrior,
    MarketMetricPoint,
    MarketStat,
    PriceObservation,
    Product,
    ResourcePoolSiteEntry,
    ResourcePoolUrl,
    SearchHistory,
    Source,
)
from app.services.document_queries import build_structured_data_search_document_query_envelope
from app.services.projects import bind_project


StructuredSearchResult = dict[str, Any]
DatasetHandler = Callable[[Any, str, int], tuple[list[dict[str, Any]], int | None]]
DatasetItemMapper = Callable[[Any], dict[str, Any]]


DATASET_ORDER: tuple[str, ...] = (
    "documents",
    "graph_nodes",
    "market_stats",
    "metric_points",
    "products",
    "price_observations",
    "resource_pool_urls",
    "resource_pool_sites",
    "keyword_history",
    "keyword_priors",
    "search_history",
    "sources",
)

DATASET_LABELS: dict[str, str] = {
    "documents": "Documents and extracted JSON",
    "graph_nodes": "Projected graph nodes",
    "market_stats": "Market statistics",
    "metric_points": "Metric time-series points",
    "products": "Products",
    "price_observations": "Price observations",
    "resource_pool_urls": "Resource-pool URLs",
    "resource_pool_sites": "Resource-pool site entries",
    "keyword_history": "Keyword history",
    "keyword_priors": "Keyword priors",
    "search_history": "Search history",
    "sources": "Document sources",
}

_GENERIC_DATA_QUESTIONS = (
    "项目里有什么数据",
    "项目有什么数据",
    "当前项目有什么数据",
    "本项目有什么数据",
    "现在有哪些数据可以用",
    "有哪些数据可以用",
    "有什么数据可以用",
    "项目里有哪些数据",
    "当前有哪些数据",
)


def query_project_structured_data(
    *,
    project_key: str | None,
    query: str | None = None,
    limit: int = 12,
    datasets: list[str] | tuple[str, ...] | None = None,
) -> StructuredSearchResult:
    """Read already-stored project data for model-owned conversational answers.

    This tool intentionally performs only tenant-schema reads. It does not
    trigger collection, enrichment, workflow execution, or artifact writes.
    """

    resolved_project_key = str(project_key or "").strip()
    if not resolved_project_key:
        return {
            "contract_version": "project.structured_data.search.v1",
            "project_key": project_key,
            "query": str(query or "").strip(),
            "items": [],
            "dataset_results": [],
            "dataset_counts": {},
            "total_matches": 0,
            "errors": [{"dataset": "project", "type": "missing_project_key", "message": "project_key is required"}],
        }

    query_text = _normalize_query(query)
    capped_limit = max(1, min(50, int(limit or 12)))
    selected_datasets = _normalize_datasets(datasets)
    per_dataset_limit = max(3, min(25, capped_limit))
    dataset_results: list[dict[str, Any]] = []
    flat_items: list[dict[str, Any]] = []
    fallback_items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with bind_project(resolved_project_key):
        with SessionLocal() as session:
            failed_datasets: set[str] = set()
            for dataset in selected_datasets:
                handler = _DATASET_HANDLERS.get(dataset)
                if handler is None:
                    errors.append(
                        {
                            "dataset": dataset,
                            "type": "unsupported_dataset",
                            "message": f"unsupported structured dataset: {dataset}",
                        }
                    )
                    continue
                try:
                    items, total_rows = handler(session, query_text, per_dataset_limit)
                except Exception as exc:  # noqa: BLE001
                    session.rollback()
                    failed_datasets.add(dataset)
                    errors.append(
                        {
                            "dataset": dataset,
                            "type": exc.__class__.__name__,
                            "message": str(exc),
                        }
                    )
                    items = []
                    total_rows = None
                dataset_results.append(
                    {
                        "dataset": dataset,
                        "label": DATASET_LABELS.get(dataset, dataset),
                        "sample_count": len(items),
                        "total_rows": total_rows,
                        "items": items,
                    }
                )
                flat_items.extend(items)
            if query_text and not flat_items and _should_include_inventory_fallback(query_text):
                fallback_limit = max(2, min(5, per_dataset_limit))
                for dataset in selected_datasets:
                    if dataset in failed_datasets:
                        continue
                    handler = _DATASET_HANDLERS.get(dataset)
                    if handler is None:
                        continue
                    try:
                        items, _total_rows = handler(session, "", fallback_limit)
                    except Exception as exc:  # noqa: BLE001
                        session.rollback()
                        errors.append(
                            {
                                "dataset": dataset,
                                "type": exc.__class__.__name__,
                                "message": str(exc),
                                "phase": "inventory_fallback",
                            }
                        )
                        continue
                    for item in items:
                        item.setdefault("dataset", dataset)
                        item["match_type"] = "inventory_fallback"
                    fallback_items.extend(items)

    dataset_counts = {item["dataset"]: item["sample_count"] for item in dataset_results}
    dataset_total_rows = {item["dataset"]: item["total_rows"] for item in dataset_results if item.get("total_rows") is not None}
    total_stored_rows = sum(int(value or 0) for value in dataset_total_rows.values())
    inventory = [
        {
            "dataset": item["dataset"],
            "label": item["label"],
            "sample_count": item["sample_count"],
            "total_rows": item["total_rows"],
        }
        for item in dataset_results
    ]
    result_items = (flat_items or fallback_items)[:capped_limit]
    document_query_envelope = build_structured_data_search_document_query_envelope(
        project_key=resolved_project_key,
        query=query_text,
        datasets_requested=selected_datasets,
        limit=capped_limit,
        items=result_items,
        query_mode="inventory" if not query_text else "search",
        total_matches=len(flat_items),
        total_stored_rows=total_stored_rows,
        fallback_used=bool(fallback_items and not flat_items),
    )
    document_query_data = document_query_envelope["data"]
    return {
        "contract_version": "project.structured_data.search.v1",
        "project_key": resolved_project_key,
        "query": query_text,
        "query_mode": "inventory" if not query_text else "search",
        "datasets_requested": selected_datasets,
        "inventory": inventory,
        "dataset_counts": dataset_counts,
        "dataset_total_rows": dataset_total_rows,
        "total_stored_rows": total_stored_rows,
        "total_matches": len(flat_items),
        "fallback_used": bool(fallback_items and not flat_items),
        "fallback_items": fallback_items[:capped_limit],
        "items": result_items,
        "document_query_contract_version": document_query_data["contract_version"],
        "document_query": document_query_data["query"],
        "document_query_results": document_query_data["results"],
        "document_query_pagination": document_query_data["pagination"],
        "document_query_meta": document_query_envelope["meta"],
        "model_evidence_manifest": build_structured_data_model_evidence_manifest(
            project_key=resolved_project_key,
            query=query_text,
            items=result_items,
            limit=max(capped_limit, 12),
        ),
        "dataset_results": dataset_results,
        "errors": errors,
    }


def build_structured_data_model_evidence_manifest(
    *,
    project_key: str | None,
    query: str | None,
    items: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Build stable model-facing read handles for already-stored project records."""

    resolved_project_key = str(project_key or "").strip()
    query_text = _normalize_query(query)
    out: list[dict[str, Any]] = []
    for item in list(items or [])[: max(1, int(limit or 12))]:
        if not isinstance(item, dict):
            continue
        dataset = str(item.get("dataset") or "").strip()
        record_id = str(item.get("record_id") or item.get("id") or "").strip()
        if not dataset or not record_id:
            continue
        source_uri = str(item.get("source_uri") or "").strip() or None
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        quality_flags = fields.get("quality_flags") if isinstance(fields.get("quality_flags"), dict) else {}
        out.append(
            {
                "item_id": f"structured:{dataset}:{record_id}",
                "resource_uri": _structured_resource_uri(resolved_project_key, dataset, record_id),
                "project_key": resolved_project_key,
                "dataset": dataset,
                "record_id": record_id,
                "kind": "structured_record",
                "category": "internal_existing",
                "title": item.get("title") or record_id,
                "why_matched": item.get("match_type") or ("query_match" if query_text else "inventory_sample"),
                "short_snippet": item.get("summary") or "",
                "source_ref": source_uri or fields.get("source_ref") or fields.get("uri") or fields.get("source_uri"),
                "quality_flags": quality_flags,
                "read_tool": "project.structured_data.item.read",
                "read_arguments": {
                    "project_key": resolved_project_key,
                    "dataset": dataset,
                    "record_id": record_id,
                },
                "is_source_catalog_entry": False,
            }
        )
    return out


def read_project_structured_data_item(
    *,
    project_key: str | None,
    dataset: str | None = None,
    record_id: Any | None = None,
    item_id: str | None = None,
    resource_uri: str | None = None,
) -> StructuredSearchResult:
    """Read one already-stored structured record by dataset/id or manifest URI."""

    resolved_project_key = str(project_key or "").strip()
    parsed = _parse_structured_data_read_ref(project_key=resolved_project_key, dataset=dataset, record_id=record_id, item_id=item_id, resource_uri=resource_uri)
    if not resolved_project_key:
        return _structured_item_read_error(project_key=project_key, dataset=parsed["dataset"], record_id=parsed["record_id"], code="missing_project_key", message="project_key is required")
    if not parsed["dataset"] or not parsed["record_id"]:
        return _structured_item_read_error(project_key=resolved_project_key, dataset=parsed["dataset"], record_id=parsed["record_id"], code="missing_record_ref", message="dataset and record_id are required")
    dataset_name = str(parsed["dataset"])
    model = _DATASET_MODELS.get(dataset_name)
    mapper = _DATASET_ITEM_MAPPERS.get(dataset_name)
    if model is None or mapper is None:
        return _structured_item_read_error(project_key=resolved_project_key, dataset=dataset_name, record_id=parsed["record_id"], code="unsupported_dataset", message=f"unsupported structured dataset: {dataset_name}")

    with bind_project(resolved_project_key):
        with SessionLocal() as session:
            row = session.execute(select(model).where(cast(model.id, Text) == str(parsed["record_id"])).limit(1)).scalar_one_or_none()
            if row is None:
                return _structured_item_read_error(project_key=resolved_project_key, dataset=dataset_name, record_id=parsed["record_id"], code="record_not_found", message="structured record was not found")
            if dataset_name == "price_observations":
                product = session.execute(select(Product).where(Product.id == getattr(row, "product_id", None)).limit(1)).scalar_one_or_none()
                item = _price_observation_item(
                    row,
                    product_name=getattr(product, "name", None),
                    product_category=getattr(product, "category", None),
                )
            else:
                item = mapper(row)
    manifest = build_structured_data_model_evidence_manifest(project_key=resolved_project_key, query=None, items=[item], limit=1)
    return {
        "contract_version": "project.structured_data.item.read.v1",
        "project_key": resolved_project_key,
        "dataset": dataset_name,
        "record_id": str(parsed["record_id"]),
        "item": item,
        "model_evidence_manifest": manifest,
        "resource_uri": manifest[0]["resource_uri"] if manifest else _structured_resource_uri(resolved_project_key, dataset_name, str(parsed["record_id"])),
        "cleaned_text": item.get("summary") or "",
        "source_ref": item.get("source_uri") or dict(item.get("fields") or {}).get("source_ref"),
        "quality_flags": dict(dict(item.get("fields") or {}).get("quality_flags") or {}),
        "errors": [],
    }


def read_project_structured_data_items(
    *,
    project_key: str | None,
    items: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    limit: int = 8,
) -> StructuredSearchResult:
    safe_limit = max(1, min(25, int(limit or 8)))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for ref in list(items or [])[:safe_limit]:
        if not isinstance(ref, dict):
            continue
        read_result = read_project_structured_data_item(
            project_key=ref.get("project_key") or project_key,
            dataset=ref.get("dataset"),
            record_id=ref.get("record_id"),
            item_id=ref.get("item_id"),
            resource_uri=ref.get("resource_uri"),
        )
        if read_result.get("item"):
            results.append(read_result)
        errors.extend([item for item in list(read_result.get("errors") or []) if isinstance(item, dict)])
    manifest: list[dict[str, Any]] = []
    for result in results:
        manifest.extend([item for item in list(result.get("model_evidence_manifest") or []) if isinstance(item, dict)])
    return {
        "contract_version": "project.structured_data.items.read.v1",
        "project_key": str(project_key or "").strip(),
        "items": results,
        "model_evidence_manifest": manifest,
        "total_returned": len(results),
        "errors": errors,
    }


def read_project_context_resource(*, project_key: str | None, resource_uri: str | None) -> StructuredSearchResult:
    uri = str(resource_uri or "").strip()
    if uri.startswith("project://structured/"):
        return read_project_structured_data_item(project_key=project_key, resource_uri=uri)
    return {
        "contract_version": "project.context.resource.read.v1",
        "project_key": str(project_key or "").strip(),
        "resource_uri": uri,
        "item": None,
        "errors": [{"type": "unsupported_resource_uri", "message": "Only project://structured/... resources are supported by this read-only tool."}],
    }


def _normalize_query(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    lowered = text.lower()
    if not lowered:
        return ""
    compact = lowered.replace("，", "").replace("？", "").replace("?", "").replace(" ", "")
    if any(phrase.replace(" ", "") in compact for phrase in _GENERIC_DATA_QUESTIONS):
        return ""
    topic = _extract_topic_query(text)
    if topic:
        return topic
    return text


def _extract_topic_query(text: str) -> str:
    compact = str(text or "").strip()
    if not compact:
        return ""
    for pattern in (
        r"已有的(.{1,24}?)相关数据",
        r"已有的(.{1,24}?)数据",
        r"关于(.{1,24}?)(?:的|相关)?(?:数据|资料|内容|线索)",
        r"(.{1,24}?)相关数据",
    ):
        match = re.search(pattern, compact)
        if match:
            candidate = _strip_query_stopwords(match.group(1))
            if candidate:
                return candidate
    if "机器人" in compact:
        return "机器人"
    return ""


def _strip_query_stopwords(value: str) -> str:
    text = str(value or "").strip(" ：:，,。.!?？ \t\n\r")
    for token in ("项目里", "项目", "本地", "已经存储", "已经", "已有", "当前", "的"):
        text = text.replace(token, "")
    return text.strip(" ：:，,。.!?？ \t\n\r")


def _normalize_datasets(value: list[str] | tuple[str, ...] | None) -> list[str]:
    if not value:
        return list(DATASET_ORDER)
    out: list[str] = []
    for item in value:
        key = str(item or "").strip()
        if key and key not in out:
            out.append(key)
    return out or list(DATASET_ORDER)


def _should_include_inventory_fallback(query: str) -> bool:
    lowered = str(query or "").strip().lower()
    if not lowered:
        return False
    exploratory_tokens = (
        "数据",
        "项目",
        "有意思",
        "找些",
        "找一些",
        "看看",
        "分析",
        "扩展",
        "关键词",
        "data",
        "interesting",
        "insight",
        "overview",
        "keyword",
    )
    return any(token in lowered for token in exploratory_tokens)


def _query_model(
    session: Any,
    model: Any,
    *,
    dataset: str,
    query: str,
    limit: int,
    mapper: Callable[[Any], dict[str, Any]],
    search_columns: tuple[Any, ...] = (),
    order_columns: tuple[Any, ...] = (),
) -> tuple[list[dict[str, Any]], int | None]:
    # Inventory questions need table sizes; targeted search turns need samples first.
    # Avoid a count(*) per dataset on normal search, which dominates tail latency
    # once the project accumulates larger structured tables.
    total_rows = None if query else int(session.execute(select(func.count()).select_from(model)).scalar() or 0)
    stmt = select(model)
    if query:
        stmt = stmt.where(_search_condition(query, search_columns))
    for column in order_columns:
        stmt = stmt.order_by(column.desc())
    fetch_limit = max(1, limit)
    if query:
        fetch_limit = max(fetch_limit, min(100, fetch_limit * 4))
    rows = session.execute(stmt.limit(fetch_limit)).scalars().all()
    items = [mapper(row) for row in rows]
    for item in items:
        item.setdefault("dataset", dataset)
    if query:
        items = _rank_visible_query_matches(items, query)[: max(1, limit)]
    return items, total_rows


def _search_condition(query: str, columns: tuple[Any, ...]) -> Any:
    if not columns:
        return True
    pattern = f"%{query}%"
    return or_(*[cast(column, Text).ilike(pattern) for column in columns])


def _rank_visible_query_matches(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        score = _visible_query_score(item, query)
        if score > 0:
            scored.append((score, -index, item))
    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    return [item for _score, _index, item in scored]


def _visible_query_score(item: dict[str, Any], query: str) -> int:
    query_terms = _query_terms(query)
    if not query_terms:
        return 0
    score = 0
    title = _searchable_text(item.get("title"))
    summary = _searchable_text(item.get("summary"))
    fields = _searchable_text(item.get("fields"))
    for term in query_terms:
        if term in title:
            score += 6
        if term in summary:
            score += 4
        if term in fields:
            score += 2
    return score


def _query_terms(query: str) -> list[str]:
    text = str(query or "").strip().lower()
    if not text:
        return []
    if re.search(r"[\u4e00-\u9fff]", text):
        return [text]
    return [part for part in re.split(r"[^a-z0-9]+", text) if len(part) >= 3]


def _searchable_text(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str).lower()
    return str(value or "").lower()


def _query_documents(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        Document,
        dataset="documents",
        query=query,
        limit=limit,
        mapper=_document_item,
        search_columns=(
            Document.title,
            Document.summary,
            Document.content,
            Document.uri,
            Document.doc_type,
            Document.status,
            Document.state,
            Document.extracted_data,
        ),
        order_columns=(Document.updated_at, Document.created_at),
    )


def _query_sources(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        Source,
        dataset="sources",
        query=query,
        limit=limit,
        mapper=_source_item,
        search_columns=(Source.name, Source.kind, Source.base_url),
        order_columns=(Source.updated_at, Source.created_at),
    )


def _query_market_stats(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        MarketStat,
        dataset="market_stats",
        query=query,
        limit=limit,
        mapper=_market_stat_item,
        search_columns=(MarketStat.state, MarketStat.game, MarketStat.source_name, MarketStat.source_uri, MarketStat.extra),
        order_columns=(MarketStat.date, MarketStat.created_at),
    )


def _query_metric_points(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        MarketMetricPoint,
        dataset="metric_points",
        query=query,
        limit=limit,
        mapper=_metric_point_item,
        search_columns=(
            MarketMetricPoint.metric_key,
            MarketMetricPoint.unit,
            MarketMetricPoint.currency,
            MarketMetricPoint.source_name,
            MarketMetricPoint.source_uri,
            MarketMetricPoint.extra,
        ),
        order_columns=(MarketMetricPoint.date, MarketMetricPoint.created_at),
    )


def _query_products(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        Product,
        dataset="products",
        query=query,
        limit=limit,
        mapper=_product_item,
        search_columns=(
            Product.name,
            Product.category,
            Product.source_name,
            Product.source_uri,
            Product.selector_hint,
            Product.currency,
            Product.extra,
        ),
        order_columns=(Product.updated_at, Product.created_at),
    )


def _query_price_observations(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    stmt = select(PriceObservation, Product.name, Product.category).join(Product, Product.id == PriceObservation.product_id)
    if query:
        stmt = stmt.where(
            or_(
                cast(Product.name, Text).ilike(f"%{query}%"),
                cast(Product.category, Text).ilike(f"%{query}%"),
                cast(PriceObservation.source_uri, Text).ilike(f"%{query}%"),
                cast(PriceObservation.availability, Text).ilike(f"%{query}%"),
                cast(PriceObservation.extra, Text).ilike(f"%{query}%"),
            )
        )
    stmt = stmt.order_by(PriceObservation.captured_at.desc(), PriceObservation.created_at.desc())
    rows = session.execute(stmt.limit(max(1, limit))).all()
    total_rows = None
    if not query:
        total_rows = int(session.execute(select(func.count()).select_from(PriceObservation)).scalar() or 0)
    return [_price_observation_item(row[0], product_name=row[1], product_category=row[2]) for row in rows], total_rows


def _query_resource_pool_urls(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        ResourcePoolUrl,
        dataset="resource_pool_urls",
        query=query,
        limit=limit,
        mapper=_resource_pool_url_item,
        search_columns=(ResourcePoolUrl.url, ResourcePoolUrl.domain, ResourcePoolUrl.source, ResourcePoolUrl.source_ref),
        order_columns=(ResourcePoolUrl.created_at,),
    )


def _query_resource_pool_sites(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        ResourcePoolSiteEntry,
        dataset="resource_pool_sites",
        query=query,
        limit=limit,
        mapper=_resource_pool_site_item,
        search_columns=(
            ResourcePoolSiteEntry.site_url,
            ResourcePoolSiteEntry.domain,
            ResourcePoolSiteEntry.entry_type,
            ResourcePoolSiteEntry.template,
            ResourcePoolSiteEntry.name,
            ResourcePoolSiteEntry.capabilities,
            ResourcePoolSiteEntry.source,
            ResourcePoolSiteEntry.source_ref,
            ResourcePoolSiteEntry.tags,
            ResourcePoolSiteEntry.extra,
        ),
        order_columns=(ResourcePoolSiteEntry.updated_at, ResourcePoolSiteEntry.created_at),
    )


def _query_graph_nodes(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        GraphNodeRecord,
        dataset="graph_nodes",
        query=query,
        limit=limit,
        mapper=_graph_node_item,
        search_columns=(
            GraphNodeRecord.node_type,
            GraphNodeRecord.canonical_id,
            GraphNodeRecord.display_name,
            GraphNodeRecord.properties,
            GraphNodeRecord.quality_flags,
        ),
        order_columns=(GraphNodeRecord.updated_at, GraphNodeRecord.created_at),
    )


def _query_keyword_history(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        KeywordHistory,
        dataset="keyword_history",
        query=query,
        limit=limit,
        mapper=_keyword_history_item,
        search_columns=(
            KeywordHistory.keyword,
            KeywordHistory.normalized_keyword,
            KeywordHistory.last_status,
            KeywordHistory.last_source,
            KeywordHistory.last_source_domain,
            KeywordHistory.extra,
        ),
        order_columns=(KeywordHistory.last_seen_at, KeywordHistory.first_seen_at),
    )


def _query_keyword_priors(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        KeywordPrior,
        dataset="keyword_priors",
        query=query,
        limit=limit,
        mapper=_keyword_prior_item,
        search_columns=(KeywordPrior.keyword, KeywordPrior.normalized_keyword, KeywordPrior.source, KeywordPrior.notes, KeywordPrior.tags, KeywordPrior.extra),
        order_columns=(KeywordPrior.updated_at, KeywordPrior.created_at),
    )


def _query_search_history(session: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], int | None]:
    return _query_model(
        session,
        SearchHistory,
        dataset="search_history",
        query=query,
        limit=limit,
        mapper=_search_history_item,
        search_columns=(SearchHistory.topic,),
        order_columns=(SearchHistory.last_search_time,),
    )


def _document_item(row: Document) -> dict[str, Any]:
    return _record(
        "documents",
        row.id,
        row.title or row.uri or f"document:{row.id}",
        row.summary or row.content,
        {
            "doc_type": row.doc_type,
            "status": row.status,
            "state": row.state,
            "publish_date": _serialize_value(row.publish_date),
            "uri": row.uri,
            "extracted_data": _compact_json_value(row.extracted_data, max_items=10, max_depth=3),
            "created_at": _serialize_value(row.created_at),
            "updated_at": _serialize_value(row.updated_at),
        },
        source_uri=row.uri,
        date_value=row.publish_date,
    )


def _source_item(row: Source) -> dict[str, Any]:
    return _record(
        "sources",
        row.id,
        row.name,
        row.kind,
        {
            "kind": row.kind,
            "base_url": row.base_url,
            "enabled": row.enabled,
            "created_at": _serialize_value(row.created_at),
            "updated_at": _serialize_value(row.updated_at),
        },
        source_uri=row.base_url,
    )


def _market_stat_item(row: MarketStat) -> dict[str, Any]:
    summary = f"{row.state or '-'} {row.game or ''} {row.date}: sales={row.sales_volume}, revenue={row.revenue}"
    return _record(
        "market_stats",
        row.id,
        f"{row.state or '-'} {row.game or 'market'} {row.date}",
        summary,
        {
            "state": row.state,
            "game": row.game,
            "date": _serialize_value(row.date),
            "sales_volume": _serialize_value(row.sales_volume),
            "revenue": _serialize_value(row.revenue),
            "revenue_estimated": _serialize_value(row.revenue_estimated),
            "jackpot": _serialize_value(row.jackpot),
            "ticket_price": _serialize_value(row.ticket_price),
            "draw_number": row.draw_number,
            "yoy": _serialize_value(row.yoy),
            "mom": _serialize_value(row.mom),
            "source_name": row.source_name,
            "source_uri": row.source_uri,
            "extra": _compact_json_value(row.extra, max_items=8, max_depth=3),
        },
        source_uri=row.source_uri,
        date_value=row.date,
    )


def _metric_point_item(row: MarketMetricPoint) -> dict[str, Any]:
    return _record(
        "metric_points",
        row.id,
        f"{row.metric_key} {row.date}",
        f"{row.metric_key}: {row.value} {row.unit or ''} {row.currency or ''}",
        {
            "metric_key": row.metric_key,
            "date": _serialize_value(row.date),
            "value": _serialize_value(row.value),
            "unit": row.unit,
            "currency": row.currency,
            "source_name": row.source_name,
            "source_uri": row.source_uri,
            "extra": _compact_json_value(row.extra, max_items=8, max_depth=3),
        },
        source_uri=row.source_uri,
        date_value=row.date,
    )


def _product_item(row: Product) -> dict[str, Any]:
    return _record(
        "products",
        row.id,
        row.name,
        row.category or row.source_name or "",
        {
            "name": row.name,
            "category": row.category,
            "source_name": row.source_name,
            "source_uri": row.source_uri,
            "selector_hint": row.selector_hint,
            "currency": row.currency,
            "enabled": row.enabled,
            "extra": _compact_json_value(row.extra, max_items=8, max_depth=3),
            "created_at": _serialize_value(row.created_at),
            "updated_at": _serialize_value(row.updated_at),
        },
        source_uri=row.source_uri,
    )


def _price_observation_item(row: PriceObservation, *, product_name: str | None, product_category: str | None) -> dict[str, Any]:
    return _record(
        "price_observations",
        row.id,
        product_name or f"product:{row.product_id}",
        f"{row.price} {row.currency or ''} at {row.captured_at}",
        {
            "product_id": row.product_id,
            "product_name": product_name,
            "product_category": product_category,
            "captured_at": _serialize_value(row.captured_at),
            "price": _serialize_value(row.price),
            "currency": row.currency,
            "availability": row.availability,
            "source_uri": row.source_uri,
            "extra": _compact_json_value(row.extra, max_items=8, max_depth=3),
        },
        source_uri=row.source_uri,
        date_value=row.captured_at,
    )


def _resource_pool_url_item(row: ResourcePoolUrl) -> dict[str, Any]:
    return _record(
        "resource_pool_urls",
        row.id,
        row.domain or row.url,
        row.url,
        {
            "url": row.url,
            "domain": row.domain,
            "source": row.source,
            "source_ref": _compact_json_value(row.source_ref, max_items=8, max_depth=3),
            "project_key": row.project_key,
            "created_at": _serialize_value(row.created_at),
        },
        source_uri=row.url,
    )


def _resource_pool_site_item(row: ResourcePoolSiteEntry) -> dict[str, Any]:
    return _record(
        "resource_pool_sites",
        row.id,
        row.name or row.domain or row.site_url,
        row.template or row.entry_type,
        {
            "site_url": row.site_url,
            "domain": row.domain,
            "entry_type": row.entry_type,
            "template": row.template,
            "capabilities": _compact_json_value(row.capabilities, max_items=8, max_depth=3),
            "tags": _compact_json_value(row.tags, max_items=8, max_depth=3),
            "enabled": row.enabled,
            "project_key": row.project_key,
            "source": row.source,
            "source_ref": _compact_json_value(row.source_ref, max_items=8, max_depth=3),
            "extra": _compact_json_value(row.extra, max_items=8, max_depth=3),
        },
        source_uri=row.site_url,
    )


def _graph_node_item(row: GraphNodeRecord) -> dict[str, Any]:
    return _record(
        "graph_nodes",
        row.id,
        row.display_name or row.canonical_id,
        row.node_type,
        {
            "node_type": row.node_type,
            "canonical_id": row.canonical_id,
            "display_name": row.display_name,
            "properties": _compact_json_value(row.properties, max_items=10, max_depth=3),
            "source_doc_id": row.source_doc_id,
            "schema_version": row.node_schema_version,
            "quality_flags": _compact_json_value(row.quality_flags, max_items=8, max_depth=3),
            "created_at": _serialize_value(row.created_at),
            "updated_at": _serialize_value(row.updated_at),
        },
    )


def _keyword_history_item(row: KeywordHistory) -> dict[str, Any]:
    return _record(
        "keyword_history",
        row.id,
        row.keyword,
        f"searches={row.search_count}, hits={row.hit_count}, inserted={row.inserted_count}, status={row.last_status}",
        {
            "keyword": row.keyword,
            "normalized_keyword": row.normalized_keyword,
            "search_count": row.search_count,
            "hit_count": row.hit_count,
            "inserted_count": row.inserted_count,
            "rejected_count": row.rejected_count,
            "last_status": row.last_status,
            "last_source": row.last_source,
            "last_source_domain": row.last_source_domain,
            "last_filter_decision": row.last_filter_decision,
            "extra": _compact_json_value(row.extra, max_items=8, max_depth=3),
        },
    )


def _keyword_prior_item(row: KeywordPrior) -> dict[str, Any]:
    return _record(
        "keyword_priors",
        row.id,
        row.keyword,
        row.notes or f"prior={row.prior_score}, confidence={row.confidence}",
        {
            "keyword": row.keyword,
            "normalized_keyword": row.normalized_keyword,
            "prior_score": _serialize_value(row.prior_score),
            "confidence": _serialize_value(row.confidence),
            "source": row.source,
            "enabled": row.enabled,
            "tags": _compact_json_value(row.tags, max_items=8, max_depth=3),
            "notes": row.notes,
            "extra": _compact_json_value(row.extra, max_items=8, max_depth=3),
        },
    )


def _search_history_item(row: SearchHistory) -> dict[str, Any]:
    return _record(
        "search_history",
        row.id,
        row.topic,
        f"last searched at {row.last_search_time}",
        {
            "topic": row.topic,
            "last_search_time": _serialize_value(row.last_search_time),
        },
        date_value=row.last_search_time,
    )


def _record(
    dataset: str,
    record_id: Any,
    title: Any,
    summary: Any,
    fields: dict[str, Any],
    *,
    source_uri: str | None = None,
    date_value: Any | None = None,
) -> dict[str, Any]:
    fields = dict(fields or {})
    summary_text, summary_flags = _clean_display_summary(summary, limit=420)
    if summary_flags:
        quality_flags = dict(fields.get("quality_flags") or {})
        quality_flags.update(summary_flags)
        fields["quality_flags"] = quality_flags
    return {
        "dataset": dataset,
        "record_id": _serialize_value(record_id),
        "title": _trim_text(title, 180),
        "summary": summary_text,
        "source_uri": source_uri,
        "date": _serialize_value(date_value),
        "fields": _compact_json_value(fields, max_items=18, max_depth=4),
    }


def _structured_resource_uri(project_key: str | None, dataset: str, record_id: str) -> str:
    return f"project://structured/{str(project_key or '').strip()}/{dataset}/{record_id}"


def _parse_structured_data_read_ref(
    *,
    project_key: str,
    dataset: str | None,
    record_id: Any | None,
    item_id: str | None,
    resource_uri: str | None,
) -> dict[str, str]:
    dataset_text = str(dataset or "").strip()
    record_text = str(record_id or "").strip()
    item_text = str(item_id or "").strip()
    uri_text = str(resource_uri or "").strip()
    if uri_text.startswith("project://structured/"):
        parts = uri_text.removeprefix("project://structured/").split("/", 2)
        if len(parts) == 3:
            if not project_key:
                project_key = parts[0]
            dataset_text = dataset_text or parts[1]
            record_text = record_text or parts[2]
    if item_text.startswith("structured:"):
        parts = item_text.split(":", 2)
        if len(parts) == 3:
            dataset_text = dataset_text or parts[1]
            record_text = record_text or parts[2]
    return {"project_key": project_key, "dataset": dataset_text, "record_id": record_text}


def _structured_item_read_error(
    *,
    project_key: str | None,
    dataset: str | None,
    record_id: Any | None,
    code: str,
    message: str,
) -> StructuredSearchResult:
    return {
        "contract_version": "project.structured_data.item.read.v1",
        "project_key": str(project_key or "").strip(),
        "dataset": str(dataset or "").strip(),
        "record_id": str(record_id or "").strip(),
        "item": None,
        "model_evidence_manifest": [],
        "errors": [{"type": code, "message": message}],
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _trim_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


_WEB_NOISE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bif\s*\(\s*typeof\b", re.IGNORECASE),
    re.compile(r"\bfunction\s*\(", re.IGNORECASE),
    re.compile(r"\b(window|document|googletag|adinstance|dataLayer)\s*[\.\[]", re.IGNORECASE),
    re.compile(r"<\s*/?\s*(script|style|iframe|noscript|html|body)\b", re.IGNORECASE),
    re.compile(r"\bvar\s+[A-Za-z_$][\w$]*\s*=", re.IGNORECASE),
    re.compile(r"\.[A-Za-z][\w-]*\s*\{"),
    re.compile(r"\b(grid-template|font-size|line-height|@media|display\s*:|margin\s*:|padding\s*:)", re.IGNORECASE),
)


def _clean_display_summary(value: Any, *, limit: int) -> tuple[str, dict[str, Any]]:
    text = " ".join(str(value or "").split())
    if not text:
        return "", {}
    noise_hits = sum(1 for pattern in _WEB_NOISE_PATTERNS if pattern.search(text))
    punctuation_ratio = _punctuation_ratio(text)
    if noise_hits >= 1 or (len(text) > 180 and punctuation_ratio > 0.24):
        return "", {
            "display_summary_omitted": True,
            "display_summary_omit_reason": "web_script_or_navigation_noise",
        }
    return _trim_text(text, limit), {}


def _punctuation_ratio(text: str) -> float:
    if not text:
        return 0.0
    punctuation_count = sum(1 for char in text if char in "{}[]();=<>|")
    return punctuation_count / max(1, len(text))


def _compact_json_value(value: Any, *, max_items: int, max_depth: int, max_string: int = 500) -> Any:
    if max_depth <= 0:
        if isinstance(value, (dict, list, tuple)):
            return "[truncated]"
        return _serialize_value(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                out["_truncated"] = True
                out["_omitted_count"] = max(0, len(value) - max_items)
                break
            out[str(key)] = _compact_json_value(item, max_items=max_items, max_depth=max_depth - 1, max_string=max_string)
        return out
    if isinstance(value, (list, tuple)):
        items = list(value)
        out = [
            _compact_json_value(item, max_items=max_items, max_depth=max_depth - 1, max_string=max_string)
            for item in items[:max_items]
        ]
        if len(items) > max_items:
            out.append({"_truncated": True, "_omitted_count": len(items) - max_items})
        return out
    value = _serialize_value(value)
    if isinstance(value, str) and len(value) > max_string:
        return f"{value[:max_string]}..."
    return value


_DATASET_HANDLERS: dict[str, DatasetHandler] = {
    "documents": _query_documents,
    "graph_nodes": _query_graph_nodes,
    "market_stats": _query_market_stats,
    "metric_points": _query_metric_points,
    "products": _query_products,
    "price_observations": _query_price_observations,
    "resource_pool_urls": _query_resource_pool_urls,
    "resource_pool_sites": _query_resource_pool_sites,
    "keyword_history": _query_keyword_history,
    "keyword_priors": _query_keyword_priors,
    "search_history": _query_search_history,
    "sources": _query_sources,
}

_DATASET_MODELS: dict[str, Any] = {
    "documents": Document,
    "graph_nodes": GraphNodeRecord,
    "market_stats": MarketStat,
    "metric_points": MarketMetricPoint,
    "products": Product,
    "price_observations": PriceObservation,
    "resource_pool_urls": ResourcePoolUrl,
    "resource_pool_sites": ResourcePoolSiteEntry,
    "keyword_history": KeywordHistory,
    "keyword_priors": KeywordPrior,
    "search_history": SearchHistory,
    "sources": Source,
}

_DATASET_ITEM_MAPPERS: dict[str, DatasetItemMapper] = {
    "documents": _document_item,
    "graph_nodes": _graph_node_item,
    "market_stats": _market_stat_item,
    "metric_points": _metric_point_item,
    "products": _product_item,
    "price_observations": lambda row: _price_observation_item(row, product_name=None, product_category=None),
    "resource_pool_urls": _resource_pool_url_item,
    "resource_pool_sites": _resource_pool_site_item,
    "keyword_history": _keyword_history_item,
    "keyword_priors": _keyword_prior_item,
    "search_history": _search_history_item,
    "sources": _source_item,
}
