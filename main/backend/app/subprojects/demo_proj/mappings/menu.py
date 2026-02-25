from __future__ import annotations


MENU_CONFIG = {
    "items": [
        {"key": "dashboard", "label": "具身智能看板", "path": "/dashboard.html", "order": 10, "visible": True},
        {"key": "ingest", "label": "信号采集", "path": "/app.html", "order": 20, "visible": True},
        {"key": "market_viz", "label": "市场图谱", "path": "/market-data-visualization.html", "order": 30, "visible": True},
        {"key": "policy_graph", "label": "政策图谱", "path": "/policy-graph.html", "order": 40, "visible": True},
        {"key": "social_graph", "label": "社媒图谱", "path": "/social-media-graph.html", "order": 50, "visible": True},
        {"key": "policy", "label": "政策洞察", "path": "/policy-dashboard.html", "order": 60, "visible": True},
        {"key": "admin", "label": "系统管理", "path": "/admin.html", "order": 99, "visible": False},
    ]
}
