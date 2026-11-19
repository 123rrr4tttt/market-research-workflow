"""Embedding provider used by indexing and vector search."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .ports import resolve_llm_provider
from ...settings.config import settings

if TYPE_CHECKING:
    from .ports import EmbeddingModel


def get_embeddings(model: str | None = None) -> EmbeddingModel:
    return resolve_llm_provider(settings.llm_provider or "").get_embeddings(model=model)
