from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Self, assert_type

import pytest
from functorial_kit import Failure
from pydantic import SecretStr
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import (
    AzureChatOpenAI,
    AzureOpenAIEmbeddings,
    ChatOpenAI,
    OpenAIEmbeddings,
)

from app.composition.llm import LiteLLMProviderAdapter, configure_llm_providers
from app.models.entities import LlmServiceConfig
from app.services.llm import config_loader
from app.services.llm import provider
from app.services.llm.codex_cli import CodexCliChatModel
from app.services.llm.adapters.langchain_provider import LangChainProviderAdapter
from app.services.llm.ports import (
    ChatModelOptions,
    LLMJsonValue,
    LLMProviderPort,
    parse_llm_json_object,
    register_llm_provider,
    reset_llm_provider_registry,
    resolve_llm_provider,
    try_parse_llm_json_object,
)
from mrw_functorial_kit.core.llm_provider_semantics import (
    llm_provider_input_failures,
)

if TYPE_CHECKING:
    from app.services.llm.ports import ChatModel, EmbeddingModel


pytestmark = pytest.mark.unit


class FixtureChatModel(CodexCliChatModel):
    def __init__(self, content: object) -> None:
        self.content = content

    def invoke(self, prompt: object) -> SimpleNamespace:
        return SimpleNamespace(content=self.content, prompt=prompt)


class FixtureEmbeddings(Embeddings):
    def __init__(self, model: str | None = None) -> None:
        self.model = model or "fixture-embedding"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


@dataclass
class RecordingProvider:
    result: ChatModel
    options: ChatModelOptions | None = None

    def get_chat_model(self, options: ChatModelOptions) -> ChatModel:
        self.options = options
        return self.result

    def get_embeddings(self, model: str | None = None) -> EmbeddingModel:
        return FixtureEmbeddings(model)


@pytest.fixture
def isolated_registry() -> Iterator[None]:
    reset_llm_provider_registry()
    try:
        yield
    finally:
        reset_llm_provider_registry()


def test_INVARIANT__provider_core_does_not_import_concrete_adapters() -> None:
    source = Path(provider.__file__).read_text(encoding="utf-8")
    assert "app.services.llm.adapters" not in source
    assert "from .adapters" not in source
    assert "langchain_openai" not in source


def test_INVARIANT__composition_registers_runtime_providers(isolated_registry: None) -> None:
    configure_llm_providers()

    providers = {
        name: resolve_llm_provider(name)
        for name in ("openai", "azure", "ollama", "litellm")
    }
    assert len({id(port) for port in providers.values()}) == 2
    assert providers["openai"] is providers["azure"] is providers["ollama"]
    assert providers["litellm"] is not providers["openai"]


