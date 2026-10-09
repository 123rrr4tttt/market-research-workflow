from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .policy import index_policy_documents


@dataclass
class IndexingApplicationService:
    def index_policy(
        self,
        material_ids: Sequence[int] | None = None,
        state: str | None = None,
    ) -> dict[str, int]:
        return index_policy_documents(material_ids=material_ids, state=state)
