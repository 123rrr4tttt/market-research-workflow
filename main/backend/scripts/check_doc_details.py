"""检查文档的详细信息，尝试找到发布日期"""
from __future__ import annotations

import logging
import json
from datetime import date, datetime
from sqlalchemy import select, func

from app.models.base import SessionLocal
from app.models.entities import Document

logger = logging.getLogger(__name__)


def check_doc_details(target_date: date, limit: int = 10):
    """检查指定创建日期的文档详情"""
    with SessionLocal() as session:
        # 查找创建日期为指定日期且publish_date为NULL的文档
        query = select(Document).where(
            func.date(Document.created_at) == target_date,
            Document.publish_date.is_(None)
        ).limit(limit)
        
        docs = session.execute(query).scalars().all()
        
        print(f"=" * 60)
        print(f"检查创建日期为 {target_date} 且 publish_date 为 NULL 的文档")
        print(f"=" * 60)
        
        for i, doc in enumerate(docs, 1):
            print(f"\n文档 {i}: ID={doc.id}")
            print(f"  标题: {doc.title[:80] if doc.title else 'N/A'}...")
            print(f"  创建时间: {doc.created_at}")
            print(f"  URL: {doc.uri[:100] if doc.uri else 'N/A'}...")
            
            # 检查extracted_data
            if doc.extracted_data:
                print(f"  extracted_data 字段:")
                data = doc.extracted_data
                # 查找所有可能包含日期的字段
                date_fields = []
                for key in ['publish_date', 'published_date', 'date', 'timestamp', 
                           'created_time', 'effective_date', 'publication_date']:
                    if key in data:
                        date_fields.append(f"{key}={data[key]}")
                
                if date_fields:
                    print(f"    找到日期相关字段: {', '.join(date_fields)}")
                else:
                    print(f"    未找到日期相关字段")
                    # 显示extracted_data的结构
                    if isinstance(data, dict):
                        print(f"    可用字段: {', '.join(list(data.keys())[:10])}")
            
            # 检查content中是否有日期信息
            if doc.content:
                content_preview = doc.content[:200].replace('\n', ' ')
                print(f"  content 预览: {content_preview}...")
                # 尝试查找日期模式
                import re
                date_patterns = [
                    r'\d{4}-\d{2}-\d{2}',
                    r'\d{4}/\d{2}/\d{2}',
                    r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}',
                ]
                found_dates = []
                for pattern in date_patterns:
                    matches = re.findall(pattern, doc.content[:1000])
                    if matches:
                        found_dates.extend(matches[:3])  # 只取前3个
                
                if found_dates:
                    print(f"  在content中找到日期模式: {', '.join(set(found_dates))}")
            
            print("-" * 60)


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    target_date_str = "2025-11-07"
    limit = 10
    
    if len(sys.argv) > 1:
        target_date_str = sys.argv[1]
    if len(sys.argv) > 2:
        limit = int(sys.argv[2])
    
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        check_doc_details(target_date, limit)
    except ValueError:
        print(f"无效的日期格式: {target_date_str}，请使用 YYYY-MM-DD 格式")
        sys.exit(1)

