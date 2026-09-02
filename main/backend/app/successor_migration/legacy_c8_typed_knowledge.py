"""Legacy typed-knowledge replay adapter for the C8.1 read/handoff slice.

The adapter calls only pure typed-knowledge contract helpers
(``build_downstream_contract_draft`` / ``build_writing_knowledge_handoff``) and
never touches persistence, providers or the writing runtime.
"""

from __future__ import annotations

from typing import Any

from app.services.typed_knowledge.contracts import (
    build_downstream_contract_draft,
    build_writing_knowledge_handoff,
    validate_knowledge_item,
)

__all__ = [
    "LEGACY_TYPED_KNOWLEDGE_INTERPRETER_ID",
    "LegacyC8TypedKnowledgeAdapter",
]

LEGACY_TYPED_KNOWLEDGE_INTERPRETER_ID = "legacy.typed_knowledge.downstream_contract.v1"


class LegacyC8TypedKnowledgeAdapter:
    """Deterministic replay of the typed-knowledge writing handoff contract."""

    interpreter_id = LEGACY_TYPED_KNOWLEDGE_INTERPRETER_ID

    def __init__(self) -> None:
        self.handoff_calls = 0

    def build_handoff_payload(
        self,
        item: Any,
        *,
        selection_hash: str,
        selection_text: str,
    ) -> dict[str, Any]:
        validate_knowledge_item(item)
        contract = build_downstream_contract_draft(item)
        handoff = build_writing_knowledge_handoff(
            contract,
            selection_hash=selection_hash,
            selection_text=selection_text,
        )
        self.handoff_calls += 1
        boundary = dict(handoff.facets["consumer_boundary"])
        return {
            "interpreter_id": self.interpreter_id,
            "contract_version": handoff.contract_version,
            "knowledge_item_key": handoff.knowledge_item_key,
            "project_key": handoff.project_key,
            "canonical_statement": handoff.canonical_statement,
            "selection_hash": handoff.selection_hash,
            "selection_text": handoff.selection_text,
            "card_source_type": boundary["card_source_type"],
            "handoff_calls": self.handoff_calls,
            "provider_calls": 0,
            "store_writes": 0,
        }
