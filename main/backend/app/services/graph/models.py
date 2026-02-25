"""图谱数据模型定义"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class NormalizedSocialPost:
    """规范化社交媒体帖子结构（跨平台统一）"""
    doc_id: int
    uri: str
    platform: str
    text: str
    username: Optional[str] = None
    subreddit: Optional[str] = None
    publish_date: Optional[datetime] = None
    createdAt: Optional[datetime] = None
    state: Optional[str] = None
    sentiment_orientation: Optional[str] = None  # positive/negative/neutral
    sentiment_tags: List[str] = field(default_factory=list)
    key_phrases: List[str] = field(default_factory=list)
    emotion_words: List[str] = field(default_factory=list)
    topic: Optional[str] = None
    entities: List[Dict[str, Any]] = field(default_factory=list)  # [{text, type, span, kb_id?, canonical_name?}]
    keywords: List[str] = field(default_factory=list)


@dataclass
class NormalizedMarketData:
    """规范化市场数据结构（从Document表中提取）"""
    stat_id: int  # 文档ID
    state: str
    game: Optional[str] = None
    date: Optional[datetime] = None
    sales_volume: Optional[float] = None
    revenue: Optional[float] = None
    jackpot: Optional[float] = None
    ticket_price: Optional[float] = None
    source_name: Optional[str] = None
    source_uri: Optional[str] = None
    title: Optional[str] = None  # 文档标题
    entities: List[Dict[str, Any]] = field(default_factory=list)  # 实体列表


@dataclass
class NormalizedPolicyData:
    """规范化政策数据结构"""
    doc_id: int
    title: Optional[str] = None
    state: Optional[str] = None
    status: Optional[str] = None
    publish_date: Optional[datetime] = None
    effective_date: Optional[datetime] = None
    policy_type: Optional[str] = None
    key_points: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    source_name: Optional[str] = None
    source_uri: Optional[str] = None
    entities: List[Dict[str, Any]] = field(default_factory=list)
    relations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GraphNode:
    """图谱节点"""
    type: str  # Post, Keyword, Entity, Topic, SentimentTag, User, Subreddit, MarketData, State, Segment
    id: str  # 节点唯一标识
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """图谱边"""
    type: str  # MENTIONS_KEYWORD, MENTIONS_ENTITY, HAS_TOPIC, HAS_SENTIMENT, AUTHORED_BY, IN_SUBREDDIT, CO_OCCURS, IN_STATE, HAS_SEGMENT, ON_DATE, etc.
    from_node: GraphNode
    to_node: GraphNode
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Graph:
    """图谱数据结构"""
    nodes: Dict[str, GraphNode] = field(default_factory=dict)  # key: node_id, value: GraphNode
    edges: List[GraphEdge] = field(default_factory=list)
    schema_version: str = "v1"

