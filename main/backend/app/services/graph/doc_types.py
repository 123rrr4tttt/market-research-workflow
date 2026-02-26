from __future__ import annotations

from typing import Any

from ...project_customization.service import get_project_customization

DEFAULT_GRAPH_DOC_TYPES: dict[str, list[str]] = {
    "social": ["social_sentiment", "social_feed"],
    "market": ["market_info", "market"],
    "policy": ["policy", "policy_regulation"],
}

DEFAULT_GRAPH_TYPE_LABELS: dict[str, str] = {
    "social": "社媒图谱",
    "market": "市场图谱",
    "policy": "政策图谱",
}

DEFAULT_GRAPH_NODE_TYPES: dict[str, list[str]] = {
    "social": ["Post", "Keyword", "Entity", "Topic", "SentimentTag", "User", "Subreddit"],
    "market": ["MarketData", "State", "Segment", "Entity"],
    "policy": ["Policy", "State", "PolicyType", "KeyPoint", "Entity"],
}

DEFAULT_GRAPH_EDGE_TYPES: dict[str, list[str]] = {
    "social": [
        "MENTIONS_KEYWORD",
        "MENTIONS_ENTITY",
        "HAS_TOPIC",
        "HAS_SENTIMENT",
        "AUTHORED_BY",
        "IN_SUBREDDIT",
        "CO_OCCURS",
    ],
    "market": ["IN_STATE", "HAS_SEGMENT", "MENTIONS_ENTITY"],
    "policy": ["APPLIES_TO_STATE", "HAS_TYPE", "HAS_KEYPOINT", "MENTIONS_ENTITY", "POLICY_RELATION"],
}

DEFAULT_GRAPH_NODE_LABELS: dict[str, str] = {
    "Post": "帖子",
    "Keyword": "关键词",
    "Entity": "实体",
    "Topic": "主题",
    "SentimentTag": "情感标签",
    "User": "用户",
    "Subreddit": "社区",
    "MarketData": "市场数据",
    "State": "州",
    "Segment": "品类",
    "Game": "游戏",
    "Policy": "政策",
    "PolicyType": "类型",
    "KeyPoint": "要点",
}

DEFAULT_GRAPH_FIELD_LABELS: dict[str, str] = {
    "platform": "平台",
    "state": "州",
    "game": "游戏",
    "segment": "品类",
    "sales_volume": "销售额",
    "revenue": "收入",
    "title": "标题",
    "status": "状态",
}

DEFAULT_GRAPH_RELATION_LABELS: dict[str, str] = {
    "MENTIONS_KEYWORD": "提及关键词",
    "MENTIONS_ENTITY": "提及实体",
    "HAS_TOPIC": "关联主题",
    "HAS_SENTIMENT": "情感标签",
    "AUTHORED_BY": "作者关系",
    "IN_SUBREDDIT": "所属社区",
    "CO_OCCURS": "关键词共现",
    "IN_STATE": "所属地区",
    "HAS_SEGMENT": "关联品类",
    "APPLIES_TO_STATE": "适用地区",
    "HAS_TYPE": "政策类型",
    "HAS_KEYPOINT": "关键要点",
    "POLICY_RELATION": "政策关系",
}


def resolve_graph_doc_types(project_key: str | None = None) -> dict[str, list[str]]:
    customization = get_project_customization(project_key)
    field_mapping = customization.get_field_mapping() or {}
    raw = field_mapping.get("graph_doc_types")

    if not isinstance(raw, dict):
        return {k: list(v) for k, v in DEFAULT_GRAPH_DOC_TYPES.items()}

    resolved: dict[str, list[str]] = {}
    for category, defaults in DEFAULT_GRAPH_DOC_TYPES.items():
        configured = raw.get(category, defaults)
        values = _normalize_doc_type_list(configured)
        resolved[category] = values or list(defaults)
    return resolved


