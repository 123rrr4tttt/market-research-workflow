from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NotRequired, Protocol, TypeAlias, TypedDict, runtime_checkable


CustomizationJsonAtom: TypeAlias = None | bool | int | float | str
CustomizationJsonValue: TypeAlias = (
    CustomizationJsonAtom
    | list["CustomizationJsonValue"]
    | dict[str, "CustomizationJsonValue"]
)
CustomizationJsonObject: TypeAlias = dict[str, CustomizationJsonValue]

ChannelHandler = Callable[
    [CustomizationJsonObject, CustomizationJsonObject, str | None],
    CustomizationJsonObject,
]

# News resource handler: (limit: int) -> dict
NewsResourceHandler = Callable[[int], CustomizationJsonObject]


class KeywordSuggestion(TypedDict):
    search_keywords: list[str]
    subreddit_keywords: NotRequired[list[str]]


@dataclass(slots=True)
class WorkflowStep:
    handler: str
    params: CustomizationJsonObject = field(default_factory=lambda: {})
    enabled: bool = True
    name: str | None = None


@dataclass(slots=True)
class WorkflowDefinition:
    steps: list[WorkflowStep] = field(default_factory=lambda: [])


@runtime_checkable
class ProjectCustomization(Protocol):
    project_key: str

    def get_menu_config(self) -> CustomizationJsonObject:
        ...

    def get_workflow_mapping(self) -> dict[str, WorkflowDefinition]:
        ...

    def get_llm_mapping(self) -> dict[str, CustomizationJsonObject]:
        ...

    def get_field_mapping(self) -> CustomizationJsonObject:
        ...

    def get_channel_handlers(self) -> dict[tuple[str, str], ChannelHandler]:
        ...

    def suggest_keywords(
        self,
        topic: str,
        base_keywords: list[str] | None = None,
        platform: str | None = None,
        language: str = "zh",
    ) -> CustomizationJsonObject | None:
        """Keyword suggestion for collection workflow.

        Subprojects override to provide domain-specific suggestions.
        Return None to use trunk default (LLM-based generation).
        Return dict with keys: search_keywords (list), optionally subreddit_keywords (list).
        """
        ...

    def get_social_keyword_guidelines(self) -> str | None:
        """Optional guidelines appended to social_keyword_generation prompt.

        Return None to skip appending (use template as-is).
        Return str to append to template (e.g. domain-specific constraints).
        """
        ...

    def get_domain_tokens(self) -> list[str] | None:
        """Optional domain tokens for keyword filtering.

        Return None or empty to allow all keywords (no domain filter).
        Return list of tokens to filter: only keywords containing these tokens pass.
        """
        ...

    def get_report_title(self) -> str:
        """Report title for generated reports. Fallback: 商业报告."""
        ...

    def get_news_resource_handlers(self) -> dict[str, NewsResourceHandler]:
        """Project-specific (子项目库) news ingest handlers. resource_id -> (limit) -> result dict.

        All behaviors must follow 总库/子项目库 dichotomy. This returns project pool only.
        Shared pool (总库) handlers are defined elsewhere (e.g. trunk defaults, shared registry).
        Effective = shared + project merged (project overrides shared on same key).
        """
        ...

    def get_shared_news_resource_handlers(self) -> dict[str, NewsResourceHandler]:
        """Shared (总库) news ingest handlers. resource_id -> (limit) -> result dict.

        Cross-project generic sources (e.g. google_news, market_info). Return {} if none.
        """
        ...
