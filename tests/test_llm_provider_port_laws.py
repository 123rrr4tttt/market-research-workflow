from __future__ import annotations

from dataclasses import dataclass
from functorial_kit import Idempotent, Ordered, PortLawSpec, port_laws

@dataclass
class ChatModelOptions:
    model: str | None = None
    temperature: float | None = None
    extra: dict[str, object] | None = None


class InMemoryLLMProviderPort:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str | None]] = []

    def get_chat_model(self, options: ChatModelOptions) -> dict[str, object]:
        self.requests.append(("chat", options.model))
        return {
            "model": options.model,
            "temperature": options.temperature,
            "extra": dict(options.extra or {}),
        }

    def get_embeddings(self, model: str | None = None) -> dict[str, object]:
        self.requests.append(("embedding", model))
        return {"model": model}


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
