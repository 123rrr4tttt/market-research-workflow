"""数据库管理API"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy import select, func, or_, and_, nullslast, nullsfirst
from sqlalchemy.orm import selectinload
from datetime import datetime, date
import logging

from ..models.base import SessionLocal
from ..models.entities import Document, Source, MarketStat, SearchHistory
from ..services.graph.doc_types import resolve_graph_doc_types
from ..services.extraction.extract import extract_policy_info, extract_market_info, extract_entities_relations
from ..services.projects import bind_project
from ..contracts import success_response


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


class ReExtractRequest(BaseModel):
    doc_ids: Optional[List[int]] = None  # 如果为空，则提取所有政策文档
    force: bool = Field(default=False, description="是否强制重新提取已有数据的文档")


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
    with SessionLocal() as session:
        # 确定要提取的文档
        if payload.doc_ids:
            query = select(Document).where(
                Document.id.in_(payload.doc_ids),
                Document.content.isnot(None)
            )
        else:
            # 提取所有政策和市场文档
            conditions = [
                Document.doc_type.in_(["policy", "market"]),
                Document.content.isnot(None)
            ]
            if not payload.force:
                conditions.append(Document.extracted_data.is_(None))
            query = select(Document).where(and_(*conditions))
        
        docs = session.execute(query).scalars().all()
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        for doc in docs:
            try:
                if not doc.content:
                    skipped_count += 1
                    continue
                
                # 提取结构化信息
                extracted_data = None
                
                if doc.doc_type == "policy":
                    # 提取政策信息
                    policy_info = extract_policy_info(doc.content)
                    if policy_info:
                        extracted_data = {"policy": policy_info}
                    
                    # 提取实体和关系
                    er_data = extract_entities_relations(doc.content)
                    if er_data:
                        if extracted_data is None:
                            extracted_data = {}
                        extracted_data["entities_relations"] = er_data
                
                elif doc.doc_type == "market":
                    # 提取市场数据信息
                    market_info = extract_market_info(doc.content)
                    if market_info:
                        extracted_data = {"market": market_info}
                    
                    # 提取实体和关系
                    er_data = extract_entities_relations(doc.content)
                    if er_data:
                        if extracted_data is None:
                            extracted_data = {}
                        extracted_data["entities_relations"] = er_data
                
                if extracted_data:
                    doc.extracted_data = extracted_data
                    success_count += 1
                else:
                    skipped_count += 1
                    
            except Exception as e:
                logger.warning(f"re_extract failed doc_id={doc.id} err={e}")
                error_count += 1
        
        session.commit()
        
        return success_response({
            "total": len(docs),
            "success": success_count,
            "error": error_count,
            "skipped": skipped_count,
        })


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
    limit: int = Query(default=100, ge=1, le=500, description="限制文档数量"),
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
    limit: int = Query(default=100, ge=1, le=500, description="限制数据数量"),
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
    limit: int = Query(default=100, ge=1, le=500, description="限制政策数量"),
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
def get_search_history(limit: int = Query(default=100, ge=1, le=1000)):
    """获取搜索历史"""
    with SessionLocal() as session:
        query = select(SearchHistory).order_by(SearchHistory.last_search_time.desc()).limit(limit)
        history = session.execute(query).scalars().all()
        
        items = []
        for h in history:
            items.append({
                "id": h.id,
                "topic": h.topic,
                "last_search_time": h.last_search_time.isoformat() if h.last_search_time else None,
            })
        
        return success_response({"items": items, "total": len(items)})
