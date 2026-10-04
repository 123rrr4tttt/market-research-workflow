from types import SimpleNamespace

from app.services.graph.doc_types import resolve_graph_edge_style_bindings


def test_graph_edge_style_bindings_transport_project_mapping(monkeypatch):
    customization = SimpleNamespace(get_field_mapping=lambda: {
        "graph_edge_style_bindings": {
            "byRelationClass": {"evidence": "arcUpArrow"},
            "byRelationToken": {"管理": "boldSolidArrow"},
            "byPredicate": {"from": "doubleDashedDiamond"},
            "default": "solidStraightArrow",
            "unused": "ignored",
        }
    })
    monkeypatch.setattr(
        "app.services.graph.doc_types.get_project_customization",
        lambda project_key: customization,
    )

    assert resolve_graph_edge_style_bindings("project") == {
        "byRelationClass": {"evidence": "arcUpArrow"},
        "byRelationToken": {"管理": "boldSolidArrow"},
        "byPredicate": {"from": "doubleDashedDiamond"},
        "default": "solidStraightArrow",
    }


def test_graph_edge_style_bindings_omit_invalid_axes(monkeypatch):
    customization = SimpleNamespace(get_field_mapping=lambda: {
        "graph_edge_style_bindings": {"byRelationClass": {"evidence": None}, "byType": "invalid"},
    })
    monkeypatch.setattr(
        "app.services.graph.doc_types.get_project_customization",
        lambda project_key: customization,
    )

    assert resolve_graph_edge_style_bindings("project") == {}
