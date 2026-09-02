"""P3 C6.1 bounded AgentTurnEpisode/tool-loop contracts."""

from __future__ import annotations

import inspect
import json

import pytest

from app.successor_migration.legacy_agent_core import C2_1PureToolSpecimen
from app.successor_runtime.capabilities import agent_core_c6_1 as c6_1
from app.successor_runtime.capabilities.agent_core_c6_1_interpreters import (
    EpisodeBindingMismatch,
    authority_requirement_digest,
    require_exact_episode_binding,
    successor_interpreter_profile_digest,
)
from app.successor_runtime.capabilities.agent_core_c6_1_program import (
    build_agent_core_c6_1_program,
    compile_agent_core_c6_1_program,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStep,
    AgentModelStepFailure,
    AgentToolCall,
    AgentToolResult,
    ProjectScope,
    c6_deployment_catalog_digest,
    freeze_c6_json_object,
    thaw_json_value,
)
from app.successor_runtime.capabilities.source_library_c2_1 import (
    source_item_definition_content_digest,
)
from app.successor_runtime.language.program import decode_program_spec
from app.successor_runtime.runtime.assignments import InterpreterBinding

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
TOOL_NAME = "fixture.echo"
RAW_SECRET = "episode-raw-secret::password=fixture-password"


def _scope() -> ProjectScope:
    return ProjectScope(
        PROJECT_KEY,
        REGISTRY_REVISION,
        RESOLVED_SCHEMA,
        SCOPE_INCARNATION,
        "",
    )


def _request(**overrides) -> c6_1.AgentTurnRequest:
    values = {
        "schema_version": c6_1.AGENT_CORE_C6_1_PAYLOAD_SCHEMA,
        "operation_kind": c6_1.AGENT_CORE_C6_1_KIND,
        "project_scope": _scope(),
        "session_id": "session-c6-1",
        "turn_id": "turn-c6-1",
        "message_ref": "project-value:message:c6-1",
        "max_iterations": 4,
        "max_tool_calls": 3,
        "approval_policy": "enabled",
    }
    values.update(overrides)
    return c6_1.AgentTurnRequest(**values)


class ScriptedModelStepSource:
    """Deterministic model-step source for the bounded loop."""

    def __init__(self, steps) -> None:
        self.steps = list(steps)
        self.calls = []

    def next_step(self, *, request, tool_names, transcript, remaining_budget):
        self.calls.append(
            {
                "tool_names": tuple(tool_names),
                "remaining_budget": dict(remaining_budget),
            }
        )
        if self.steps:
            return self.steps.pop(0)
        return AgentModelStep(
            schema_version="mrw.successor.agent-core.c6.model-step.v1",
            step_type="final_answer",
            content="loop exhausted",
        )


class EchoSpecimen:
    tool_name = TOOL_NAME

    def validate(self, tool_call: AgentToolCall) -> AgentToolResult | None:
        if "value" not in dict(tool_call.arguments):
            return AgentToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary="echo requires value argument",
                error=freeze_c6_json_object(
                    {
                        "code": "tool_schema_validation_failed",
                        "message": "missing value",
                    }
                ),
            )
        return None

    def execute(
        self, tool_call: AgentToolCall, request: c6_1.AgentTurnRequest
    ) -> AgentToolResult:
        value = dict(tool_call.arguments)["value"]
        return AgentToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary="echo completed",
            structured_content=freeze_c6_json_object({"echo": value}),
        )


def _echo_call(
    *, call_id: str = "call-echo-1", value: str = RAW_SECRET
) -> AgentToolCall:
    return AgentToolCall(
        call_id=call_id,
        tool_name=TOOL_NAME,
        arguments=freeze_c6_json_object({"value": value}),
        reason="test",
    )


def _final(answer: str = "done") -> AgentModelStep:
    return AgentModelStep(
        schema_version="mrw.successor.agent-core.c6.model-step.v1",
        step_type="final_answer",
        content=answer,
    )


def _tools_step(*calls: AgentToolCall) -> AgentModelStep:
    return AgentModelStep(
        schema_version="mrw.successor.agent-core.c6.model-step.v1",
        step_type="tool_calls",
        tool_calls=calls,
    )


def _run(
    request,
    *,
    steps,
    policy=None,
    redactor=None,
    specimen=None,
):
    if specimen is None:
        specimen = EchoSpecimen()
    source = ScriptedModelStepSource(steps)
    outcome = c6_1.interpret_agent_turn(
        request,
        model_step_source=source,
        tool_specimens=(specimen,),
        permission_policy=policy or c6_1.StaticPermissionPolicy(),
        redactor=redactor or c6_1.CanonicalJsonEventRedactor(),
    )
    return outcome, source


def test_direct_final_answer_has_no_tool_calls() -> None:
    outcome, source = _run(_request(), steps=[_final("hello")])
    assert isinstance(outcome, c6_1.AgentTurnEpisode)
    assert outcome.stop_reason == "final_answer"
    assert outcome.final_answer == "hello"
    assert outcome.tool_call_count == 0
    assert [event.event_type for event in outcome.ordered_events] == [
        "session_started",
        "user_message",
        "final_answer",
    ]
    assert source.calls[0]["remaining_budget"] == {
        "max_iterations": 4,
        "iteration": 1,
        "max_tool_calls": 3,
        "remaining_tool_calls": 3,
    }


