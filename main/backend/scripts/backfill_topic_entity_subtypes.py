#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import select  # noqa: E402

from app.models.base import SessionLocal  # noqa: E402
from app.models.entities import Document  # noqa: E402
from app.services.projects.context import bind_project  # noqa: E402


TOPIC_FIELDS = {
    "company": "company_structured",
    "product": "product_structured",
    "operation": "operation_structured",
}

ALLOWED_TYPES = {
    "company": {"company", "brand", "business_unit", "partner", "channel"},
    "product": {"product", "model", "category", "brand", "component", "scenario"},
    "operation": {"operation_subject", "platform", "store", "channel", "metric", "strategy", "region", "period"},
}


def _s(v: Any) -> str:
    return str(v or "").strip()


def _sl(v: Any) -> str:
    return _s(v).lower()


def infer_company_type(text: str, old_type: str) -> str:
    t = _sl(text)
    ot = _sl(old_type)
    if ot in ALLOWED_TYPES["company"]:
        return ot
    if ot in {"organization", "org", "institution", "community", "user"}:
        return "company"
    if ot in {"person", "founder", "ceo"}:
        return "partner"
    if ot in {"brand"}:
        return "brand"
    if any(k in t for k in ["品牌", "brand"]):
        return "brand"
    if any(k in t for k in ["渠道", "channel", "dealer", "distributor", "经销"]):
        return "channel"
    if any(k in t for k in ["事业部", "业务线", "department", "division", "unit"]):
        return "business_unit"
    if any(k in t for k in ["合作方", "partner", "供应商", "supplier"]):
        return "partner"
    return "company"


def infer_product_type(text: str, old_type: str) -> str:
    t = _sl(text)
    ot = _sl(old_type)
    if ot in ALLOWED_TYPES["product"]:
        return ot
    if ot in {"technology", "application", "program", "service"}:
        if ot == "application":
            return "scenario"
        if ot == "technology":
            return "component"
        return "product"
    if ot in {"brand", "company"}:
        return "brand"
    if any(k in t for k in ["型号", "model", "series", "版本", "pro", "mini", "max"]):
        return "model"
    if any(k in t for k in ["组件", "模组", "电机", "减速器", "传感器", "控制器", "芯片", "controller", "motor", "sensor", "actuator", "battery"]):
        return "component"
    if any(k in t for k in ["场景", "应用", "物流", "仓储", "工业", "教育", "家用", "医疗", "scenario"]):
        return "scenario"
    if any(k in t for k in ["品类", "category", "机器人", "robot", "机械臂", "arm"]):
        return "category" if "category" in t or "品类" in t else "product"
    return "product"


def infer_operation_type(text: str, old_type: str) -> str:
    t = _sl(text)
    ot = _sl(old_type)
    if ot in ALLOWED_TYPES["operation"]:
        return ot
    if ot in {"company", "organization", "institution"}:
        return "operation_subject"
    if ot in {"industry", "market", "application", "technology", "program", "service", "topic"}:
        return "strategy" if ot in {"strategy", "program"} else "operation_subject"
    if any(k in t for k in ["amazon", "taobao", "jd", "tiktok shop", "shopify", "平台", "platform", "marketplace"]):
        return "platform"
    if any(k in t for k in ["店铺", "shop", "store", "旗舰店"]):
        return "store"
    if any(k in t for k in ["渠道", "channel", "分销", "dealer", "经销"]):
        return "channel"
    if any(k in t for k in ["gmv", "roi", "cac", "转化", "销量", "客单", "收入", "利润", "成本", "metric", "率", "%"]):
        return "metric"
    if any(k in t for k in ["策略", "促销", "投放", "定价", "补贴", "运营模式", "经营模式", "strategy", "pricing", "campaign"]):
        return "strategy"
    if any(k in t for k in ["中国", "美国", "欧洲", "亚太", "region", "地区", "区域"]):
        return "region"
    if re.search(r"\b20\d{2}\b", t) or any(k in t for k in ["季度", "q1", "q2", "q3", "q4", "month", "year", "202", "period"]):
        return "period"
    return "operation_subject"


