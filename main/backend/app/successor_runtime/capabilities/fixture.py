"""Extension-locality fixture capability.

This independent capability proves the normal heterogeneous-task extension
path: it adds a contract, codec and profile under capability ownership and
never touches the shared Program AST, compiler fold, reducer or work-item root
schema.  It is built only from the public ``make_operation_contract`` builder,
the public profile contracts and the canonical ``ObjectType`` identity; it does
not reuse any first-specimen private helper or module.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)
from app.successor_runtime.research.object_types import ObjectType

from .checksum import content_digest, require_hex64
from .codecs import PayloadCodec, dataclass_codec
from .contracts import OperationContract
from .profiles import (
    AuthorityProfile,
    ContractProfileRef,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)

FIXTURE_OPERATION_KIND = "fixture.echo_hex_digest.v1"

# Shared structures that a capability extension must never modify. The frozen
# P0-A slice has not created these modules yet; the locality test therefore
# asserts both that this capability does not reference them and that no shared
# module source hash changes when the fixture is registered.
SHARED_STRUCTURE_MODULES: tuple[str, ...] = (
    "successor_runtime.language.program",
    "successor_runtime.language.compile",
    "successor_runtime.runtime.reducer",
    "successor_runtime.substrate.postgres.work_items",
)


def _object_type(type_id: str) -> ObjectType:
    return ObjectType(type_id)


def _profile_ref(
    profile_id: str,
    profile_version: str,
    profile_digest: str,
) -> ContractProfileRef:
    return ContractProfileRef(
        profile_id=profile_id,
        profile_version=profile_version,
        profile_digest=profile_digest,
    )


@dataclass(frozen=True, slots=True)
class EchoHexDigestInput:
    value_sha256_hex: str
    payload_digest: str

    def __post_init__(self) -> None:
        require_hex64(self.value_sha256_hex, "EchoHexDigestInput.value_sha256_hex")
        require_hex64(self.payload_digest, "EchoHexDigestInput.payload_digest")
        if content_digest(self, omit_fields=("payload_digest",)) != self.payload_digest:
            raise ValueError("EchoHexDigestInput.payload_digest does not match content")


@dataclass(frozen=True, slots=True)
class HexDigestObservation:
    observed_digest: str
    observed_by: str
    observation_digest: str

    def __post_init__(self) -> None:
        require_hex64(self.observed_digest, "HexDigestObservation.observed_digest")
        require_hex64(self.observation_digest, "HexDigestObservation.observation_digest")


def _fixture_profiles() -> tuple[
    SemanticProfile,
    EffectProfile,
    ResourceProfile,
    FailureProfile,
    AuthorityProfile,
    InterpreterProfile,
    ObservationProfile,
]:
    semantic_values = dict(
        semantic_profile_id=f"{FIXTURE_OPERATION_KIND}.semantic",
        semantic_profile_version="1.0.0",
        reads=(),
        creates=("HexDigestObservation.v1",),
        creates_relations=(),
        declared_loss=(),
        observation_profile_ref=f"{FIXTURE_OPERATION_KIND}.observation",
    )
    semantic = SemanticProfile(**semantic_values, profile_digest=content_digest(semantic_values))

    effect_values = dict(
        effect_profile_id=f"{FIXTURE_OPERATION_KIND}.effect",
        effect_profile_version="1.0.0",
        execution_class="PURE_TRANSFORM",
        external_visibility="NONE",
        network_required=False,
        irreversible=False,
        cancellation_points=("step_boundary",),
        internal_export_only=False,
        human_approval_required=False,
        external_acquisition=False,
        idempotency_profile_ref="logical_request_id",
    )
    effect = EffectProfile(**effect_values, profile_digest=content_digest(effect_values))

    resource_values = dict(
        resource_profile_id=f"{FIXTURE_OPERATION_KIND}.resource",
        resource_profile_version="1.0.0",
        resource_classes=("cpu",),
        concurrency_key="project",
        budget_units="operation",
        default_soft_limit_seconds=60,
        default_hard_limit_seconds=120,
        node_profile_selector="any",
        budget_ref="mrw.functorial-successor.budget.fixture.v1",
        deadline_policy_ref="mrw.functorial-successor.deadline.fixture.v1",
        node_profile_requirements=("any",),
        units=1,
    )
    resource = ResourceProfile(**resource_values, profile_digest=content_digest(resource_values))

    failure_values = dict(
        failure_profile_id=f"{FIXTURE_OPERATION_KIND}.failure",
        failure_profile_version="1.0.0",
        typed_failures=("INVALID_INPUT",),
        retryable=False,
        degraded_acceptable=False,
        unknown_outcome_supported=False,
        readback_or_compensation="none",
        failure_union_ref="mrw.functorial-successor.failures.fixture.v1",
        retryable_failure_kinds=(),
        readback_profile_ref=None,
        compensation_profile_ref=None,
    )
    failure = FailureProfile(**failure_values, profile_digest=content_digest(failure_values))

    authority_values = dict(
        authority_profile_id=f"{FIXTURE_OPERATION_KIND}.authority",
        authority_profile_version="1.0.0",
        grant_scopes=("project",),
        approval_required=False,
        approval_kinds=(),
        credential_refs=(),
        canonical_owner="FixtureCapability",
        revalidation_points=("claim_time",),
        authority_epoch=1,
    )
    authority = AuthorityProfile(**authority_values, profile_digest=content_digest(authority_values))

    interpreter_values = dict(
        interpreter_profile_id=f"{FIXTURE_OPERATION_KIND}.interpreter",
        interpreter_profile_version="1.0.0",
        supported_contract_kinds=(FIXTURE_OPERATION_KIND,),
        supported_contract_refs=(),
        dependency_digest=content_digest({"fixture": FIXTURE_OPERATION_KIND}),
        security_profile_ref="mrw.functorial-successor.security.p0-a.v1",
        resource_profile_ref=f"{FIXTURE_OPERATION_KIND}.resource",
        credential_requirements_ref=None,
        cancellation_profile_ref="step_boundary",
        idempotency_profile_ref="logical_request_id",
        authoritative_readback_profile_ref=None,
        receipt_codec_ref="mrw.functorial-successor.receipt.none.v1",
    )
    interpreter = InterpreterProfile(
        **interpreter_values,
        profile_digest=content_digest(interpreter_values),
    )

    observation_values = dict(
        observation_profile_id=f"{FIXTURE_OPERATION_KIND}.observation",
        observation_profile_version="1.0.0",
        dimensions=("input_closure_digest", "output_closure_digest", "failure"),
        compatible_with_legacy=False,
        observation_schema_ref="mrw.functorial-successor.observation.v1",
    )
    observation = ObservationProfile(
        **observation_values,
        profile_digest=content_digest(observation_values),
    )
    return semantic, effect, resource, failure, authority, interpreter, observation


@dataclass(frozen=True, slots=True)
class FixtureCapabilityBundle:
    operation: OperationContract
    codec: PayloadCodec


def build_fixture_capability_bundle() -> FixtureCapabilityBundle:
    (
        semantic,
        effect,
        resource,
        failure,
        authority,
        interpreter,
        observation,
    ) = _fixture_profiles()
    operation = make_operation_contract(
        kind=FIXTURE_OPERATION_KIND,
        contract_version="1.0.0",
        input_type=_object_type("EchoHexDigestInput.v1"),
        output_type=_object_type("HexDigestObservation.v1"),
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        semantic_profile_ref=_profile_ref(
            semantic.semantic_profile_id,
            semantic.semantic_profile_version,
            semantic.profile_digest,
        ),
        effect_profile_ref=_profile_ref(
            effect.effect_profile_id,
            effect.effect_profile_version,
            effect.profile_digest,
        ),
        resource_profile_ref=_profile_ref(
            resource.resource_profile_id,
            resource.resource_profile_version,
            resource.profile_digest,
        ),
        failure_profile_ref=_profile_ref(
            failure.failure_profile_id,
            failure.failure_profile_version,
            failure.profile_digest,
        ),
        authority_profile_ref=_profile_ref(
            authority.authority_profile_id,
            authority.authority_profile_version,
            authority.profile_digest,
        ),
        interpreter_compatibility_ref=_profile_ref(
            interpreter.interpreter_profile_id,
            interpreter.interpreter_profile_version,
            interpreter.profile_digest,
        ),
        observation_profile_ref=_profile_ref(
            observation.observation_profile_id,
            observation.observation_profile_version,
            observation.profile_digest,
        ),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id="fixture.locality_probe.v1",
    )
    codec = dataclass_codec(
        "fixture.echo_hex_digest.v1.payload",
        "1.0.0",
        operation.ref,
        "EchoHexDigestInput.v1",
        EchoHexDigestInput,
    )
    return FixtureCapabilityBundle(operation=operation, codec=codec)
