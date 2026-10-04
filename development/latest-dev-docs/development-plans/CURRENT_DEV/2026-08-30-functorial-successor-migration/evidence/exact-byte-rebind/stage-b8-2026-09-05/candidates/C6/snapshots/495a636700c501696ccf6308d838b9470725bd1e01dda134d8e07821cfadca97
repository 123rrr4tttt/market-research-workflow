"""Bound successor interpreter for the C6.3 pre-persistence redaction atom.

The interpreter validates the exact Program/Plan/payload/policy/binding closure
and then applies the deterministic redaction transformation.  Raw source
values are call-time arguments only; the interpreter never returns, persists or
digests them.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Protocol, runtime_checkable

from app.successor_runtime.capabilities import agent_core_c6_3 as c6_3
from app.successor_runtime.capabilities.agent_core_c6_common import (
    InterpreterFailure,
    InterpreterOutcome,
    InterpreterSuccess,
    ProjectScope,
)
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.language.plan import with_plan_digest
from app.successor_runtime.research.codec import is_sha256_hex

__all__ = [
    "AGENT_CORE_C6_3_KIND",
    "AGENT_CORE_C6_3_LEGACY_INTERPRETER_ID",
    "AGENT_CORE_C6_3_OWNER",
    "AGENT_CORE_C6_3_SUCCESSOR_INTERPRETER_ID",
    "PolicyView",
    "ProjectScopeView",
    "RedactionBindingMismatch",
    "VersionedRedactionEvidenceInterpreter",
    "authority_requirement_digest",
    "legacy_interpreter_profile_digest",
    "require_exact_redaction_binding",
    "successor_interpreter_profile_digest",
]


AGENT_CORE_C6_3_KIND = c6_3.AGENT_CORE_C6_3_KIND
AGENT_CORE_C6_3_OWNER = c6_3.AGENT_CORE_C6_3_OWNER
AGENT_CORE_C6_3_LEGACY_INTERPRETER_ID = "legacy.agent_core.c6_3.redaction.v1"
AGENT_CORE_C6_3_SUCCESSOR_INTERPRETER_ID = "successor.agent_core.c6_3.redaction.v1"


@runtime_checkable
class ProjectScopeView(Protocol):
    project_key: str
    registry_revision: int
    incarnation: str
    scope_digest: str


@runtime_checkable
class PolicyView(Protocol):
    policy_id: str
    policy_version: str
    policy_digest: str


@runtime_checkable
class PayloadView(Protocol):
    schema_version: str
    operation_kind: str
    project_scope: ProjectScopeView
    source_observation_ref: str
    source_observation_digest: str
    source_kind: str
    trace_id: str
    request_id: str
    call_id: str
    interpreter_profile_ref: str
    policy: PolicyView
    field_classifications: Any
    max_input_bytes: int
    max_event_batch: int
    payload_digest: str


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and is_sha256_hex(value)


def require_exact_redaction_binding(
    *,
    program: Any,
    plan: Any,
    contract_ref: OperationContractRef,
    payload_ref: Any,
    payload: PayloadView,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: Any,
    expected_interpreter_profile_digest: str | None = None,
) -> dict[str, str]:
    """Fail closed unless the complete C6.3 closure is exact."""

    failures: list[str] = []
    if payload.operation_kind != AGENT_CORE_C6_3_KIND:
        failures.append("payload operation_kind")
    if program.project_key != project_scope.project_key:
        failures.append("program/project key")
    if program.project_registry_revision != project_scope.registry_revision:
        failures.append("program/registry revision")
    if program.project_scope_digest != project_scope.scope_digest:
        failures.append("program/scope digest")
    if payload.project_scope.project_key != project_scope.project_key:
        failures.append("payload/scope project key")
    if payload.project_scope.registry_revision != project_scope.registry_revision:
        failures.append("payload/scope registry revision")
    if payload.project_scope.scope_digest != project_scope.scope_digest:
        failures.append("payload/scope digest")

    metadata = dict(program.metadata)
    if metadata.get("resolved_schema") != project_scope.resolved_schema:
        failures.append("program metadata/resolved schema")
    if metadata.get("project_scope_incarnation") != project_scope.incarnation:
        failures.append("program metadata/scope incarnation")
    if metadata.get("source_observation_ref") != payload.source_observation_ref:
        failures.append("program metadata/source observation ref")
    if metadata.get("source_observation_digest") != payload.source_observation_digest:
        failures.append("program metadata/source observation digest")
    if metadata.get("source_kind") != payload.source_kind:
        failures.append("program metadata/source kind")
    if metadata.get("trace_id") != payload.trace_id:
        failures.append("program metadata/trace id")
    if metadata.get("request_id") != payload.request_id:
        failures.append("program metadata/request id")
    if metadata.get("call_id") != payload.call_id:
        failures.append("program metadata/call id")
    if metadata.get("interpreter_profile_ref") != payload.interpreter_profile_ref:
        failures.append("program metadata/interpreter profile ref")
    if metadata.get("policy_id") != payload.policy.policy_id:
        failures.append("program metadata/policy id")
    if metadata.get("policy_version") != payload.policy.policy_version:
        failures.append("program metadata/policy version")
    if metadata.get("policy_digest") != payload.policy.policy_digest:
        failures.append("program metadata/policy digest")

    if program.program_digest != program.digest():
        failures.append("program digest")
    if plan.program_id != program.program_id:
        failures.append("plan/program id")
    if plan.program_digest != program.program_digest:
        failures.append("plan/program digest")
    if not _is_hex64(plan.plan_digest):
        failures.append("plan digest")
    if with_plan_digest(plan).plan_digest != plan.plan_digest:
        failures.append("plan digest forged")
    if (
        getattr(plan.input_type, "type_id", None)
        != c6_3.AGENT_CORE_C6_3_PAYLOAD_TYPE.type_id
    ):
        failures.append("plan input type")
    if (
        getattr(plan.output_type, "type_id", None)
        != c6_3.AGENT_CORE_C6_3_RESULT_TYPE.type_id
    ):
        failures.append("plan output type")

    effect_steps = tuple(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    if len(effect_steps) != 1:
        failures.append("plan effect steps")
    else:
        step_ref = effect_steps[0].operation_contract_ref
        if (
            step_ref.kind != contract_ref.kind
            or step_ref.contract_version != contract_ref.contract_version
            or step_ref.contract_digest != contract_ref.contract_digest
        ):
            failures.append("plan/contract ref")
    if any(step.step_kind == "ADMISSION" for step in plan.ordered_steps):
        failures.append("plan admission step")

    if contract_ref.kind != AGENT_CORE_C6_3_KIND:
        failures.append("contract kind")
    if not _is_hex64(contract_ref.contract_digest):
        failures.append("contract digest")
    catalog_ref = catalog.lookup(contract_ref)
    if (
        catalog_ref is None
        or catalog_ref.contract_digest != contract_ref.contract_digest
    ):
        failures.append("catalog/contract ref")

    plain = dataclasses.asdict(payload)
    expected_content_digest = sha256_hex(canonical_json(plain).encode("utf-8"))
    if payload_ref.content_digest != expected_content_digest:
        failures.append("payload ref content digest")
    if payload_ref.project_key != project_scope.project_key:
        failures.append("payload ref project key")
    if (
        getattr(payload_ref.object_type, "type_id", None)
        != c6_3.AGENT_CORE_C6_3_PAYLOAD_TYPE.type_id
    ):
        failures.append("payload ref object type")
    if not _is_hex64(payload_ref.provenance_digest):
        failures.append("payload ref provenance digest")

    if not _is_hex64(binding.binding_digest):
        failures.append("binding digest")
    if (
        getattr(binding, "operation_contract_digest", None)
        != contract_ref.contract_digest
    ):
        failures.append("binding/contract digest")
    if getattr(binding, "project_scope_digest", None) != project_scope.scope_digest:
        failures.append("binding/scope digest")
    if not _is_hex64(deployment_catalog_digest):
        failures.append("deployment catalog digest")
    if getattr(binding, "deployment_catalog_digest", None) != deployment_catalog_digest:
        failures.append("binding/deployment catalog digest")
    if (
        expected_interpreter_profile_digest is not None
        and getattr(binding, "interpreter_profile_digest", None)
        != expected_interpreter_profile_digest
    ):
        failures.append("binding/interpreter profile")

    if failures:
        raise RedactionBindingMismatch(
            "C6.3 redaction binding drift: " + ", ".join(sorted(set(failures)))
        )
    return {
        "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest,
        "contract_digest": contract_ref.contract_digest,
        "payload_content_digest": payload_ref.content_digest,
        "binding_digest": binding.binding_digest,
    }


def legacy_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": AGENT_CORE_C6_3_LEGACY_INTERPRETER_ID,
            "version": "1.0.0",
            "donor": "provider_trace._redacted_tool_event_replay+_redacted_arguments_snapshot",
        }
    )


def successor_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": AGENT_CORE_C6_3_SUCCESSOR_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "successor-native pre-persistence redaction algebra",
        }
    )


def authority_requirement_digest() -> str:
    return content_digest(
        {
            "schema": "mrw.successor.agent-core.c6-3.authority.v1",
            "canonical_owner": AGENT_CORE_C6_3_OWNER,
            "authority": "versioned redaction before persistence",
            "grant_scope": "project",
        }
    )


class RedactionBindingMismatch(ValueError):
    """Raised when Program/Plan/payload/policy/binding drift."""


class VersionedRedactionEvidenceInterpreter:
    """Bound successor interpreter for the C6.3 redaction atom."""

    interpreter_id = AGENT_CORE_C6_3_SUCCESSOR_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: OperationContractRef,
        payload_ref: Any,
        payload: c6_3.RedactionEvidencePayload,
        project_scope: ProjectScope,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: Any,
        raw_observation: Any,
    ) -> InterpreterOutcome[c6_3.RedactionReceipt]:
        try:
            require_exact_redaction_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    successor_interpreter_profile_digest()
                ),
            )
        except RedactionBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )

        outcome = c6_3.redact_observation(payload, raw_observation)
        if isinstance(outcome, c6_3.RedactionFailure):
            return InterpreterFailure(
                code=outcome.code,
                message=outcome.message,
                retryable=outcome.retryable,
            )
        return InterpreterSuccess(outcome)
