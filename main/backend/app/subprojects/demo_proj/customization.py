from __future__ import annotations

from dataclasses import dataclass

from ...project_customization.interfaces import (
    ChannelHandler,
    CustomizationJsonObject,
    NewsResourceHandler,
    ProjectCustomization,
    WorkflowDefinition,
)
from .mappings import FIELD_MAPPING, LLM_MAPPING, MENU_CONFIG, WORKFLOW_MAPPING


@dataclass(slots=True)
class DemoProjCustomization(ProjectCustomization):
    project_key: str = "demo_proj"

    def get_menu_config(self) -> CustomizationJsonObject:
        return MENU_CONFIG

    def get_workflow_mapping(self) -> dict[str, WorkflowDefinition]:
        return WORKFLOW_MAPPING

    def get_llm_mapping(self) -> dict[str, CustomizationJsonObject]:
        return LLM_MAPPING

    def get_field_mapping(self) -> CustomizationJsonObject:
        return FIELD_MAPPING

    def get_channel_handlers(self) -> dict[tuple[str, str], ChannelHandler]:
        return {}

    def get_social_keyword_guidelines(self) -> str | None:
        return (
            "生成要求：\n"
            "1. 所有搜索关键词需紧扣具身智能、机器人、自主系统主题；\n"
            "2. 结合提供的基础关键词提炼同义词、动名词、复合短语；\n"
            "3. 每条关键词独立成行，不附加额外说明。"
        )

    def get_domain_tokens(self) -> list[str] | None:
        return ["embodied", "robot", "robotics", "ai", "humanoid", "autonomous"]

    def get_report_title(self) -> str:
        return "具身智能情报简报"

    def get_news_resource_handlers(self) -> dict[str, NewsResourceHandler]:
        return {}

    def get_shared_news_resource_handlers(self) -> dict[str, NewsResourceHandler]:
        return {}
