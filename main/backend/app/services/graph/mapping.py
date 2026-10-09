"""Graph interface mapping layer.

This layer freezes the external graph payload contract while allowing
internal node generation logic to evolve independently.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import TypeGuard

from ...contracts.json import JSONObject, JSONValue

from .models import GraphEdge, GraphNode

GRAPH_INTERFACE_VERSION = "v1"

# Reserved keys in node properties that must not shadow interface fields.
_RESERVED_NODE_KEYS = {"type", "id", "from", "to"}


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def normalize_graph_json_value(value: object) -> JSONValue:
    """Normalize a graph property into the persisted/interface JSON domain."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if _is_object_mapping(value):
        return {
            str(key): normalize_graph_json_value(item)
            for key, item in value.items()
        }
    if _is_object_sequence(value):
        return [normalize_graph_json_value(item) for item in value]
    return str(value)


def normalize_graph_json_object(value: object) -> JSONObject:
    if not _is_object_mapping(value):
        return {}
    return {
        str(key): normalize_graph_json_value(item)
        for key, item in value.items()
    }


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_node_type(node_type: object) -> str:
    text = _normalize_text(node_type)
    return text or "Unknown"


def normalize_node_id(node_id: object) -> str:
    return _normalize_text(node_id)


def normalize_canonical_node_id(node_id: object) -> str:
    return _normalize_text(node_id).casefold()


def normalize_node_properties(properties: Mapping[str, JSONValue] | None) -> JSONObject:
    if properties is None:
        return {}
    normalized: JSONObject = {}
    for key, value in properties.items():
        k = _normalize_text(key)
        if not k or k in _RESERVED_NODE_KEYS:
            continue
        normalized[k] = value
    return normalized


def map_node_for_interface(node: GraphNode) -> JSONObject:
    return {
        "type": normalize_node_type(node.type),
        "id": normalize_node_id(node.id),
        **normalize_node_properties(node.properties),
    }


def map_edge_for_interface(edge: GraphEdge) -> JSONObject:
    edge_props = edge.properties
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
