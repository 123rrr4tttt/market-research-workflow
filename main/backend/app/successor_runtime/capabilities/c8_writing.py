"""Pure ordered writing composition and staged artifacts for C8.

P4 ahead-of-time family-local scaffold: writing handoff, card projection and
staged artifact values preserve demand-read provenance and read handles.
The module never calls admission, export, provider or store code.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.successor_runtime.capabilities.c8_common import (
    KNOWLEDGE_ITEM_FIELDS,
    CitationClosure,
    IssuedKnowledgeRead,
    KnowledgeRead,
    Provenance,
    ProvenanceClosureEntry,
    ReadHandle,
    ResearchDraftArtifact,
    TestOnlySealedValue,
    UnavailableProjection,
    WritingCompositionSpec,
    c8_canonical_digest,
    research_draft_artifact_digest,
    validate_citation_closure,
)

__all__ = [
    "CONSUMER_BOUNDARY_FACET",
    "LEGACY_CARD_METADATA_LOSS",
    "WRITING_CARD_PROJECTION",
    "WRITING_HANDOFF_CONTRACT_VERSION",
    "WRITING_STAGE_SEQUENCE",
    "WRITING_SYNTHESIS_REQUIRED_FIELDS",
    "ResearchDraftArtifact",
    "StagedWritingArtifact",
    "WritingCard",
    "WritingHandoff",
    "compose_markdown_draft",
    "compose_markdown_draft_test_only",
    "compose_writing_handoff",
    "ordered_composition_digest",
    "project_writing_card",
    "stage_writing_artifact",
]

LEGACY_CARD_METADATA_LOSS: tuple[str, ...] = (
    "legacy_card_cache",
    "legacy_score",
    "legacy_wall_clock_retrieved_at",
    "legacy_ui_convenience_fields",
)

WRITING_HANDOFF_CONTRACT_VERSION = "typed_knowledge.writing_handoff.v1"
WRITING_CARD_PROJECTION = "writing.keyword_card"
WRITING_SYNTHESIS_REQUIRED_FIELDS = ("canonical_statement", "evidence_refs")
WRITING_STAGE_SEQUENCE = (
    "demand_read",
    "writing_handoff",
    "writing_card",
    "staged_artifact",
)

CONSUMER_BOUNDARY_FACET: Mapping[str, str] = {
    "source_domain": "typed_knowledge",
    "consumer_domain": "writing",
    "consumer": "writing.keyword_card",
    "card_source_type": "resource",
    "boundary_rule": "consume_typed_knowledge_handoff_as_resource_card_only",
    "non_goal": "graph_projection_or_persistence_writeback",
}


@dataclass(frozen=True, slots=True)
class WritingHandoff:
    contract_version: str
    knowledge_item_key: str
    project_key: str
    canonical_statement: str
    selection_hash: str
    selection_text: str
    evidence_refs: tuple[str, ...]
    facets: Mapping[str, Any]
    handle: ReadHandle
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class WritingCard:
    card_id: str
    source_type: str
    publisher: str
    knowledge_item_key: str
    canonical_statement: str
    selection_hash: str
    selection_text: str
    facets: Mapping[str, Any]
    handle: ReadHandle
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class StagedWritingArtifact:
    artifact_id: str
    stage_sequence: tuple[str, ...]
    card: WritingCard
    composition_digest: str
    provenance: Provenance
    declared_loss: tuple[str, ...]
    provenance_chain: tuple[str, ...]


def compose_writing_handoff(
    read: KnowledgeRead,
    *,
    selection_hash: str,
    selection_text: str,
) -> WritingHandoff:
    missing = [
        name for name in WRITING_SYNTHESIS_REQUIRED_FIELDS if name not in read.fields
    ]
    if missing:
        raise UnavailableProjection(
            "writing synthesis requires demand-read fields: " + ",".join(missing)
        )
    facets = {
        "consumer_boundary": dict(CONSUMER_BOUNDARY_FACET),
        "demand_read_field_mask": list(read.fields),
    }
    return WritingHandoff(
        contract_version=WRITING_HANDOFF_CONTRACT_VERSION,
        knowledge_item_key=read.item.key,
        project_key=read.item.project_key,
        canonical_statement=read.fields["canonical_statement"],
        selection_hash=selection_hash,
        selection_text=selection_text,
        evidence_refs=tuple(read.fields["evidence_refs"]),
        facets=facets,
        handle=read.handle,
        provenance=read.provenance,
    )


def project_writing_card(handoff: WritingHandoff) -> WritingCard:
    payload = {
        "knowledge_item_key": handoff.knowledge_item_key,
        "canonical_statement": handoff.canonical_statement,
        "selection_hash": handoff.selection_hash,
        "source_type": "resource",
        "publisher": "typed_knowledge",
        "handle_id": handoff.handle.handle_id,
    }
    card_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return WritingCard(
        card_id=card_id,
        source_type="resource",
        publisher="typed_knowledge",
        knowledge_item_key=handoff.knowledge_item_key,
        canonical_statement=handoff.canonical_statement,
        selection_hash=handoff.selection_hash,
        selection_text=handoff.selection_text,
        facets=dict(handoff.facets),
        handle=handoff.handle,
        provenance=Provenance(
            projection_name=WRITING_CARD_PROJECTION,
            canonical_identity=handoff.provenance.canonical_identity,
            canonical_digest=handoff.provenance.canonical_digest,
            canonical_revision=handoff.provenance.canonical_revision,
            canonical_incarnation=handoff.provenance.canonical_incarnation,
            source_label=handoff.provenance.source_label,
        ),
    )


def ordered_composition_digest(stages: tuple[str, ...]) -> str:
    return c8_canonical_digest({"stage_sequence": list(stages)})


def stage_writing_artifact(card: WritingCard) -> StagedWritingArtifact:
    composition_digest = ordered_composition_digest(WRITING_STAGE_SEQUENCE)
    payload = {
        "card_id": card.card_id,
        "composition_digest": composition_digest,
    }
    artifact_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    demand_mask = set(card.facets.get("demand_read_field_mask") or ())
    declared_loss = tuple(
        f"not_demand_read:{name}"
        for name in KNOWLEDGE_ITEM_FIELDS
        if name not in demand_mask
    )
    return StagedWritingArtifact(
        artifact_id=artifact_id,
        stage_sequence=WRITING_STAGE_SEQUENCE,
        card=card,
        composition_digest=composition_digest,
        provenance=Provenance(
            projection_name="writing.staged_artifact",
            canonical_identity=card.provenance.canonical_identity,
            canonical_digest=card.provenance.canonical_digest,
            canonical_revision=card.provenance.canonical_revision,
            canonical_incarnation=card.provenance.canonical_incarnation,
            source_label=card.provenance.source_label,
        ),
        declared_loss=declared_loss,
        provenance_chain=(
            "demand_read",
            "writing_handoff",
            "writing_card",
            "staged_artifact",
        ),
    )


def compose_markdown_draft(
    *,
    artifact_id: str,
    reads: tuple[IssuedKnowledgeRead, ...],
    citation_closure: CitationClosure,
    spec: WritingCompositionSpec,
) -> ResearchDraftArtifact:
    for read in reads:
        if isinstance(read.witness_marker, TestOnlySealedValue):
            raise UnavailableProjection(
                "production writing rejects TEST_ONLY read witness"
            )
    return _compose_markdown_draft(
        artifact_id=artifact_id,
        reads=reads,
        citation_closure=citation_closure,
        spec=spec,
    )


def compose_markdown_draft_test_only(
    *,
    artifact_id: str,
    reads: tuple[IssuedKnowledgeRead, ...],
    citation_closure: CitationClosure,
    spec: WritingCompositionSpec,
) -> ResearchDraftArtifact:
    return _compose_markdown_draft(
        artifact_id=artifact_id,
        reads=reads,
        citation_closure=citation_closure,
        spec=spec,
    )


def _compose_markdown_draft(
    *,
    artifact_id: str,
    reads: tuple[IssuedKnowledgeRead, ...],
    citation_closure: CitationClosure,
    spec: WritingCompositionSpec,
) -> ResearchDraftArtifact:
    validate_citation_closure(
        citation_closure,
        duplicate_policy=spec.duplicate_policy,
        ceiling=spec.citation_ceiling,
    )
    if not reads:
        raise UnavailableProjection("markdown draft requires issued knowledge reads")
    for read in reads:
        if read.handle.project_key != spec.project_key:
            raise UnavailableProjection("issued read project scope mismatch")
        if (
            read.handle.revision != spec.base_revision
            or read.handle.incarnation != spec.base_incarnation
        ):
            raise UnavailableProjection(
                "markdown base revision/incarnation must equal every issued source"
            )
        if "canonical_statement" not in read.fields:
            raise UnavailableProjection(
                "markdown draft requires demand-read canonical_statement"
            )
        evidence_refs = read.fields.get("evidence_refs")
        if not evidence_refs:
            raise UnavailableProjection(
                "markdown draft requires non-empty evidence_refs"
            )
        citation_ids = {ref.citation_id for ref in citation_closure.refs}
        missing = [ref for ref in evidence_refs if ref not in citation_ids]
        if missing:
            raise UnavailableProjection(
                "evidence_refs require ordered citations: " + ",".join(sorted(missing))
            )
    read_by_identity = {read.handle.canonical_identity: read for read in reads}
    for ref in citation_closure.refs:
        bound_read = read_by_identity.get(ref.source_identity)
        if bound_read is None:
            raise UnavailableProjection(
                f"citation source is not an issued read: {ref.source_identity}"
            )
        if (
            ref.source_digest != bound_read.handle.canonical_digest
            or ref.source_revision != bound_read.handle.revision
            or ref.source_incarnation != bound_read.handle.incarnation
            or ref.handle_id != bound_read.handle.handle_id
            or ref.fields_digest != bound_read.handle.fields_digest
        ):
            raise UnavailableProjection(
                "citation is not bound to the exact issued read"
            )
    lines = [f"# {artifact_id}", ""]
    for read in reads:
        lines.append(f"- {read.fields['canonical_statement']}")
    lines.append("")
    lines.append("## Citations")
    for ref in citation_closure.refs:
        lines.append(f"{ref.position}. {ref.citation_id} ({ref.source_identity})")
    markdown_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    if len(markdown_bytes) > spec.byte_ceiling:
        raise UnavailableProjection("markdown draft exceeds byte ceiling")
    artifact = ResearchDraftArtifact(
        artifact_id=artifact_id,
        project_key=spec.project_key,
        markdown_bytes=markdown_bytes,
        base_revision=spec.base_revision,
        base_incarnation=spec.base_incarnation,
        provenance_closure=tuple(
            ProvenanceClosureEntry(
                identity=read.handle.canonical_identity,
                digest=read.handle.canonical_digest,
                revision=read.handle.revision,
                incarnation=read.handle.incarnation,
                handle_id=read.handle.handle_id,
                fields_digest=read.handle.fields_digest,
            )
            for read in reads
        ),
        citation_closure=citation_closure,
        declared_legacy_metadata_loss=LEGACY_CARD_METADATA_LOSS,
    )
    return dataclasses.replace(
        artifact,
        artifact_digest=research_draft_artifact_digest(artifact),
    )