def test_ordered_tool_loop_and_no_raw_persistence() -> None:
    outcome, _source = _run(
        _request(),
        steps=[_tools_step(_echo_call()), _final("answer after tool")],
    )
    assert isinstance(outcome, c6_1.AgentTurnEpisode)
    assert outcome.stop_reason == "final_answer"
    assert outcome.tool_call_count == 1
    tool_events = [
        event.event_type
        for event in outcome.ordered_events
        if event.event_type
        in {"tool_call_requested", "tool_call_started", "tool_result"}
    ]
    assert tool_events == ["tool_call_requested", "tool_call_started", "tool_result"]
    encoded = json.dumps(
        [event.to_plain() for event in outcome.ordered_events], sort_keys=True
    )
    assert RAW_SECRET not in encoded
    assert "raw_value_persisted" in encoded
    assert outcome.tool_results[0].status == "completed"


def test_validation_failure_never_starts_tool() -> None:
    invalid = _echo_call(call_id="call-invalid")
    invalid = AgentToolCall(
        call_id=invalid.call_id,
        tool_name=invalid.tool_name,
        arguments=freeze_c6_json_object({}),
    )
    outcome, _source = _run(
        _request(),
        steps=[_tools_step(invalid), _final("after validation")],
    )
    assert isinstance(outcome, c6_1.AgentTurnEpisode)
    assert outcome.tool_results[0].status == "failed"
    assert outcome.tool_results[0].error is not None
    assert "tool_call_started" not in [
        event.event_type for event in outcome.ordered_events
    ]


def test_max_tool_calls_and_max_iterations_are_bounded() -> None:
    capped, _source = _run(
        _request(max_tool_calls=1),
        steps=[
            _tools_step(_echo_call(call_id="call-1"), _echo_call(call_id="call-2")),
            _final(),
        ],
    )
    assert isinstance(capped, c6_1.AgentTurnEpisode)
    assert capped.stop_reason == "max_tool_calls_exceeded"
    assert capped.tool_call_count == 1

    iter_capped, _source = _run(
        _request(max_iterations=1, max_tool_calls=3),
        steps=[
            _tools_step(_echo_call(call_id="call-iter")),
            _final(),
        ],
    )
    assert isinstance(iter_capped, c6_1.AgentTurnEpisode)
    assert iter_capped.stop_reason == "max_iterations_exceeded"


def test_permission_pause_and_resume_executes_same_call() -> None:
    ask_policy = c6_1.StaticPermissionPolicy(ask_tools=(TOOL_NAME,))
    paused, _source = _run(
        _request(),
        steps=[_tools_step(_echo_call(call_id="call-approve")), _final()],
        policy=ask_policy,
    )
    assert isinstance(paused, c6_1.AgentTurnEpisode)
    assert paused.stop_reason == "permission_requested"
    assert paused.tool_call_count == 0

    resumed, _source = _run(
        _request(
            resume_call_id="call-approve",
            resume_tool_call=_echo_call(call_id="call-approve"),
            approved_call_ids=("call-approve",),
        ),
        steps=[_final("resumed answer")],
        policy=ask_policy,
    )
    assert isinstance(resumed, c6_1.AgentTurnEpisode)
    assert resumed.stop_reason == "final_answer"
    assert resumed.tool_call_count == 1
    event_types = [event.event_type for event in resumed.ordered_events]
    assert "run_resumed" in event_types
    assert "tool_result" in event_types


def test_denied_tool_is_blocked_without_prompt() -> None:
    deny_policy = c6_1.StaticPermissionPolicy(deny_tools=(TOOL_NAME,))
    outcome, _source = _run(
        _request(),
        steps=[_tools_step(_echo_call()), _final()],
        policy=deny_policy,
    )
    assert isinstance(outcome, c6_1.AgentTurnEpisode)
    assert outcome.tool_results[0].status == "failed"
    assert outcome.tool_results[0].error is not None
    assert dict(outcome.tool_results[0].error or {})["code"] == "tool_permission_denied"
    assert "permission_requested" not in [
        event.event_type for event in outcome.ordered_events
    ]


def test_cooperative_cancellation_stops_at_boundary() -> None:
    outcome, _source = _run(
        _request(cancel_requested=True),
        steps=[_tools_step(_echo_call()), _final()],
    )
    assert isinstance(outcome, c6_1.AgentTurnEpisode)
    assert outcome.stop_reason == "canceled"
    assert outcome.tool_call_count == 0
    assert any(event.event_type == "error" for event in outcome.ordered_events)


def test_unsupported_model_step_failure() -> None:
    outcome, _source = _run(
        _request(),
        steps=[
            AgentModelStepFailure(
                code="unsupported_model_step",
                message="unknown step type",
            )
        ],
    )
    assert isinstance(outcome, c6_1.AgentTurnEpisode)
    assert outcome.stop_reason == "error"


