"""Real-PostgreSQL RuntimeNode canary for the P3 C6 family-local line.

The canary is opt-in (``SUCCESSOR_TEST_DATABASE_URL`` names a dedicated
test/CI database), creates the unique disposable schema
``mrw_p3_c6_worker_test``, promotes SHADOW->CANARY authority, claims and
executes one exact RuntimeAssignment per C6 cell through a store-rehydrated
handler (deterministic provider/receipt-only port/C2.1 pure tool loop), proves
lease/attempt/reservation/terminal rows with ``provider_calls=0`` and raw
sentinel absence, then rolls back to legacy as the only future claim owner.
The schema is dropped on teardown; no live provider or network is touched.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_migration import legacy_agent_core
from app.successor_runtime.capabilities import (
    agent_core_c6_1 as c6_1,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_2 as c6_2,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_3 as c6_3,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStep,
    AgentToolCall,
    ProjectScope,
    c6_deployment_catalog_digest,
    freeze_c6_json_object,
)
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest
from app.successor_runtime.capabilities.source_library_c2_1 import (
    source_item_definition_content_digest,
)
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.research.codec import sha256_hex
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
    AuthorityResourceLimit,
)
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    NodeIdentity,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
    ProjectScopeRef,
    RuntimeScope,
)
from app.successor_runtime.runtime.qualification import (
    QualifiedPlan,
    StepAuthorizationBinding,
)
from app.successor_runtime.runtime.resources import QueueEligibility, ResourceClass
from app.successor_runtime.substrate.postgres.agent_core_c6_canary import (
    AgentCoreC6CanaryService,
    C6CanaryPhase,
    C6CanaryTransitionPacket,
    select_future_owner,
)
from app.successor_runtime.substrate.postgres.agent_core_c6_canary import (
    authority_digest as c6_authority_digest,
)
from app.successor_runtime.substrate.postgres.agent_core_c6_handler import (
    AgentCoreC6StoreRehydratedHandler,
)
from app.successor_runtime.substrate.postgres.agent_core_c6_worker import (
    AgentCoreC6WorkerStore,
)
from app.successor_runtime.substrate.postgres.approvals import (
    ApprovalBinding,
    ApprovalRepository,
)
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrant,
    AuthorityGrantRepository,
)
from app.successor_runtime.substrate.postgres.authority_provider import (
    PostgresAuthorityProvider,
)
from app.successor_runtime.substrate.postgres.composition_root import (
    ExactInstalledHandlerResolver,
    PostgresCancellationAuthorityGuard,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.node_adapter import (
    PostgresRuntimeNodeAdapter,
    runtime_uow_factory,
)
from app.successor_runtime.substrate.postgres.nodes import (
    DeploymentCatalog,
    DeploymentCatalogRepository,
    RuntimeNodeRepository,
)
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.qualification_store import (
    QualificationStoreRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactQualificationBinding,
    RuntimeJournalRepository,
)
from app.successor_runtime.substrate.postgres.session import (
    create_runtime_engine,
)
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork
from app.successor_runtime.substrate.postgres.values import ValueRepository

pytestmark = pytest.mark.integration

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_SCHEMA = "mrw_p3_c6_worker_test"
PROJECT_KEY = "p3-c6-runtime-canary"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "c6-canary-incarnation-1"
SCOPE_DIGEST = ProjectScope(
    PROJECT_KEY,
    REGISTRY_REVISION,
    PROJECT_SCHEMA,
    SCOPE_INCARNATION,
    "",
).scope_digest
ACTOR = "human:p3-c6-canary"
NOW = datetime(2030, 9, 1, 8, 0, tzinfo=UTC)
NODE_ID = "node:p3-c6-canary"
NODE_INCARNATION = "node-inc:p3-c6-canary"
CANARY_EPOCH = 1
RAW_SENTINEL = "mrw-p3-c6-canary-raw-secret::api_key=fixture-key"

ALLOWLIST_DIGEST = hashlib.sha256(b"c6-allowlist").hexdigest()
CONFIG_DIGEST = hashlib.sha256(b"c6-config").hexdigest()
DEPLOYMENT_CATALOG_DIGEST = c6_deployment_catalog_digest()
CLAIM_POLICY_DIGEST = hashlib.sha256(b"c6-claim-policy").hexdigest()
RESOURCE_POLICY_DIGEST = hashlib.sha256(b"c6-resource-policy").hexdigest()
NODE_PROFILE_DIGEST = hashlib.sha256(b"c6-node-profile").hexdigest()
RESOURCE_POLICY_EPOCH = 1


def _digest(value: str | bytes) -> str:
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class _C6Fixture:
    cell: str
    index: int
    resume: bool
    capability_id: str
    run_id: str
    step_id: str
    work_item_id: str
    program_id: str
    run_incarnation: str
    payload_incarnation: str
    payload: Any
    program: Any
    plan: Any
    catalog: Any
    contract_ref: Any
    value_ref: Any
    successor_binding: Any
    legacy_binding: Any
    recovery_binding: Any
    return_binding: Any
    assignment: Any
    step_authorization: Any
    shadow_before_digest: str
    canary_after_digest: str
    rollback_after_digest: str
    expected_output_digest: str
    handler: Any


def _scope_ref() -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=PROJECT_SCHEMA,
            project_registry_revision=REGISTRY_REVISION,
            incarnation=SCOPE_INCARNATION,
            scope_digest=SCOPE_DIGEST,
        ),
        actor_id=ACTOR,
    )


def _c2_1_item() -> dict[str, object]:
    item = {
        "item_key": "handler.cluster.news",
        "channel_key": "handler.cluster",
        "enabled": True,
        "params": {"keywords": ["robotics"], "limit": 3},
        "revision": 1,
        "incarnation": "item-inc-1",
    }
    item["content_digest"] = source_item_definition_content_digest(item)
    return item


def _c2_1_arguments() -> dict[str, object]:
    return {
        "project_key": PROJECT_KEY,
        "registry_revision": REGISTRY_REVISION,
        "resolved_schema": PROJECT_SCHEMA,
        "scope_incarnation": SCOPE_INCARNATION,
        "channels": [
            {
                "channel_key": "handler.cluster",
                "provider_type": "native",
                "enabled": True,
            }
        ],
        "item": _c2_1_item(),
        "params": {
            "query_terms": ["robotics", RAW_SENTINEL],
            "site_entries": ["https://example.com/search?q={{q}}"],
        },
    }


def _c6_1_payload() -> c6_1.AgentTurnRequest:
    return c6_1.AgentTurnRequest(
        schema_version=c6_1.AGENT_CORE_C6_1_PAYLOAD_SCHEMA,
        operation_kind=c6_1.AGENT_CORE_C6_1_KIND,
        project_scope=ProjectScope(
            PROJECT_KEY,
            REGISTRY_REVISION,
            PROJECT_SCHEMA,
            SCOPE_INCARNATION,
            "",
        ),
        session_id="session-c6-canary",
        turn_id="turn-c6-canary",
        message_ref="project-value:message:c6-canary",
        max_iterations=4,
        max_tool_calls=3,
        approval_policy="frozen",
    )


def _c6_1_resume_payload() -> c6_1.AgentTurnRequest:
    resume_call_id = "call-c6-canary-resume"
    return c6_1.AgentTurnRequest(
        schema_version=c6_1.AGENT_CORE_C6_1_PAYLOAD_SCHEMA,
        operation_kind=c6_1.AGENT_CORE_C6_1_KIND,
        project_scope=ProjectScope(
            PROJECT_KEY,
            REGISTRY_REVISION,
            PROJECT_SCHEMA,
            SCOPE_INCARNATION,
            "",
        ),
        session_id="session-c6-canary",
        turn_id="turn-c6-canary-resume",
        message_ref="project-value:message:c6-canary",
        max_iterations=4,
        max_tool_calls=3,
        approval_policy="enabled",
        approved_call_ids=(resume_call_id,),
        resume_call_id=resume_call_id,
        resume_tool_call=AgentToolCall(
            call_id=resume_call_id,
            tool_name=legacy_agent_core.C2_1_PURE_TOOL_NAME,
            arguments=freeze_c6_json_object(_c2_1_arguments()),
        ),
    )


def _c6_1_steps(*, resume: bool = False) -> tuple[AgentModelStep, ...]:
    if resume:
        return (
            AgentModelStep(
                schema_version="mrw.successor.agent-core.c6.model-step.v1",
                step_type="final_answer",
                content="resumed answer",
            ),
        )
    tool_call = AgentToolCall(
        call_id="call-c6-canary-c2-1",
        tool_name=legacy_agent_core.C2_1_PURE_TOOL_NAME,
        arguments=freeze_c6_json_object(_c2_1_arguments()),
    )
    return (
        AgentModelStep(
            schema_version="mrw.successor.agent-core.c6.model-step.v1",
            step_type="tool_calls",
            tool_calls=(tool_call,),
        ),
        AgentModelStep(
            schema_version="mrw.successor.agent-core.c6.model-step.v1",
            step_type="final_answer",
            content="c6 canary answer",
        ),
    )


class _ScriptedModelStepSource:
    def __init__(self, steps) -> None:
        self.steps = list(steps)

    def next_step(self, *, request, tool_names, transcript, remaining_budget):
        if self.steps:
            return self.steps.pop(0)
        return AgentModelStep(
            schema_version="mrw.successor.agent-core.c6.model-step.v1",
            step_type="final_answer",
            content="exhausted",
        )


def _c6_2_payload() -> c6_2.AgentModelStepRequest:
    return c6_2.AgentModelStepRequest(
        schema_version=c6_2.AGENT_CORE_C6_2_PAYLOAD_SCHEMA,
        operation_kind=c6_2.AGENT_CORE_C6_2_KIND,
        project_scope=ProjectScope(
            PROJECT_KEY,
            REGISTRY_REVISION,
            PROJECT_SCHEMA,
            SCOPE_INCARNATION,
            "",
        ),
        session_id="session-c6-canary",
        turn_id="turn-c6-canary",
        message_ref="project-value:message:c6-canary",
        transcript_ref="project-value:transcript:c6-canary",
        tool_contract_refs=("source_library.resolve_execution_request.v1",),
        max_iterations=4,
        iteration=1,
        max_tool_calls=3,
        remaining_tool_calls=3,
        provider_profile_ref="receipt_only",
        credential_ref="credential:opaque:c6-canary",
    )


def _c6_3_payload() -> tuple[c6_3.RedactionEvidencePayload, dict[str, object]]:
    classifications = {"provider.request": "REDACT", "provider.headers": "OMIT"}
    policy = c6_3.RedactionPolicyRef(
        policy_id="c6-3-canary-policy",
        policy_version="1",
        policy_digest=c6_3.redaction_policy_digest(
            "c6-3-canary-policy", "1", classifications
        ),
    )
    raw: dict[str, object] = {
        "provider": {
            "request": {"body": RAW_SENTINEL},
            "headers": {"authorization": "Bearer fixture-token"},
        },
        "notes": "visible",
    }
    payload = c6_3.RedactionEvidencePayload(
        schema_version=c6_3.AGENT_CORE_C6_3_PAYLOAD_SCHEMA,
        operation_kind=c6_3.AGENT_CORE_C6_3_KIND,
        project_scope=ProjectScope(
            PROJECT_KEY,
            REGISTRY_REVISION,
            PROJECT_SCHEMA,
            SCOPE_INCARNATION,
            "",
        ),
        source_observation_ref="project-value:source:c6-canary",
        source_observation_digest=c6_3.source_observation_digest(raw),
        source_kind="agent_core.tool_event",
        trace_id="trace-c6-canary",
        request_id="req-c6-canary",
        call_id="call-c6-canary",
        interpreter_profile_ref="successor.agent_core.c6_3.redaction.v1",
        policy=policy,
        field_classifications=freeze_c6_json_object(classifications),
        max_input_bytes=c6_3.REDACTION_RESOURCE_CEILING.max_input_bytes,
        max_event_batch=c6_3.REDACTION_RESOURCE_CEILING.max_event_batch,
    )
    return payload, raw


def _c6_fixture(
    engine: Engine, cell: str, index: int, *, resume: bool = False
) -> _C6Fixture:
    from app.successor_runtime.capabilities.agent_core_c6_1_program import (
        build_agent_core_c6_1_program,
        compile_agent_core_c6_1_program,
    )
    from app.successor_runtime.capabilities.agent_core_c6_1_program import (
        payload_value_ref as payload_value_ref_1,
    )
    from app.successor_runtime.capabilities.agent_core_c6_2_program import (
        build_agent_core_c6_2_program,
        compile_agent_core_c6_2_program,
    )
    from app.successor_runtime.capabilities.agent_core_c6_2_program import (
        payload_value_ref as payload_value_ref_2,
    )
    from app.successor_runtime.capabilities.agent_core_c6_3_program import (
        build_agent_core_c6_3_program,
        compile_agent_core_c6_3_program,
    )
    from app.successor_runtime.capabilities.agent_core_c6_3_program import (
        payload_value_ref as payload_value_ref_3,
    )

    run_id = f"run:p3-c6-canary-{index}"
    work_item_id = f"work:p3-c6-canary-{index}"
    program_id = f"program:p3-c6-canary-{index}"
    run_incarnation = f"run-inc:p3-c6-canary-{index}"
    payload_incarnation = f"payload-inc:{cell}-canary"
    capability_id = {
        "c6_1": c6_1.AGENT_CORE_C6_1_OWNER,
        "c6_2": c6_2.AGENT_CORE_C6_2_OWNER,
        "c6_3": c6_3.AGENT_CORE_C6_3_OWNER,
    }[cell]

    if cell == "c6_1":
        payload = _c6_1_resume_payload() if resume else _c6_1_payload()
        bundle = c6_1.build_agent_core_c6_1_bundle()
        catalog = c6_1.build_agent_core_c6_1_catalog(bundle)
        registry = c6_1.build_agent_core_c6_1_registry(bundle)
        program = build_agent_core_c6_1_program(
            payload=payload,
            catalog=catalog,
            program_id=program_id,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
        )
        plan = compile_agent_core_c6_1_program(
            program, catalog, operation_contracts=registry
        )
        value_ref = payload_value_ref_1(
            payload, program_id=program_id, project_key=PROJECT_KEY
        )
        readback_ref = "readback:c6-1-episode.v1"
    elif cell == "c6_2":
        payload = _c6_2_payload()
        bundle = c6_2.build_agent_core_c6_2_bundle()
        catalog = c6_2.build_agent_core_c6_2_catalog(bundle)
        registry = c6_2.build_agent_core_c6_2_registry(bundle)
        program = build_agent_core_c6_2_program(
            payload=payload,
            catalog=catalog,
            program_id=program_id,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
        )
        plan = compile_agent_core_c6_2_program(
            program, catalog, operation_contracts=registry
        )
        value_ref = payload_value_ref_2(
            payload, program_id=program_id, project_key=PROJECT_KEY
        )
        readback_ref = "readback:c6-2-provider.v1"
    else:
        payload, raw = _c6_3_payload()
        bundle = c6_3.build_agent_core_c6_3_bundle()
        catalog = c6_3.build_agent_core_c6_3_catalog(bundle)
        registry = c6_3.build_agent_core_c6_3_registry(bundle)
        program = build_agent_core_c6_3_program(
            payload=payload,
            catalog=catalog,
            program_id=program_id,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
        )
        plan = compile_agent_core_c6_3_program(
            program, catalog, operation_contracts=registry
        )
        value_ref = payload_value_ref_3(
            payload, program_id=program_id, project_key=PROJECT_KEY
        )
        readback_ref = "readback:c6-3-redaction.v1"

    effect_steps = tuple(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    if len(effect_steps) != 1:  # pragma: no cover - fixture guard
        raise RuntimeError(f"{cell} plan must compile exactly one EFFECT step")
    step = effect_steps[0]
    step_id = step.step_id
    contract_ref = step.operation_contract_ref
    successor_binding = legacy_agent_core.build_successor_agent_core_c6_1_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
        runtime_protocol_version="1",
    )
    if cell == "c6_2":
        successor_binding = legacy_agent_core.build_successor_agent_core_c6_2_binding(
            contract_digest=contract_ref.contract_digest,
            project_scope_digest=SCOPE_DIGEST,
            runtime_protocol_version="1",
        )
    elif cell == "c6_3":
        successor_binding = legacy_agent_core.build_successor_agent_core_c6_3_binding(
            contract_digest=contract_ref.contract_digest,
            project_scope_digest=SCOPE_DIGEST,
            runtime_protocol_version="1",
        )
    legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_1_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
        runtime_protocol_version="1",
    )
    if cell == "c6_2":
        legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_2_binding(
            contract_digest=contract_ref.contract_digest,
            project_scope_digest=SCOPE_DIGEST,
            runtime_protocol_version="1",
        )
    elif cell == "c6_3":
        legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_3_binding(
            contract_digest=contract_ref.contract_digest,
            project_scope_digest=SCOPE_DIGEST,
            runtime_protocol_version="1",
        )
    recovery_binding = RecoveryBinding.from_content(
        recovery_handler_id=f"recovery.{cell}.local-pure",
        recovery_handler_version="1",
        interpreter_profile_digest=successor_binding.interpreter_profile_digest,
        authoritative_readback_profile_ref=readback_ref,
    )
    return_binding = ReturnContractBinding.from_contract(
        step.return_contract_ref or "mrw.return.runtime-value.v1",
        step.return_contract,
    )
    queue = QueueEligibility(
        project_key=PROJECT_KEY,
        capability_id=capability_id,
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=RESOURCE_POLICY_EPOCH,
        policy_digest=RESOURCE_POLICY_DIGEST,
        concurrency_key=f"{cell}:concurrency",
        provider_key="provider:c6-local-pure-only",
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version=successor_binding.runtime_protocol_version,
        work_item_id=work_item_id,
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id=run_id,
        step_id=step_id,
        step_role=CompiledStepRole.EFFECT,
        capability_id=capability_id,
        operation_contract_ref=OperationContractRef(
            kind=contract_ref.kind,
            contract_version=contract_ref.contract_version,
            contract_digest=contract_ref.contract_digest,
        ),
        operation_contract_digest=contract_ref.contract_digest,
        return_contract_binding=return_binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=(
            f"handler-binding:sha256:{successor_binding.binding_digest}"
        ),
        handler_binding_digest=successor_binding.binding_digest,
        handler_binding=successor_binding,
        program_digest=program.program_digest,
        plan_digest=plan.plan_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation=run_incarnation,
        input_refs=(value_ref.storage_ref,),
        input_closure_digest=sha256_hex([value_ref.storage_ref]),
        payload_ref=value_ref.storage_ref,
        payload_digest=payload.payload_digest,
        queue_eligibility_digest=queue.eligibility_digest,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=CANARY_EPOCH,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        expected_step_revision=0,
        trace_id=f"trace:{run_id}",
    )
    authorization = StepAuthorizationBinding.from_content(
        run_id=run_id,
        step_id=step_id,
        operation_kind=contract_ref.kind,
        operation_contract_digest=contract_ref.contract_digest,
        capability_id=capability_id,
        claim_owner="successor",
        claim_authority_epoch=CANARY_EPOCH,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        payload_digest=payload.payload_digest,
        actor_id=ACTOR,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        interpreter_binding_digest=successor_binding.binding_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        authority_source_bindings=(),
        grants_digest=_digest(f"{cell}-grants"),
        approval_refs=(f"approval:c6-{index}-canary",),
        resource_ceiling_digest=_digest(f"{cell}-resource-ceiling"),
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        queue_eligibility_digest=queue.eligibility_digest,
        grant_epoch=1,
        expires_at=NOW + timedelta(days=1),
        canonical_base_revision=0,
        canonical_incarnation=run_incarnation,
    )
    approval_ref = f"approval:c6-{index}-canary"
    rollback_approval_ref = f"approval:c6-{index}-rollback"
    shadow_before_digest = c6_authority_digest(
        project_key=PROJECT_KEY,
        capability_id=capability_id,
        mode=C6CanaryPhase.SHADOW.mode,
        authority_epoch=0,
        successor_claim_enabled=False,
        legacy_claim_enabled=True,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        updated_by=ACTOR,
        approval_ref="approval:c6-shadow-baseline",
        rollback_target_ref=f"rollback:legacy:{cell}",
        revision=0,
    )
    canary_after_digest = c6_authority_digest(
        project_key=PROJECT_KEY,
        capability_id=capability_id,
        mode=C6CanaryPhase.CANARY.mode,
        authority_epoch=CANARY_EPOCH,
        successor_claim_enabled=True,
        legacy_claim_enabled=False,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        updated_by=ACTOR,
        approval_ref=approval_ref,
        rollback_target_ref=f"rollback:legacy:{cell}",
        revision=1,
    )
    rollback_after_digest = c6_authority_digest(
        project_key=PROJECT_KEY,
        capability_id=capability_id,
        mode=C6CanaryPhase.OFF.mode,
        authority_epoch=CANARY_EPOCH + 1,
        successor_claim_enabled=False,
        legacy_claim_enabled=True,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        updated_by=ACTOR,
        approval_ref=rollback_approval_ref,
        rollback_target_ref=f"rollback:legacy:{cell}",
        revision=2,
    )

    if cell == "c6_1":
        expected = c6_1.interpret_agent_turn(
            payload,
            model_step_source=_ScriptedModelStepSource(_c6_1_steps(resume=resume)),
            tool_specimens=(legacy_agent_core.C2_1PureToolSpecimen(),),
            permission_policy=c6_1.StaticPermissionPolicy(),
            redactor=c6_1.CanonicalJsonEventRedactor(),
        )
        assert isinstance(expected, c6_1.AgentTurnEpisode)
        expected_output_digest = expected.episode_digest
    elif cell == "c6_2":
        attempt_id = f"attempt:{run_id}:{step_id}"
        evidence = c6_2.build_c6_2_receipt_only_evidence(payload, attempt_id=attempt_id)
        expected_output_digest = evidence["result_digest"]
    else:
        receipt = c6_3.redact_observation(payload, raw)
        assert isinstance(receipt, c6_3.RedactionReceipt)
        expected_output_digest = receipt.receipt_digest

    return _C6Fixture(
        cell=cell,
        index=index,
        resume=resume,
        capability_id=capability_id,
        run_id=run_id,
        step_id=step_id,
        work_item_id=work_item_id,
        program_id=program_id,
        run_incarnation=run_incarnation,
        payload_incarnation=payload_incarnation,
        payload=payload,
        program=program,
        plan=plan,
        catalog=catalog,
        contract_ref=contract_ref,
        value_ref=value_ref,
        successor_binding=successor_binding,
        legacy_binding=legacy_binding,
        recovery_binding=recovery_binding,
        return_binding=return_binding,
        assignment=assignment,
        step_authorization=authorization,
        shadow_before_digest=shadow_before_digest,
        canary_after_digest=canary_after_digest,
        rollback_after_digest=rollback_after_digest,
        expected_output_digest=expected_output_digest,
        handler=None,
    )


def _require_dedicated_database_url() -> str:
    database_url = os.environ.get(DATABASE_ENV)
    if not database_url:
        pytest.skip(f"{DATABASE_ENV} is not set")
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        pytest.fail(f"{DATABASE_ENV} must use a PostgreSQL driver")
    database_name = url.database or ""
    if database_name in {"postgres", "template0", "template1"} or not re.search(
        r"(?:test|testing|ci)", database_name, re.IGNORECASE
    ):
        pytest.fail(
            f"{DATABASE_ENV} must name a dedicated test/CI database; "
            f"refusing database {database_name!r}"
        )
    return database_url


def _scope_row() -> dict[str, Any]:
    return {
        "project_key": PROJECT_KEY,
        "registry_revision": REGISTRY_REVISION,
        "resolved_schema": PROJECT_SCHEMA,
        "scope_digest": SCOPE_DIGEST,
        "incarnation": SCOPE_INCARNATION,
        "state": "ACTIVE",
        "updated_by": ACTOR,
        "approval_ref": "approval:c6-canary-project-scope",
    }


def _program_ref_row(fx: _C6Fixture) -> dict[str, Any]:
    return {
        "program_id": fx.program_id,
        "project_key": PROJECT_KEY,
        "program_digest": fx.program.program_digest,
        "project_storage_ref": f"project-value:{fx.program_id}",
        "contract_version": fx.program.contract_version,
    }


def _plan_ref_row(fx: _C6Fixture) -> dict[str, Any]:
    return {
        "plan_id": fx.plan.plan_id,
        "project_key": PROJECT_KEY,
        "plan_digest": fx.plan.plan_digest,
        "program_id": fx.plan.program_id,
        "program_digest": fx.plan.program_digest,
        "project_storage_ref": f"project-value:{fx.plan.plan_id}",
        "compiler_id": fx.plan.compiler_id,
        "compiler_version": fx.plan.compiler_version,
        "operation_catalog_id": fx.catalog.catalog_id,
        "catalog_version": fx.catalog.catalog_version,
        "catalog_digest": fx.catalog.catalog_digest,
        "effect_closure_digest": fx.plan.effect_closure_digest,
        "authority_closure_digest": fx.plan.authority_closure_digest,
        "resource_closure_digest": fx.plan.resource_closure_digest,
    }


def _run_row(fx: _C6Fixture) -> dict[str, Any]:
    return {
        "run_id": fx.run_id,
        "project_key": PROJECT_KEY,
        "project_registry_revision": REGISTRY_REVISION,
        "project_scope_digest": SCOPE_DIGEST,
        "resolved_schema": PROJECT_SCHEMA,
        "program_id": fx.program_id,
        "program_digest": fx.program.program_digest,
        "plan_id": fx.plan.plan_id,
        "plan_digest": fx.plan.plan_digest,
        "state": "RUNNING",
        "revision": 0,
        "next_event_seq": 1,
        "execution_epoch": 0,
        "incarnation": fx.run_incarnation,
        "submission_authority_digest": _digest(f"{fx.cell}-submission-authority"),
        "qualification_digest": _digest(f"{fx.cell}-qualification"),
        "cancellation_requested": False,
    }


def _step_row(fx: _C6Fixture) -> dict[str, Any]:
    return {
        "project_key": PROJECT_KEY,
        "run_id": fx.run_id,
        "step_id": fx.step_id,
        "operation_id": fx.contract_ref.kind,
        "operation_kind": fx.contract_ref.kind,
        "operation_version": fx.contract_ref.contract_version,
        "state": "READY",
        "revision": 0,
        "execution_epoch": 0,
        "input_digest": fx.assignment.input_closure_digest,
        "effect_class": {
            "c6_1": "PURE_LOCAL_EPISODE",
            "c6_2": "RECEIPT_ONLY_PROVIDER",
            "c6_3": "CPU_LIGHT_REDACTION",
        }[fx.cell],
        "resource_class": "CPU_LIGHT",
        "concurrency_key": f"{fx.cell}:concurrency",
        "capability_id": fx.capability_id,
        "claim_owner": "successor",
        "claim_authority_epoch": CANARY_EPOCH,
        "claim_policy_digest": CLAIM_POLICY_DIGEST,
        "max_attempts": 2,
    }


def _work_item_row(fx: _C6Fixture) -> dict[str, Any]:
    assignment = fx.assignment
    return {
        "work_item_id": assignment.work_item_id,
        "project_key": assignment.project_key,
        "run_id": assignment.run_id,
        "step_id": assignment.step_id,
        "assignment_kind": assignment.assignment_kind.value,
        "capability_id": assignment.capability_id,
        "operation_contract_digest": assignment.operation_contract_digest,
        "assignment_digest": assignment.assignment_digest,
        "assignment_binding_json": assignment.model_dump(mode="json"),
        "execution_epoch": assignment.execution_epoch,
        "assignment_incarnation": assignment.incarnation,
        "input_closure_digest": assignment.input_closure_digest,
        "claim_authority_epoch": assignment.claim_authority_epoch,
        "claim_policy_digest": assignment.claim_policy_digest,
        "handler_binding_kind": assignment.handler_binding_kind.value,
        "handler_binding_ref": assignment.handler_binding_ref,
        "handler_binding_digest": assignment.handler_binding_digest,
        "deployment_catalog_digest": assignment.deployment_catalog_digest,
        "runtime_protocol_version": assignment.runtime_protocol_version,
        "interpreter_profile_digest": fx.successor_binding.interpreter_profile_digest,
        "required_node_profile_selector": NODE_PROFILE_DIGEST,
        "program_digest": assignment.program_digest,
        "plan_digest": assignment.plan_digest,
        "qualification_digest": _digest(f"{fx.cell}-qualification"),
        "expected_step_revision": assignment.expected_step_revision,
        "payload_ref": assignment.payload_ref,
        "payload_digest": assignment.payload_digest,
        "authority_digest": fx.step_authorization.binding_digest,
        "resource_policy_digest": RESOURCE_POLICY_DIGEST,
        "resource_policy_epoch": assignment.resource_policy_epoch,
        "queue_eligibility_digest": assignment.queue_eligibility_digest,
        "resource_class": "CPU_LIGHT",
        "resource_units": 1,
        "concurrency_key": f"{fx.cell}:concurrency",
        "provider_key": "provider:c6-local-pure-only",
        "recovery_handler_binding_ref": (
            f"handler-binding:sha256:{fx.recovery_binding.binding_digest}"
        ),
        "recovery_handler_binding_digest": fx.recovery_binding.binding_digest,
        "recovery_binding_json": fx.recovery_binding.model_dump(mode="json"),
        "authoritative_readback_profile_ref": (
            fx.recovery_binding.authoritative_readback_profile_ref
        ),
        "fairness_key": PROJECT_KEY,
        "state": "READY",
        "declared_priority": 0,
        "enqueued_at": NOW,
        "due_at": NOW,
        "attempt_count": 0,
        "revision": 0,
    }


def _authority_row(fx: _C6Fixture) -> dict[str, Any]:
    return {
        "project_key": PROJECT_KEY,
        "capability_id": fx.capability_id,
        "mode": C6CanaryPhase.SHADOW.mode,
        "authority_epoch": 0,
        "successor_claim_enabled": False,
        "legacy_claim_enabled": True,
        "allowlist_digest": ALLOWLIST_DIGEST,
        "config_digest": CONFIG_DIGEST,
        "effective_at": NOW,
        "updated_by": ACTOR,
        "approval_ref": "approval:c6-shadow-baseline",
        "rollback_target_ref": f"rollback:legacy:{fx.cell}",
        "revision": 0,
    }


def _seed(connection: sa.Connection, fx: _C6Fixture) -> None:
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(**_program_ref_row(fx))
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_plan_refs"]).values(**_plan_ref_row(fx))
    )
    connection.execute(sa.insert(PUBLIC_TABLES["runtime_runs"]).values(**_run_row(fx)))
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_steps"]).values(**_step_row(fx))
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(**_work_item_row(fx))
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
            **_authority_row(fx)
        )
    )
    scope = _scope_ref()
    ProgramRepository(
        connection,
        project_tables(sa.MetaData(), PROJECT_SCHEMA),
    ).put_exact(scope, fx.program, fx.program.program_digest)
    PlanRepository(
        connection,
        project_tables(sa.MetaData(), PROJECT_SCHEMA),
    ).put_exact(
        scope,
        fx.plan,
        fx.plan.plan_digest,
        operation_catalog_id=fx.catalog.catalog_id,
        catalog_version=fx.catalog.catalog_version,
        catalog_digest=fx.catalog.catalog_digest,
    )
    exact_bytes = canonical_json(dataclasses.asdict(fx.payload)).encode("utf-8")
    ValueRepository(
        connection,
        project_tables(sa.MetaData(), PROJECT_SCHEMA),
    ).put_exact(
        scope,
        value_id=fx.value_ref.value_id,
        object_type=fx.value_ref.object_type.type_id,
        codec_id=fx.value_ref.codec_id,
        content=exact_bytes,
        expected_digest=fx.value_ref.content_digest,
        provenance_digest=fx.value_ref.provenance_digest,
        expected_revision=0,
        expected_incarnation=fx.payload_incarnation,
    )


def _seed_stores_only(connection: sa.Connection, fx: _C6Fixture) -> None:
    """Seed only public refs/run and project stores for rehydration tests."""

    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(**_program_ref_row(fx))
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_plan_refs"]).values(**_plan_ref_row(fx))
    )
    connection.execute(sa.insert(PUBLIC_TABLES["runtime_runs"]).values(**_run_row(fx)))
    scope = _scope_ref()
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    ProgramRepository(connection, tables).put_exact(
        scope, fx.program, fx.program.program_digest
    )
    PlanRepository(connection, tables).put_exact(
        scope,
        fx.plan,
        fx.plan.plan_digest,
        operation_catalog_id=fx.catalog.catalog_id,
        catalog_version=fx.catalog.catalog_version,
        catalog_digest=fx.catalog.catalog_digest,
    )
    exact_bytes = canonical_json(dataclasses.asdict(fx.payload)).encode("utf-8")
    ValueRepository(connection, tables).put_exact(
        scope,
        value_id=fx.value_ref.value_id,
        object_type=fx.value_ref.object_type.type_id,
        codec_id=fx.value_ref.codec_id,
        content=exact_bytes,
        expected_digest=fx.value_ref.content_digest,
        provenance_digest=fx.value_ref.provenance_digest,
        expected_revision=0,
        expected_incarnation=fx.payload_incarnation,
    )


def _persist_qualification(
    engine: Engine,
    fx: _C6Fixture,
) -> tuple[Any, Any, Any]:
    with engine.begin() as connection:
        scope = _scope_ref()
        context = PostgresAuthorityProvider(connection, scope).current_context(
            ACTOR,
            capability_id=fx.capability_id,
            approval_refs=(f"approval:c6-{fx.index}-canary",),
            canonical_base_revision=0,
            canonical_incarnation=f"canonical:{fx.run_id}:{fx.cell}:1",
            now=NOW,
        )
        authorization = StepAuthorizationBinding.from_content(
            run_id=fx.run_id,
            step_id=fx.step_id,
            operation_kind=fx.contract_ref.kind,
            operation_contract_digest=fx.contract_ref.contract_digest,
            capability_id=fx.capability_id,
            claim_owner="successor",
            claim_authority_epoch=CANARY_EPOCH,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            payload_digest=fx.payload.payload_digest,
            actor_id=ACTOR,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            interpreter_binding_digest=fx.successor_binding.binding_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            authority_source_bindings=context.authority_source_bindings,
            grants_digest=context.grants_digest,
            approval_refs=context.approval_refs or (f"approval:c6-{fx.index}-canary",),
            resource_ceiling_digest=context.resource_ceiling_digest,
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
            queue_eligibility_digest=fx.assignment.queue_eligibility_digest,
            grant_epoch=context.grant_epoch,
            expires_at=context.expires_at,
            canonical_base_revision=context.canonical_base_revision,
            canonical_incarnation=context.canonical_incarnation,
        )
        qualified = QualifiedPlan.from_content(
            plan_digest=fx.plan.plan_digest,
            authority_context_digest=context.context_digest,
            step_bindings=(authorization,),
        )
        exact = ExactQualificationBinding.from_content(
            qualification_id=f"qualification:c6-{fx.index}-canary",
            project_key=PROJECT_KEY,
            run_id=fx.run_id,
            plan_id=fx.plan.plan_id,
            plan_digest=fx.plan.plan_digest,
            authority_context=context,
            authority_context_digest=context.context_digest,
            qualified_plan=qualified,
            decision="QUALIFIED",
        )
        QualificationStoreRepository(connection, scope).persist(exact)
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_runs"])
            .where(
                PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_runs"].c.run_id == fx.run_id,
            )
            .values(qualification_digest=qualified.qualification_digest)
        )
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id == fx.work_item_id,
            )
            .values(
                qualification_digest=qualified.qualification_digest,
                authority_digest=authorization.binding_digest,
            )
        )
    return context, authorization, exact


def _approvals(connection: sa.Connection, fx: _C6Fixture) -> None:
    scope = _scope_ref()
    approvals = ApprovalRepository(connection, scope)
    approvals.decide(
        ApprovalBinding(
            approval_id=f"approval:c6-{fx.index}-canary",
            actor_id=ACTOR,
            run_id=fx.run_id,
            step_id=fx.step_id,
            payload_digest=fx.payload.payload_digest,
            decision="APPROVED",
            expires_at=NOW + timedelta(days=1),
            authority_digest=fx.canary_after_digest,
        )
    )
    approvals.decide(
        ApprovalBinding(
            approval_id=f"approval:c6-{fx.index}-rollback",
            actor_id=ACTOR,
            run_id=fx.run_id,
            step_id=fx.step_id,
            payload_digest=fx.payload.payload_digest,
            decision="APPROVED",
            expires_at=NOW + timedelta(days=1),
            authority_digest=fx.rollback_after_digest,
        )
    )


def _seed_public(engine: Engine, fx: _C6Fixture) -> None:
    with engine.begin() as connection:
        _approvals(connection, fx)
        DeploymentCatalogRepository(connection).put_exact(
            DeploymentCatalog(
                catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                catalog_version="1.0.0",
                catalog_ref="artifact:c6-canary-deployment",
                node_profile_digest=NODE_PROFILE_DIGEST,
                security_profile_digest=_digest("c6-security"),
                resource_profile_digest=_digest("c6-resource-profile"),
            )
        )
        RuntimeNodeRepository(connection).register(
            node_id=NODE_ID,
            node_profile_digest=NODE_PROFILE_DIGEST,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            runtime_protocol_version="1",
            started_at=NOW - timedelta(minutes=1),
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_resource_policies"]).values(
                resource_policy_id=f"policy:c6-{fx.index}-canary",
                project_key=PROJECT_KEY,
                capability_id=fx.capability_id,
                resource_class=ResourceClass.CPU_LIGHT.value,
                concurrency_limit=2,
                max_project_active=2,
                max_capability_active=2,
                max_resource_active=2,
                units_ceiling=2,
                budget_ceiling=None,
                provider_limit=None,
                policy_epoch=RESOURCE_POLICY_EPOCH,
                policy_digest=RESOURCE_POLICY_DIGEST,
                revision=0,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        scope = _scope_ref()
        AuthorityGrantRepository(connection, scope).create(
            AuthorityGrant(
                grant_id=f"grant:c6-{fx.index}-canary",
                actor_id=ACTOR,
                capability_id=fx.capability_id,
                operation_scope_json=AuthorityOperationScope.from_content(
                    operation_kinds=(fx.contract_ref.kind,),
                    project_scope_digest=SCOPE_DIGEST,
                ),
                resource_ceiling_json=AuthorityResourceCeiling.from_content(
                    limits=(
                        AuthorityResourceLimit(
                            resource_class=ResourceClass.CPU_LIGHT.value,
                            units=2,
                        ),
                    ),
                    max_active=2,
                ),
                credential_ref=None,
                grant_epoch=1,
                expires_at=NOW + timedelta(days=1),
            )
        )


def _seed_public_deployment(engine: Engine) -> None:
    """Seed only the idempotent deployment catalog and node registration."""

    with engine.begin() as connection:
        DeploymentCatalogRepository(connection).put_exact(
            DeploymentCatalog(
                catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                catalog_version="1.0.0",
                catalog_ref="artifact:c6-canary-deployment",
                node_profile_digest=NODE_PROFILE_DIGEST,
                security_profile_digest=_digest("c6-security"),
                resource_profile_digest=_digest("c6-resource-profile"),
            )
        )
        RuntimeNodeRepository(connection).register(
            node_id=NODE_ID,
            node_profile_digest=NODE_PROFILE_DIGEST,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            runtime_protocol_version="1",
            started_at=NOW - timedelta(minutes=1),
        )


class _TestClock:
    def __init__(self) -> None:
        self.current = NOW + timedelta(minutes=2)

    def now(self):
        result = self.current
        self.current += timedelta(seconds=1)
        return result


def _build_node(
    engine: Engine,
    fx: _C6Fixture,
) -> tuple[RuntimeNode, AgentCoreC6StoreRehydratedHandler]:
    uow_factory = runtime_uow_factory(engine)
    if fx.cell == "c6_1":
        handler = AgentCoreC6StoreRehydratedHandler(
            uow_factory=uow_factory,
            cell="c6_1",
            handler_binding_digest=fx.successor_binding.binding_digest,
            interpreter_profile_digest=fx.successor_binding.interpreter_profile_digest,
            operation_contract_digest=fx.contract_ref.contract_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            model_step_source=_ScriptedModelStepSource(_c6_1_steps(resume=fx.resume)),
            tool_specimens=(legacy_agent_core.C2_1PureToolSpecimen(),),
            permission_policy=c6_1.StaticPermissionPolicy(),
            redactor=c6_1.CanonicalJsonEventRedactor(),
        )
    elif fx.cell == "c6_2":
        handler = AgentCoreC6StoreRehydratedHandler(
            uow_factory=uow_factory,
            cell="c6_2",
            handler_binding_digest=fx.successor_binding.binding_digest,
            interpreter_profile_digest=fx.successor_binding.interpreter_profile_digest,
            operation_contract_digest=fx.contract_ref.contract_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            provider_port=c6_2.ReceiptOnlyProviderPort(),
        )
    else:
        _payload, raw = _c6_3_payload()
        handler = AgentCoreC6StoreRehydratedHandler(
            uow_factory=uow_factory,
            cell="c6_3",
            handler_binding_digest=fx.successor_binding.binding_digest,
            interpreter_profile_digest=fx.successor_binding.interpreter_profile_digest,
            operation_contract_digest=fx.contract_ref.contract_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            raw_observation=dict(raw),
        )
    lifecycle = PostgresRuntimeNodeAdapter(uow_factory)
    resolver = ExactInstalledHandlerResolver((handler,))
    node = RuntimeNode(
        identity=NodeIdentity(
            node_id=NODE_ID,
            incarnation=NODE_INCARNATION,
            started_at=NOW - timedelta(minutes=1),
        ),
        profile=RuntimeNodeProfile(
            profile_digest=NODE_PROFILE_DIGEST,
            supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
            interpreter_profile_digests=frozenset(
                {fx.successor_binding.interpreter_profile_digest}
            ),
        ),
        deployment=DeploymentBinding(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            node_profile_digest=NODE_PROFILE_DIGEST,
            runtime_protocol_version="1",
        ),
        protocol=RuntimeNodeProtocol(
            version="1",
            claim_batch_size=8,
            heartbeat_extension=timedelta(seconds=45),
        ),
        control_scope=ControlPlaneScope(
            system_actor_id=NODE_ID,
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=CANARY_EPOCH,
        ),
        claims=lifecycle,
        interpreters=resolver,
        outcomes=lifecycle,
        cancellation=PostgresCancellationAuthorityGuard(uow_factory),
        clock=_TestClock(),
    )
    return node, handler


def _promote_packet(fx: _C6Fixture) -> C6CanaryTransitionPacket:
    return C6CanaryTransitionPacket.from_content(
        transition_id=f"transition:c6-{fx.index}:promote-canary",
        capability_id=fx.capability_id,
        run_id=fx.run_id,
        step_id=fx.step_id,
        work_item_id=fx.work_item_id,
        program_digest=fx.program.program_digest,
        plan_digest=fx.plan.plan_digest,
        payload_digest=fx.payload.payload_digest,
        payload_ref=fx.value_ref.storage_ref,
        successor_binding_digest=fx.successor_binding.binding_digest,
        source_phase=C6CanaryPhase.SHADOW,
        target_phase=C6CanaryPhase.CANARY,
        expected_authority_epoch=0,
        expected_authority_revision=0,
        expected_run_revision=0,
        approval_ref=f"approval:c6-{fx.index}-canary",
        rollback_target_ref=f"rollback:legacy:{fx.cell}",
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        before_authority_digest=fx.shadow_before_digest,
        after_authority_digest=fx.canary_after_digest,
    )


def _rollback_packet(
    fx: _C6Fixture, *, expected_run_revision: int
) -> C6CanaryTransitionPacket:
    return C6CanaryTransitionPacket.from_content(
        transition_id=f"transition:c6-{fx.index}:rollback-legacy",
        capability_id=fx.capability_id,
        run_id=fx.run_id,
        step_id=fx.step_id,
        work_item_id=fx.work_item_id,
        program_digest=fx.program.program_digest,
        plan_digest=fx.plan.plan_digest,
        payload_digest=fx.payload.payload_digest,
        payload_ref=fx.value_ref.storage_ref,
        successor_binding_digest=fx.successor_binding.binding_digest,
        source_phase=C6CanaryPhase.CANARY,
        target_phase=C6CanaryPhase.OFF,
        expected_authority_epoch=CANARY_EPOCH,
        expected_authority_revision=1,
        expected_run_revision=expected_run_revision,
        approval_ref=f"approval:c6-{fx.index}-rollback",
        rollback_target_ref=f"rollback:legacy:{fx.cell}",
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        before_authority_digest=fx.canary_after_digest,
        after_authority_digest=fx.rollback_after_digest,
    )


@pytest.fixture(scope="module")
def canary_database() -> Iterator[dict[str, _C6Fixture]]:
    database_url = _require_dedicated_database_url()
    engine = create_runtime_engine(database_url, poolclass=NullPool)
    inspector = sa.inspect(engine)
    existing_public = set(inspector.get_table_names(schema="public")) & set(
        PUBLIC_TABLES
    )
    if existing_public:
        engine.dispose()
        pytest.fail(
            "dedicated database already contains successor public tables; "
            f"refusing overwrite: {sorted(existing_public)}"
        )
    project_metadata = sa.MetaData()
    project_tables(project_metadata, PROJECT_SCHEMA)
    fixtures = {
        cell: _c6_fixture(engine, cell, index)
        for index, cell in enumerate(("c6_1", "c6_2", "c6_3"), start=1)
    }
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(f'CREATE SCHEMA IF NOT EXISTS "{PROJECT_SCHEMA}"')
            )
            PUBLIC_METADATA.create_all(connection, checkfirst=False)
            project_metadata.create_all(connection, checkfirst=False)
            connection.execute(
                sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
                    **_scope_row()
                )
            )
            for fx in fixtures.values():
                _seed(connection, fx)
        for fx in fixtures.values():
            _seed_public(engine, fx)
        yield fixtures
    finally:
        with engine.begin() as connection:
            PUBLIC_METADATA.drop_all(connection, checkfirst=True)
            connection.execute(
                sa.text(f'DROP SCHEMA IF EXISTS "{PROJECT_SCHEMA}" CASCADE')
            )
        engine.dispose()


def _load_run(engine: Engine, fx: _C6Fixture) -> dict[str, Any]:
    with engine.connect() as connection:
        return RuntimeJournalRepository(connection, _scope_ref()).load_run(fx.run_id)


def _load_authority(engine: Engine, fx: _C6Fixture) -> dict[str, Any]:
    from app.successor_runtime.substrate.postgres.authority import (
        CapabilityAuthorityRepository,
    )

    with engine.connect() as connection:
        return CapabilityAuthorityRepository(connection, _scope_ref()).load(
            fx.capability_id
        )


def _runtime_rows(
    engine: Engine, fx: _C6Fixture
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    with engine.connect() as connection:
        attempt = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == fx.run_id,
                )
            )
            .mappings()
            .one()
        )
        step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_steps"].c.run_id == fx.run_id,
                    PUBLIC_TABLES["runtime_steps"].c.step_id == fx.step_id,
                )
            )
            .mappings()
            .one()
        )
        work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                    == fx.work_item_id,
                )
            )
            .mappings()
            .one()
        )
        events = RuntimeJournalRepository(connection, _scope_ref()).load_events(
            fx.run_id
        )
    return dict(attempt), dict(step), dict(work), [dict(event) for event in events]


@pytest.mark.parametrize(
    "cell",
    ["c6_1", "c6_2", "c6_3"],
)
def test_c6_runtime_node_canary_terminal_and_future_owner_rollback(
    cell: str, canary_database: dict[str, _C6Fixture]
) -> None:
    engine = None
    fx = canary_database[cell]
    # Re-open the engine through the module fixture's stored URL is not
    # possible; execute everything through a fresh engine over the same DB.
    database_url = _require_dedicated_database_url()
    engine = create_runtime_engine(database_url, poolclass=NullPool)
    try:
        with RuntimeUnitOfWork(engine=engine) as uow:
            service = AgentCoreC6CanaryService(uow.connection, _scope_ref())
            receipt = service.promote_canary(_promote_packet(fx), now=NOW)
            uow.commit()
        assert receipt.authority_epoch == CANARY_EPOCH
        assert receipt.run_revision == 1

        authority = _load_authority(engine, fx)
        assert authority["mode"] == "canary"
        assert authority["successor_claim_enabled"] is True
        assert authority["legacy_claim_enabled"] is False
        assert select_future_owner(authority) == "successor"

        _persist_qualification(engine, fx)
        node, handler = _build_node(engine, fx)
        report = node.run_once()
        assert report.claimed == 1
        assert len(report.results) == 1
        result = report.results[0]
        assert result.state.value == "COMMITTED"
        assert result.executed is True
        assert result.committed is True
        assert result.disposition.value == "SUCCEEDED"
        assert handler.provider_calls == 0

        attempt, step, work, events = _runtime_rows(engine, fx)
        assert attempt["attempt_id"] == result.attempt_id
        assert attempt["disposition"] == "SUCCEEDED"
        assert attempt["handler_binding_digest"] == fx.successor_binding.binding_digest
        assert step["state"] == "SUCCEEDED"
        assert step["output_digest"] == fx.expected_output_digest
        assert work["state"] == "COMPLETED"
        assert work["lease_token"] is None
        assert work["lease_owner"] is None
        assert all(row["state"] == "RELEASED" for row in reservations_of(engine, fx))
        terminal = next(
            event for event in events if event["event_type"] == "RuntimeValueProduced"
        )
        assert terminal["schema_version"] == "mrw.runtime.event.effect_succeeded.v1"
        assert terminal["step_id"] == fx.step_id
        assert events[0]["event_type"] == "CapabilityAuthorityChanged"

        encoded_runtime = json.dumps(
            [attempt, step, work, events], sort_keys=True, default=str
        )
        assert RAW_SENTINEL not in encoded_runtime
        if cell == "c6_3":
            receipt = c6_3.redact_observation(fx.payload, _c6_3_payload()[1])
            assert isinstance(receipt, c6_3.RedactionReceipt)
            with engine.begin() as connection:
                store = AgentCoreC6WorkerStore(connection, PROJECT_SCHEMA)
                store.install()
                store.persist_receipt(
                    cell="c6_3",
                    receipt_id=content_digest(receipt.to_plain()),
                    outcome_code="RedactionSucceeded",
                    provider_calls=0,
                    redacted_value=dict(receipt.evidence.redacted_value),
                    receipt_plain=receipt.to_plain(),
                    forbidden_sentinel=RAW_SENTINEL,
                )
                assert store.raw_sentinel_present(RAW_SENTINEL) is False

        run_revision = int(_load_run(engine, fx)["revision"])
        event_count = len(events)
        with RuntimeUnitOfWork(engine=engine) as uow:
            service = AgentCoreC6CanaryService(uow.connection, _scope_ref())
            rollback = service.rollback_legacy(
                _rollback_packet(fx, expected_run_revision=run_revision),
                now=NOW,
            )
            uow.commit()
        assert rollback.authority_epoch == CANARY_EPOCH + 1
        authority = _load_authority(engine, fx)
        assert authority["mode"] == "off"
        assert authority["successor_claim_enabled"] is False
        assert authority["legacy_claim_enabled"] is True
        assert int(authority["authority_epoch"]) == CANARY_EPOCH + 1
        assert select_future_owner(authority) == "legacy"

        _attempt, _step, _work, after_events = _runtime_rows(engine, fx)
        assert len(after_events) == event_count + 1
        assert after_events[-1]["event_type"] == "CapabilityAuthorityChanged"
        assert _attempt["disposition"] == "SUCCEEDED"
        assert _step["output_digest"] == fx.expected_output_digest

        second_node, _second_handler = _build_node(engine, fx)
        second_report = second_node.run_once()
        assert second_report.claimed == 0
        assert second_report.results == ()
    finally:
        if engine is not None:
            engine.dispose()


def reservations_of(engine: Engine, fx: _C6Fixture) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_resource_reservations"]).where(
                    PUBLIC_TABLES["runtime_resource_reservations"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_resource_reservations"].c.run_id
                    == fx.run_id,
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def test_c6_store_rehydrated_pause_resume_round_trip(
    canary_database: dict[str, _C6Fixture],
) -> None:
    database_url = _require_dedicated_database_url()
    engine = create_runtime_engine(database_url, poolclass=NullPool)
    try:
        fx = _c6_fixture(engine, "c6_1", 9, resume=True)
        with engine.begin() as connection:
            _seed_stores_only(connection, fx)
        _seed_public_deployment(engine)
        _node, handler = _build_node(engine, fx)
        loaded = handler._load_exact_closure(fx.assignment, NODE_ID)
        assert isinstance(loaded.payload.resume_tool_call, c6_1.AgentToolCall)
        assert loaded.payload.resume_tool_call.call_id == "call-c6-canary-resume"
        assert loaded.payload.resume_call_id == loaded.payload.resume_tool_call.call_id
        assert "call-c6-canary-resume" in loaded.payload.approved_call_ids
        outcome = c6_1.interpret_agent_turn(
            loaded.payload,
            model_step_source=_ScriptedModelStepSource(_c6_1_steps(resume=True)),
            tool_specimens=(legacy_agent_core.C2_1PureToolSpecimen(),),
            permission_policy=c6_1.StaticPermissionPolicy(),
            redactor=c6_1.CanonicalJsonEventRedactor(),
        )
        assert isinstance(outcome, c6_1.AgentTurnEpisode)
        assert outcome.stop_reason == "final_answer"
        assert outcome.tool_call_count == 1
        event_types = [event.event_type for event in outcome.ordered_events]
        assert "run_resumed" in event_types
        assert "tool_result" in event_types
    finally:
        engine.dispose()
