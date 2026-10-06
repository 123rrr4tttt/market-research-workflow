from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import TYPE_CHECKING, Dict, List, NoReturn, Optional, Protocol, TypeAlias, TypeGuard, Union

from functorial_kit import Failure
from mrw_functorial_kit.core.llm_provider_semantics import (
    LLMProviderInputFailureCode,
    llm_provider_input_failures,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.embeddings import Embeddings

    from app.services.llm.codex_cli import CodexCliChatModel

    ChatModel: TypeAlias = BaseChatModel | CodexCliChatModel
    EmbeddingModel: TypeAlias = Embeddings


LLMJsonValue: TypeAlias = Union[
    None,
    bool,
    int,
    float,
    str,
    List["LLMJsonValue"],
    Dict[str, "LLMJsonValue"],
]
LLMConfig: TypeAlias = Mapping[str, LLMJsonValue]
_LLM_INPUT_WITNESS = (
    "test:test_llm_provider_input_parser_classifies_all_malformed_branches"
)


def _is_plain_json_object(value: object) -> TypeGuard[dict[object, object]]:
    return type(value) is dict


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _llm_provider_input_code(value: str) -> LLMProviderInputFailureCode:
    if value == "json_number_non_finite":
        return "json_number_non_finite"
    if value == "json_key_invalid":
        return "json_key_invalid"
    if value == "config_shape_invalid":
        return "config_shape_invalid"
    return "json_value_invalid"


def _llm_provider_input_failure(
    code: LLMProviderInputFailureCode,
    message: str,
    *,
    path: str,
    public_message: str | None = None,
) -> Failure:
    return llm_provider_input_failures.fail(
        code,
        message,
        {
            "owner": "llm.ports.input_parser",
            "operation": "parse_llm_json",
            "path": path,
            "public_exception": "TypeError",
            "public_message": public_message or message,
            "witness": _LLM_INPUT_WITNESS,
        },
    )


def try_parse_llm_json_value(
    value: object,
    *,
    path: str = "value",
) -> LLMJsonValue | Failure:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return _llm_provider_input_failure(
                "json_number_non_finite",
                f"{path} must be a finite JSON number",
                path=path,
            )
        return value
    if _is_object_list(value):
        normalized_items: list[LLMJsonValue] = []
        for index, item in enumerate(value):
            parsed = try_parse_llm_json_value(item, path=f"{path}[{index}]")
            if isinstance(parsed, Failure):
                return parsed
            normalized_items.append(parsed)
        return normalized_items
    if _is_plain_json_object(value):
        normalized_object: dict[str, LLMJsonValue] = {}
        for key, item in value.items():
            if type(key) is not str:
                return _llm_provider_input_failure(
                    "json_key_invalid",
                    f"{path} must contain only string JSON keys",
                    path=path,
                )
            parsed = try_parse_llm_json_value(item, path=f"{path}.{key}")
            if isinstance(parsed, Failure):
                return parsed
            normalized_object[key] = parsed
        return normalized_object
    return _llm_provider_input_failure(
        "json_value_invalid",
        f"{path} has unsupported LLM JSON value {type(value).__name__}",
        path=path,
    )


def try_parse_llm_json_object(
    value: object,
    *,
    field: str,
) -> dict[str, LLMJsonValue] | Failure:
    public_message = f"{field} must contain only finite JSON values"
    if not _is_plain_json_object(value):
        return _llm_provider_input_failure(
            "config_shape_invalid",
            f"{field} must be a JSON object",
            path=field,
            public_message=public_message,
        )
    parsed = try_parse_llm_json_value(value, path=field)
    if isinstance(parsed, Failure):
        return _llm_provider_input_failure(
            _llm_provider_input_code(parsed.code),
            parsed.message,
            path=str((parsed.context or {}).get("path") or field),
            public_message=public_message,
        )
    if isinstance(parsed, dict):
        return parsed
    return _llm_provider_input_failure(
        "config_shape_invalid",
        f"{field} must be a JSON object",
        path=field,
        public_message=public_message,
    )


def _raise_llm_provider_input_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    public_message = str(context.get("public_message") or failure.message)
    cause = TypeError(failure.message)
    # kit:boundary owner=llm.ports.input_parser class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=llm.provider_input.failure witness=test:test_llm_provider_input_parser_preserves_type_error_abi_and_cause
    raise TypeError(public_message) from cause


def parse_llm_json_object(
    value: object,
    *,
    field: str,
) -> dict[str, LLMJsonValue]:
    parsed = try_parse_llm_json_object(value, field=field)
    if isinstance(parsed, Failure):
        _raise_llm_provider_input_failure(parsed)
    return parsed


@dataclass
class ChatModelOptions:
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    extra: dict[str, LLMJsonValue] | None = None

    def __post_init__(self) -> None:
        if self.extra is None:
            return
        self.extra = parse_llm_json_object(self.extra, field="extra")


class ChatPort(Protocol):
    def get_chat_model(self, options: ChatModelOptions) -> "ChatModel":
        ...


class EmbeddingPort(Protocol):
    def get_embeddings(self, model: Optional[str] = None) -> "EmbeddingModel":
        ...


class PromptConfigPort(Protocol):
    def get_config(self, service_name: str) -> LLMConfig | None:
        ...


class LLMProviderPort(Protocol):
    """Runtime provider boundary shared by chat and embedding requests."""

    def get_chat_model(self, options: ChatModelOptions) -> "ChatModel":
        ...

    def get_embeddings(self, model: Optional[str] = None) -> "EmbeddingModel":
        ...


LLM_PROVIDER_NOT_REGISTERED = "provider_not_registered"


class LLMProviderResolutionError(RuntimeError):
    """The composition root did not install the requested provider."""

    code = LLM_PROVIDER_NOT_REGISTERED


_LLM_PROVIDER_PORTS: dict[str, LLMProviderPort] = {}


def register_llm_provider(provider_names: tuple[str, ...], port: LLMProviderPort) -> None:
    for provider_name in provider_names:
        _LLM_PROVIDER_PORTS[provider_name.lower()] = port


def reset_llm_provider_registry() -> None:
    _LLM_PROVIDER_PORTS.clear()


def resolve_llm_provider(provider_name: str) -> LLMProviderPort:
    normalized = provider_name.strip().lower()
    port = _LLM_PROVIDER_PORTS.get(normalized)
    if port is None:
        # kit:boundary
        raise LLMProviderResolutionError(
            f"No LLM provider port registered for {normalized!r}"
        )
    return port
