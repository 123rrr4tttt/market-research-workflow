"""Open, declarative profile validation and atomic in-memory structural patches."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from functorial_kit import Failure

from .contracts import (
    BoundRef, PatchOperation, TopologyState, TopologyView, ViewSpec, topology_failures,
    topology_state_codec,
)


@dataclass(frozen=True, slots=True)
class AttributeRule:
    value_type: str
    required: bool = False


@dataclass(frozen=True, slots=True)
class EndpointRule:
    target_types: frozenset[str]
    min_count: int = 0
    max_count: int | None = None
    ordered: bool = False
    allow_external: bool = False


@dataclass(frozen=True, slots=True)
class TypeRule:
    attributes: Mapping[str, AttributeRule] = field(default_factory=dict)
    endpoints: Mapping[str, EndpointRule] = field(default_factory=dict)
    allow_extra_attributes: bool = False
    # Declares which authored attribute carries this type's domain relation token.
    # Readers project the declared value into the structural read field
    # ``relation_token``; the attribute itself stays the single authored source.
    relation_token_attribute: str | None = None
    # Declares how this type appears in graph projections: an element that can be
    # a node, or a relation realized as an edge between two of its endpoints.
    # ``relation_axis`` names those two roles in source → target order.
    structural_role: str | None = None
    relation_axis: tuple[str, str] | None = None


Constraint = Callable[[TopologyState], Failure | None]


@dataclass(frozen=True, slots=True)
class ProfileSpec:
    """A module supplies these declarations and optional local constraints.

    No module type, relation type, or domain vocabulary is compiled into the core.
    """

    profile_id: str
    version: str
    types: Mapping[str, TypeRule]
    relation_types: frozenset[str]
    constraints: tuple[Constraint, ...] = ()


def _fail(message: str, path: str) -> Failure:
    return topology_failures.fail("INVALID_STRUCTURE", message, {"path": path})


def _json_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return value == value and value not in (float("inf"), float("-inf"))
    if isinstance(value, (list, tuple)):
        return all(_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _json_value(item) for key, item in value.items())
    return False


def _attribute_matches(value: Any, value_type: str) -> bool:
    return {
        "string": lambda: isinstance(value, str),
        "integer": lambda: type(value) is int,
        "number": lambda: (type(value) in (int, float)) and _json_value(value),
        "boolean": lambda: type(value) is bool,
        "object": lambda: isinstance(value, Mapping),
        "array": lambda: isinstance(value, (list, tuple)),
        "null": lambda: value is None,
        "any": lambda: _json_value(value),
    }.get(value_type, lambda: False)()


def validate_state(profile: ProfileSpec, state: TopologyState) -> Failure | None:
    if (state.profile_id, state.profile_version) != (profile.profile_id, profile.version):
        return topology_failures.fail(
            "UNKNOWN_PROFILE", "state profile identity or version is not registered",
            {"profile_id": state.profile_id, "profile_version": state.profile_version},
        )
    if not profile.profile_id or not profile.version or not profile.types:
        return _fail("profile declaration is incomplete", "profile")
    if not profile.relation_types <= profile.types.keys():
        return _fail("relation type is not declared", "profile.relation_types")
    allowed_attribute_types = {"string", "integer", "number", "boolean", "object", "array", "null", "any"}
    for type_id, rule in profile.types.items():
        if not type_id or (type_id not in profile.relation_types and rule.endpoints):
            return _fail("invalid type declaration", f"profile.types.{type_id}")
        if rule.relation_token_attribute is not None and rule.relation_token_attribute not in rule.attributes:
            return _fail("relation token attribute is not declared",
                         f"profile.types.{type_id}.relation_token_attribute")
        if rule.structural_role is not None and not rule.structural_role.strip():
            return _fail("structural role declaration is empty", f"profile.types.{type_id}.structural_role")
        if rule.relation_axis is not None:
            source_role, target_role = rule.relation_axis
            if rule.structural_role != "relation" or source_role == target_role:
                return _fail("relation axis requires a relation structural role with two distinct roles",
                             f"profile.types.{type_id}.relation_axis")
            if source_role not in rule.endpoints or target_role not in rule.endpoints:
                return _fail("relation axis role is not declared for this type",
                             f"profile.types.{type_id}.relation_axis")
        for attribute_name, attribute_rule in rule.attributes.items():
            if not attribute_name or attribute_rule.value_type not in allowed_attribute_types:
                return _fail("invalid attribute declaration", f"profile.types.{type_id}.attributes.{attribute_name}")
        for role, endpoint_rule in rule.endpoints.items():
            if (not role or not endpoint_rule.target_types or endpoint_rule.min_count < 0 or
                    (endpoint_rule.max_count is not None and endpoint_rule.max_count < endpoint_rule.min_count)):
                return _fail("invalid endpoint declaration", f"profile.types.{type_id}.endpoints.{role}")

    refs: set[BoundRef] = set()
    projects: set[str] = set()
    for index, element in enumerate(state.elements):
        path = f"elements[{index}]"
        ref = element.ref
        identity = ref.ref
        if not all((identity.project_key, identity.module_id, identity.namespace,
                    identity.type_id, identity.local_id, ref.observed_revision)):
            return _fail("reference identity and observed revision must be nonempty", f"{path}.ref")
        if ref in refs:
            return _fail("duplicate bound element reference", f"{path}.ref")
        refs.add(ref)
        projects.add(identity.project_key)
        type_rule = profile.types.get(identity.type_id)
        if type_rule is None:
            return _fail("element type is not declared by profile", f"{path}.ref.type_id")
        if identity.type_id not in profile.relation_types and element.endpoints:
            return _fail("nonrelation element has endpoints", f"{path}.endpoints")
        for name, attr_rule in type_rule.attributes.items():
            if attr_rule.required and name not in element.attributes:
                return _fail("required attribute missing", f"{path}.attributes.{name}")
        for name, value in element.attributes.items():
            if not isinstance(name, str) or not _json_value(value):
                return _fail("attribute is not JSON data", f"{path}.attributes")
            rule = type_rule.attributes.get(name)
            if rule is None:
                if not type_rule.allow_extra_attributes:
                    return _fail("attribute not declared by profile", f"{path}.attributes.{name}")
            elif not _attribute_matches(value, rule.value_type):
                return _fail("attribute has wrong type", f"{path}.attributes.{name}")
    if len(projects) > 1:
        return _fail("state contains multiple projects", "elements")

    for index, element in enumerate(state.elements):
        path = f"elements[{index}]"
        type_rule = profile.types[element.ref.ref.type_id]
        counts: dict[str, int] = {}
        positions: dict[str, set[int]] = {}
        for endpoint_index, endpoint in enumerate(element.endpoints):
            endpoint_path = f"{path}.endpoints[{endpoint_index}]"
            rule = type_rule.endpoints.get(endpoint.role)
            if rule is None:
                return _fail("endpoint role not declared for relation type", f"{endpoint_path}.role")
            if not endpoint.role or endpoint.target.ref.type_id not in rule.target_types:
                return _fail("endpoint target type does not match role", endpoint_path)
            if not endpoint.target.observed_revision or not all(
                (endpoint.target.ref.project_key, endpoint.target.ref.module_id,
                 endpoint.target.ref.namespace, endpoint.target.ref.local_id)
            ):
                return _fail("endpoint has incomplete bound reference", endpoint_path)
            if endpoint.target.ref.project_key != element.ref.ref.project_key:
                return _fail("cross-project endpoint", endpoint_path)
            if endpoint.target not in refs and not rule.allow_external:
                return _fail("local endpoint target is absent", endpoint_path)
            if endpoint.position is not None and (type(endpoint.position) is not int or endpoint.position < 0):
                return _fail("endpoint position must be a nonnegative integer", endpoint_path)
            if rule.ordered and endpoint.position is None:
                return _fail("ordered endpoint requires position", endpoint_path)
            if not rule.ordered and endpoint.position is not None:
                return _fail("unordered endpoint must not carry position", endpoint_path)
            counts[endpoint.role] = counts.get(endpoint.role, 0) + 1
            if endpoint.position is not None:
                role_positions = positions.setdefault(endpoint.role, set())
                if endpoint.position in role_positions:
                    return _fail("duplicate position within endpoint role", endpoint_path)
                role_positions.add(endpoint.position)
        for role, rule in type_rule.endpoints.items():
            count = counts.get(role, 0)
            if count < rule.min_count or (rule.max_count is not None and count > rule.max_count):
                return _fail("endpoint cardinality outside profile bounds", f"{path}.endpoints.{role}")
    for constraint in profile.constraints:
        failure = constraint(state)
        if failure is not None:
            return failure
    return None


def decode_state(profile: ProfileSpec, wire: object) -> TopologyState | Failure:
    """Decode and validate against an explicitly selected profile/version."""

    parsed = topology_state_codec.parse(wire)
    if isinstance(parsed, Failure):
        return topology_failures.fail("INVALID_WIRE_FORMAT", parsed.message, parsed.context)
    failure = validate_state(profile, parsed)
    return failure if failure is not None else parsed


def encode_state(profile: ProfileSpec, state: TopologyState) -> Mapping[str, Any] | Failure:
    """Only validated states may be emitted as topology wire data."""

    failure = validate_state(profile, state)
    return failure if failure is not None else topology_state_codec.to_wire(state)


def project_view(
    profile: ProfileSpec,
    state: TopologyState,
    spec: ViewSpec,
    input_revisions: Mapping[str, str],
) -> TopologyView | Failure:
    """Derive a view whose membership and observed versions remain tied to its input."""

    failure = validate_state(profile, state)
    if failure is not None:
        return failure
    if (spec.profile_id, spec.profile_version) != (profile.profile_id, profile.version):
        return topology_failures.fail("UNKNOWN_PROFILE", "view profile identity or version differs")
    if not spec.definition_id or not spec.definition_version or any(
        not isinstance(key, str) or not key or not isinstance(value, str) or not value
        for key, value in input_revisions.items()
    ):
        return topology_failures.fail("INVALID_STRUCTURE", "view definition or input revisions are incomplete")
    members, relations, organization = spec.project(state)
    available = {element.ref for element in state.elements}
    relation_refs = {element.ref for element in state.elements if element.ref.ref.type_id in profile.relation_types}
    if any(ref not in available for ref in members) or any(ref not in relation_refs for ref in relations):
        return topology_failures.fail("INVALID_STRUCTURE", "view references are not present in input state")
    if not _json_value(organization):
        return topology_failures.fail("INVALID_STRUCTURE", "view organization is not JSON data")
    return TopologyView(spec.definition_id, spec.definition_version, dict(input_revisions),
                        tuple(members), tuple(relations), dict(organization))


def apply_patch(
    profile: ProfileSpec,
    state: TopologyState,
    operations: tuple[PatchOperation, ...],
) -> TopologyState | Failure:
    """Apply a whole batch to a candidate, validating before returning any change."""

    initial_failure = validate_state(profile, state)
    if initial_failure is not None:
        return initial_failure
    if not operations:
        return state
    elements = list(state.elements)
    for index, operation in enumerate(operations):
        match = next((i for i, e in enumerate(elements) if e.ref == operation.ref), None)
        if operation.action == "add":
            if operation.element is None or operation.ref != operation.element.ref or match is not None:
                return topology_failures.fail("INVALID_PATCH", "invalid add operation", {"index": index})
            elements.append(operation.element)
        elif operation.action == "replace":
            if operation.element is None or match is None:
                return topology_failures.fail("VERSION_CONFLICT", "replacement base revision absent", {"index": index})
            if operation.element.ref.ref != operation.ref.ref:
                return topology_failures.fail("INVALID_PATCH", "replacement changes stable identity", {"index": index})
            elements[match] = operation.element
        elif operation.action == "remove":
            if operation.element is not None:
                return topology_failures.fail("INVALID_PATCH", "remove must not supply element", {"index": index})
            if match is None:
                return topology_failures.fail("VERSION_CONFLICT", "removal base revision absent", {"index": index})
            elements.pop(match)
        else:
            return topology_failures.fail("INVALID_PATCH", "unknown patch action", {"index": index})
    candidate = TopologyState(state.profile_id, state.profile_version, tuple(elements))
    failure = validate_state(profile, candidate)
    return failure if failure is not None else candidate
