"""Exact, transport-neutral runtime assignment contracts.

The assignment says *what* canonical work may be attempted.  The embedded
handler binding says *which exact realization* may handle it.  Neither a
broker message nor a mutable process-local registry may weaken that binding.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from collections.abc import Collection
from typing import Annotated, Literal, TypeAlias, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.language.object_contracts import ReturnContract


Digest: TypeAlias = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def canonical_digest(
    value: BaseModel | dict[str, object] | tuple[object, ...],
    *,
    exclude_fields: Collection[str] = (),
) -> str:
    """Return the deterministic sha256 digest used by identity contracts."""

    if isinstance(value, BaseModel):
        payload = value.model_dump(
            mode="json",
            exclude=set(exclude_fields),
            exclude_none=False,
        )
    else:
        payload = value
        if exclude_fields:
            if not isinstance(payload, dict):
                raise TypeError(
                    "exclude_fields is only valid for model or mapping digests"
                )
            payload = {
                key: item for key, item in payload.items() if key not in exclude_fields
            }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_digest(value: str, field_name: str) -> str:
    """Fail closed when a runtime identity is not canonical SHA-256 hex."""

    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field_name} must be a 64-char lowercase hex digest")
    return value


class FrozenContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


_BindingT = TypeVar("_BindingT", bound="ContentAddressedBinding")


class ContentAddressedBinding(FrozenContract):
    """A binding whose identity is exactly its canonical field content."""

    binding_digest: Digest

    @model_validator(mode="after")
    def validate_binding_digest(self) -> "ContentAddressedBinding":
        expected = canonical_digest(self, exclude_fields={"binding_digest"})
        if self.binding_digest != expected:
            raise ValueError("binding_digest does not match canonical binding content")
        return self

    @classmethod
    def from_content(cls: type[_BindingT], **content: object) -> _BindingT:
        """Construct a binding without accepting a caller-chosen identity."""

        if "binding_digest" in content:
            raise ValueError("binding_digest is derived from canonical binding content")
        provisional = cls.model_construct(**content, binding_digest="0" * 64)
        return cls(
            **content,
            binding_digest=canonical_digest(
                provisional,
                exclude_fields={"binding_digest"},
            ),
        )


class AssignmentKind(StrEnum):
    COMPILE = "COMPILE"
    QUALIFY = "QUALIFY"
    INTERPRET = "INTERPRET"
    VERIFY_ADMIT = "VERIFY_ADMIT"
    PROJECT = "PROJECT"
    RECONCILE = "RECONCILE"
    MATERIALIZE_SUCCESSOR = "MATERIALIZE_SUCCESSOR"


class CompiledStepRole(StrEnum):
    EFFECT = "EFFECT"
    ADMISSION = "ADMISSION"


class HandlerBindingKind(StrEnum):
    COMPILER = "COMPILER"
    QUALIFICATION = "QUALIFICATION"
    INTERPRETER = "INTERPRETER"
    PROJECTOR = "PROJECTOR"
    MATERIALIZER = "MATERIALIZER"
    RECOVERY = "RECOVERY"


class CompilerBinding(ContentAddressedBinding):
    binding_kind: Literal[HandlerBindingKind.COMPILER] = HandlerBindingKind.COMPILER
    compiler_id: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    compiler_digest: Digest
    operation_catalog_digest: Digest
    domain_contract_snapshot_digest: Digest


class QualificationBinding(ContentAddressedBinding):
    binding_kind: Literal[HandlerBindingKind.QUALIFICATION] = (
        HandlerBindingKind.QUALIFICATION
    )
    authority_reader_id: str = Field(min_length=1)
    authority_reader_version: str = Field(min_length=1)
    authority_reader_digest: Digest
    deployment_catalog_digest: Digest
    resource_policy_epoch: int = Field(ge=0)


class InterpreterBinding(ContentAddressedBinding):
    binding_kind: Literal[HandlerBindingKind.INTERPRETER] = (
        HandlerBindingKind.INTERPRETER
    )
    operation_contract_digest: Digest
    interpreter_profile_digest: Digest
    deployment_catalog_digest: Digest
    runtime_protocol_version: str = Field(min_length=1)
    project_scope_digest: Digest
    resource_policy_epoch: int = Field(ge=0)
    authority_requirement_digest: Digest


class ProjectorBinding(ContentAddressedBinding):
    binding_kind: Literal[HandlerBindingKind.PROJECTOR] = HandlerBindingKind.PROJECTOR
    projector_id: str = Field(min_length=1)
    projector_version: str = Field(min_length=1)
    source_kind: Literal["RESEARCH_LEDGER", "RUNTIME_JOURNAL", "CANONICAL_OWNER"]
    source_ref: str = Field(min_length=1)
    source_digest: Digest
    projection_schema_ref: str = Field(min_length=1)
    declared_loss_profile_ref: str = Field(min_length=1)


class MaterializerBinding(ContentAddressedBinding):
    binding_kind: Literal[HandlerBindingKind.MATERIALIZER] = (
        HandlerBindingKind.MATERIALIZER
    )
    materializer_id: str = Field(min_length=1)
    materializer_version: str = Field(min_length=1)
    predecessor_plan_digest: Digest
    source_value_digest: Digest
    target_domain_contract_snapshot_digest: Digest


class RecoveryBinding(ContentAddressedBinding):
    binding_kind: Literal[HandlerBindingKind.RECOVERY] = HandlerBindingKind.RECOVERY
    recovery_handler_id: str = Field(min_length=1)
    recovery_handler_version: str = Field(min_length=1)
    interpreter_profile_digest: Digest | None = None
    authoritative_readback_profile_ref: str = Field(min_length=1)


class ReturnContractBinding(ContentAddressedBinding):
    """Exact named return contract copied from one compiled step."""

    return_contract_ref: str = Field(min_length=1)
    success_modes: tuple[str, ...]
    failure_modes: tuple[str, ...]
    admission_required: bool
    wait_modes: tuple[str, ...] = ()
    cancel_modes: tuple[str, ...] = ()

    @classmethod
    def from_contract(
        cls, return_contract_ref: str, contract: ReturnContract
    ) -> "ReturnContractBinding":
        return cls.from_content(
            return_contract_ref=return_contract_ref,
            success_modes=contract.success_modes,
            failure_modes=contract.failure_modes,
            admission_required=contract.admission_required,
            wait_modes=contract.wait_modes,
            cancel_modes=contract.cancel_modes,
        )


class CompiledAdmissionBinding(ContentAddressedBinding):
    """Exact compiler output required to authorize one admission step."""

    plan_digest: Digest
    effect_step_id: str = Field(min_length=1)
    admission_step_id: str = Field(min_length=1)
    operation_contract_digest: Digest
    return_contract_ref: str = Field(min_length=1)
    return_contract_digest: Digest
    source_map_digest: Digest
    control_digest: Digest

    @model_validator(mode="after")
    def validate_distinct_steps(self) -> "CompiledAdmissionBinding":
        if self.effect_step_id == self.admission_step_id:
            raise ValueError("effect and admission step identities must be distinct")
        return self


HandlerBinding: TypeAlias = Annotated[
    CompilerBinding
    | QualificationBinding
    | InterpreterBinding
    | ProjectorBinding
    | MaterializerBinding
    | RecoveryBinding,
    Field(discriminator="binding_kind"),
]


_EXPECTED_BINDING = {
    AssignmentKind.COMPILE: HandlerBindingKind.COMPILER,
    AssignmentKind.QUALIFY: HandlerBindingKind.QUALIFICATION,
    AssignmentKind.INTERPRET: HandlerBindingKind.INTERPRETER,
    AssignmentKind.VERIFY_ADMIT: HandlerBindingKind.INTERPRETER,
    AssignmentKind.PROJECT: HandlerBindingKind.PROJECTOR,
    AssignmentKind.RECONCILE: HandlerBindingKind.RECOVERY,
    AssignmentKind.MATERIALIZE_SUCCESSOR: HandlerBindingKind.MATERIALIZER,
}


class RuntimeAssignment(FrozenContract):
    """Canonical assignment plus its exact handler realization."""

    schema_version: Literal["mrw.runtime.assignment.v1"] = "mrw.runtime.assignment.v1"
    runtime_protocol_version: str = Field(min_length=1)
    work_item_id: str = Field(min_length=1)
    assignment_kind: AssignmentKind
    project_key: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    step_id: str | None = None
    step_role: CompiledStepRole | None = None
    capability_id: str = Field(min_length=1)
    operation_contract_ref: OperationContractRef | None = None
    operation_contract_digest: Digest | None = None
    return_contract_binding: ReturnContractBinding | None = None
    compiled_admission_binding: CompiledAdmissionBinding | None = None
    handler_binding_kind: HandlerBindingKind
    handler_binding_ref: str = Field(min_length=1)
    handler_binding_digest: Digest
    handler_binding: HandlerBinding
    program_digest: Digest
    plan_digest: Digest | None = None
    deployment_catalog_digest: Digest
    execution_epoch: int = Field(ge=0)
    incarnation: str = Field(min_length=1)
    input_refs: tuple[str, ...] = ()
    input_closure_digest: Digest | None = None
    payload_ref: str | None = None
    payload_digest: Digest | None = None
    queue_eligibility_digest: Digest
    resource_policy_epoch: int = Field(ge=0)
    claim_authority_epoch: int = Field(ge=0)
    claim_policy_digest: Digest
    expected_step_revision: int | None = Field(default=None, ge=0)
    reconciliation_attempt_id: Digest | None = None
    deadline_at: datetime | None = None
    trace_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_state_dependent_contract(self) -> "RuntimeAssignment":
        expected = _EXPECTED_BINDING[self.assignment_kind]
        if (
            self.handler_binding_kind != expected
            or self.handler_binding.binding_kind != expected
        ):
            raise ValueError(
                f"{self.assignment_kind} requires exact {expected} binding"
            )
        if self.handler_binding_digest != self.handler_binding.binding_digest:
            raise ValueError("handler_binding_digest does not match the exact binding")
        expected_locator = f"handler-binding:sha256:{self.handler_binding_digest}"
        if self.handler_binding_ref != expected_locator:
            raise ValueError(
                "handler_binding_ref must be the canonical locator for the exact binding digest"
            )

        if self.operation_contract_ref is not None:
            if (
                self.operation_contract_digest
                != self.operation_contract_ref.contract_digest
            ):
                raise ValueError("operation contract ref/digest mismatch")

        if self.assignment_kind in {
            AssignmentKind.INTERPRET,
            AssignmentKind.VERIFY_ADMIT,
        }:
            self._require_step_contract()
            if self.return_contract_binding is None:
                raise ValueError(
                    f"{self.assignment_kind} requires return_contract_binding"
                )
            expected_role = (
                CompiledStepRole.ADMISSION
                if self.assignment_kind is AssignmentKind.VERIFY_ADMIT
                else CompiledStepRole.EFFECT
            )
            if self.step_role is not expected_role:
                raise ValueError(
                    f"{self.assignment_kind} requires compiled step role {expected_role}"
                )
            if (
                self.assignment_kind is AssignmentKind.VERIFY_ADMIT
                and not self.return_contract_binding.admission_required
            ):
                raise ValueError(
                    "VERIFY_ADMIT requires an admission_required return contract"
                )
            if self.assignment_kind is AssignmentKind.VERIFY_ADMIT:
                self._validate_compiled_admission_binding()
            elif self.compiled_admission_binding is not None:
                raise ValueError(
                    "compiled_admission_binding is only valid for VERIFY_ADMIT"
                )
            binding = self.handler_binding
            assert isinstance(binding, InterpreterBinding)
            if binding.operation_contract_digest != self.operation_contract_digest:
                raise ValueError(
                    "interpreter is bound to a different operation contract"
                )
            if binding.deployment_catalog_digest != self.deployment_catalog_digest:
                raise ValueError("interpreter deployment catalog drift")
            if binding.runtime_protocol_version != self.runtime_protocol_version:
                raise ValueError("interpreter runtime protocol drift")
            if binding.resource_policy_epoch != self.resource_policy_epoch:
                raise ValueError("interpreter resource policy epoch drift")

        elif self.assignment_kind is AssignmentKind.RECONCILE:
            self._require_step_contract()
            if not self.reconciliation_attempt_id:
                raise ValueError("RECONCILE requires the original attempt identity")
            binding = self.handler_binding
            assert isinstance(binding, RecoveryBinding)
            if binding.interpreter_profile_digest is None:
                raise ValueError(
                    "RECONCILE must close over the original interpreter profile"
                )

        elif self.assignment_kind is AssignmentKind.COMPILE:
            if (
                self.step_id is not None
                or self.step_role is not None
                or self.expected_step_revision is not None
            ):
                raise ValueError("COMPILE is run-scoped, not step-scoped")

        elif self.assignment_kind is AssignmentKind.QUALIFY:
            if not self.plan_digest:
                raise ValueError("QUALIFY requires plan_digest")
            binding = self.handler_binding
            assert isinstance(binding, QualificationBinding)
            if binding.deployment_catalog_digest != self.deployment_catalog_digest:
                raise ValueError("qualification deployment catalog drift")
            if binding.resource_policy_epoch != self.resource_policy_epoch:
                raise ValueError("qualification resource policy epoch drift")

        elif self.assignment_kind is AssignmentKind.PROJECT:
            binding = self.handler_binding
            assert isinstance(binding, ProjectorBinding)
            if not (
                binding.source_ref
                and binding.source_digest
                and binding.declared_loss_profile_ref
            ):
                raise ValueError(
                    "PROJECT requires exact source and declared loss binding"
                )

        elif self.assignment_kind is AssignmentKind.MATERIALIZE_SUCCESSOR:
            binding = self.handler_binding
            assert isinstance(binding, MaterializerBinding)
            if (
                self.step_id is not None
                or self.step_role is not None
                or self.expected_step_revision is not None
            ):
                raise ValueError(
                    "MATERIALIZE_SUCCESSOR is a post-run assignment, not a step replay"
                )
            if self.plan_digest != binding.predecessor_plan_digest:
                raise ValueError("materializer predecessor plan drift")
            if (
                not self.input_refs
                or self.payload_ref not in self.input_refs
                or self.payload_digest != binding.source_value_digest
            ):
                raise ValueError(
                    "materializer source locator/digest pair is absent from exact inputs"
                )

        return self

    def _require_step_contract(self) -> None:
        if not self.step_id:
            raise ValueError(f"{self.assignment_kind} requires step_id")
        if self.expected_step_revision is None:
            raise ValueError(f"{self.assignment_kind} requires expected_step_revision")
        if not self.operation_contract_digest:
            raise ValueError(
                f"{self.assignment_kind} requires operation_contract_digest"
            )
        if self.operation_contract_ref is None:
            raise ValueError(f"{self.assignment_kind} requires operation_contract_ref")

    def _validate_compiled_admission_binding(self) -> None:
        binding = self.compiled_admission_binding
        if binding is None:
            raise ValueError("VERIFY_ADMIT requires compiled_admission_binding")
        if not self.plan_digest:
            raise ValueError("VERIFY_ADMIT requires plan_digest")
        if binding.plan_digest != self.plan_digest:
            raise ValueError("compiled admission plan digest drift")
        if binding.admission_step_id != self.step_id:
            raise ValueError(
                "VERIFY_ADMIT step_id must equal the compiled admission step"
            )
        if binding.operation_contract_digest != self.operation_contract_digest:
            raise ValueError("compiled admission operation contract drift")
        return_binding = self.return_contract_binding
        assert return_binding is not None
        if binding.return_contract_ref != return_binding.return_contract_ref:
            raise ValueError("compiled admission return contract ref drift")
        if binding.return_contract_digest != return_binding.binding_digest:
            raise ValueError("compiled admission return contract digest drift")

    @property
    def assignment_digest(self) -> str:
        return canonical_digest(self)
