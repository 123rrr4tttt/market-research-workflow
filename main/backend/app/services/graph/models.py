"""图谱数据模型定义"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ...contracts.json import JSONObject, JSONValue


@dataclass
class NormalizedSocialPost:
    """规范化社交媒体帖子结构（跨平台统一）"""
    doc_id: int
    uri: str
    platform: str
    text: str
    username: str | None = None
    subreddit: str | None = None
    publish_date: datetime | None = None
    createdAt: datetime | None = None
    state: str | None = None
    sentiment_orientation: str | None = None  # positive/negative/neutral
    sentiment_tags: list[str] = field(default_factory=list[str])
    key_phrases: list[str] = field(default_factory=list[str])
    emotion_words: list[str] = field(default_factory=list[str])
    topic: str | None = None
    entities: list[JSONObject] = field(default_factory=list[JSONObject])  # [{text, type, span, kb_id?, canonical_name?}]
    keywords: list[str] = field(default_factory=list[str])


@dataclass
class NormalizedMarketData:
    """规范化市场数据结构（从Document表中提取）"""
    stat_id: int  # 文档ID
    state: str
    game: str | None = None
    date: datetime | None = None
    sales_volume: float | None = None
    revenue: float | None = None
    jackpot: float | None = None
    ticket_price: float | None = None
    source_name: str | None = None
    source_uri: str | None = None
    title: str | None = None  # 文档标题
    entities: list[JSONObject] = field(default_factory=list[JSONObject])  # 实体列表


@dataclass
class NormalizedPolicyData:
    """规范化政策数据结构"""
    doc_id: int
    title: str | None = None
    state: str | None = None
    status: str | None = None
    publish_date: datetime | None = None
    effective_date: datetime | None = None
    policy_type: str | None = None
    key_points: list[str] = field(default_factory=list[str])
    summary: str | None = None
    source_name: str | None = None
    source_uri: str | None = None
    entities: list[JSONObject] = field(default_factory=list[JSONObject])
    relations: list[JSONObject] = field(default_factory=list[JSONObject])


@dataclass
class GraphNode:
    """图谱节点"""
    type: str  # Post, Keyword, Entity, Topic, SentimentTag, User, Subreddit, MarketData, State, Segment
    id: str  # 节点唯一标识
    properties: JSONObject = field(default_factory=dict[str, JSONValue])


@dataclass
class GraphEdge:
    """图谱边"""
    type: str  # MENTIONS_KEYWORD, MENTIONS_ENTITY, HAS_TOPIC, HAS_SENTIMENT, AUTHORED_BY, IN_SUBREDDIT, CO_OCCURS, IN_STATE, HAS_SEGMENT, ON_DATE, etc.
    from_node: GraphNode
    to_node: GraphNode
    properties: JSONObject = field(default_factory=dict[str, JSONValue])


@dataclass
class Graph:
    """图谱数据结构"""
    nodes: dict[str, GraphNode] = field(default_factory=dict[str, GraphNode])  # key: node_id, value: GraphNode
    edges: list[GraphEdge] = field(default_factory=list[GraphEdge])
    schema_version: str = "v1"
