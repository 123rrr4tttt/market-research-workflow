"""Versioned operation contract declarations for heterogeneous tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.successor_runtime.research.codec import dataclass_to_json, sha256_hex
from app.successor_runtime.research.object_types import ObjectType

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
            raise ValueError("return contract ref must be non-empty")
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate return contract ref")

    def resolve(self, ref: str) -> ReturnContract | None:
        for candidate, contract in self.entries:
            if candidate == ref:
                return contract
        return None

    def resolve_required(self, ref: str) -> ReturnContract:
        contract = self.resolve(ref)
        if contract is None:
            raise KeyError(f"unresolved return contract: {ref}")
        return contract


def _first_specimen_return_contract(*, admission_required: bool) -> ReturnContract:
    return ReturnContract(
        success_modes=("SUCCEEDED",),
        failure_modes=("FAILED",),
        admission_required=admission_required,
        wait_modes=("WAIT",),
        cancel_modes=("CANCELED",),
    )


def build_frozen_base_return_contract_registry() -> ReturnContractRegistry:
    """Frozen six-ref base registry; order and contracts must never change."""

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


def build_c7_document_admission_return_contract_extension() -> tuple[
    tuple[str, ReturnContract], ...
]:
    """Exact additive C7 extension: one Document admission contract."""

    return (
        (
            DOCUMENT_ADMISSION_RETURN_CONTRACT_REF,
            _first_specimen_return_contract(admission_required=True),
        ),
    )


def build_first_specimen_return_contract_registry() -> ReturnContractRegistry:
    """Frozen base return vocabulary plus the single additive C7 extension."""

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
            raise ValueError("OperationContract ref digest mismatch")


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
        """Return the exact contract or raise when the ref is not resolvable."""
