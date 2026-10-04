"""Thin C6/P3 family fragment config for the shared family generator.

This module declares only the C6 family data and differences: family identity,
exact binding targets and the family observation glue that calls the existing
C6 capability modules.  No full fragment generator pipeline is copied;
canonical JSON/digest, path confinement, authority ceiling, determinism and
the read-only check gate live in ``shared_family_generator``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.successor_migration import legacy_agent_core
from app.successor_migration.legacy_agent_core import (
    CoreModelStep,
    FakeCoreProvider,
)
from app.successor_runtime.capabilities import agent_core_c6_1 as c6_1
from app.successor_runtime.capabilities import (
    agent_core_c6_1_interpreters as c6_1i,
)
from app.successor_runtime.capabilities import agent_core_c6_1_program as c6_1p
from app.successor_runtime.capabilities import agent_core_c6_2 as c6_2
from app.successor_runtime.capabilities import (
    agent_core_c6_2_interpreters as c6_2i,
)
from app.successor_runtime.capabilities import agent_core_c6_2_program as c6_2p
from app.successor_runtime.capabilities import agent_core_c6_3 as c6_3
from app.successor_runtime.capabilities import (
    agent_core_c6_3_interpreters as c6_3i,
)
from app.successor_runtime.capabilities import agent_core_c6_3_program as c6_3p
from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStep,
    AgentToolCall,
    ProjectScope,
    c6_deployment_catalog_digest,
    freeze_c6_json_object,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_library_c2_1 import (
    source_item_definition_content_digest,
)
from app.successor_runtime.specification.shared_family_generator import (
    BindingsByKind,
    BindingTarget,
    FamilyFragmentConfig,
)

PROJECT_KEY = "demo_proj"
REGISTRY_REVISION = 5
RESOLVED_SCHEMA = "mrw_p_demo_proj"
SCOPE_INCARNATION = "scope-inc-5"
SCOPE_DIGEST = ProjectScope(
    PROJECT_KEY,
    REGISTRY_REVISION,
    RESOLVED_SCHEMA,
    SCOPE_INCARNATION,
    "",
).scope_digest
ATTEMPT_ID = "attempt:c6-2:fragment"
RAW_SENTINEL = "mrw-c6-fragment-sentinel::api_key=fixture-key"
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_EVIDENCE_ROOT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
FRAGMENT_OUTPUT_REL = f"{_EVIDENCE_ROOT}/p3-fragments/C6.json"
FRAGMENT_ID = "p3-c6-family-local-implementation"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p3_fragment.v1"
FRAGMENT_PHASE = "P3"
FRAGMENT_FAMILY = "C6"
FRAGMENT_STATUS = "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"

AUTHORITY = {
    "production_canonical_write": False,
    "live_provider": False,
    "external_delivery": False,
    "live_credential": False,
    "network": False,
    "cutover": False,
    "authority_transfer": False,
    "legacy_retired": False,
    "p3_promotion": False,
}

OPEN_FINDINGS = (
    {
        "id": "P3C6_PRODUCTION_RUNTIME_NODE_NOT_PROVEN",
        "severity": "P1",
        "description": (
            "disposable local RuntimeNode canary is proven for all C6 "
            "cells; production RuntimeNode/cutover remains pending"
        ),
    },
    {
        "id": "P3C6_PRODUCTION_STORE_NOT_PROVEN",
        "severity": "P1",
        "description": (
            "project-store rehydration is proven in the disposable "
            "mrw_p3_c6_worker_test schema; production store/cutover is "
            "not proven"
        ),
    },
    {
        "id": "P3C6_LOOP_LIVE_MODEL_NOT_PROVEN",
        "severity": "P1",
        "description": (
            "C6.1 model-step source is a scripted deterministic fixture; "
            "live model/provider integration is not frozen"
        ),
    },
    {
        "id": "P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED",
        "severity": "P1",
        "description": (
            "capability surface remains untracked; exact review tree pending"
        ),
    },
    {
        "id": "C6_2_LIVE_PROVIDER_AUTHORITY_NOT_FROZEN",
        "severity": "P1",
        "description": (
            "live provider/credential authority, authoritative readback and "
            "idempotency/non-start proof are not frozen; this fragment "
            "makes no live-provider claim"
        ),
    },
    {
        "id": "P3C6_PRODUCTION_REDACTION_PERSISTENCE_NOT_PROVEN",
        "severity": "P1",
        "description": (
            "pre-persistence redaction is verified on a disposable "
            "PostgreSQL worker schema; production AgentCore/agent_runtime "
            "emitters are still legacy"
        ),
    },
)

_SOURCE_BINDINGS = (
    BindingTarget(
        f"{_EVIDENCE_ROOT}/P1FunctorizationEligibility.v1.json", "p1_eligibility"
    ),
    BindingTarget(f"{_EVIDENCE_ROOT}/p1-fragments/C6.json", "p1_fragment"),
    BindingTarget(
        "main/backend/app/services/agent_core/core.py",
        "legacy_donor_c6_1",
    ),
    BindingTarget(
        "main/backend/app/services/agent_core/contracts.py",
        "legacy_donor_c6_1_c6_2",
    ),
    BindingTarget(
        "main/backend/app/services/agent_core/fake_provider.py",
        "legacy_donor_c6_2",
    ),
    BindingTarget(
        "main/backend/app/services/agent_core/native_provider.py",
        "legacy_donor_c6_2",
    ),
    BindingTarget(
        "main/backend/app/services/agent_core/json_provider.py",
        "legacy_donor_c6_2",
    ),
    BindingTarget(
        "main/backend/app/services/agent_core/provider_trace.py",
        "legacy_donor_c6_3",
    ),
    BindingTarget(
        "main/backend/app/services/agent_runtime/run_loop.py",
        "legacy_donor_c6_3",
    ),
)

_IMPLEMENTATION_BINDINGS = (
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/agent_core_c6_common.py",
        "family_shared_contracts",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/agent_core_c6_1.py",
        "c6_1_contracts",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/agent_core_c6_1_program.py",
        "c6_1_program",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/"
        "agent_core_c6_1_interpreters.py",
        "c6_1_interpreters",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/agent_core_c6_2.py",
        "c6_2_contracts",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/agent_core_c6_2_program.py",
        "c6_2_program",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/"
        "agent_core_c6_2_interpreters.py",
        "c6_2_interpreters",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/agent_core_c6_3.py",
        "c6_3_contracts",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/agent_core_c6_3_program.py",
        "c6_3_program",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/"
        "agent_core_c6_3_interpreters.py",
        "c6_3_interpreters",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/legacy_agent_core.py",
        "legacy_adapter",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/postgres/agent_core_c6_worker.py",
        "postgres_worker_store",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/postgres/agent_core_c6_handler.py",
        "store_rehydrated_handler",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/postgres/agent_core_c6_canary.py",
        "runtime_canary_service",
    ),
    BindingTarget(
        "main/backend/scripts/generate_successor_p3_c6_fragment.py",
        "evidence_generator",
    ),
)

_TEST_BINDINGS = (
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c6_1_episode.py",
        "c6_1_episode",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c6_2_provider.py",
        "c6_2_provider",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c6_3_redaction.py",
        "c6_3_redaction",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c6_legacy_shadow.py",
        "c6_legacy_shadow",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c6_evidence.py",
        "c6_evidence",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c6_worker_postgres.py",
        "c6_postgres_worker",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c6_runtime_canary_postgres.py",
        "c6_runtime_canary",
    ),
)


def _p1_cells() -> dict[str, dict[str, Any]]:
    artifact = json.loads(
        (
            REPOSITORY_ROOT / _EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json"
        ).read_text()
    )
    return {str(cell["cell"]): cell for cell in artifact["cells"]}


def _p1_cell_digest(cell_id: str) -> str:
    return content_digest(_p1_cells()[cell_id])


def _scope() -> ProjectScope:
    return ProjectScope(
        PROJECT_KEY,
        REGISTRY_REVISION,
        RESOLVED_SCHEMA,
        SCOPE_INCARNATION,
        "",
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
        "resolved_schema": RESOLVED_SCHEMA,
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


def _c6_1_request() -> c6_1.AgentTurnRequest:
    return c6_1.AgentTurnRequest(
        schema_version=c6_1.AGENT_CORE_C6_1_PAYLOAD_SCHEMA,
        operation_kind=c6_1.AGENT_CORE_C6_1_KIND,
        project_scope=_scope(),
        session_id="session-fragment",
        turn_id="turn-fragment",
        message_ref="project-value:message:fragment",
        max_iterations=4,
        max_tool_calls=3,
        approval_policy="frozen",
    )


def _c6_1_steps() -> tuple[AgentModelStep, ...]:
    tool_call = AgentToolCall(
        call_id="call-fragment-c2-1",
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
            content="shadow parity answer",
        ),
    )


def _c6_1_closure():
    payload = _c6_1_request()
    bundle = c6_1.build_agent_core_c6_1_bundle()
    catalog = c6_1.build_agent_core_c6_1_catalog(bundle)
    registry = c6_1.build_agent_core_c6_1_registry(bundle)
    program = c6_1p.build_agent_core_c6_1_program(
        payload=payload,
        catalog=catalog,
        program_id="p3-c6-fragment.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = c6_1p.compile_agent_core_c6_1_program(
        program, catalog, operation_contracts=registry
    )
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    return payload, program, plan, catalog, registry, contract_ref, bundle


def _c6_1_observations() -> tuple[dict[str, object], dict[str, object]]:
    payload, program, plan, catalog, _registry, contract_ref, _bundle = _c6_1_closure()
    legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_1_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor_binding = legacy_agent_core.build_successor_agent_core_c6_1_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
    )
    specimen = legacy_agent_core.C2_1PureToolSpecimen()
    redactor = c6_1.CanonicalJsonEventRedactor()
    common = {
        "program": program,
        "plan": plan,
        "contract_ref": contract_ref,
        "payload_ref": program.root.operation.payload_ref,
        "payload": payload,
        "project_scope": _scope(),
        "catalog": catalog,
        "deployment_catalog_digest": c6_deployment_catalog_digest(),
    }
    legacy_episode = legacy_agent_core.LegacyAgentCoreCapabilityInterpreter().interpret(
        **common,
        binding=legacy_binding,
        scripted_steps=_c6_1_steps(),
        specimen=specimen,
        redactor=redactor,
    )
    successor_outcome = c6_1i.AgentCoreEpisodeInterpreter().interpret(
        **common,
        binding=successor_binding,
        model_step_source=_ScriptedModelStepSource(_c6_1_steps()),
        tool_specimens=(specimen,),
        permission_policy=c6_1.StaticPermissionPolicy(),
        redactor=redactor,
    )
    assert successor_outcome.disposition == "SUCCEEDED"
    successor_episode = successor_outcome.value
    assert legacy_episode.tool_results and (
        legacy_episode.tool_results[0].status == "completed"
    )
    assert successor_episode.tool_results and (
        successor_episode.tool_results[0].status == "completed"
    )
    observation_digest = dict(successor_episode.tool_results[0].structured_content)[
        "observation_digest"
    ]
    tool_events = [
        event.event_type
        for event in legacy_episode.ordered_events
        if event.event_type
        in {"tool_call_requested", "tool_call_started", "tool_result"}
    ]
    statuses = [result.status for result in legacy_episode.tool_results]
    legacy_observation = {
        "interpreter_id": legacy_agent_core.LegacyAgentCoreCapabilityInterpreter.interpreter_id,
        "stop_reason": legacy_episode.stop_reason,
        "tool_event_types": tool_events,
        "tool_result_statuses": statuses,
        "observation_digest": observation_digest,
        "final_answer_digest": content_digest(
            {"final_answer": legacy_episode.final_answer}
        ),
        "trace_digest": content_digest(
            {
                "stop_reason": legacy_episode.stop_reason,
                "tool_event_types": tool_events,
                "tool_result_statuses": statuses,
                "final_answer": legacy_episode.final_answer,
            }
        ),
    }
    successor_observation = {
        "interpreter_id": c6_1i.AgentCoreEpisodeInterpreter.interpreter_id,
        "stop_reason": successor_episode.stop_reason,
        "episode_digest": successor_episode.episode_digest,
        "tool_call_count": successor_episode.tool_call_count,
        "tool_result_statuses": [
            result.status for result in successor_episode.tool_results
        ],
        "observation_digest": observation_digest,
        "provider_calls": 0,
        "raw_value_persisted": False,
    }
    return legacy_observation, successor_observation


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


def _c6_2_request() -> c6_2.AgentModelStepRequest:
    return c6_2.AgentModelStepRequest(
        schema_version=c6_2.AGENT_CORE_C6_2_PAYLOAD_SCHEMA,
        operation_kind=c6_2.AGENT_CORE_C6_2_KIND,
        project_scope=_scope(),
        session_id="session-fragment",
        turn_id="turn-fragment",
        message_ref="project-value:message:fragment",
        transcript_ref="project-value:transcript:fragment",
        tool_contract_refs=("source_library.resolve_execution_request.v1",),
        max_iterations=4,
        iteration=1,
        max_tool_calls=3,
        remaining_tool_calls=3,
        provider_profile_ref="fake_core_provider",
        credential_ref="credential:opaque:fragment",
    )


def _c6_2_closure():
    payload = _c6_2_request()
    bundle = c6_2.build_agent_core_c6_2_bundle()
    catalog = c6_2.build_agent_core_c6_2_catalog(bundle)
    registry = c6_2.build_agent_core_c6_2_registry(bundle)
    program = c6_2p.build_agent_core_c6_2_program(
        payload=payload,
        catalog=catalog,
        program_id="p3-c6-fragment.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = c6_2p.compile_agent_core_c6_2_program(
        program, catalog, operation_contracts=registry
    )
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    return payload, program, plan, catalog, registry, contract_ref, bundle


def _c6_2_observations() -> tuple[dict[str, object], dict[str, object]]:
    payload, program, plan, catalog, _registry, contract_ref, _bundle = _c6_2_closure()
    legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_2_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
    )
    common = {
        "program": program,
        "plan": plan,
        "contract_ref": contract_ref,
        "payload_ref": program.root.operation.payload_ref,
        "payload": payload,
        "project_scope": _scope(),
        "catalog": catalog,
        "deployment_catalog_digest": c6_deployment_catalog_digest(),
    }
    legacy_result = legacy_agent_core.NamedProviderModelStepInterpreter().interpret(
        **common,
        binding=legacy_binding,
        provider=FakeCoreProvider(
            [
                CoreModelStep.final(
                    "shadow provider answer", model_path="fake_core_provider"
                )
            ]
        ),
        attempt_id=ATTEMPT_ID,
    )
    legacy_observation = {
        "interpreter_id": legacy_agent_core.NamedProviderModelStepInterpreter.interpreter_id,
        "step_type": legacy_result.step.step_type,
        "scripted_provider_invocations": 1,
        "live_provider_calls": 0,
        "trace_digest": content_digest(
            {
                "step_type": legacy_result.step.step_type,
                "content": legacy_result.step.content,
                "model_path": "fake_core_provider",
            }
        ),
    }
    evidence = c6_2.build_c6_2_receipt_only_evidence(payload, attempt_id=ATTEMPT_ID)
    successor_observation = {
        "interpreter_id": c6_2i.NamedProviderModelStepInterpreter.interpreter_id,
        "outcome_code": evidence["outcome_code"],
        "readback_status": evidence["readback_status"],
        "provider_calls": 0,
        "receipt_digest": evidence["receipt_digest"],
        "result_digest": evidence["result_digest"],
    }
    return legacy_observation, successor_observation


def _c6_3_payload() -> tuple[c6_3.RedactionEvidencePayload, dict[str, object]]:
    classifications = {"provider.request": "REDACT", "provider.headers": "OMIT"}
    policy = c6_3.RedactionPolicyRef(
        policy_id="c6-3-fragment-policy",
        policy_version="1",
        policy_digest=c6_3.redaction_policy_digest(
            "c6-3-fragment-policy", "1", classifications
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
        project_scope=_scope(),
        source_observation_ref="project-value:source:fragment",
        source_observation_digest=c6_3.source_observation_digest(raw),
        source_kind="agent_core.tool_event",
        trace_id="trace-fragment",
        request_id="req-fragment",
        call_id="call-fragment",
        interpreter_profile_ref="successor.agent_core.c6_3.redaction.v1",
        policy=policy,
        field_classifications=freeze_c6_json_object(classifications),
        max_input_bytes=c6_3.REDACTION_RESOURCE_CEILING.max_input_bytes,
        max_event_batch=c6_3.REDACTION_RESOURCE_CEILING.max_event_batch,
    )
    return payload, raw


def _c6_3_closure():
    payload, raw = _c6_3_payload()
    bundle = c6_3.build_agent_core_c6_3_bundle()
    catalog = c6_3.build_agent_core_c6_3_catalog(bundle)
    registry = c6_3.build_agent_core_c6_3_registry(bundle)
    program = c6_3p.build_agent_core_c6_3_program(
        payload=payload,
        catalog=catalog,
        program_id="p3-c6-fragment.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = c6_3p.compile_agent_core_c6_3_program(
        program, catalog, operation_contracts=registry
    )
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    return payload, raw, program, plan, catalog, registry, contract_ref, bundle


def _c6_3_observations() -> tuple[dict[str, object], dict[str, object]]:
    payload, raw, program, plan, catalog, _registry, contract_ref, _bundle = (
        _c6_3_closure()
    )
    legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_3_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor_binding = legacy_agent_core.build_successor_agent_core_c6_3_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
    )
    assert legacy_agent_core.bindings_are_distinct(legacy_binding, successor_binding)
    common = {
        "program": program,
        "plan": plan,
        "contract_ref": contract_ref,
        "payload_ref": program.root.operation.payload_ref,
        "payload": payload,
        "project_scope": _scope(),
        "catalog": catalog,
        "deployment_catalog_digest": c6_deployment_catalog_digest(),
    }
    adapter = legacy_agent_core.RedactedObservationAdapter()
    legacy_receipt = adapter.interpret(
        **common,
        binding=legacy_binding,
        raw_observation=dict(raw),
    )
    successor_outcome = c6_3i.VersionedRedactionEvidenceInterpreter().interpret(
        **common,
        binding=successor_binding,
        raw_observation=dict(raw),
    )
    assert successor_outcome.disposition == "SUCCEEDED"
    successor_receipt = successor_outcome.value
    assert isinstance(successor_receipt, c6_3.RedactionReceipt)
    assert legacy_receipt.receipt_digest == successor_receipt.receipt_digest
    legacy_observation = {
        "interpreter_id": adapter.interpreter_id,
        "redaction_receipt_digest": legacy_receipt.receipt_digest,
        "policy_id": payload.policy.policy_id,
        "raw_sensitive_values_absent": True,
        "binding_digest": legacy_binding.binding_digest,
        "same_program_shadow_parity": True,
    }
    successor_observation = {
        "interpreter_id": c6_3i.VersionedRedactionEvidenceInterpreter.interpreter_id,
        "redaction_receipt_digest": successor_receipt.receipt_digest,
        "redacted_digest": successor_receipt.evidence.redacted_digest,
        "redacted_field_count": len(successor_receipt.evidence.redacted_field_paths),
        "omitted_field_count": len(successor_receipt.evidence.omitted_field_paths),
        "raw_value_persisted": False,
        "binding_digest": successor_binding.binding_digest,
        "same_program_shadow_parity": True,
    }
    return legacy_observation, successor_observation


def _build_body(_root: Path, bindings: BindingsByKind) -> dict[str, Any]:
    c6_1_legacy, c6_1_successor = _c6_1_observations()
    c6_2_legacy, c6_2_successor = _c6_2_observations()
    c6_3_legacy, c6_3_successor = _c6_3_observations()

    _p61, program61, plan61, _c61, _r61, _ref61, bundle61 = _c6_1_closure()
    _p62, program62, plan62, _c62, _r62, _ref62, bundle62 = _c6_2_closure()
    _p63, _raw63, program63, plan63, _c63, _r63, _ref63, bundle63 = _c6_3_closure()

    def program_digest(spec, reason: str) -> dict[str, object]:
        return {"value": spec.program_digest, "reason": reason}

    def plan_digest(plan, reason: str) -> dict[str, object]:
        return {"value": plan.plan_digest, "reason": reason}

    def operation_binding(bundle, role: str) -> list[dict[str, object]]:
        return [
            {
                "operation_kind": bundle.operation.ref.kind,
                "contract_digest": bundle.operation.ref.contract_digest,
                "role": role,
            }
        ]

    cells = [
        {
            "cell_id": "C6.1",
            "p1_cell_digest": _p1_cell_digest("C6.1"),
            "operation_bindings": operation_binding(
                bundle61, "episode_interpreter_atom"
            ),
            "owner_capability_id": c6_1.AGENT_CORE_C6_1_OWNER,
            "program_digest": program_digest(
                program61,
                "single-Atom Program for the bounded C6.1 episode request",
            ),
            "plan_digest": plan_digest(
                plan61,
                "compiled episode program through the shared compiler",
            ),
            "legacy_observation": c6_1_legacy,
            "successor_observation": {
                **c6_1_successor,
                "runtime_node_canary": {
                    "state": "COMMITTED",
                    "disposition": "SUCCEEDED",
                    "provider_calls": 0,
                    "sentinel_scan_passed": True,
                    "rollback_future_owner": "legacy",
                },
            },
            "rollback_observation": {
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "successor_journal_retained": True,
                        "dual_claim_authority": False,
                    }
                ),
                "claim_owner": "legacy",
                "successor_journal_retained": True,
                "dual_claim_authority": False,
            },
            "provider_calls": 0,
            "postgres_requirement": "not_required",
        },
        {
            "cell_id": "C6.2",
            "p1_cell_digest": _p1_cell_digest("C6.2"),
            "operation_bindings": operation_binding(bundle62, "provider_step_atom"),
            "owner_capability_id": c6_2.AGENT_CORE_C6_2_OWNER,
            "program_digest": program_digest(
                program62,
                "single-Atom Program for the exact C6.2 provider-step request",
            ),
            "plan_digest": plan_digest(
                plan62,
                "compiled provider-step program through the shared compiler",
            ),
            "legacy_observation": c6_2_legacy,
            "successor_observation": {
                **c6_2_successor,
                "runtime_node_canary": {
                    "state": "COMMITTED",
                    "disposition": "SUCCEEDED",
                    "provider_calls": 0,
                    "sentinel_scan_passed": True,
                    "rollback_future_owner": "legacy",
                },
            },
            "rollback_observation": {
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "attempt_receipt_retained": True,
                        "no_duplicate_provider_dispatch": True,
                    }
                ),
                "claim_owner": "legacy",
                "attempt_receipt_retained": True,
                "no_duplicate_provider_dispatch": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "required_and_verified_mrw_p3_c6_worker_test",
        },
        {
            "cell_id": "C6.3",
            "p1_cell_digest": _p1_cell_digest("C6.3"),
            "operation_bindings": operation_binding(bundle63, "redaction_atom"),
            "owner_capability_id": c6_3.AGENT_CORE_C6_3_OWNER,
            "program_digest": program_digest(
                program63,
                "single-Atom Program for the exact C6.3 redaction payload",
            ),
            "plan_digest": plan_digest(
                plan63,
                "compiled redaction program through the shared compiler",
            ),
            "legacy_observation": c6_3_legacy,
            "successor_observation": {
                **c6_3_successor,
                "runtime_node_canary": {
                    "state": "COMMITTED",
                    "disposition": "SUCCEEDED",
                    "provider_calls": 0,
                    "sentinel_scan_passed": True,
                    "rollback_future_owner": "legacy",
                },
            },
            "rollback_observation": {
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "raw_never_persisted": True,
                        "receipts_retained": True,
                    }
                ),
                "claim_owner": "legacy",
                "raw_never_persisted": True,
                "receipts_retained": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "required_and_verified_mrw_p3_c6_worker_test",
        },
    ]

    return {
        "schema": FRAGMENT_SCHEMA,
        "phase": FRAGMENT_PHASE,
        "family": FRAGMENT_FAMILY,
        "fragment_id": FRAGMENT_ID,
        "status": FRAGMENT_STATUS,
        "cells": cells,
        "source_bindings": bindings["source_bindings"],
        "implementation_bindings": bindings["implementation_bindings"],
        "test_bindings": bindings["test_bindings"],
        "authority": dict(AUTHORITY),
        "open_findings": [dict(finding) for finding in OPEN_FINDINGS],
    }


def _self_check(fragment: dict[str, object]) -> None:
    assert fragment["schema"] == FRAGMENT_SCHEMA
    assert fragment["phase"] == FRAGMENT_PHASE
    assert fragment["family"] == FRAGMENT_FAMILY
    assert fragment["status"] == FRAGMENT_STATUS
    body = {key: value for key, value in fragment.items() if key != "content_digest"}
    assert fragment["content_digest"] == content_digest(body)
    required_roots = {
        "schema",
        "phase",
        "family",
        "fragment_id",
        "status",
        "cells",
        "source_bindings",
        "implementation_bindings",
        "test_bindings",
        "authority",
        "open_findings",
        "content_digest",
    }
    assert set(fragment) == required_roots
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C6.1",
        "C6.2",
        "C6.3",
    ]
    for cell in fragment["cells"]:
        assert cell["provider_calls"] == 0
        assert set(cell["program_digest"]) == {"value", "reason"}
        assert set(cell["plan_digest"]) == {"value", "reason"}
    assert all(not value for value in fragment["authority"].values()), (
        "authority flags must all be false"
    )


CONFIG = FamilyFragmentConfig(
    family_id=FRAGMENT_FAMILY,
    phase=FRAGMENT_PHASE,
    schema=FRAGMENT_SCHEMA,
    fragment_id=FRAGMENT_ID,
    status=FRAGMENT_STATUS,
    fragment_output_rel=FRAGMENT_OUTPUT_REL,
    source_bindings=_SOURCE_BINDINGS,
    implementation_bindings=_IMPLEMENTATION_BINDINGS,
    test_bindings=_TEST_BINDINGS,
    authority=AUTHORITY,
    open_findings=OPEN_FINDINGS,
    body_builder=_build_body,
    self_check=_self_check,
)
