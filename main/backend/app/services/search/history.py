"""搜索历史管理模块"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
import logging

from sqlalchemy import select
from ...models.base import SessionLocal
from ...models.entities import SearchHistory


logger = logging.getLogger(__name__)


def get_last_search_time(topic: str) -> Optional[datetime]:
    """获取指定主题的上次搜索时间"""
    with SessionLocal() as session:
        history = session.execute(
            select(SearchHistory).where(SearchHistory.topic == topic)
        ).scalar_one_or_none()
        return history.last_search_time if history else None


def update_search_time(topic: str) -> None:
    """更新或创建搜索历史记录"""
    with SessionLocal() as session:
        history = session.execute(
            select(SearchHistory).where(SearchHistory.topic == topic)
        ).scalar_one_or_none()
        
        if history:
            history.last_search_time = datetime.now()
        else:
            history = SearchHistory(topic=topic, last_search_time=datetime.now())
            session.add(history)
        
        session.commit()
        logger.info("search_history: updated topic=%s time=%s", topic, history.last_search_time)