def resolve_graph_type_labels(project_key: str | None = None) -> dict[str, str]:
    customization = get_project_customization(project_key)
    field_mapping = customization.get_field_mapping() or {}
    raw = field_mapping.get("graph_type_labels")

    if not isinstance(raw, dict):
        return dict(DEFAULT_GRAPH_TYPE_LABELS)

    labels: dict[str, str] = {}
    for category, default_label in DEFAULT_GRAPH_TYPE_LABELS.items():
        label = raw.get(category, default_label)
        labels[category] = str(label).strip() or default_label
    return labels


def resolve_graph_node_types(project_key: str | None = None) -> dict[str, list[str]]:
    customization = get_project_customization(project_key)
    field_mapping = customization.get_field_mapping() or {}
    raw = field_mapping.get("graph_node_types")

    if not isinstance(raw, dict):
        return {k: list(v) for k, v in DEFAULT_GRAPH_NODE_TYPES.items()}

    resolved: dict[str, list[str]] = {}
    for category, defaults in DEFAULT_GRAPH_NODE_TYPES.items():
        configured = raw.get(category, defaults)
        values = _normalize_string_list(configured)
        resolved[category] = values or list(defaults)
    return resolved


def resolve_graph_edge_types(project_key: str | None = None) -> dict[str, list[str]]:
    customization = get_project_customization(project_key)
    field_mapping = customization.get_field_mapping() or {}
    raw = field_mapping.get("graph_edge_types")

    if not isinstance(raw, dict):
        return {k: list(v) for k, v in DEFAULT_GRAPH_EDGE_TYPES.items()}

    resolved: dict[str, list[str]] = {}
    for category, defaults in DEFAULT_GRAPH_EDGE_TYPES.items():
        configured = raw.get(category, defaults)
        values = _normalize_string_list(configured)
        resolved[category] = values or list(defaults)
    return resolved


def resolve_graph_node_labels(project_key: str | None = None) -> dict[str, str]:
    """Node type -> display label. Projects can override via graph_node_labels in field_mapping."""
    customization = get_project_customization(project_key)
    field_mapping = customization.get_field_mapping() or {}
    raw = field_mapping.get("graph_node_labels")

    labels = dict(DEFAULT_GRAPH_NODE_LABELS)
    if isinstance(raw, dict):
        for key, value in raw.items():
            k = str(key or "").strip()
            if k:
                labels[k] = str(value or "").strip() or labels.get(k, k)
    return labels


def resolve_graph_field_labels(project_key: str | None = None) -> dict[str, str]:
    """Field-level display labels for card sections (state, game, sales_volume, etc.)."""
    customization = get_project_customization(project_key)
    field_mapping = customization.get_field_mapping() or {}
    raw = field_mapping.get("graph_field_labels")

    labels = dict(DEFAULT_GRAPH_FIELD_LABELS)
    if isinstance(raw, dict):
        for key, value in raw.items():
            k = str(key or "").strip()
            if k:
                labels[k] = str(value or "").strip() or labels.get(k, k)
    return labels


def resolve_graph_relation_labels(project_key: str | None = None) -> dict[str, str]:
    customization = get_project_customization(project_key)
    field_mapping = customization.get_field_mapping() or {}
    raw = field_mapping.get("graph_relation_labels")

    if not isinstance(raw, dict):
        return dict(DEFAULT_GRAPH_RELATION_LABELS)

    labels = dict(DEFAULT_GRAPH_RELATION_LABELS)
    for key, value in raw.items():
        normalized = str(key or "").strip()
        if not normalized:
            continue
        labels[normalized] = str(value or "").strip() or labels.get(normalized, normalized)
    return labels


def _normalize_doc_type_list(value: Any) -> list[str]:
    if isinstance(value, str):
        candidate = [value]
    elif isinstance(value, (list, tuple, set)):
        candidate = list(value)
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in candidate:
        key = str(item or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        candidate = [value]
    elif isinstance(value, (list, tuple, set)):
        candidate = list(value)
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in candidate:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized
