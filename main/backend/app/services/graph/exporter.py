"""图谱导出功能"""
from __future__ import annotations

import json
import logging
from typing import Dict, List, Any, Optional
from collections import Counter

from .models import Graph, GraphNode, GraphEdge

logger = logging.getLogger(__name__)


def export_to_json(graph: Graph) -> Dict[str, Any]:
    """
    将图谱导出为JSON格式
    
    输出格式：
    {
        "graph_schema_version": "v1",
        "nodes": [
            {"type": "Post", "id": "123", "properties": {...}},
            ...
        ],
        "edges": [
            {
                "type": "MENTIONS_KEYWORD",
                "from": {"type": "Post", "id": "123"},
                "to": {"type": "Keyword", "id": "sha1:..."},
                "properties": {"weight": 1.0}
            },
            ...
        ]
    }
    """
    nodes_list = []
    for node_key, node in graph.nodes.items():
        node_dict = {
            "type": node.type,
            "id": node.id,
            **node.properties
        }
        nodes_list.append(node_dict)
    
    edges_list = []
    for edge in graph.edges:
        edge_dict = {
            "type": edge.type,
            "from": {
                "type": edge.from_node.type,
                "id": edge.from_node.id
            },
            "to": {
                "type": edge.to_node.type,
                "id": edge.to_node.id
            },
            **edge.properties
        }
        edges_list.append(edge_dict)
    
    return {
        "graph_schema_version": graph.schema_version,
        "nodes": nodes_list,
        "edges": edges_list
    }


def validate_graph(graph: Graph) -> Dict[str, Any]:
    """
    校验图谱一致性
    
    检查项：
    1. 节点ID唯一性
    2. 边端点存在性
    3. 空值比例告警
    
    Returns:
        校验结果字典，包含 warnings 和 errors
    """
    errors: List[str] = []
    warnings: List[str] = []
    
    # 1. 检查节点ID唯一性
    node_ids: Dict[str, List[str]] = {}
    for node_key, node in graph.nodes.items():
        node_id = f"{node.type}:{node.id}"
        if node_id not in node_ids:
            node_ids[node_id] = []
        node_ids[node_id].append(node_key)
    
    duplicate_ids = {k: v for k, v in node_ids.items() if len(v) > 1}
    if duplicate_ids:
        errors.append(f"发现重复节点ID: {duplicate_ids}")
    
    # 2. 检查边端点存在性
    missing_nodes = []
    for edge in graph.edges:
        from_key = f"{edge.from_node.type}:{edge.from_node.id}"
        to_key = f"{edge.to_node.type}:{edge.to_node.id}"
        
        if from_key not in graph.nodes:
            missing_nodes.append(f"边 {edge.type} 的源节点不存在: {from_key}")
        if to_key not in graph.nodes:
            missing_nodes.append(f"边 {edge.type} 的目标节点不存在: {to_key}")
    
    if missing_nodes:
        errors.extend(missing_nodes[:10])  # 只显示前10个错误
        if len(missing_nodes) > 10:
            errors.append(f"... 还有 {len(missing_nodes) - 10} 个类似错误")
    
    # 3. 检查空值比例
    total_nodes = len(graph.nodes)
    if total_nodes > 0:
        empty_property_nodes = 0
        for node in graph.nodes.values():
            if not node.properties or all(v is None for v in node.properties.values()):
                empty_property_nodes += 1
        
        empty_ratio = empty_property_nodes / total_nodes
        if empty_ratio > 0.3:
            warnings.append(f"空属性节点比例较高: {empty_ratio:.2%} ({empty_property_nodes}/{total_nodes})")
    
    # 统计信息
    node_type_counts = Counter(node.type for node in graph.nodes.values())
    edge_type_counts = Counter(edge.type for edge in graph.edges)
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "statistics": {
            "total_nodes": total_nodes,
            "total_edges": len(graph.edges),
            "node_types": dict(node_type_counts),
            "edge_types": dict(edge_type_counts),
        }
    }


def export_to_json_file(graph: Graph, output_path: str, validate: bool = True) -> Dict[str, Any]:
    """
    将图谱导出为JSON文件
    
    Args:
        graph: 要导出的图谱
        output_path: 输出文件路径
        validate: 是否在导出前进行校验
    
    Returns:
        校验结果（如果validate=True）
    """
    if validate:
        validation_result = validate_graph(graph)
        if not validation_result["valid"]:
            logger.warning(f"图谱校验失败: {validation_result['errors']}")
        if validation_result["warnings"]:
            logger.warning(f"图谱校验警告: {validation_result['warnings']}")
    
    json_data = export_to_json(graph)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
    
    logger.info(f"图谱已导出到: {output_path}")
    logger.info(f"节点数: {len(json_data['nodes'])}, 边数: {len(json_data['edges'])}")
    
    if validate:
        return validation_result
    return {}

