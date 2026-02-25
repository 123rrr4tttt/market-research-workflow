from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol


@dataclass
class ChatModelOptions:
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    extra: dict[str, Any] | None = None


class ChatPort(Protocol):
    def get_chat_model(self, options: ChatModelOptions) -> Any:
        ...


class EmbeddingPort(Protocol):
    def get_embeddings(self, model: Optional[str] = None) -> Any:
        ...


class PromptConfigPort(Protocol):
    def get_config(self, service_name: str) -> dict[str, Any] | None:
        ...
