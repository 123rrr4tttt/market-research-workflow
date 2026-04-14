#!/usr/bin/env python3
"""清理重复的社交平台数据"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta
from typing import Optional
import logging
from sqlalchemy import select, and_, func
from collections import defaultdict

from app.models.base import SessionLocal
from app.models.entities import Document

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def remove_duplicate_social_data(
    days: Optional[int] = None,
    dry_run: bool = True,
    keep_newer: bool = True
) -> dict:
    """
    清理重复的社交平台数据
    
    Args:
        days: 检查最近几天的数据（None表示检查所有）
        dry_run: 是否为试运行（不实际删除）
        keep_newer: 是否保留较新的记录（True保留新的，False保留旧的）
        
    Returns:
        包含统计信息的字典
    """
    with SessionLocal() as session:
        # 构建查询条件
        conditions = [
            Document.doc_type == "social_sentiment",
            Document.uri.isnot(None)
        ]
        
        if days:
            cutoff_date = datetime.now() - timedelta(days=days)
            conditions.append(Document.created_at >= cutoff_date)
        
        query = select(Document).where(and_(*conditions)).order_by(Document.uri, Document.created_at)
        docs = session.execute(query).scalars().all()
        
        logger.info(f"找到 {len(docs)} 条文档")
        
        # 按URI分组
        uri_groups = defaultdict(list)
        for doc in docs:
            if doc.uri:
                uri_groups[doc.uri].append(doc)
        
        # 找出重复的URI
        duplicates = {uri: group for uri, group in uri_groups.items() if len(group) > 1}
        
        logger.info(f"发现 {len(duplicates)} 个重复的URI")
        
        to_delete = []
        kept_count = 0
        
        for uri, group in duplicates.items():
            # 按创建时间排序
            group_sorted = sorted(group, key=lambda d: d.created_at or datetime.min, reverse=keep_newer)
            
            # 保留第一条（最新的或最旧的）
            keep_doc = group_sorted[0]
            delete_docs = group_sorted[1:]
            
            to_delete.extend(delete_docs)
            kept_count += 1
            
            logger.info(f"URI: {uri[:80]}...")
            logger.info(f"  保留: 文档ID={keep_doc.id}, 创建时间={keep_doc.created_at}")
            logger.info(f"  删除: {[doc.id for doc in delete_docs]}")
        
        if not dry_run and to_delete:
            # 删除重复记录
            delete_ids = [doc.id for doc in to_delete]
            deleted = session.query(Document).filter(Document.id.in_(delete_ids)).delete(synchronize_session=False)
            session.commit()
            logger.info(f"已删除 {deleted} 条重复记录")
        else:
            logger.info(f"试运行模式：将删除 {len(to_delete)} 条重复记录")
        
        return {
            "total": len(docs),
            "unique_uris": len(uri_groups),
            "duplicate_uris": len(duplicates),
            "to_delete": len(to_delete),
            "kept": kept_count,
            "deleted": len(to_delete) if not dry_run else 0,
        }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="清理重复的社交平台数据")
    parser.add_argument("--days", type=int, default=None, help="检查最近几天的数据（默认检查所有）")
    parser.add_argument("--dry-run", action="store_true", default=True, help="试运行，不实际删除（默认）")
    parser.add_argument("--execute", action="store_true", help="实际执行删除（覆盖dry-run）")
    parser.add_argument("--keep-older", action="store_true", help="保留较旧的记录（默认保留较新的）")
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    print(f"开始清理重复的社交平台数据...")
    print(f"参数: days={args.days or '全部'}, dry_run={dry_run}, keep_newer={not args.keep_older}")
    print("-" * 60)
    
    result = remove_duplicate_social_data(
        days=args.days,
        dry_run=dry_run,
        keep_newer=not args.keep_older
    )
    
    print("-" * 60)
    print(f"处理完成:")
    print(f"  总文档数: {result['total']}")
    print(f"  唯一URI数: {result['unique_uris']}")
    print(f"  重复URI数: {result['duplicate_uris']}")
    print(f"  将删除: {result['to_delete']} 条")
    print(f"  保留: {result['kept']} 条")
    
    if dry_run:
        print("\n注意: 这是试运行，数据库未实际更新")
        print("使用 --execute 参数来实际执行删除")

