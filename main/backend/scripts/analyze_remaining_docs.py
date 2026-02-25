"""分析剩余缺少发布日期的文档"""
from __future__ import annotations

import sys
import os
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
os.environ.setdefault("PYTHONPATH", str(backend_dir))

from sqlalchemy import select
from app.models.base import SessionLocal
from app.models.entities import Document, Source
from collections import defaultdict

with SessionLocal() as session:
    query = select(Document, Source).join(
        Source, Document.source_id == Source.id, isouter=True
    ).where(Document.publish_date.is_(None))
    
    docs = session.execute(query).all()
    
    print("=" * 80)
    print(f"剩余 {len(docs)} 个文档缺少发布日期")
    print("=" * 80)
    
    # 分类
    pdf_files = []
    static_pages = []
    google_news = []
    other = []
    
    for doc, source in docs:
        uri_lower = (doc.uri or "").lower()
        
        if ".pdf" in uri_lower:
            pdf_files.append((doc, source.name if source else "未知"))
        elif "calottery.com" in uri_lower or "faq" in uri_lower or uri_lower.endswith("/"):
            static_pages.append((doc, source.name if source else "未知"))
        elif "google.com/rss" in uri_lower or "news.google" in uri_lower:
            google_news.append((doc, source.name if source else "未知"))
        else:
            other.append((doc, source.name if source else "未知"))
    
    print(f"\n【PDF文件】 ({len(pdf_files)}个)")
    for doc, source in pdf_files:
        print(f"  ID {doc.id}: {doc.title[:60] if doc.title else 'N/A'}...")
        print(f"    来源: {source}")
        print(f"    URL: {doc.uri[:80] if doc.uri else 'N/A'}...")
    
    print(f"\n【静态页面】 ({len(static_pages)}个)")
    for doc, source in static_pages:
        print(f"  ID {doc.id}: {doc.title[:60] if doc.title else 'N/A'}...")
        print(f"    来源: {source}")
        print(f"    URL: {doc.uri[:80] if doc.uri else 'N/A'}...")
    
    print(f"\n【Google News】 ({len(google_news)}个)")
    for doc, source in google_news:
        print(f"  ID {doc.id}: {doc.title[:60] if doc.title else 'N/A'}...")
        print(f"    来源: {source}")
        print(f"    URL: {doc.uri[:80] if doc.uri else 'N/A'}...")
    
    print(f"\n【其他】 ({len(other)}个)")
    for doc, source in other[:15]:
        print(f"  ID {doc.id}: {doc.title[:60] if doc.title else 'N/A'}...")
        print(f"    来源: {source}")
        print(f"    URL: {doc.uri[:80] if doc.uri else 'N/A'}...")
    
    # 按来源统计
    by_source = defaultdict(int)
    for doc, source in docs:
        by_source[source.name if source else "未知"] += 1
    
    print(f"\n按来源统计:")
    for source_name, count in sorted(by_source.items(), key=lambda x: x[1], reverse=True):
        print(f"  {source_name}: {count}个")
    
    print(f"\n按文档类型统计:")
    by_doc_type = defaultdict(int)
    for doc, source in docs:
        by_doc_type[doc.doc_type] += 1
    
    for doc_type, count in sorted(by_doc_type.items(), key=lambda x: x[1], reverse=True):
        print(f"  {doc_type}: {count}个")
    
    print(f"\n按文件类型:")
    print(f"  PDF: {len(pdf_files)}个")
    print(f"  静态页面: {len(static_pages)}个")
    print(f"  Google News: {len(google_news)}个")
    print(f"  其他: {len(other)}个")
