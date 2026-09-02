"""C8-owned exact HandlerBinding construction on the shared runtime side.

P4 ahead-of-time family-local scaffold: this substrate module is the single
place where C8 converts the family-local handler payload into the exact
shared ``InterpreterBinding``/HandlerBinding identity.  Capability modules
never import the runtime layer.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.successor_runtime.capabilities import c8_common as c8
from app.successor_runtime.capabilities.c8_common import c8_canonical_digest
from app.successor_runtime.capabilities.c8_program import (
    C8_3_KIND,
    C8_ADMISSION_KIND,
    C8_DELIVERY_INTENT_PREPARE_KIND,
    C8_VERIFY_KIND,
    DELIVERY_INTERNAL_EXPORT_KIND,
)
from app.successor_runtime.language.combinators import default_registries
from app.successor_runtime.runtime.assignments import (
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
)
from app.successor_runtime.runtime.resources import QueueEligibility
from app.successor_runtime.substrate.postgres.first_specimen_activation import (
    ActivationCatalogEntry,
    FirstSpecimenActivationCatalog,
)

__all__ = [
    "C8CapturedReadbackPort",
    "C8ReadbackPort",
    "C8RecoveryReadbackHandler",
    "build_c8_delivery_activation_catalog",
    "build_c8_interpreter_binding",
    "build_c8_recovery_binding",
    "handler_binding_ref",
]

C8_DELIVERY_BRIDGE_OPERATION_KINDS = (
    C8_3_KIND,
    C8_VERIFY_KIND,
    C8_ADMISSION_KIND,
    C8_DELIVERY_INTENT_PREPARE_KIND,
    DELIVERY_INTERNAL_EXPORT_KIND,
)


def build_c8_interpreter_binding(payload: dict[str, Any]) -> InterpreterBinding:
    """Build an exact content-addressed InterpreterBinding from a payload."""

    binding = InterpreterBinding.from_content(**payload)
    assert binding.binding_kind == HandlerBindingKind.INTERPRETER
    return binding


def handler_binding_ref(binding: InterpreterBinding) -> str:
    return f"handler-binding:sha256:{binding.binding_digest}"


def build_c8_delivery_activation_catalog(
    plan: object,
    *,
    interpreter_profile_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    authority_requirement_digest: str,
    resource_policy_digest: str,
    required_node_profile_selector: str,
    fairness_key: str,
    queue_eligibility: QueueEligibility,
) -> FirstSpecimenActivationCatalog:
    """Build the exact five-entry C8 delivery-bridge activation catalog."""

    from app.successor_runtime.capabilities.c8_program import (
        handler_binding_payload,
    )

    entries: list[ActivationCatalogEntry] = []
    seen: set[str] = set()
    for step in plan.ordered_steps:
        ref = step.operation_contract_ref
        if ref is None or ref.kind not in C8_DELIVERY_BRIDGE_OPERATION_KINDS:
            continue
        if ref.contract_digest in seen:
            continue
        seen.add(ref.contract_digest)
        payload = handler_binding_payload(
            operation_contract_digest=ref.contract_digest,
            interpreter_profile_digest=interpreter_profile_digest,
            deployment_catalog_digest=deployment_catalog_digest,
            project_scope_digest=project_scope_digest,
            authority_requirement_digest=authority_requirement_digest,
            resource_policy_epoch=queue_eligibility.policy_epoch,
            runtime_protocol_version="1",
        )
        binding = build_c8_interpreter_binding(payload)
        recovery = build_c8_recovery_binding(
            interpreter_profile_digest=interpreter_profile_digest,
            authoritative_readback_profile_ref=(f"c8.readback.{ref.kind}"),
        )
        entries.append(
            ActivationCatalogEntry(
                operation_contract_digest=ref.contract_digest,
                interpreter_binding=binding,
                recovery_binding=recovery,
                queue_eligibility=queue_eligibility,
                required_node_profile_selector=required_node_profile_selector,
                resource_policy_digest=resource_policy_digest,
                fairness_key=fairness_key,
                effect_class="LOCAL_SUCCESSOR_NATIVE",
                max_attempts=1,
                declared_priority=0,
                external_gate_required=(ref.kind == DELIVERY_INTERNAL_EXPORT_KIND),
            )
        )
    if len(entries) != len(C8_DELIVERY_BRIDGE_OPERATION_KINDS):
        raise ValueError(
            "C8 delivery bridge activation catalog must contain exactly five "
            "operation realizations"
        )
    registries = default_registries()
    return FirstSpecimenActivationCatalog(
        entries=tuple(entries),
        transform_registry=registries.transforms,
        merge_registry=registries.merges,
        discriminator_registry=registries.discriminators,
    )


def build_c8_recovery_binding(
    *,
    interpreter_profile_digest: str,
    authoritative_readback_profile_ref: str,
    recovery_handler_id: str = "c8.recovery.readback.v1",
    recovery_handler_version: str = "1.0.0",
) -> RecoveryBinding:
    """Build the exact shared RecoveryBinding for unknown-outcome readback."""

    binding = RecoveryBinding.from_content(
        recovery_handler_id=recovery_handler_id,
        recovery_handler_version=recovery_handler_version,
        interpreter_profile_digest=interpreter_profile_digest,
        authoritative_readback_profile_ref=authoritative_readback_profile_ref,
    )
    assert binding.binding_kind == HandlerBindingKind.RECOVERY
    return binding


class C8RecoveryReadbackHandler:
    """Production readback handler for unknown-outcome C8 attempts."""

    def __init__(self, port: C8ReadbackPort | None = None) -> None:
        self.port = port or C8CapturedReadbackPort()
        self.readback_calls = 0

    def handle_unknown(
        self,
        binding: RecoveryBinding,
        *,
        cell_id: str,
        attempt_digest: str,
        readback_profile_ref: str | None = None,
    ) -> c8.C8RecoveryResult:
        self.readback_calls += 1
        if (
            readback_profile_ref is not None
            and readback_profile_ref != binding.authoritative_readback_profile_ref
        ):
            raise ValueError(
                "readback profile override rejected: profile must equal "
                "RecoveryBinding.authoritative_readback_profile_ref"
            )
        resolved_profile = binding.authoritative_readback_profile_ref
        outcome = self.port.readback(
            attempt_digest=attempt_digest,
            binding=binding,
            readback_profile_ref=resolved_profile,
        )
        return c8.recover_unknown_outcome(
            cell_id=cell_id,
            binding_digest=binding.binding_digest,
            attempt_digest=attempt_digest,
            readback_profile_ref=resolved_profile,
            outcome_digest=c8_canonical_digest(outcome),
        )


class C8ReadbackPort(Protocol):
    """Authoritative readback port for unknown-outcome C8 attempts."""

    def readback(
        self,
        *,
        attempt_digest: str,
        binding: RecoveryBinding,
        readback_profile_ref: str,
    ) -> dict[str, Any]: ...


class C8CapturedReadbackPort:
    """Captured read-only readback port; never executes a real effect."""

    def readback(
        self,
        *,
        attempt_digest: str,
        binding: RecoveryBinding,
        readback_profile_ref: str,
    ) -> dict[str, Any]:
        return {
            "outcome": "OUTCOME_UNKNOWN",
            "readback_required": True,
            "new_attempt_allowed": False,
            "attempt_digest": attempt_digest,
            "readback_profile_ref": readback_profile_ref,
        }