def test_FAILURE_PRESERVED__unregistered_provider_fails_closed(
    monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    monkeypatch.setattr(provider.settings, "llm_provider", "local")

    with pytest.raises(RuntimeError, match="No LLM provider port registered for 'local'"):
        provider.get_chat_model()


def test_provider_preserves_chat_options(
    monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    recorded = RecordingProvider(result=FixtureChatModel("chat-model"))
    register_llm_provider(("openai",), recorded)
    monkeypatch.setattr(provider.settings, "llm_provider", "openai")

    result = provider.get_chat_model(
        "test-model",
        max_tokens=128,
        top_p=0.7,
        presence_penalty=0.1,
        frequency_penalty=0.2,
        custom_option="value",
    )

    if TYPE_CHECKING:
        assert_type(result, ChatModel)
    assert isinstance(result, FixtureChatModel)
    assert result.content == "chat-model"
    assert recorded.options is not None
    assert recorded.options.model == "test-model"
    assert recorded.options.temperature is None
    assert recorded.options.max_tokens == 128
    assert recorded.options.top_p == 0.7
    assert recorded.options.presence_penalty == 0.1
    assert recorded.options.frequency_penalty == 0.2
    assert recorded.options.extra == {"custom_option": "value"}


def test_litellm_adapter_constructs_openai_compatible_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: dict[str, object] = {}

    def fake_chat(**kwargs: LLMJsonValue) -> ChatOpenAI:
        created["chat"] = kwargs
        return ChatOpenAI(api_key=SecretStr("fixture-key"))

    def fake_embeddings(**kwargs: LLMJsonValue) -> OpenAIEmbeddings:
        created["embeddings"] = kwargs
        return OpenAIEmbeddings(api_key=SecretStr("fixture-key"))

    monkeypatch.setattr("app.composition.llm.ChatOpenAI", fake_chat)
    monkeypatch.setattr("app.composition.llm.OpenAIEmbeddings", fake_embeddings)
    monkeypatch.setattr(provider.settings, "litellm_api_base", "http://litellm.test")
    monkeypatch.setattr(provider.settings, "litellm_api_key", "fixture-key")
    monkeypatch.setattr(provider.settings, "embedding_model", "fixture-embedding")

    adapter = LiteLLMProviderAdapter()
    chat = adapter.get_chat_model(
        ChatModelOptions(
            model="proxy-model",
            temperature=0.3,
            max_tokens=64,
            extra={"codex_cli_timeout_seconds": 10, "seed": 7},
        )
    )
    embeddings = adapter.get_embeddings("custom-embedding")

    assert isinstance(chat, ChatOpenAI)
    assert created["chat"] == {
        "model": "proxy-model",
        "base_url": "http://litellm.test",
        "api_key": SecretStr("fixture-key"),
        "temperature": 0.3,
        "max_tokens": 64,
        "seed": 7,
    }
    assert isinstance(embeddings, OpenAIEmbeddings)
    assert created["embeddings"] == {
        "model": "custom-embedding",
        "base_url": "http://litellm.test",
        "api_key": SecretStr("fixture-key"),
    }


def test_langchain_adapter_returns_platform_model_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider.settings, "llm_provider", "openai")
    monkeypatch.setattr(provider.settings, "openai_api_key", "fixture-key")
    monkeypatch.setattr(provider.settings, "embedding_model", "fixture-embedding")
    monkeypatch.setattr(provider.settings, "codex_cli_llm_preferred", False)

    adapter = LangChainProviderAdapter()
    chat = adapter.get_chat_model(ChatModelOptions(model="gpt-test"))
    embeddings = adapter.get_embeddings()

    assert isinstance(chat, BaseChatModel)
    assert isinstance(chat, ChatOpenAI)
    assert chat.model_name == "gpt-test"
    assert isinstance(embeddings, Embeddings)
    assert isinstance(embeddings, OpenAIEmbeddings)
    assert embeddings.model == "fixture-embedding"


def test_langchain_adapter_preserves_unknown_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider.settings, "llm_provider", "local")
    adapter = LangChainProviderAdapter()

    with pytest.raises(ValueError, match="未知的 llm_provider: local"):
        adapter.get_chat_model(ChatModelOptions())
    with pytest.raises(ValueError, match="未知的 llm_provider: local"):
        adapter.get_embeddings("fixture-embedding")


def test_llm_options_keep_the_extension_axis_json_shaped() -> None:
    options = ChatModelOptions(
        extra={
            "seed": 7,
            "nested": {"values": [1, True, None, "fixture"]},
        }
    )

    assert options.extra is not None
    assert options.extra == {
        "seed": 7,
        "nested": {"values": [1, True, None, "fixture"]},
    }

    with pytest.raises(TypeError, match="extra must contain only finite JSON values"):
        ChatModelOptions(extra={"nested": {"values": [1, {"bad"}, None]}})


def test_llm_provider_input_parser_classifies_all_malformed_branches() -> None:
    malformed_key: dict[object, object] = {1: "value"}
    cases: tuple[tuple[object, str, str], ...] = (
        ({"nested": {"value": {"bad"}}}, "json_value_invalid", "extra.nested.value"),
        ({"temperature": float("nan")}, "json_number_non_finite", "extra.temperature"),
        (malformed_key, "json_key_invalid", "extra"),
        (["not", "an", "object"], "config_shape_invalid", "extra"),
    )

    for value, expected_code, expected_path in cases:
        failure = try_parse_llm_json_object(value, field="extra")

        assert isinstance(failure, Failure)
        assert llm_provider_input_failures.matches(failure)
        assert failure.code == expected_code
        assert failure.context == {
            "owner": "llm.ports.input_parser",
            "operation": "parse_llm_json",
            "path": expected_path,
            "public_exception": "TypeError",
            "public_message": "extra must contain only finite JSON values",
            "witness": "test:test_llm_provider_input_parser_classifies_all_malformed_branches",
        }


