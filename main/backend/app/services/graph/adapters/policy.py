"\"\"\"政策数据适配器\"\"\""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from ....models.entities import Document
from ..models import NormalizedPolicyData

logger = logging.getLogger(__name__)


def _to_datetime(value: Any) -> Optional[datetime]:
    """将日期/时间值转换为datetime对象"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("无法解析日期字符串 %s: %s", value, exc)
            return None
    return None


class PolicyAdapter:
    """政策数据适配器"""

    def to_normalized(self, doc: Document) -> Optional[NormalizedPolicyData]:
        if not doc.extracted_data:
            logger.debug("Document %s 缺少 extracted_data，跳过", doc.id)
            return None

        extracted = doc.extracted_data
        policy_data: Dict[str, Any] = extracted.get("policy") or {}

        # 如果既没有 policy 数据也没有基本信息，则跳过
        if not policy_data and doc.doc_type not in ("policy", "policy_regulation"):
            logger.debug("Document %s doc_type=%s，非政策文档", doc.id, doc.doc_type)
            return None

        state = (policy_data.get("state") or doc.state or "").strip() or None
        policy_type = (policy_data.get("policy_type") or "").strip() or None

        key_points_raw = policy_data.get("key_points") or []
        key_points: List[str] = []
        if isinstance(key_points_raw, list):
            for item in key_points_raw[:5]:
                if isinstance(item, str):
                    cleaned = item.strip()
                    if cleaned:
                        key_points.append(cleaned)

        entities_relations = extracted.get("entities_relations", {}) or {}
        entities = []
        relations = []
        if isinstance(entities_relations, dict):
            ent_list = entities_relations.get("entities")
            if isinstance(ent_list, list):
                entities = [e for e in ent_list if isinstance(e, dict)]
            rel_list = entities_relations.get("relations")
            if isinstance(rel_list, list):
                relations = [r for r in rel_list if isinstance(r, dict)]

        publish_dt = _to_datetime(doc.publish_date)
        effective_dt = _to_datetime(policy_data.get("effective_date"))

        source_name = None
        try:
            if doc.source:
                source_name = doc.source.name
        except Exception as exc:  # noqa: BLE001
            logger.debug("访问文档 %s 的 source 失败: %s", doc.id, exc)

        summary = doc.summary or extracted.get("summary")

        return NormalizedPolicyData(
            doc_id=doc.id,
            title=doc.title,
            state=state,
            status=doc.status,
            publish_date=publish_dt,
            effective_date=effective_dt,
            policy_type=policy_type,
            key_points=key_points,
            summary=summary,
            source_name=source_name,
            source_uri=doc.uri,
            entities=entities,
            relations=relations,
        )

