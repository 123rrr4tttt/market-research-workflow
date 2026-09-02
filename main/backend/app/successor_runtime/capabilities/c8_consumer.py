"""Read-only graph consumer for the C8 movement closure package.

P4 ahead-of-time family-local scaffold: the production consumer accepts only
an opaque active read handle (never caller-supplied generation/offset/
provenance claims), preserves source/projection provenance and inherited loss,
and never synthesizes evidence or claim support.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.successor_runtime.capabilities.c8_common import (
    C8ProjectionError,
    GraphConsumerResult,
    GraphProjectionGeneration,
    TestOnlySealedValue,
    graph_occurrence_digest,
    graph_projection_generation_digest,
)

__all__ = [
    "consume_graph_projection",
    "consume_graph_projection_test_only",
]


def consume_graph_projection(
    *,
    consumer_id: str,
    projection: GraphProjectionGeneration,
    project_key: str,
    active_read_handle: object,
    request_claim_support: bool = False,
) -> GraphConsumerResult:
    if isinstance(active_read_handle, TestOnlySealedValue):
        raise C8ProjectionError(
            "production graph consumer rejects TEST_ONLY active read handle"
        )
    return consume_graph_projection_test_only(
        consumer_id=consumer_id,
        projection=projection,
        project_key=project_key,
        active_generation_id=active_read_handle.generation_id,
        active_offset=active_read_handle.offset,
        active_provenance_digest=active_read_handle.provenance_digest,
        request_claim_support=request_claim_support,
    )


def consume_graph_projection_test_only(
    *,
    consumer_id: str,
    projection: GraphProjectionGeneration,
    project_key: str,
    active_generation_id: str,
    active_offset: str,
    active_provenance_digest: str,
    request_claim_support: bool = False,
) -> GraphConsumerResult:
    if request_claim_support:
        raise C8ProjectionError(
            "graph consumer never creates claim support or synthetic evidence"
        )
    if projection.project_key != project_key:
        raise C8ProjectionError("graph consumer project scope mismatch")
    if projection.generation_id != active_generation_id:
        raise C8ProjectionError("stale graph generation rejected")
    if projection.offset != active_offset:
        raise C8ProjectionError("graph generation offset mismatch")
    if projection.provenance_digest != active_provenance_digest:
        raise C8ProjectionError("graph provenance digest is not the active one")
    if projection.projection_digest != graph_projection_generation_digest(projection):
        raise C8ProjectionError("tampered graph projection generation")
    for occurrence in projection.occurrences:
        if occurrence.occurrence_digest != graph_occurrence_digest(occurrence):
            raise C8ProjectionError("tampered graph occurrence")
    if not projection.provenance_digest:
        return GraphConsumerResult(
            consumer_id=consumer_id,
            generation_id=projection.generation_id,
            project_key=project_key,
            items=(),
            declared_loss=projection.declared_loss,
            state="UNAVAILABLE",
        )
    items: tuple[Mapping[str, Any], ...] = tuple(
        {
            "occurrence_id": occurrence.occurrence_id,
            "edge_type": occurrence.edge_type,
            "source_identity": occurrence.source_identity,
            "target_identity": occurrence.target_identity,
        }
        for occurrence in projection.occurrences
    )
    return GraphConsumerResult(
        consumer_id=consumer_id,
        generation_id=projection.generation_id,
        project_key=project_key,
        items=items,
        declared_loss=projection.declared_loss,
        state="AVAILABLE",
        provider_calls=0,
        store_writes=0,
        export_calls=0,
    )
