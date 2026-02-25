"""仪表盘数据API"""
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.exc import OperationalError, DatabaseError
from datetime import datetime, date, timedelta
import logging

from ..models.base import SessionLocal
from ..models.entities import (
    Document,
    Source,
    MarketStat,
    SearchHistory,
    EtlJobRun,
    MarketMetricPoint,
    Product,
    PriceObservation,
)
from ..services.graph.doc_types import resolve_graph_doc_types

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _decimal_to_float(value):
    """将Decimal转换为float"""
    if value is None:
        return None
    return float(value)


@router.get("/global/stats")
def get_global_stats():
    """总库汇总统计（aggregator schema）"""
    from sqlalchemy import text
    from ..models.base import engine

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM aggregator.documents_agg) AS documents_total,
                  (SELECT COUNT(*) FROM aggregator.market_metric_points_agg) AS metrics_total,
                  (SELECT COUNT(*) FROM aggregator.price_observations_agg) AS prices_total
                """
            )
        ).first()
        if not rows:
            return {"documents_total": 0, "metrics_total": 0, "prices_total": 0}
        return {
            "documents_total": int(rows.documents_total or 0),
            "metrics_total": int(rows.metrics_total or 0),
            "prices_total": int(rows.prices_total or 0),
        }


@router.get("/stats")
def get_dashboard_stats():
    """获取仪表盘概览统计数据"""
    try:
        with SessionLocal() as session:
            # 文档统计
            doc_total = session.execute(select(func.count(Document.id))).scalar() or 0
            today = datetime.now().date()
            doc_recent_today = session.execute(
                select(func.count(Document.id)).where(
                    func.date(Document.created_at) == today
                )
            ).scalar() or 0
            
            # 最近7天文档增长
            seven_days_ago = today - timedelta(days=7)
            doc_recent_7d = session.execute(
                select(func.count(Document.id)).where(
                    func.date(Document.created_at) >= seven_days_ago
                )
            ).scalar() or 0
            
            # 数据源统计
            source_total = session.execute(select(func.count(Source.id))).scalar() or 0
            source_enabled = session.execute(
                select(func.count(Source.id)).where(Source.enabled == True)
            ).scalar() or 0
            
            # 市场数据统计
            market_total = session.execute(select(func.count(MarketStat.id))).scalar() or 0
            
            # 覆盖的州数
            states_count = session.execute(
                select(func.count(func.distinct(MarketStat.state)))
            ).scalar() or 0
            
            # 搜索历史统计
            history_total = session.execute(select(func.count(SearchHistory.id))).scalar() or 0
            
            # ETL任务统计
            task_total = session.execute(select(func.count(EtlJobRun.id))).scalar() or 0
            task_running = session.execute(
                select(func.count(EtlJobRun.id)).where(EtlJobRun.status == "running")
            ).scalar() or 0
            task_completed = session.execute(
                select(func.count(EtlJobRun.id)).where(EtlJobRun.status == "completed")
            ).scalar() or 0
            task_failed = session.execute(
                select(func.count(EtlJobRun.id)).where(EtlJobRun.status == "failed")
            ).scalar() or 0
            
            # 文档类型分布
            doc_type_dist = session.execute(
                select(
                    Document.doc_type,
                    func.count(Document.id).label("count")
                ).group_by(Document.doc_type)
            ).all()
            doc_type_distribution = {row.doc_type: row.count for row in doc_type_dist}
            
            # 结构化数据提取率
            doc_with_extracted = session.execute(
                select(func.count(Document.id)).where(
                    Document.extracted_data.isnot(None)
                )
            ).scalar() or 0
            extraction_rate = (doc_with_extracted / doc_total * 100) if doc_total > 0 else 0
            
            return {
                "documents": {
                    "total": doc_total,
                    "recent_today": doc_recent_today,
                    "recent_7d": doc_recent_7d,
                    "type_distribution": doc_type_distribution,
                    "extraction_rate": round(extraction_rate, 2),
                },
                "sources": {
                    "total": source_total,
                    "enabled": source_enabled,
                },
                "market_stats": {
                    "total": market_total,
                    "states_count": states_count,
                },
                "search_history": {
                    "total": history_total,
                },
                "tasks": {
                    "total": task_total,
                    "running": task_running,
                    "completed": task_completed,
                    "failed": task_failed,
                },
            }
    except (OperationalError, DatabaseError) as e:
        logger.exception("数据库连接失败")
        raise HTTPException(
            status_code=503,
            detail="数据库服务不可用，请检查数据库服务是否已启动。"
        )
    except Exception as e:
        logger.exception("获取仪表盘统计数据失败")
        error_msg = str(e)
        if "Connection" in error_msg or "db" in error_msg.lower() or "database" in error_msg.lower() or "postgres" in error_msg.lower() or "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail="数据库服务不可用，请检查数据库服务是否已启动。"
            )
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {error_msg}")


@router.get("/market-trends")
def get_market_trends(
    state: Optional[str] = Query(None, description="州过滤"),
    game: Optional[str] = Query(None, description="游戏类型过滤"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    period: str = Query("daily", pattern="^(daily|monthly)$", description="聚合周期"),
):
    """获取市场趋势数据"""
    with SessionLocal() as session:
        query = select(MarketStat)
        
        conditions = []
        if state:
            conditions.append(MarketStat.state == state.upper())
        if game:
            conditions.append(MarketStat.game.ilike(f"%{game}%"))
        if start_date:
            try:
                start = datetime.fromisoformat(start_date).date()
                conditions.append(MarketStat.date >= start)
            except Exception:
                pass
        if end_date:
            try:
                end = datetime.fromisoformat(end_date).date()
                conditions.append(MarketStat.date <= end)
            except Exception:
                pass
        
        if conditions:
            query = query.where(and_(*conditions))
        
        if period == "monthly":
            # 按月聚合
            rows = session.execute(
                select(
                    func.date_trunc("month", MarketStat.date).label("month"),
                    MarketStat.state,
                    MarketStat.game,
                    func.avg(MarketStat.revenue).label("avg_revenue"),
                    func.avg(MarketStat.sales_volume).label("avg_sales_volume"),
                    func.avg(MarketStat.jackpot).label("avg_jackpot"),
                    func.sum(MarketStat.revenue).label("total_revenue"),
                    func.sum(MarketStat.sales_volume).label("total_sales_volume"),
                )
                .where(and_(*conditions) if conditions else True)
                .group_by(
                    func.date_trunc("month", MarketStat.date),
                    MarketStat.state,
                    MarketStat.game,
                )
                .order_by(func.date_trunc("month", MarketStat.date))
            ).all()
            
            series = []
            for row in rows:
                series.append({
                    "date": row.month.date().isoformat() if row.month else None,
                    "state": row.state,
                    "game": row.game,
                    "revenue": _decimal_to_float(row.avg_revenue),
                    "sales_volume": _decimal_to_float(row.avg_sales_volume),
                    "jackpot": _decimal_to_float(row.avg_jackpot),
                    "total_revenue": _decimal_to_float(row.total_revenue),
                    "total_sales_volume": _decimal_to_float(row.total_sales_volume),
                })
        else:
            # 按日聚合
            rows = session.execute(
                query.order_by(MarketStat.date.asc())
            ).scalars().all()
            
            series = []
            for stat in rows:
                series.append({
                    "date": stat.date.isoformat() if stat.date else None,
                    "state": stat.state,
                    "game": stat.game,
                    "revenue": _decimal_to_float(stat.revenue),
                    "sales_volume": _decimal_to_float(stat.sales_volume),
                    "jackpot": _decimal_to_float(stat.jackpot),
                    "ticket_price": _decimal_to_float(stat.ticket_price),
                    "yoy": _decimal_to_float(stat.yoy),
                    "mom": _decimal_to_float(stat.mom),
                })
        
        # 州分布统计
        state_dist = session.execute(
            select(
                MarketStat.state,
                func.count(MarketStat.id).label("count"),
                func.sum(MarketStat.revenue).label("total_revenue"),
            )
            .where(and_(*conditions) if conditions else True)
            .group_by(MarketStat.state)
        ).all()
        state_distribution = [
            {
                "state": row.state,
                "count": row.count,
                "total_revenue": _decimal_to_float(row.total_revenue),
            }
            for row in state_dist
        ]
        
        # 游戏类型分布
        game_dist = session.execute(
            select(
                MarketStat.game,
                func.count(MarketStat.id).label("count"),
                func.avg(MarketStat.revenue).label("avg_revenue"),
            )
            .where(and_(*conditions) if conditions else True)
            .where(MarketStat.game.isnot(None))
            .group_by(MarketStat.game)
        ).all()
        game_distribution = [
            {
                "game": row.game,
                "count": row.count,
                "avg_revenue": _decimal_to_float(row.avg_revenue),
            }
            for row in game_dist
        ]
        
        return {
            "series": series,
            "state_distribution": state_distribution,
            "game_distribution": game_distribution,
            "period": period,
        }


@router.get("/document-analysis")
def get_document_analysis(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
):
    """获取文档分析数据"""
    with SessionLocal() as session:
        conditions = []
        if start_date:
            try:
                start = datetime.fromisoformat(start_date).date()
                conditions.append(func.date(Document.created_at) >= start)
            except Exception:
                pass
        if end_date:
            try:
                end = datetime.fromisoformat(end_date).date()
                conditions.append(func.date(Document.created_at) <= end)
            except Exception:
                pass
        
        # 文档类型分布
        type_query = select(
            Document.doc_type,
            func.count(Document.id).label("count")
        ).group_by(Document.doc_type)
        if conditions:
            type_query = type_query.where(and_(*conditions))
        type_dist = session.execute(type_query).all()
        type_distribution = [
            {"type": row.doc_type, "count": row.count}
            for row in type_dist
        ]
        
        # 文档增长趋势（按日期）
        growth_query = select(
            func.date(Document.created_at).label("date"),
            func.count(Document.id).label("count")
        ).group_by(func.date(Document.created_at))
        if conditions:
            growth_query = growth_query.where(and_(*conditions))
        growth_query = growth_query.order_by(func.date(Document.created_at))
        growth_data = session.execute(growth_query).all()
        growth_trend = [
            {
                "date": row.date.isoformat() if row.date else None,
                "count": row.count,
            }
            for row in growth_data
        ]
        
        # 州分布
        state_query = select(
            Document.state,
            func.count(Document.id).label("count")
        ).where(Document.state.isnot(None)).group_by(Document.state)
        if conditions:
            state_query = state_query.where(and_(*conditions))
        state_dist = session.execute(state_query).all()
        state_distribution = [
            {"state": row.state, "count": row.count}
            for row in state_dist
        ]
        
        # 数据源贡献度
        source_query = select(
            Source.name,
            Source.id,
            func.count(Document.id).label("count")
        ).join(Document, Source.id == Document.source_id, isouter=True)
        if conditions:
            source_query = source_query.where(and_(*conditions))
        source_query = source_query.group_by(Source.id, Source.name)
        source_dist = session.execute(source_query).all()
        source_contribution = [
            {"source_name": row.name or "未知", "count": row.count}
            for row in source_dist
        ]
        
        # 结构化数据提取率（按类型）
        extraction_query = select(
            Document.doc_type,
            func.count(Document.id).label("total"),
            func.sum(
                case((Document.extracted_data.isnot(None), 1), else_=0)
            ).label("with_extracted")
        ).group_by(Document.doc_type)
        if conditions:
            extraction_query = extraction_query.where(and_(*conditions))
        extraction_dist = session.execute(extraction_query).all()
        extraction_by_type = [
            {
                "type": row.doc_type,
                "total": row.total,
                "with_extracted": row.with_extracted,
                "rate": round((row.with_extracted / row.total * 100) if row.total > 0 else 0, 2),
            }
            for row in extraction_dist
        ]
        
        return {
            "type_distribution": type_distribution,
            "growth_trend": growth_trend,
            "state_distribution": state_distribution,
            "source_contribution": source_contribution,
            "extraction_by_type": extraction_by_type,
        }


@router.get("/sentiment-analysis")
def get_sentiment_analysis(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
):
    """获取社交媒体情感分析数据"""
    graph_doc_types = resolve_graph_doc_types()
    social_doc_types = graph_doc_types.get("social") or ["social_sentiment", "social_feed"]
    with SessionLocal() as session:
        conditions = [
            Document.doc_type.in_(social_doc_types),
            Document.extracted_data.isnot(None),
        ]
        
        if start_date:
            try:
                start = datetime.fromisoformat(start_date).date()
                # 使用发布时间过滤，如果没有发布时间则使用创建时间
                conditions.append(
                    or_(
                        Document.publish_date >= start,
                        and_(Document.publish_date.is_(None), func.date(Document.created_at) >= start)
                    )
                )
            except Exception:
                pass
        if end_date:
            try:
                end = datetime.fromisoformat(end_date).date()
                # 使用发布时间过滤，如果没有发布时间则使用创建时间
                conditions.append(
                    or_(
                        Document.publish_date <= end,
                        and_(Document.publish_date.is_(None), func.date(Document.created_at) <= end)
                    )
                )
            except Exception:
                pass
        
        query = select(Document).where(and_(*conditions))
        docs = session.execute(query).scalars().all()
        
        # 情感分布统计
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0, "unknown": 0}
        platform_counts = {}
        platform_sentiment = {}  # 每个平台的情感分布
        sentiment_trend = {}
        keyword_counts = {}  # 关键词统计
        
        for doc in docs:
            extracted = doc.extracted_data or {}
            sentiment = extracted.get("sentiment", {}).get("sentiment_orientation")
            if sentiment in ["positive", "negative", "neutral"]:
                sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
            else:
                sentiment_counts["unknown"] = sentiment_counts.get("unknown", 0) + 1
            
            # 平台统计
            platform = extracted.get("platform", "unknown")
            platform_counts[platform] = platform_counts.get(platform, 0) + 1
            
            # 平台情感分布统计
            if platform not in platform_sentiment:
                platform_sentiment[platform] = {"positive": 0, "negative": 0, "neutral": 0, "unknown": 0}
            if sentiment in ["positive", "negative", "neutral"]:
                platform_sentiment[platform][sentiment] = platform_sentiment[platform].get(sentiment, 0) + 1
            else:
                platform_sentiment[platform]["unknown"] = platform_sentiment[platform].get("unknown", 0) + 1
            
            # 情感趋势（按日期）- 使用发布时间，如果没有则使用创建时间
            date_for_trend = doc.publish_date if doc.publish_date else (doc.created_at.date() if doc.created_at else None)
            if date_for_trend:
                date_key = date_for_trend.isoformat() if isinstance(date_for_trend, date) else date_for_trend
                if date_key not in sentiment_trend:
                    sentiment_trend[date_key] = {"positive": 0, "negative": 0, "neutral": 0}
                if sentiment in ["positive", "negative", "neutral"]:
                    sentiment_trend[date_key][sentiment] = sentiment_trend[date_key].get(sentiment, 0) + 1
            
            # 关键词统计（从key_phrases、topic、sentiment_tags中提取）
            sentiment_data = extracted.get("sentiment", {})
            
            # 统计key_phrases
            key_phrases = sentiment_data.get("key_phrases", [])
            if isinstance(key_phrases, list):
                for phrase in key_phrases:
                    if phrase and isinstance(phrase, str):
                        phrase_lower = phrase.lower().strip()
                        if phrase_lower:
                            keyword_counts[phrase_lower] = keyword_counts.get(phrase_lower, 0) + 1
            
            # 统计topic
            topic = sentiment_data.get("topic", "")
            if topic and isinstance(topic, str):
                topic_lower = topic.lower().strip()
                if topic_lower:
                    keyword_counts[topic_lower] = keyword_counts.get(topic_lower, 0) + 1
            
            # 统计sentiment_tags
            sentiment_tags = sentiment_data.get("sentiment_tags", [])
            if isinstance(sentiment_tags, list):
                for tag in sentiment_tags:
                    if tag and isinstance(tag, str):
                        tag_lower = tag.lower().strip()
                        if tag_lower:
                            keyword_counts[tag_lower] = keyword_counts.get(tag_lower, 0) + 1
        
        # 转换趋势数据为列表格式
        trend_series = []
        for date_key in sorted(sentiment_trend.keys()):
            trend_series.append({
                "date": date_key,
                **sentiment_trend[date_key],
            })
        
        # 平台分布（包含情感数据）
        platform_distribution = []
        for platform, count in platform_counts.items():
            platform_distribution.append({
                "platform": platform,
                "count": count,
                "positive": platform_sentiment.get(platform, {}).get("positive", 0),
                "negative": platform_sentiment.get(platform, {}).get("negative", 0),
                "neutral": platform_sentiment.get(platform, {}).get("neutral", 0),
                "unknown": platform_sentiment.get(platform, {}).get("unknown", 0),
            })
        
        # 关键词排行（取前20个）
        keyword_ranking = sorted(
            keyword_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]
        keyword_ranking_list = [
            {"keyword": keyword, "count": count}
            for keyword, count in keyword_ranking
        ]
        
        return {
            "sentiment_distribution": sentiment_counts,
            "platform_distribution": platform_distribution,
            "sentiment_trend": trend_series,
            "keyword_ranking": keyword_ranking_list,
            "total_documents": len(docs),
        }


@router.get("/sentiment-sources")
def get_sentiment_sources(
    sentiment: Optional[str] = Query(None, description="情感类型: positive, negative, neutral, unknown"),
    platform: Optional[str] = Query(None, description="平台名称"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(default=50, ge=1, le=200, description="返回数量限制"),
):
    """根据筛选条件获取数据源列表"""
    graph_doc_types = resolve_graph_doc_types()
    social_doc_types = graph_doc_types.get("social") or ["social_sentiment", "social_feed"]
    with SessionLocal() as session:
        conditions = [
            Document.doc_type.in_(social_doc_types),
            Document.extracted_data.isnot(None),
        ]
        
        if start_date:
            try:
                start = datetime.fromisoformat(start_date).date()
                # 使用发布时间过滤，如果没有发布时间则使用创建时间
                conditions.append(
                    or_(
                        Document.publish_date >= start,
                        and_(Document.publish_date.is_(None), func.date(Document.created_at) >= start)
                    )
                )
            except Exception:
                pass
        if end_date:
            try:
                end = datetime.fromisoformat(end_date).date()
                # 使用发布时间过滤，如果没有发布时间则使用创建时间
                conditions.append(
                    or_(
                        Document.publish_date <= end,
                        and_(Document.publish_date.is_(None), func.date(Document.created_at) <= end)
                    )
                )
            except Exception:
                pass
        
        query = select(Document).where(and_(*conditions))
        docs = session.execute(query).scalars().all()
        
        # 根据情感和平台筛选
        filtered_docs = []
        for doc in docs:
            extracted = doc.extracted_data or {}
            doc_sentiment = extracted.get("sentiment", {}).get("sentiment_orientation")
            doc_platform = extracted.get("platform", "unknown")
            
            # 情感筛选
            if sentiment:
                if sentiment == "unknown":
                    if doc_sentiment not in ["positive", "negative", "neutral"]:
                        pass  # 匹配unknown
                    else:
                        continue
                elif doc_sentiment != sentiment:
                    continue
            
            # 平台筛选
            if platform and doc_platform != platform:
                continue
            
            filtered_docs.append(doc)
        
        # 限制数量
        filtered_docs = filtered_docs[:limit]
        
        # 构建返回数据
        sources = []
        for doc in filtered_docs:
            extracted = doc.extracted_data or {}
            sources.append({
                "id": doc.id,
                "title": doc.title or "无标题",
                "uri": doc.uri,
                "platform": extracted.get("platform", "unknown"),
                "sentiment": extracted.get("sentiment", {}).get("sentiment_orientation", "unknown"),
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "publish_date": doc.publish_date.isoformat() if doc.publish_date else None,
                "summary": doc.summary or "",
            })
        
        return {
            "sources": sources,
            "total": len(filtered_docs),
            "filters": {
                "sentiment": sentiment,
                "platform": platform,
                "start_date": start_date,
                "end_date": end_date,
            }
        }


@router.get("/task-monitoring")
def get_task_monitoring(
    limit: int = Query(default=50, ge=1, le=500),
    status: Optional[str] = Query(None, description="任务状态过滤"),
):
    """获取任务监控数据"""
    with SessionLocal() as session:
        query = select(EtlJobRun)
        
        if status:
            query = query.where(EtlJobRun.status == status)
        
        query = query.order_by(EtlJobRun.started_at.desc()).limit(limit)
        tasks = session.execute(query).scalars().all()
        
        # 任务类型分布
        type_query = select(
            EtlJobRun.job_type,
            func.count(EtlJobRun.id).label("count"),
            func.sum(
                case((EtlJobRun.status == "completed", 1), else_=0)
            ).label("completed"),
            func.sum(
                case((EtlJobRun.status == "failed", 1), else_=0)
            ).label("failed"),
        ).group_by(EtlJobRun.job_type)
        type_dist = session.execute(type_query).all()
        type_distribution = [
            {
                "job_type": row.job_type,
                "count": row.count,
                "completed": row.completed,
                "failed": row.failed,
            }
            for row in type_dist
        ]
        
        # 最近任务列表
        recent_tasks = []
        for task in tasks:
            duration = None
            if task.started_at and task.finished_at:
                duration = (task.finished_at - task.started_at).total_seconds()
            elif task.started_at:
                duration = (datetime.now(task.started_at.tzinfo) - task.started_at).total_seconds()
            
            recent_tasks.append({
                "id": task.id,
                "job_type": task.job_type,
                "status": task.status,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "finished_at": task.finished_at.isoformat() if task.finished_at else None,
                "duration_seconds": duration,
                "error": task.error,
            })
        
        return {
            "recent_tasks": recent_tasks,
            "type_distribution": type_distribution,
        }


@router.get("/search-analytics")
def get_search_analytics(limit: int = Query(default=50, ge=1, le=500)):
    """获取搜索行为分析数据"""
    with SessionLocal() as session:
        # 热门搜索主题
        query = select(SearchHistory).order_by(
            SearchHistory.last_search_time.desc()
        ).limit(limit)
        history = session.execute(query).scalars().all()
        
        # 统计每个主题的搜索次数（基于topic唯一性，实际是last_search_time）
        topic_counts = {}
        for h in history:
            topic_counts[h.topic] = topic_counts.get(h.topic, 0) + 1
        
        # 转换为列表并排序
        popular_topics = [
            {"topic": topic, "count": count}
            for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
        ]
        
        # 搜索频率趋势（按日期）
        trend_query = select(
            func.date(SearchHistory.last_search_time).label("date"),
            func.count(SearchHistory.id).label("count")
        ).group_by(func.date(SearchHistory.last_search_time)).order_by(
            func.date(SearchHistory.last_search_time)
        )
        trend_data = session.execute(trend_query).all()
        search_trend = [
            {
                "date": row.date.isoformat() if row.date else None,
                "count": row.count,
            }
            for row in trend_data
        ]
        
        return {
            "popular_topics": popular_topics[:20],  # 返回TOP 20
            "search_trend": search_trend,
        }


@router.get("/commodity-trends")
def get_commodity_trends(
    metric_key: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    period: str = Query("daily", pattern="^(daily|monthly)$"),
):
    with SessionLocal() as session:
        query = select(MarketMetricPoint)
        if metric_key:
            query = query.where(MarketMetricPoint.metric_key == metric_key)
        if start_date:
            try:
                query = query.where(MarketMetricPoint.date >= datetime.fromisoformat(start_date).date())
            except Exception:
                pass
        if end_date:
            try:
                query = query.where(MarketMetricPoint.date <= datetime.fromisoformat(end_date).date())
            except Exception:
                pass

        if period == "monthly":
            rows = session.execute(
                select(
                    func.date_trunc("month", MarketMetricPoint.date).label("month"),
                    MarketMetricPoint.metric_key,
                    func.avg(MarketMetricPoint.value).label("avg_value"),
                    func.count(MarketMetricPoint.id).label("count"),
                )
                .where(
                    MarketMetricPoint.metric_key == metric_key if metric_key else True
                )
                .group_by(func.date_trunc("month", MarketMetricPoint.date), MarketMetricPoint.metric_key)
                .order_by(func.date_trunc("month", MarketMetricPoint.date))
            ).all()
            series = [
                {
                    "date": row.month.date().isoformat() if row.month else None,
                    "metric_key": row.metric_key,
                    "value": _decimal_to_float(row.avg_value),
                    "count": row.count,
                }
                for row in rows
            ]
        else:
            rows = session.execute(query.order_by(MarketMetricPoint.date.asc())).scalars().all()
            series = [
                {
                    "date": row.date.isoformat() if row.date else None,
                    "metric_key": row.metric_key,
                    "value": _decimal_to_float(row.value),
                    "unit": row.unit,
                    "currency": row.currency,
                    "source_name": row.source_name,
                }
                for row in rows
            ]

        metric_distribution = session.execute(
            select(
                MarketMetricPoint.metric_key,
                func.count(MarketMetricPoint.id).label("count"),
            ).group_by(MarketMetricPoint.metric_key)
        ).all()

        return {
            "series": series,
            "metric_distribution": [
                {"metric_key": row.metric_key, "count": row.count}
                for row in metric_distribution
            ],
            "period": period,
        }


@router.get("/ecom-price-trends")
def get_ecom_price_trends(
    product_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None, description="开始时间 ISO8601"),
    end_date: Optional[str] = Query(None, description="结束时间 ISO8601"),
):
    with SessionLocal() as session:
        query = (
            select(PriceObservation, Product)
            .join(Product, Product.id == PriceObservation.product_id)
        )
        if product_id:
            query = query.where(PriceObservation.product_id == product_id)
        if start_date:
            try:
                query = query.where(PriceObservation.captured_at >= datetime.fromisoformat(start_date))
            except Exception:
                pass
        if end_date:
            try:
                query = query.where(PriceObservation.captured_at <= datetime.fromisoformat(end_date))
            except Exception:
                pass

        rows = session.execute(query.order_by(PriceObservation.captured_at.asc())).all()
        series = [
            {
                "product_id": p.id,
                "product_name": p.name,
                "captured_at": o.captured_at.isoformat() if o.captured_at else None,
                "price": _decimal_to_float(o.price),
                "currency": o.currency or p.currency,
                "availability": o.availability,
            }
            for o, p in rows
        ]

        product_distribution = session.execute(
            select(
                Product.id,
                Product.name,
                func.count(PriceObservation.id).label("count"),
                func.avg(PriceObservation.price).label("avg_price"),
            )
            .join(PriceObservation, PriceObservation.product_id == Product.id, isouter=True)
            .group_by(Product.id, Product.name)
        ).all()

        return {
            "series": series,
            "product_distribution": [
                {
                    "product_id": row.id,
                    "product_name": row.name,
                    "count": row.count,
                    "avg_price": _decimal_to_float(row.avg_price),
                }
                for row in product_distribution
            ],
        }

