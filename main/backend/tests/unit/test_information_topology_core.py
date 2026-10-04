from __future__ import annotations

import json
from dataclasses import replace

from functorial_kit import Failure

from app.services.information_topology import (
    AttributeRule,
    BoundRef,
    Correspondence,
    Element,
    ElementRef,
    Endpoint,
    EndpointRule,
    MappingSpec,
    PatchOperation,
    ProfileSpec,
    TopologyState,
    TypeRule,
    ViewSpec,
    apply_patch,
    decode_state,
    encode_state,
    preview_mapping,
    project_view,
    topology_failures,
    topology_state_codec,
    validate_state,
)
from app.services.information_topology.structural_schema import with_structural_attributes


def ref(type_id: str, local_id: str, revision: str = "1") -> BoundRef:
    return BoundRef(ElementRef("project-a", "report", "outline-1", type_id, local_id), revision)


def report_constraint(state: TopologyState) -> Failure | None:
    sections = {element.ref: element for element in state.elements if element.ref.ref.type_id == "section"}
    roots = [item.ref for item in sections.values() if item.attributes["root"]]
    if len(roots) != 1:
        return topology_failures.fail("INVALID_STRUCTURE", "one synthetic root is required")
    parents: dict[BoundRef, BoundRef] = {}
    sibling_positions: set[tuple[BoundRef, int]] = set()
    for relation in (item for item in state.elements if item.ref.ref.type_id == "parent"):
        parent = next(point.target for point in relation.endpoints if point.role == "parent")
        child_point = next(point for point in relation.endpoints if point.role == "child")
        child = child_point.target
        if child in parents:
            return topology_failures.fail("INVALID_STRUCTURE", "section has multiple parents")
        sibling_position = (parent, child_point.position)
        if sibling_position in sibling_positions:
            return topology_failures.fail("INVALID_STRUCTURE", "sibling position is duplicated")
        sibling_positions.add(sibling_position)
        parents[child] = parent
    root = roots[0]
    if root in parents or set(parents) != set(sections) - {root}:
        return topology_failures.fail("INVALID_STRUCTURE", "parent coverage differs from single-root tree")
    for section in sections:
        visited: set[BoundRef] = set()
        cursor = section
        while cursor != root:
            if cursor in visited or cursor not in parents:
                return topology_failures.fail("INVALID_STRUCTURE", "report outline has a cycle")
            visited.add(cursor)
            cursor = parents[cursor]
    return None


REPORT = ProfileSpec(
    "report.outline", "1",
    types={
        "section": TypeRule(attributes={"root": AttributeRule("boolean", required=True)}),
        "parent": TypeRule(endpoints={
            "parent": EndpointRule(frozenset({"section"}), 1, 1),
            "child": EndpointRule(frozenset({"section"}), 1, 1, ordered=True),
        }),
    },
    relation_types=frozenset({"parent"}),
    constraints=(report_constraint,),
)


def report_state() -> TopologyState:
    root, first, second = ref("section", "root"), ref("section", "a"), ref("section", "b")
    return TopologyState("report.outline", "1", (
        Element(root, {"root": True}), Element(first, {"root": False}), Element(second, {"root": False}),
        Element(ref("parent", "root-a"), endpoints=(Endpoint("parent", root), Endpoint("child", first, 0))),
        Element(ref("parent", "a-b"), endpoints=(Endpoint("parent", first), Endpoint("child", second, 0))),
    ))


EVIDENCE = ProfileSpec(
    "evidence.network", "1",
    types={
        "material": TypeRule(attributes={"title": AttributeRule("string", required=True)}),
        "judgment": TypeRule(endpoints={
            "subject": EndpointRule(frozenset({"material", "judgment"}), 1, 2),
            "object": EndpointRule(frozenset({"material", "judgment"}), 1, 1),
        }),
        "support": TypeRule(endpoints={
            "material": EndpointRule(frozenset({"material"}), 1, 1),
            "judgment": EndpointRule(frozenset({"judgment"}), 1, 1),
        }),
    },
    relation_types=frozenset({"judgment", "support"}),
)