INFER_FN = {
    "company": infer_company_type,
    "product": infer_product_type,
    "operation": infer_operation_type,
}


def normalize_topic_field(topic: str, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    changed = Counter()
    out = copy.deepcopy(payload)
    entities = out.get("entities")
    if not isinstance(entities, list):
        return out, changed

    infer = INFER_FN[topic]
    text_to_type: dict[str, str] = {}
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        text = _s(ent.get("text") or ent.get("name"))
        old_type = _s(ent.get("type"))
        new_type = infer(text, old_type)
        if new_type and new_type != _sl(old_type):
            ent["type"] = new_type
            changed["entity_type_updates"] += 1
            changed[f"entity_type_to::{new_type}"] += 1
        elif old_type and old_type != _sl(old_type):
            ent["type"] = _sl(old_type)
            changed["entity_type_normalized_case"] += 1
        if text:
            text_to_type[text.lower()] = _sl(ent.get("type"))

    relations = out.get("relations")
    if isinstance(relations, list):
        for rel in relations:
            if not isinstance(rel, dict):
                continue
            subj = _sl(rel.get("subject") or rel.get("subject_text"))
            obj = _sl(rel.get("object") or rel.get("object_text"))
            if subj and subj in text_to_type:
                if _sl(rel.get("subject_type")) != text_to_type[subj]:
                    rel["subject_type"] = text_to_type[subj]
                    changed["relation_subject_type_updates"] += 1
            if obj and obj in text_to_type:
                if _sl(rel.get("object_type")) != text_to_type[obj]:
                    rel["object_type"] = text_to_type[obj]
                    changed["relation_object_type_updates"] += 1
    return out, changed


def process_documents(project_key: str, topics: list[str], limit: int | None, dry_run: bool, batch_size: int) -> dict[str, Any]:
    summary = {
        "project_key": project_key,
        "topics": topics,
        "dry_run": dry_run,
        "docs_scanned": 0,
        "docs_updated": 0,
        "topic_updates": {t: 0 for t in topics},
        "changes": {},
    }
    change_counter = Counter()
    topic_fields = [TOPIC_FIELDS[t] for t in topics]

    with bind_project(project_key):
        with SessionLocal() as session:
            q = select(Document).where(Document.extracted_data.isnot(None)).order_by(Document.id.asc())
            if limit:
                q = q.limit(limit)
            docs = session.execute(q).scalars().all()
            summary["docs_scanned"] = len(docs)
            dirty_count = 0
            for idx, doc in enumerate(docs, start=1):
                ex = doc.extracted_data if isinstance(doc.extracted_data, dict) else None
                if not ex:
                    continue
                new_ex = copy.deepcopy(ex)
                doc_changed = False
                for topic in topics:
                    field = TOPIC_FIELDS[topic]
                    payload = new_ex.get(field)
                    if not isinstance(payload, dict):
                        continue
                    normalized, ch = normalize_topic_field(topic, payload)
                    if ch:
                        new_ex[field] = normalized
                        doc_changed = True
                        summary["topic_updates"][topic] += 1
                        for k, v in ch.items():
                            change_counter[f"{topic}:{k}"] += v
                if doc_changed:
                    dirty_count += 1
                    summary["docs_updated"] += 1
                    if not dry_run:
                        doc.extracted_data = new_ex
                if not dry_run and dirty_count and (dirty_count % max(1, batch_size) == 0):
                    session.commit()
            if not dry_run:
                session.commit()
    summary["changes"] = dict(change_counter.most_common())
    return summary


def main():
    parser = argparse.ArgumentParser(description="Backfill topic entity subtypes for company/product/operation structured fields")
    parser.add_argument("--project-key", default="demo_proj")
    parser.add_argument("--topics", default="company,product,operation", help="comma separated: company,product,operation")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--apply", action="store_true", help="apply changes (default dry-run)")
    args = parser.parse_args()

    topics = [t.strip() for t in (args.topics or "").split(",") if t.strip() in TOPIC_FIELDS]
    if not topics:
        raise SystemExit("No valid topics specified")
    result = process_documents(
        project_key=args.project_key,
        topics=topics,
        limit=args.limit or None,
        dry_run=(not args.apply),
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

