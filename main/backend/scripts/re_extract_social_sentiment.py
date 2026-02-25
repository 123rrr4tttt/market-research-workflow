#!/usr/bin/env python3
"""重新提取社交平台数据的sentiment、实体和关键词信息"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta
from typing import Optional
import logging
from sqlalchemy import select, and_

from app.models.base import SessionLocal
from app.models.entities import Document
from app.services.llm.extraction import extract_structured_sentiment
from app.services.extraction.extract import extract_entities_relations

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def re_extract_social_sentiment(
    days: int = 2,
    limit: Optional[int] = None,
    dry_run: bool = False,
    force: bool = False,
    extract_entities: bool = True,
    extract_keywords: bool = True
) -> dict:
    """
    重新提取社交平台数据的sentiment、实体和关键词信息
    
    Args:
        days: 检查最近几天的数据（默认2天）
        limit: 限制处理的文档数量（None表示不限制）
        dry_run: 是否为试运行（不实际更新数据库）
        force: 是否强制重新提取已有sentiment的数据
        extract_entities: 是否提取实体（默认True）
        extract_keywords: 是否提取关键词（默认True）
        
    Returns:
        包含统计信息的字典
    """
    with SessionLocal() as session:
        # 构建查询条件
        cutoff_date = datetime.now() - timedelta(days=days)
        conditions = [
            Document.doc_type == "social_sentiment",
            Document.created_at >= cutoff_date,
            Document.extracted_data.isnot(None)
        ]
        
        if not force:
            # 只处理没有sentiment字段的数据
            # 使用JSONB查询来检查sentiment字段是否存在
            conditions.append(
                ~Document.extracted_data.has_key("sentiment")
            )
        
        query = select(Document).where(and_(*conditions))
        
        if limit:
            query = query.limit(limit)
        
        docs = session.execute(query).scalars().all()
        
        logger.info(f"找到 {len(docs)} 条需要处理的文档")
        
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        for i, doc in enumerate(docs, 1):
            try:
                # 获取文本内容
                text = None
                if doc.extracted_data:
                    if isinstance(doc.extracted_data, dict):
                        text = doc.extracted_data.get("text")
                    elif isinstance(doc.extracted_data, str):
                        import json
                        try:
                            data = json.loads(doc.extracted_data)
                            text = data.get("text")
                        except:
                            pass
                
                # 如果没有text，尝试使用content或summary
                if not text:
                    text = doc.content or doc.summary or doc.title
                
                if not text or len(text.strip()) < 20:
                    logger.warning(f"文档 {doc.id} 文本太短，跳过")
                    skipped_count += 1
                    continue
                
                # 提取sentiment信息
                logger.info(f"[{i}/{len(docs)}] 处理文档 {doc.id}: {doc.title[:50] if doc.title else '无标题'}")
                sentiment_info = extract_structured_sentiment(text)
                
                # 确保extracted_data是字典格式
                if isinstance(doc.extracted_data, str):
                    import json
                    try:
                        doc.extracted_data = json.loads(doc.extracted_data)
                    except Exception as e:
                        logger.error(f"文档 {doc.id} 解析extracted_data失败: {e}")
                        error_count += 1
                        continue
                
                if not isinstance(doc.extracted_data, dict):
                    doc.extracted_data = {}
                
                updated = False
                
                # 更新sentiment信息
                if sentiment_info:
                    doc.extracted_data["sentiment"] = sentiment_info
                    updated = True
                    
                    # 从sentiment中提取keywords（使用key_phrases作为关键词）
                    if extract_keywords and sentiment_info.get("key_phrases"):
                        doc.extracted_data["keywords"] = sentiment_info["key_phrases"]
                        logger.debug(f"文档 {doc.id} 提取到 {len(sentiment_info['key_phrases'])} 个关键词")
                
                # 提取实体和关系（用于图谱构建）
                if extract_entities:
                    try:
                        er_data = extract_entities_relations(text)
                        if er_data and er_data.get("entities"):
                            doc.extracted_data["entities"] = er_data["entities"]
                            updated = True
                            logger.debug(f"文档 {doc.id} 提取到 {len(er_data['entities'])} 个实体")
                    except Exception as e:
                        logger.warning(f"文档 {doc.id} 提取实体失败: {e}")
                
                if updated:
                    # 标记字段已修改，让SQLAlchemy检测到变化
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(doc, "extracted_data")
                    
                    if not dry_run:
                        session.add(doc)
                        if i % 10 == 0:  # 每10条提交一次
                            session.commit()
                            logger.info(f"已提交 {i} 条记录")
                    
                    success_count += 1
                    logger.info(f"✓ 文档 {doc.id} 提取成功")
                else:
                    logger.warning(f"✗ 文档 {doc.id} 提取失败（未提取到任何信息）")
                    skipped_count += 1
                    
            except Exception as e:
                logger.error(f"处理文档 {doc.id} 时出错: {e}", exc_info=True)
                error_count += 1
        
        # 最终提交
        if not dry_run and success_count > 0:
            session.commit()
            logger.info(f"最终提交完成")
        
        return {
            "total": len(docs),
            "success": success_count,
            "error": error_count,
            "skipped": skipped_count,
        }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="重新提取社交平台数据的sentiment、实体和关键词信息")
    parser.add_argument("--days", type=int, default=2, help="检查最近几天的数据（默认2天）")
    parser.add_argument("--limit", type=int, default=None, help="限制处理的文档数量")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不实际更新数据库")
    parser.add_argument("--force", action="store_true", help="强制重新提取已有sentiment的数据")
    parser.add_argument("--no-entities", action="store_true", help="不提取实体")
    parser.add_argument("--no-keywords", action="store_true", help="不提取关键词")
    
    args = parser.parse_args()
    
    print(f"开始重新提取社交平台数据...")
    print(f"参数: days={args.days}, limit={args.limit}, dry_run={args.dry_run}, force={args.force}")
    print(f"提取选项: entities={not args.no_entities}, keywords={not args.no_keywords}")
    print("-" * 60)
    
    result = re_extract_social_sentiment(
        days=args.days,
        limit=args.limit,
        dry_run=args.dry_run,
        force=args.force,
        extract_entities=not args.no_entities,
        extract_keywords=not args.no_keywords
    )
    
    print("-" * 60)
    print(f"处理完成:")
    print(f"  总数: {result['total']}")
    print(f"  成功: {result['success']}")
    print(f"  错误: {result['error']}")
    print(f"  跳过: {result['skipped']}")
    
    if args.dry_run:
        print("\n注意: 这是试运行，数据库未实际更新")

