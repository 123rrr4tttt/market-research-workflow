"""市场数据适配器"""
from __future__ import annotations

import logging
from datetime import datetime

from ....models.entities import Material
from ..models import NormalizedMarketData
from ...extraction.numeric import normalize_market_payload, normalize_numeric_scalar
from ...document_views import (
    get_document_source_label,
    get_market_data,
    get_market_entities,
    has_structured_data,
)
from ..mapping import normalize_graph_json_object

logger = logging.getLogger(__name__)


class MarketAdapter:
    """市场数据适配器"""
    
    def to_normalized(self, doc: Material) -> NormalizedMarketData | None:
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
        if not has_structured_data(doc):
            return None
        
        market: dict[str, object] = dict(get_market_data(doc))
        
        # 提取基础字段
        raw_state = market.get("state")
        state = raw_state if isinstance(raw_state, str) else (doc.state or "")
        raw_game = market.get("game")
        game = raw_game if isinstance(raw_game, str) else None
        
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
                logger.warning(f"Material {doc.id} report_date parsing failed: {e}")
        
        if not date and doc.publish_date:
            if isinstance(doc.publish_date, datetime):
                date = doc.publish_date
            else:
                try:
                    date = datetime.combine(doc.publish_date, datetime.min.time())
                except Exception as e:
                    logger.warning(f"Material {doc.id} publish_date conversion failed: {e}")
        
        try:
            market, market_quality = normalize_market_payload(market, scope="market")
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
        source_name = get_document_source_label(doc)
        
        # 提取实体信息
        entities = get_market_entities(doc)
        
        return NormalizedMarketData(
            stat_id=doc.id,
            state=state,
            game=game,
            date=date,
            sales_volume=normalize_numeric_scalar(market.get("sales_volume")),
            revenue=normalize_numeric_scalar(market.get("revenue")),
            jackpot=normalize_numeric_scalar(market.get("jackpot")),
            ticket_price=normalize_numeric_scalar(market.get("ticket_price")),
            source_name=source_name,
            source_uri=doc.uri,
            title=doc.title,
            entities=[normalize_graph_json_object(entity) for entity in entities],
        )
