"""香港水资源与水治理：项目绑定的图谱视图声明。

The project owns one unified information topology (57 migrated Rapid 分册).
Its graph entry points are therefore not market/policy/social sources but views
over that one topology: a 总图 plus one view per 分析总纲 chapter. Each entry
binds to an existing projection id and may narrow the topology read model with
``topology_filter``; the shared realizer keeps layout, interaction and rendering.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from ...defaults import DefaultProjectCustomization

# 分析总纲 三、大纲节与信息搜集
OUTLINE_VIEWS: tuple[tuple[str, str], ...] = (
    ("1", "一 供水与水资源物质基础"),
    ("2", "二 排水河流与防洪"),
    ("3", "三 港湾填海与航道"),
    ("4", "四 社会关系、阶级意识与生活"),
)

# Entry points are the existing graph projections; the project selects, orders
# and relabels them instead of introducing project-specific routes.
VIEW_IDS: tuple[str, ...] = (
    "graphDeep",
    "graphMarket",
    "graphPolicy",
    "graphSocial",
    "graphCompany",
    "graphProduct",
    "graphOperation",
)


def _graph_projections() -> list[Dict[str, Any]]:
    projections: list[Dict[str, Any]] = [
        {"id": "graphDeep", "label": "总图"},
    ]
    for (section, label), view_id in zip(OUTLINE_VIEWS, VIEW_IDS[1:5]):
        projections.append({
            "id": view_id,
            "label": label,
            "topology_filter": {"attribute": "outline_section", "contains_any": [section]},
        })
    for view_id in VIEW_IDS[5:]:
        projections.append({"id": view_id, "hidden": True})
    projections.append({"id": "graphBuilder", "label": "新建图谱"})
    return projections


@dataclass(slots=True)
class HkWaterInvestigationCustomization(DefaultProjectCustomization):
    project_key: str = "hk_water_investigation"
    _graph_projections: list[Dict[str, Any]] = field(
        default_factory=_graph_projections, init=False, repr=False,
    )

    def get_field_mapping(self) -> Dict[str, Any]:
        return {"graph_projections": list(self._graph_projections)}

    def get_report_title(self) -> str:
        return "香港水资源与水治理"