def evidence_state() -> TopologyState:
    material = ref("material", "m")
    judgment_a, judgment_b = ref("judgment", "a"), ref("judgment", "b")
    return TopologyState("evidence.network", "1", (
        Element(material, {"title": "archive"}),
        Element(judgment_a, endpoints=(
            Endpoint("subject", material), Endpoint("subject", material), Endpoint("object", judgment_b),
        )),
        Element(judgment_b, endpoints=(Endpoint("subject", judgment_a), Endpoint("object", material))),
        Element(ref("support", "q"), endpoints=(Endpoint("material", material), Endpoint("judgment", judgment_a))),
    ))


def test_structural_overlay_is_project_bound_not_core_protocol():
    base = evidence_state()
    material = base.elements[0]
    enhanced = replace(
        material,
        attributes={
            **material.attributes,
            "content_name": "archive",
            "content_summary": "source document",
            "content_order": 0,
            "structural_role": "member",
            "source_uri": "https://example.test/archive",
            "source_status": "active",
        },
    )
    state = replace(base, elements=(enhanced, *base.elements[1:]))
    # The facility protocol stays closed: undeclared structural fields are invalid.
    assert validate_state(EVIDENCE, state).code == "INVALID_STRUCTURE"

    # A project/module binding opts in explicitly; the core does not change.
    bound = ProfileSpec(
        EVIDENCE.profile_id, EVIDENCE.version,
        with_structural_attributes(EVIDENCE.types),
        EVIDENCE.relation_types, EVIDENCE.constraints,
    )
    assert validate_state(bound, state) is None

    invalid = replace(enhanced, attributes={**enhanced.attributes, "content_order": "0"})
    assert validate_state(bound, replace(base, elements=(invalid, *base.elements[1:]))).code == "INVALID_STRUCTURE"


def test_report_tree_rejects_multiple_parents_and_cycle() -> None:
    state = report_state()
    assert validate_state(REPORT, state) is None
    root, first, second = state.elements[:3]
    duplicate_parent = Element(ref("parent", "root-b"), endpoints=(
        Endpoint("parent", root.ref), Endpoint("child", second.ref, 1),
    ))
    failure = validate_state(REPORT, replace(state, elements=state.elements + (duplicate_parent,)))
    assert isinstance(failure, Failure) and failure.code == "INVALID_STRUCTURE"
    cyclic = Element(ref("parent", "b-root"), endpoints=(
        Endpoint("parent", second.ref), Endpoint("child", root.ref, 0),
    ))
    failure = validate_state(REPORT, replace(state, elements=state.elements + (cyclic,)))
    assert isinstance(failure, Failure) and failure.code == "INVALID_STRUCTURE"


def test_relation_to_relation_duplicate_endpoints_and_finite_cycle_round_trip() -> None:
    state = evidence_state()
    assert validate_state(EVIDENCE, state) is None
    wire = json.loads(topology_state_codec.serialize(state))
    assert wire == encode_state(EVIDENCE, state)
    decoded = decode_state(EVIDENCE, wire)
    assert decoded == state
    assert decoded.elements[1].endpoints[0] == decoded.elements[1].endpoints[1]
    assert decoded.elements[1].endpoints[2].target == decoded.elements[2].ref
    assert decode_state(REPORT, wire).code == "UNKNOWN_PROFILE"
    assert decode_state(EVIDENCE, {**wire, "unexpected": True}).code == "INVALID_WIRE_FORMAT"


def test_stable_identity_and_observed_revision_are_separate() -> None:
    old = ref("section", "a", "1")
    fresh = ref("section", "a", "2")
    assert old.ref == fresh.ref and old != fresh
    state = report_state()
    assert apply_patch(REPORT, state, ()) is state
    result = apply_patch(REPORT, state, (PatchOperation("replace", old, Element(fresh, {"root": False})),))
    assert isinstance(result, Failure) and result.code == "INVALID_STRUCTURE"
    assert state.elements[1].ref == old


