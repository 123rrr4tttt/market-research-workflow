from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.composition.llm import LiteLLMProviderAdapter, configure_llm_providers
from app.services.llm import ports, provider
from app.services.llm.ports import ChatModelOptions


pytestmark = pytest.mark.unit


@dataclass
class RecordingProvider:
    result: Any = "chat-model"
    options: ChatModelOptions | None = None

    def get_chat_model(self, options: ChatModelOptions) -> Any:
        self.options = options
        return self.result

    def get_embeddings(self, model: str | None = None) -> Any:
        return f"embedding-model:{model}"


@pytest.fixture
def isolated_registry() -> None:
    original = dict(ports._LLM_PROVIDER_PORTS)
    ports._LLM_PROVIDER_PORTS.clear()
    try:
        yield
    finally:
        ports._LLM_PROVIDER_PORTS.clear()
        ports._LLM_PROVIDER_PORTS.update(original)


def test_INVARIANT__provider_core_does_not_import_concrete_adapters() -> None:
    source = Path(provider.__file__).read_text(encoding="utf-8")
    assert "app.services.llm.adapters" not in source
    assert "from .adapters" not in source
    assert "langchain_openai" not in source


def test_INVARIANT__composition_registers_runtime_providers(isolated_registry: None) -> None:
    configure_llm_providers()

    assert set(ports._LLM_PROVIDER_PORTS) == {
        "openai",
        "azure",
        "ollama",
        "litellm",
    }
    assert ports._LLM_PROVIDER_PORTS["openai"] is ports._LLM_PROVIDER_PORTS["azure"]


def test_FAILURE_PRESERVED__unregistered_provider_fails_closed(
    monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    monkeypatch.setattr(provider.settings, "llm_provider", "local")

    with pytest.raises(RuntimeError, match="No LLM provider port registered for 'local'"):
        provider.get_chat_model()


def test_provider_preserves_chat_options(
    monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    recorded = RecordingProvider()
    ports.register_llm_provider(("openai",), recorded)
    monkeypatch.setattr(provider.settings, "llm_provider", "openai")

    result = provider.get_chat_model(
        "test-model",
        max_tokens=128,
        top_p=0.7,
        presence_penalty=0.1,
        frequency_penalty=0.2,
        custom_option="value",
    )

    assert result == "chat-model"
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
    created: dict[str, Any] = {}

    def fake_chat(**kwargs: Any) -> SimpleNamespace:
        created["chat"] = kwargs
        return SimpleNamespace(name="chat")

    def fake_embeddings(**kwargs: Any) -> SimpleNamespace:
        created["embeddings"] = kwargs
        return SimpleNamespace(name="embeddings")

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

    assert chat.name == "chat"
    assert created["chat"] == {
        "model": "proxy-model",
        "base_url": "http://litellm.test",
        "api_key": "fixture-key",
        "temperature": 0.3,
        "max_tokens": 64,
        "seed": 7,
    }
    assert embeddings.name == "embeddings"
    assert created["embeddings"] == {
        "model": "custom-embedding",
        "base_url": "http://litellm.test",
        "api_key": "fixture-key",
    }


def test_local_fallback_wraps_registered_chat(
    monkeypatch: pytest.MonkeyPatch, isolated_registry: None
) -> None:
    class Invokable:
        def invoke(self, prompt: Any) -> SimpleNamespace:
            return SimpleNamespace(content="fallback", prompt=prompt)

    recorded = RecordingProvider(result=Invokable())
    ports.register_llm_provider(("litellm",), recorded)
    monkeypatch.setattr(provider.settings, "llm_provider", "litellm")

    chat = provider.get_local_fallback_chat("fallback-model", temperature=0.1)
    result = chat.invoke("prompt")

    assert recorded.options is not None
    assert recorded.options.model == "fallback-model"
    assert recorded.options.temperature == 0.1
    assert chat.with_retry() is chat
    assert result.content == "fallback"
