from __future__ import annotations

from typing import Final

K1_BASELINE_SURFACES: Final[dict[str, str]] = {
    "main/backend/app/services/discovery/store.py": "Evidence-first ingestion and extraction storage.",
    "main/backend/app/services/resource_pool/auto_classify.py": "Automation pattern for classification heuristics.",
    "main/backend/app/api/topics.py": "Existing lightweight topic model and project-scoped topic APIs.",
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
    "No dedicated typed-knowledge organization domain contract currently exists.",
    "Topic object exists but does not yet express typed hierarchy and governance state boundaries.",
    "No shared typed read model currently freezes taxonomy/topic/booklet semantics for downstream consumers.",
)