def test_patch_validation_is_atomic_and_unknown_profile_rejected() -> None:
    state = report_state()
    invalid = Element(ref("section", "new"), {"root": False})
    result = apply_patch(REPORT, state, (PatchOperation("add", invalid.ref, invalid),))
    assert isinstance(result, Failure) and result.code == "INVALID_STRUCTURE"
    assert len(state.elements) == 5
    assert validate_state(REPORT, replace(state, profile_version="2")).code == "UNKNOWN_PROFILE"
    assert apply_patch(REPORT, state, (PatchOperation("replace", ref("section", "a", "old"), invalid),)).code == "VERSION_CONFLICT"


def test_mapping_coverage_and_fidelity_are_independent() -> None:
    state = evidence_state()
    source = state.elements[:2]
    def transform(_: TopologyState) -> tuple[TopologyState, tuple[Correspondence, ...]]:
        return state, (Correspondence(source[0].ref, (source[0].ref,)),)
    base = MappingSpec("self", "evidence.network", "1", "evidence.network", "1",
                       lambda _: (source[0].ref, source[1].ref), transform, "lossless",
                       lambda a, b, pairs: a == b and all(pair.source in pair.targets for pair in pairs))
    preview = preview_mapping(base, EVIDENCE, EVIDENCE, state)
    assert preview.coverage == "partial"
    assert preview.unmapped == (source[1].ref,)
    assert preview.fidelity == "unverified"
    complete = replace(base, transform=lambda _: (state, (
        Correspondence(source[0].ref, (source[0].ref,)),
        Correspondence(source[1].ref, (source[1].ref,)),
    )))
    verified = preview_mapping(complete, EVIDENCE, EVIDENCE, state)
    assert verified.coverage == "total" and verified.fidelity == "lossless"
    assert preview_mapping(replace(complete, observation_witness=None), EVIDENCE, EVIDENCE, state).fidelity == "unverified"
    assert preview_mapping(replace(complete, fidelity_claim="lossy"), EVIDENCE, EVIDENCE, state).fidelity == "lossy"


def test_new_profile_is_data_not_core_enum() -> None:
    new = ProfileSpec("method.signature", "42", {"parameter": TypeRule()}, frozenset())
    state = TopologyState("method.signature", "42", (Element(ref("parameter", "x")),))
    assert validate_state(new, state) is None
    assert validate_state(REPORT, state).code == "UNKNOWN_PROFILE"


def test_view_projection_retains_bound_origins_and_input_revision() -> None:
    state = evidence_state()
    judgment = state.elements[1].ref
    spec = ViewSpec("evidence-as-node", "1", "evidence.network", "1",
                    lambda _: ((judgment,), (judgment,), {"layout": "abstract"}))
    view = project_view(EVIDENCE, state, spec, {"evidence-state": "7"})
    assert view.members == view.relations == (judgment,)
    assert view.input_revisions == {"evidence-state": "7"}
    absent = ref("judgment", "absent")
    invalid = replace(spec, project=lambda _: ((absent,), (), {}))
    assert project_view(EVIDENCE, state, invalid, {"evidence-state": "7"}).code == "INVALID_STRUCTURE"


def test_role_signature_and_project_boundary_are_checked() -> None:
    state = evidence_state()
    relation = state.elements[1]
    missing_subject = replace(relation, endpoints=tuple(point for point in relation.endpoints if point.role != "subject"))
    assert validate_state(EVIDENCE, replace(state, elements=(state.elements[0], missing_subject) + state.elements[2:])).code == "INVALID_STRUCTURE"
    foreign = BoundRef(replace(state.elements[0].ref.ref, project_key="project-b"), "1")
    foreign_relation = replace(relation, endpoints=(Endpoint("subject", foreign),) + relation.endpoints[1:])
    assert validate_state(EVIDENCE, replace(state, elements=(state.elements[0], foreign_relation) + state.elements[2:])).code == "INVALID_STRUCTURE"
