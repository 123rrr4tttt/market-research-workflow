"""智能搜索模块：自动增量搜索"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional
import logging

from .web import search_sources
from .history import get_last_search_time, update_search_time


logger = logging.getLogger(__name__)


def smart_search(topic: str, days_back: int = 30, max_results: int = 10, language: str = "en", provider: str = "auto") -> List[dict]:
    """智能搜索：自动判断是否增量，只返回新信息
    
    Args:
        topic: 搜索主题
        days_back: 首次搜索时，回溯多少天（默认30天）
        max_results: 最大结果数
        language: 语言
        provider: 搜索服务提供商
    
    Returns:
        搜索结果列表
    """
    # 1. 检查上次搜索时间
    last_time = get_last_search_time(topic)
    
    # 2. 确定搜索范围
    if last_time:
        # 增量搜索：计算距离上次搜索的天数
        now = datetime.now()
        # 处理时区：如果last_time有时区信息，转换为naive datetime
        if last_time.tzinfo:
            last_time_naive = last_time.replace(tzinfo=None)
        else:
            last_time_naive = last_time
        days_since = (now - last_time_naive).days
        if days_since > 0:
            logger.info("smart_search: incremental search topic=%s days_since=%d", topic, days_since)
            # 只搜索上次搜索后的新内容
            results = search_sources(
                topic=topic,
                language=language,
                max_results=max_results,
                provider=provider,
                days_back=min(days_since, days_back),
                exclude_existing=True,
            )
        else:
            # 同一天内搜索，返回空结果避免重复
            logger.info("smart_search: skipped (same day) topic=%s", topic)
            results = []
    else:
        # 首次搜索
        logger.info("smart_search: first search topic=%s days_back=%d", topic, days_back)
        results = search_sources(
            topic=topic,
            language=language,
            max_results=max_results,
            provider=provider,
            days_back=days_back,
            exclude_existing=True,
        )
    
    # 3. 更新搜索历史
    if results:
        update_search_time(topic)
    
    return results

