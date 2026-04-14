"""检查数据库中发布日期的分布情况"""
from __future__ import annotations

import logging
from datetime import date
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.models.base import SessionLocal
from app.models.entities import Document

logger = logging.getLogger(__name__)


def check_date_distribution():
    """检查发布日期的分布情况"""
    with SessionLocal() as session:
        # 查找所有有发布日期的文档，按日期分组统计
        query = select(
            Document.publish_date,
            func.count(Document.id).label('count')
        ).where(
            Document.publish_date.isnot(None)
        ).group_by(
            Document.publish_date
        ).order_by(
            Document.publish_date.desc()
        )
        
        results = session.execute(query).all()
        
        print("=" * 60)
        print("发布日期分布统计:")
        print("=" * 60)
        
        total = 0
        for publish_date, count in results:
            total += count
            print(f"{publish_date}: {count} 个文档")
        
        print("=" * 60)
        print(f"总计: {total} 个文档有发布日期")
        
        # 检查2025-11-16的数据
        target_date = date(2025, 11, 16)
        query_target = select(Document).where(Document.publish_date == target_date)
        docs_target = session.execute(query_target).scalars().all()
        
        print(f"\n2025-11-16 的数据: {len(docs_target)} 个文档")
        if len(docs_target) > 0:
            print("\n前10个文档:")
            for i, doc in enumerate(docs_target[:10], 1):
                print(f"  {i}. ID={doc.id}, created_at={doc.created_at.date()}, "
                      f"publish_date={doc.publish_date}, URL={doc.uri[:80] if doc.uri else 'N/A'}...")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    check_date_distribution()

