from __future__ import annotations

from typing import Final

K1_BASELINE_SURFACES: Final[dict[str, str]] = {
    "main/backend/app/services/discovery/store.py": "Evidence-first ingestion and extraction storage.",
    "main/backend/app/services/resource_pool/auto_classify.py": "Automation pattern for classification heuristics.",
    "main/backend/app/api/topics.py": "Existing lightweight topic model and project-scoped topic APIs.",
    "main/backend/app/api/typed_knowledge.py": "Public typed-knowledge API route contract for persistence-boundary readback.",
    "main/backend/app/services/graph/doc_types.py": "Graph projection constraints and node-type catalog.",
    "main/backend/app/api/writing.py": "Downstream writing consumer surface for organized knowledge usage.",
}

K1_GLOSSARY: Final[dict[str, str]] = {
    "type_node": "Taxonomy anchor for classification and navigation. It is not a graph-rendering node.",
    "knowledge_item": "Normalized downstream-facing knowledge unit with provenance and governance metadata.",
    "topic_cluster": "Cross-type thematic grouping over many knowledge items; not a free-form tag bucket.",
    "booklet": "Curated presentation container that can include type nodes, topic clusters, and knowledge items.",
}

K1_GAP_LIST: Final[tuple[str, ...]] = (
    "Typed-knowledge persistence remains contract-only; a public route contract exists, but no live DB table or DB-backed readback exists.",
    "Topic object exists but does not yet express typed hierarchy and governance state boundaries.",
    "No integrated source-library or graph write-back path currently materializes typed knowledge items.",
)
