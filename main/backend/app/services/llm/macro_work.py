"""Local contracts for ordinary, single-call LLM work.

These bindings describe business work and its existing boundaries. They do not
mount a native Agent Core or change the model provider execution path.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class MacroWorkBinding:
    """A small semantic binding for one existing LLM-backed business action."""

    work_id: str
    entrypoint: str
    skill_path: str
    input_fields: Tuple[str, ...]
    context_sources: Tuple[str, ...]
    method: str
    result_contract: str
    failure_contract: str
    effects: Tuple[str, ...]
    consumers: Tuple[str, ...]
    execution_boundary: str


KEYWORD_GENERATION_WORK = MacroWorkBinding(
    work_id="social-keyword-generation",
    entrypoint="app.services.keyword_generation.generate_social_keywords",
    skill_path="main/backend/skills/keyword-generation/SKILL.md",
    input_fields=("topic", "language", "platform", "base_keywords", "return_combined"),
    context_sources=(
        "social_keyword_generation prompt configuration",
        "keyword_generation prompt configuration for list compatibility",
        "project social keyword guidelines",
    ),
    method=(
        "Generate social search terms and, for combined mode, subreddit discovery terms; "
        "parse the configured model response according to the requested output mode."
    ),
    result_contract=(
        "combined mode returns search_keywords and subreddit_keywords; legacy mode returns "
        "a keyword list; bilingual search results retain Chinese and English coverage."
    ),
    failure_contract=(
        "Keep the existing no-key and exception fallbacks, malformed/empty-response "
        "fallbacks, cleaning, and output limits."
    ),
    effects=("clean keywords", "store non-empty search keywords for platform"),
    consumers=(
        "app.api.discovery keyword suggestion",
        "app.services.ingest.social collection setup",
        "project-specific social keyword customization",
    ),
    execution_boundary=(
        "Existing get_chat_model/provider and one model.invoke call; no recursive Agent "
        "provider, added tool loop, or native Core execution claim."
    ),
)
