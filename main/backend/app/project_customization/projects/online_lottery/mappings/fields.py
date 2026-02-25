from __future__ import annotations


FIELD_MAPPING = {
    "graph_doc_types": {
        "social": ["social_feed", "social_sentiment"],
        "market": ["market_info", "market", "news", "official_update", "retailer_update"],
        "policy": ["policy", "policy_regulation"],
    },
    "graph_type_labels": {
        "social": "社媒图谱",
        "market": "市场图谱",
        "policy": "政策图谱",
    },
    "graph_node_types": {
        "social": ["Post", "Keyword", "Entity", "Topic", "SentimentTag", "User", "Subreddit"],
        "market": ["MarketData", "State", "Segment", "Entity"],
        "policy": ["Policy", "State", "PolicyType", "KeyPoint", "Entity"],
    },
    "graph_edge_types": {
        "social": ["MENTIONS_KEYWORD", "MENTIONS_ENTITY", "HAS_TOPIC", "HAS_SENTIMENT", "AUTHORED_BY", "IN_SUBREDDIT", "CO_OCCURS"],
        "market": ["IN_STATE", "HAS_SEGMENT", "MENTIONS_ENTITY"],
        "policy": ["APPLIES_TO_STATE", "HAS_TYPE", "HAS_KEYPOINT", "MENTIONS_ENTITY", "POLICY_RELATION"],
    },
    "graph_node_labels": {
        "Segment": "游戏",
    },
    "graph_field_labels": {
        "game": "游戏",
    },
    "graph_relation_labels": {
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
    },
    "market": {
        "state": "state",
        "game": "segment",
        "jackpot": "financing_or_order_amount",
        "sales_volume": "deployment_volume",
        "revenue": "market_size",
    },
    "policy": {
        "policy_type": "policy_category",
        "key_points": "highlights",
    },
}
