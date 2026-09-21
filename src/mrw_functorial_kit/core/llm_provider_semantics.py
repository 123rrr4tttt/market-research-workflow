"""Kit projection for the runtime LLM provider boundary."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family, define_vocabulary


LLMProviderName = Literal["openai", "azure", "ollama", "litellm"]
LLMProviderResolutionFailureCode = Literal["provider_not_registered"]

llm_provider_names = define_vocabulary(
    "llm.provider.name",
    get_args(LLMProviderName),
)
llm_provider_resolution_failures = define_failure_family(
    "llm.provider_resolution.failure",
    get_args(LLMProviderResolutionFailureCode),
)


__all__ = [
    "llm_provider_names",
    "llm_provider_resolution_failures",
]
