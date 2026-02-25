from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ...project_customization.interfaces import ChannelHandler, ProjectCustomization, WorkflowDefinition
from .mappings import FIELD_MAPPING, LLM_MAPPING, MENU_CONFIG, WORKFLOW_MAPPING


@dataclass(slots=True)
class DemoProjCustomization(ProjectCustomization):
    project_key: str = "demo_proj"

    def get_menu_config(self) -> Dict[str, Any]:
        return MENU_CONFIG

    def get_workflow_mapping(self) -> Dict[str, WorkflowDefinition]:
        return WORKFLOW_MAPPING

    def get_llm_mapping(self) -> Dict[str, Dict[str, Any]]:
        return LLM_MAPPING

    def get_field_mapping(self) -> Dict[str, Any]:
        return FIELD_MAPPING

    def get_channel_handlers(self) -> Dict[tuple[str, str], ChannelHandler]:
        return {}
