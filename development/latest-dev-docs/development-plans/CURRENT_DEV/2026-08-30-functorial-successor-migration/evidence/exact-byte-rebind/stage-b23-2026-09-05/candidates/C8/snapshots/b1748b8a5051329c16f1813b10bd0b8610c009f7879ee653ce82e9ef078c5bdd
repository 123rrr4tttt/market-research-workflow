"""Legacy writing-card replay adapter for the C8.2 writing projection.

The adapter replays ``build_keyword_card_from_typed_knowledge_handoff`` with a
fixed normalized query.  It captures only deterministic card fields; the
legacy builder's wall-clock ``retrieved_at`` is excluded from observations.
"""

from __future__ import annotations

from typing import Any

from app.services.document_views.writing_card_view import (
    build_keyword_card_from_typed_knowledge_handoff,
)

__all__ = [
    "LEGACY_WRITING_CARD_INTERPRETER_ID",
    "LegacyC8WritingAdapter",
]

LEGACY_WRITING_CARD_INTERPRETER_ID = (
    "legacy.writing.keyword_card_from_typed_knowledge.v1"
)


class LegacyC8WritingAdapter:
    """Deterministic replay of the typed-knowledge to writing card handoff."""

    interpreter_id = LEGACY_WRITING_CARD_INTERPRETER_ID

    def __init__(self) -> None:
        self.card_calls = 0

    def build_card_observation(
        self,
        handoff: Any,
        *,
        normalized_query: str,
    ) -> dict[str, Any]:
        card = build_keyword_card_from_typed_knowledge_handoff(
            handoff,
            normalized_query=normalized_query,
        )
        self.card_calls += 1
        extra = card.extra or {}
        return {
            "interpreter_id": self.interpreter_id,
            "card_id": card.card_id,
            "source_type": card.source_type,
            "publisher": card.publisher,
            "title": card.title,
            "url": card.url,
            "evidence": card.evidence,
            "knowledge_item_key": extra.get("knowledge_item_key"),
            "handoff_contract_version": extra.get("typed_knowledge_contract_version"),
            "retrieved_at": "non_deterministic_excluded",
            "card_calls": self.card_calls,
            "provider_calls": 0,
            "store_writes": 0,
            "export_calls": 0,
        }
