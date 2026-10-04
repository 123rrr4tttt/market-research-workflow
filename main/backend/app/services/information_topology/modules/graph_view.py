"""Graph topology view profile; presentation state remains outside the facts."""

from __future__ import annotations

from typing import Any, Mapping

from ..contracts import BoundRef, TopologyState, ViewSpec
from ..profiles import AttributeRule, EndpointRule, ProfileSpec, TypeRule

GRAPH_VIEW_PROFILE_ID = "graph.view"
GRAPH_VIEW_PROFILE_VERSION = "1"
GRAPH_VIEW_DEFINITION_ID = "graph.members-and-relations"
GRAPH_VIEW_DEFINITION_VERSION = "1"

graph_view_profile = ProfileSpec(
    GRAPH_VIEW_PROFILE_ID,
    GRAPH_VIEW_PROFILE_VERSION,
    {
        "graph_node": TypeRule(allow_extra_attributes=True),
        "graph_relation": TypeRule(
            attributes={"edge_type": AttributeRule("string", True), "origin_ref": AttributeRule("object", True),
                        "properties": AttributeRule("object", True)},
            endpoints={
                "source": EndpointRule(frozenset({"graph_node"}), 1, 1),
                "target": EndpointRule(frozenset({"graph_node"}), 1, 1),
            },
            allow_extra_attributes=False,
        ),
    },
    frozenset({"graph_relation"}),
)


def make_graph_view_spec(*, group_by: str | None = None) -> ViewSpec:
    """Build a pure projection; `group_by` reads a node property only."""
    if group_by is not None and (not isinstance(group_by, str) or not group_by.strip()):
        # kit:boundary owner=information_topology.modules.graph_view.make_graph_view_spec.group_by class=PROGRAMMER_DEFECT failure_family=none witness=test:test_graph_adapter_preserves_relation_origin_and_endpoints_and_ignores_ui_state
        raise ValueError("group_by must be a non-empty property name")

    def project(state: TopologyState) -> tuple[tuple[BoundRef, ...], tuple[BoundRef, ...], Mapping[str, Any]]:
        nodes = tuple(element.ref for element in state.elements if element.ref.ref.type_id == "graph_node")
        relations = tuple(element.ref for element in state.elements if element.ref.ref.type_id == "graph_relation")
        groups: dict[str, list[dict[str, str]]] = {}
        if group_by:
            for element in state.elements:
                if element.ref.ref.type_id != "graph_node":
                    continue
                value = element.attributes.get(group_by)
                if value is None:
                    continue
                groups.setdefault(str(value), []).append({"module_id": element.ref.ref.module_id,
                    "type_id": element.ref.ref.type_id, "local_id": element.ref.ref.local_id})
        organization = {"group_by": group_by, "groups": groups} if group_by else {}
        return nodes, relations, organization

    return ViewSpec(GRAPH_VIEW_DEFINITION_ID, GRAPH_VIEW_DEFINITION_VERSION,
                    GRAPH_VIEW_PROFILE_ID, GRAPH_VIEW_PROFILE_VERSION, project)
