from types import SimpleNamespace

from app.services.graph.doc_types import resolve_graph_projections


def _customization(field_mapping):
    return SimpleNamespace(get_field_mapping=lambda: field_mapping)


def test_graph_projection_bindings_normalize_project_declarations(monkeypatch):
    customization = _customization({
        "graph_projections": [
            {"id": "graphDeep", "label": "总图"},
            {
                "id": "graphMarket",
                "label": "一 供水与水资源物质基础",
                "topology_filter": {"attribute": "outline_section", "contains_any": ["1", "", "1"]},
            },
            {"id": "graphProduct", "hidden": True},
            {"id": "graphOperation", "topology_filter": {"attribute": "", "contains_any": ["x"]}},
            {"label": "missing id"},
            "not-an-object",
            {"id": "graphDeep", "label": "duplicate id"},
        ]
    })
    monkeypatch.setattr(
        "app.services.graph.doc_types.get_project_customization",
        lambda project_key: customization,
    )

    assert resolve_graph_projections("project") == [
        {"id": "graphDeep", "label": "总图"},
        {
            "id": "graphMarket",
            "label": "一 供水与水资源物质基础",
            "topology_filter": {"attribute": "outline_section", "contains_any": ["1"]},
        },
        {"id": "graphProduct", "hidden": True},
        {"id": "graphOperation"},
    ]


def test_graph_projection_bindings_absent_for_projects_without_declaration(monkeypatch):
    monkeypatch.setattr(
        "app.services.graph.doc_types.get_project_customization",
        lambda project_key: _customization({}),
    )
    assert resolve_graph_projections("default") == []
