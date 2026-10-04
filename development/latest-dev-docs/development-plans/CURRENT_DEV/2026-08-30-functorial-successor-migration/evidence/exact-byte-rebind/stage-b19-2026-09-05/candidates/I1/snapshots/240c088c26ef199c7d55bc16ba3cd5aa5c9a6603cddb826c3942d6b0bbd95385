"""P4 C8 legacy replay and shadow observation tests."""

from __future__ import annotations

from app.services.graph.models import (
    GraphEdge as LegacyGraphEdge,
)
from app.services.graph.models import (
    GraphNode as LegacyGraphNode,
)
from app.services.typed_knowledge.contracts import (
    build_downstream_contract_draft,
    build_writing_knowledge_handoff,
)
from app.successor_migration.legacy_c8_graph import LegacyC8GraphAdapter
from app.successor_migration.legacy_c8_report import (
    UNBOUND_C8_3_REPORT_LOCATOR,
    LegacyC8ReportAdapter,
)
from app.successor_migration.legacy_c8_typed_knowledge import (
    LegacyC8TypedKnowledgeAdapter,
)
from app.successor_migration.legacy_c8_writing import LegacyC8WritingAdapter
from app.successor_runtime.capabilities.c8_report import build_report_artifact
from app.successor_runtime.capabilities.c8_typed_knowledge import demand_read
from app.successor_runtime.capabilities.c8_writing import (
    compose_writing_handoff,
)

from .p4_c8_fixture import (
    NORMALIZED_QUERY,
    PROJECT_KEY,
    SELECTION_HASH,
    SELECTION_TEXT,
    TOPIC,
    captured_item,
    legacy_item,
    new_registry,
)


def test_legacy_typed_knowledge_handoff_parity() -> None:
    adapter = LegacyC8TypedKnowledgeAdapter()
    legacy_observation = adapter.build_handoff_payload(
        legacy_item(),
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    item = captured_item()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    handoff = compose_writing_handoff(
        read,
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    assert legacy_observation["contract_version"] == handoff.contract_version
    assert legacy_observation["knowledge_item_key"] == handoff.knowledge_item_key
    assert legacy_observation["canonical_statement"] == handoff.canonical_statement
    assert legacy_observation["card_source_type"] == "resource"
    assert legacy_observation["provider_calls"] == 0
    assert legacy_observation["store_writes"] == 0


def test_legacy_writing_card_observation_is_read_only() -> None:
    item = legacy_item()
    contract = build_downstream_contract_draft(item)
    handoff = build_writing_knowledge_handoff(
        contract,
        selection_hash=SELECTION_HASH,
        selection_text=SELECTION_TEXT,
    )
    observation = LegacyC8WritingAdapter().build_card_observation(
        handoff,
        normalized_query=NORMALIZED_QUERY,
    )
    assert observation["source_type"] == "resource"
    assert observation["publisher"] == "typed_knowledge"
    assert observation["knowledge_item_key"] == item.key
    assert observation["export_calls"] == 0
    assert observation["store_writes"] == 0


def test_legacy_graph_projection_parity() -> None:
    post = LegacyGraphNode(type="Post", id="1")
    keyword = LegacyGraphNode(type="Keyword", id="k1")
    edge = LegacyGraphEdge(type="MENTIONS_KEYWORD", from_node=post, to_node=keyword)
    adapter = LegacyC8GraphAdapter()
    projected = adapter.project(
        {"Post:1": post, "Keyword:k1": keyword},
        [edge],
        ["Post", "Keyword"],
    )
    assert projected["node_keys"] == ["Keyword:k1", "Post:1"]
    assert projected["edge_types"] == ["MENTIONS_KEYWORD"]
    assert projected["unchanged"] is False
    assert projected["provider_calls"] == 0

    unchanged = adapter.project(
        {"Post:1": post, "Keyword:k1": keyword},
        [edge],
        [],
    )
    assert unchanged["unchanged"] is True


def test_legacy_report_observation_records_unbound_locator() -> None:
    item = captured_item()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    artifact = build_report_artifact(
        report_id="report-1",
        project_key=PROJECT_KEY,
        topic=TOPIC,
        source_reads=(read,),
    )
    observation = LegacyC8ReportAdapter().observe_staging(artifact)
    assert observation["locator"] == UNBOUND_C8_3_REPORT_LOCATOR
    assert observation["availability"] == "READ_ONLY_UNAVAILABLE"
    assert observation["reads_only"] is True
    assert observation["adoption"] is False
    assert observation["admission_calls"] == 0
    assert observation["export_calls"] == 0
    assert observation["delivery_calls"] == 0
    assert observation["store_writes"] == 0
