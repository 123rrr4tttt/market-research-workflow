"""P3 C6 same-Program legacy/successor shadow parity over the C2.1 specimen."""

from __future__ import annotations

import json

import pytest

from app.services.agent_core.contracts import CoreModelStep
from app.services.agent_core.fake_provider import FakeCoreProvider
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
from app.successor_runtime.capabilities.agent_core_c6_1_interpreters import (
    AgentCoreEpisodeInterpreter as SuccessorEpisodeInterpreter,
)
from app.successor_runtime.capabilities.agent_core_c6_1_program import (
    build_agent_core_c6_1_program,
    compile_agent_core_c6_1_program,
)
from app.successor_runtime.capabilities.agent_core_c6_2_interpreters import (
    NamedProviderModelStepInterpreter as SuccessorProviderInterpreter,
)
from app.successor_runtime.capabilities.agent_core_c6_2_program import (
    build_agent_core_c6_2_program,
    compile_agent_core_c6_2_program,
)
from app.successor_runtime.capabilities.agent_core_c6_3_interpreters import (
    RedactionBindingMismatch,
    VersionedRedactionEvidenceInterpreter,
)
from app.successor_runtime.capabilities.agent_core_c6_3_program import (
    build_agent_core_c6_3_program,
    compile_agent_core_c6_3_program,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStep,
    AgentToolCall,
    ProjectScope,
    c6_deployment_catalog_digest,
    freeze_c6_json_object,
    rollback_authority_ceiling,
)
from app.successor_runtime.capabilities.source_library_c2_1 import (
    source_item_definition_content_digest,
)

pytestmark = pytest.mark.unit

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
RAW_SENTINEL = "mrw-c6-shadow-sentinel::api_key=fixture-key"


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


def _c2_1_disabled_arguments() -> dict[str, object]:
    arguments = _c2_1_arguments()
    item = dict(arguments["item"])
    item["enabled"] = False
    item["content_digest"] = source_item_definition_content_digest(item)
    arguments["item"] = item
    return arguments


def _c6_1_request() -> c6_1.AgentTurnRequest:
    return c6_1.AgentTurnRequest(
        schema_version=c6_1.AGENT_CORE_C6_1_PAYLOAD_SCHEMA,
        operation_kind=c6_1.AGENT_CORE_C6_1_KIND,
        project_scope=_scope(),
        session_id="session-shadow",
        turn_id="turn-shadow",
        message_ref="project-value:message:shadow",
        max_iterations=4,
        max_tool_calls=3,
        approval_policy="frozen",
    )


def _c6_1_program_and_plan(payload):
    bundle = c6_1.build_agent_core_c6_1_bundle()
    catalog = c6_1.build_agent_core_c6_1_catalog(bundle)
    registry = c6_1.build_agent_core_c6_1_registry(bundle)
    program = build_agent_core_c6_1_program(
        payload=payload,
        catalog=catalog,
        program_id="p3.c6-1.shadow",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_agent_core_c6_1_program(
        program, catalog, operation_contracts=registry
    )
    return program, plan, catalog, registry


def _scripted_steps():
    tool_call = AgentToolCall(
        call_id="call-shadow-c2-1",
        tool_name=legacy_agent_core.C2_1_PURE_TOOL_NAME,
        arguments=freeze_c6_json_object(_c2_1_arguments()),
    )
    return [
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
    ]


def test_c6_1_same_program_legacy_and_successor_shadow_parity() -> None:
    payload = _c6_1_request()
    program, plan, catalog, registry = _c6_1_program_and_plan(payload)
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_1_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor_binding = legacy_agent_core.build_successor_agent_core_c6_1_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
    )
    assert legacy_agent_core.bindings_are_distinct(legacy_binding, successor_binding)

    specimen = legacy_agent_core.C2_1PureToolSpecimen()
    redactor = c6_1.CanonicalJsonEventRedactor()
    successor_outcome = SuccessorEpisodeInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=successor_binding,
        model_step_source=_ScriptedSource(_scripted_steps()),
        tool_specimens=(specimen,),
        permission_policy=c6_1.StaticPermissionPolicy(),
        redactor=redactor,
    )
    assert successor_outcome.disposition == "SUCCEEDED"
    successor = successor_outcome.value

    legacy = legacy_agent_core.LegacyAgentCoreCapabilityInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=legacy_binding,
        scripted_steps=_scripted_steps(),
        specimen=specimen,
        redactor=redactor,
    )

    assert successor.stop_reason == legacy.stop_reason == "final_answer"
    assert successor.final_answer == legacy.final_answer == "shadow parity answer"
    assert [result.status for result in successor.tool_results] == ["completed"]
    assert [result.status for result in successor.tool_results] == [
        result.status for result in legacy.tool_results
    ]
    successor_observation = dict(successor.tool_results[0].structured_content)[
        "observation_digest"
    ]
    legacy_observation = dict(legacy.tool_results[0].structured_content)[
        "observation_digest"
    ]
    assert successor_observation == legacy_observation
    assert len(successor_observation) == 64
    successor_tool_events = [
        event.event_type
        for event in successor.ordered_events
        if event.event_type
        in {"tool_call_requested", "tool_call_started", "tool_result"}
    ]
    legacy_tool_events = [
        event.event_type
        for event in legacy.ordered_events
        if event.event_type
        in {"tool_call_requested", "tool_call_started", "tool_result"}
    ]
    assert successor_tool_events == legacy_tool_events
    for episode in (successor, legacy):
        encoded = json.dumps(
            [event.to_plain() for event in episode.ordered_events], sort_keys=True
        )
        assert RAW_SENTINEL not in encoded
        assert "fixture-key" not in encoded


