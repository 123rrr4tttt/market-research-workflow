"""Read-only structural representation of one retrieval method definition.

The profile is deliberately separate from the descriptive ``method`` profile.
It records typed ports, occurrence multiplicity, wiring and ordered control, but
never binds or invokes a handler.
"""

from __future__ import annotations

from typing import Any

from functorial_kit import Failure

from app.successor_runtime.capabilities.retrieval_flow_native import (
    FlowEnd, RetrievalFlowDefinition,
)

from ..contracts import BoundRef, Element, ElementRef, Endpoint, TopologyState, topology_failures
from ..profiles import AttributeRule, EndpointRule, ProfileSpec, TypeRule, validate_state


METHOD_FLOW_PROFILE_ID = "information_topology.retrieval_method_flow"
METHOD_FLOW_PROFILE_VERSION = "1"
BOUNDARY = "flow_boundary"
OCCURRENCE = "flow_occurrence"
WIRE = "flow_wire"
CONTROL = "flow_control"


def _type_wire(value: Any) -> dict[str, str]:
    return {
        "type_id": value.type_id,
        "schema_version": value.schema_version,
        "codec_id": value.codec_id,
        "canonical_codec_version": value.canonical_codec_version,
    }


def _port_wire(ports: Any) -> list[dict[str, object]]:
    return [{"name": port.name, "object_type": _type_wire(port.object_type)} for port in ports]


def _invalid(path: str, message: str) -> Failure:
    return topology_failures.fail("INVALID_STRUCTURE", message, {"path": path})


def _ports(element: Element, key: str) -> dict[str, object] | None:
    raw = element.attributes.get(key)
    if not isinstance(raw, list):
        return None
    result: dict[str, object] = {}
    for port in raw:
        if not isinstance(port, dict) or set(port) != {"name", "object_type"}:
            return None
        name, object_type = port["name"], port["object_type"]
        if not isinstance(name, str) or not name or name in result or not isinstance(object_type, dict) or set(object_type) != {
            "type_id", "schema_version", "codec_id", "canonical_codec_version"
        } or any(not isinstance(value, str) or not value for value in object_type.values()):
            return None
        result[name] = object_type
    return result


def _flow_constraint(state: TopologyState) -> Failure | None:
    boundaries = [element for element in state.elements if element.ref.ref.type_id == BOUNDARY]
    occurrences = [element for element in state.elements if element.ref.ref.type_id == OCCURRENCE]
    wires = [element for element in state.elements if element.ref.ref.type_id == WIRE]
    controls = [element for element in state.elements if element.ref.ref.type_id == CONTROL]
    if len(boundaries) != 2 or {item.attributes.get("role") for item in boundaries} != {"input", "output"}:
        return _invalid("elements", "one input and one output boundary required")
    by_ref = {element.ref: element for element in state.elements}
    for element in boundaries + occurrences:
        for key in ("inputs", "outputs"):
            if _ports(element, key) is None:
                return _invalid(f"{element.ref.ref.local_id}.{key}", "malformed typed port family")
    orders = sorted(item.attributes.get("order") for item in occurrences if type(item.attributes.get("order")) is int)
    if len(orders) != len(occurrences) or orders != list(range(len(occurrences))):
        return _invalid("occurrences", "occurrence order must be unique and contiguous")
    for item in occurrences:
        attrs = item.attributes
        if attrs.get("control_kind") not in {"atomic", "macro"}:
            return _invalid(item.ref.ref.local_id, "invalid control boundary")
        if attrs["control_kind"] == "macro" and not attrs.get("entrypoint_ref"):
            return _invalid(item.ref.ref.local_id, "macro requires external entrypoint")
        definition = [end.target for end in item.endpoints if end.role == "operation_definition"]
        if len(definition) != 1 or definition[0].ref.local_id != attrs.get("operation_id") or definition[0].observed_revision != attrs.get("operation_version"):
            return _invalid(item.ref.ref.local_id, "operation identity/version reference drift")
    input_boundary = next(item for item in boundaries if item.attributes["role"] == "input")
    output_boundary = next(item for item in boundaries if item.attributes["role"] == "output")
    if (input_boundary.attributes["flow_id"], input_boundary.attributes["flow_version"]) != (
        output_boundary.attributes["flow_id"], output_boundary.attributes["flow_version"]
    ) or input_boundary.ref.observed_revision != output_boundary.ref.observed_revision:
        return _invalid("boundaries", "flow identity/version boundary drift")
    seen_wires: set[tuple[BoundRef, str, BoundRef, str]] = set()
    used_sources: list[tuple[BoundRef, str]] = []
    used_targets: list[tuple[BoundRef, str]] = []
    for wire in wires:
        endpoints = {end.role: end.target for end in wire.endpoints}
        if set(endpoints) != {"source", "target"}:
            return _invalid(wire.ref.ref.local_id, "wire needs source and target")
        source = by_ref.get(endpoints["source"])
        target = by_ref.get(endpoints["target"])
        if source is None or target is None:
            return _invalid(wire.ref.ref.local_id, "wire endpoint missing")
        source_port = wire.attributes.get("source_port")
        target_port = wire.attributes.get("target_port")
        source_ports = _ports(source, "outputs")
        target_ports = _ports(target, "inputs")
        if (source not in occurrences and source != input_boundary) or (target not in occurrences and target != output_boundary):
            return _invalid(wire.ref.ref.local_id, "wire direction invalid")
        if source_port not in source_ports or target_port not in target_ports or source_ports[source_port] != target_ports[target_port]:
            return _invalid(wire.ref.ref.local_id, "wire endpoint ObjectType mismatch")
        signature = (source.ref, source_port, target.ref, target_port)
        if signature in seen_wires:
            return _invalid(wire.ref.ref.local_id, "duplicate wire")
        seen_wires.add(signature)
        used_sources.append((source.ref, source_port))
        used_targets.append((target.ref, target_port))
    expected_sources = {(item.ref, name) for item in [input_boundary, *occurrences]
                        for name in _ports(item, "outputs")}
    expected_targets = {(item.ref, name) for item in [*occurrences, output_boundary]
                        for name in _ports(item, "inputs")}
    if set(used_sources) != expected_sources or set(used_targets) != expected_targets or (
        len(used_sources) != len(expected_sources) or len(used_targets) != len(expected_targets)
    ):
        return _invalid("wires", "every typed port must have exactly one wire")
    by_order = sorted(occurrences, key=lambda item: item.attributes["order"])
    expected_controls = {(left.ref, right.ref) for left, right in zip(by_order, by_order[1:])}
    actual_controls = {
        (next(end.target for end in item.endpoints if end.role == "before"),
         next(end.target for end in item.endpoints if end.role == "after"))
        for item in controls
    }
    if actual_controls != expected_controls or len(controls) != len(expected_controls):
        return _invalid("controls", "ordered control edge drift")
    return None


