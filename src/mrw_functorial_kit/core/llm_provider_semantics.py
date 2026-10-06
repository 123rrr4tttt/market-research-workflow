"""Kit projection for the runtime LLM provider boundary."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family, define_vocabulary


LLMProviderName = Literal["openai", "azure", "ollama", "litellm"]
LLMProviderResolutionFailureCode = Literal["provider_not_registered"]
LLMProviderInputFailureCode = Literal[
    "json_value_invalid",
    "json_number_non_finite",
    "json_key_invalid",
    "config_shape_invalid",
]

llm_provider_names = define_vocabulary(
    "llm.provider.name",
    get_args(LLMProviderName),
)
llm_provider_resolution_failures = define_failure_family(
    "llm.provider_resolution.failure",
    get_args(LLMProviderResolutionFailureCode),
)
llm_provider_input_failures = define_failure_family(
    "llm.provider_input.failure",
    get_args(LLMProviderInputFailureCode),
)


__all__ = [
    "llm_provider_names",
    "llm_provider_input_failures",
    "llm_provider_resolution_failures",
]
