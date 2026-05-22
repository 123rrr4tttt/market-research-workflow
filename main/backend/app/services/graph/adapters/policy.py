"\"\"\"政策数据适配器\"\"\""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from ....models.entities import Document
from ..models import NormalizedPolicyData
from ...document_views import (
    get_policy_data,
    get_policy_entities,
    get_policy_key_points,
    get_policy_relations,
    get_policy_state,
    get_policy_summary_text,
    get_policy_type,
    has_structured_data,
)

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
        if not has_structured_data(doc):
            logger.debug("Document %s 缺少 extracted_data，跳过", doc.id)
            return None

        policy_data: Dict[str, Any] = get_policy_data(doc)

        # 如果既没有 policy 数据也没有基本信息，则跳过
        if not policy_data and doc.doc_type not in ("policy", "policy_regulation"):
            logger.debug("Document %s doc_type=%s，非政策文档", doc.id, doc.doc_type)
            return None

        state = get_policy_state(doc)
        policy_type = get_policy_type(doc)
        key_points = get_policy_key_points(doc)[:5]
        entities = get_policy_entities(doc)
        relations = get_policy_relations(doc)

        publish_dt = _to_datetime(doc.publish_date)
        effective_dt = _to_datetime(policy_data.get("effective_date"))

        source_name = None
        try:
            if doc.source:
                source_name = doc.source.name
        except Exception as exc:  # noqa: BLE001
            logger.debug("访问文档 %s 的 source 失败: %s", doc.id, exc)

        summary = get_policy_summary_text(doc)

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
