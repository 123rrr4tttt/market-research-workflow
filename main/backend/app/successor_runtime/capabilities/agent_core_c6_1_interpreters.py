"""Bound successor interpreter for the C6.1 bounded episode atom."""

from __future__ import annotations

import dataclasses
from typing import Any, Protocol, runtime_checkable

from app.successor_runtime.capabilities import agent_core_c6_1 as c6_1
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
    "AGENT_CORE_C6_1_KIND",
    "AGENT_CORE_C6_1_LEGACY_INTERPRETER_ID",
    "AGENT_CORE_C6_1_OWNER",
    "AGENT_CORE_C6_1_SUCCESSOR_INTERPRETER_ID",
    "AgentCoreEpisodeInterpreter",
    "EpisodeBindingMismatch",
    "TurnRequestView",
    "authority_requirement_digest",
    "legacy_interpreter_profile_digest",
    "require_exact_episode_binding",
    "successor_interpreter_profile_digest",
]


AGENT_CORE_C6_1_KIND = c6_1.AGENT_CORE_C6_1_KIND
AGENT_CORE_C6_1_OWNER = c6_1.AGENT_CORE_C6_1_OWNER
AGENT_CORE_C6_1_LEGACY_INTERPRETER_ID = "legacy.agent_core.c6_1.episode.v1"
AGENT_CORE_C6_1_SUCCESSOR_INTERPRETER_ID = "successor.agent_core.c6_1.episode.v1"


@runtime_checkable
class ProjectScopeView(Protocol):
    project_key: str
    registry_revision: int
    incarnation: str
    scope_digest: str


@runtime_checkable
class TurnRequestView(Protocol):
    schema_version: str
    operation_kind: str
    project_scope: ProjectScopeView
    session_id: str
    turn_id: str
    message_ref: str
    max_iterations: int
    max_tool_calls: int
    approval_policy: str
    approved_call_ids: tuple[str, ...]
    resume_call_id: str | None
    cancel_requested: bool
    payload_digest: str


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and is_sha256_hex(value)


def require_exact_episode_binding(
    *,
    program: Any,
    plan: Any,
    contract_ref: OperationContractRef,
    payload_ref: Any,
    payload: TurnRequestView,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: Any,
    expected_interpreter_profile_digest: str | None = None,
) -> dict[str, str]:
    """Fail closed unless the complete C6.1 closure is exact."""

    failures: list[str] = []
    if payload.operation_kind != AGENT_CORE_C6_1_KIND:
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
    if metadata.get("session_id") != payload.session_id:
        failures.append("program metadata/session id")
    if metadata.get("turn_id") != payload.turn_id:
        failures.append("program metadata/turn id")
    if metadata.get("message_ref") != payload.message_ref:
        failures.append("program metadata/message ref")
    if metadata.get("max_iterations") != payload.max_iterations:
        failures.append("program metadata/max iterations")
    if metadata.get("max_tool_calls") != payload.max_tool_calls:
        failures.append("program metadata/max tool calls")
    if metadata.get("approval_policy") != payload.approval_policy:
        failures.append("program metadata/approval policy")
    if metadata.get("approved_call_ids") != tuple(payload.approved_call_ids):
        failures.append("program metadata/approved call ids")
    if metadata.get("resume_call_id") != payload.resume_call_id:
        failures.append("program metadata/resume call id")
    if metadata.get("cancel_requested") != payload.cancel_requested:
        failures.append("program metadata/cancel requested")

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
        != c6_1.AGENT_CORE_C6_1_PAYLOAD_TYPE.type_id
    ):
        failures.append("plan input type")
    if (
        getattr(plan.output_type, "type_id", None)
        != c6_1.AGENT_CORE_C6_1_RESULT_TYPE.type_id
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

    if contract_ref.kind != AGENT_CORE_C6_1_KIND:
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
        != c6_1.AGENT_CORE_C6_1_PAYLOAD_TYPE.type_id
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
        raise EpisodeBindingMismatch(
            "C6.1 episode binding drift: " + ", ".join(sorted(set(failures)))
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
            "interpreter_id": AGENT_CORE_C6_1_LEGACY_INTERPRETER_ID,
            "version": "1.0.0",
            "donor": "AgentCore.run ordered model/tool loop",
        }
    )


def successor_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": AGENT_CORE_C6_1_SUCCESSOR_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "successor-native bounded episode algebra",
        }
    )


def authority_requirement_digest() -> str:
    return content_digest(
        {
            "schema": "mrw.successor.agent-core.c6-1.authority.v1",
            "canonical_owner": AGENT_CORE_C6_1_OWNER,
            "authority": "bounded episode interpretation only",
            "grant_scope": "project",
        }
    )


class EpisodeBindingMismatch(ValueError):
    """Raised when Program/Plan/payload/tool/binding drift."""


class AgentCoreEpisodeInterpreter:
    """Bound successor interpreter for the C6.1 bounded episode atom."""

    interpreter_id = AGENT_CORE_C6_1_SUCCESSOR_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: OperationContractRef,
        payload_ref: Any,
        payload: c6_1.AgentTurnRequest,
        project_scope: ProjectScope,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: Any,
        model_step_source: c6_1.ModelStepSource,
        tool_specimens: tuple[c6_1.ToolSpecimen, ...],
        permission_policy: c6_1.PermissionPolicy,
        redactor: c6_1.EventRedactor,
    ) -> InterpreterOutcome[c6_1.AgentTurnEpisode]:
        try:
            require_exact_episode_binding(
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
        except EpisodeBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )
        outcome = c6_1.interpret_agent_turn(
            payload,
            model_step_source=model_step_source,
            tool_specimens=tool_specimens,
            permission_policy=permission_policy,
            redactor=redactor,
        )
        if isinstance(outcome, c6_1.AgentTurnFailure):
            return InterpreterFailure(
                code=outcome.code,
                message=outcome.message,
                retryable=outcome.retryable,
            )
        return InterpreterSuccess(outcome)
