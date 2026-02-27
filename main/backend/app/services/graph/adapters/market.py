"""市场数据适配器"""
from __future__ import annotations

import logging
from typing import Optional
from datetime import datetime

from ....models.entities import Document
from ..models import NormalizedMarketData
from ...extraction.numeric import normalize_market_payload

logger = logging.getLogger(__name__)


class MarketAdapter:
    """市场数据适配器"""
    
    def to_normalized(self, doc: Document) -> Optional[NormalizedMarketData]:
        """
        将市场文档转换为规范化格式
        
        字段映射规则：
        - doc_id: doc.id
        - state: extracted_data.market.state 或 doc.state
        - game: extracted_data.market.game
        - date: extracted_data.market.report_date 或 doc.publish_date
        - sales_volume: extracted_data.market.sales_volume
        - revenue: extracted_data.market.revenue
        - jackpot: extracted_data.market.jackpot
        - ticket_price: extracted_data.market.ticket_price
        - source_name: doc.source.name (如果存在)
        - source_uri: doc.uri
        """
        if not doc.extracted_data:
            return None
        
        extracted = doc.extracted_data
        market = extracted.get("market", {})

        # For project-customized pipelines (e.g. demo_proj), "market" docs may come
        # from normalized news/social sources without extracted_data.market.
        # Build a minimal market view from document metadata to keep graph usable.
        if not market:
            fallback_state = (
                (doc.state or "").strip()
                or str(extracted.get("state") or "").strip()
                or "NA"
            )
            fallback_game = (
                str(extracted.get("keyword") or "").strip()
                or str(extracted.get("topic") or "").strip()
                or str(extracted.get("source") or "").strip()
                or "general"
            )
            market = {
                "state": fallback_state,
                "game": fallback_game,
                "report_date": doc.publish_date.isoformat() if doc.publish_date else None,
            }
        
        # 提取基础字段
        state = market.get("state") or doc.state or ""
        game = market.get("game")
        
        # 处理日期
        date = None
        report_date = market.get("report_date")
        if report_date:
            try:
                if isinstance(report_date, str):
                    date = datetime.fromisoformat(report_date.replace('Z', '+00:00'))
                elif isinstance(report_date, datetime):
                    date = report_date
            except Exception as e:
                logger.warning(f"Document {doc.id} report_date parsing failed: {e}")
        
        if not date and doc.publish_date:
            if isinstance(doc.publish_date, datetime):
                date = doc.publish_date
            else:
                try:
                    date = datetime.combine(doc.publish_date, datetime.min.time())
                except Exception as e:
                    logger.warning(f"Document {doc.id} publish_date conversion failed: {e}")
        
        try:
            market, market_quality = normalize_market_payload(market, scope="lottery.market")
            if market_quality:
                market["_numeric_quality"] = market_quality
        except Exception as e:
            logger.warning("MarketAdapter.to_normalized: normalize_market_payload failed: %s", e)
            market_quality = None

        if market_quality:
            market["_numeric_quality"] = market_quality

        # 获取数据源名称
        # Avoid lazy-loading doc.source here: imported demo schemas may not include sources table,
        # and a single UndefinedTable can poison the whole transaction.
        source_name = (
            str(extracted.get("platform") or "").strip()
            or str(extracted.get("source") or "").strip()
            or None
        )
        
        # 提取实体信息
        entities_relations = extracted.get("entities_relations", {})
        entities = entities_relations.get("entities", []) if isinstance(entities_relations, dict) else []
        
        return NormalizedMarketData(
            stat_id=doc.id,
            state=state,
            game=game,
            date=date,
            sales_volume=market.get("sales_volume"),
            revenue=market.get("revenue"),
            jackpot=market.get("jackpot"),
            ticket_price=market.get("ticket_price"),
            source_name=source_name,
            source_uri=doc.uri,
            title=doc.title,
            entities=entities or [],
        )
