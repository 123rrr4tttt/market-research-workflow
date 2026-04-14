#!/usr/bin/env python3
"""
一键修复社交内容文档的关键词大小写与去重问题（可选修复情感标签）

用法示例：
  # 试运行（不落库），查看将要修改的统计
  python3 scripts/normalize_social_keywords.py --dry-run

  # 真正执行（写回数据库）
  python3 scripts/normalize_social_keywords.py --commit

可选参数：
  --fix-tags        同时统一 sentiment.sentiment_tags 为小写并去重（默认开启）
  --limit N         只处理前 N 条（调试用）

注意：只处理 doc_type = 'social_sentiment' 且 extracted_data 非空的文档。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

# 将项目 backend 根目录加入 sys.path
import sys
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from sqlalchemy import select, and_  # type: ignore

from app.models.base import SessionLocal  # type: ignore
from app.models.entities import Document  # type: ignore


def normalize_list_lower_dedup(values: List[Any]) -> List[str]:
    """将字符串列表按小写去重，保留原始顺序。非字符串元素将被跳过。"""
    if not isinstance(values, list):
        return []
    seen = set()
    result: List[str] = []
    for v in values:
        if not isinstance(v, str):
            continue
        n = v.lower().strip()
        if not n or n in seen:
            continue
        seen.add(n)
        result.append(n)
    return result


def ensure_dict(obj: Any) -> Dict[str, Any]:
    """确保返回字典；如果是 JSON 字符串则尝试解析。失败返回空 dict。"""
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        try:
            return json.loads(obj)
        except Exception:
            return {}
    return {}


def process_document_payload(extracted: Dict[str, Any], *, fix_tags: bool = True) -> Tuple[Dict[str, Any], bool]:
    """
    处理单个 extracted_data，返回(新对象, 是否修改)。
    - 统一 keywords 为小写并去重
    - 可选：统一 sentiment.sentiment_tags 为小写并去重
    """
    changed = False
    new_extracted = dict(extracted)  # 浅拷贝

    # 处理 keywords（顶层）
    kws = new_extracted.get("keywords")
    if isinstance(kws, list):
        norm_kws = normalize_list_lower_dedup(kws)
        if norm_kws != kws:
            new_extracted["keywords"] = norm_kws
            changed = True

    # 处理 sentiment.sentiment_tags（可选）
    if fix_tags:
        sentiment = ensure_dict(new_extracted.get("sentiment"))
        tags = sentiment.get("sentiment_tags")
        if isinstance(tags, list):
            norm_tags = normalize_list_lower_dedup(tags)
            if norm_tags != tags:
                sentiment["sentiment_tags"] = norm_tags
                new_extracted["sentiment"] = sentiment
                changed = True

    return new_extracted, changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize social keywords/tags")
    parser.add_argument("--commit", action="store_true", help="写回数据库（默认不写）")
    parser.add_argument("--dry-run", action="store_true", help="试运行（打印统计，不写库）")
    parser.add_argument("--fix-tags", action="store_true", default=True, help="同时修复 sentiment_tags（默认开启）")
    parser.add_argument("--no-fix-tags", action="store_false", dest="fix_tags", help="不处理 sentiment_tags")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 条")
    parser.add_argument("--verbose", action="store_true", help="打印每条变更的前后对比")
    args = parser.parse_args()

    to_commit = args.commit and not args.dry_run

    updated = 0
    unchanged = 0
    processed = 0

    with SessionLocal() as session:
        stmt = select(Document).where(
            and_(Document.doc_type == "social_sentiment", Document.extracted_data.isnot(None))
        )
        if args.limit:
            stmt = stmt.limit(args.limit)
        docs = session.execute(stmt).scalars().all()

        for doc in docs:
            processed += 1
            extracted = ensure_dict(doc.extracted_data)
            if not extracted:
                unchanged += 1
                continue

            # 保留原字段用于对比
            old_keywords = extracted.get("keywords") if isinstance(extracted.get("keywords"), list) else None
            old_sentiment = ensure_dict(extracted.get("sentiment"))
            old_tags = old_sentiment.get("sentiment_tags") if isinstance(old_sentiment.get("sentiment_tags"), list) else None

            new_payload, changed = process_document_payload(extracted, fix_tags=args.fix_tags)
            if changed:
                doc.extracted_data = new_payload
                updated += 1
                if args.verbose:
                    new_keywords = new_payload.get("keywords") if isinstance(new_payload.get("keywords"), list) else None
                    new_sentiment = ensure_dict(new_payload.get("sentiment"))
                    new_tags = new_sentiment.get("sentiment_tags") if isinstance(new_sentiment.get("sentiment_tags"), list) else None
                    print(f"[变更] doc_id={doc.id}")
                    if old_keywords is not None or new_keywords is not None:
                        print(f"  keywords: {old_keywords} -> {new_keywords}")
                    if args.fix_tags and (old_tags is not None or new_tags is not None):
                        print(f"  sentiment_tags: {old_tags} -> {new_tags}")
            else:
                unchanged += 1

        if to_commit and updated > 0:
            session.commit()

    print(f"总计处理: {processed}")
    print(f"已修复:   {updated}")
    print(f"无变化:   {unchanged}")
    if to_commit:
        print("已写回数据库。")
    else:
        print("试运行完成（未写库）。要落库请加 --commit 并移除 --dry-run。")


if __name__ == "__main__":
    main()


