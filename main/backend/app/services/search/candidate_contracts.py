"""Compatibility re-export of the canonical candidate observation schema.

The authoritative declarations live in the pure capability shared-contract
module; this module preserves the existing public import path for the search
and ingest services that already consume them.
"""

from app.successor_runtime.capabilities.retrieval_common import (
    Candidate,
    CandidateBundle,
    CandidateOccurrence,
    CandidateRequestFailure,
    CandidateSearchRequest,
    FailureKind,
    ProviderObservation,
    ProviderStatus,
    StopReason,
)

__all__ = [
    "Candidate",
    "CandidateBundle",
    "CandidateOccurrence",
    "CandidateRequestFailure",
    "CandidateSearchRequest",
    "FailureKind",
    "ProviderObservation",
    "ProviderStatus",
    "StopReason",
]