def test_program_plan_compile_and_binding_mismatch() -> None:
    payload = _request()
    bundle = c6_1.build_agent_core_c6_1_bundle()
    catalog = c6_1.build_agent_core_c6_1_catalog(bundle)
    registry = c6_1.build_agent_core_c6_1_registry(bundle)
    program = build_agent_core_c6_1_program(
        payload=payload,
        catalog=catalog,
        program_id="p3.c6-1.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_agent_core_c6_1_program(
        program, catalog, operation_contracts=registry
    )
    decoded = decode_program_spec(
        {
            "program": json.loads(program.canonical_json()),
            "program_digest": program.digest(),
        }
    )
    assert decoded.program_digest == program.program_digest
    contract_ref = registry.resolve_required(program.root.operation.contract_ref).ref
    binding = InterpreterBinding.from_content(
        operation_contract_digest=contract_ref.contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest(),
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        runtime_protocol_version="mrw.runtime.protocol.v1",
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=1,
        authority_requirement_digest=authority_requirement_digest(),
    )
    require_exact_episode_binding(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_scope(),
        catalog=catalog,
        deployment_catalog_digest=c6_deployment_catalog_digest(),
        binding=binding,
    )
    with pytest.raises(EpisodeBindingMismatch):
        require_exact_episode_binding(
            program=build_agent_core_c6_1_program(
                payload=_request(max_iterations=2),
                catalog=catalog,
                program_id="p3.c6-1.program",
                project_key=PROJECT_KEY,
                project_registry_revision=REGISTRY_REVISION,
                project_scope_digest=SCOPE_DIGEST,
            ),
            plan=plan,
            contract_ref=contract_ref,
            payload_ref=program.root.operation.payload_ref,
            payload=payload,
            project_scope=_scope(),
            catalog=catalog,
            deployment_catalog_digest=c6_deployment_catalog_digest(),
            binding=binding,
        )


def test_c6_1_has_no_provider_settings_or_registry_dependency() -> None:
    source = inspect.getsource(c6_1)
    assert "app.settings" not in source
    assert "CoreToolRegistry" not in source
    assert "provider_calls" not in source


def _c2_1_arguments(*, enabled: bool = True) -> dict[str, object]:
    item = {
        "item_key": "handler.cluster.news",
        "channel_key": "handler.cluster",
        "enabled": enabled,
        "params": {"keywords": ["robotics"], "limit": 3},
        "extra": {"stable_handler_cluster": True},
        "revision": 1,
        "incarnation": "item-inc-1",
    }
    item["content_digest"] = source_item_definition_content_digest(item)
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
                "extra": {"source_tier": "primary"},
            }
        ],
        "item": item,
        "params": {
            "query_terms": ["robotics"],
            "site_entries": ["https://example.com/search?q={{q}}"],
        },
    }


def test_nested_arguments_thaw_c2_1_specimen_success_and_rejection_counterexample() -> (
    None
):
    specimen = C2_1PureToolSpecimen()
    request = _request()
    nested_call = AgentToolCall(
        call_id="call-nested",
        tool_name=specimen.tool_name,
        arguments=freeze_c6_json_object(_c2_1_arguments()),
    )
    success = specimen.execute(nested_call, request)
    assert success.status == "completed"
    assert dict(success.structured_content)["kind"] == "resolved"
    observation_digest = dict(success.structured_content)["observation_digest"]
    assert len(observation_digest) == 64

    disabled = AgentToolCall(
        call_id="call-disabled",
        tool_name=specimen.tool_name,
        arguments=freeze_c6_json_object(_c2_1_arguments(enabled=False)),
    )
    rejected = specimen.execute(disabled, request)
    assert rejected.status == "failed"
    assert rejected.error is not None
    assert dict(rejected.error)["code"] == "C2_1_RESOLUTION_REJECTED"
    assert dict(rejected.error)["rejection_code"] == "DISABLED_ITEM"


def test_thaw_law_preserves_empty_lists_and_ambiguous_arrays() -> None:
    original = {"a": [], "b": {}, "c": [["k", "v"]], "d": []}
    assert thaw_json_value(freeze_c6_json_object(original)) == original
    assert thaw_json_value(freeze_c6_json_object({})) == {}
    assert thaw_json_value(dict(freeze_c6_json_object({"a": []}))["a"]) == []


def test_c2_1_specimen_empty_list_arguments_regression() -> None:
    specimen = C2_1PureToolSpecimen()
    arguments = _c2_1_arguments()
    arguments["params"] = {
        "query_terms": ["robotics"],
        "urls": [],
        "site_entries": [],
    }
    tool_call = AgentToolCall(
        call_id="call-empty-lists",
        tool_name=specimen.tool_name,
        arguments=freeze_c6_json_object(arguments),
    )
    result = specimen.execute(tool_call, _request())
    assert result.status == "completed"
    assert dict(result.structured_content)["kind"] == "resolved"
