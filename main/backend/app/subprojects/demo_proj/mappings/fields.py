from __future__ import annotations


FIELD_MAPPING = {
    "graph_doc_types": {
        "social": ["social_sentiment", "social_feed"],
        "market": ["market_info", "market"],
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
    "graph_topic_scope_entities": {
        "company": ["CompanyEntity", "CompanyBrand", "CompanyUnit", "CompanyPartner", "CompanyChannel"],
        "product": ["ProductEntity", "ProductModel", "ProductCategory", "ProductBrand", "ProductComponent", "ProductScenario"],
        "operation": ["OperationEntity", "OperationPlatform", "OperationStore", "OperationChannel", "OperationMetric", "OperationStrategy", "OperationRegion", "OperationPeriod"],
    },
    "graph_node_labels": {
        "State": "地区",
        "Segment": "品类",
        "MarketData": "数据",
        "Policy": "数据",
        "Post": "数据",
    },
    "graph_field_labels": {
        "state": "地区",
        "game": "产品",
        "segment": "品类",
        "sales_volume": "部署量",
        "revenue": "市场规模",
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
    "doc_type_mapping": {
        "social_feed": "social_sentiment",
        "social_sentiment": "social_sentiment",
        "news": "market_info",
        "market_info": "market_info",
        "policy_regulation": "policy",
    },
    "market": {
        "deployment_volume": "sales_volume",
        "financing_or_order_amount": "funding_amount",
    },
    "policy": {
        "policy_category": "policy_type",
        "highlights": "key_points",
    },
}
