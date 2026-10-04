"""P4 C8.2 pure ordered writing composition and staged artifact tests."""

from __future__ import annotations

import pytest

from app.successor_runtime.capabilities.c8_typed_knowledge import (
    UnavailableProjection,
    demand_read,
)
from app.successor_runtime.capabilities.c8_writing import (
    WRITING_HANDOFF_CONTRACT_VERSION,
    WRITING_STAGE_SEQUENCE,
    compose_writing_handoff,
    ordered_composition_digest,
    project_writing_card,
    stage_writing_artifact,
)

from .p4_c8_fixture import (
    PROJECT_KEY,
    SELECTION_HASH,
    SELECTION_TEXT,
    captured_item,
    new_registry,
)


def _full_read():
    item = captured_item()
    return demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )


def test_writing_synthesis_requires_demand_read_fields() -> None:
    item = captured_item()
    partial = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement",),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    with pytest.raises(UnavailableProjection, match="demand-read"):
        compose_writing_handoff(
            partial,
            selection_hash=SELECTION_HASH,
            selection_text=SELECTION_TEXT,
        )


def test_writing_handoff_preserves_read_handle_and_provenance() -> None:
    read = _full_read()
    handoff = compose_writing_handoff(
        read,
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    assert handoff.contract_version == WRITING_HANDOFF_CONTRACT_VERSION
    assert handoff.handle == read.handle
    assert handoff.provenance == read.provenance
    assert handoff.provenance.canonical_revision == read.provenance.canonical_revision
    assert handoff.provenance.canonical_incarnation == (
        read.provenance.canonical_incarnation
    )
    assert handoff.facets["consumer_boundary"]["card_source_type"] == "resource"


def test_writing_card_projection_is_deterministic_and_bounded() -> None:
    read = _full_read()
    first = project_writing_card(
        compose_writing_handoff(
            read,
            selection_hash=SELECTION_HASH,
            selection_text=SELECTION_TEXT,
        )
    )
    second = project_writing_card(
        compose_writing_handoff(
            read,
            selection_hash=SELECTION_HASH,
            selection_text=SELECTION_TEXT,
        )
    )
    assert first == second
    assert first.source_type == "resource"
    assert first.publisher == "typed_knowledge"
    assert first.handle.handle_id == read.handle.handle_id
    assert first.provenance.canonical_identity == read.provenance.canonical_identity


def test_ordered_composition_is_order_sensitive() -> None:
    forward = ordered_composition_digest(("demand_read", "handoff", "card"))
    reversed_order = ordered_composition_digest(("card", "handoff", "demand_read"))
    assert forward != reversed_order


def test_staged_artifact_preserves_ordered_stages() -> None:
    read = _full_read()
    handoff = compose_writing_handoff(
        read,
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    card = project_writing_card(handoff)
    artifact = stage_writing_artifact(card)
    assert artifact.stage_sequence == WRITING_STAGE_SEQUENCE
    assert artifact.composition_digest == ordered_composition_digest(
        WRITING_STAGE_SEQUENCE
    )
    assert artifact.card == card
    assert artifact.provenance.canonical_identity == (
        f"knowledge:{PROJECT_KEY}:{read.item.key}"
    )
    assert "not_demand_read:topic_cluster_keys" in artifact.declared_loss
    assert artifact.provenance_chain == (
        "demand_read",
        "writing_handoff",
        "writing_card",
        "staged_artifact",
    )