method_flow_profile = ProfileSpec(
    METHOD_FLOW_PROFILE_ID, METHOD_FLOW_PROFILE_VERSION,
    {
        BOUNDARY: TypeRule(attributes={
            "role": AttributeRule("string", True), "flow_id": AttributeRule("string", True),
            "flow_version": AttributeRule("string", True), "inputs": AttributeRule("array", True),
            "outputs": AttributeRule("array", True),
        }),
        OCCURRENCE: TypeRule(attributes={
            "order": AttributeRule("integer", True), "operation_id": AttributeRule("string", True),
            "operation_version": AttributeRule("string", True), "inputs": AttributeRule("array", True),
            "outputs": AttributeRule("array", True), "control_kind": AttributeRule("string", True),
            "effect_refs": AttributeRule("array", True), "failure_refs": AttributeRule("array", True),
            "authority_ref": AttributeRule("string", True), "stop_ref": AttributeRule("string", True),
            "entrypoint_ref": AttributeRule("string", True),
        }, endpoints={
            "operation_definition": EndpointRule(frozenset({"flow_operation_definition"}), 1, 1, allow_external=True),
        }),
        WIRE: TypeRule(attributes={
            "source_port": AttributeRule("string", True), "target_port": AttributeRule("string", True),
            "order": AttributeRule("integer", True),
        }, endpoints={
            "source": EndpointRule(frozenset({BOUNDARY, OCCURRENCE}), 1, 1),
            "target": EndpointRule(frozenset({BOUNDARY, OCCURRENCE}), 1, 1),
        }),
        CONTROL: TypeRule(attributes={"order": AttributeRule("integer", True)}, endpoints={
            "before": EndpointRule(frozenset({OCCURRENCE}), 1, 1),
            "after": EndpointRule(frozenset({OCCURRENCE}), 1, 1),
        }),
    }, frozenset({OCCURRENCE, WIRE, CONTROL}), (_flow_constraint,),
)


