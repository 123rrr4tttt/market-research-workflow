"""检查指定创建日期的文档"""
from __future__ import annotations

import logging
from datetime import date, datetime
from sqlalchemy import select, func

from app.models.base import SessionLocal
from app.models.entities import Document

logger = logging.getLogger(__name__)


def check_created_date(target_date: date):
    """检查指定创建日期的文档"""
    with SessionLocal() as session:
        # 查找创建日期为指定日期的文档
        query = select(Document).where(
            func.date(Document.created_at) == target_date
        )
        
        docs = session.execute(query).scalars().all()
        
        print(f"=" * 60)
        print(f"创建日期为 {target_date} 的文档统计:")
        print(f"=" * 60)
        print(f"总计: {len(docs)} 个文档\n")
        
        # 按publish_date分组统计
        publish_date_stats = {}
        for doc in docs:
            pub_date = doc.publish_date
            if pub_date:
                key = str(pub_date)
            else:
                key = "NULL (将显示created_at)"
            
            if key not in publish_date_stats:
                publish_date_stats[key] = []
            publish_date_stats[key].append(doc)
        
        print("按publish_date分组:")
        for pub_date, doc_list in sorted(publish_date_stats.items()):
            print(f"\n  publish_date = {pub_date}: {len(doc_list)} 个文档")
            # 显示前5个示例
            for i, doc in enumerate(doc_list[:5], 1):
                print(f"    {i}. ID={doc.id}, title={doc.title[:60] if doc.title else 'N/A'}...")
            if len(doc_list) > 5:
                print(f"    ... 还有 {len(doc_list) - 5} 个文档")
        
        # 特别关注publish_date为NULL的文档（这些在前端会显示created_at）
        null_publish_date_docs = [d for d in docs if d.publish_date is None]
        if null_publish_date_docs:
            print(f"\n⚠️  有 {len(null_publish_date_docs)} 个文档的 publish_date 为 NULL")
            print("   这些文档在前端会显示 created_at 日期")
            print("\n前10个文档详情:")
            for i, doc in enumerate(null_publish_date_docs[:10], 1):
                print(f"  {i}. ID={doc.id}")
                print(f"     created_at={doc.created_at}")
                print(f"     publish_date={doc.publish_date}")
                print(f"     title={doc.title[:60] if doc.title else 'N/A'}...")
                print(f"     URL={doc.uri[:80] if doc.uri else 'N/A'}...")
                print()


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 默认检查2025-11-07
    target_date_str = "2025-11-07"
    
    if len(sys.argv) > 1:
        target_date_str = sys.argv[1]
    
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        check_created_date(target_date)
    except ValueError:
        print(f"无效的日期格式: {target_date_str}，请使用 YYYY-MM-DD 格式")
        sys.exit(1)

