from __future__ import annotations

from typing import Protocol

from ...models.entities import Material
from .models import NormalizedSocialPost


class GraphDocumentNormalizer(Protocol):
    def __call__(self, material: Material) -> NormalizedSocialPost | None:
        ...
