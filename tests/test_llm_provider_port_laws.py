from __future__ import annotations


from types import SimpleNamespace

from langchain_core.embeddings import Embeddings

from functorial_kit import Idempotent, Ordered, PortLawSpec, port_laws
from app.services.llm.codex_cli import CodexCliChatModel
from app.services.llm.ports import ChatModelOptions
from mrw_functorial_kit.core.llm_provider_semantics import (
    llm_provider_input_failures,
)


class LawChatModel(CodexCliChatModel):
    def __init__(self, model: str | None = None) -> None:
        self.model = model or "fixture-chat"

    def invoke(self, prompt: object) -> SimpleNamespace:
        return SimpleNamespace(prompt=prompt, model=self.model)


class LawEmbeddings(Embeddings):
    def __init__(self, model: str | None = None) -> None:
        self.model = model or "fixture-embedding"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


class InMemoryLLMProviderPort:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str | None]] = []
        self._chat_models: dict[str | None, LawChatModel] = {}
        self._embedding_models: dict[str | None, LawEmbeddings] = {}

    def get_chat_model(self, options: ChatModelOptions) -> LawChatModel:
        self.requests.append(("chat", options.model))
        return self._chat_models.setdefault(
            options.model,
            LawChatModel(options.model),
        )

    def get_embeddings(self, model: str | None = None) -> LawEmbeddings:
        self.requests.append(("embedding", model))
        return self._embedding_models.setdefault(model, LawEmbeddings(model))


def test_llm_provider_input_failure_family_is_closed() -> None:
    assert llm_provider_input_failures.name == "llm.provider_input.failure"
    assert llm_provider_input_failures.codes == (
        "json_value_invalid",
        "json_number_non_finite",
        "json_key_invalid",
        "config_shape_invalid",
    )


_chat_idempotent: Idempotent[InMemoryLLMProviderPort] = Idempotent(
    "chat option mapping is deterministic",
    lambda port: port.get_chat_model(
        ChatModelOptions(model="fixture", extra={"seed": 7})
    ),
)
_embedding_idempotent: Idempotent[InMemoryLLMProviderPort] = Idempotent(
    "embedding option mapping is deterministic",
    lambda port: port.get_embeddings("fixture-embedding"),
)
_llm_ordered: Ordered[InMemoryLLMProviderPort] = Ordered(
    "provider request order is preserved",
    first=lambda port: port.get_chat_model(ChatModelOptions(model="first")),
    second=lambda port: port.get_embeddings("second"),
    observe=lambda port: list(port.requests),
    commutes=False,
)
_llm_spec: PortLawSpec[InMemoryLLMProviderPort] = PortLawSpec(
    idempotent=[_chat_idempotent, _embedding_idempotent],
    ordered=[_llm_ordered],
)
TestLLMProviderPort = port_laws(
    "LLMProviderPort", InMemoryLLMProviderPort, _llm_spec
)
