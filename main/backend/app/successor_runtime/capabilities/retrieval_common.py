"""Retrieval-family canonical shared contracts.

This module is the single owner of the pure declarations shared by the
retrieval native capabilities: the candidate observation schema, the typed
flow-expression language, and the information-topology / project-retrieval
failure families and state codec registered by the semantics contribution.
It contains no concrete provider or search callable and performs no effect.

The service modules that previously owned these declarations re-export them
from here so their existing consumers keep the same import identities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Callable, Literal, Mapping, NoReturn, cast, get_args

from functorial_kit import Failure, define_codec, define_failure_family
from functorial_kit.contributions import contribution_failures

from app.successor_runtime.research.object_types import ObjectType


# --- candidate observation schema ---------------------------------------

ProviderStatus = Literal["completed", "failed", "not_configured"]
FailureKind = Literal["rate_limited", "timeout", "not_configured", "exception", "unknown"]
StopReason = Literal["limit_reached", "candidates_observed", "no_candidates_observed", "not_attempted"]


@dataclass(frozen=True, slots=True)
class CandidateRequestFailure:
    """A rejected request; no provider attempt or evidence claim occurred."""

    code: Literal["INVALID_TOPIC", "INVALID_LIMIT", "INVALID_DAYS_BACK", "INVALID_OFFSET", "INVALID_KEYWORDS"]
    field: str
    message: str


def _runtime_object(value: object) -> object:
    """Keep constructor inputs total when callers bypass static annotations."""

    return value


def raise_retrieval_contract_error(
    exception_type: type[Exception],
    message: object,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """Preserve the public exception ABI for unreachable contract defects."""

    if cause is None:
        # kit:boundary owner=ret class=PROGRAMMER_DEFECT failure_family=none witness=test:test_ret_contract_errors
        raise exception_type(message)
    # kit:boundary owner=ret class=PROGRAMMER_DEFECT failure_family=none witness=test:test_ret_contract_errors
    raise exception_type(message) from cause


@dataclass(frozen=True, slots=True)
class CandidateSearchRequest:
    topic: str
    language: str = "en"
    max_results: int = 10
    provider: str = "auto"
    days_back: int | None = None
    exclude_existing: bool = True
    start_offset: int | None = None
    keywords: tuple[str, ...] | None = None
    project_ref: str | None = None
    source_ref: str | None = None
    facet_ref: str | None = None

    def __post_init__(self) -> None:
        raw_keywords: object = self.keywords
        if isinstance(raw_keywords, (list, tuple)):
            object.__setattr__(self, "keywords", tuple(raw_keywords))

    def validation_failure(self) -> CandidateRequestFailure | None:
        topic = _runtime_object(self.topic)
        max_results = _runtime_object(self.max_results)
        days_back = _runtime_object(self.days_back)
        start_offset = _runtime_object(self.start_offset)
        keywords = _runtime_object(self.keywords)
        if not isinstance(topic, str) or not topic.strip():
            return CandidateRequestFailure("INVALID_TOPIC", "topic", "topic must be nonempty")
        if type(max_results) is not int or max_results < 1:
            return CandidateRequestFailure("INVALID_LIMIT", "max_results", "max_results must be positive")
        if days_back is not None and (type(days_back) is not int or days_back < 1):
            return CandidateRequestFailure("INVALID_DAYS_BACK", "days_back", "days_back must be positive")
        if start_offset is not None and (type(start_offset) is not int or start_offset < 1):
            return CandidateRequestFailure("INVALID_OFFSET", "start_offset", "start_offset must be positive")
        if keywords is not None and (
            not isinstance(keywords, tuple)
            or any(
                not isinstance(item, str) or not item.strip()
                for item in cast(tuple[object, ...], keywords)
            )
        ):
            return CandidateRequestFailure(
                "INVALID_KEYWORDS", "keywords", "keywords must contain only nonempty strings"
            )
        return None

    @classmethod
    def from_legacy(cls, **kwargs: Any) -> CandidateSearchRequest:
        return cls(**kwargs)


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    provider: str
    route: str
    keyword: str | None
    status: ProviderStatus
    returned_count: int = 0
    failure_kind: FailureKind | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateOccurrence:
    resource_uri: str
    keyword: str | None
    provider: str
    route: str
    original_rank: int | None
    retained: bool
    facet_ref: str | None = None


@dataclass(frozen=True, slots=True)
class Candidate:
    resource_uri: str
    title: str | None
    snippet: str | None
    source: str | None
    keyword: str | None
    original_rank: int | None
    result_rank: int
    relevance_score: float
    raw: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass(frozen=True, slots=True)
class CandidateBundle:
    request: CandidateSearchRequest
    candidates: tuple[Candidate, ...]
    occurrences: tuple[CandidateOccurrence, ...]
    observations: tuple[ProviderObservation, ...]
    stop_reason: StopReason
    request_failure: CandidateRequestFailure | None = None

    @property
    def partial(self) -> bool:
        return bool(self.candidates) and any(item.status != "completed" for item in self.observations)

    def legacy_list(self) -> list[dict[str, Any]]:
        """Compatibility projection. Branch failures and duplicate occurrences are lost."""
        return [dict(item.raw) for item in self.candidates]


RetrievalQueryKind = Literal["initial", "followup"]


def retrieval_budget_id(
    *, project_key: str, root_run_id: str, plan_id: str, mode_version: str
) -> str:
    """Return the stable identity shared by every child of one retrieval root."""

    payload = json.dumps(
        {
            "mode_version": mode_version,
            "plan_id": plan_id,
            "project_key": project_key,
            "root_run_id": root_run_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "retrieval-budget:" + sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class RetrievalBudgetState:
    """Immutable domain budget transported across event-linked child runs.

    The runtime journal remains the consumption evidence.  A new value is
    materialized from settled child events; this object is not a second budget
    ledger and cannot reserve or release capacity by itself.
    """

    budget_id: str
    project_key: str
    root_run_id: str
    plan_id: str
    mode_version: str
    max_queries: int
    max_materials: int
    max_followups: int
    queries_attempted: int = 0
    materials_accepted: int = 0
    followup_rounds_started: int = 0

    def __post_init__(self) -> None:
        identities = (
            self.budget_id,
            self.project_key,
            self.root_run_id,
            self.plan_id,
            self.mode_version,
        )
        if any(not value.strip() for value in identities):
            raise_retrieval_contract_error(ValueError, 'retrieval budget identities must be nonempty')
        expected = retrieval_budget_id(
            project_key=self.project_key,
            root_run_id=self.root_run_id,
            plan_id=self.plan_id,
            mode_version=self.mode_version,
        )
        if self.budget_id != expected:
            raise_retrieval_contract_error(ValueError, 'retrieval budget identity does not match its root binding')
        counts = (
            self.max_queries,
            self.max_materials,
            self.max_followups,
            self.queries_attempted,
            self.materials_accepted,
            self.followup_rounds_started,
        )
        if any(type(value) is not int for value in counts):
            raise_retrieval_contract_error(TypeError, 'retrieval budget counters must be integers')
        if self.max_queries < 1 or self.max_materials < 1 or self.max_followups < 0:
            raise_retrieval_contract_error(ValueError, 'retrieval budget ceilings are invalid')
        if not 0 <= self.queries_attempted <= self.max_queries:
            raise_retrieval_contract_error(ValueError, 'retrieval query consumption exceeds its ceiling')
        if not 0 <= self.materials_accepted <= self.max_materials:
            raise_retrieval_contract_error(ValueError, 'retrieval material consumption exceeds its ceiling')
        if not 0 <= self.followup_rounds_started <= self.max_followups:
            raise_retrieval_contract_error(ValueError, 'retrieval followup consumption exceeds its ceiling')

    @property
    def remaining_queries(self) -> int:
        return self.max_queries - self.queries_attempted

    @property
    def remaining_materials(self) -> int:
        return self.max_materials - self.materials_accepted

    @property
    def remaining_followups(self) -> int:
        return self.max_followups - self.followup_rounds_started

    def after_settled_events(
        self,
        *,
        query_attempts: int = 0,
        accepted_materials: int = 0,
        followup_rounds: int = 0,
    ) -> "RetrievalBudgetState":
        """Derive the next value from unique settled lineage events."""

        deltas = (query_attempts, accepted_materials, followup_rounds)
        if any(type(value) is not int or value < 0 for value in deltas):
            raise_retrieval_contract_error(ValueError, 'retrieval budget deltas must be nonnegative integers')
        return RetrievalBudgetState(
            budget_id=self.budget_id,
            project_key=self.project_key,
            root_run_id=self.root_run_id,
            plan_id=self.plan_id,
            mode_version=self.mode_version,
            max_queries=self.max_queries,
            max_materials=self.max_materials,
            max_followups=self.max_followups,
            queries_attempted=self.queries_attempted + query_attempts,
            materials_accepted=self.materials_accepted + accepted_materials,
            followup_rounds_started=self.followup_rounds_started + followup_rounds,
        )


@dataclass(frozen=True, slots=True)
class RetrievalCandidateInvocation:
    """One exact provider attempt linked to the immutable root budget."""

    query_id: str
    route_id: str
    query_kind: RetrievalQueryKind
    query_ordinal: int
    followup_round: int
    budget_id: str
    request: CandidateSearchRequest

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.query_id, self.route_id, self.budget_id)
        ):
            raise_retrieval_contract_error(ValueError, 'retrieval candidate invocation identities must be nonempty')
        if self.query_kind not in ("initial", "followup"):
            raise_retrieval_contract_error(ValueError, 'retrieval candidate invocation has an invalid query kind')
        if type(self.query_ordinal) is not int or self.query_ordinal < 1:
            raise_retrieval_contract_error(ValueError, 'retrieval query ordinal must be positive')
        if type(self.followup_round) is not int or self.followup_round < 0:
            raise_retrieval_contract_error(ValueError, 'retrieval followup round must be nonnegative')
        if self.query_kind == "initial" and self.followup_round != 0:
            raise_retrieval_contract_error(ValueError, 'initial query cannot carry a followup round')
        if self.query_kind == "followup" and self.followup_round < 1:
            raise_retrieval_contract_error(ValueError, 'followup query requires a positive round')

    def validate_budget(self, budget: RetrievalBudgetState) -> None:
        """Fail before an effect when the exact root budget no longer admits it."""

        if self.budget_id != budget.budget_id:
            raise_retrieval_contract_error(ValueError, 'candidate invocation crosses retrieval budget identity')
        if self.query_ordinal <= budget.queries_attempted:
            raise_retrieval_contract_error(ValueError, 'candidate invocation would replay a consumed query ordinal')
        if self.query_ordinal > budget.max_queries:
            raise_retrieval_contract_error(ValueError, 'candidate invocation exceeds the query budget')
        if self.query_kind == "followup":
            if self.followup_round <= budget.followup_rounds_started:
                raise_retrieval_contract_error(ValueError, 'candidate invocation would replay a followup round')
            if self.followup_round > budget.max_followups:
                raise_retrieval_contract_error(ValueError, 'candidate invocation exceeds the followup budget')


CandidateAttemptState = Literal["completed", "failed", "cancelled"]


@dataclass(frozen=True, slots=True)
class RetrievalCandidateAttemptOutcome:
    """One settled query attempt, including runtime failure and cancellation."""

    query_id: str
    route_id: str
    query_kind: RetrievalQueryKind
    query_ordinal: int
    followup_round: int
    budget_id: str
    state: CandidateAttemptState
    bundle: CandidateBundle | None = None
    error_code: str | None = None
    error_message: str | None = None
    terminal_ref: str | None = None
    terminal_digest: str | None = None

    def __post_init__(self) -> None:
        identities = (self.query_id, self.route_id, self.budget_id)
        if any(not value.strip() for value in identities):
            raise_retrieval_contract_error(ValueError, 'candidate attempt outcome identities must be nonempty')
        if self.state not in ("completed", "failed", "cancelled"):
            raise_retrieval_contract_error(ValueError, 'candidate attempt outcome has an invalid state')
        if type(self.query_ordinal) is not int or self.query_ordinal < 1:
            raise_retrieval_contract_error(ValueError, 'candidate attempt outcome ordinal must be positive')
        if type(self.followup_round) is not int or self.followup_round < 0:
            raise_retrieval_contract_error(ValueError, 'candidate attempt outcome followup round must be nonnegative')
        if self.query_kind == "initial" and self.followup_round != 0:
            raise_retrieval_contract_error(ValueError, 'initial candidate outcome cannot carry a followup round')
        if self.query_kind == "followup" and self.followup_round < 1:
            raise_retrieval_contract_error(ValueError, 'followup candidate outcome requires a positive round')
        if self.state == "completed":
            if self.bundle is None:
                raise_retrieval_contract_error(ValueError, 'completed candidate outcome requires a bundle')
            if self.bundle.request.validation_failure() is not None:
                raise_retrieval_contract_error(ValueError, 'completed candidate outcome carries an invalid request')
        elif self.bundle is not None:
            raise_retrieval_contract_error(ValueError, 'non-completed candidate outcome cannot carry a bundle')
        if self.state == "failed" and not str(self.error_code or "").strip():
            raise_retrieval_contract_error(ValueError, 'failed candidate outcome requires an error code')

    @classmethod
    def completed(
        cls,
        invocation: RetrievalCandidateInvocation,
        bundle: CandidateBundle,
    ) -> "RetrievalCandidateAttemptOutcome":
        if bundle.request != invocation.request:
            raise_retrieval_contract_error(ValueError, 'candidate bundle request differs from its invocation')
        return cls(
            query_id=invocation.query_id,
            route_id=invocation.route_id,
            query_kind=invocation.query_kind,
            query_ordinal=invocation.query_ordinal,
            followup_round=invocation.followup_round,
            budget_id=invocation.budget_id,
            state="completed",
            bundle=bundle,
        )

    @classmethod
    def terminal_without_value(
        cls,
        invocation: RetrievalCandidateInvocation,
        *,
        state: Literal["failed", "cancelled"],
        error_code: str | None = None,
        error_message: str | None = None,
        terminal_ref: str | None = None,
        terminal_digest: str | None = None,
    ) -> "RetrievalCandidateAttemptOutcome":
        return cls(
            query_id=invocation.query_id,
            route_id=invocation.route_id,
            query_kind=invocation.query_kind,
            query_ordinal=invocation.query_ordinal,
            followup_round=invocation.followup_round,
            budget_id=invocation.budget_id,
            state=state,
            error_code=error_code or ("CANCELLED" if state == "cancelled" else None),
            error_message=error_message,
            terminal_ref=terminal_ref,
            terminal_digest=terminal_digest,
        )


CANDIDATE_REQUEST_TYPE = ObjectType("CandidateSearchRequest.v1")
CANDIDATE_BUNDLE_TYPE = ObjectType("CandidateBundle.v1")


# --- typed flow-expression language ------------------------------------


@dataclass(frozen=True, slots=True)
class FlowPort:
    name: str
    object_type: ObjectType


@dataclass(frozen=True, slots=True)
class FlowInterface:
    ports: tuple[FlowPort, ...]


@dataclass(frozen=True, slots=True)
class FlowOperation:
    operation_id: str
    version: str
    inputs: FlowInterface
    outputs: FlowInterface
    effect_refs: tuple[str, ...] = ()
    failure_refs: tuple[str, ...] = ()
    authority_ref: str = ""
    stop_ref: str = ""
    entrypoint_ref: str = ""
    control_kind: Literal["atomic", "macro"] = "atomic"


@dataclass(frozen=True, slots=True)
class FlowIdentity:
    interface: FlowInterface


@dataclass(frozen=True, slots=True)
class FlowOccurrence:
    occurrence_id: str
    operation: FlowOperation


@dataclass(frozen=True, slots=True)
class PortWire:
    output_port: str
    input_port: str


@dataclass(frozen=True, slots=True)
class FlowThen:
    first: FlowExpression
    second: FlowExpression
    wiring: tuple[PortWire, ...]


FlowExpression = FlowIdentity | FlowOccurrence | FlowThen


@dataclass(frozen=True, slots=True)
class RetrievalFlowSource:
    flow_id: str
    version: str
    owner: str
    expression: FlowExpression
    indexed: bool = True


@dataclass(frozen=True, slots=True)
class FlowEnd:
    role: Literal["input", "operation_input", "operation_output", "output"]
    port: str
    occurrence_id: str = ""


@dataclass(frozen=True, slots=True)
class FlowEdge:
    source: FlowEnd
    target: FlowEnd


@dataclass(frozen=True, slots=True)
class RetrievalFlowDefinition:
    source: RetrievalFlowSource
    inputs: FlowInterface
    outputs: FlowInterface
    occurrences: tuple[FlowOccurrence, ...]
    edges: tuple[FlowEdge, ...]

    @property
    def contribution_id(self) -> str:
        return f"{self.source.flow_id}.{self.source.version}"


def _interface(expression: FlowExpression) -> tuple[FlowInterface, FlowInterface]:
    if isinstance(expression, FlowIdentity):
        return expression.interface, expression.interface
    if isinstance(expression, FlowOccurrence):
        return expression.operation.inputs, expression.operation.outputs
    return _interface(expression.first)[0], _interface(expression.second)[1]


def _validate_interface(interface: FlowInterface, path: str, issues: list[dict[str, str]]) -> None:
    names: set[str] = set()
    for index, port in enumerate(interface.ports):
        if not port.name or port.name in names or not port.object_type.type_id:
            issues.append({"path": f"{path}.ports[{index}]", "message": "empty or duplicate port/type"})
        names.add(port.name)


def _check(expression: FlowExpression, path: str, ids: set[str], issues: list[dict[str, str]]) -> None:
    if isinstance(expression, FlowIdentity):
        _validate_interface(expression.interface, path, issues)
        return
    if isinstance(expression, FlowOccurrence):
        operation = expression.operation
        if not expression.occurrence_id or expression.occurrence_id in ids:
            issues.append({"path": f"{path}.occurrence_id", "message": "empty or repeated occurrence"})
        ids.add(expression.occurrence_id)
        if not operation.operation_id or not operation.version or operation.control_kind not in {"atomic", "macro"}:
            issues.append({"path": f"{path}.operation", "message": "invalid operation identity or control kind"})
        if operation.control_kind == "macro" and not operation.entrypoint_ref:
            issues.append({"path": f"{path}.operation.entrypoint_ref", "message": "macro requires an external entrypoint"})
        for key in ("effect_refs", "failure_refs"):
            if any(not ref for ref in getattr(operation, key)):
                issues.append({"path": f"{path}.operation.{key}", "message": "empty contract reference"})
        _validate_interface(operation.inputs, f"{path}.inputs", issues)
        _validate_interface(operation.outputs, f"{path}.outputs", issues)
        return
    _check(expression.first, f"{path}.first", ids, issues)
    _check(expression.second, f"{path}.second", ids, issues)
    upstream = {port.name: port.object_type for port in _interface(expression.first)[1].ports}
    downstream = {port.name: port.object_type for port in _interface(expression.second)[0].ports}
    if len(expression.wiring) != len(upstream) or len(expression.wiring) != len(downstream):
        issues.append({"path": f"{path}.wiring", "message": "complete interface wiring required"})
    if {wire.output_port for wire in expression.wiring} != set(upstream) or {wire.input_port for wire in expression.wiring} != set(downstream):
        issues.append({"path": f"{path}.wiring", "message": "wiring must be a bijection of declared ports"})
    for index, wire in enumerate(expression.wiring):
        if wire.output_port in upstream and wire.input_port in downstream and upstream[wire.output_port] != downstream[wire.input_port]:
            issues.append({"path": f"{path}.wiring[{index}]", "message": "endpoint ObjectType mismatch"})


def _graph(expression: FlowExpression) -> tuple[tuple[FlowOccurrence, ...], tuple[FlowEdge, ...]]:
    if isinstance(expression, FlowIdentity):
        return (), tuple(FlowEdge(FlowEnd("input", port.name), FlowEnd("output", port.name)) for port in expression.interface.ports)
    if isinstance(expression, FlowOccurrence):
        return (expression,), (
            tuple(FlowEdge(FlowEnd("input", port.name), FlowEnd("operation_input", port.name, expression.occurrence_id)) for port in expression.operation.inputs.ports)
            + tuple(FlowEdge(FlowEnd("operation_output", port.name, expression.occurrence_id), FlowEnd("output", port.name)) for port in expression.operation.outputs.ports)
        )
    left_nodes, left_edges = _graph(expression.first)
    right_nodes, right_edges = _graph(expression.second)
    right_inputs = {edge.source.port: edge.target for edge in right_edges if edge.source.role == "input"}
    left_outputs = {edge.target.port: edge.source for edge in left_edges if edge.target.role == "output"}
    bridge = tuple(FlowEdge(left_outputs[wire.output_port], right_inputs[wire.input_port]) for wire in expression.wiring)
    retained = tuple(edge for edge in left_edges if edge.target.role != "output") + tuple(edge for edge in right_edges if edge.source.role != "input")
    # Identity wires are transparent even when either side is itself a composite.
    edges = retained + bridge
    while True:
        passthrough = next((edge for edge in edges if edge.source.role == "input" and edge.target.role == "output"), None)
        if passthrough is None or len(edges) == 1:
            break
        incoming = [edge for edge in edges if edge.target == passthrough.source]
        outgoing = [edge for edge in edges if edge.source == passthrough.target]
        if not incoming and not outgoing:
            break
        edges = tuple(edge for edge in edges if edge != passthrough and edge not in incoming and edge not in outgoing) + tuple(
            FlowEdge(before.source, after.target) for before in incoming for after in outgoing
        )
    return left_nodes + right_nodes, edges


def lower_retrieval_flow_source(source: RetrievalFlowSource) -> RetrievalFlowDefinition | Failure:
    issues: list[dict[str, str]] = []
    if not source.flow_id or not source.version or not source.owner:
        issues.append({"path": "$.source", "message": "flow identity, version and owner are required"})
    _check(source.expression, "$.expression", set(), issues)
    if issues:
        return contribution_failures.fail("CONTRIBUTION_INVALID", "retrieval flow definition invalid", {"issues": tuple(issues)})
    inputs, outputs = _interface(source.expression)
    occurrences, edges = _graph(source.expression)
    definitions: dict[tuple[str, str], FlowOperation] = {}
    for occurrence in occurrences:
        key = (occurrence.operation.operation_id, occurrence.operation.version)
        prior = definitions.setdefault(key, occurrence.operation)
        if prior != occurrence.operation:
            return contribution_failures.fail(
                "CONTRIBUTION_INVALID", "one operation identity/version has conflicting contracts",
                {"operation_id": key[0], "version": key[1]},
            )
    return RetrievalFlowDefinition(source, inputs, outputs, occurrences, edges)


@dataclass(frozen=True, slots=True)
class FlowOperationBinding:
    operation_id: str
    version: str
    input_type: ObjectType
    output_type: ObjectType
    effect_refs: tuple[str, ...]
    failure_refs: tuple[str, ...]
    authority_ref: str
    stop_ref: str
    entrypoint_ref: str
    invoke: Callable[[Any], Any]


@dataclass(frozen=True, slots=True)
class RetrievalFlowAssemblyContext:
    bindings: tuple[FlowOperationBinding, ...]


@dataclass(frozen=True, slots=True)
class RetrievalFlowBinding:
    definition: RetrievalFlowDefinition
    bindings: tuple[FlowOperationBinding, ...]

    def run(self, value: Any) -> Any | Failure:
        """Interpret only an explicitly assembled single-port linear method."""
        result = value
        by_key = {(item.operation_id, item.version): item for item in self.bindings}
        for occurrence in self.definition.occurrences:
            operation = occurrence.operation
            if len(operation.inputs.ports) != 1 or len(operation.outputs.ports) != 1:
                return contribution_failures.fail(
                    "CONTRIBUTION_INVALID", "multi-port execution requires an original runtime interpreter"
                )
            result = by_key[(operation.operation_id, operation.version)].invoke(result)
        return result


def assemble_retrieval_flow_definition(
    definition: RetrievalFlowDefinition, context: RetrievalFlowAssemblyContext,
) -> RetrievalFlowBinding | Failure:
    expected = {(item.operation.operation_id, item.operation.version): item.operation for item in definition.occurrences}
    supplied = {(item.operation_id, item.version): item for item in context.bindings}
    if len(supplied) != len(context.bindings) or set(supplied) != set(expected) or any(
        len(operation.inputs.ports) != 1 or len(operation.outputs.ports) != 1
        or supplied[key].input_type != operation.inputs.ports[0].object_type
        or supplied[key].output_type != operation.outputs.ports[0].object_type
        or supplied[key].effect_refs != operation.effect_refs
        or supplied[key].failure_refs != operation.failure_refs
        or supplied[key].authority_ref != operation.authority_ref
        or supplied[key].stop_ref != operation.stop_ref
        or supplied[key].entrypoint_ref != operation.entrypoint_ref
        for key, operation in expected.items()
    ):
        return contribution_failures.fail("CONTRIBUTION_INVALID", "retrieval flow binding does not match typed operations")
    return RetrievalFlowBinding(definition, context.bindings)


# --- information-topology canonical declarations ------------------------

topology_failures = define_failure_family(
    "information_topology",
    (
        "INVALID_STRUCTURE", "INVALID_PATCH", "VERSION_CONFLICT", "NOT_FOUND",
        "STALE_REFERENCE", "UNRESOLVABLE_REFERENCE", "UNKNOWN_PROFILE",
        "MAPPING_NOT_APPLICABLE", "SOURCE_CHANGED", "IDENTITY_CONFLICT",
        "INVALID_WIRE_FORMAT",
    ),
)


@dataclass(frozen=True, slots=True)
class ElementRef:
    project_key: str
    module_id: str
    namespace: str
    type_id: str
    local_id: str


@dataclass(frozen=True, slots=True)
class BoundRef:
    ref: ElementRef
    observed_revision: str
    content_digest: str | None = None


@dataclass(frozen=True, slots=True)
class Endpoint:
    role: str
    target: BoundRef
    position: int | None = None


@dataclass(frozen=True, slots=True)
class Element:
    ref: BoundRef
    attributes: Mapping[str, Any] = field(default_factory=dict[str, Any])
    endpoints: tuple[Endpoint, ...] = ()


@dataclass(frozen=True, slots=True)
class TopologyState:
    profile_id: str
    profile_version: str
    elements: tuple[Element, ...]


@dataclass(frozen=True, slots=True)
class TopologyView:
    definition_id: str
    definition_version: str
    input_revisions: Mapping[str, str]
    members: tuple[BoundRef, ...]
    relations: tuple[BoundRef, ...]
    organization: Mapping[str, Any] = field(default_factory=dict[str, Any])


ViewProjection = Callable[[TopologyState], tuple[tuple[BoundRef, ...], tuple[BoundRef, ...], Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class ViewSpec:
    definition_id: str
    definition_version: str
    profile_id: str
    profile_version: str
    project: ViewProjection


@dataclass(frozen=True, slots=True)
class PatchOperation:
    """An explicit structural edit. `remove` uses ref; add/replace use element."""

    action: str
    ref: BoundRef
    element: Element | None = None


def _ref_wire(ref: ElementRef) -> dict[str, str]:
    return {
        "project_key": ref.project_key, "module_id": ref.module_id,
        "namespace": ref.namespace, "type_id": ref.type_id, "local_id": ref.local_id,
    }


def _bound_wire(ref: BoundRef) -> dict[str, Any]:
    return {"ref": _ref_wire(ref.ref), "observed_revision": ref.observed_revision,
            "content_digest": ref.content_digest}


def _state_wire(state: TopologyState) -> Mapping[str, Any]:
    return {
        "kind": "information_topology.state.v1",
        "profile_id": state.profile_id,
        "profile_version": state.profile_version,
        "elements": [
            {"ref": _bound_wire(element.ref), "attributes": dict(element.attributes),
             "endpoints": [
                 {"role": endpoint.role, "target": _bound_wire(endpoint.target),
                  "position": endpoint.position}
                 for endpoint in element.endpoints
             ]}
            for element in state.elements
        ],
    }


def _invalid(path: str) -> Failure:
    return topology_failures.fail("INVALID_WIRE_FORMAT", f"invalid topology wire value at {path}", {"path": path})


def _string_object_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    untyped = cast(Mapping[object, object], value)
    if any(not isinstance(key, str) for key in untyped):
        return None
    return cast(Mapping[str, object], untyped)


def _parse_ref(raw: object, path: str) -> ElementRef | Failure:
    values = _string_object_mapping(raw)
    if values is None or set(values) != {
        "project_key", "module_id", "namespace", "type_id", "local_id"
    }:
        return _invalid(path)
    if any(not isinstance(values[key], str) or not values[key] for key in values):
        return _invalid(path)
    return ElementRef(
        project_key=cast(str, values["project_key"]),
        module_id=cast(str, values["module_id"]),
        namespace=cast(str, values["namespace"]),
        type_id=cast(str, values["type_id"]),
        local_id=cast(str, values["local_id"]),
    )


def _parse_bound(raw: object, path: str) -> BoundRef | Failure:
    values = _string_object_mapping(raw)
    if values is None or set(values) != {"ref", "observed_revision", "content_digest"}:
        return _invalid(path)
    ref = _parse_ref(values["ref"], f"{path}.ref")
    if isinstance(ref, Failure):
        return ref
    revision = values["observed_revision"]
    digest = values["content_digest"]
    if not isinstance(revision, str) or not revision or (digest is not None and not isinstance(digest, str)):
        return _invalid(path)
    return BoundRef(ref, revision, digest)


def _parse_state(raw: Mapping[str, Any]) -> TopologyState | Failure:
    if not isinstance(raw["profile_id"], str) or not raw["profile_id"]:
        return _invalid("profile_id")
    if not isinstance(raw["profile_version"], str) or not raw["profile_version"]:
        return _invalid("profile_version")
    source_elements: object = raw["elements"]
    if not isinstance(source_elements, list):
        return _invalid("elements")
    elements: list[Element] = []
    for index, item in enumerate(cast(list[object], source_elements)):
        path = f"elements[{index}]"
        item_values = _string_object_mapping(item)
        if item_values is None or set(item_values) != {"ref", "attributes", "endpoints"}:
            return _invalid(path)
        ref = _parse_bound(item_values["ref"], f"{path}.ref")
        if isinstance(ref, Failure):
            return ref
        attributes = item_values["attributes"]
        attribute_values = _string_object_mapping(attributes)
        if attribute_values is None:
            return _invalid(f"{path}.attributes")
        typed_attributes = cast(Mapping[str, Any], attribute_values)
        source_endpoints = item_values["endpoints"]
        if not isinstance(source_endpoints, list):
            return _invalid(f"{path}.endpoints")
        endpoints: list[Endpoint] = []
        for endpoint_index, raw_endpoint in enumerate(cast(list[object], source_endpoints)):
            endpoint_path = f"{path}.endpoints[{endpoint_index}]"
            endpoint_values = _string_object_mapping(raw_endpoint)
            if endpoint_values is None or set(endpoint_values) != {"role", "target", "position"}:
                return _invalid(endpoint_path)
            target = _parse_bound(endpoint_values["target"], f"{endpoint_path}.target")
            if isinstance(target, Failure):
                return target
            role = endpoint_values["role"]
            position = endpoint_values["position"]
            if not isinstance(role, str) or not role or (position is not None and (type(position) is not int or position < 0)):
                return _invalid(endpoint_path)
            endpoints.append(Endpoint(role, target, position))
        elements.append(Element(ref, dict(typed_attributes), tuple(endpoints)))
    return TopologyState(
        raw["profile_id"],
        raw["profile_version"],
        tuple(elements),
    )


topology_state_codec = define_codec(
    name="information-topology-state",
    discriminant="information_topology.state.v1",
    keys=("kind", "profile_id", "profile_version", "elements"),
    parse=_parse_state,
    to_wire=_state_wire,
)


# --- project-retrieval failure family -----------------------------------

ProjectRetrievalFailureCode = Literal[
    "MODE_INVALID",
    "PLAN_INVALID",
    "FORMALIZATION_INPUT_INVALID",
    "FORMALIZATION_RESPONSE_INVALID",
    "FORMALIZATION_PROPOSAL_INVALID",
    "FORMALIZATION_PROVIDER_FAILED",
    "PROJECT_MISMATCH",
    "MODE_NOT_FOUND",
    "MODE_VERSION_CONFLICT",
    "INVALID_PLAN",
    "INVALID_IDEMPOTENCY_KEY",
    "IDEMPOTENCY_CONFLICT",
    "PLAN_NOT_FOUND",
    "PLAN_BLOCKED",
    "DISPATCH_FAILED",
    "RUN_NOT_FOUND",
]

project_retrieval_failures = define_failure_family(
    "project_retrieval.failure", get_args(ProjectRetrievalFailureCode),
)


def retrieval_failure(
    code: ProjectRetrievalFailureCode,
    message: str,
    *,
    site: str,
    path: str | None = None,
    **details: Any,
) -> Failure:
    context: dict[str, Any] = {"site": site, **details}
    if path is not None:
        context["path"] = path
    return project_retrieval_failures.fail(code, message, context)


__all__ = [
    "CANDIDATE_BUNDLE_TYPE",
    "CANDIDATE_REQUEST_TYPE",
    "Candidate",
    "CandidateBundle",
    "CandidateOccurrence",
    "CandidateRequestFailure",
    "CandidateSearchRequest",
    "Element",
    "ElementRef",
    "Endpoint",
    "FlowEdge",
    "FlowEnd",
    "FlowExpression",
    "FlowIdentity",
    "FlowInterface",
    "FlowOccurrence",
    "FlowOperation",
    "FlowOperationBinding",
    "FlowPort",
    "FlowThen",
    "PatchOperation",
    "PortWire",
    "ProjectRetrievalFailureCode",
    "ProviderObservation",
    "raise_retrieval_contract_error",
    "RetrievalFlowAssemblyContext",
    "RetrievalFlowBinding",
    "RetrievalFlowDefinition",
    "RetrievalFlowSource",
    "TopologyState",
    "TopologyView",
    "ViewSpec",
    "assemble_retrieval_flow_definition",
    "lower_retrieval_flow_source",
    "project_retrieval_failures",
    "retrieval_failure",
    "topology_failures",
    "topology_state_codec",
]