def test_shared_failure_counterexample_is_not_parity_success() -> None:
    """A C2.1 rejection must surface as failed on both interpreters."""

    payload = _c6_1_request()
    program, plan, catalog, registry = _c6_1_program_and_plan(payload)
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
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
    tool_call = AgentToolCall(
        call_id="call-disabled-shadow",
        tool_name=legacy_agent_core.C2_1_PURE_TOOL_NAME,
        arguments=freeze_c6_json_object(_c2_1_disabled_arguments()),
    )
    steps = [
        AgentModelStep(
            schema_version="mrw.successor.agent-core.c6.model-step.v1",
            step_type="tool_calls",
            tool_calls=(tool_call,),
        ),
        AgentModelStep(
            schema_version="mrw.successor.agent-core.c6.model-step.v1",
            step_type="final_answer",
            content="answer after rejection",
        ),
    ]
    successor_outcome = SuccessorEpisodeInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=successor_binding,
        model_step_source=_ScriptedSource(list(steps)),
        tool_specimens=(specimen,),
        permission_policy=c6_1.StaticPermissionPolicy(),
        redactor=redactor,
    )
    assert successor_outcome.disposition == "SUCCEEDED"
    legacy_episode = legacy_agent_core.LegacyAgentCoreCapabilityInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=legacy_binding,
        scripted_steps=list(steps),
        specimen=specimen,
        redactor=redactor,
    )
    for episode in (successor_outcome.value, legacy_episode):
        assert [result.status for result in episode.tool_results] == ["failed"]
        assert dict(episode.tool_results[0].error or {})["code"] == (
            "C2_1_RESOLUTION_REJECTED"
        )
        assert "completed" not in [result.status for result in episode.tool_results]


class _ScriptedSource:
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
        session_id="session-shadow",
        turn_id="turn-shadow",
        message_ref="project-value:message:shadow",
        transcript_ref="project-value:transcript:shadow",
        tool_contract_refs=("source_library.resolve_execution_request.v1",),
        max_iterations=4,
        iteration=1,
        max_tool_calls=3,
        remaining_tool_calls=3,
        provider_profile_ref="fake_core_provider",
        credential_ref="credential:opaque:shadow",
    )


def test_c6_2_same_program_legacy_and_successor_provider_parity() -> None:
    payload = _c6_2_request()
    bundle = c6_2.build_agent_core_c6_2_bundle()
    catalog = c6_2.build_agent_core_c6_2_catalog(bundle)
    registry = c6_2.build_agent_core_c6_2_registry(bundle)
    program = build_agent_core_c6_2_program(
        payload=payload,
        catalog=catalog,
        program_id="p3.c6-2.shadow",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_agent_core_c6_2_program(
        program, catalog, operation_contracts=registry
    )
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_2_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor_binding = legacy_agent_core.build_successor_agent_core_c6_2_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
    )
    attempt_id = "attempt:c6-2:shadow"

    def legacy_provider():
        return FakeCoreProvider(
            [
                CoreModelStep.final(
                    "shadow provider answer", model_path="fake_core_provider"
                )
            ]
        )

    legacy_result = legacy_agent_core.NamedProviderModelStepInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=legacy_binding,
        provider=legacy_provider(),
        attempt_id=attempt_id,
    )
    successor_result = SuccessorProviderInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=successor_binding,
        port=legacy_agent_core.LegacyProviderPortAdapter(legacy_provider()),
        attempt_id=attempt_id,
    )
    assert successor_result.disposition == "SUCCEEDED"
    assert legacy_result.result_digest == successor_result.value.result_digest
    assert legacy_result.step.to_plain() == successor_result.value.step.to_plain()


