"""Graph interface mapping layer.

This layer freezes the external graph payload contract while allowing
internal node generation logic to evolve independently.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict

from .models import GraphEdge, GraphNode

GRAPH_INTERFACE_VERSION = "v1"

# Reserved keys in node properties that must not shadow interface fields.
_RESERVED_NODE_KEYS = {"type", "id", "from", "to"}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_node_type(node_type: Any) -> str:
    text = _normalize_text(node_type)
    return text or "Unknown"


def normalize_node_id(node_id: Any) -> str:
    return _normalize_text(node_id)


def normalize_node_properties(properties: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(properties, dict):
        return {}
    normalized: Dict[str, Any] = {}
    for key, value in properties.items():
        k = _normalize_text(key)
        if not k or k in _RESERVED_NODE_KEYS:
            continue
        normalized[k] = value
    return normalized


def map_node_for_interface(node: GraphNode) -> Dict[str, Any]:
    return {
        "type": normalize_node_type(node.type),
        "id": normalize_node_id(node.id),
        **normalize_node_properties(node.properties),
    }


def map_edge_for_interface(edge: GraphEdge) -> Dict[str, Any]:
    edge_props = edge.properties if isinstance(edge.properties, dict) else {}
    return {
        "type": _normalize_text(edge.type),
        "from": {
            "type": normalize_node_type(edge.from_node.type),
            "id": normalize_node_id(edge.from_node.id),
        },
        "to": {
            "type": normalize_node_type(edge.to_node.type),
            "id": normalize_node_id(edge.to_node.id),
        },
        **edge_props,
    }

