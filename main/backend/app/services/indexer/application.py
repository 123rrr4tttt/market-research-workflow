from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .policy import index_policy_documents


@dataclass
class IndexingApplicationService:
    def index_policy(self, document_ids: Sequence[int] | None = None, state: str | None = None) -> dict:
        return index_policy_documents(document_ids=document_ids, state=state)
