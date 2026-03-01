"""数据库管理API"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Literal
from sqlalchemy import select, func, or_, and_, nullslast, nullsfirst
from sqlalchemy.orm import selectinload
from datetime import datetime, date
import hashlib
import re
import logging

from ..models.base import SessionLocal
from ..models.entities import Document, Source, MarketStat, SearchHistory
from ..services.graph.doc_types import resolve_graph_doc_types, resolve_graph_topic_scope_entities
from ..services.extraction.extract import extract_policy_info, extract_market_info, extract_entities_relations
from ..services.extraction.application import ExtractionApplicationService
from ..services.extraction.topic_workflow import (
    TOPIC_FIELDS as WORKFLOW_TOPIC_FIELDS,
    empty_topic_structured as wf_empty_topic_structured,
    merge_topic_structured as wf_merge_topic_structured,
    run_topic_extraction_workflow,
    topic_has_data as wf_topic_has_data,
)
from ..services.projects import bind_project
from ..contracts import success_response
from ..services.ingest.adapters.http_utils import fetch_html
from ..services.ingest.url_pool import _extract_text_from_html
from ..project_customization import get_project_customization


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _project_key_from_request(request: Request) -> str:
    """Extract project_key from request (sync routes run in thread pool, context not inherited)."""
    from ..settings.config import settings
    pk = request.headers.get("X-Project-Key") or request.query_params.get("project_key")
    if pk:
        return pk.strip()
    try:
        from ..models.base import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text('SET search_path TO "public"'))
            row = conn.execute(
                text("SELECT project_key FROM public.projects WHERE is_active = true LIMIT 1")
            ).fetchone()
            if row:
                return str(row[0])
    except Exception:
        pass
    return settings.active_project_key or "default"


class DocumentListRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    state: Optional[str] = None
    doc_type: Optional[str] = None
    has_extracted_data: Optional[bool] = None
    search: Optional[str] = None
    sort_by: Optional[str] = Field(default="created_at", description="排序字段: created_at, publish_date, id")
    sort_order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$", description="排序方向: asc, desc")


class SourceListRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    kind: Optional[str] = None
    enabled: Optional[bool] = None
    sort_by: Optional[str] = Field(default="created_at", description="排序字段: created_at, id, name, document_count")
    sort_order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$", description="排序方向: asc, desc")


class MarketStatsListRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    state: Optional[str] = None
    game: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    sort_by: Optional[str] = Field(default="date", description="排序字段: date, id, sales_volume, revenue, jackpot")
    sort_order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$", description="排序方向: asc, desc")


class SocialDataListRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    platform: Optional[str] = None
    search: Optional[str] = None
    sentiment_orientation: Optional[str] = Field(None, pattern="^(positive|negative|neutral)$", description="情感倾向: positive, negative, neutral")
    sort_by: Optional[str] = Field(default="created_at", description="排序字段: created_at, publish_date, id")
    sort_order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$", description="排序方向: asc, desc")


class DeleteDocumentsRequest(BaseModel):
    ids: List[int]


def _deep_merge_json(base: Any, incoming: Any) -> Any:
    if isinstance(base, dict) and isinstance(incoming, dict):
        out: dict[str, Any] = dict(base)
        for k, v in incoming.items():
            if k in out:
                out[k] = _deep_merge_json(out[k], v)
            else:
                out[k] = v
        return out
    return incoming


class ReExtractRequest(BaseModel):
    doc_ids: Optional[List[int]] = None  # 如果为空，则提取所有政策文档
    force: bool = Field(default=False, description="是否强制重新提取已有数据的文档")
    fetch_missing_content: bool = Field(default=False, description="content为空时，尝试抓取正文后再提取")
    batch_size: int = Field(default=20, ge=1, le=200, description="分批提交大小（降低长事务）")
    limit: Optional[int] = Field(default=None, ge=1, le=5000, description="最多处理文档数")
    treat_empty_er_as_missing: bool = Field(default=True, description="entities_relations存在但实体/关系为空时仍视为缺失")


class TopicExtractRequest(BaseModel):
    topics: List[Literal["company", "product", "operation"]] = Field(default_factory=lambda: ["company", "product", "operation"], min_length=1)
    doc_ids: Optional[List[int]] = None
    doc_types: Optional[List[str]] = None
    force: bool = Field(default=False)
    fetch_missing_content: bool = Field(default=False)
    batch_size: int = Field(default=10, ge=1, le=100)
    limit: Optional[int] = Field(default=200, ge=1, le=5000)
    candidate_mode: Literal["rules_then_llm"] = "rules_then_llm"


class RawImportItem(BaseModel):
    title: Optional[str] = None
    uri: Optional[str] = None
    uris: Optional[List[str]] = None
    text: str = Field(..., min_length=1, description="粘贴文本/文件文本内容")
    summary: Optional[str] = None
    doc_type: Optional[str] = None
    publish_date: Optional[str] = None
    state: Optional[str] = None


class RawImportRequest(BaseModel):
    items: List[RawImportItem] = Field(default_factory=list, min_length=1, max_length=200)
    source_name: str = Field(default="raw_import", min_length=1, max_length=255)
    source_kind: str = Field(default="manual")
    infer_from_links: bool = Field(default=True, description="从文本中识别首个 URL 作为 uri")
    enable_extraction: bool = Field(default=True, description="是否直接进入结构化提取流程")
    default_doc_type: Literal["market_info", "policy", "social_sentiment", "news", "raw_note"] = "raw_note"
    extraction_mode: Literal["auto", "market", "policy", "social"] = "auto"
    overwrite_on_uri: bool = Field(default=False, description="相同 URI 是否覆盖已存在文档内容")
    chunk_size: int = Field(default=2800, ge=500, le=8000, description="大文本分片长度（字符）")
    chunk_overlap: int = Field(default=200, ge=0, le=1000, description="分片重叠长度（字符）")
    max_chunks: int = Field(default=8, ge=1, le=50, description="单条文本最多分片数")


_URL_RE = re.compile(r"https?://[^\s<>()\"']+")


def _first_url_in_text(text: str) -> str | None:
    m = _URL_RE.search(text or "")
    return m.group(0).rstrip(".,;)]") if m else None


def _all_urls_in_text(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _URL_RE.finditer(text or ""):
        u = m.group(0).rstrip(".,;)]")
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _normalize_uri_list(item: RawImportItem, infer_from_text: bool) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    candidates: list[str] = []
    if item.uri:
        candidates.append(str(item.uri))
    if item.uris:
        candidates.extend([str(x) for x in item.uris if x])
    if infer_from_text:
        candidates.extend(_all_urls_in_text(str(item.text or "")))
    for raw in candidates:
        u = raw.strip()
        if not u or u in seen:
            continue
        seen.add(u)
        urls.append(u)
    return urls


def _chunk_text_for_extraction(text: str, chunk_size: int, overlap: int, max_chunks: int) -> list[str]:
    s = str(text or "").strip()
    if not s:
        return []
    if len(s) <= chunk_size:
        return [s]
    step = max(1, chunk_size - overlap)
    chunks: list[str] = []
    i = 0
    while i < len(s) and len(chunks) < max_chunks:
        part = s[i:i + chunk_size].strip()
        if part:
            chunks.append(part)
        i += step
    return chunks or [s[:chunk_size]]


def _merge_extracted_batch(parts: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    all_entities: list[dict[str, Any]] = []
    all_relations: list[dict[str, Any]] = []

    def _entity_key(e: Any) -> str:
        if not isinstance(e, dict):
            return str(e)
        return f"{str(e.get('text') or '').strip().lower()}::{str(e.get('type') or '').strip().lower()}"

    def _rel_key(r: Any) -> str:
        if not isinstance(r, dict):
            return str(r)
        return "::".join([
            str(r.get("subject") or "").strip().lower(),
            str(r.get("predicate") or "").strip().lower(),
            str(r.get("object") or "").strip().lower(),
        ])

    seen_entities: set[str] = set()
    seen_relations: set[str] = set()
    for p in parts:
        if not isinstance(p, dict):
            continue
        merged = _deep_merge_json(merged, p)
        er = p.get("entities_relations")
        if isinstance(er, dict):
            for e in (er.get("entities") or []):
                k = _entity_key(e)
                if k and k not in seen_entities:
                    seen_entities.add(k)
                    all_entities.append(e)
            for r in (er.get("relations") or []):
                k = _rel_key(r)
                if k and k not in seen_relations:
                    seen_relations.add(k)
                    all_relations.append(r)
        for e in (p.get("entities") or []):
            k = _entity_key(e)
            if k and k not in seen_entities:
                seen_entities.add(k)
                all_entities.append(e)
    if all_entities or all_relations:
        merged["entities_relations"] = {
            "entities": all_entities[:50],
            "relations": all_relations[:50],
        }
        if "entities" in merged and isinstance(merged.get("entities"), list):
            merged["entities"] = all_entities[:50]
    return merged


def _normalize_doc_type_for_raw(dt: str | None, default_doc_type: str) -> str:
    key = (dt or "").strip().lower()
    allowed = {"market", "market_info", "policy", "policy_regulation", "social_sentiment", "social_feed", "news", "raw_note"}
    if key in allowed:
        return key
    return default_doc_type


def _topic_structured_empty() -> dict[str, Any]:
    return {
        "entities": [],
        "relations": [],
        "facts": [],
        "topics": [],
        "signals": {},
        "confidence": 0.0,
        "source_excerpt": "",
        "_status": "no_topic_signal",
    }


def _topic_has_data(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("entities") or payload.get("relations") or payload.get("facts") or payload.get("topics") or payload.get("signals"))


def _normalize_topic_merge(existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    base = existing if isinstance(existing, dict) else {}
    nxt = incoming if isinstance(incoming, dict) else {}

    def _dedupe(items: list[Any], key_fn):
        seen = set()
        out = []
        for item in items:
            try:
                k = key_fn(item)
            except Exception:
                k = str(item)
            if k in seen:
                continue
            seen.add(k)
            out.append(item)
        return out

    entities = _dedupe(
        list(base.get("entities") or []) + list(nxt.get("entities") or []),
        lambda e: f"{str((e or {}).get('text') or '').strip().lower()}::{str((e or {}).get('type') or '').strip().lower()}",
    )
    relations = _dedupe(
        list(base.get("relations") or []) + list(nxt.get("relations") or []),
        lambda r: "::".join([
            str((r or {}).get("subject") or "").strip().lower(),
            str((r or {}).get("predicate") or "").strip().lower(),
            str((r or {}).get("object") or "").strip().lower(),
        ]),
    )
    facts = _dedupe(
        list(base.get("facts") or []) + list(nxt.get("facts") or []),
        lambda f: f"{str((f or {}).get('fact_type') or '').strip().lower()}::{str(sorted((f or {}).items()))}",
    )
    topics = _dedupe(
        [str(x).strip() for x in (list(base.get("topics") or []) + list(nxt.get("topics") or [])) if str(x).strip()],
        lambda x: x.lower(),
    )
    signals = dict(base.get("signals") or {})
    signals.update(nxt.get("signals") or {})
    try:
        confidence = max(float(base.get("confidence") or 0.0), float(nxt.get("confidence") or 0.0))
    except Exception:
        confidence = 0.0
    source_excerpt = str(nxt.get("source_excerpt") or base.get("source_excerpt") or "")[:800]
    out = {
        "entities": entities[:80],
        "relations": relations[:80],
        "facts": facts[:80],
        "topics": topics[:50],
        "signals": signals,
        "confidence": confidence,
        "source_excerpt": source_excerpt,
    }
    if not _topic_has_data(out):
        out["_status"] = str(nxt.get("_status") or base.get("_status") or "no_topic_signal")
    return out


def _get_topic_dictionaries(project_key: str) -> dict[str, Any]:
    """主干只内置谓词/修饰词；项目可通过 field_mapping.topic_dictionaries 提供名词/成分词典。"""
    customization = get_project_customization(project_key)
    fm = customization.get_field_mapping() or {}
    td = fm.get("topic_dictionaries") if isinstance(fm, dict) else None
    td = td if isinstance(td, dict) else {}
    return {
        "predicates": td.get("predicates") if isinstance(td.get("predicates"), list) else [
            "合作", "并购", "收购", "供应", "分销", "依赖", "运营", "销售", "上架", "投放", "促销", "定价",
            "发布", "推出", "适配", "接入", "升级", "降本", "增长", "转化", "gmv"
        ],
        "modifiers": td.get("modifiers") if isinstance(td.get("modifiers"), list) else [
            "公司", "企业", "品牌", "平台", "店铺", "商家", "型号", "产品", "品类", "渠道", "策略", "指标",
            "model", "product", "brand", "platform", "store", "sku", "category", "component", "pricing"
        ],
        "company_nouns": td.get("company_nouns") if isinstance(td.get("company_nouns"), list) else [],
        "product_nouns": td.get("product_nouns") if isinstance(td.get("product_nouns"), list) else [],
        "operation_nouns": td.get("operation_nouns") if isinstance(td.get("operation_nouns"), list) else [],
        "components": td.get("components") if isinstance(td.get("components"), list) else [
            "电机", "减速器", "传感器", "控制器", "末端执行器", "芯片", "battery", "motor", "sensor", "controller", "actuator"
        ],
    }


def _topic_rule_score(topic: str, text: str, extracted_data: dict[str, Any] | None, er: dict[str, Any] | None, dicts: dict[str, Any]) -> int:
    s = str(text or "").lower()
    score = 0
    predicates = [str(x).lower() for x in (dicts.get("predicates") or [])]
    modifiers = [str(x).lower() for x in (dicts.get("modifiers") or [])]
    if any(t and t in s for t in predicates):
        score += 1
    if any(t and t in s for t in modifiers):
        score += 1
    topic_nouns = [str(x).lower() for x in (dicts.get(f"{topic}_nouns") or [])]
    if any(t and t in s for t in topic_nouns):
        score += 2
    if topic == "product" and any(t and t in s for t in [str(x).lower() for x in (dicts.get("components") or [])]):
        score += 1
    ex = extracted_data if isinstance(extracted_data, dict) else {}
    if topic == "operation":
        if isinstance(ex.get("market"), dict) or isinstance(ex.get("sentiment"), dict):
            score += 1
    if topic == "company":
        ents = (er or {}).get("entities") if isinstance(er, dict) else []
        if any(str((e or {}).get("type") or "").upper() == "ORG" for e in (ents or [])):
            score += 2
    if topic == "product":
        kw = [str(x).lower() for x in (ex.get("keywords") or [])] if isinstance(ex.get("keywords"), list) else []
        if any(any(n in k for n in topic_nouns[:50]) for k in kw) if topic_nouns else False:
            score += 1
        market = ex.get("market") if isinstance(ex.get("market"), dict) else {}
        if any(str(market.get(k) or "").strip() for k in ("product", "segment", "category", "game")):
            score += 2
        if any(tok in s for tok in ["robot", "机器人", "sku", "型号", "产品", "component", "传感器", "电机"]):
            score += 1
    if topic == "operation":
        market = ex.get("market") if isinstance(ex.get("market"), dict) else {}
        if any(str(market.get(k) or "").strip() for k in ("platform", "channel", "price", "revenue")):
            score += 1
    return score


def _augment_market_graph_with_topic_structured(graph, documents: list[Document]) -> None:
    from app.services.graph.models import GraphNode, GraphEdge

    def _topic_entity_node_type(topic_field: str, entity_type: str) -> str:
        et = str(entity_type or "").strip().lower()
        if topic_field == "company_structured":
            mapping = {
                "company": "CompanyEntity",
                "brand": "CompanyBrand",
                "business_unit": "CompanyUnit",
                "partner": "CompanyPartner",
                "channel": "CompanyChannel",
            }
            return mapping.get(et, "CompanyEntity")
        if topic_field == "product_structured":
            mapping = {
                "product": "ProductEntity",
                "model": "ProductModel",
                "category": "ProductCategory",
                "brand": "ProductBrand",
                "component": "ProductComponent",
                "scenario": "ProductScenario",
            }
            return mapping.get(et, "ProductEntity")
        if topic_field == "operation_structured":
            mapping = {
                "operation_subject": "OperationEntity",
                "platform": "OperationPlatform",
                "store": "OperationStore",
                "channel": "OperationChannel",
                "metric": "OperationMetric",
                "strategy": "OperationStrategy",
                "region": "OperationRegion",
                "period": "OperationPeriod",
            }
            return mapping.get(et, "OperationEntity")
        return "Entity"

    def _relation_type_for_topic(topic_field: str) -> str:
        return {
            "company_structured": "HAS_COMPANY_ENTITY",
            "product_structured": "HAS_PRODUCT_ENTITY",
            "operation_structured": "HAS_OPERATION_ENTITY",
        }.get(topic_field, "HAS_TOPIC_ENTITY")

    def _topic_entity_id(text: str, entity_type: str | None) -> str:
        t = str(text or "").strip().lower()
        et = str(entity_type or "").strip().lower()
        if not t:
            return ""
        return f"{et}:{t}" if et else t

    def _ensure_node(node_type: str, node_id: str, props: dict[str, Any]):
        key = f"{node_type}:{node_id}"
        if key not in graph.nodes:
            graph.nodes[key] = GraphNode(type=node_type, id=node_id, properties=props)
        return graph.nodes[key]

    for doc in documents:
        market_key = f"MarketData:{doc.id}"
        market_node = graph.nodes.get(market_key)
        if market_node is None:
            continue
        ex = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
        for field in ["company_structured", "product_structured", "operation_structured"]:
            topic_data = ex.get(field)
            if not isinstance(topic_data, dict):
                continue
            # topic tags
            for topic in (topic_data.get("topics") or []):
                t = str(topic or "").strip()
                if not t:
                    continue
                topic_node = _ensure_node("TopicTag", t.lower(), {"label": t})
                graph.edges.append(GraphEdge(type="HAS_TOPIC_TAG", from_node=market_node, to_node=topic_node, properties={}))
            # entities
            for ent in (topic_data.get("entities") or []):
                if not isinstance(ent, dict):
                    continue
                text = str(ent.get("text") or "").strip()
                etype = str(ent.get("type") or "").strip().lower()
                if not text:
                    continue
                eid = _topic_entity_id(text, etype)
                entity_node_type = _topic_entity_node_type(field, etype)
                node = _ensure_node(entity_node_type, eid, {"text": text, "entity_type": etype or None})
                graph.edges.append(GraphEdge(type=_relation_type_for_topic(field), from_node=market_node, to_node=node, properties={"weight": 1.0}))
            # relations between topic entities (optional lightweight edge synthesis)
            for rel in (topic_data.get("relations") or []):
                if not isinstance(rel, dict):
                    continue
                subj = str(rel.get("subject") or "").strip()
                obj = str(rel.get("object") or "").strip()
                pred = str(rel.get("predicate") or "").strip()
                if not subj or not obj:
                    continue
                subj_id = _topic_entity_id(subj, str(rel.get("subject_type") or ""))
                obj_id = _topic_entity_id(obj, str(rel.get("object_type") or ""))
                rel_subj_type = _topic_entity_node_type(field, str(rel.get("subject_type") or ""))
                rel_obj_type = _topic_entity_node_type(field, str(rel.get("object_type") or ""))
                subj_node = _ensure_node(rel_subj_type, subj_id, {"text": subj, "entity_type": rel.get("subject_type")})
                obj_node = _ensure_node(rel_obj_type, obj_id, {"text": obj, "entity_type": rel.get("object_type")})
                graph.edges.append(GraphEdge(type="TOPIC_RELATION", from_node=subj_node, to_node=obj_node, properties={"predicate": pred}))


def _prune_market_graph_by_topic_scope(graph, topic_scope: str | None, topic_scope_entities: dict[str, list[str]] | None):
    from app.services.graph.models import Graph

    normalized_scope = str(topic_scope or "").strip().lower()
    if not normalized_scope:
        return graph

    mapping = topic_scope_entities if isinstance(topic_scope_entities, dict) else {}
    scope_types = {str(item or "").strip() for item in (mapping.get(normalized_scope) or []) if str(item or "").strip()}
    if not scope_types:
        return graph

    if not graph.nodes:
        return Graph(schema_version=graph.schema_version)

    adjacency: dict[str, set[str]] = {}
    for edge in graph.edges:
        from_key = f"{edge.from_node.type}:{edge.from_node.id}"
        to_key = f"{edge.to_node.type}:{edge.to_node.id}"
        if from_key not in graph.nodes or to_key not in graph.nodes:
            continue
        adjacency.setdefault(from_key, set()).add(to_key)
        adjacency.setdefault(to_key, set()).add(from_key)

    # Keep only connected components that contain both:
    # 1) topic-scope entities (Company*/Product*/Operation*)
    # 2) market roots (MarketData)
    unvisited = set(graph.nodes.keys())
    kept_node_keys: set[str] = set()
    while unvisited:
        start = unvisited.pop()
        component = {start}
        stack = [start]
        has_scope = graph.nodes[start].type in scope_types
        has_market_root = graph.nodes[start].type == "MarketData"
        while stack:
            current = stack.pop()
            for neighbor in adjacency.get(current, set()):
                if neighbor in component:
                    continue
                component.add(neighbor)
                if neighbor in unvisited:
                    unvisited.remove(neighbor)
                node_type = graph.nodes.get(neighbor).type if graph.nodes.get(neighbor) else ""
                if node_type in scope_types:
                    has_scope = True
                if node_type == "MarketData":
                    has_market_root = True
                stack.append(neighbor)
        if has_scope and has_market_root:
            kept_node_keys.update(component)

    pruned = Graph(schema_version=graph.schema_version)
    for node_key in kept_node_keys:
        node = graph.nodes.get(node_key)
        if node is not None:
            pruned.nodes[node_key] = node

    for edge in graph.edges:
        from_key = f"{edge.from_node.type}:{edge.from_node.id}"
        to_key = f"{edge.to_node.type}:{edge.to_node.id}"
        if from_key in kept_node_keys and to_key in kept_node_keys:
            pruned.edges.append(edge)
    return pruned


@router.get("/stats")
def get_stats():
    """获取数据库统计信息"""
    with SessionLocal() as session:
        # 文档统计
        doc_total = session.execute(select(func.count(Document.id))).scalar() or 0
        today = datetime.now().date()
        doc_recent = session.execute(
            select(func.count(Document.id)).where(
                func.date(Document.created_at) == today
            )
        ).scalar() or 0
        
        # 社交平台数据统计
        social_total = session.execute(
            select(func.count(Document.id)).where(Document.doc_type == "social_sentiment")
        ).scalar() or 0
        social_recent = session.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.doc_type == "social_sentiment",
                    func.date(Document.created_at) == today
                )
            )
        ).scalar() or 0
        
        # 数据源统计
        source_total = session.execute(select(func.count(Source.id))).scalar() or 0
        
        # 市场数据统计
        market_total = session.execute(select(func.count(MarketStat.id))).scalar() or 0
        
        # 搜索历史统计
        history_total = session.execute(select(func.count(SearchHistory.id))).scalar() or 0
        
        return success_response({
            "documents": {
                "total": doc_total,
                "recent_today": doc_recent,
            },
            "social_data": {
                "total": social_total,
                "recent_today": social_recent,
            },
            "sources": {
                "total": source_total,
            },
            "market_stats": {
                "total": market_total,
            },
            "search_history": {
                "total": history_total,
            },
        })


@router.post("/documents/raw-import")
def raw_import_documents(request: Request, payload: RawImportRequest):
    """Raw data direct ingest: skip fetch stage, store documents and optionally run structured extraction."""
    project_key = _project_key_from_request(request)
    extraction_app = ExtractionApplicationService()
    now = datetime.utcnow()

    with bind_project(project_key):
        with SessionLocal() as session:
            source = session.execute(
                select(Source).where(Source.name == payload.source_name)
            ).scalar_one_or_none()
            if source is None:
                source = Source(
                    name=payload.source_name,
                    kind=payload.source_kind or "manual",
                    base_url=None,
                    enabled=True,
                )
                session.add(source)
                session.flush()

            inserted = 0
            updated = 0
            skipped = 0
            errors: list[dict[str, Any]] = []
            item_results: list[dict[str, Any]] = []

            for idx, item in enumerate(payload.items):
                try:
                    text = str(item.text or "").strip()
                    if not text:
                        skipped += 1
                        continue

                    uri_list = _normalize_uri_list(item, payload.infer_from_links)
                    uri = uri_list[0] if uri_list else None
                    title = (item.title or "").strip() or None
                    if not title:
                        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
                        title = (first_line[:240] if first_line else None)
                    summary = (item.summary or "").strip() or None
                    if not summary:
                        summary = text[:400] if len(text) > 400 else None

                    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    doc_type = _normalize_doc_type_for_raw(item.doc_type, payload.default_doc_type)

                    publish_date_value = None
                    if item.publish_date:
                        try:
                            publish_date_value = datetime.fromisoformat(str(item.publish_date)).date()
                        except Exception:
                            try:
                                publish_date_value = date.fromisoformat(str(item.publish_date))
                            except Exception:
                                publish_date_value = None

                    existing = None
                    if uri:
                        existing = session.execute(select(Document).where(Document.uri == uri)).scalar_one_or_none()
                    if existing is None:
                        existing = session.execute(select(Document).where(Document.text_hash == text_hash)).scalar_one_or_none()

                    doc = existing
                    if doc and not payload.overwrite_on_uri:
                        skipped += 1
                        item_results.append({"index": idx, "doc_id": doc.id, "status": "skipped_exists", "uri": doc.uri})
                        continue

                    if doc is None:
                        doc = Document(
                            source_id=source.id,
                            state=(item.state or None),
                            doc_type=doc_type,
                            title=title,
                            publish_date=publish_date_value,
                            content=text,
                            summary=summary,
                            text_hash=text_hash,
                            uri=uri,
                            created_at=now,
                            updated_at=now,
                        )
                        session.add(doc)
                        session.flush()
                        inserted += 1
                    else:
                        doc.source_id = source.id
                        doc.state = item.state or doc.state
                        doc.doc_type = doc_type or doc.doc_type
                        doc.title = title or doc.title
                        doc.publish_date = publish_date_value or doc.publish_date
                        doc.content = text
                        doc.summary = summary or doc.summary
                        doc.text_hash = text_hash
                        doc.uri = uri or doc.uri
                        doc.updated_at = now
                        updated += 1

                    if payload.enable_extraction:
                        extract_mode = payload.extraction_mode
                        if extract_mode == "auto":
                            if doc_type in {"market", "market_info"}:
                                extract_mode = "market"
                            elif doc_type in {"policy", "policy_regulation"}:
                                extract_mode = "policy"
                            elif doc_type in {"social_sentiment", "social_feed"}:
                                extract_mode = "social"
                            else:
                                extract_mode = "social"  # generic path with ER+sentiment as default

                        chunks = _chunk_text_for_extraction(
                            text,
                            chunk_size=int(payload.chunk_size),
                            overlap=int(payload.chunk_overlap),
                            max_chunks=int(payload.max_chunks),
                        )
                        extracted_parts: list[dict[str, Any]] = []
                        for chunk in chunks:
                            if extract_mode == "market":
                                extracted = extraction_app.extract_structured_enriched(chunk, include_market=True)
                            elif extract_mode == "policy":
                                extracted = extraction_app.extract_structured_enriched(chunk, include_policy=True)
                            elif extract_mode == "social":
                                extracted = extraction_app.extract_structured_enriched(chunk, include_sentiment=True)
                            else:
                                extracted = extraction_app.extract_structured_enriched(chunk)
                            if isinstance(extracted, dict) and extracted:
                                extracted_parts.append(extracted)

                        final_extracted = _merge_extracted_batch(extracted_parts) if extracted_parts else {}
                        if final_extracted:
                            raw_meta = {
                                "uris": uri_list,
                                "uri_count": len(uri_list),
                                "chunk_count": len(chunks),
                                "chunk_size": int(payload.chunk_size),
                                "chunk_overlap": int(payload.chunk_overlap),
                            }
                            final_extracted["_raw_input"] = _deep_merge_json(
                                final_extracted.get("_raw_input", {}),
                                raw_meta,
                            )
                            doc.extracted_data = final_extracted

                    item_results.append({
                        "index": idx,
                        "doc_id": doc.id,
                        "status": "ok",
                        "uri": doc.uri,
                        "uris": uri_list,
                        "doc_type": doc.doc_type,
                    })
                except Exception as e:  # noqa: BLE001
                    logger.warning("raw_import failed idx=%s err=%s", idx, e)
                    errors.append({"index": idx, "error": str(e)})

            session.commit()
            return success_response(
                {
                    "inserted": inserted,
                    "updated": updated,
                    "skipped": skipped,
                    "error_count": len(errors),
                    "errors": errors[:20],
                    "items": item_results[:50],
                    "source_name": source.name,
                    "project_key": project_key,
                }
            )


@router.post("/documents/list")
def list_documents(payload: DocumentListRequest):
    """列出文档"""
    with SessionLocal() as session:
        query = select(Document)
        
        # 过滤条件
        conditions = []
        if payload.state:
            conditions.append(Document.state == payload.state.upper())
        if payload.doc_type:
            conditions.append(Document.doc_type == payload.doc_type)
        if payload.has_extracted_data is True:
            conditions.append(Document.extracted_data.isnot(None))
        elif payload.has_extracted_data is False:
            conditions.append(Document.extracted_data.is_(None))
        if payload.search:
            search_term = f"%{payload.search}%"
            conditions.append(
                or_(
                    Document.title.ilike(search_term),
                    Document.summary.ilike(search_term),
                    Document.uri.ilike(search_term),
                )
            )
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 总数
        total_query = select(func.count()).select_from(Document)
        if conditions:
            total_query = total_query.where(and_(*conditions))
        total = session.execute(total_query).scalar() or 0
        
        # 排序 - 重新构建查询以确保排序正确应用
        sort_by = payload.sort_by or "created_at"
        sort_order = payload.sort_order or "desc"
        
        logger.info(f"文档列表排序参数: sort_by={sort_by}, sort_order={sort_order}, payload.sort_by={payload.sort_by}, payload.sort_order={payload.sort_order}")
        
        # 重新构建查询：先构建基础查询（带过滤条件），然后应用排序
        base_query = select(Document)
        if conditions:
            base_query = base_query.where(and_(*conditions))
        
        if sort_by == "publish_date":
            if sort_order == "desc":
                # 使用nullslast函数确保null值在最后，然后按id降序作为二级排序
                query = base_query.order_by(
                    nullslast(Document.publish_date.desc()),
                    Document.id.desc()
                )
                logger.info("应用排序: publish_date DESC NULLS LAST, id DESC")
            else:
                query = base_query.order_by(
                    nullslast(Document.publish_date.asc()),
                    Document.id.asc()
                )
                logger.info("应用排序: publish_date ASC NULLS LAST, id ASC")
        elif sort_by == "created_at":
            if sort_order == "desc":
                # 先按created_at降序，然后按id降序作为二级排序
                query = base_query.order_by(
                    Document.created_at.desc(),
                    Document.id.desc()
                )
                logger.info("应用排序: created_at DESC, id DESC")
            else:
                query = base_query.order_by(
                    Document.created_at.asc(),
                    Document.id.asc()
                )
                logger.info("应用排序: created_at ASC, id ASC")
        elif sort_by == "id":
            if sort_order == "desc":
                query = base_query.order_by(Document.id.desc())
                logger.info("应用排序: id DESC")
            else:
                query = base_query.order_by(Document.id.asc())
                logger.info("应用排序: id ASC")
        else:
            query = base_query.order_by(Document.created_at.desc(), Document.id.desc())
            logger.info("应用默认排序: created_at DESC, id DESC")
        
        # 打印SQL查询用于调试
        try:
            compiled_query = str(query.compile(compile_kwargs={"literal_binds": False}))
            logger.info(f"SQL查询编译结果: {compiled_query[:500]}...")  # 只打印前500字符
        except Exception as e:
            logger.warning(f"无法编译SQL查询: {e}")
        
        # 分页
        offset = (payload.page - 1) * payload.page_size
        query = query.offset(offset).limit(payload.page_size)
        
        logger.info(f"执行查询: offset={offset}, limit={payload.page_size}")
        documents = session.execute(query).scalars().all()
        logger.info(f"查询返回 {len(documents)} 条记录")
        
        # 记录排序后的前几条数据的ID和排序字段值，用于调试
        if documents:
            sample_ids = [doc.id for doc in documents[:5]]
            if sort_by == "created_at":
                sample_values = [doc.created_at.isoformat() if doc.created_at else None for doc in documents[:5]]
            elif sort_by == "publish_date":
                sample_values = [doc.publish_date.isoformat() if doc.publish_date else None for doc in documents[:5]]
            elif sort_by == "id":
                sample_values = [doc.id for doc in documents[:5]]
            else:
                sample_values = []
            logger.info(f"排序后前5条数据: IDs={sample_ids}, {sort_by}={sample_values}")
            
            # 验证排序是否正确
            if sort_by == "created_at" and len(documents) > 1:
                for i in range(len(documents) - 1):
                    if documents[i].created_at and documents[i+1].created_at:
                        if sort_order == "desc":
                            if documents[i].created_at < documents[i+1].created_at:
                                logger.warning(f"排序错误: 位置{i}的created_at ({documents[i].created_at}) < 位置{i+1}的created_at ({documents[i+1].created_at})")
                            elif documents[i].created_at == documents[i+1].created_at and documents[i].id < documents[i+1].id:
                                logger.warning(f"二级排序错误: 位置{i}和{i+1}的created_at相同，但ID顺序错误 ({documents[i].id} < {documents[i+1].id})")
                        else:
                            if documents[i].created_at > documents[i+1].created_at:
                                logger.warning(f"排序错误: 位置{i}的created_at ({documents[i].created_at}) > 位置{i+1}的created_at ({documents[i+1].created_at})")
                            elif documents[i].created_at == documents[i+1].created_at and documents[i].id > documents[i+1].id:
                                logger.warning(f"二级排序错误: 位置{i}和{i+1}的created_at相同，但ID顺序错误 ({documents[i].id} > {documents[i+1].id})")
        
        items = []
        for doc in documents:
            items.append({
                "id": doc.id,
                "title": doc.title,
                "doc_type": doc.doc_type,
                "state": doc.state,
                "source_id": doc.source_id,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "publish_date": doc.publish_date.isoformat() if doc.publish_date else None,
                "has_extracted_data": doc.extracted_data is not None,
            })
        
        return success_response({
            "items": items,
            "total": total,
            "page": payload.page,
            "page_size": payload.page_size,
        })


@router.get("/documents/{doc_id}")
def get_document(doc_id: int):
    """获取文档详情"""
    with SessionLocal() as session:
        doc = session.execute(
            select(Document).where(Document.id == doc_id)
        ).scalar_one_or_none()
        
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        
        return success_response({
            "id": doc.id,
            "title": doc.title,
            "doc_type": doc.doc_type,
            "state": doc.state,
            "status": doc.status,
            "publish_date": doc.publish_date.isoformat() if doc.publish_date else None,
            "content": doc.content,
            "summary": doc.summary,
            "uri": doc.uri,
            "extracted_data": doc.extracted_data,
            "source_id": doc.source_id,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        })


class UpdateExtractedDataRequest(BaseModel):
    mode: Literal["replace", "merge"] = Field(default="replace", description="replace: 全量替换；merge: 递归合并(对象)")
    extracted_data: Any = Field(default=None, description="要写入的 JSON 值；null 表示清空 extracted_data")


class BulkUpdateExtractedDataRequest(BaseModel):
    doc_ids: List[int] = Field(..., description="要更新的文档ID列表")
    mode: Literal["replace", "merge"] = Field(default="replace", description="replace: 全量替换；merge: 递归合并(对象)")
    extracted_data: Any = Field(default=None, description="要写入的 JSON 值；null 表示清空 extracted_data")


@router.post("/documents/{doc_id}/extracted-data")
def update_document_extracted_data(doc_id: int, payload: UpdateExtractedDataRequest):
    """手动写入/合并文档 extracted_data（在库结构化结果）。"""
    with SessionLocal() as session:
        doc = session.execute(
            select(Document).where(Document.id == doc_id)
        ).scalar_one_or_none()

        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")

        if payload.extracted_data is None:
            doc.extracted_data = None
        else:
            if payload.mode == "merge":
                base_val = doc.extracted_data or {}
                if not isinstance(base_val, dict) or not isinstance(payload.extracted_data, dict):
                    raise HTTPException(status_code=400, detail="merge 模式要求 extracted_data 为 JSON 对象(dict)")
                doc.extracted_data = _deep_merge_json(base_val, payload.extracted_data)
            else:
                doc.extracted_data = payload.extracted_data

        session.commit()
        return success_response({"id": doc.id, "extracted_data": doc.extracted_data})


@router.post("/documents/bulk/extracted-data")
def bulk_update_document_extracted_data(payload: BulkUpdateExtractedDataRequest):
    """批量写入/合并文档 extracted_data。"""
    if not payload.doc_ids:
        raise HTTPException(status_code=400, detail="doc_ids 不能为空")

    updated = 0
    skipped = 0
    errors: list[dict[str, Any]] = []

    with SessionLocal() as session:
        docs = (
            session.execute(select(Document).where(Document.id.in_(payload.doc_ids)))
            .scalars()
            .all()
        )
        found_ids = {d.id for d in docs}
        missing = [i for i in payload.doc_ids if i not in found_ids]

        for doc in docs:
            try:
                if payload.extracted_data is None:
                    doc.extracted_data = None
                else:
                    if payload.mode == "merge":
                        base_val = doc.extracted_data or {}
                        if not isinstance(base_val, dict) or not isinstance(payload.extracted_data, dict):
                            skipped += 1
                            errors.append({"id": doc.id, "error": "merge 模式要求 extracted_data 为 JSON 对象(dict)"})
                            continue
                        doc.extracted_data = _deep_merge_json(base_val, payload.extracted_data)
                    else:
                        doc.extracted_data = payload.extracted_data
                updated += 1
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                errors.append({"id": doc.id, "error": str(exc)})

        session.commit()

    return success_response(
        {
            "requested": len(payload.doc_ids),
            "updated": updated,
            "skipped": skipped,
            "missing": missing,
            "errors": errors,
        }
    )

@router.post("/documents/delete")
def delete_documents(payload: DeleteDocumentsRequest):
    """删除文档"""
    with SessionLocal() as session:
        deleted = 0
        for doc_id in payload.ids:
            doc = session.execute(
                select(Document).where(Document.id == doc_id)
            ).scalar_one_or_none()
            if doc:
                session.delete(doc)
                deleted += 1
        
        session.commit()
        return success_response({"deleted": deleted})


@router.post("/documents/re-extract")
def re_extract_documents(payload: ReExtractRequest):
    """重新提取文档的结构化数据"""
    from ..services.extraction.application import ExtractionApplicationService
    extraction_app = ExtractionApplicationService()
    with SessionLocal() as session:
        # 确定要提取的文档
        if payload.doc_ids:
            conditions = [Document.id.in_(payload.doc_ids)]
            if not bool(payload.fetch_missing_content):
                conditions.append(Document.content.isnot(None))
            query = select(Document).where(and_(*conditions))
        else:
            # 不限制 doc_type：只要有可提取文本（或允许回抓正文）就参与候选
            conditions: list[Any] = []
            if not bool(payload.fetch_missing_content):
                conditions.append(Document.content.isnot(None))
            query = select(Document).where(and_(*conditions))
        
        if payload.limit:
            query = query.limit(int(payload.limit))
        docs = session.execute(query).scalars().all()
        if not payload.force:
            filtered_docs: list[Document] = []
            for d in docs:
                ex = d.extracted_data if isinstance(d.extracted_data, dict) else {}
                if not ex:
                    filtered_docs.append(d)
                    continue
                if bool(payload.treat_empty_er_as_missing):
                    er = ex.get("entities_relations")
                    has_er = isinstance(er, dict) and bool((er.get("entities") or []) or (er.get("relations") or []))
                    if not has_er:
                        filtered_docs.append(d)
            docs = filtered_docs
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        pending = 0
        for doc in docs:
            try:
                content_text = (doc.content or "").strip()
                text_for_extract = content_text
                if not text_for_extract and bool(payload.fetch_missing_content):
                    try:
                        uri = str(doc.uri or "").strip()
                        if uri:
                            html, _resp = fetch_html(uri, timeout=12.0, retries=1)
                            content_text = (_extract_text_from_html(html) or "").strip()
                            text_for_extract = content_text
                            if content_text:
                                doc.content = content_text
                    except Exception as fetch_err:  # noqa: BLE001
                        logger.warning("re_extract fetch_content failed doc_id=%s url=%s err=%s", doc.id, doc.uri, fetch_err)

                # Unified prompt text: title + summary + content (or fallback if no正文)
                title_text = (doc.title or "").strip()
                summary_text = (doc.summary or "").strip()
                parts = [x for x in [title_text, summary_text, content_text] if x]
                if parts:
                    text_for_extract = "\n\n".join(parts)
                elif not text_for_extract:
                    text_for_extract = ""

                # 提取结构化信息
                extracted_data = None
                
                dt = str(doc.doc_type or "").strip().lower()
                extracted_data = extraction_app.extract_structured_enriched(
                    text_for_extract,
                    include_policy=dt in {"policy", "policy_regulation"},
                    include_market=dt in {"market", "market_info"},
                    include_sentiment=dt in {"social_sentiment", "social_feed"},
                )
                
                if extracted_data:
                    doc.extracted_data = extracted_data
                    success_count += 1
                    pending += 1
                else:
                    skipped_count += 1
                    
            except Exception as e:
                logger.warning(f"re_extract failed doc_id={doc.id} err={e}")
                error_count += 1
            if pending >= int(payload.batch_size):
                session.commit()
                pending = 0
        
        session.commit()
        
        return success_response({
            "total": len(docs),
            "success": success_count,
            "error": error_count,
            "skipped": skipped_count,
            "fetch_missing_content": bool(payload.fetch_missing_content),
            "batch_size": int(payload.batch_size),
            "treat_empty_er_as_missing": bool(payload.treat_empty_er_as_missing),
        })


@router.post("/documents/topic-extract")
def topic_extract_documents(request: Request, payload: TopicExtractRequest):
    """专题析取（规则筛 + LLM确认），回填 company/product/operation 专题结构化字段。"""
    from ..services.extraction.application import ExtractionApplicationService
    extraction_app = ExtractionApplicationService()
    project_key = _project_key_from_request(request)
    dicts = _get_topic_dictionaries(project_key)
    default_doc_types = ["market", "market_info", "policy", "policy_regulation", "social_sentiment", "social_feed", "news", "raw_note"]

    topic_to_field = dict(WORKFLOW_TOPIC_FIELDS)
    with bind_project(project_key):
        with SessionLocal() as session:
            if payload.doc_ids:
                q = select(Document).where(Document.id.in_(payload.doc_ids))
            else:
                doc_types = payload.doc_types or default_doc_types
                q = select(Document).where(Document.doc_type.in_(doc_types))
            if payload.limit:
                q = q.limit(int(payload.limit))
            docs = session.execute(q).scalars().all()

            # force=false 时只选缺失专题字段的文档
            if not payload.force:
                filtered: list[Document] = []
                for d in docs:
                    ex = d.extracted_data if isinstance(d.extracted_data, dict) else {}
                    needs = False
                    for t in payload.topics:
                        field = topic_to_field[t]
                        if not _topic_has_data(ex.get(field)):
                            needs = True
                            break
                    if needs:
                        filtered.append(d)
                docs = filtered

            total = len(docs)
            processed = 0
            success_count = 0
            skipped_count = 0
            error_count = 0
            topic_hits = {t: 0 for t in payload.topics}
            topic_fallback_hits = {t: 0 for t in payload.topics}
            topic_avg_coverage = {t: [] for t in payload.topics}
            pending = 0

            for doc in docs:
                processed += 1
                try:
                    content_text = (doc.content or "").strip()
                    if not content_text and bool(payload.fetch_missing_content):
                        uri = str(doc.uri or "").strip()
                        if uri:
                            try:
                                html, _resp = fetch_html(uri, timeout=12.0, retries=1)
                                fetched = (_extract_text_from_html(html) or "").strip()
                                if fetched:
                                    doc.content = fetched
                                    content_text = fetched
                            except Exception as fetch_err:  # noqa: BLE001
                                logger.warning("topic_extract fetch_content failed doc_id=%s err=%s", doc.id, fetch_err)

                    title_text = (doc.title or "").strip()
                    summary_text = (doc.summary or "").strip()
                    parts = [x for x in [title_text, summary_text, content_text] if x]
                    text_for_extract = "\n\n".join(parts).strip()
                    if len(text_for_extract) < 20:
                        skipped_count += 1
                        continue

                    ex = dict(doc.extracted_data) if isinstance(doc.extracted_data, dict) else {}
                    er = ex.get("entities_relations") if isinstance(ex.get("entities_relations"), dict) else None
                    wrote_any = False
                    selected_topics: list[str] = []
                    for topic in payload.topics:
                        score = _topic_rule_score(topic, text_for_extract, ex, er, dicts)
                        if score <= 0 and not payload.force:
                            # 写空壳标记，避免反复扫
                            field = topic_to_field[topic]
                            merged = _normalize_topic_merge(ex.get(field), _topic_structured_empty())
                            ex[field] = merged
                            continue
                        selected_topics.append(topic)

                    workflow_diag = {}
                    if selected_topics:
                        wf_result = run_topic_extraction_workflow(
                            extraction_app=extraction_app,
                            text=text_for_extract,
                            topics=selected_topics,
                            extracted_data=ex,
                            dictionaries=dicts,
                            max_selected_chunks=6,
                            fallback_max_chunks=8,
                        )
                        topic_results = wf_result.get("results") if isinstance(wf_result, dict) else {}
                        workflow_diag = wf_result.get("diagnostics") if isinstance(wf_result, dict) else {}
                        for topic in selected_topics:
                            field = topic_to_field[topic]
                            incoming = topic_results.get(topic) if isinstance(topic_results, dict) else None
                            incoming = incoming if isinstance(incoming, dict) else wf_empty_topic_structured()
                            ex[field] = wf_merge_topic_structured(ex.get(field), incoming)
                            if wf_topic_has_data(ex[field]):
                                topic_hits[topic] += 1
                                wrote_any = True
                            tdiag = (workflow_diag.get("topics") or {}).get(topic) if isinstance(workflow_diag, dict) else None
                            if isinstance(tdiag, dict):
                                cov = tdiag.get("coverage_ratio")
                                if isinstance(cov, (int, float)):
                                    topic_avg_coverage[topic].append(float(cov))
                                if bool(tdiag.get("fallback_used")):
                                    topic_fallback_hits[topic] += 1

                    ex["_topic_extract_workflow"] = {
                        "version": 1,
                        "candidate_mode": payload.candidate_mode,
                        "doc_topics_selected": selected_topics,
                        "diagnostics": workflow_diag if isinstance(workflow_diag, dict) else {},
                    }

                    doc.extracted_data = dict(ex)
                    success_count += 1 if wrote_any else 0
                    if not wrote_any:
                        skipped_count += 1
                    pending += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("topic_extract failed doc_id=%s err=%s", getattr(doc, "id", None), exc)
                    error_count += 1
                if pending >= int(payload.batch_size):
                    session.commit()
                    pending = 0

            session.commit()
            return success_response(
                {
                    "project_key": project_key,
                    "total": total,
                    "processed": processed,
                    "success": success_count,
                    "skipped": skipped_count,
                    "error": error_count,
                    "topics": list(payload.topics),
                    "topic_hits": topic_hits,
                    "topic_fallback_hits": topic_fallback_hits,
                    "topic_avg_coverage": {
                        k: round(sum(v) / len(v), 4) if v else 0.0 for k, v in topic_avg_coverage.items()
                    },
                    "batch_size": int(payload.batch_size),
                    "candidate_mode": payload.candidate_mode,
                    "fetch_missing_content": bool(payload.fetch_missing_content),
                }
            )


@router.post("/sources/list")
def list_sources(payload: SourceListRequest):
    """列出数据源"""
    with SessionLocal() as session:
        query = select(Source)
        
        conditions = []
        if payload.kind:
            conditions.append(Source.kind == payload.kind)
        if payload.enabled is not None:
            conditions.append(Source.enabled == payload.enabled)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 总数
        total_query = select(func.count()).select_from(Source)
        if conditions:
            total_query = total_query.where(and_(*conditions))
        total = session.execute(total_query).scalar() or 0
        
        # 排序
        sort_by = payload.sort_by or "created_at"
        sort_order = payload.sort_order or "desc"
        
        if sort_by == "id":
            if sort_order == "desc":
                query = query.order_by(Source.id.desc())
            else:
                query = query.order_by(Source.id.asc())
        elif sort_by == "name":
            if sort_order == "desc":
                query = query.order_by(Source.name.desc())
            else:
                query = query.order_by(Source.name.asc())
        elif sort_by == "created_at":
            if sort_order == "desc":
                query = query.order_by(Source.created_at.desc())
            else:
                query = query.order_by(Source.created_at.asc())
        else:
            query = query.order_by(Source.created_at.desc())
        
        # 如果按文档数排序，需要先获取所有数据再排序
        if sort_by == "document_count":
            # 先不分页获取所有数据
            all_sources = session.execute(query).scalars().all()
            # 计算每个源的文档数
            doc_counts = {}
            for src in all_sources:
                doc_count = session.execute(
                    select(func.count(Document.id)).where(Document.source_id == src.id)
                ).scalar() or 0
                doc_counts[src.id] = doc_count
            # 排序
            all_sources.sort(key=lambda s: doc_counts.get(s.id, 0), reverse=(sort_order == "desc"))
            # 分页
            offset = (payload.page - 1) * payload.page_size
            sources = all_sources[offset:offset + payload.page_size]
        else:
            # 分页
            offset = (payload.page - 1) * payload.page_size
            query = query.offset(offset).limit(payload.page_size)
            sources = session.execute(query).scalars().all()
        
        items = []
        for src in sources:
            # 统计该源下的文档数
            doc_count = session.execute(
                select(func.count(Document.id)).where(Document.source_id == src.id)
            ).scalar() or 0
            
            items.append({
                "id": src.id,
                "name": src.name,
                "kind": src.kind,
                "base_url": src.base_url,
                "enabled": src.enabled,
                "document_count": doc_count,
                "created_at": src.created_at.isoformat() if src.created_at else None,
            })
        
        return success_response({
            "items": items,
            "total": total,
            "page": payload.page,
            "page_size": payload.page_size,
        })


@router.post("/market-stats/list")
def list_market_stats(payload: MarketStatsListRequest):
    """列出市场数据"""
    with SessionLocal() as session:
        query = select(MarketStat)
        
        conditions = []
        if payload.state:
            conditions.append(MarketStat.state == payload.state.upper())
        if payload.game:
            conditions.append(MarketStat.game.ilike(f"%{payload.game}%"))
        if payload.start_date:
            try:
                start = datetime.fromisoformat(payload.start_date).date()
                conditions.append(MarketStat.date >= start)
            except Exception:
                pass
        if payload.end_date:
            try:
                end = datetime.fromisoformat(payload.end_date).date()
                conditions.append(MarketStat.date <= end)
            except Exception:
                pass
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 总数
        total_query = select(func.count()).select_from(MarketStat)
        if conditions:
            total_query = total_query.where(and_(*conditions))
        total = session.execute(total_query).scalar() or 0
        
        # 排序
        sort_by = payload.sort_by or "date"
        sort_order = payload.sort_order or "desc"
        
        if sort_by == "date":
            if sort_order == "desc":
                query = query.order_by(MarketStat.date.desc().nullslast())
            else:
                query = query.order_by(MarketStat.date.asc().nullslast())
        elif sort_by == "id":
            if sort_order == "desc":
                query = query.order_by(MarketStat.id.desc())
            else:
                query = query.order_by(MarketStat.id.asc())
        elif sort_by == "sales_volume":
            if sort_order == "desc":
                query = query.order_by(MarketStat.sales_volume.desc().nullslast())
            else:
                query = query.order_by(MarketStat.sales_volume.asc().nullslast())
        elif sort_by == "revenue":
            if sort_order == "desc":
                query = query.order_by(MarketStat.revenue.desc().nullslast())
            else:
                query = query.order_by(MarketStat.revenue.asc().nullslast())
        elif sort_by == "jackpot":
            if sort_order == "desc":
                query = query.order_by(MarketStat.jackpot.desc().nullslast())
            else:
                query = query.order_by(MarketStat.jackpot.asc().nullslast())
        else:
            query = query.order_by(MarketStat.date.desc())
        
        # 分页
        offset = (payload.page - 1) * payload.page_size
        query = query.offset(offset).limit(payload.page_size)
        
        stats = session.execute(query).scalars().all()
        
        items = []
        for stat in stats:
            items.append({
                "id": stat.id,
                "state": stat.state,
                "game": stat.game,
                "date": stat.date.isoformat() if stat.date else None,
                "sales_volume": float(stat.sales_volume) if stat.sales_volume else None,
                "revenue": float(stat.revenue) if stat.revenue else None,
                "revenue_estimated": float(stat.revenue_estimated) if stat.revenue_estimated else None,
                "jackpot": float(stat.jackpot) if stat.jackpot else None,
                "ticket_price": float(stat.ticket_price) if stat.ticket_price else None,
                "draw_number": stat.draw_number,
                "yoy": float(stat.yoy) if stat.yoy else None,
                "mom": float(stat.mom) if stat.mom else None,
                "source_name": stat.source_name,
                "source_uri": stat.source_uri,
            })
        
        return success_response({
            "items": items,
            "total": total,
            "page": payload.page,
            "page_size": payload.page_size,
        })


@router.post("/social-data/list")
def list_social_data(payload: SocialDataListRequest):
    """列出社交平台数据"""
    with SessionLocal() as session:
        query = select(Document).where(Document.doc_type == "social_sentiment")
        
        # 过滤条件
        conditions = [Document.doc_type == "social_sentiment"]
        
        if payload.platform:
            # 平台信息存储在extracted_data中
            conditions.append(Document.extracted_data["platform"].astext == payload.platform)
        
        if payload.sentiment_orientation:
            # 情感倾向存储在extracted_data->sentiment->sentiment_orientation中
            conditions.append(
                Document.extracted_data["sentiment"]["sentiment_orientation"].astext == payload.sentiment_orientation
            )
        
        if payload.search:
            search_term = f"%{payload.search}%"
            conditions.append(
                or_(
                    Document.title.ilike(search_term),
                    Document.summary.ilike(search_term),
                    Document.content.ilike(search_term),
                    Document.uri.ilike(search_term),
                )
            )
        
        query = query.where(and_(*conditions))
        
        # 总数
        total_query = select(func.count()).select_from(Document).where(and_(*conditions))
        total = session.execute(total_query).scalar() or 0
        
        # 排序
        sort_by = payload.sort_by or "created_at"
        sort_order = payload.sort_order or "desc"
        
        if sort_by == "publish_date":
            if sort_order == "desc":
                query = query.order_by(
                    nullslast(Document.publish_date.desc()),
                    Document.id.desc()
                )
            else:
                query = query.order_by(
                    nullslast(Document.publish_date.asc()),
                    Document.id.asc()
                )
        elif sort_by == "created_at":
            if sort_order == "desc":
                query = query.order_by(Document.created_at.desc(), Document.id.desc())
            else:
                query = query.order_by(Document.created_at.asc(), Document.id.asc())
        elif sort_by == "id":
            if sort_order == "desc":
                query = query.order_by(Document.id.desc())
            else:
                query = query.order_by(Document.id.asc())
        else:
            query = query.order_by(Document.created_at.desc(), Document.id.desc())
        
        # 分页
        offset = (payload.page - 1) * payload.page_size
        query = query.offset(offset).limit(payload.page_size)
        
        documents = session.execute(query).scalars().all()
        
        items = []
        for doc in documents:
            extracted = doc.extracted_data or {}
            sentiment = extracted.get("sentiment", {})
            
            items.append({
                "id": doc.id,
                "title": doc.title,
                "platform": extracted.get("platform"),
                "username": extracted.get("username"),
                "subreddit": extracted.get("subreddit"),
                "likes": extracted.get("likes"),
                "comments": extracted.get("comments"),
                "text": extracted.get("text") or doc.content or doc.summary,
                "sentiment_orientation": sentiment.get("sentiment_orientation"),
                "sentiment_tags": sentiment.get("sentiment_tags", []),
                "topic": sentiment.get("topic"),
                "key_phrases": sentiment.get("key_phrases", []),
                "emotion_words": sentiment.get("emotion_words", []),
                "keywords": extracted.get("keywords", []),
                "entities": extracted.get("entities", []),
                "uri": doc.uri,
                "publish_date": doc.publish_date.isoformat() if doc.publish_date else None,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "extracted_data": doc.extracted_data,
            })
        
        return success_response({
            "items": items,
            "total": total,
            "page": payload.page,
            "page_size": payload.page_size,
        })


@router.get("/export-graph")
def export_graph(doc_ids: str = Query(..., description="文档ID列表，逗号分隔")):
    """导出指定文档的内容图谱"""
    from fastapi.responses import JSONResponse
    from app.services.graph.adapters import normalize_document
    from app.services.graph.builder import build_graph
    from app.services.graph.exporter import export_to_json
    
    try:
        doc_id_list = [int(id.strip()) for id in doc_ids.split(',') if id.strip()]
        if not doc_id_list:
            return JSONResponse(
                status_code=400,
                content={"error": "请提供至少一个文档ID"}
            )
        
        with SessionLocal() as session:
            # 查询文档
            from sqlalchemy import in_
            query = select(Document).where(
                and_(
                    Document.doc_type == "social_sentiment",
                    Document.id.in_(doc_id_list)
                )
            )
            documents = session.execute(query).scalars().all()
            
            if not documents:
                return JSONResponse(
                    status_code=404,
                    content={"error": "未找到指定的文档"}
                )
            
            # 规范化文档
            normalized_posts = []
            for doc in documents:
                normalized = normalize_document(doc)
                if normalized:
                    normalized_posts.append(normalized)
            
            if not normalized_posts:
                return JSONResponse(
                    status_code=400,
                    content={"error": "无法规范化文档数据"}
                )
            
            # 构建图谱
            graph = build_graph(normalized_posts)
            
            # 导出JSON
            json_data = export_to_json(graph)
            
            return JSONResponse(content=json_data)
            
    except Exception as e:
        logger.error(f"导出图谱失败: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"导出失败: {str(e)}"}
        )


@router.get("/content-graph")
def get_content_graph(
    request: Request,
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    platform: Optional[str] = Query(None, description="平台名称，如 reddit, twitter"),
    topic: Optional[str] = Query(None, description="主题过滤"),
    limit: int = Query(default=100, ge=1, le=2000, description="限制文档数量"),
):
    """根据条件获取内容图谱数据"""
    from fastapi.responses import JSONResponse
    from app.services.graph.adapters import normalize_document
    from app.services.graph.builder import build_graph, build_topic_subgraph
    from app.services.graph.exporter import export_to_json
    from app.services.graph.models import Graph
    project_key = _project_key_from_request(request)
    graph_doc_types = resolve_graph_doc_types(project_key)
    social_doc_types = graph_doc_types.get("social") or ["social_sentiment", "social_feed"]

    try:
        with bind_project(project_key):
            with SessionLocal() as session:
                # 构建查询条件
                conditions = [
                    Document.doc_type.in_(social_doc_types),
                    Document.extracted_data.isnot(None),
                ]

                # 时间过滤
                if start_date:
                    try:
                        start = datetime.fromisoformat(start_date).date()
                        conditions.append(
                            or_(
                                Document.publish_date >= start,
                                and_(Document.publish_date.is_(None), func.date(Document.created_at) >= start)
                            )
                        )
                    except Exception as e:
                        logger.warning(f"解析开始日期失败: {start_date}, 错误: {e}")

                if end_date:
                    try:
                        end = datetime.fromisoformat(end_date).date()
                        conditions.append(
                            or_(
                                Document.publish_date <= end,
                                and_(Document.publish_date.is_(None), func.date(Document.created_at) <= end)
                            )
                        )
                    except Exception as e:
                        logger.warning(f"解析结束日期失败: {end_date}, 错误: {e}")

                query = select(Document).where(and_(*conditions)).limit(limit)
                documents = session.execute(query).scalars().all()

                logger.info(f"查询到 {len(documents)} 条文档")

                if not documents:
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

                normalized_posts = []
                skipped_count = 0
                for doc in documents:
                    if platform:
                        extracted = doc.extracted_data or {}
                        doc_platform = extracted.get("platform", "").lower()
                        if doc_platform != platform.lower():
                            skipped_count += 1
                            continue

                    if topic:
                        extracted = doc.extracted_data or {}
                        sentiment = extracted.get("sentiment", {})
                        doc_topic = sentiment.get("topic", "").lower()
                        if topic.lower() not in doc_topic:
                            skipped_count += 1
                            continue

                    try:
                        normalized = normalize_document(doc)
                        if normalized:
                            normalized_posts.append(normalized)
                        else:
                            skipped_count += 1
                    except Exception as e:
                        logger.warning(f"规范化文档 {doc.id} 失败: {e}")
                        skipped_count += 1

                logger.info(f"规范化成功: {len(normalized_posts)}, 跳过: {skipped_count}")

                if not normalized_posts:
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

                try:
                    graph = build_graph(normalized_posts)
                    logger.info(f"构建图谱成功: {len(graph.nodes)} 个节点, {len(graph.edges)} 条边")
                except Exception as e:
                    logger.error(f"构建图谱失败: {e}", exc_info=True)
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

                if topic:
                    try:
                        graph = build_topic_subgraph(graph, topic)
                        logger.info(f"构建主题子图成功: {len(graph.nodes)} 个节点, {len(graph.edges)} 条边")
                    except Exception as e:
                        logger.warning(f"构建主题子图失败: {e}")
                        empty_graph = Graph()
                        json_data = export_to_json(empty_graph)
                        return JSONResponse(content=json_data)

                try:
                    json_data = export_to_json(graph)
                    return JSONResponse(content=json_data)
                except Exception as e:
                    logger.error(f"导出JSON失败: {e}", exc_info=True)
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)
            
    except Exception as e:
        logger.error(f"获取内容图谱失败: {e}", exc_info=True)
        # 返回空图谱而不是错误，这样前端可以正常显示
        try:
            empty_graph = Graph()
            json_data = export_to_json(empty_graph)
            return JSONResponse(content=json_data)
        except Exception as e2:
            logger.error(f"创建空图谱失败: {e2}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"error": f"获取失败: {str(e)}", "nodes": [], "edges": []}
            )


@router.get("/market-graph")
def get_market_graph(
    request: Request,
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    state: Optional[str] = Query(None, description="州代码过滤，如 CA"),
    game: Optional[str] = Query(None, description="游戏类型过滤"),
    topic_scope: Optional[Literal["company", "product", "operation"]] = Query(None, description="专题范围(company/product/operation)"),
    view: Optional[str] = Query(None, description="视图模式，如 market_deep_entities"),
    limit: int = Query(default=100, ge=1, le=2000, description="限制数据数量"),
):
    """根据条件获取市场数据图谱（从Document表中查询doc_type='market'的文档）"""
    from fastapi.responses import JSONResponse
    from app.services.graph.adapters.market import MarketAdapter
    from app.services.graph.builder import build_market_graph
    from app.services.graph.exporter import export_to_json
    from app.services.graph.models import Graph
    from datetime import datetime
    project_key = _project_key_from_request(request)
    graph_doc_types = resolve_graph_doc_types(project_key)
    market_doc_types = graph_doc_types.get("market") or ["market"]

    try:
        with bind_project(project_key):
            with SessionLocal() as session:
                from sqlalchemy import and_, or_, func
                conditions = [
                    Document.doc_type.in_(market_doc_types),
                    Document.extracted_data.isnot(None),
                ]

                if state:
                    state_upper = state.upper()
                    conditions.append(
                        or_(
                            Document.state == state_upper,
                            Document.extracted_data['market']['state'].astext == state_upper
                        )
                    )

                if game:
                    conditions.append(
                        Document.extracted_data['market']['game'].astext.ilike(f"%{game}%")
                    )

                if start_date:
                    try:
                        start = datetime.fromisoformat(start_date).date()
                        conditions.append(
                            or_(
                                Document.publish_date >= start,
                                and_(
                                    Document.publish_date.is_(None),
                                    func.date(Document.created_at) >= start
                                ),
                                func.cast(
                                    Document.extracted_data['market']['report_date'].astext,
                                    date
                                ) >= start
                            )
                        )
                    except Exception as e:
                        logger.warning(f"解析开始日期失败: {start_date}, 错误: {e}")

                if end_date:
                    try:
                        end = datetime.fromisoformat(end_date).date()
                        conditions.append(
                            or_(
                                Document.publish_date <= end,
                                and_(
                                    Document.publish_date.is_(None),
                                    func.date(Document.created_at) <= end
                                ),
                                func.cast(
                                    Document.extracted_data['market']['report_date'].astext,
                                    date
                                ) <= end
                            )
                        )
                    except Exception as e:
                        logger.warning(f"解析结束日期失败: {end_date}, 错误: {e}")

                query = select(Document).where(and_(*conditions))
                query = query.order_by(Document.publish_date.desc().nullslast(), Document.created_at.desc()).limit(limit)

                documents = session.execute(query).scalars().all()

                logger.info(f"查询到 {len(documents)} 条市场文档")

                if not documents:
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

                adapter = MarketAdapter()
                normalized_data = []
                skipped_count = 0
                for doc in documents:
                    if game:
                        extracted = doc.extracted_data or {}
                        market = extracted.get("market", {})
                        doc_game = market.get("game", "").lower()
                        if game.lower() not in doc_game:
                            skipped_count += 1
                            continue

                    try:
                        normalized = adapter.to_normalized(doc)
                        if normalized:
                            normalized_data.append(normalized)
                        else:
                            skipped_count += 1
                    except Exception as e:
                        logger.warning(f"规范化文档 {doc.id} 失败: {e}")
                        skipped_count += 1

                logger.info(f"规范化成功: {len(normalized_data)}, 跳过: {skipped_count}")

                if not normalized_data:
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

                try:
                    graph = build_market_graph(normalized_data)
                    logger.info(f"构建图谱成功: {len(graph.nodes)} 个节点, {len(graph.edges)} 条边")
                except Exception as e:
                    logger.error(f"构建图谱失败: {e}", exc_info=True)
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

                if str(view or "").strip().lower() == "market_deep_entities":
                    try:
                        _augment_market_graph_with_topic_structured(graph, documents)
                    except Exception as e:
                        logger.warning(f"扩展专题图谱节点失败: {e}")
                if topic_scope:
                    graph = _prune_market_graph_by_topic_scope(
                        graph,
                        topic_scope=topic_scope,
                        topic_scope_entities=resolve_graph_topic_scope_entities(project_key),
                    )

                try:
                    json_data = export_to_json(graph)
                    return JSONResponse(content=json_data)
                except Exception as e:
                    logger.error(f"导出JSON失败: {e}", exc_info=True)
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

    except Exception as e:
        logger.error(f"获取市场数据图谱失败: {e}", exc_info=True)
        # 返回空图谱而不是错误，这样前端可以正常显示
        try:
            empty_graph = Graph()
            json_data = export_to_json(empty_graph)
            return JSONResponse(content=json_data)
        except Exception as e2:
            logger.error(f"创建空图谱失败: {e2}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"error": f"获取失败: {str(e)}", "nodes": [], "edges": []}
            )


@router.get("/policy-graph")
def get_policy_graph(
    request: Request,
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    state: Optional[str] = Query(None, description="州代码过滤，如 CA"),
    policy_type: Optional[str] = Query(None, description="政策类型过滤，如 regulation"),
    limit: int = Query(default=100, ge=1, le=2000, description="限制政策数量"),
):
    """根据条件获取政策数据图谱"""
    from fastapi.responses import JSONResponse
    from app.services.graph.adapters.policy import PolicyAdapter
    from app.services.graph.builder import build_policy_graph
    from app.services.graph.exporter import export_to_json
    from app.services.graph.models import Graph
    project_key = _project_key_from_request(request)
    graph_doc_types = resolve_graph_doc_types(project_key)
    policy_doc_types = graph_doc_types.get("policy") or ["policy", "policy_regulation"]

    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).date()
        except Exception as exc:  # noqa: BLE001
            logger.warning("解析日期失败 %s: %s", value, exc)
            return None

    try:
        with bind_project(project_key):
            with SessionLocal() as session:
                conditions = [
                    Document.doc_type.in_(policy_doc_types),
                    Document.extracted_data.isnot(None),
                ]

                if state:
                    state_upper = state.upper()
                    conditions.append(
                        or_(
                            Document.state == state_upper,
                            Document.extracted_data["policy"]["state"].astext == state_upper,
                        )
                    )

                if policy_type:
                    conditions.append(
                        Document.extracted_data["policy"]["policy_type"].astext.ilike(f"%{policy_type}%")
                    )

                query = select(Document).where(and_(*conditions))
                query = query.order_by(
                    Document.publish_date.desc().nullslast(),
                    Document.created_at.desc(),
                )

                sql_limit = min(limit * 3, 1000)
                query = query.limit(sql_limit)

                documents = session.execute(query).scalars().all()
                logger.info("查询到 %s 条政策文档", len(documents))

                if not documents:
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

                start_dt = _parse_date(start_date)
                end_dt = _parse_date(end_date)

                adapter = PolicyAdapter()
                normalized_policies = []
                skipped_count = 0

                for doc in documents:
                    extracted = doc.extracted_data or {}
                    policy_info = extracted.get("policy") or {}

                    def _collect_dates() -> List[date]:
                        dates: List[date] = []
                        if doc.publish_date:
                            if isinstance(doc.publish_date, datetime):
                                dates.append(doc.publish_date.date())
                            else:
                                dates.append(doc.publish_date)
                        if doc.created_at:
                            dates.append(doc.created_at.date())
                        effective = policy_info.get("effective_date")
                        if effective:
                            parsed_effective = _parse_date(effective)
                            if parsed_effective:
                                dates.append(parsed_effective)
                        return dates

                    candidate_dates = _collect_dates()

                    if start_dt:
                        if not any(d >= start_dt for d in candidate_dates if d):
                            skipped_count += 1
                            continue
                    if end_dt:
                        if not any(d <= end_dt for d in candidate_dates if d):
                            skipped_count += 1
                            continue

                    try:
                        normalized = adapter.to_normalized(doc)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("规范化政策文档 %s 失败: %s", doc.id, exc)
                        skipped_count += 1
                        continue

                    if not normalized:
                        skipped_count += 1
                        continue

                    if policy_type and normalized.policy_type:
                        if policy_type.lower() not in normalized.policy_type.lower():
                            skipped_count += 1
                            continue

                    normalized_policies.append(normalized)
                    if len(normalized_policies) >= limit:
                        break

                logger.info("规范化成功 %s 条，跳过 %s 条", len(normalized_policies), skipped_count)

                if not normalized_policies:
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

                try:
                    graph = build_policy_graph(normalized_policies)
                    logger.info(
                        "构建政策图谱成功: %s 个节点, %s 条边",
                        len(graph.nodes),
                        len(graph.edges),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error("构建政策图谱失败: %s", exc, exc_info=True)
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

                try:
                    json_data = export_to_json(graph)
                    return JSONResponse(content=json_data)
                except Exception as exc:  # noqa: BLE001
                    logger.error("导出政策图谱失败: %s", exc, exc_info=True)
                    empty_graph = Graph()
                    json_data = export_to_json(empty_graph)
                    return JSONResponse(content=json_data)

    except Exception as exc:  # noqa: BLE001
        logger.error("获取政策图谱失败: %s", exc, exc_info=True)
        try:
            empty_graph = Graph()
            json_data = export_to_json(empty_graph)
            return JSONResponse(content=json_data)
        except Exception as exc2:  # noqa: BLE001
            logger.error("创建空政策图谱失败: %s", exc2, exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"error": f"获取失败: {str(exc)}", "nodes": [], "edges": []},
            )


@router.get("/search-history")
def get_search_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
):
    """获取搜索历史"""
    with SessionLocal() as session:
        total_query = select(func.count()).select_from(SearchHistory)
        total = session.execute(total_query).scalar() or 0

        query = (
            select(SearchHistory)
            .order_by(SearchHistory.last_search_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        history = session.execute(query).scalars().all()

        items = []
        for h in history:
            items.append({
                "id": h.id,
                "topic": h.topic,
                "last_search_time": h.last_search_time.isoformat() if h.last_search_time else None,
            })

        return success_response({
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        })
