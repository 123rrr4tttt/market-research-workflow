#!/usr/bin/env python3
"""修复市场文档中key_findings字段的中文内容，统一转换为英文"""

import sys
import os
import re
from pathlib import Path
from typing import List, Optional

# 添加项目根目录到路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# 设置环境变量（如果需要）
os.environ.setdefault("PYTHONPATH", str(backend_dir))

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.models.base import SessionLocal
from app.models.entities import Document
from app.services.llm.provider import get_chat_model
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def contains_chinese(text: str) -> bool:
    """检查文本是否包含中文字符"""
    if not text:
        return False
    # 检查是否包含中文字符（Unicode范围）
    chinese_pattern = re.compile(r'[\u4e00-\u9fff]+')
    return bool(chinese_pattern.search(text))


def translate_to_english(text: str) -> Optional[str]:
    """使用LLM将中文文本翻译为英文"""
    if not text or not contains_chinese(text):
        return text
    
    try:
        model = get_chat_model(temperature=0.2)
        prompt = f"""Translate the following Chinese text to English. Return only the English translation, without any explanation or additional text.

Chinese text: {text}

English translation:"""
        
        response = model.invoke(prompt)
        translated = response.content if hasattr(response, "content") else str(response)
        # 清理可能的markdown格式
        translated = translated.strip()
        if translated.startswith("```"):
            # 移除markdown代码块标记
            lines = translated.split("\n")
            translated = "\n".join([line for line in lines if not line.strip().startswith("```")])
        translated = translated.strip()
        return translated if translated else text
    except Exception as e:
        logger.warning(f"Translation failed for text '{text[:50]}...': {e}")
        return text


def fix_market_key_findings(dry_run: bool = True, limit: Optional[int] = None) -> dict:
    """
    修复市场文档中key_findings字段的中文内容
    
    Args:
        dry_run: 如果为True，只显示需要修复的文档，不实际更新
        limit: 限制处理的文档数量（用于测试）
    
    Returns:
        修复统计信息
    """
    stats = {
        "total_market_docs": 0,
        "docs_with_key_findings": 0,
        "docs_with_chinese": 0,
        "fixed_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
    }
    
    with SessionLocal() as session:
        try:
            # 查询所有市场文档
            query = select(Document).where(Document.doc_type == "market")
            if limit:
                query = query.limit(limit)
            
            documents = session.execute(query).scalars().all()
            stats["total_market_docs"] = len(documents)
            
            logger.info(f"找到 {stats['total_market_docs']} 个市场文档")
            
            for doc in documents:
                if not doc.extracted_data:
                    continue
                
                market_data = doc.extracted_data.get("market", {})
                if not market_data:
                    continue
                
                key_findings = market_data.get("key_findings", [])
                if not key_findings or not isinstance(key_findings, list):
                    continue
                
                stats["docs_with_key_findings"] += 1
                
                # 检查是否有中文
                has_chinese = False
                for finding in key_findings:
                    if contains_chinese(str(finding)):
                        has_chinese = True
                        break
                
                if not has_chinese:
                    continue
                
                stats["docs_with_chinese"] += 1
                logger.info(f"\n文档 ID: {doc.id}")
                logger.info(f"标题: {doc.title[:100] if doc.title else 'N/A'}")
                logger.info(f"原始 key_findings: {key_findings}")
                
                if dry_run:
                    logger.info("  [DRY RUN] 需要修复，但跳过实际更新")
                    stats["skipped_count"] += 1
                    continue
                
                # 翻译中文内容
                try:
                    translated_findings = []
                    for finding in key_findings:
                        finding_str = str(finding)
                        if contains_chinese(finding_str):
                            translated = translate_to_english(finding_str)
                            translated_findings.append(translated)
                            logger.info(f"  翻译: '{finding_str}' -> '{translated}'")
                        else:
                            translated_findings.append(finding_str)
                    
                    # 更新extracted_data
                    market_data["key_findings"] = translated_findings
                    doc.extracted_data["market"] = market_data
                    # 标记JSONB字段已修改，让SQLAlchemy检测到变化
                    flag_modified(doc, "extracted_data")
                    
                    session.add(doc)
                    stats["fixed_count"] += 1
                    logger.info(f"  ✅ 已修复文档 {doc.id}")
                    
                except Exception as e:
                    stats["failed_count"] += 1
                    logger.error(f"  ❌ 修复文档 {doc.id} 失败: {e}", exc_info=True)
            
            if not dry_run:
                session.commit()
                logger.info(f"\n✅ 已提交 {stats['fixed_count']} 个文档的更新")
            else:
                logger.info(f"\n[DRY RUN] 共找到 {stats['docs_with_chinese']} 个需要修复的文档")
            
        except Exception as e:
            session.rollback()
            logger.error(f"处理失败: {e}", exc_info=True)
            raise
    
    return stats


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="修复市场文档中key_findings字段的中文内容")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="只显示需要修复的文档，不实际更新（默认）"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际执行修复（需要明确指定）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制处理的文档数量（用于测试）"
    )
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    print("=" * 60)
    print("市场文档 key_findings 中文修复工具")
    print("=" * 60)
    print(f"模式: {'DRY RUN (预览模式)' if dry_run else 'EXECUTE (实际修复)'}")
    if args.limit:
        print(f"限制: 只处理前 {args.limit} 个文档")
    print("=" * 60)
    
    if dry_run:
        print("\n⚠️  这是预览模式，不会实际修改数据库")
        print("   如需实际修复，请使用 --execute 参数")
        print()
    
    stats = fix_market_key_findings(dry_run=dry_run, limit=args.limit)
    
    print("\n" + "=" * 60)
    print("修复统计:")
    print("=" * 60)
    print(f"总市场文档数: {stats['total_market_docs']}")
    print(f"包含key_findings的文档: {stats['docs_with_key_findings']}")
    print(f"包含中文的文档: {stats['docs_with_chinese']}")
    if not dry_run:
        print(f"成功修复: {stats['fixed_count']}")
        print(f"修复失败: {stats['failed_count']}")
    else:
        print(f"需要修复: {stats['docs_with_chinese']}")
        print(f"跳过（预览模式）: {stats['skipped_count']}")
    print("=" * 60)


if __name__ == "__main__":
    main()

