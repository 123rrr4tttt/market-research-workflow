"""Descriptive method signatures and explicit structural composition checks.

This module stores no executable function and never invokes a method. Compatibility
is a profile-level statement about declared input/output roles and preconditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from functorial_kit import Failure

from ..contracts import BoundRef, Element, ElementRef, Endpoint, TopologyState, topology_failures
from ..profiles import AttributeRule, EndpointRule, ProfileSpec, TypeRule, validate_state
from ..structural_schema import with_structural_attributes

METHOD_TYPE = "method"
METHOD_PROFILE_ID = "information_topology.method_description"
METHOD_PROFILE_VERSION = "1"


def _method_constraint(state: TopologyState) -> Failure | None:
    for element in state.elements:
        if element.ref.ref.type_id != METHOD_TYPE:
            continue
        for key in ("inputs", "outputs"):
            value = element.attributes.get(key)
            if not isinstance(value, list):
                return topology_failures.fail("INVALID_STRUCTURE", f"{key} must be a list of role declarations", {"method": element.ref.ref.local_id, "path": key})
            names: set[str] = set()
            for index, port in enumerate(value):
                if (not isinstance(port, dict) or set(port) != {"name", "type", "required"}
                        or not isinstance(port["name"], str) or not port["name"]
                        or not isinstance(port["type"], str) or not port["type"]
                        or type(port["required"]) is not bool or port["name"] in names):
                    return topology_failures.fail("INVALID_STRUCTURE", "port declaration is malformed or duplicated", {"method": element.ref.ref.local_id, "path": f"{key}[{index}]"})
                names.add(port["name"])
        for key in ("preconditions", "assumptions", "composition_compatibility"):
            value = element.attributes.get(key, [])
            if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
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
        "implementation_reference": EndpointRule(frozenset({"implementation", "document", "artifact"}), allow_external=True),
        "composes_after": EndpointRule(frozenset({METHOD_TYPE}), allow_external=True),
    })}), frozenset({METHOD_TYPE}), (_method_constraint,),
)


@dataclass(frozen=True, slots=True)
class Port:
    name: str
    type_id: str
    required: bool = True

    def wire(self) -> dict[str, object]:
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


def _ports(element: Element, key: str) -> tuple[dict[str, object], ...]:
    raw = element.attributes.get(key, [])
    if not isinstance(raw, list):
        return ()
    return tuple(item for item in raw if isinstance(item, dict))


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
    conditions = tuple(str(item) for item in consumer.attributes.get("preconditions", ())) + tuple(
        str(item) for item in consumer.attributes.get("assumptions", ())
    )
    return CompositionCheck(not missing and not mismatched, tuple(matched), tuple(missing), tuple(mismatched), conditions)


def validate_method_state(state: TopologyState) -> Failure | None:
    return validate_state(method_profile, state)


def declare_method_module() -> Mapping[str, object]:
    return {"module_id": "method", "profile": method_profile, "validate": validate_method_state, "check_composition": check_composition}
