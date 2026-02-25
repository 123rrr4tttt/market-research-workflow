from __future__ import annotations


MENU_CONFIG = {
    "items": [
        {"key": "home", "label": "主页", "path": "index.html", "order": 10, "visible": True},
        {"key": "dashboard", "label": "综合仪表盘", "path": "dashboard.html", "order": 20, "visible": True},
        {"key": "data", "label": "数据仪表盘", "path": "data-dashboard.html", "order": 30, "visible": True},
        {"key": "market", "label": "市场可视化", "path": "market-data-visualization.html", "order": 40, "visible": True},
        {"key": "policy", "label": "政策仪表盘", "path": "policy-dashboard.html", "order": 50, "visible": True},
        {"key": "social", "label": "社媒可视化", "path": "social-media-visualization.html", "order": 60, "visible": True},
        {"key": "policy_graph", "label": "政策图谱", "path": "policy-graph.html", "order": 70, "visible": True},
        {"key": "social_graph", "label": "社媒图谱", "path": "social-media-graph.html", "order": 80, "visible": True},
        {"key": "source_library", "label": "信息源库管理", "path": "source-library-management.html", "order": 90, "visible": True},
        {"key": "llm", "label": "LLM 配置", "path": "settings.html#llm-config", "order": 100, "visible": True},
    ]
}
