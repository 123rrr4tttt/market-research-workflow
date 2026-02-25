from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol


ChannelHandler = Callable[[Dict[str, Any], Dict[str, Any], Optional[str]], Dict[str, Any]]


@dataclass(slots=True)
class WorkflowStep:
    handler: str
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    name: str | None = None


@dataclass(slots=True)
class WorkflowDefinition:
    steps: list[WorkflowStep] = field(default_factory=list)


class ProjectCustomization(Protocol):
    project_key: str

    def get_menu_config(self) -> Dict[str, Any]:
        ...

    def get_workflow_mapping(self) -> Dict[str, WorkflowDefinition]:
        ...

    def get_llm_mapping(self) -> Dict[str, Dict[str, Any]]:
        ...

    def get_field_mapping(self) -> Dict[str, Any]:
        ...

    def get_channel_handlers(self) -> Dict[tuple[str, str], ChannelHandler]:
        ...

    def suggest_keywords(
        self,
        topic: str,
        base_keywords: Optional[List[str]] = None,
        platform: Optional[str] = None,
        language: str = "zh",
    ) -> Optional[Dict[str, Any]]:
        """Keyword suggestion for collection workflow.

        Subprojects override to provide domain-specific suggestions.
        Return None to use trunk default (LLM-based generation).
        Return dict with keys: search_keywords (list), optionally subreddit_keywords (list).
        """
        ...
