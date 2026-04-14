#!/usr/bin/env python
"""
删除数据库中所有带有中国区域信息的政策文档。

默认执行“预览”模式（只打印命中记录，不删除），
通过 --apply 明确确认后才会真正删除。

使用方法：
  python scripts/remove_cn_policy_docs.py            # 仅预览
  python scripts/remove_cn_policy_docs.py --apply    # 真正删除
"""
from __future__ import annotations

import argparse
import re
from typing import Iterable, List

from sqlalchemy import and_, cast, or_, String

from app.models.base import SessionLocal
from app.models.entities import Document


# 常见的中国省级行政区名称（可根据需要扩充）
CHINA_REGIONS: List[str] = [
    "北京",
    "天津",
    "河北",
    "山西",
    "内蒙古",
    "辽宁",
    "吉林",
    "黑龙江",
    "上海",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "重庆",
    "四川",
    "贵州",
    "云南",
    "西藏",
    "陕西",
    "甘肃",
    "青海",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
    "台湾",
]

# 额外关键词
CHINA_KEYWORDS: List[str] = [
    "中国",
    "中华人民共和国",
    "中华人民共和國",
    "PRC",
]


CHINESE_CHAR_PATTERN = re.compile(r"[^\x00-\x7F]")


def contains_chinese(text: str | None) -> bool:
    if not text:
        return False
    return bool(CHINESE_CHAR_PATTERN.search(text))


def build_query(session):
    """构建筛选包含中国区域或中文正文的政策文档的查询。"""
    json_state = cast(Document.extracted_data["policy"]["state"], String)
    region_conditions = []

    for region in CHINA_REGIONS + CHINA_KEYWORDS:
        region_conditions.append(Document.state.ilike(f"%{region}%"))
        region_conditions.append(json_state.ilike(f"%{region}%"))

    content_condition = and_(
        Document.content.isnot(None),
        Document.content.op("~")(r"[^\x00-\x7F]"),
    )

    return (
        session.query(Document)
        .filter(
            and_(
                Document.doc_type.in_(["policy", "policy_regulation"]),
                or_(or_(*region_conditions), content_condition),
            )
        )
        .order_by(Document.id.asc())
    )


def dry_run(documents: Iterable[Document]) -> int:
    """打印命中的文档信息（预览模式）。"""
    count = 0
    print("📝 预览模式：以下文档将被删除（未执行删除）")
    print("-" * 80)
    for doc in documents:
        count += 1
        extracted_state = (doc.extracted_data or {}).get("policy", {}).get("state")
        has_cn_body = contains_chinese(doc.content)
        print(
            f"ID={doc.id}  state={doc.state!r}  extracted_state={extracted_state!r}  "
            f"title={doc.title!r}  body_has_cn={has_cn_body}"
        )
    print("-" * 80)
    print(f"共匹配到 {count} 条文档。")
    return count


def delete_documents(documents: Iterable[Document], session) -> int:
    """删除命中的文档。"""
    count = 0
    ids_to_delete: List[int] = []
    for doc in documents:
        ids_to_delete.append(doc.id)
        count += 1

    if not ids_to_delete:
        return 0

    session.query(Document).filter(Document.id.in_(ids_to_delete)).delete(
        synchronize_session=False
    )
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="删除中国相关政策文档")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行删除；未提供该参数时仅预览",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        query = build_query(session)
        documents = list(query)

        if not documents:
            print("✅ 未发现中国相关的政策文档，无需删除。")
            return

        if not args.apply:
            dry_run(documents)
            print("ℹ️  如需删除，请运行：python scripts/remove_cn_policy_docs.py --apply")
            return

        deleted = delete_documents(documents, session)
        session.commit()
        print(f"✅ 已删除 {deleted} 条中国相关的政策文档。")


if __name__ == "__main__":
    main()

