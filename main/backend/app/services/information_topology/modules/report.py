"""Report outline as an ordered, single-root local topology.

Report structure owns outline facts only. Body text and its revisions remain with
the writing module; this module records observations and can only flag drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from functorial_kit import Failure

from ..contracts import BoundRef, Element, ElementRef, Endpoint, PatchOperation, TopologyState, topology_failures
from ..profiles import AttributeRule, EndpointRule, ProfileSpec, TypeRule, apply_patch, validate_state
from ..structural_schema import with_structural_attributes

ROOT_TYPE = "outline_root"
SECTION_TYPE = "section"
REPORT_PROFILE_ID = "information_topology.report_outline"
REPORT_PROFILE_VERSION = "1"


def _outline_constraint(state: TopologyState) -> Failure | None:
    roots = [e for e in state.elements if e.ref.ref.type_id == ROOT_TYPE]
    sections = [e for e in state.elements if e.ref.ref.type_id == SECTION_TYPE]
    if len(roots) != 1:
        return topology_failures.fail("INVALID_STRUCTURE", "outline must contain exactly one synthetic root", {"path": "elements"})
    root = roots[0]
    children: dict[BoundRef, list[tuple[int, BoundRef]]] = {root.ref: []}
    section_refs = {s.ref for s in sections}
    for section in sections:
        parents = [ep for ep in section.endpoints if ep.role == "parent"]
        if len(parents) != 1:
            return topology_failures.fail("INVALID_STRUCTURE", "each section must have exactly one parent", {"section": section.ref.ref.local_id})
        parent = parents[0].target
        if parent != root.ref and parent not in section_refs:
            return topology_failures.fail("INVALID_STRUCTURE", "section parent is outside this outline", {"section": section.ref.ref.local_id})
        order = section.attributes.get("order")
        if type(order) is not int or order < 0:
            return topology_failures.fail("INVALID_STRUCTURE", "section order must be a nonnegative integer", {"section": section.ref.ref.local_id})
        children.setdefault(parent, []).append((order, section.ref))
        children.setdefault(section.ref, [])
    for parent, entries in children.items():
        positions = sorted(order for order, _ in entries)
        if positions != list(range(len(entries))):
            return topology_failures.fail("INVALID_STRUCTURE", "sibling order must be unique and contiguous", {"parent": parent.ref.local_id})
    # Parent pointers form a finite function; every section must terminate at root.
    parent_of = {s.ref: next(ep.target for ep in s.endpoints if ep.role == "parent") for s in sections}
    for section in sections:
        seen: set[BoundRef] = set()
        cursor = section.ref
        while cursor != root.ref:
            if cursor in seen:
                return topology_failures.fail("INVALID_STRUCTURE", "outline parent relation contains a cycle", {"section": section.ref.ref.local_id})
            seen.add(cursor)
            if cursor not in parent_of:
                return topology_failures.fail("INVALID_STRUCTURE", "section is disconnected from synthetic root", {"section": section.ref.ref.local_id})
            cursor = parent_of[cursor]
    return None


report_profile = ProfileSpec(
    REPORT_PROFILE_ID, REPORT_PROFILE_VERSION,
    with_structural_attributes({
        ROOT_TYPE: TypeRule(attributes={"hidden": AttributeRule("boolean", required=True)}),
        SECTION_TYPE: TypeRule(
            attributes={
                "title": AttributeRule("string", required=True),
                "order": AttributeRule("integer", required=True),
                "body_version": AttributeRule("string"),
                "body_digest": AttributeRule("string"),
            },
            endpoints={
                "parent": EndpointRule(frozenset({ROOT_TYPE, SECTION_TYPE}), min_count=1, max_count=1),
                "argument": EndpointRule(frozenset({"judgment", "evidence", "claim", "argument", "method"}), ordered=True, allow_external=True),
            },
        ),
    }), frozenset({SECTION_TYPE}), (_outline_constraint,),
)


def empty_outline(project_key: str, outline_id: str = "report") -> TopologyState:
    """Return the canonical empty outline: its synthetic root is not display content."""
    root = BoundRef(ElementRef(project_key, "report", "outline", ROOT_TYPE, outline_id), "0")
    return TopologyState(REPORT_PROFILE_ID, REPORT_PROFILE_VERSION, (Element(root, {"hidden": True}),))


def section_element(
    ref: BoundRef, parent: BoundRef, title: str, order: int,
    *, arguments: tuple[BoundRef, ...] = (), body_version: str | None = None,
    body_digest: str | None = None,
) -> Element:
    attrs: dict[str, object] = {"title": title, "order": order}
    if body_version is not None:
        attrs["body_version"] = body_version
    if body_digest is not None:
        attrs["body_digest"] = body_digest
    endpoints = (Endpoint("parent", parent),) + tuple(Endpoint("argument", item, i) for i, item in enumerate(arguments))
    return Element(ref, attrs, endpoints)


def read_view(state: TopologyState) -> tuple[Element, ...] | Failure:
    failure = validate_state(report_profile, state)
    if failure:
        return failure
    root = next(e.ref for e in state.elements if e.ref.ref.type_id == ROOT_TYPE)
    by_parent: dict[BoundRef, list[Element]] = {}
    for element in state.elements:
        if element.ref.ref.type_id == SECTION_TYPE:
            parent = next(ep.target for ep in element.endpoints if ep.role == "parent")
            by_parent.setdefault(parent, []).append(element)
    result: list[Element] = []
    def visit(parent: BoundRef) -> None:
        for item in sorted(by_parent.get(parent, ()), key=lambda e: e.attributes["order"]):
            result.append(item)
            visit(item.ref)
    visit(root)
    return tuple(result)


def apply_outline_patch(state: TopologyState, operations: tuple[PatchOperation, ...]) -> TopologyState | Failure:
    return apply_patch(report_profile, state, operations)


def move_section(state: TopologyState, section: BoundRef, new_parent: BoundRef, order: int) -> TopologyState | Failure:
    failure = validate_state(report_profile, state)
    if failure:
        return failure
    target = next((e for e in state.elements if e.ref == section and e.ref.ref.type_id == SECTION_TYPE), None)
    if target is None:
        return topology_failures.fail("NOT_FOUND", "section does not exist in outline", {"section": section.ref.local_id})
    old_parent = next(ep.target for ep in target.endpoints if ep.role == "parent")
    siblings: dict[BoundRef, list[Element]] = {}
    for item in state.elements:
        if item.ref.ref.type_id == SECTION_TYPE and item.ref != section:
            parent = next(ep.target for ep in item.endpoints if ep.role == "parent")
            siblings.setdefault(parent, []).append(item)
    destinations = siblings.setdefault(new_parent, [])
    if new_parent != old_parent and any(e.ref == new_parent for e in (target,)):
        return topology_failures.fail("INVALID_STRUCTURE", "section cannot parent itself", {"section": section.ref.local_id})
    if new_parent.ref.type_id not in {ROOT_TYPE, SECTION_TYPE} or (new_parent.ref.type_id == SECTION_TYPE and new_parent not in {e.ref for e in state.elements}):
        return topology_failures.fail("INVALID_STRUCTURE", "new parent is not in outline", {"parent": new_parent.ref.local_id})
    if order < 0 or order > len(destinations):
        return topology_failures.fail("INVALID_PATCH", "destination order is outside sibling range", {"order": order})
    old_siblings = siblings.setdefault(old_parent, [])
    old_sorted = sorted(old_siblings, key=lambda e: e.attributes["order"])
    new_sorted = sorted(destinations, key=lambda e: e.attributes["order"])
    new_sorted.insert(order, target)
    operations: list[PatchOperation] = []
    for idx, item in enumerate(old_sorted):
        operations.append(PatchOperation("replace", item.ref, Element(item.ref, {**item.attributes, "order": idx}, item.endpoints)))
    for idx, item in enumerate(new_sorted):
        if item.ref == section:
            endpoints = tuple(Endpoint(ep.role, new_parent if ep.role == "parent" else ep.target, ep.position) for ep in item.endpoints)
            updated = Element(item.ref, {**item.attributes, "order": idx}, endpoints)
        else:
            updated = Element(item.ref, {**item.attributes, "order": idx}, item.endpoints)
        operations.append(PatchOperation("replace", item.ref, updated))
    return apply_patch(report_profile, state, tuple(operations))


@dataclass(frozen=True, slots=True)
class BodyDrift:
    section: BoundRef
    drifted: bool
    expected_version: str | None
    observed_version: str
    expected_digest: str | None
    observed_digest: str | None


def observe_body(section: Element, *, version: str, digest: str | None) -> BodyDrift:
    """Compare a recorded body observation without reading or changing writing content."""
    expected_version = section.attributes.get("body_version")
    expected_digest = section.attributes.get("body_digest")
    return BodyDrift(section.ref, expected_version != version or (expected_digest is not None and expected_digest != digest), expected_version, version, expected_digest, digest)


def declare_report_module() -> Mapping[str, object]:
    return {"module_id": "report", "profile": report_profile, "read_view": read_view, "apply_patch": apply_outline_patch}
