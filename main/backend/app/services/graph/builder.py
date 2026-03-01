"""图谱构建核心逻辑"""
from __future__ import annotations

import hashlib
import logging
import math
from collections import defaultdict, Counter
import unicodedata
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Set, Tuple

from ...settings.graph import (
    STOPWORDS, COOCCUR_WINDOW, USE_TFIDF, TIME_DECAY_TAU_DAYS,
    MAX_KEYWORDS_PER_POST
)
from .models import (
    Graph,
    GraphNode,
    GraphEdge,
    NormalizedSocialPost,
    NormalizedMarketData,
    NormalizedPolicyData,
)
from .relation_ontology import relation_annotation

logger = logging.getLogger(__name__)


def _generate_keyword_id(text: str, lang: str = "en") -> str:
    """生成关键词ID: sha1(normalize(text)+lang)
    规范化包含：NFKC、去零宽字符、合并空白、小写、strip
    """
    normalized = _normalize_text(text)
    content = f"{normalized}{lang.lower()}"
    return hashlib.sha1(content.encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    """标准化文本：NFKC + 去零宽字符 + 合并空白 + 小写 + strip"""
    if not isinstance(text, str):
        return ""
    s = unicodedata.normalize("NFKC", text)
    # 去除零宽空白等隐形字符
    s = re.sub(r"[\u200B-\u200D\uFEFF]", "", s)
    # 合并各种空白为单个空格
    s = re.sub(r"\s+", " ", s)
    return s.lower().strip()


def _generate_entity_id(entity: Dict) -> str:
    """生成实体ID: kb_id or sha1(normalize(canonical_name)+lower(type))"""
    kb_id = entity.get("kb_id")
    if kb_id:
        return f"kb:{kb_id}"
    
    canonical_name = _normalize_text(entity.get("canonical_name") or entity.get("text", ""))
    entity_type = (entity.get("type", "UNKNOWN") or "UNKNOWN").lower().strip()
    content = f"{canonical_name}{entity_type}"
    return hashlib.sha1(content.encode("utf-8")).hexdigest()


def _generate_keypoint_id(text: str) -> str:
    """生成政策关键要点ID"""
    normalized = _normalize_text(text)
    content = f"policy_keypoint:{normalized}"
    return hashlib.sha1(content.encode("utf-8")).hexdigest()


def _calculate_tfidf(
    posts: List[NormalizedSocialPost],
    keyword_counts: Dict[str, Dict[str, int]]
) -> Dict[str, Dict[str, float]]:
    """计算TF-IDF权重"""
    if not USE_TFIDF:
        return {}
    
    # 计算文档频率（包含该关键词的文档数）
    doc_freq: Dict[str, int] = defaultdict(int)
    total_docs = len(posts)
    
    for keyword in keyword_counts:
        doc_freq[keyword] = len(keyword_counts[keyword])
    
    # 计算TF-IDF
    tfidf_scores: Dict[str, Dict[str, float]] = defaultdict(dict)
    
    for post in posts:
        post_id = str(post.doc_id)
        # 规范化并去重帖子关键词
        post_keywords_norm: List[str] = []
        _seen: Set[str] = set()
        for kw in post.keywords[:MAX_KEYWORDS_PER_POST]:
            n = kw.lower().strip()
            if n and n not in _seen:
                _seen.add(n)
                post_keywords_norm.append(n)
        
        # 计算词频（TF）
        keyword_freq = Counter(post_keywords_norm)
        total_terms = len(post_keywords_norm)
        
        for keyword, count in keyword_freq.items():
            if total_terms > 0:
                tf = count / total_terms
                # IDF = log(总文档数 / 包含该词的文档数)
                df = doc_freq.get(keyword, 1)
                idf = 1.0 if df == 0 else (total_docs / max(df, 1))
                tfidf = tf * (1.0 + math.log(idf))
                tfidf_scores[post_id][keyword] = tfidf
    
    return tfidf_scores


def _apply_time_decay(
    weight: float,
    post_date: Optional[datetime],
    reference_date: Optional[datetime] = None
) -> float:
    """应用时间衰减: decay = exp(-Δt/τ)"""
    if TIME_DECAY_TAU_DAYS is None or not post_date:
        return weight
    
    if reference_date is None:
        reference_date = datetime.utcnow()
    
    delta_days = (reference_date - post_date).total_seconds() / 86400.0
    tau = TIME_DECAY_TAU_DAYS
    decay = math.exp(-delta_days / tau)
    
    return weight * decay


def build_graph(
    posts: List[NormalizedSocialPost],
    *,
    window: int = COOCCUR_WINDOW,
    use_tfidf: bool = USE_TFIDF,
    tau: Optional[int] = TIME_DECAY_TAU_DAYS
) -> Graph:
    """
    构建内容图谱
    
    Args:
        posts: 规范化社交媒体帖子列表
        window: 共现窗口大小（0=整帖共现，>0=滑动窗口）
        use_tfidf: 是否使用TF-IDF计算权重
        tau: 时间衰减参数（天数）
    
    Returns:
        构建好的图谱对象
    """
    graph = Graph()
    
    # 统计关键词出现次数（用于TF-IDF）
    keyword_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    # 第一遍：构建所有节点
    for post in posts:
        post_id = str(post.doc_id)
        
        # Post节点
        post_node = GraphNode(
            type="Post",
            id=post_id,
            properties={
                "uri": post.uri,
                "platform": post.platform,
                "text": post.text[:500] if post.text else None,  # 限制长度避免数据过大
                "publish_date": post.publish_date.isoformat() if post.publish_date else None,
                "created_at": post.createdAt.isoformat() if post.createdAt else None,
                "state": post.state,
                "sentiment_orientation": post.sentiment_orientation,
                "username": post.username,
                "subreddit": post.subreddit,
                "topic": post.topic,
                "sentiment_tags": post.sentiment_tags,
                "key_phrases": post.key_phrases,
                "emotion_words": post.emotion_words,
            }
        )
        graph.nodes[f"Post:{post_id}"] = post_node
        
        # Keyword节点（统一小写合并，去重）
        seen_kw: Set[str] = set()
        for keyword in post.keywords[:MAX_KEYWORDS_PER_POST]:
            norm_kw = _normalize_text(keyword)
            if not norm_kw or norm_kw in seen_kw:
                continue
            seen_kw.add(norm_kw)
            keyword_id = _generate_keyword_id(norm_kw)
            keyword_counts[norm_kw][post_id] += 1
            if f"Keyword:{keyword_id}" not in graph.nodes:
                keyword_node = GraphNode(
                    type="Keyword",
                    id=keyword_id,
                    properties={"text": norm_kw}
                )
                graph.nodes[f"Keyword:{keyword_id}"] = keyword_node
        
        # Entity节点
        for entity in post.entities:
            entity_id = _generate_entity_id(entity)
            if f"Entity:{entity_id}" not in graph.nodes:
                entity_node = GraphNode(
                    type="Entity",
                    id=entity_id,
                    properties={
                        "canonical_name": entity.get("canonical_name") or entity.get("text", ""),
                        "type": entity.get("type", "UNKNOWN"),
                        "kb_id": entity.get("kb_id"),
                    }
                )
                graph.nodes[f"Entity:{entity_id}"] = entity_node
        
        # Topic节点
        if post.topic:
            topic_id = post.topic.lower().strip()
            if f"Topic:{topic_id}" not in graph.nodes:
                topic_node = GraphNode(
                    type="Topic",
                    id=topic_id,
                    properties={"label": post.topic}
                )
                graph.nodes[f"Topic:{topic_id}"] = topic_node
        
        # SentimentTag节点
        for tag in post.sentiment_tags:
            tag_id = tag.lower().strip()
            if f"SentimentTag:{tag_id}" not in graph.nodes:
                tag_node = GraphNode(
                    type="SentimentTag",
                    id=tag_id,
                    properties={"label": tag}
                )
                graph.nodes[f"SentimentTag:{tag_id}"] = tag_node
        
        # User节点
        if post.username:
            user_id = f"{post.platform}:{post.username}"
            if f"User:{user_id}" not in graph.nodes:
                user_node = GraphNode(
                    type="User",
                    id=user_id,
                    properties={
                        "platform": post.platform,
                        "username": post.username,
                    }
                )
                graph.nodes[f"User:{user_id}"] = user_node
        
        # Subreddit节点
        if post.subreddit:
            subreddit_id = post.subreddit.lower().strip()
            if f"Subreddit:{subreddit_id}" not in graph.nodes:
                subreddit_node = GraphNode(
                    type="Subreddit",
                    id=subreddit_id,
                    properties={"name": post.subreddit}
                )
                graph.nodes[f"Subreddit:{subreddit_id}"] = subreddit_node
    
    # 计算TF-IDF（如果需要）
    tfidf_scores = {}
    if use_tfidf:
        tfidf_scores = _calculate_tfidf(posts, keyword_counts)
    
    # 第二遍：构建边
    for post in posts:
        post_id = str(post.doc_id)
        post_node = graph.nodes[f"Post:{post_id}"]
        
        # 构建本帖规范化关键词列表（去重）
        post_keywords_norm: List[str] = []
        _seen_local: Set[str] = set()
        for kw in post.keywords[:MAX_KEYWORDS_PER_POST]:
            n = _normalize_text(kw)
            if n and n not in _seen_local:
                _seen_local.add(n)
                post_keywords_norm.append(n)

        # Post -> Keyword (MENTIONS_KEYWORD)
        for keyword in post_keywords_norm:
            keyword_id = _generate_keyword_id(keyword)
            keyword_node = graph.nodes[f"Keyword:{keyword_id}"]
            
            # 计算权重
            weight = 1.0
            if use_tfidf and post_id in tfidf_scores:
                weight = tfidf_scores[post_id].get(keyword, 1.0)
            
            # 应用时间衰减
            weight = _apply_time_decay(weight, post.publish_date or post.createdAt)
            
            edge = GraphEdge(
                type="MENTIONS_KEYWORD",
                from_node=post_node,
                to_node=keyword_node,
                properties={"weight": weight}
            )
            graph.edges.append(edge)
        
        # Post -> Entity (MENTIONS_ENTITY)
        for entity in post.entities:
            entity_id = _generate_entity_id(entity)
            entity_node = graph.nodes[f"Entity:{entity_id}"]
            
            edge_props = {}
            if entity.get("span"):
                edge_props["positions"] = entity["span"]
            if entity.get("confidence"):
                edge_props["confidence"] = entity["confidence"]
            
            edge = GraphEdge(
                type="MENTIONS_ENTITY",
                from_node=post_node,
                to_node=entity_node,
                properties=edge_props
            )
            graph.edges.append(edge)
        
        # Post -> Topic (HAS_TOPIC)
        if post.topic:
            topic_id = post.topic.lower().strip()
            topic_node = graph.nodes[f"Topic:{topic_id}"]
            
            edge = GraphEdge(
                type="HAS_TOPIC",
                from_node=post_node,
                to_node=topic_node,
                properties={}
            )
            graph.edges.append(edge)
        
        # Post -> SentimentTag (HAS_SENTIMENT)
        for tag in post.sentiment_tags:
            tag_id = tag.lower().strip()
            tag_node = graph.nodes[f"SentimentTag:{tag_id}"]
            
            edge = GraphEdge(
                type="HAS_SENTIMENT",
                from_node=post_node,
                to_node=tag_node,
                properties={
                    "orientation": post.sentiment_orientation,
                }
            )
            graph.edges.append(edge)
        
        # Post -> User (AUTHORED_BY)
        if post.username:
            user_id = f"{post.platform}:{post.username}"
            user_node = graph.nodes[f"User:{user_id}"]
            
            edge = GraphEdge(
                type="AUTHORED_BY",
                from_node=post_node,
                to_node=user_node,
                properties={}
            )
            graph.edges.append(edge)
        
        # Post -> Subreddit (IN_SUBREDDIT)
        if post.subreddit:
            subreddit_id = post.subreddit.lower().strip()
            subreddit_node = graph.nodes[f"Subreddit:{subreddit_id}"]
            
            edge = GraphEdge(
                type="IN_SUBREDDIT",
                from_node=post_node,
                to_node=subreddit_node,
                properties={}
            )
            graph.edges.append(edge)
        
        # Keyword -> Keyword (CO_OCCURS) - 同一帖子内的关键词共现（使用规范化关键词）
        if len(post_keywords_norm) > 1:
            for i, kw1 in enumerate(post_keywords_norm):
                for kw2 in post_keywords_norm[i+1:]:
                    kw1_id = _generate_keyword_id(kw1)
                    kw2_id = _generate_keyword_id(kw2)
                    
                    kw1_node = graph.nodes[f"Keyword:{kw1_id}"]
                    kw2_node = graph.nodes[f"Keyword:{kw2_id}"]
                    
                    edge = GraphEdge(
                        type="CO_OCCURS",
                        from_node=kw1_node,
                        to_node=kw2_node,
                        properties={
                            "weight": 1.0,
                            "window": window,
                        }
                    )
                    graph.edges.append(edge)
    
    logger.info(f"Built graph with {len(graph.nodes)} nodes and {len(graph.edges)} edges")
    return graph


def build_topic_subgraph(
    graph: Graph,
    topic_label: str,
    *,
    time_window: Optional[Tuple[datetime, datetime]] = None
) -> Graph:
    """
    构建主题子图
    
    Args:
        graph: 原始图谱
        topic_label: 主题标签
        time_window: 可选的时间窗口 (start, end)
    
    Returns:
        主题子图
    """
    topic_id = topic_label.lower().strip()
    topic_node_key = f"Topic:{topic_id}"
    
    if topic_node_key not in graph.nodes:
        logger.warning(f"Topic '{topic_label}' not found in graph")
        return Graph()
    
    subgraph = Graph()
    
    # 找到所有连接到该主题的Post节点
    related_post_ids: Set[str] = set()
    
    for edge in graph.edges:
        if edge.type == "HAS_TOPIC":
            if edge.to_node.id == topic_id:
                related_post_ids.add(edge.from_node.id)
    
    # 如果指定了时间窗口，过滤Post
    if time_window:
        start_date, end_date = time_window
        filtered_post_ids: Set[str] = set()
        
        for post_id in related_post_ids:
            post_node_key = f"Post:{post_id}"
            if post_node_key in graph.nodes:
                post_node = graph.nodes[post_node_key]
                post_date_str = post_node.properties.get("publish_date") or post_node.properties.get("created_at")
                if post_date_str:
                    try:
                        post_date = datetime.fromisoformat(post_date_str.replace("Z", "+00:00"))
                        if start_date <= post_date <= end_date:
                            filtered_post_ids.add(post_id)
                    except (ValueError, TypeError):
                        pass
        
        related_post_ids = filtered_post_ids
    
    # 收集所有相关节点
    related_node_keys: Set[str] = set()
    
    for post_id in related_post_ids:
        related_node_keys.add(f"Post:{post_id}")
    
    # 遍历所有边，收集相关节点
    for edge in graph.edges:
        from_key = f"{edge.from_node.type}:{edge.from_node.id}"
        to_key = f"{edge.to_node.type}:{edge.to_node.id}"
        
        if from_key in related_node_keys or to_key in related_node_keys:
            related_node_keys.add(from_key)
            related_node_keys.add(to_key)
    
    # 构建子图
    for node_key in related_node_keys:
        if node_key in graph.nodes:
            subgraph.nodes[node_key] = graph.nodes[node_key]
    
    for edge in graph.edges:
        from_key = f"{edge.from_node.type}:{edge.from_node.id}"
        to_key = f"{edge.to_node.type}:{edge.to_node.id}"
        
        if from_key in related_node_keys and to_key in related_node_keys:
            subgraph.edges.append(edge)
    
    logger.info(f"Built topic subgraph for '{topic_label}' with {len(subgraph.nodes)} nodes and {len(subgraph.edges)} edges")
    return subgraph


def build_market_graph(
    market_data_list: List[NormalizedMarketData]
) -> Graph:
    """
    构建市场数据图谱
    
    Args:
        market_data_list: 规范化市场数据列表
    
    Returns:
        构建好的图谱对象
    """
    graph = Graph()
    
    # 第一遍：构建所有节点
    for market_data in market_data_list:
        stat_id = str(market_data.stat_id)
        
        # MarketData节点
        market_node = GraphNode(
            type="MarketData",
            id=stat_id,
            properties={
                "title": market_data.title,
                "state": market_data.state,
                "game": market_data.game,
                "date": market_data.date.isoformat() if market_data.date else None,
                "sales_volume": market_data.sales_volume,
                "revenue": market_data.revenue,
                "jackpot": market_data.jackpot,
                "ticket_price": market_data.ticket_price,
                "source_name": market_data.source_name,
                "source_uri": market_data.source_uri,
            }
        )
        graph.nodes[f"MarketData:{stat_id}"] = market_node
        
        # State节点
        if market_data.state:
            state_id = market_data.state.upper().strip()
            if f"State:{state_id}" not in graph.nodes:
                state_node = GraphNode(
                    type="State",
                    id=state_id,
                    properties={"name": state_id}
                )
                graph.nodes[f"State:{state_id}"] = state_node
        
        # Segment节点（通用：lottery的game、demo的segment等均适配为此）
        if market_data.game:
            seg_id = market_data.game.lower().strip()
            if f"Segment:{seg_id}" not in graph.nodes:
                seg_node = GraphNode(
                    type="Segment",
                    id=seg_id,
                    properties={"name": market_data.game}
                )
                graph.nodes[f"Segment:{seg_id}"] = seg_node
        
        # Entity节点
        for entity in market_data.entities:
            entity_id = _generate_entity_id(entity)
            if f"Entity:{entity_id}" not in graph.nodes:
                entity_node = GraphNode(
                    type="Entity",
                    id=entity_id,
                    properties={
                        "canonical_name": entity.get("canonical_name") or entity.get("text", ""),
                        "entity_type": entity.get("type", "UNKNOWN"),  # 使用entity_type避免与节点type冲突
                        "kb_id": entity.get("kb_id"),
                    }
                )
                graph.nodes[f"Entity:{entity_id}"] = entity_node
    
    # 第二遍：构建边
    for market_data in market_data_list:
        stat_id = str(market_data.stat_id)
        market_node_key = f"MarketData:{stat_id}"
        
        if market_node_key not in graph.nodes:
            continue
        
        market_node = graph.nodes[market_node_key]
        
        # MarketData -> State
        if market_data.state:
            state_id = market_data.state.upper().strip()
            state_node_key = f"State:{state_id}"
            if state_node_key in graph.nodes:
                state_node = graph.nodes[state_node_key]
                edge = GraphEdge(
                    type="IN_STATE",
                    from_node=market_node,
                    to_node=state_node,
                    properties={"weight": 1.0}
                )
                graph.edges.append(edge)
        
        # MarketData -> Segment (generic: game/segment/category)
        if market_data.game:
            seg_id = market_data.game.lower().strip()
            seg_node_key = f"Segment:{seg_id}"
            if seg_node_key in graph.nodes:
                seg_node = graph.nodes[seg_node_key]
                edge = GraphEdge(
                    type="HAS_SEGMENT",
                    from_node=market_node,
                    to_node=seg_node,
                    properties={"weight": 1.0}
                )
                graph.edges.append(edge)
        
        # MarketData -> Entity
        for entity in market_data.entities:
            entity_id = _generate_entity_id(entity)
            entity_node_key = f"Entity:{entity_id}"
            if entity_node_key in graph.nodes:
                entity_node = graph.nodes[entity_node_key]
                edge = GraphEdge(
                    type="MENTIONS_ENTITY",
                    from_node=market_node,
                    to_node=entity_node,
                    properties={"weight": 1.0}
                )
                graph.edges.append(edge)
    
    # 不再创建CO_OCCURS边，相似的数据点会通过布局算法自然靠近
    # 因为它们都连接到相同的State和Segment节点，力导向图会自动让它们靠近
    
    logger.info(f"Built market graph with {len(graph.nodes)} nodes and {len(graph.edges)} edges")
    return graph


def build_policy_graph(
    policy_data_list: List[NormalizedPolicyData]
) -> Graph:
    """
    构建政策数据图谱
    """
    graph = Graph()

    # 第一遍：创建节点
    for policy in policy_data_list:
        policy_id = str(policy.doc_id)

        policy_node = GraphNode(
            type="Policy",
            id=policy_id,
            properties={
                "title": policy.title,
                "state": policy.state,
                "status": policy.status,
                "publish_date": policy.publish_date.isoformat() if policy.publish_date else None,
                "effective_date": policy.effective_date.isoformat() if policy.effective_date else None,
                "policy_type": policy.policy_type,
                "summary": policy.summary,
                "source_name": policy.source_name,
                "source_uri": policy.source_uri,
                "key_points": policy.key_points,
            },
        )
        graph.nodes[f"Policy:{policy_id}"] = policy_node

        if policy.state:
            state_id = policy.state.upper().strip()
            if state_id:
                node_key = f"State:{state_id}"
                if node_key not in graph.nodes:
                    graph.nodes[node_key] = GraphNode(
                        type="State",
                        id=state_id,
                        properties={"name": state_id},
                    )

        if policy.policy_type:
            policy_type_id = policy.policy_type.lower().strip()
            if policy_type_id:
                node_key = f"PolicyType:{policy_type_id}"
                if node_key not in graph.nodes:
                    graph.nodes[node_key] = GraphNode(
                        type="PolicyType",
                        id=policy_type_id,
                        properties={"name": policy.policy_type},
                    )

        for key_point in policy.key_points:
            normalized_point = _normalize_text(key_point)
            if not normalized_point:
                continue
            key_point_id = _generate_keypoint_id(normalized_point)
            node_key = f"KeyPoint:{key_point_id}"
            if node_key not in graph.nodes:
                graph.nodes[node_key] = GraphNode(
                    type="KeyPoint",
                    id=key_point_id,
                    properties={"text": key_point},
                )

        for entity in policy.entities:
            entity_id = _generate_entity_id(entity)
            node_key = f"Entity:{entity_id}"
            if node_key not in graph.nodes:
                graph.nodes[node_key] = GraphNode(
                    type="Entity",
                    id=entity_id,
                    properties={
                        "canonical_name": entity.get("canonical_name") or entity.get("text", ""),
                        "entity_type": entity.get("type", "UNKNOWN"),
                        "kb_id": entity.get("kb_id"),
                    },
                )

    # 第二遍：创建边
    for policy in policy_data_list:
        policy_id = str(policy.doc_id)
        policy_node_key = f"Policy:{policy_id}"
        if policy_node_key not in graph.nodes:
            continue

        policy_node = graph.nodes[policy_node_key]

        if policy.state:
            state_id = policy.state.upper().strip()
            state_node_key = f"State:{state_id}"
            if state_node_key in graph.nodes:
                graph.edges.append(
                    GraphEdge(
                        type="APPLIES_TO_STATE",
                        from_node=policy_node,
                        to_node=graph.nodes[state_node_key],
                        properties={"weight": 1.0},
                    )
                )

        if policy.policy_type:
            policy_type_id = policy.policy_type.lower().strip()
            policy_type_node_key = f"PolicyType:{policy_type_id}"
            if policy_type_node_key in graph.nodes:
                graph.edges.append(
                    GraphEdge(
                        type="HAS_TYPE",
                        from_node=policy_node,
                        to_node=graph.nodes[policy_type_node_key],
                        properties={},
                    )
                )

        for index, key_point in enumerate(policy.key_points, start=1):
            normalized_point = _normalize_text(key_point)
            if not normalized_point:
                continue
            key_point_id = _generate_keypoint_id(normalized_point)
            key_point_node_key = f"KeyPoint:{key_point_id}"
            if key_point_node_key in graph.nodes:
                graph.edges.append(
                    GraphEdge(
                        type="HAS_KEYPOINT",
                        from_node=policy_node,
                        to_node=graph.nodes[key_point_node_key],
                        properties={"order": index},
                    )
                )

        entity_text_map: Dict[str, str] = {}
        for entity in policy.entities:
            entity_id = _generate_entity_id(entity)
            entity_node_key = f"Entity:{entity_id}"
            if entity_node_key in graph.nodes:
                graph.edges.append(
                    GraphEdge(
                        type="MENTIONS_ENTITY",
                        from_node=policy_node,
                        to_node=graph.nodes[entity_node_key],
                        properties={"entity_type": entity.get("type", "UNKNOWN")},
                    )
                )

                text_key = _normalize_text(entity.get("canonical_name") or entity.get("text", ""))
                if text_key:
                    entity_text_map[text_key] = entity_node_key

        def _ensure_entity_node(text: Optional[str]) -> Optional[GraphNode]:
            if not text:
                return None
            normalized = _normalize_text(text)
            if not normalized:
                return None
            existing_key = entity_text_map.get(normalized)
            if existing_key and existing_key in graph.nodes:
                return graph.nodes[existing_key]

            temp_entity = {"canonical_name": text, "type": "UNKNOWN"}
            temp_id = _generate_entity_id(temp_entity)
            node_key = f"Entity:{temp_id}"
            if node_key not in graph.nodes:
                graph.nodes[node_key] = GraphNode(
                    type="Entity",
                    id=temp_id,
                    properties={
                        "canonical_name": text,
                        "entity_type": "UNKNOWN",
                        "kb_id": None,
                    },
                )
            entity_text_map[normalized] = node_key
            return graph.nodes[node_key]

        for relation in policy.relations:
            subject_node = _ensure_entity_node(relation.get("subject"))
            object_node = _ensure_entity_node(relation.get("object"))
            if not subject_node or not object_node:
                continue

            ann = relation_annotation(relation.get("predicate"))
            properties = {
                "predicate": ann["predicate_norm"],
                "predicate_raw": ann["predicate_raw"],
                "relation_class": ann["relation_class"],
                "evidence": relation.get("evidence"),
                "confidence": relation.get("confidence"),
                "date": relation.get("date"),
                "policy_id": policy_id,
            }
            # 移除None值以保持输出精简
            properties = {k: v for k, v in properties.items() if v is not None}

            graph.edges.append(
                GraphEdge(
                    type="POLICY_RELATION",
                    from_node=subject_node,
                    to_node=object_node,
                    properties=properties,
                )
            )

    logger.info("Built policy graph with %s nodes and %s edges", len(graph.nodes), len(graph.edges))
    return graph
