from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .interfaces import ChannelHandler, NewsResourceHandler, ProjectCustomization, WorkflowDefinition


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

    def get_domain_tokens(self) -> Optional[list[str]]:
        return None

    def get_report_title(self) -> str:
        return "商业报告"

    def get_news_resource_handlers(self) -> Dict[str, NewsResourceHandler]:
        return {}

    def get_shared_news_resource_handlers(self) -> Dict[str, NewsResourceHandler]:
        return {}
