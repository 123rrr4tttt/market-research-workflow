from __future__ import annotations

from typing import Protocol

from ...models.entities import Document
from .models import NormalizedSocialPost


class GraphDocumentNormalizer(Protocol):
    def __call__(self, document: Document) -> NormalizedSocialPost | None:
        ...
