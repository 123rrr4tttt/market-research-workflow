"""Descriptive method signatures and explicit structural composition checks.

This module stores no executable function and never invokes a method. Compatibility
is a profile-level statement about declared input/output roles and preconditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, TypedDict, TypeGuard

from functorial_kit import Failure

from ..contracts import BoundRef, Element, Endpoint, TopologyState, topology_failures
from ..profiles import AttributeRule, EndpointRule, ProfileSpec, TypeRule, validate_state
from ..structural_schema import with_structural_attributes

METHOD_TYPE = "method"
METHOD_PROFILE_ID = "information_topology.method_description"
METHOD_PROFILE_VERSION = "1"


class PortWire(TypedDict):
    name: str
    type: str
    required: bool


def _method_constraint(state: TopologyState) -> Failure | None:
    for element in state.elements:
        if element.ref.ref.type_id != METHOD_TYPE:
            continue
        for key in ("inputs", "outputs"):
            value = element.attributes.get(key)
            if not _is_object_list(value):
                return topology_failures.fail("INVALID_STRUCTURE", f"{key} must be a list of role declarations", {"method": element.ref.ref.local_id, "path": key})
            names: set[str] = set()
            for index, raw_port in enumerate(value):
                port = _port_wire(raw_port)
                if port is None or port["name"] in names:
                    return topology_failures.fail("INVALID_STRUCTURE", "port declaration is malformed or duplicated", {"method": element.ref.ref.local_id, "path": f"{key}[{index}]"})
                names.add(port["name"])
        for key in ("preconditions", "assumptions", "composition_compatibility"):
            value = element.attributes.get(key, [])
            if not _is_non_empty_string_list(value):
                return topology_failures.fail("INVALID_STRUCTURE", f"{key} must contain descriptive strings", {"method": element.ref.ref.local_id, "path": key})
    return None


method_profile = ProfileSpec(
    METHOD_PROFILE_ID, METHOD_PROFILE_VERSION,
    with_structural_attributes({METHOD_TYPE: TypeRule(attributes={
        "name": AttributeRule("string", required=True),
        "inputs": AttributeRule("array", required=True),
        "outputs": AttributeRule("array", required=True),
        "preconditions": AttributeRule("array"),
        "assumptions": AttributeRule("array"),
        "composition_compatibility": AttributeRule("array"),
    }, endpoints={
        "implementation_reference": EndpointRule(frozenset({"implementation", "material", "document", "artifact"}), allow_external=True),
        "composes_after": EndpointRule(frozenset({METHOD_TYPE}), allow_external=True),
    })}), frozenset({METHOD_TYPE}), (_method_constraint,),
)


@dataclass(frozen=True, slots=True)
class Port:
    name: str
    type_id: str
    required: bool = True

    def wire(self) -> PortWire:
        return {"name": self.name, "type": self.type_id, "required": self.required}


def method_element(
    ref: BoundRef, name: str, *, inputs: tuple[Port, ...], outputs: tuple[Port, ...],
    preconditions: tuple[str, ...] = (), assumptions: tuple[str, ...] = (),
    composition_compatibility: tuple[str, ...] = (),
    implementation_reference: BoundRef | None = None,
    composes_after: tuple[BoundRef, ...] = (),
) -> Element:
    endpoints = tuple(
        [Endpoint("implementation_reference", implementation_reference)] if implementation_reference else []
    ) + tuple(Endpoint("composes_after", target, i) for i, target in enumerate(composes_after))
    return Element(ref, {
        "name": name, "inputs": [port.wire() for port in inputs], "outputs": [port.wire() for port in outputs],
        "preconditions": list(preconditions), "assumptions": list(assumptions),
        "composition_compatibility": list(composition_compatibility),
    }, endpoints)


@dataclass(frozen=True, slots=True)
class CompositionCheck:
    compatible: bool
    matched: tuple[tuple[str, str], ...]
    missing_required: tuple[str, ...]
    incompatible_types: tuple[tuple[str, str, str], ...]
    conditions: tuple[str, ...]


def _ports(element: Element, key: str) -> tuple[PortWire, ...]:
    raw = element.attributes.get(key, [])
    if not _is_object_list(raw):
        return ()
    return tuple(value for value in raw if _is_declared_port_mapping(value))


def check_composition(producer: Element, consumer: Element) -> CompositionCheck:
    """Check declared shape only; compatibility never means executable or proven."""
    outputs = {str(port["name"]): port for port in _ports(producer, "outputs")}
    inputs = _ports(consumer, "inputs")
    matched: list[tuple[str, str]] = []
    missing: list[str] = []
    mismatched: list[tuple[str, str, str]] = []
    for port in inputs:
        name = str(port["name"])
        source = outputs.get(name)
        if source is None:
            if port["required"]:
                missing.append(name)
            continue
        if source["type"] != port["type"]:
            mismatched.append((name, str(source["type"]), str(port["type"])))
        else:
            matched.append((name, name))
    # Both signatures can be locally coherent while semantic conditions remain unresolved.
    conditions = _string_tuple(consumer.attributes.get("preconditions", ())) + _string_tuple(
        consumer.attributes.get("assumptions", ())
    )
    return CompositionCheck(not missing and not mismatched, tuple(matched), tuple(missing), tuple(mismatched), conditions)


def validate_method_state(state: TopologyState) -> Failure | None:
    return validate_state(method_profile, state)


def declare_method_module() -> Mapping[str, object]:
    return {"module_id": "method", "profile": method_profile, "validate": validate_method_state, "check_composition": check_composition}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_object_sequence(value: object) -> TypeGuard[list[object] | tuple[object, ...]]:
    return isinstance(value, (list, tuple))


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _port_wire(value: object) -> PortWire | None:
    if not _is_object_mapping(value) or set(value) != {"name", "type", "required"}:
        return None
    name, type_id, required = value["name"], value["type"], value["required"]
    if not isinstance(name, str) or not name or not isinstance(type_id, str) or not type_id or type(required) is not bool:
        return None
    return {"name": name, "type": type_id, "required": required}


def _is_declared_port_mapping(value: object) -> TypeGuard[PortWire]:
    """Preserve the composition reader's original dict-only dynamic guard."""
    return isinstance(value, dict)


def _is_non_empty_string_list(value: object) -> bool:
    return _is_object_list(value) and all(isinstance(item, str) and bool(item) for item in value)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not _is_object_sequence(value):
        return ()
    return tuple(str(item) for item in value)
