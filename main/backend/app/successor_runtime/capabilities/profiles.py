"""Capability-facing re-exports of the canonical language profile contracts.

Capabilities own and publish profile instances, but do not define a parallel
profile type system.
"""

from app.successor_runtime.language.profiles import (
    PROFILE_FAMILIES,
    AuthorityProfile,
    ContractProfileRef,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)

__all__ = [
    "AuthorityProfile",
    "ContractProfileRef",
    "EffectProfile",
    "FailureProfile",
    "InterpreterProfile",
    "ObservationProfile",
    "PROFILE_FAMILIES",
    "ResourceProfile",
    "SemanticProfile",
]
