from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .interfaces import ChannelHandler, ProjectCustomization, WorkflowDefinition


@dataclass(slots=True)
class DefaultProjectCustomization(ProjectCustomization):
    project_key: str = "default"

    def get_menu_config(self) -> Dict[str, Any]:
        return {"items": []}

    def get_workflow_mapping(self) -> Dict[str, WorkflowDefinition]:
        return {}

    def get_llm_mapping(self) -> Dict[str, Dict[str, Any]]:
        return {}

    def get_field_mapping(self) -> Dict[str, Any]:
        return {}

    def get_channel_handlers(self) -> Dict[tuple[str, str], ChannelHandler]:
        return {}

    def suggest_keywords(
        self,
        topic: str,
        base_keywords: Optional[list[str]] = None,
        platform: Optional[str] = None,
        language: str = "zh",
    ) -> Optional[Dict[str, Any]]:
        """Default: no project-specific suggestion; trunk uses built-in LLM service."""
        return None
