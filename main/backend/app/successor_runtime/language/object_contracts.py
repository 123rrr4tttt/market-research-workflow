"""Versioned operation contract declarations for heterogeneous tasks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, NoReturn, Protocol, runtime_checkable

from functorial_kit import Failure


from app.successor_runtime.research.codec import dataclass_to_json, is_sha256_hex, sha256_hex
from app.successor_runtime.research.object_types import ObjectType

@runtime_checkable
class _FailureFamilyLike(Protocol):
    def fail(
        self,
        code: str,
        message: str,
        context: "dict[str, object] | None" = None,
    ) -> Failure: ...

    def matches(self, value: object) -> bool: ...


@runtime_checkable
class _FailureFamilyFactory(Protocol):
    def __call__(self, name: str, codes: "tuple[str, ...]") -> _FailureFamilyLike: ...


def _load_language_failures() -> _FailureFamilyLike:
    import importlib

    module = importlib.import_module("mrw_functorial_kit.core.workflow_research_failure_semantics")
    factory: object = getattr(module, "define_failure_family", None)
    if not isinstance(factory, _FailureFamilyFactory):
        # kit:boundary owner=successor.language.failure_family class=PROGRAMMER_DEFECT failure_family=none witness=test:test_language_failure_family_loader_rejects_missing_factory
        raise TypeError("language failure family factory is unavailable")
    family: object = getattr(module, "language_failures", None)
    if not isinstance(family, _FailureFamilyLike):
        # kit:boundary owner=successor.language.failure_family class=PROGRAMMER_DEFECT failure_family=none witness=test:test_language_failure_family_loader_rejects_missing_family
        raise TypeError("language failure family is unavailable")
    return family


_LANGUAGE_FAILURES = _load_language_failures()
_LANGUAGE_FAILURE_WITNESS = "test:test_language_and_research_failures_are_closed_values"


def language_failure(
    code: str,
    message: object,
    exception_type: type[Exception],
    *,
    site: str,
) -> Failure:
    """Create a closed language failure before lifting at the public ABI."""

    public_message = str(exception_type(message))
    return _LANGUAGE_FAILURES.fail(
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


def raise_language_failure(
    failure: Failure,
    exception_type: type[Exception],
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """Lift a complete typed failure while retaining the existing exception ABI."""

    context = failure.context or {}
    if (
        not _LANGUAGE_FAILURES.matches(failure)
        or context.get("public_exception") != exception_type.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=successor.language.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_language_and_research_failures_are_closed_values
        raise TypeError("language failure lift context is incomplete")
    # kit:boundary owner=successor.language.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_language_and_research_failures_are_closed_values
    if cause is None:
        # kit:boundary owner=successor.language.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_language_and_research_failures_are_closed_values
        raise exception_type(context.get("public_argument", context["public_message"]))
    # kit:boundary owner=successor.language.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.language.failure witness=test:test_language_and_research_failures_are_closed_values
    raise exception_type(context.get("public_argument", context["public_message"])) from cause

def _failure(
    code: str,
    message: object,
    exception_type: type[Exception],
    *,
    site: str,
) -> Failure:
    return language_failure(code, message, exception_type, site=site)


def _raise_failure(
    failure: Failure,
    exception_type: type[Exception],
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    raise_language_failure(failure, exception_type, cause=cause)


_PRIVATE_FAILURE_FOR_COMPAT = _failure
_PRIVATE_RAISE_FAILURE_FOR_COMPAT = _raise_failure


__all__ = [
    "CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF",
    "CLAIM_OR_GAP_RETURN_CONTRACT_REF",
    "DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF",
    "EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF",
    "FROZEN_BASE_RETURN_CONTRACT_REFS",
    "READ_CANONICAL_REF_RETURN_CONTRACT_REF",
    "RESEARCH_ARTIFACT_RETURN_CONTRACT_REF",
    "RUNTIME_VALUE_RETURN_CONTRACT_REF",
    "OperationContract",
    "ContractProfileRef",
    "OperationContractRef",
    "OperationContractResolver",
    "ReturnContract",
    "ReturnContractRegistry",
    "language_failure",
    "raise_language_failure",
    "build_first_specimen_return_contract_registry",
    "build_frozen_base_return_contract_registry",
    "make_operation_contract",
]


@dataclass(frozen=True, slots=True)
class ContractProfileRef:
    """Profile identity referenced by operation contracts and profile values."""

    profile_id: str
    profile_version: str
    profile_digest: str

    def __post_init__(self) -> None:
        if not is_sha256_hex(self.profile_digest):
            raise_language_failure(
                language_failure(
                    "PROFILE_INVALID",
                    "ContractProfileRef.profile_digest must be a 64-char lowercase hex digest",
                    ValueError,
                    site="ContractProfileRef.profile_digest.digest",
                ),
                ValueError,
            )

    def to_ref_string(self) -> str:
        return f"{self.profile_id}@{self.profile_version}"


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
# Frozen order and identity of the first-specimen return boundaries.
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
            raise_language_failure(
                language_failure(
                    "CONTRACT_REGISTRY_INVALID",
                    "return contract ref must be non-empty",
                    ValueError,
                    site="ReturnContractRegistry.ref",
                ),
                ValueError,
            )
        if len(refs) != len(set(refs)):
            raise_language_failure(
                language_failure(
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
            raise_language_failure(
                language_failure(
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
    "witness=test:test_workflow_language_projections_do_not_claim_authority",
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


def build_first_specimen_return_contract_registry() -> Annotated[
    ReturnContractRegistry,
    "kit:non-authoritative derived_as=view "
    "fact_source=successor_runtime.language.object_contracts.FROZEN_BASE_RETURN_CONTRACT_REFS "
    "witness=test:test_workflow_language_projections_do_not_claim_authority",
]:
    """Return the frozen first-specimen return vocabulary."""
    # derived(view) is explicitly non-authoritative; the frozen refs are the fact source.

    return build_frozen_base_return_contract_registry()


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
    semantic_profile_ref: "ContractProfileRef"
    effect_profile_ref: "ContractProfileRef"
    resource_profile_ref: "ContractProfileRef"
    failure_profile_ref: "ContractProfileRef"
    authority_profile_ref: "ContractProfileRef"
    interpreter_compatibility_ref: "ContractProfileRef"
    observation_profile_ref: "ContractProfileRef"
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
            raise_language_failure(
                language_failure(
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
    semantic_profile_ref: "ContractProfileRef",
    effect_profile_ref: "ContractProfileRef",
    resource_profile_ref: "ContractProfileRef",
    failure_profile_ref: "ContractProfileRef",
    authority_profile_ref: "ContractProfileRef",
    interpreter_compatibility_ref: "ContractProfileRef",
    observation_profile_ref: "ContractProfileRef",
    allowed_override_schema_ref: str,
    owner_capability_id: str,
) -> OperationContract:
    """Build an operation contract whose ref digest matches its content."""
    payload: "dict[str, object]" = {
        "ref": {"kind": kind, "contract_version": contract_version},
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
    ref = OperationContractRef(
        kind=kind,
        contract_version=contract_version,
        contract_digest=sha256_hex(payload),
    )
    return OperationContract(
        ref=ref,
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=return_contract_ref,
        semantic_profile_ref=semantic_profile_ref,
        effect_profile_ref=effect_profile_ref,
        resource_profile_ref=resource_profile_ref,
        failure_profile_ref=failure_profile_ref,
        authority_profile_ref=authority_profile_ref,
        interpreter_compatibility_ref=interpreter_compatibility_ref,
        observation_profile_ref=observation_profile_ref,
        allowed_override_schema_ref=allowed_override_schema_ref,
        owner_capability_id=owner_capability_id,
    )


class OperationContractResolver(Protocol):
    """Compiler-facing read port for full operation contracts by ref."""

    def resolve(self, ref: OperationContractRef) -> OperationContract | None:
        """Return the exact contract or None when the ref is not resolvable."""

    def resolve_required(self, ref: OperationContractRef) -> OperationContract:
        """Return the exact contract or fail when the ref is not resolvable."""
        # kit:boundary owner=successor.language.operation_contract_resolver class=PROGRAMMER_DEFECT failure_family=none witness=test:test_operation_contract_resolver_requires_required_resolution
        raise NotImplementedError
