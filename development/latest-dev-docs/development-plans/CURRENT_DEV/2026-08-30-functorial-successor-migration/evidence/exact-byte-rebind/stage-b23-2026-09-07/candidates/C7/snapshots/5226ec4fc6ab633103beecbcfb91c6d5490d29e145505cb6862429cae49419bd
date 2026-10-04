"""Versioned operation contract declarations for heterogeneous tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from functorial_kit import Failure

from mrw_functorial_kit.core.w07_semantics import language_failures

from app.successor_runtime.research.codec import dataclass_to_json, sha256_hex
from app.successor_runtime.research.object_types import ObjectType

_LANGUAGE_FAILURE_WITNESS = "test:test_w07_language_research_failure_boundary"


def _failure(
    code: str,
    message: object,
    exception_type: type[Exception],
    *,
    site: str,
) -> Failure:
    """Create a closed language failure before lifting at the public ABI."""

    public_message = str(exception_type(message))
    return language_failures.fail(
        code,
        public_message,
        {
            "public_exception": exception_type.__name__,
            "public_argument": message,
            "public_message": public_message,
            "site": site,
            "witness": _LANGUAGE_FAILURE_WITNESS,
        },
    )


def _raise_failure(
    failure: Failure,
    exception_type: type[Exception],
    *,
    cause: BaseException | None = None,
) -> None:
    """Lift a complete typed failure while retaining the existing exception ABI."""

    context = failure.context or {}
    if (
        not language_failures.matches(failure)
        or context.get("public_exception") != exception_type.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=successor.language.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w07_language_research_failure_boundary
        raise TypeError("language failure lift context is incomplete")
    # kit:boundary owner=successor.language.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_w07_language_research_failure_boundary
    if cause is None:
        # kit:boundary owner=successor.language.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_w07_language_research_failure_boundary
        raise exception_type(context.get("public_argument", context["public_message"]))
    # kit:boundary owner=successor.language.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_w07_language_research_failure_boundary
    raise exception_type(context.get("public_argument", context["public_message"])) from cause

__all__ = [
    "CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF",
    "CLAIM_OR_GAP_RETURN_CONTRACT_REF",
    "DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF",
    "DOCUMENT_ADMISSION_RETURN_CONTRACT_REF",
    "EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF",
    "FROZEN_BASE_RETURN_CONTRACT_REFS",
    "READ_CANONICAL_REF_RETURN_CONTRACT_REF",
    "RESEARCH_ARTIFACT_RETURN_CONTRACT_REF",
    "RUNTIME_VALUE_RETURN_CONTRACT_REF",
    "OperationContract",
    "OperationContractRef",
    "OperationContractResolver",
    "ReturnContract",
    "ReturnContractRegistry",
    "build_c7_document_admission_return_contract_extension",
    "build_first_specimen_return_contract_registry",
    "build_frozen_base_return_contract_registry",
    "make_operation_contract",
]


@dataclass(frozen=True, slots=True)
class ReturnContract:
    success_modes: tuple[str, ...]
    failure_modes: tuple[str, ...]
    admission_required: bool
    wait_modes: tuple[str, ...] = ()
    cancel_modes: tuple[str, ...] = ()


# A single output does not imply canonical admission.  These independently
# named refs make the six first-specimen return boundaries explicit.
RUNTIME_VALUE_RETURN_CONTRACT_REF = "mrw.return.runtime-value.v1"
SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF = (
    "mrw.functorial-successor.return.single-typed-output.v1"
)
CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF = (
    "mrw.return.material.capture-document-snapshot.v1"
)
READ_CANONICAL_REF_RETURN_CONTRACT_REF = "mrw.return.material.read-canonical-ref.v1"
EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF = (
    "mrw.return.evidence.qualification-relation-admission.v1"
)
CLAIM_OR_GAP_RETURN_CONTRACT_REF = "mrw.return.claim.claim-or-gap-admission.v1"
RESEARCH_ARTIFACT_RETURN_CONTRACT_REF = (
    "mrw.return.artifact.research-artifact-admission.v1"
)
DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF = (
    "mrw.return.delivery.intent-receipt-admission.v1"
)
DOCUMENT_ADMISSION_RETURN_CONTRACT_REF = "mrw.return.ingest.document-admission.v1"

# Frozen order and identity of the six P0-A return boundaries.  The C7 family
# may only extend this list by the single Document admission contract below.
FROZEN_BASE_RETURN_CONTRACT_REFS: tuple[str, ...] = (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    SINGLE_TYPED_OUTPUT_RETURN_CONTRACT_REF,
    CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF,
    READ_CANONICAL_REF_RETURN_CONTRACT_REF,
    EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF,
    CLAIM_OR_GAP_RETURN_CONTRACT_REF,
    RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
    DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
)

_BASE_ADMISSION_REQUIRED_REFS = frozenset(
    {
        EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF,
        CLAIM_OR_GAP_RETURN_CONTRACT_REF,
        RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
        DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
    }
)


@dataclass(frozen=True, slots=True)
class ReturnContractRegistry:
    """Immutable resolver for named return contracts."""

    entries: tuple[tuple[str, ReturnContract], ...]

    def __post_init__(self) -> None:
        refs = tuple(ref for ref, _contract in self.entries)
        if any(not ref for ref in refs):
            _raise_failure(
                _failure(
                    "CONTRACT_REGISTRY_INVALID",
                    "return contract ref must be non-empty",
                    ValueError,
                    site="ReturnContractRegistry.ref",
                ),
                ValueError,
            )
        if len(refs) != len(set(refs)):
            _raise_failure(
                _failure(
                    "CONTRACT_REGISTRY_INVALID",
                    "duplicate return contract ref",
                    ValueError,
                    site="ReturnContractRegistry.ref.unique",
                ),
                ValueError,
            )

    def resolve(self, ref: str) -> ReturnContract | None:
        for candidate, contract in self.entries:
            if candidate == ref:
                return contract
        return None

    def resolve_required(self, ref: str) -> ReturnContract:
        contract = self.resolve(ref)
        if contract is None:
            _raise_failure(
                _failure(
                    "UNKNOWN_RETURN_CONTRACT",
                    f"unresolved return contract: {ref}",
                    KeyError,
                    site="ReturnContractRegistry.resolve_required",
                ),
                KeyError,
            )
        return contract


def _first_specimen_return_contract(*, admission_required: bool) -> ReturnContract:
    return ReturnContract(
        success_modes=("SUCCEEDED",),
        failure_modes=("FAILED",),
        admission_required=admission_required,
        wait_modes=("WAIT",),
        cancel_modes=("CANCELED",),
    )


def build_frozen_base_return_contract_registry() -> Annotated[
    ReturnContractRegistry,
    "kit:non-authoritative derived_as=view "
    "fact_source=successor_runtime.language.object_contracts.FROZEN_BASE_RETURN_CONTRACT_REFS "
    "witness=test:test_w07_derived_metadata_is_exact_and_non_authoritative",
]:
    """Frozen six-ref base registry; order and contracts must never change."""
    # derived(view) is explicitly non-authoritative; the frozen refs remain the fact source.

    return ReturnContractRegistry(
        entries=tuple(
            (
                ref,
                _first_specimen_return_contract(
                    admission_required=ref in _BASE_ADMISSION_REQUIRED_REFS
                ),
            )
            for ref in FROZEN_BASE_RETURN_CONTRACT_REFS
        )
    )


def build_c7_document_admission_return_contract_extension() -> Annotated[
    tuple[tuple[str, ReturnContract], ...],
    "kit:non-authoritative derived_as=view "
    "fact_source=successor_runtime.language.object_contracts.DOCUMENT_ADMISSION_RETURN_CONTRACT_REF "
    "witness=test:test_w07_derived_metadata_is_exact_and_non_authoritative",
]:
    """Exact additive C7 extension: one Document admission contract."""
    # derived(view) is explicitly non-authoritative; the contract ref is the fact source.

    return (
        (
            DOCUMENT_ADMISSION_RETURN_CONTRACT_REF,
            _first_specimen_return_contract(admission_required=True),
        ),
    )


def build_first_specimen_return_contract_registry() -> Annotated[
    ReturnContractRegistry,
    "kit:non-authoritative derived_as=view "
    "fact_source=successor_runtime.language.object_contracts.FROZEN_BASE_RETURN_CONTRACT_REFS "
    "witness=test:test_w07_derived_metadata_is_exact_and_non_authoritative",
]:
    """Frozen base return vocabulary plus the single additive C7 extension."""
    # derived(view) is explicitly non-authoritative; the base and extension refs are fact sources.

    return ReturnContractRegistry(
        entries=(
            build_frozen_base_return_contract_registry().entries
            + build_c7_document_admission_return_contract_extension()
        )
    )


@dataclass(frozen=True, slots=True)
class OperationContractRef:
    kind: str
    contract_version: str
    contract_digest: str


@dataclass(frozen=True, slots=True)
class OperationContract:
    ref: OperationContractRef
    input_type: ObjectType
    output_type: ObjectType
    return_contract_ref: str
    semantic_profile_ref: str
    effect_profile_ref: str
    resource_profile_ref: str
    failure_profile_ref: str
    authority_profile_ref: str
    interpreter_compatibility_ref: str
    observation_profile_ref: str
    allowed_override_schema_ref: str
    owner_capability_id: str

    def content_payload(self) -> dict[str, Any]:
        payload = dataclass_to_json(self, ("ref",))
        payload["ref"] = {
            "kind": self.ref.kind,
            "contract_version": self.ref.contract_version,
        }
        return payload

    def contract_digest(self) -> str:
        return sha256_hex(self.content_payload())

    def __post_init__(self) -> None:
        expected = self.contract_digest()
        if self.ref.contract_digest != expected:
            _raise_failure(
                _failure(
                    "CONTRACT_BINDING_MISSING",
                    "OperationContract ref digest mismatch",
                    ValueError,
                    site="OperationContract.ref.contract_digest",
                ),
                ValueError,
            )


def make_operation_contract(
    *,
    kind: str,
    contract_version: str,
    input_type: ObjectType,
    output_type: ObjectType,
    return_contract_ref: str,
    semantic_profile_ref: str,
    effect_profile_ref: str,
    resource_profile_ref: str,
    failure_profile_ref: str,
    authority_profile_ref: str,
    interpreter_compatibility_ref: str,
    observation_profile_ref: str,
    allowed_override_schema_ref: str,
    owner_capability_id: str,
) -> OperationContract:
    """Build an operation contract whose ref digest matches its content."""
    body = {
        "input_type": input_type,
        "output_type": output_type,
        "return_contract_ref": return_contract_ref,
        "semantic_profile_ref": semantic_profile_ref,
        "effect_profile_ref": effect_profile_ref,
        "resource_profile_ref": resource_profile_ref,
        "failure_profile_ref": failure_profile_ref,
        "authority_profile_ref": authority_profile_ref,
        "interpreter_compatibility_ref": interpreter_compatibility_ref,
        "observation_profile_ref": observation_profile_ref,
        "allowed_override_schema_ref": allowed_override_schema_ref,
        "owner_capability_id": owner_capability_id,
    }
    payload = {
        "ref": {"kind": kind, "contract_version": contract_version},
        **body,
    }
    ref = OperationContractRef(
        kind=kind,
        contract_version=contract_version,
        contract_digest=sha256_hex(payload),
    )
    return OperationContract(ref=ref, **body)


class OperationContractResolver(Protocol):
    """Compiler-facing read port for full operation contracts by ref."""

    def resolve(self, ref: OperationContractRef) -> OperationContract | None:
        """Return the exact contract or None when the ref is not resolvable."""

    def resolve_required(self, ref: OperationContractRef) -> OperationContract:
        """Return the exact contract or fail when the ref is not resolvable."""
