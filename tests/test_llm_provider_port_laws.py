from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from functorial_kit import Idempotent, Ordered, PortLawSpec, port_laws

@dataclass
class ChatModelOptions:
    model: str | None = None
    temperature: float | None = None
    extra: dict[str, Any] | None = None


@dataclass
class InMemoryLLMProviderPort:
    requests: list[tuple[str, str | None]] = field(default_factory=list)

    def get_chat_model(self, options: ChatModelOptions) -> dict[str, Any]:
        self.requests.append(("chat", options.model))
        return {
            "model": options.model,
            "temperature": options.temperature,
            "extra": dict(options.extra or {}),
        }

    def get_embeddings(self, model: str | None = None) -> dict[str, Any]:
        self.requests.append(("embedding", model))
        return {"model": model}


TestLLMProviderPort = port_laws(
    "LLMProviderPort",
    InMemoryLLMProviderPort,
    PortLawSpec(
        idempotent=[
            Idempotent(
                "chat option mapping is deterministic",
                lambda port: port.get_chat_model(
                    ChatModelOptions(model="fixture", extra={"seed": 7})
                ),
            ),
            Idempotent(
                "embedding option mapping is deterministic",
                lambda port: port.get_embeddings("fixture-embedding"),
            ),
        ],
        ordered=[
            Ordered(
                "provider request order is preserved",
                first=lambda port: port.get_chat_model(
                    ChatModelOptions(model="first")
                ),
                second=lambda port: port.get_embeddings("second"),
                observe=lambda port: list(port.requests),
                commutes=False,
            )
        ],
    ),
)
