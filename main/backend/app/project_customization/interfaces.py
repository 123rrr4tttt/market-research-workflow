from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol


ChannelHandler = Callable[[Dict[str, Any], Dict[str, Any], Optional[str]], Dict[str, Any]]

# News resource handler: (limit: int) -> dict
NewsResourceHandler = Callable[[int], Dict[str, Any]]


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

    def get_social_keyword_guidelines(self) -> Optional[str]:
        """Optional guidelines appended to social_keyword_generation prompt.

        Return None to skip appending (use template as-is).
        Return str to append to template (e.g. domain-specific constraints).
        """
        ...

    def get_domain_tokens(self) -> Optional[list[str]]:
        """Optional domain tokens for keyword filtering.

        Return None or empty to allow all keywords (no domain filter).
        Return list of tokens to filter: only keywords containing these tokens pass.
        """
        ...

    def get_report_title(self) -> str:
        """Report title for generated reports. Fallback: 商业报告."""
        ...

    def get_news_resource_handlers(self) -> Dict[str, NewsResourceHandler]:
        """Project-specific (子项目库) news ingest handlers. resource_id -> (limit) -> result dict.

        All behaviors must follow 总库/子项目库 dichotomy. This returns project pool only.
        Shared pool (总库) handlers are defined elsewhere (e.g. trunk defaults, shared registry).
        Effective = shared + project merged (project overrides shared on same key).
        """
        ...

    def get_shared_news_resource_handlers(self) -> Dict[str, NewsResourceHandler]:
        """Shared (总库) news ingest handlers. resource_id -> (limit) -> result dict.

        Cross-project generic sources (e.g. google_news, market_info). Return {} if none.
        """
        ...