def _c6_3_payload_and_raw(
    *, trace_id: str = "trace-shadow"
) -> tuple[c6_3.RedactionEvidencePayload, dict[str, object]]:
    classifications = {
        "provider.request": "REDACT",
        "provider.headers": "OMIT",
    }
    policy = c6_3.RedactionPolicyRef(
        policy_id="c6-3-shadow-policy",
        policy_version="1",
        policy_digest=c6_3.redaction_policy_digest(
            "c6-3-shadow-policy", "1", classifications
        ),
    )
    raw_event: dict[str, object] = {
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
        source_observation_ref="project-value:event:shadow",
        source_observation_digest=c6_3.source_observation_digest(raw_event),
        source_kind="agent_core.tool_event",
        trace_id=trace_id,
        request_id="req-shadow",
        call_id="call-shadow",
        interpreter_profile_ref="successor.agent_core.c6_3.redaction.v1",
        policy=policy,
        field_classifications=freeze_c6_json_object(classifications),
        max_input_bytes=c6_3.REDACTION_RESOURCE_CEILING.max_input_bytes,
        max_event_batch=c6_3.REDACTION_RESOURCE_CEILING.max_event_batch,
    )
    return payload, raw_event


def _c6_3_program_and_plan(payload):
    bundle = c6_3.build_agent_core_c6_3_bundle()
    catalog = c6_3.build_agent_core_c6_3_catalog(bundle)
    registry = c6_3.build_agent_core_c6_3_registry(bundle)
    program = build_agent_core_c6_3_program(
        payload=payload,
        catalog=catalog,
        program_id="p3.c6-3.shadow",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_agent_core_c6_3_program(
        program, catalog, operation_contracts=registry
    )
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    return program, plan, catalog, registry, contract_ref


def test_c6_3_same_program_legacy_and_successor_redaction_parity() -> None:
    payload, raw_event = _c6_3_payload_and_raw()
    program, plan, catalog, _registry, contract_ref = _c6_3_program_and_plan(payload)
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
        raw_observation=dict(raw_event),
    )
    successor_outcome = VersionedRedactionEvidenceInterpreter().interpret(
        **common,
        binding=successor_binding,
        raw_observation=dict(raw_event),
    )
    assert successor_outcome.disposition == "SUCCEEDED"
    assert isinstance(successor_outcome.value, c6_3.RedactionReceipt)
    assert legacy_receipt.receipt_digest == successor_outcome.value.receipt_digest
    assert adapter.legacy_trace is not None
    assert adapter.legacy_trace["raw_sensitive_values_absent"] is True
    shadow = adapter.shadow_evidence(
        receipts=[legacy_receipt, successor_outcome.value],
        sensitive_values=[RAW_SENTINEL, "fixture-token"],
    )
    assert shadow["raw_sensitive_values_absent"] is True
    assert shadow["receipt_count"] == 2


def test_c6_3_swapped_bindings_and_mutation_reject() -> None:
    payload, raw_event = _c6_3_payload_and_raw()
    program, plan, catalog, _registry, contract_ref = _c6_3_program_and_plan(payload)
    legacy_binding = legacy_agent_core.build_legacy_agent_core_c6_3_binding(
        contract_digest=contract_ref.contract_digest,
        project_scope_digest=SCOPE_DIGEST,
    )
    successor_binding = legacy_agent_core.build_successor_agent_core_c6_3_binding(
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
    adapter = legacy_agent_core.RedactedObservationAdapter()
    with pytest.raises(RedactionBindingMismatch, match="interpreter profile"):
        adapter.interpret(
            **common,
            binding=successor_binding,
            raw_observation=dict(raw_event),
        )
    swapped_outcome = VersionedRedactionEvidenceInterpreter().interpret(
        **common,
        binding=legacy_binding,
        raw_observation=dict(raw_event),
    )
    assert swapped_outcome.disposition == "FAILED"
    assert swapped_outcome.code == "ASSIGNMENT_BINDING_MISMATCH"

    tampered_payload, _ = _c6_3_payload_and_raw(trace_id="trace-mutated")
    tampered_program, _plan, _catalog, _registry, _ref = _c6_3_program_and_plan(
        tampered_payload
    )
    with pytest.raises(RedactionBindingMismatch):
        adapter.interpret(
            **{
                **common,
                "program": tampered_program,
            },
            binding=legacy_binding,
            raw_observation=dict(raw_event),
        )


def test_family_rollback_ceiling_is_honest_and_local_only() -> None:
    ceiling = rollback_authority_ceiling()
    legacy_receipt = legacy_agent_core.legacy_rollback_receipt()
    assert ceiling["status"] == "LOCAL_FIXTURE_ONLY_PROMOTED_NOT_LIVE"
    assert ceiling["provider_calls"] == 0
    assert ceiling["raw_value_persisted"] is False
    assert ceiling["successor_journal_retained_on_rollback"] is True
    assert ceiling["dual_claim_authority"] is False
    assert legacy_receipt["successor_journal_retained_on_rollback"] is True
    for key in (
        "business_authority_migrated",
        "successor_claim_enabled",
        "live_provider",
        "external_delivery",
        "production_canonical_write",
        "cutover",
        "authority_transfer",
    ):
        assert ceiling["authority"][key] is False