def project_retrieval_method_flow(definition: RetrievalFlowDefinition, project_key: str) -> TopologyState | Failure:
    """Derive a fresh local read model; this function owns no topology writes."""
    if not project_key:
        return topology_failures.fail("INVALID_STRUCTURE", "project_key must be nonempty", {"path": "project_key"})
    source = definition.source

    def ref(type_id: str, local_id: str) -> BoundRef:
        return BoundRef(ElementRef(project_key, "retrieval_method_flow", source.flow_id, type_id, local_id), source.version)

    input_ref, output_ref = ref(BOUNDARY, "input"), ref(BOUNDARY, "output")
    elements: list[Element] = [
        Element(input_ref, {"role": "input", "flow_id": source.flow_id, "flow_version": source.version,
                            "inputs": [], "outputs": _port_wire(definition.inputs.ports)}),
        Element(output_ref, {"role": "output", "flow_id": source.flow_id, "flow_version": source.version,
                             "inputs": _port_wire(definition.outputs.ports), "outputs": []}),
    ]
    occurrence_refs: dict[str, BoundRef] = {}
    for order, occurrence in enumerate(definition.occurrences):
        operation = occurrence.operation
        occurrence_ref = ref(OCCURRENCE, occurrence.occurrence_id)
        occurrence_refs[occurrence.occurrence_id] = occurrence_ref
        definition_ref = BoundRef(
            ElementRef(project_key, "retrieval_method_flow", "operation_definition", "flow_operation_definition", operation.operation_id),
            operation.version,
        )
        elements.append(Element(occurrence_ref, {
            "order": order, "operation_id": operation.operation_id, "operation_version": operation.version,
            "inputs": _port_wire(operation.inputs.ports), "outputs": _port_wire(operation.outputs.ports),
            "control_kind": operation.control_kind, "effect_refs": list(operation.effect_refs),
            "failure_refs": list(operation.failure_refs), "authority_ref": operation.authority_ref,
            "stop_ref": operation.stop_ref, "entrypoint_ref": operation.entrypoint_ref,
        }, (Endpoint("operation_definition", definition_ref),)))

    def endpoint_ref(end: FlowEnd) -> BoundRef:
        if end.role == "input":
            return input_ref
        if end.role == "output":
            return output_ref
        return occurrence_refs[end.occurrence_id]

    for order, edge in enumerate(definition.edges):
        elements.append(Element(ref(WIRE, f"wire:{order}"), {
            "source_port": edge.source.port, "target_port": edge.target.port, "order": order,
        }, (Endpoint("source", endpoint_ref(edge.source)), Endpoint("target", endpoint_ref(edge.target)))))
    for order, (before, after) in enumerate(zip(definition.occurrences, definition.occurrences[1:])):
        elements.append(Element(ref(CONTROL, f"control:{order}"), {"order": order}, (
            Endpoint("before", occurrence_refs[before.occurrence_id]),
            Endpoint("after", occurrence_refs[after.occurrence_id]),
        )))
    return TopologyState(METHOD_FLOW_PROFILE_ID, METHOD_FLOW_PROFILE_VERSION, tuple(elements))


def validate_retrieval_method_flow(state: TopologyState) -> Failure | None:
    return validate_state(method_flow_profile, state)


def structure_signature(state: TopologyState) -> tuple[object, ...] | Failure:
    """Compare local-ID renamings while preserving semantic refs and all order."""
    failure = validate_retrieval_method_flow(state)
    if failure is not None:
        return failure
    boundaries = {item.attributes["role"]: item for item in state.elements if item.ref.ref.type_id == BOUNDARY}
    occurrences = sorted((item for item in state.elements if item.ref.ref.type_id == OCCURRENCE), key=lambda item: item.attributes["order"])
    node_index = {item.ref: index for index, item in enumerate(occurrences)}

    def node(ref: BoundRef) -> tuple[str, int]:
        if ref == boundaries["input"].ref:
            return ("input", -1)
        if ref == boundaries["output"].ref:
            return ("output", -1)
        return ("occurrence", node_index[ref])

    operation_values = tuple((
        item.attributes["operation_id"], item.attributes["operation_version"],
        tuple((port["name"], tuple(sorted(port["object_type"].items()))) for port in item.attributes["inputs"]),
        tuple((port["name"], tuple(sorted(port["object_type"].items()))) for port in item.attributes["outputs"]),
        item.attributes["control_kind"], tuple(item.attributes["effect_refs"]),
        tuple(item.attributes["failure_refs"]), item.attributes["authority_ref"],
        item.attributes["stop_ref"], item.attributes["entrypoint_ref"],
        next(end.target for end in item.endpoints if end.role == "operation_definition"),
    ) for item in occurrences)
    wire_values = tuple(sorted((
        node(next(end.target for end in item.endpoints if end.role == "source")),
        item.attributes["source_port"],
        node(next(end.target for end in item.endpoints if end.role == "target")),
        item.attributes["target_port"],
    ) for item in state.elements if item.ref.ref.type_id == WIRE))
    return (
        boundaries["input"].ref, boundaries["output"].ref,
        boundaries["input"].attributes["flow_id"], boundaries["input"].attributes["flow_version"],
        tuple((port["name"], tuple(sorted(port["object_type"].items()))) for port in boundaries["input"].attributes["outputs"]),
        tuple((port["name"], tuple(sorted(port["object_type"].items()))) for port in boundaries["output"].attributes["inputs"]),
        operation_values, wire_values,
    )
