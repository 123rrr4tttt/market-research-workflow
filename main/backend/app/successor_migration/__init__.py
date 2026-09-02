"""Bounded adapters from legacy-owned data into the successor runtime."""

from .document_canonical_read import (
    LegacyDocumentCanonicalReadError,
    LegacyDocumentInvalidObservation,
    LegacyDocumentNotFound,
    LegacyDocumentScopeMismatch,
    PostgresLegacyDocumentCanonicalReadAdapter,
)

__all__ = [
    "LegacyDocumentCanonicalReadError",
    "LegacyDocumentInvalidObservation",
    "LegacyDocumentNotFound",
    "LegacyDocumentScopeMismatch",
    "PostgresLegacyDocumentCanonicalReadAdapter",
]
