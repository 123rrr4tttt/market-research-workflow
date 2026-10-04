"""Frozen typed contracts for the C6.1 bounded AgentTurnEpisode atom.

The episode interpreter owns only the ordered model/tool-loop algebra: bounded
iterations and tool calls, validation before execution, permission
pause/resume, cooperative cancellation and stop reasons.  It never imports a
provider, registry, process configuration or legacy service, never performs durable
effects, and never retains raw argument/result payloads.  Tool specimens and
model-step sources are injected; the only specimen used in this family line is
the C2.1 pure tool specimen supplied by the sibling migration adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeAlias, runtime_checkable

from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStepFailure,
    AgentModelStepOutcome,
    AgentToolCall,
    AgentToolResult,
    ProjectScope,
    SchemaSpec,
    build_payload_codec,
    freeze_c6_json_object,
    thaw_json_value,
)
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
    sha256_hex,
)
from app.successor_runtime.capabilities.contracts import (
    OperationContract,
    OperationContractCatalogSnapshot,
)
from app.successor_runtime.capabilities.profiles import (
    AuthorityProfile,
    ContractProfileRef,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)
from app.successor_runtime.language.algebra import (
    FrozenJsonObject,
)
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "AGENT_CORE_C6_1_CATALOG_ID",
    "AGENT_CORE_C6_1_CATALOG_VERSION",
    "AGENT_CORE_C6_1_KIND",
    "AGENT_CORE_C6_1_OPERATION_ID",
    "AGENT_CORE_C6_1_OWNER",
    "AGENT_CORE_C6_1_PAYLOAD_CODEC_ID",
    "AGENT_CORE_C6_1_PAYLOAD_SCHEMA",
    "AGENT_CORE_C6_1_RESULT_TYPE",
    "AGENT_CORE_C6_1_SEMANTIC_IDENTITY",
    "AGENT_TURN_EPISODE_SCHEMA",
    "AGENT_TURN_EVENT_SCHEMA",
    "AGENT_TURN_REQUEST_SCHEMA",
    "AgentCoreC6_1CapabilityBundle",
    "AgentTurnEpisode",
    "AgentTurnEvent",
    "AgentTurnFailure",
    "AgentTurnRequest",
    "CanonicalJsonEventRedactor",
    "EventRedactor",
    "ModelStepSource",
    "PermissionPolicy",
    "StaticPermissionPolicy",
    "ToolSpecimen",
    "build_agent_core_c6_1_bundle",
    "build_agent_core_c6_1_catalog",
    "build_agent_core_c6_1_registry",
    "interpret_agent_turn",
]


AGENT_CORE_C6_1_KIND = "agent_core.episode_interpret.v1"
AGENT_CORE_C6_1_OWNER = "agent_core.c6_1.v1"
AGENT_CORE_C6_1_OPERATION_ID = "agent_core.episode_interpret"
AGENT_CORE_C6_1_PAYLOAD_SCHEMA = "mrw.successor.agent-core.c6-1.payload.v1"
AGENT_CORE_C6_1_PAYLOAD_CODEC_ID = "mrw.successor.agent-core.c6-1.payload.codec.v1"
AGENT_CORE_C6_1_CATALOG_ID = "mrw.successor.agent-core.c6-1.operations"
AGENT_CORE_C6_1_CATALOG_VERSION = "1.0.0"
AGENT_CORE_C6_1_OBSERVATION_PROFILE = "mrw.successor.agent-core.c6-1.observation.v1"
AGENT_CORE_C6_1_SEMANTIC_IDENTITY = "agent-core.episode"
AGENT_TURN_REQUEST_SCHEMA_REF = "mrw.successor.agent-core.c6-1.request.v1"
AGENT_TURN_EVENT_SCHEMA_REF = "mrw.successor.agent-core.c6-1.event.v1"
AGENT_TURN_EPISODE_SCHEMA_REF = "mrw.successor.agent-core.c6-1.episode.v1"

AGENT_TURN_REQUEST_TYPE = ObjectType("AgentTurnRequest.v1")
AGENT_TURN_EVENT_TYPE = ObjectType("AgentTurnEvent.v1")
AGENT_TURN_EPISODE_TYPE = ObjectType("AgentTurnEpisode.v1")
AGENT_CORE_C6_1_PAYLOAD_TYPE = AGENT_TURN_REQUEST_TYPE
AGENT_CORE_C6_1_RESULT_TYPE = AGENT_TURN_EPISODE_TYPE

AGENT_TURN_REQUEST_SCHEMA = SchemaSpec(
    schema_ref=AGENT_TURN_REQUEST_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("operation_kind", True),
        ("project_scope", True),
        ("session_id", True),
        ("turn_id", True),
        ("message_ref", True),
        ("max_iterations", True),
        ("max_tool_calls", True),
        ("approval_policy", True),
        ("approved_call_ids", True),
        ("resume_call_id", False),
        ("resume_tool_call", False),
        ("cancel_requested", True),
        ("payload_digest", True),
    ),
)
AGENT_TURN_EVENT_SCHEMA = SchemaSpec(
    schema_ref=AGENT_TURN_EVENT_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("event_type", True),
        ("call_id", False),
        ("actor", True),
        ("payload", True),
        ("event_digest", True),
    ),
)
AGENT_TURN_EPISODE_SCHEMA = SchemaSpec(
    schema_ref=AGENT_TURN_EPISODE_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("episode_id", True),
        ("request_digest", True),
        ("ordered_events", True),
        ("tool_results", True),
        ("final_answer", True),
        ("stop_reason", True),
        ("tool_call_count", True),
        ("iteration", True),
        ("episode_digest", True),
    ),
)

AGENT_TURN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "session_started",
        "user_message",
        "assistant_delta",
        "assistant_message",
        "tool_call_requested",
        "tool_call_started",
        "tool_result",
        "permission_requested",
        "approval_resolved",
        "run_resumed",
        "final_answer",
        "error",
    }
)
AGENT_TURN_STOP_REASONS: frozenset[str] = frozenset(
    {
        "final_answer",
        "no_more_tools",
        "permission_requested",
        "approval_denied",
        "max_tool_calls_exceeded",
        "max_iterations_exceeded",
        "canceled",
        "tool_needs_approval",
        "tool_deferred",
        "error",
    }
)
AGENT_TURN_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "tool_schema_validation_failed",
        "tool_permission_denied",
        "tool_not_registered",
        "unsupported_model_step",
        "session_canceled",
        "loop_configuration_invalid",
    }
)


@dataclass(frozen=True, slots=True)
class AgentTurnRequest:
    """Bounded turn request; message/transcript stay as opaque refs."""

    schema_version: Literal["mrw.successor.agent-core.c6-1.payload.v1"]
    operation_kind: Literal["agent_core.episode_interpret.v1"]
    project_scope: ProjectScope
    session_id: str
    turn_id: str
    message_ref: str
    max_iterations: int
    max_tool_calls: int
    approval_policy: Literal["frozen", "enabled"]
    approved_call_ids: tuple[str, ...] = ()
    resume_call_id: str | None = None
    resume_tool_call: AgentToolCall | None = None
    cancel_requested: bool = False
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_CORE_C6_1_PAYLOAD_SCHEMA:
            raise ValueError(f"unsupported payload schema {self.schema_version!r}")
        if self.operation_kind != AGENT_CORE_C6_1_KIND:
            raise ValueError(f"unsupported operation kind {self.operation_kind!r}")
        for name in ("session_id", "turn_id", "message_ref"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"AgentTurnRequest.{name} is required")
        for name in ("max_iterations", "max_tool_calls"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"AgentTurnRequest.{name} must be a positive int")
        if self.approval_policy not in {"frozen", "enabled"}:
            raise ValueError(f"unsupported approval_policy {self.approval_policy!r}")
        object.__setattr__(self, "approved_call_ids", tuple(self.approved_call_ids))
        if not all(
            isinstance(call_id, str) and call_id.strip()
            for call_id in self.approved_call_ids
        ):
            raise ValueError("approved_call_ids must be non-empty strings")
        if self.resume_call_id is not None and (
            not isinstance(self.resume_call_id, str) or not self.resume_call_id.strip()
        ):
            raise ValueError("resume_call_id must be a non-empty string or None")
        if self.resume_tool_call is not None and not isinstance(
            self.resume_tool_call, AgentToolCall
        ):
            raise TypeError("resume_tool_call must be AgentToolCall or None")
        if self.resume_tool_call is not None and (
            self.resume_call_id != self.resume_tool_call.call_id
        ):
            raise ValueError("resume_call_id must match resume_tool_call.call_id")
        if not isinstance(self.cancel_requested, bool):
            raise TypeError("AgentTurnRequest.cancel_requested must be a bool")
        expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            require_hex64(self.payload_digest, "AgentTurnRequest.payload_digest")
            if self.payload_digest != expected:
                raise ValueError(
                    "AgentTurnRequest.payload_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_kind": self.operation_kind,
            "project_scope": self.project_scope.to_plain(),
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "message_ref": self.message_ref,
            "max_iterations": self.max_iterations,
            "max_tool_calls": self.max_tool_calls,
            "approval_policy": self.approval_policy,
            "approved_call_ids": list(self.approved_call_ids),
            "resume_call_id": self.resume_call_id,
            "resume_tool_call": (
                None
                if self.resume_tool_call is None
                else self.resume_tool_call.to_plain()
            ),
            "cancel_requested": self.cancel_requested,
            "payload_digest": self.payload_digest,
        }


@dataclass(frozen=True, slots=True)
class AgentTurnEvent:
    """One ordered episode event with a redacted, content-addressed payload."""

    schema_version: Literal["mrw.successor.agent-core.c6-1.event.v1"]
    event_type: Literal[
        "session_started",
        "user_message",
        "assistant_delta",
        "assistant_message",
        "tool_call_requested",
        "tool_call_started",
        "tool_result",
        "permission_requested",
        "approval_resolved",
        "run_resumed",
        "final_answer",
        "error",
    ]
    actor: str
    payload: FrozenJsonObject
    call_id: str | None = None
    event_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_TURN_EVENT_SCHEMA_REF:
            raise ValueError("AgentTurnEvent.schema_version is not frozen")
        if self.event_type not in AGENT_TURN_EVENT_TYPES:
            raise ValueError(f"unsupported event_type {self.event_type!r}")
        if not isinstance(self.actor, str) or not self.actor:
            raise ValueError("AgentTurnEvent.actor is required")
        object.__setattr__(self, "payload", freeze_c6_json_object(dict(self.payload)))
        expected = content_digest(self, omit_fields=("event_digest",))
        if self.event_digest == "":
            object.__setattr__(self, "event_digest", expected)
        else:
            require_hex64(self.event_digest, "AgentTurnEvent.event_digest")
            if self.event_digest != expected:
                raise ValueError("AgentTurnEvent.event_digest does not match content")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "actor": self.actor,
            "payload": thaw_json_value(self.payload),
            "call_id": self.call_id,
            "event_digest": self.event_digest,
        }


@dataclass(frozen=True, slots=True)
class AgentTurnEpisode:
    """Deterministic bounded episode; no raw value survives in events."""

    schema_version: Literal["mrw.successor.agent-core.c6-1.episode.v1"]
    episode_id: str
    request_digest: str
    ordered_events: tuple[AgentTurnEvent, ...]
    tool_results: tuple[AgentToolResult, ...]
    final_answer: str
    stop_reason: Literal[
        "final_answer",
        "no_more_tools",
        "permission_requested",
        "approval_denied",
        "max_tool_calls_exceeded",
        "max_iterations_exceeded",
        "canceled",
        "tool_needs_approval",
        "tool_deferred",
        "error",
    ]
    tool_call_count: int
    iteration: int
    episode_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_TURN_EPISODE_SCHEMA_REF:
            raise ValueError("AgentTurnEpisode.schema_version is not frozen")
        for name in ("episode_id", "request_digest"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"AgentTurnEpisode.{name} is required")
        require_hex64(self.request_digest, "AgentTurnEpisode.request_digest")
        object.__setattr__(self, "ordered_events", tuple(self.ordered_events))
        object.__setattr__(self, "tool_results", tuple(self.tool_results))
        if not isinstance(self.final_answer, str):
            raise TypeError("AgentTurnEpisode.final_answer must be a string")
        if self.stop_reason not in AGENT_TURN_STOP_REASONS:
            raise ValueError(f"unsupported stop_reason {self.stop_reason!r}")
        for name in ("tool_call_count", "iteration"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"AgentTurnEpisode.{name} must be non-negative int")
        expected = content_digest(self, omit_fields=("episode_digest",))
        if self.episode_digest == "":
            object.__setattr__(self, "episode_digest", expected)
        else:
            require_hex64(self.episode_digest, "AgentTurnEpisode.episode_digest")
            if self.episode_digest != expected:
                raise ValueError(
                    "AgentTurnEpisode.episode_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "request_digest": self.request_digest,
            "ordered_events": [event.to_plain() for event in self.ordered_events],
            "tool_results": [result.to_plain() for result in self.tool_results],
            "final_answer": self.final_answer,
            "stop_reason": self.stop_reason,
            "tool_call_count": self.tool_call_count,
            "iteration": self.iteration,
            "episode_digest": self.episode_digest,
        }


@dataclass(frozen=True, slots=True)
class AgentTurnFailure:
    code: Literal[
        "tool_schema_validation_failed",
        "tool_permission_denied",
        "tool_not_registered",
        "unsupported_model_step",
        "session_canceled",
        "loop_configuration_invalid",
    ]
    message: str
    stop_reason: str
    retryable: bool = False
    disposition: Literal["FAILED"] = "FAILED"


AgentTurnOutcome: TypeAlias = AgentTurnEpisode | AgentTurnFailure


@runtime_checkable
class ModelStepSource(Protocol):
    """Deterministic model-step source; no provider/configuration dependency."""

    def next_step(
        self,
        *,
        request: AgentTurnRequest,
        tool_names: tuple[str, ...],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> AgentModelStepOutcome: ...


@runtime_checkable
class ToolSpecimen(Protocol):
    """One capability-owned pure tool specimen (C2.1 in this family line)."""

    tool_name: str

    def validate(self, tool_call: AgentToolCall) -> AgentToolResult | None: ...

    def execute(
        self, tool_call: AgentToolCall, request: AgentTurnRequest
    ) -> AgentToolResult: ...


@runtime_checkable
class PermissionPolicy(Protocol):
    def permission_for(
        self, tool_call: AgentToolCall
    ) -> Literal["allow", "ask", "deny"]: ...


@runtime_checkable
class EventRedactor(Protocol):
    def redact(
        self,
        *,
        event_type: str,
        call_id: str | None,
        payload: dict[str, Any],
    ) -> FrozenJsonObject: ...


class StaticPermissionPolicy:
    """Deterministic permission policy over exact tool names."""

    def __init__(
        self,
        *,
        allow_tools: tuple[str, ...] = (),
        ask_tools: tuple[str, ...] = (),
        deny_tools: tuple[str, ...] = (),
    ) -> None:
        self.allow_tools = set(allow_tools)
        self.ask_tools = set(ask_tools)
        self.deny_tools = set(deny_tools)

    def permission_for(
        self, tool_call: AgentToolCall
    ) -> Literal["allow", "ask", "deny"]:
        if tool_call.tool_name in self.deny_tools:
            return "deny"
        if tool_call.tool_name in self.ask_tools:
            return "ask"
        return "allow"


class CanonicalJsonEventRedactor:
    """Default no-raw redactor: value snapshots only, never raw content."""

    def __init__(
        self,
        *,
        sensitive_keys: tuple[str, ...] = ("arguments", "structured_content"),
    ) -> None:
        self.sensitive_keys = set(sensitive_keys)

    def redact(
        self,
        *,
        event_type: str,
        call_id: str | None,
        payload: dict[str, Any],
    ) -> FrozenJsonObject:
        return freeze_c6_json_object(self._walk(payload))

    def _walk(self, value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                if key in self.sensitive_keys and isinstance(item, dict):
                    encoded = canonical_json(item)
                    out[key] = {
                        "redacted": True,
                        "keys": sorted(str(child) for child in item),
                        "sha256": sha256_hex(encoded.encode("utf-8")),
                        "raw_value_persisted": False,
                    }
                else:
                    out[key] = self._walk(item)
            return out
        if isinstance(value, (list, tuple)):
            return [self._walk(item) for item in value]
        return value


def _emit(
    events: list[AgentTurnEvent],
    redactor: EventRedactor,
    *,
    event_type: str,
    actor: str,
    payload: dict[str, Any],
    call_id: str | None = None,
) -> None:
    events.append(
        AgentTurnEvent(
            schema_version=AGENT_TURN_EVENT_SCHEMA_REF,
            event_type=event_type,
            actor=actor,
            payload=redactor.redact(
                event_type=event_type,
                call_id=call_id,
                payload=payload,
            ),
            call_id=call_id,
        )
    )


def _tool_specimens_by_name(
    tool_specimens: tuple[ToolSpecimen, ...],
) -> dict[str, ToolSpecimen]:
    by_name: dict[str, ToolSpecimen] = {}
    for specimen in tool_specimens:
        if specimen.tool_name in by_name:
            raise ValueError(f"duplicate tool specimen name {specimen.tool_name!r}")
        by_name[specimen.tool_name] = specimen
    return by_name


def interpret_agent_turn(
    request: AgentTurnRequest,
    *,
    model_step_source: ModelStepSource,
    tool_specimens: tuple[ToolSpecimen, ...],
    permission_policy: PermissionPolicy,
    redactor: EventRedactor,
) -> AgentTurnOutcome:
    """Run one bounded ordered episode; raw values never enter the episode."""

    if request.operation_kind != AGENT_CORE_C6_1_KIND:
        return AgentTurnFailure(
            code="loop_configuration_invalid",
            message="request operation_kind is not the frozen C6.1 episode atom",
            stop_reason="error",
        )
    by_name = _tool_specimens_by_name(tool_specimens)
    events: list[AgentTurnEvent] = []
    tool_results: list[AgentToolResult] = []
    transcript: list[dict[str, Any]] = [
        {"role": "user", "content": request.message_ref}
    ]
    final_answer = ""
    tool_call_count = 0

    _emit(
        events,
        redactor,
        event_type="session_started",
        actor="agent_core",
        payload={
            "project_key": request.project_scope.project_key,
            "core": "agent_core.c6_1.v1",
        },
    )
    _emit(
        events,
        redactor,
        event_type="user_message",
        actor="user",
        payload={"message_ref": request.message_ref},
    )

    resume_executed = False
    if request.resume_call_id is not None:
        if request.resume_call_id not in request.approved_call_ids:
            _emit(
                events,
                redactor,
                event_type="approval_resolved",
                actor="user",
                payload={
                    "approval_id": request.resume_call_id,
                    "approved": False,
                },
                call_id=request.resume_call_id,
            )
            return _episode(
                request,
                events,
                tool_results,
                final_answer="",
                stop_reason="approval_denied",
                tool_call_count=tool_call_count,
                iteration=0,
            )
        _emit(
            events,
            redactor,
            event_type="run_resumed",
            actor="agent_core",
            payload={"approval_id": request.resume_call_id},
            call_id=request.resume_call_id,
        )
        specimen = by_name.get(
            request.resume_tool_call.tool_name if request.resume_tool_call else ""
        )
        if specimen is None:
            return AgentTurnFailure(
                code="tool_not_registered",
                message="resume tool is not registered in the episode specimen set",
                stop_reason="error",
            )
        if request.resume_tool_call is None:
            return AgentTurnFailure(
                code="loop_configuration_invalid",
                message="resume_call_id requires resume_tool_call",
                stop_reason="error",
            )
        pending = request.resume_tool_call
        result = specimen.execute(pending, request)
        tool_results.append(result)
        transcript.append({"role": "tool", "tool_result": result.to_plain()})
        _emit(
            events,
            redactor,
            event_type="tool_result",
            actor="agent_core",
            payload={"tool_result": result.to_plain()},
            call_id=pending.call_id,
        )
        tool_call_count += 1
        resume_executed = True

    for iteration in range(1, max(1, request.max_iterations) + 1):
        if request.cancel_requested:
            _emit(
                events,
                redactor,
                event_type="error",
                actor="agent_core",
                payload={
                    "code": "session_canceled",
                    "message": "cooperative cancellation observed at loop boundary",
                },
            )
            return _episode(
                request,
                events,
                tool_results,
                final_answer=final_answer,
                stop_reason="canceled",
                tool_call_count=tool_call_count,
                iteration=iteration,
            )
        if tool_call_count >= request.max_tool_calls:
            return _episode(
                request,
                events,
                tool_results,
                final_answer=final_answer,
                stop_reason="max_tool_calls_exceeded",
                tool_call_count=tool_call_count,
                iteration=iteration,
            )
        step = model_step_source.next_step(
            request=request,
            tool_names=tuple(by_name),
            transcript=list(transcript),
            remaining_budget={
                "max_iterations": request.max_iterations,
                "iteration": iteration,
                "max_tool_calls": request.max_tool_calls,
                "remaining_tool_calls": max(
                    0, request.max_tool_calls - tool_call_count
                ),
            },
        )
        if isinstance(step, AgentModelStepFailure):
            _emit(
                events,
                redactor,
                event_type="error",
                actor="agent_core",
                payload={"code": step.code, "message": step.message},
            )
            return _episode(
                request,
                events,
                tool_results,
                final_answer=final_answer,
                stop_reason="error",
                tool_call_count=tool_call_count,
                iteration=iteration,
            )
        if step.step_type == "assistant_delta":
            _emit(
                events,
                redactor,
                event_type="assistant_delta",
                actor="agent_core",
                payload={"delta": step.content},
            )
            transcript.append({"role": "assistant", "delta": step.content})
            continue
        if step.step_type == "final_answer":
            final_answer = step.content
            _emit(
                events,
                redactor,
                event_type="final_answer",
                actor="agent_core",
                payload={"final_answer": final_answer},
            )
            return _episode(
                request,
                events,
                tool_results,
                final_answer=final_answer,
                stop_reason="final_answer",
                tool_call_count=tool_call_count,
                iteration=iteration,
            )
        if not step.tool_calls:
            _emit(
                events,
                redactor,
                event_type="final_answer",
                actor="agent_core",
                payload={"final_answer": final_answer or ""},
            )
            return _episode(
                request,
                events,
                tool_results,
                final_answer=final_answer,
                stop_reason="no_more_tools",
                tool_call_count=tool_call_count,
                iteration=iteration,
            )
        for tool_call in step.tool_calls:
            if tool_call_count >= request.max_tool_calls:
                return _episode(
                    request,
                    events,
                    tool_results,
                    final_answer=final_answer,
                    stop_reason="max_tool_calls_exceeded",
                    tool_call_count=tool_call_count,
                    iteration=iteration,
                )
            specimen = by_name.get(tool_call.tool_name)
            _emit(
                events,
                redactor,
                event_type="tool_call_requested",
                actor="agent_core",
                payload={
                    "tool_call": tool_call.to_plain(),
                    "permission": permission_policy.permission_for(tool_call),
                },
                call_id=tool_call.call_id,
            )
            if specimen is None:
                result = AgentToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary=f"Tool {tool_call.tool_name} is not registered.",
                    error=freeze_c6_json_object(
                        {"code": "tool_not_registered", "message": "unknown tool"}
                    ),
                )
                tool_results.append(result)
                _emit(
                    events,
                    redactor,
                    event_type="tool_result",
                    actor="agent_core",
                    payload={"tool_result": result.to_plain()},
                    call_id=tool_call.call_id,
                )
                tool_call_count += 1
                continue
            validation = specimen.validate(tool_call)
            if validation is not None:
                tool_results.append(validation)
                _emit(
                    events,
                    redactor,
                    event_type="tool_result",
                    actor="agent_core",
                    payload={"tool_result": validation.to_plain()},
                    call_id=tool_call.call_id,
                )
                tool_call_count += 1
                continue
            permission = permission_policy.permission_for(tool_call)
            if permission == "deny":
                result = AgentToolResult(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    status="failed",
                    model_summary=f"Tool {tool_call.tool_name} is denied by policy.",
                    error=freeze_c6_json_object(
                        {
                            "code": "tool_permission_denied",
                            "message": "tool is denied by policy",
                        }
                    ),
                )
                tool_results.append(result)
                _emit(
                    events,
                    redactor,
                    event_type="tool_result",
                    actor="agent_core",
                    payload={"tool_result": result.to_plain()},
                    call_id=tool_call.call_id,
                )
                tool_call_count += 1
                continue
            if (
                permission == "ask"
                and tool_call.call_id not in request.approved_call_ids
                and not resume_executed
            ):
                _emit(
                    events,
                    redactor,
                    event_type="permission_requested",
                    actor="agent_core",
                    payload={
                        "approval_id": f"approval:{tool_call.call_id}",
                        "tool_name": tool_call.tool_name,
                    },
                    call_id=tool_call.call_id,
                )
                return _episode(
                    request,
                    events,
                    tool_results,
                    final_answer="",
                    stop_reason="permission_requested",
                    tool_call_count=tool_call_count,
                    iteration=iteration,
                )
            _emit(
                events,
                redactor,
                event_type="tool_call_started",
                actor="agent_core",
                payload={"tool_name": tool_call.tool_name},
                call_id=tool_call.call_id,
            )
            result = specimen.execute(tool_call, request)
            tool_results.append(result)
            transcript.append({"role": "tool", "tool_result": result.to_plain()})
            _emit(
                events,
                redactor,
                event_type="tool_result",
                actor="agent_core",
                payload={"tool_result": result.to_plain()},
                call_id=tool_call.call_id,
            )
            tool_call_count += 1
            if result.status == "needs_approval":
                return _episode(
                    request,
                    events,
                    tool_results,
                    final_answer=final_answer,
                    stop_reason="tool_needs_approval",
                    tool_call_count=tool_call_count,
                    iteration=iteration,
                )
            if result.status == "deferred":
                return _episode(
                    request,
                    events,
                    tool_results,
                    final_answer=final_answer,
                    stop_reason="tool_deferred",
                    tool_call_count=tool_call_count,
                    iteration=iteration,
                )
        resume_executed = False

    return _episode(
        request,
        events,
        tool_results,
        final_answer=final_answer,
        stop_reason="max_iterations_exceeded",
        tool_call_count=tool_call_count,
        iteration=max(1, request.max_iterations),
    )


def _episode(
    request: AgentTurnRequest,
    events: list[AgentTurnEvent],
    tool_results: list[AgentToolResult],
    *,
    final_answer: str,
    stop_reason: str,
    tool_call_count: int,
    iteration: int,
) -> AgentTurnEpisode:
    return AgentTurnEpisode(
        schema_version=AGENT_TURN_EPISODE_SCHEMA_REF,
        episode_id=f"episode:{request.turn_id}",
        request_digest=request.payload_digest,
        ordered_events=tuple(events),
        tool_results=tuple(tool_results),
        final_answer=final_answer,
        stop_reason=stop_reason,
        tool_call_count=tool_call_count,
        iteration=iteration,
    )


def _profile_ref(
    profile_id: str, profile_version: str, digest: str
) -> ContractProfileRef:
    return ContractProfileRef(
        profile_id=profile_id,
        profile_version=profile_version,
        profile_digest=digest,
    )


def _semantic_profile() -> SemanticProfile:
    values = {
        "semantic_profile_id": "agent_core.episode_interpret.v1.semantic",
        "semantic_profile_version": "1.0.0",
        "reads": ("AgentTurnRequest.v1", "AgentToolCall.v1"),
        "creates": ("AgentTurnEpisode.v1", "AgentTurnEvent.v1"),
        "creates_relations": (),
        "declared_loss": ("RAW_TOOL_ARGUMENTS_OMITTED",),
        "observation_profile_ref": AGENT_CORE_C6_1_OBSERVATION_PROFILE,
    }
    return SemanticProfile(**values, profile_digest=content_digest(values))


def _effect_profile() -> EffectProfile:
    values = {
        "effect_profile_id": "agent_core.episode_interpret.v1.effect",
        "effect_profile_version": "1.0.0",
        "execution_class": "PURE_TRANSFORM",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": ("loop_boundary",),
        "internal_export_only": False,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "logical_request_id",
    }
    return EffectProfile(**values, profile_digest=content_digest(values))


def _resource_profile() -> ResourceProfile:
    values = {
        "resource_profile_id": "agent_core.episode_interpret.v1.resource",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("cpu",),
        "concurrency_key": "project",
        "budget_units": "episode",
        "default_soft_limit_seconds": 30,
        "default_hard_limit_seconds": 120,
        "node_profile_selector": "any",
        "budget_ref": "mrw.successor.agent-core.c6-1.budget.v1",
        "deadline_policy_ref": "mrw.successor.agent-core.c6-1.deadline.v1",
        "node_profile_requirements": ("any",),
        "units": 1,
    }
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile() -> FailureProfile:
    values = {
        "failure_profile_id": "agent_core.episode_interpret.v1.failure",
        "failure_profile_version": "1.0.0",
        "typed_failures": tuple(sorted(AGENT_TURN_FAILURE_CODES)),
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": False,
        "readback_or_compensation": "none",
        "failure_union_ref": "mrw.successor.agent-core.c6-1.failures.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": None,
        "compensation_profile_ref": None,
    }
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile() -> AuthorityProfile:
    values = {
        "authority_profile_id": "agent_core.episode_interpret.v1.authority",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": AGENT_CORE_C6_1_OWNER,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile() -> InterpreterProfile:
    values = {
        "interpreter_profile_id": "successor.agent_core.c6_1.episode.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (AGENT_CORE_C6_1_KIND,),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "successor-native.agent_core.c6_1.episode",
                "version": "1.0.0",
                "donor": "AgentCore.run ordered loop algebra",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.no-raw-event.v1",
        "resource_profile_ref": "agent_core.episode_interpret.v1.resource",
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "loop_boundary",
        "idempotency_profile_ref": "logical_request_id",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": AGENT_TURN_EPISODE_SCHEMA_REF,
    }
    return InterpreterProfile(**values, profile_digest=content_digest(values))


def _observation_profile() -> ObservationProfile:
    values = {
        "observation_profile_id": AGENT_CORE_C6_1_OBSERVATION_PROFILE,
        "observation_profile_version": "1.0.0",
        "dimensions": (
            "schema_version",
            "episode_id",
            "ordered_event_types",
            "tool_call_ids",
            "tool_result_statuses",
            "stop_reason",
            "final_answer",
            "tool_call_count",
            "iteration",
            "raw_value_persisted",
        ),
        "compatible_with_legacy": True,
        "observation_schema_ref": AGENT_TURN_EPISODE_SCHEMA_REF,
    }
    return ObservationProfile(**values, profile_digest=content_digest(values))


@dataclass(frozen=True, slots=True)
class AgentCoreC6_1CapabilityBundle:
    bundle_id: str
    operation: OperationContract
    codecs: tuple[Any, ...]
    profiles: dict[str, object]

    def payload_codec(self) -> Any:
        return self.codecs[0]


def build_agent_core_c6_1_bundle() -> AgentCoreC6_1CapabilityBundle:
    semantic = _semantic_profile()
    effect = _effect_profile()
    resource = _resource_profile()
    failure = _failure_profile()
    authority = _authority_profile()
    interpreter = _interpreter_profile()
    observation = _observation_profile()
    operation = make_operation_contract(
        kind=AGENT_CORE_C6_1_KIND,
        contract_version="1.0.0",
        input_type=AGENT_CORE_C6_1_PAYLOAD_TYPE,
        output_type=AGENT_CORE_C6_1_RESULT_TYPE,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        semantic_profile_ref=_profile_ref(
            semantic.semantic_profile_id,
            semantic.semantic_profile_version,
            semantic.profile_digest,
        ),
        effect_profile_ref=_profile_ref(
            effect.effect_profile_id,
            effect.effect_profile_version,
            effect.profile_digest,
        ),
        resource_profile_ref=_profile_ref(
            resource.resource_profile_id,
            resource.resource_profile_version,
            resource.profile_digest,
        ),
        failure_profile_ref=_profile_ref(
            failure.failure_profile_id,
            failure.failure_profile_version,
            failure.profile_digest,
        ),
        authority_profile_ref=_profile_ref(
            authority.authority_profile_id,
            authority.authority_profile_version,
            authority.profile_digest,
        ),
        interpreter_compatibility_ref=_profile_ref(
            interpreter.interpreter_profile_id,
            interpreter.interpreter_profile_version,
            interpreter.profile_digest,
        ),
        observation_profile_ref=_profile_ref(
            observation.observation_profile_id,
            observation.observation_profile_version,
            observation.profile_digest,
        ),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=AGENT_CORE_C6_1_OWNER,
    )
    codec = build_payload_codec(
        codec_id=AGENT_CORE_C6_1_PAYLOAD_CODEC_ID,
        codec_version="1",
        contract_ref=operation.ref,
        payload_type_id=AGENT_CORE_C6_1_PAYLOAD_TYPE.type_id,
        dto_cls=AgentTurnRequest,
    )
    return AgentCoreC6_1CapabilityBundle(
        bundle_id="mrw.successor.agent-core.c6-1",
        operation=operation,
        codecs=(codec,),
        profiles={
            "semantic": semantic,
            "effect": effect,
            "resource": resource,
            "failure": failure,
            "authority": authority,
            "interpreter": interpreter,
            "observation": observation,
        },
    )


def build_agent_core_c6_1_catalog(
    bundle: AgentCoreC6_1CapabilityBundle,
) -> OperationContractCatalogSnapshot:
    return OperationContractCatalogSnapshot(
        catalog_id=AGENT_CORE_C6_1_CATALOG_ID,
        catalog_version=AGENT_CORE_C6_1_CATALOG_VERSION,
        entries=(
            (
                bundle.operation.ref.kind,
                bundle.operation.ref.contract_version,
                bundle.operation.ref.contract_digest,
                bundle.operation.owner_capability_id,
            ),
        ),
    )


def build_agent_core_c6_1_registry(
    bundle: AgentCoreC6_1CapabilityBundle,
) -> OperationContractRegistry:
    return OperationContractRegistry(
        build_agent_core_c6_1_catalog(bundle),
        (bundle.operation,),
    )
