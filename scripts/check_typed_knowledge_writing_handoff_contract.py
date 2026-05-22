#!/usr/bin/env python3
"""Check the typed-knowledge to writing-workbench handoff contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "main" / "backend"
sys.path.insert(0, str(BACKEND))

from app.contracts.schemas.writing import (  # noqa: E402
    TypedKnowledgeWritingContext,
    TypedKnowledgeWritingHandoffData,
    WritingContextEnvelope,
)
from app.services.document_views.writing_card_view import build_keyword_card_from_typed_knowledge_handoff  # noqa: E402
from app.services.typed_knowledge import contracts  # noqa: E402


def main() -> int:
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    check(
        TypedKnowledgeWritingHandoffData.model_fields["contract_version"].default
        == contracts.WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION,
        "writing schema handoff version diverged from typed_knowledge contract",
    )
    check(
        TypedKnowledgeWritingContext.model_fields["contract_version"].default
        == contracts.WRITING_KNOWLEDGE_CONTEXT_ENVELOPE_VERSION,
        "writing schema context envelope version diverged from typed_knowledge contract",
    )

    item = contracts.KnowledgeItem(
        key="ki:robotics-policy",
        project_key="demo_proj",
        canonical_statement="Humanoid robotics investment is shifting toward industrial pilots.",
        primary_type_node_key="type:market_signal",
        evidence_refs=("doc:robotics:42",),
        topic_cluster_keys=("topic:robotics",),
        booklet_keys=("booklet:q2-review",),
        review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
        quality_grade=contracts.QUALITY_GRADE_GOLD,
        locale="en",
    )
    handoff = contracts.build_writing_knowledge_handoff(
        contracts.build_downstream_contract_draft(item),
        selection_hash="selection:robotics",
        selection_text="robotics investment",
    )
    envelope = contracts.build_writing_knowledge_context_envelope((handoff,))
    writing_context = WritingContextEnvelope(typed_knowledge_context=envelope)
    dumped_context = writing_context.model_dump()
    typed_context = dumped_context.get("typed_knowledge_context") or {}
    parsed_handoffs = contracts.parse_writing_knowledge_context_envelope(typed_context)
    card = build_keyword_card_from_typed_knowledge_handoff(parsed_handoffs[0], normalized_query="robotics investment")

    check(len(parsed_handoffs) == 1, "context envelope must preserve one handoff")
    check(card.source_type == "resource", "typed knowledge must enter writing cards as resource")
    check(card.publisher == "typed_knowledge", "typed knowledge card publisher mismatch")
    check(card.extra.get("knowledge_item_key") == item.key, "card lost typed knowledge item identity")
    check(card.extra.get("selection_hash") == "selection:robotics", "card lost selection hash")
    check(card.extra.get("selection_text") == "robotics investment", "card lost selection text")
    check(
        card.extra.get("facets", {}).get("consumer_boundary", {}).get("card_source_type") == "resource",
        "card facets lost consumer boundary",
    )

    summary = {
        "status": "ok" if not failures else "failed",
        "contract_version": contracts.WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION,
        "context_envelope_version": contracts.WRITING_KNOWLEDGE_CONTEXT_ENVELOPE_VERSION,
        "card_id": card.card_id,
        "source_type": card.source_type,
        "publisher": card.publisher,
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