def test_llm_provider_input_parser_preserves_type_error_abi_and_cause() -> None:
    malformed_key: dict[object, object] = {1: "value"}
    cases: tuple[tuple[object, str], ...] = (
        (
            {"nested": {"values": [1, {"bad"}, None]}},
            "extra.nested.values[1] has unsupported LLM JSON value set",
        ),
        (
            {"temperature": float("inf")},
            "extra.temperature must be a finite JSON number",
        ),
        (malformed_key, "extra must contain only string JSON keys"),
        (["not", "an", "object"], "extra must be a JSON object"),
    )

    for value, cause_message in cases:
        with pytest.raises(
            TypeError,
            match=r"^extra must contain only finite JSON values$",
        ) as captured:
            parse_llm_json_object(value, field="extra")

        assert isinstance(captured.value.__cause__, TypeError)
        assert str(captured.value.__cause__) == cause_message


def test_langchain_adapter_rejects_wrongly_shaped_codex_options() -> None:
    adapter = LangChainProviderAdapter()

    with pytest.raises(TypeError, match="extra.codex_cli_timeout_seconds"):
        adapter.get_chat_model(
            ChatModelOptions(extra={"codex_cli_timeout_seconds": "10"})
        )
    with pytest.raises(TypeError, match="extra.codex_cli_reasoning_effort"):
        adapter.get_chat_model(
            ChatModelOptions(extra={"codex_cli_reasoning_effort": 7})
        )


def test_langchain_adapter_constructs_azure_models_with_current_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider.settings, "llm_provider", "azure")
    monkeypatch.setattr(provider.settings, "azure_api_base", "http://azure.test")
    monkeypatch.setattr(provider.settings, "azure_api_key", "fixture-key")
    monkeypatch.setattr(provider.settings, "azure_api_version", "fixture-version")
    monkeypatch.setattr(provider.settings, "azure_chat_deployment", "chat")
    monkeypatch.setattr(provider.settings, "azure_embedding_deployment", "embedding")

    adapter = LangChainProviderAdapter()
    chat = adapter.get_chat_model(
        ChatModelOptions(model="fixture-model", max_tokens=64)
    )
    embeddings = adapter.get_embeddings("fixture-embedding")

    assert isinstance(chat, AzureChatOpenAI)
    assert chat.deployment_name == "chat"
    assert isinstance(embeddings, AzureOpenAIEmbeddings)
    assert embeddings.deployment == "embedding"


def test_local_fallback_wraps_registered_chat(
    monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    recorded = RecordingProvider(result=FixtureChatModel("fallback"))
    register_llm_provider(("litellm",), recorded)
    monkeypatch.setattr(provider.settings, "llm_provider", "litellm")

    chat = provider.get_local_fallback_chat("fallback-model", temperature=0.1)
    result = chat.invoke("prompt")

    assert recorded.options is not None
    assert recorded.options.model == "fallback-model"
    assert recorded.options.temperature == 0.1
    assert chat.with_retry() is chat
    assert result.content == "fallback"


def test_config_loader_reads_typed_orm_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = LlmServiceConfig(
        service_name="policy_summary",
        system_prompt="system prompt",
        user_prompt_template="base prompt",
        model="fixture-model",
        temperature=Decimal("0.00"),
        max_tokens=512,
        top_p=Decimal("0.7500"),
        presence_penalty=Decimal("0.0000"),
        frequency_penalty=Decimal("-0.2500"),
        enabled=True,
    )

    class ScalarResult:
        def scalar_one_or_none(self) -> LlmServiceConfig:
            return row

    class FakeSession:
        def __enter__(self) -> Self:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

        def execute(self, statement: object) -> ScalarResult:
            return ScalarResult()

    session = FakeSession()
    monkeypatch.setattr(config_loader, "SessionLocal", lambda: session)

    loaded = config_loader.get_llm_config("policy_summary")
    assert loaded == {
        "service_name": "policy_summary",
        "system_prompt": "system prompt",
        "user_prompt_template": "base prompt",
        "model": "fixture-model",
        "temperature": None,
        "max_tokens": 512,
        "top_p": 0.75,
        "presence_penalty": None,
        "frequency_penalty": -0.25,
    }


@pytest.mark.skipif(
    not TYPE_CHECKING,
    reason="wrong provider signatures are enforced by the Pyright negative selector",
)
def test_STATIC_NEGATIVE__wrong_provider_shapes_are_rejected() -> None:
    if TYPE_CHECKING:

        class WrongProvider:
            def get_chat_model(self, options: int) -> int:
                return options

            def get_embeddings(self, model: int) -> int:
                return model

        wrong_port: LLMProviderPort = WrongProvider()
        assert_type(wrong_port, LLMProviderPort)
