"""Capability-facing re-exports of the canonical language profile contracts.

Capabilities own and publish profile instances, but do not define a parallel
profile type system.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, TypeVar

from app.successor_runtime.language.object_contracts import OperationContract, make_operation_contract
from app.successor_runtime.research.object_types import ObjectType

from .checksum import content_digest
from app.successor_runtime.language.profiles import (
    build_profile,
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
    "OperationProfiles",
    "build_operation_profiles",
]

_Profile = TypeVar("_Profile")


@dataclass(frozen=True, slots=True)
class OperationProfiles:
    """One operation's declarations; refs and contract wiring are derived."""

    semantic: SemanticProfile
    effect: EffectProfile
    resource: ResourceProfile
    failure: FailureProfile
    authority: AuthorityProfile
    interpreter: InterpreterProfile
    observation: ObservationProfile

    def contract(
        self,
        *,
        kind: str,
        contract_version: str,
        input_type: ObjectType,
        output_type: ObjectType,
        return_contract_ref: str,
        allowed_override_schema_ref: str,
        owner_capability_id: str,
    ) -> OperationContract:
        return make_operation_contract(
            kind=kind,
            contract_version=contract_version,
            input_type=input_type,
            output_type=output_type,
            return_contract_ref=return_contract_ref,
            allowed_override_schema_ref=allowed_override_schema_ref,
            owner_capability_id=owner_capability_id,
            semantic_profile_ref=self.semantic.ref,
            effect_profile_ref=self.effect.ref,
            resource_profile_ref=self.resource.ref,
            failure_profile_ref=self.failure.ref,
            authority_profile_ref=self.authority.ref,
            interpreter_compatibility_ref=self.interpreter.ref,
            observation_profile_ref=self.observation.ref,
        )


def build_operation_profiles(
    *,
    identity: str,
    version: str = "1.0.0",
    semantic: Mapping[str, object],
    effect: Mapping[str, object],
    resource: Mapping[str, object],
    failure: Mapping[str, object],
    authority: Mapping[str, object],
    interpreter: Mapping[str, object],
    observation: Mapping[str, object],
) -> Annotated[OperationProfiles, 'kit:non-authoritative derived_as=view fact_source=operation_profile_declarations witness=test:test_dispatch_single_profiles_are_real_semantics']:
    """Derive only identity/version/digests; each semantic field is explicit."""

    def build(profile_type: type[_Profile], family: str, declaration: Mapping[str, object]) -> _Profile:
        values = {f"{family}_profile_id": f"{identity}.{family}", f"{family}_profile_version": version, **declaration}
        if "profile_digest" in values:
            message = "operation profile digest is derived from its declaration"
            # kit:boundary owner=batch.business class=PROGRAMMER_DEFECT failure_family=none witness=test:test_operation_profiles_reject_caller_supplied_digest
            raise ValueError(message)
        return build_profile(profile_type, **values, profile_digest=content_digest(values))

    return OperationProfiles(
        semantic=build(SemanticProfile, "semantic", semantic),
        effect=build(EffectProfile, "effect", effect),
        resource=build(ResourceProfile, "resource", resource),
        failure=build(FailureProfile, "failure", failure),
        authority=build(AuthorityProfile, "authority", authority),
        interpreter=build(InterpreterProfile, "interpreter", interpreter),
        observation=build(ObservationProfile, "observation", observation),
    )
