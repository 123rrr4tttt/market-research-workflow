"""Captured deterministic fixtures for the P4 C8 family-local line."""

from __future__ import annotations

import dataclasses
from typing import Any

from app.successor_runtime.capabilities.c8_typed_knowledge import (
    CanonicalRef,
    KnowledgeItem,
    ReadHandleRegistry,
    item_digest,
)

PROJECT_KEY = "p4-c8-demo"
TOPIC = "C8.knowledge-writing-report-graph"
SELECTION_HASH = "selection:robotics"
SELECTION_TEXT = "robotics investment"
NORMALIZED_QUERY = "robotics investment"


def captured_item(
    *,
    key: str = "ki:robotics",
    project_key: str = PROJECT_KEY,
    statement: str = "机器人产品市场证据",
    node_type: str = "Topic",
    evidence_refs: tuple[str, ...] = ("ev:1", "ev:2"),
    review_state: str = "human_confirmed",
    quality_grade: str | None = "gold",
    locale: str | None = "zh",
) -> KnowledgeItem:
    body = KnowledgeItem(
        key=key,
        project_key=project_key,
        canonical_statement=statement,
        primary_type_node_key=node_type,
        evidence_refs=evidence_refs,
        topic_cluster_keys=("tc:robotics",),
        booklet_keys=("bk:robotics",),
        review_state=review_state,
        quality_grade=quality_grade,
        locale=locale,
        visibility_scope="downstream_ready",
    )
    return dataclasses.replace(
        body,
        canonical_ref=CanonicalRef(
            identity=f"knowledge:{project_key}:{key}",
            content_digest=item_digest(body),
            revision=1,
            incarnation="p4-c8-captured-1",
        ),
    )


def new_registry() -> ReadHandleRegistry:
    return ReadHandleRegistry()


def legacy_item(**overrides: Any) -> Any:
    from app.services.typed_knowledge.contracts import (
        KnowledgeItem as LegacyKnowledgeItem,
    )

    values = {
        "key": "ki:robotics",
        "project_key": PROJECT_KEY,
        "canonical_statement": "机器人产品市场证据",
        "primary_type_node_key": "Topic",
        "evidence_refs": ("ev:1", "ev:2"),
        "topic_cluster_keys": ("tc:robotics",),
        "booklet_keys": ("bk:robotics",),
        "review_state": "human_confirmed",
        "quality_grade": "gold",
        "locale": "zh",
        "updated_at": "2026-08-30T00:00:00Z",
    }
    values.update(overrides)
    return LegacyKnowledgeItem(**values)
