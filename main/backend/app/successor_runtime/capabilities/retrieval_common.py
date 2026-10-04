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
from typing import Any, Callable, Literal, Mapping, get_args

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
        if isinstance(self.keywords, (list, tuple)):
            object.__setattr__(self, "keywords", tuple(self.keywords))

    def validation_failure(self) -> CandidateRequestFailure | None:
        if not isinstance(self.topic, str) or not self.topic.strip():
            return CandidateRequestFailure("INVALID_TOPIC", "topic", "topic must be nonempty")
        if not isinstance(self.max_results, int) or self.max_results < 1:
            return CandidateRequestFailure("INVALID_LIMIT", "max_results", "max_results must be positive")
        if self.days_back is not None and (not isinstance(self.days_back, int) or self.days_back < 1):
            return CandidateRequestFailure("INVALID_DAYS_BACK", "days_back", "days_back must be positive")
        if self.start_offset is not None and (not isinstance(self.start_offset, int) or self.start_offset < 1):
            return CandidateRequestFailure("INVALID_OFFSET", "start_offset", "start_offset must be positive")
        if self.keywords is not None and (
            not isinstance(self.keywords, tuple)
            or any(not isinstance(term, str) for term in self.keywords)
        ):
            return CandidateRequestFailure("INVALID_KEYWORDS", "keywords", "keywords must be a sequence of search terms")
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
    raw: dict[str, Any] = field(default_factory=dict)


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


@dataclass(frozen=True, slots=True)
class RetrievalMethodIndexEntry:
    flow_id: str
    version: str
    inputs: FlowInterface
    outputs: FlowInterface
    operation_refs: tuple[tuple[str, str], ...]


def project_retrieval_method_index(definition: RetrievalFlowDefinition) -> RetrievalMethodIndexEntry | None:
    if not definition.source.indexed:
        return None
    return RetrievalMethodIndexEntry(
        definition.source.flow_id, definition.source.version,
        definition.inputs, definition.outputs,
        tuple((item.operation.operation_id, item.operation.version) for item in definition.occurrences),
    )


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
    attributes: Mapping[str, Any] = field(default_factory=dict)
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
    organization: Mapping[str, Any] = field(default_factory=dict)


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


def _parse_ref(raw: object, path: str) -> ElementRef | Failure:
    if not isinstance(raw, Mapping) or set(raw) != {
        "project_key", "module_id", "namespace", "type_id", "local_id"
    }:
        return _invalid(path)
    if any(not isinstance(raw[key], str) or not raw[key] for key in raw):
        return _invalid(path)
    return ElementRef(**raw)


def _parse_bound(raw: object, path: str) -> BoundRef | Failure:
    if not isinstance(raw, Mapping) or set(raw) != {"ref", "observed_revision", "content_digest"}:
        return _invalid(path)
    ref = _parse_ref(raw["ref"], f"{path}.ref")
    if isinstance(ref, Failure):
        return ref
    revision = raw["observed_revision"]
    digest = raw["content_digest"]
    if not isinstance(revision, str) or not revision or (digest is not None and not isinstance(digest, str)):
        return _invalid(path)
    return BoundRef(ref, revision, digest)


def _parse_state(raw: Mapping[str, Any]) -> TopologyState | Failure:
    if not isinstance(raw["profile_id"], str) or not raw["profile_id"]:
        return _invalid("profile_id")
    if not isinstance(raw["profile_version"], str) or not raw["profile_version"]:
        return _invalid("profile_version")
    source_elements = raw["elements"]
    if not isinstance(source_elements, list):
        return _invalid("elements")
    elements: list[Element] = []
    for index, item in enumerate(source_elements):
        path = f"elements[{index}]"
        if not isinstance(item, Mapping) or set(item) != {"ref", "attributes", "endpoints"}:
            return _invalid(path)
        ref = _parse_bound(item["ref"], f"{path}.ref")
        if isinstance(ref, Failure):
            return ref
        attributes = item["attributes"]
        if not isinstance(attributes, Mapping) or any(not isinstance(k, str) for k in attributes):
            return _invalid(f"{path}.attributes")
        source_endpoints = item["endpoints"]
        if not isinstance(source_endpoints, list):
            return _invalid(f"{path}.endpoints")
        endpoints: list[Endpoint] = []
        for endpoint_index, raw_endpoint in enumerate(source_endpoints):
            endpoint_path = f"{path}.endpoints[{endpoint_index}]"
            if not isinstance(raw_endpoint, Mapping) or set(raw_endpoint) != {"role", "target", "position"}:
                return _invalid(endpoint_path)
            target = _parse_bound(raw_endpoint["target"], f"{endpoint_path}.target")
            if isinstance(target, Failure):
                return target
            role = raw_endpoint["role"]
            position = raw_endpoint["position"]
            if not isinstance(role, str) or not role or (position is not None and (type(position) is not int or position < 0)):
                return _invalid(endpoint_path)
            endpoints.append(Endpoint(role, target, position))
        elements.append(Element(ref, dict(attributes), tuple(endpoints)))
    return TopologyState(raw["profile_id"], raw["profile_version"], tuple(elements))


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
    "RetrievalFlowAssemblyContext",
    "RetrievalFlowBinding",
    "RetrievalFlowDefinition",
    "RetrievalFlowSource",
    "RetrievalMethodIndexEntry",
    "TopologyState",
    "TopologyView",
    "ViewSpec",
    "assemble_retrieval_flow_definition",
    "lower_retrieval_flow_source",
    "project_retrieval_failures",
    "project_retrieval_method_index",
    "retrieval_failure",
    "topology_failures",
    "topology_state_codec",
]
