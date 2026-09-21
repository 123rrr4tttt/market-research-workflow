"""Kit projection for typed-knowledge persistence boundary failures."""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family


TypedKnowledgePersistenceBoundaryFailureCode = Literal[
    "typed_knowledge_persistence_boundary_violation"
]

typed_knowledge_persistence_boundary_failures = define_failure_family(
    "typed_knowledge.persistence_boundary_failure",
    get_args(TypedKnowledgePersistenceBoundaryFailureCode),
)


__all__ = ["typed_knowledge_persistence_boundary_failures"]
