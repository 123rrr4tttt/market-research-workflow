"""Frozen typed contracts for the C6.2 provider-interpretation atom.

The atom interprets one deterministic model step through an injected provider
port.  No global configuration, model cache, credential bytes or network are
touched; the port is a test-receipt boundary and ``provider_calls`` records
only explicit port invocations.  Failures, OUTCOME_UNKNOWN and authoritative
readback are represented as typed receipts, never as collapsed metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, NoReturn, Protocol, TypeAlias, runtime_checkable

from functorial_kit import Failure
from mrw_functorial_kit.core import (
    successor_capability_contract_failures as capability_contract_failures,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStep,
    ProjectScope,
    SchemaSpec,
    build_payload_codec,
)
from app.successor_runtime.capabilities.checksum import (
    content_digest,
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
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "AGENT_CORE_C6_2_CATALOG_ID",
    "AGENT_CORE_C6_2_CATALOG_VERSION",
    "AGENT_CORE_C6_2_KIND",
    "AGENT_CORE_C6_2_OPERATION_ID",
    "AGENT_CORE_C6_2_OWNER",
    "AGENT_CORE_C6_2_PAYLOAD_CODEC_ID",
    "AGENT_CORE_C6_2_PAYLOAD_SCHEMA",
    "AGENT_CORE_C6_2_RESULT_TYPE",
    "AGENT_CORE_C6_2_SEMANTIC_IDENTITY",
    "AGENT_MODEL_STEP_REQUEST_SCHEMA",
    "AGENT_MODEL_STEP_RESULT_SCHEMA",
    "PROVIDER_ATTEMPT_RECEIPT_SCHEMA",
    "PROVIDER_READBACK_SCHEMA",
    "AgentCoreC6_2CapabilityBundle",
    "AgentModelStepRequest",
    "AgentModelStepResult",
    "ProviderAttemptReceipt",
    "ProviderFailure",
    "ProviderPort",
    "ProviderReadback",
    "ProviderStepOutcome",
    "ProviderStepSucceeded",
    "ReceiptOnlyProviderPort",
    "TestReceiptProviderPort",
    "build_agent_core_c6_2_bundle",
    "build_agent_core_c6_2_catalog",
    "build_agent_core_c6_2_registry",
    "build_c6_2_receipt_only_evidence",
    "interpret_model_step",
    "try_interpret_model_step",
]


AGENT_CORE_C6_2_KIND = "agent.model_step.v1"
AGENT_CORE_C6_2_OWNER = "agent_core.c6_2.v1"
AGENT_CORE_C6_2_OPERATION_ID = "agent.model_step"
AGENT_CORE_C6_2_PAYLOAD_SCHEMA = "mrw.successor.agent-core.c6-2.payload.v1"
AGENT_CORE_C6_2_PAYLOAD_CODEC_ID = "mrw.successor.agent-core.c6-2.payload.codec.v1"
AGENT_CORE_C6_2_CATALOG_ID = "mrw.successor.agent-core.c6-2.operations"
AGENT_CORE_C6_2_CATALOG_VERSION = "1.0.0"
AGENT_CORE_C6_2_OBSERVATION_PROFILE = "mrw.successor.agent-core.c6-2.observation.v1"
AGENT_CORE_C6_2_SEMANTIC_IDENTITY = "agent-core.model-step"
AGENT_CORE_C6_2_CONTRACT_WITNESS = "test:test_w05_n3_c62_typed_contract_failures"
AGENT_MODEL_STEP_REQUEST_SCHEMA_REF = "mrw.successor.agent-core.c6-2.model-step-request.v1"
PROVIDER_ATTEMPT_RECEIPT_SCHEMA_REF = "mrw.successor.agent-core.c6-2.attempt-receipt.v1"
PROVIDER_READBACK_SCHEMA_REF = "mrw.successor.agent-core.c6-2.readback.v1"
AGENT_MODEL_STEP_RESULT_SCHEMA_REF = "mrw.successor.agent-core.c6-2.model-step-result.v1"

AGENT_MODEL_STEP_REQUEST_TYPE = ObjectType("AgentModelStepRequest.v1")
PROVIDER_ATTEMPT_RECEIPT_TYPE = ObjectType("ProviderAttemptReceipt.v1")
PROVIDER_READBACK_TYPE = ObjectType("ProviderReadback.v1")
AGENT_MODEL_STEP_RESULT_TYPE = ObjectType("AgentModelStepResult.v1")
AGENT_CORE_C6_2_PAYLOAD_TYPE = AGENT_MODEL_STEP_REQUEST_TYPE
AGENT_CORE_C6_2_RESULT_TYPE = AGENT_MODEL_STEP_RESULT_TYPE

AGENT_MODEL_STEP_REQUEST_SCHEMA = SchemaSpec(
    schema_ref=AGENT_MODEL_STEP_REQUEST_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("operation_kind", True),
        ("project_scope", True),
        ("session_id", True),
        ("turn_id", True),
        ("message_ref", True),
        ("transcript_ref", True),
        ("tool_contract_refs", True),
        ("max_iterations", True),
        ("iteration", True),
        ("max_tool_calls", True),
        ("remaining_tool_calls", True),
        ("provider_profile_ref", True),
        ("credential_ref", True),
        ("payload_digest", True),
    ),
)
PROVIDER_ATTEMPT_RECEIPT_SCHEMA = SchemaSpec(
    schema_ref=PROVIDER_ATTEMPT_RECEIPT_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("attempt_id", True),
        ("request_digest", True),
        ("outcome_code", True),
        ("provider_calls", True),
        ("readback_status", True),
        ("readback_digest", True),
        ("receipt_digest", True),
    ),
)
PROVIDER_READBACK_SCHEMA = SchemaSpec(
    schema_ref=PROVIDER_READBACK_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("attempt_id", True),
        ("status", True),
        ("provider_observation_digest", False),
    ),
)
AGENT_MODEL_STEP_RESULT_SCHEMA = SchemaSpec(
    schema_ref=AGENT_MODEL_STEP_RESULT_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("step", False),
        ("receipt", True),
        ("result_digest", True),
    ),
)

PROVIDER_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "ProviderUnavailable",
        "ProviderInvocationFailed",
        "ProviderProtocolInvalid",
        "ProviderTimeout",
        "ProviderRateLimited",
        "ProviderCredentialRejected",
        "ProviderFallbackSelected",
        "ProviderOutcomeUnknown",
    }
)
PROVIDER_READBACK_STATUSES: frozenset[str] = frozenset(
    {
        "AUTHORITATIVE_READBACK_SUCCEEDED",
        "AUTHORITATIVE_READBACK_FAILED",
        "NON_START_PROOF",
    }
)


def _contract_failure(
    code: str,
    message: str,
    *,
    boundary_class: str = "PURE_CONTRACT_FAILURE",
    **details: Any,
) -> Failure:
    """Build the one registered capability-contract failure value."""

    return capability_contract_failures.fail(
        code,
        message,
        {
            "owner": AGENT_CORE_C6_2_OWNER,
            "effect_boundary": "agent_core.c6_2.contract_core",
            "boundary_class": boundary_class,
            "failure_family": capability_contract_failures.name,
            "witness": AGENT_CORE_C6_2_CONTRACT_WITNESS,
            **details,
        },
    )


def _raise_contract_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
) -> NoReturn:
    # kit:boundary owner=agent_core_c6_2.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.capability.contract_failure witness=test:test_w05_n3_c62_retained_boundary_lifts
    raise exception_type(failure.message)


def _raise_programmer_defect(message: str) -> NoReturn:
    # kit:boundary owner=agent_core_c6_2.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w05_n3_c62_retained_boundary_lifts
    raise TypeError(message)  # noqa: TRY003, TRY004


def _hex64_failure(value: Any, field_name: str) -> Failure | None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        return _contract_failure(
            "digest_contract_invalid",
            f"{field_name} must be a 64-char lowercase hex digest",
            field=field_name,
        )
    return None


@dataclass(frozen=True, slots=True)
class AgentModelStepRequest:
    """Exact-bound provider-step request; transcript/message stay as refs."""

    schema_version: Literal["mrw.successor.agent-core.c6-2.payload.v1"]
    operation_kind: Literal["agent.model_step.v1"]
    project_scope: ProjectScope
    session_id: str
    turn_id: str
    message_ref: str
    transcript_ref: str
    tool_contract_refs: tuple[str, ...]
    max_iterations: int
    iteration: int
    max_tool_calls: int
    remaining_tool_calls: int
    provider_profile_ref: str
    credential_ref: str
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_CORE_C6_2_PAYLOAD_SCHEMA:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    f"unsupported payload schema {self.schema_version!r}",
                    field="AgentModelStepRequest.schema_version",
                )
            )
        if self.operation_kind != AGENT_CORE_C6_2_KIND:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    f"unsupported operation kind {self.operation_kind!r}",
                    field="AgentModelStepRequest.operation_kind",
                )
            )
        for name in (
            "session_id",
            "turn_id",
            "message_ref",
            "transcript_ref",
            "provider_profile_ref",
            "credential_ref",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                _raise_contract_failure(
                    _contract_failure(
                        "schema_contract_invalid",
                        f"AgentModelStepRequest.{name} is required",
                        field=f"AgentModelStepRequest.{name}",
                    )
                )
        object.__setattr__(self, "tool_contract_refs", tuple(self.tool_contract_refs))
        if not all(isinstance(ref, str) and ref.strip() for ref in self.tool_contract_refs):
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "tool_contract_refs must be non-empty strings",
                    field="AgentModelStepRequest.tool_contract_refs",
                )
            )
        for name in (
            "max_iterations",
            "iteration",
            "max_tool_calls",
            "remaining_tool_calls",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                _raise_contract_failure(
                    _contract_failure(
                        "schema_contract_invalid",
                        f"AgentModelStepRequest.{name} must be non-negative int",
                        field=f"AgentModelStepRequest.{name}",
                    )
                )
        if self.iteration > self.max_iterations:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "iteration exceeds max_iterations",
                    field="AgentModelStepRequest.iteration",
                )
            )
        if self.remaining_tool_calls > self.max_tool_calls:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "remaining_tool_calls exceeds max_tool_calls",
                    field="AgentModelStepRequest.remaining_tool_calls",
                )
            )
        expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            digest_failure = _hex64_failure(self.payload_digest, "AgentModelStepRequest.payload_digest")
            if digest_failure is not None:
                _raise_contract_failure(digest_failure)
            if self.payload_digest != expected:
                _raise_contract_failure(
                    _contract_failure(
                        "digest_contract_invalid",
                        "AgentModelStepRequest.payload_digest does not match content",
                        field="AgentModelStepRequest.payload_digest",
                    )
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_kind": self.operation_kind,
            "project_scope": self.project_scope.to_plain(),
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "message_ref": self.message_ref,
            "transcript_ref": self.transcript_ref,
            "tool_contract_refs": list(self.tool_contract_refs),
            "max_iterations": self.max_iterations,
            "iteration": self.iteration,
            "max_tool_calls": self.max_tool_calls,
            "remaining_tool_calls": self.remaining_tool_calls,
            "provider_profile_ref": self.provider_profile_ref,
            "credential_ref": self.credential_ref,
            "payload_digest": self.payload_digest,
        }


@dataclass(frozen=True, slots=True)
class ProviderStepSucceeded:
    """Named observational step success without a live-provider claim."""

    schema_version: Literal["mrw.successor.agent-core.c6-2.step-success.v1"]
    step: AgentModelStep
    provider_observation_ref: str
    provider_calls: int

    def __post_init__(self) -> None:
        if self.schema_version != "mrw.successor.agent-core.c6-2.step-success.v1":
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "ProviderStepSucceeded.schema_version is not frozen",
                    field="ProviderStepSucceeded.schema_version",
                )
            )
        if not isinstance(self.provider_observation_ref, str) or not self.provider_observation_ref:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "provider_observation_ref is required",
                    field="ProviderStepSucceeded.provider_observation_ref",
                )
            )
        if not isinstance(self.provider_calls, int) or isinstance(self.provider_calls, bool) or self.provider_calls < 0:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "provider_calls must be a non-negative int",
                    field="ProviderStepSucceeded.provider_calls",
                )
            )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "step": self.step.to_plain(),
            "provider_observation_ref": self.provider_observation_ref,
            "provider_calls": self.provider_calls,
        }


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """Typed provider failure; OUTCOME_UNKNOWN keeps attempt identity."""

    code: Literal[
        "ProviderUnavailable",
        "ProviderInvocationFailed",
        "ProviderProtocolInvalid",
        "ProviderTimeout",
        "ProviderRateLimited",
        "ProviderCredentialRejected",
        "ProviderFallbackSelected",
        "ProviderOutcomeUnknown",
    ]
    message: str
    retryable: bool = False
    disposition: Literal["FAILED"] = "FAILED"


ProviderStepOutcome: TypeAlias = ProviderStepSucceeded | ProviderFailure


@dataclass(frozen=True, slots=True)
class ProviderReadback:
    """Authoritative readback or NonStartProof for one attempt."""

    schema_version: Literal["mrw.successor.agent-core.c6-2.readback.v1"]
    attempt_id: str
    status: Literal[
        "AUTHORITATIVE_READBACK_SUCCEEDED",
        "AUTHORITATIVE_READBACK_FAILED",
        "NON_START_PROOF",
    ]
    provider_observation_digest: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != PROVIDER_READBACK_SCHEMA_REF:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "ProviderReadback.schema_version is not frozen",
                    field="ProviderReadback.schema_version",
                )
            )
        if not isinstance(self.attempt_id, str) or not self.attempt_id:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "ProviderReadback.attempt_id is required",
                    field="ProviderReadback.attempt_id",
                )
            )
        if self.status not in PROVIDER_READBACK_STATUSES:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    f"unsupported readback status {self.status!r}",
                    field="ProviderReadback.status",
                )
            )
        if self.provider_observation_digest is not None:
            digest_failure = _hex64_failure(
                self.provider_observation_digest,
                "ProviderReadback.provider_observation_digest",
            )
            if digest_failure is not None:
                _raise_contract_failure(digest_failure)

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "status": self.status,
            "provider_observation_digest": self.provider_observation_digest,
        }


@dataclass(frozen=True, slots=True)
class ProviderAttemptReceipt:
    """Durable receipt for one provider-step attempt (no secret bytes)."""

    schema_version: Literal["mrw.successor.agent-core.c6-2.attempt-receipt.v1"]
    attempt_id: str
    request_digest: str
    outcome_code: str
    provider_calls: int
    readback_status: Literal[
        "AUTHORITATIVE_READBACK_SUCCEEDED",
        "AUTHORITATIVE_READBACK_FAILED",
        "NON_START_PROOF",
        "NOT_APPLICABLE",
    ]
    readback_digest: str
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != PROVIDER_ATTEMPT_RECEIPT_SCHEMA_REF:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "ProviderAttemptReceipt.schema_version is not frozen",
                    field="ProviderAttemptReceipt.schema_version",
                )
            )
        for name in ("attempt_id", "outcome_code"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                _raise_contract_failure(
                    _contract_failure(
                        "schema_contract_invalid",
                        f"ProviderAttemptReceipt.{name} is required",
                        field=f"ProviderAttemptReceipt.{name}",
                    )
                )
        for value, field_name in (
            (self.request_digest, "ProviderAttemptReceipt.request_digest"),
            (self.readback_digest, "ProviderAttemptReceipt.readback_digest"),
        ):
            digest_failure = _hex64_failure(value, field_name)
            if digest_failure is not None:
                _raise_contract_failure(digest_failure)
        if not isinstance(self.provider_calls, int) or isinstance(self.provider_calls, bool) or self.provider_calls < 0:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "ProviderAttemptReceipt.provider_calls must be non-negative",
                    field="ProviderAttemptReceipt.provider_calls",
                )
            )
        if self.outcome_code not in PROVIDER_FAILURE_CODES and self.outcome_code != "ProviderStepSucceeded":
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    f"unsupported outcome code {self.outcome_code!r}",
                    field="ProviderAttemptReceipt.outcome_code",
                )
            )
        if self.readback_status not in PROVIDER_READBACK_STATUSES | {"NOT_APPLICABLE"}:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    f"unsupported readback status {self.readback_status!r}",
                    field="ProviderAttemptReceipt.readback_status",
                )
            )
        expected = content_digest(self, omit_fields=("receipt_digest",))
        if self.receipt_digest == "":
            object.__setattr__(self, "receipt_digest", expected)
        else:
            digest_failure = _hex64_failure(self.receipt_digest, "ProviderAttemptReceipt.receipt_digest")
            if digest_failure is not None:
                _raise_contract_failure(digest_failure)
            if self.receipt_digest != expected:
                _raise_contract_failure(
                    _contract_failure(
                        "digest_contract_invalid",
                        "ProviderAttemptReceipt.receipt_digest does not match content",
                        field="ProviderAttemptReceipt.receipt_digest",
                    )
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "request_digest": self.request_digest,
            "outcome_code": self.outcome_code,
            "provider_calls": self.provider_calls,
            "readback_status": self.readback_status,
            "readback_digest": self.readback_digest,
            "receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True, slots=True)
class AgentModelStepResult:
    """Typed model-step result carrying step success or a failure receipt."""

    schema_version: Literal["mrw.successor.agent-core.c6-2.model-step-result.v1"]
    step: AgentModelStep | None
    receipt: ProviderAttemptReceipt
    result_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_MODEL_STEP_RESULT_SCHEMA_REF:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "AgentModelStepResult.schema_version is not frozen",
                    field="AgentModelStepResult.schema_version",
                )
            )
        if self.step is not None and not isinstance(self.step, AgentModelStep):
            _raise_programmer_defect("AgentModelStepResult.step must be AgentModelStep or None")
        expected = content_digest(self, omit_fields=("result_digest",))
        if self.result_digest == "":
            object.__setattr__(self, "result_digest", expected)
        else:
            digest_failure = _hex64_failure(self.result_digest, "AgentModelStepResult.result_digest")
            if digest_failure is not None:
                _raise_contract_failure(digest_failure)
            if self.result_digest != expected:
                _raise_contract_failure(
                    _contract_failure(
                        "digest_contract_invalid",
                        "AgentModelStepResult.result_digest does not match content",
                        field="AgentModelStepResult.result_digest",
                    )
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "step": None if self.step is None else self.step.to_plain(),
            "receipt": self.receipt.to_plain(),
            "result_digest": self.result_digest,
        }


@runtime_checkable
class ProviderPort(Protocol):
    """Deterministic injected provider boundary; never reads global config."""

    provider_calls: int

    def next_step(self, request: AgentModelStepRequest) -> ProviderStepOutcome: ...

    def readback(self, attempt_id: str) -> ProviderReadback: ...


class TestReceiptProviderPort:
    """Scripted deterministic port recording every explicit invocation."""

    interpreter_id = "fixture.agent_core.c6_2.provider_port.v1"

    def __init__(
        self,
        outcomes: list[ProviderStepOutcome] | tuple[ProviderStepOutcome, ...] = (),
        readbacks: dict[str, ProviderReadback] | None = None,
    ) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[AgentModelStepRequest] = []
        self._readbacks = dict(readbacks or {})

    @property
    def provider_calls(self) -> int:
        return len(self.calls)

    def next_step(self, request: AgentModelStepRequest) -> ProviderStepOutcome:
        self.calls.append(request)
        if self._outcomes:
            return self._outcomes.pop(0)
        return ProviderFailure(
            code="ProviderOutcomeUnknown",
            message="scripted provider exhausted",
        )

    def readback(self, attempt_id: str) -> ProviderReadback:
        return self._readbacks.get(
            attempt_id,
            ProviderReadback(
                schema_version=PROVIDER_READBACK_SCHEMA_REF,
                attempt_id=attempt_id,
                status="NON_START_PROOF",
            ),
        )


class ReceiptOnlyProviderPort:
    """Receipt-only port that never performs a provider invocation."""

    interpreter_id = "fixture.agent_core.c6_2.receipt_only_port.v1"
    provider_calls = 0

    def next_step(self, request: AgentModelStepRequest) -> ProviderStepOutcome:
        return ProviderFailure(
            code="ProviderOutcomeUnknown",
            message="receipt-only port does not invoke any provider",
            retryable=False,
        )

    def readback(self, attempt_id: str) -> ProviderReadback:
        return ProviderReadback(
            schema_version=PROVIDER_READBACK_SCHEMA_REF,
            attempt_id=attempt_id,
            status="NON_START_PROOF",
        )


def interpret_model_step(
    request: AgentModelStepRequest,
    port: ProviderPort,
    *,
    attempt_id: str,
) -> AgentModelStepResult:
    """Interpret one bounded model step and emit a durable receipt."""

    outcome = try_interpret_model_step(
        request,
        port,
        attempt_id=attempt_id,
    )
    if isinstance(outcome, ProviderFailure):
        _raise_contract_failure(
            _contract_failure(
                "program_binding_invalid",
                outcome.message,
                provider_failure_code=outcome.code,
                attempt_id=attempt_id,
            )
        )
    return outcome


def try_interpret_model_step(
    request: AgentModelStepRequest,
    port: ProviderPort,
    *,
    attempt_id: str,
) -> AgentModelStepResult | ProviderFailure:
    """Return a durable result, or a typed failure instead of raising."""

    provider_outcome = port.next_step(request)
    provider_calls = int(port.provider_calls)
    if isinstance(provider_outcome, ProviderFailure):
        outcome = provider_outcome
        if outcome.code == "ProviderOutcomeUnknown":
            readback = port.readback(attempt_id)
            if readback.attempt_id != attempt_id:
                failure = _contract_failure(
                    "scope_contract_invalid",
                    "provider readback attempt_id does not match the requested attempt",
                    attempt_id=attempt_id,
                )
                return ProviderFailure(
                    code="ProviderInvocationFailed",
                    message=failure.message,
                    retryable=False,
                )
            readback_status: str = readback.status
            if readback.status in {
                "AUTHORITATIVE_READBACK_SUCCEEDED",
                "AUTHORITATIVE_READBACK_FAILED",
            }:
                digest = readback.provider_observation_digest
                if digest is None:
                    failure = _contract_failure(
                        "schema_contract_invalid",
                        "authoritative readback requires a canonical observation digest",
                        attempt_id=attempt_id,
                    )
                    return ProviderFailure(
                        code="ProviderInvocationFailed",
                        message=failure.message,
                        retryable=False,
                    )
                if (
                    not isinstance(digest, str)
                    or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest)
                ):
                    failure = _contract_failure(
                        "digest_contract_invalid",
                        ("ProviderReadback.provider_observation_digest must be a 64-char lowercase hex digest"),
                        attempt_id=attempt_id,
                    )
                    return ProviderFailure(
                        code="ProviderInvocationFailed",
                        message=failure.message,
                        retryable=False,
                    )
            readback_digest = readback.provider_observation_digest or content_digest(
                {"schema": PROVIDER_READBACK_SCHEMA_REF, "attempt_id": attempt_id}
            )
        else:
            readback_status = "NOT_APPLICABLE"
            readback_digest = content_digest(
                {
                    "schema": PROVIDER_ATTEMPT_RECEIPT_SCHEMA_REF,
                    "outcome_code": outcome.code,
                }
            )
        return AgentModelStepResult(
            schema_version=AGENT_MODEL_STEP_RESULT_SCHEMA_REF,
            step=None,
            receipt=ProviderAttemptReceipt(
                schema_version=PROVIDER_ATTEMPT_RECEIPT_SCHEMA_REF,
                attempt_id=attempt_id,
                request_digest=request.payload_digest,
                outcome_code=outcome.code,
                provider_calls=provider_calls,
                readback_status=readback_status,
                readback_digest=readback_digest,
            ),
        )
    return AgentModelStepResult(
        schema_version=AGENT_MODEL_STEP_RESULT_SCHEMA_REF,
        step=provider_outcome.step,
        receipt=ProviderAttemptReceipt(
            schema_version=PROVIDER_ATTEMPT_RECEIPT_SCHEMA_REF,
            attempt_id=attempt_id,
            request_digest=request.payload_digest,
            outcome_code="ProviderStepSucceeded",
            provider_calls=provider_calls,
            readback_status="NOT_APPLICABLE",
            readback_digest=content_digest(
                {
                    "schema": PROVIDER_ATTEMPT_RECEIPT_SCHEMA_REF,
                    "outcome_code": "ProviderStepSucceeded",
                }
            ),
        ),
    )


def build_c6_2_receipt_only_evidence(
    request: AgentModelStepRequest,
    *,
    attempt_id: str,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=generated_evidence "
    "fact_source=ReceiptOnlyProviderPort+receipt_fields "
    "witness=test:test_w05_agent_core_authority_metadata",
]:
    """Deterministic fragment input proving zero provider invocations."""

    port = ReceiptOnlyProviderPort()
    result = interpret_model_step(request, port, attempt_id=attempt_id)
    return {
        "schema": "mrw.successor.agent-core.c6-2.receipt-only-evidence.v1",
        "provider_calls": port.provider_calls,
        "outcome_code": result.receipt.outcome_code,
        "readback_status": result.receipt.readback_status,
        "receipt_digest": result.receipt.receipt_digest,
        "result_digest": result.result_digest,
        "network_required": False,
        "live_provider_claim": False,
    }


def _profile_ref(profile_id: str, profile_version: str, digest: str) -> ContractProfileRef:
    return ContractProfileRef(
        profile_id=profile_id,
        profile_version=profile_version,
        profile_digest=digest,
    )


def _semantic_profile() -> SemanticProfile:
    values = {
        "semantic_profile_id": "agent.model_step.v1.semantic",
        "semantic_profile_version": "1.0.0",
        "reads": ("AgentModelStepRequest.v1", "AgentToolCall.v1"),
        "creates": ("AgentModelStepResult.v1", "ProviderAttemptReceipt.v1"),
        "creates_relations": (),
        "declared_loss": ("RAW_TRANSCRIPT_OMITTED",),
        "observation_profile_ref": AGENT_CORE_C6_2_OBSERVATION_PROFILE,
    }
    return SemanticProfile(**values, profile_digest=content_digest(values))


def _effect_profile() -> EffectProfile:
    values = {
        "effect_profile_id": "agent.model_step.v1.effect",
        "effect_profile_version": "1.0.0",
        "execution_class": "EFFECTFUL",
        "external_visibility": "INTERNAL_ONLY",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": ("attempt_boundary",),
        "internal_export_only": True,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "logical_request_id",
    }
    return EffectProfile(**values, profile_digest=content_digest(values))


def _resource_profile() -> ResourceProfile:
    values = {
        "resource_profile_id": "agent.model_step.v1.resource",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("llm_call",),
        "concurrency_key": "provider:model",
        "budget_units": "request+token",
        "default_soft_limit_seconds": 30,
        "default_hard_limit_seconds": 120,
        "node_profile_selector": "any",
        "budget_ref": "mrw.successor.agent-core.c6-2.budget.receipt-only.v1",
        "deadline_policy_ref": "mrw.successor.agent-core.c6-2.deadline.v1",
        "node_profile_requirements": ("any",),
        "units": 1,
    }
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile() -> FailureProfile:
    values = {
        "failure_profile_id": "agent.model_step.v1.failure",
        "failure_profile_version": "1.0.0",
        "typed_failures": tuple(sorted(PROVIDER_FAILURE_CODES)),
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": True,
        "readback_or_compensation": "authoritative_readback",
        "failure_union_ref": "mrw.successor.agent-core.c6-2.failures.v1",
        "retryable_failure_kinds": ("ProviderTimeout", "ProviderRateLimited"),
        "readback_profile_ref": PROVIDER_READBACK_SCHEMA_REF,
        "compensation_profile_ref": None,
    }
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile() -> AuthorityProfile:
    values = {
        "authority_profile_id": "agent.model_step.v1.authority",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": ("mrw.credential.opaque.v1",),
        "canonical_owner": AGENT_CORE_C6_2_OWNER,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile() -> InterpreterProfile:
    values = {
        "interpreter_profile_id": "successor.agent_core.c6_2.provider.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (AGENT_CORE_C6_2_KIND,),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "successor-native.agent_core.c6_2.provider",
                "version": "1.0.0",
                "donor": "CoreProvider.next_step+NativeToolCallingCoreProvider normalization",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.credential-ref-only.v1",
        "resource_profile_ref": "agent.model_step.v1.resource",
        "credential_requirements_ref": "mrw.credential.opaque.v1",
        "cancellation_profile_ref": "attempt_boundary",
        "idempotency_profile_ref": "logical_request_id",
        "authoritative_readback_profile_ref": PROVIDER_READBACK_SCHEMA_REF,
        "receipt_codec_ref": PROVIDER_ATTEMPT_RECEIPT_SCHEMA_REF,
    }
    return InterpreterProfile(**values, profile_digest=content_digest(values))


def _observation_profile() -> ObservationProfile:
    values = {
        "observation_profile_id": AGENT_CORE_C6_2_OBSERVATION_PROFILE,
        "observation_profile_version": "1.0.0",
        "dimensions": (
            "schema_version",
            "attempt_id",
            "provider_profile_ref",
            "model_step_type",
            "ordered_tool_calls",
            "provider_calls",
            "outcome_code",
            "readback_status",
            "receipt_digest",
            "network_scope",
        ),
        "compatible_with_legacy": True,
        "observation_schema_ref": PROVIDER_ATTEMPT_RECEIPT_SCHEMA_REF,
    }
    return ObservationProfile(**values, profile_digest=content_digest(values))


@dataclass(frozen=True, slots=True)
class AgentCoreC6_2CapabilityBundle:
    bundle_id: str
    operation: OperationContract
    codecs: tuple[Any, ...]
    profiles: dict[str, object]

    def payload_codec(self) -> Any:
        return self.codecs[0]


def build_agent_core_c6_2_bundle() -> Annotated[
    AgentCoreC6_2CapabilityBundle,
    "kit:non-authoritative derived_as=view "
    "fact_source=AGENT_CORE_C6_2_OWNER+capability_contract_constants "
    "witness=test:test_w05_agent_core_authority_metadata",
]:
    semantic = _semantic_profile()
    effect = _effect_profile()
    resource = _resource_profile()
    failure = _failure_profile()
    authority = _authority_profile()
    interpreter = _interpreter_profile()
    observation = _observation_profile()
    operation = make_operation_contract(
        kind=AGENT_CORE_C6_2_KIND,
        contract_version="1.0.0",
        input_type=AGENT_CORE_C6_2_PAYLOAD_TYPE,
        output_type=AGENT_CORE_C6_2_RESULT_TYPE,
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
        owner_capability_id=AGENT_CORE_C6_2_OWNER,
    )
    codec = build_payload_codec(
        codec_id=AGENT_CORE_C6_2_PAYLOAD_CODEC_ID,
        codec_version="1",
        contract_ref=operation.ref,
        payload_type_id=AGENT_CORE_C6_2_PAYLOAD_TYPE.type_id,
        dto_cls=AgentModelStepRequest,
    )
    return AgentCoreC6_2CapabilityBundle(
        bundle_id="mrw.successor.agent-core.c6-2",
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


def build_agent_core_c6_2_catalog(
    bundle: AgentCoreC6_2CapabilityBundle,
) -> Annotated[
    OperationContractCatalogSnapshot,
    "kit:non-authoritative derived_as=view "
    "fact_source=AgentCoreC6_2CapabilityBundle.operations "
    "witness=test:test_w05_agent_core_authority_metadata",
]:
    return OperationContractCatalogSnapshot(
        catalog_id=AGENT_CORE_C6_2_CATALOG_ID,
        catalog_version=AGENT_CORE_C6_2_CATALOG_VERSION,
        entries=(
            (
                bundle.operation.ref.kind,
                bundle.operation.ref.contract_version,
                bundle.operation.ref.contract_digest,
                bundle.operation.owner_capability_id,
            ),
        ),
    )


def build_agent_core_c6_2_registry(
    bundle: AgentCoreC6_2CapabilityBundle,
) -> Annotated[
    OperationContractRegistry,
    "kit:non-authoritative derived_as=view "
    "fact_source=AgentCoreC6_2CapabilityBundle+catalog_snapshot "
    "witness=test:test_w05_agent_core_authority_metadata",
]:
    return OperationContractRegistry(
        build_agent_core_c6_2_catalog(bundle),
        (bundle.operation,),
    )
