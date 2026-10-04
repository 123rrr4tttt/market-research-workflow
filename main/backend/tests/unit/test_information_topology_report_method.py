from app.services.information_topology.contracts import BoundRef, Element, ElementRef, Endpoint, PatchOperation, TopologyState
from app.services.information_topology.modules.method import Port, check_composition, method_element, method_profile, validate_method_state
from app.services.information_topology.modules.report import (
    REPORT_PROFILE_ID, REPORT_PROFILE_VERSION, SECTION_TYPE, apply_outline_patch,
    empty_outline, move_section, observe_body, read_view, report_profile, section_element,
)
from app.services.information_topology.profiles import validate_state


def ref(type_id: str, local_id: str, revision: str = "1") -> BoundRef:
    return BoundRef(ElementRef("p", "report", "test", type_id, local_id), revision)


def test_empty_outline_and_ordered_reorder_move_and_duplicate_argument_refs():
    state = empty_outline("p")
    root = state.elements[0].ref
    a, b, c = ref(SECTION_TYPE, "a"), ref(SECTION_TYPE, "b"), ref(SECTION_TYPE, "c")
    cited = ref("claim", "q")
    state = apply_outline_patch(state, (
        PatchOperation("add", a, section_element(a, root, "A", 0, arguments=(cited, cited))),
        PatchOperation("add", b, section_element(b, root, "B", 1)),
        PatchOperation("add", c, section_element(c, a, "C", 0)),
    ))
    assert isinstance(state, TopologyState)
    assert [item.attributes["title"] for item in read_view(state)] == ["A", "C", "B"]
    moved = move_section(state, c, root, 0)
    assert [item.attributes["title"] for item in read_view(moved)] == ["C", "A", "B"]
    a_after = next(item for item in moved.elements if item.ref == a)
    assert [ep.target for ep in a_after.endpoints if ep.role == "argument"] == [cited, cited]


def test_report_rejects_multi_parent_and_parent_cycle():
    state = empty_outline("p")
    root = state.elements[0].ref
    a, b = ref(SECTION_TYPE, "a"), ref(SECTION_TYPE, "b")
    a_node = section_element(a, root, "A", 0)
    b_node = section_element(b, a, "B", 0)
    multi = Element(a, a_node.attributes, a_node.endpoints + (Endpoint("parent", b),))
    candidate = TopologyState(REPORT_PROFILE_ID, REPORT_PROFILE_VERSION, (state.elements[0], multi, b_node))
    assert validate_state(report_profile, candidate) is not None
    cycle_a = section_element(a, b, "A", 0)
    cycle_b = section_element(b, a, "B", 0)
    candidate = TopologyState(REPORT_PROFILE_ID, REPORT_PROFILE_VERSION, (state.elements[0], cycle_a, cycle_b))
    assert validate_state(report_profile, candidate) is not None


def test_body_observation_reports_drift_without_changing_outline():
    outline = empty_outline("p")
    root = outline.elements[0].ref
    section = section_element(ref(SECTION_TYPE, "s"), root, "S", 0, body_version="4", body_digest="old")
    drift = observe_body(section, version="5", digest="new")
    assert drift.drifted and drift.expected_version == "4" and drift.observed_version == "5"
    assert section.attributes["body_digest"] == "old"


def test_report_argument_can_reference_method_profile_element():
    outline = empty_outline("p")
    root = outline.elements[0].ref
    section = section_element(ref(SECTION_TYPE, "s"), root, "Method", 0, arguments=(ref("method", "m"),))
    candidate = TopologyState(REPORT_PROFILE_ID, REPORT_PROFILE_VERSION, (outline.elements[0], section))
    assert validate_state(report_profile, candidate) is None


def test_method_signature_is_descriptive_and_checks_explicit_shape_only():
    producer = method_element(ref("method", "collect"), "Collect", inputs=(Port("question", "Question"),), outputs=(Port("materials", "Material"),))
    consumer = method_element(ref("method", "synthesize"), "Synthesize", inputs=(Port("materials", "Material"),), outputs=(Port("report", "Report"),), preconditions=("sources are reviewed",), assumptions=("scope is stable",))
    state = TopologyState(method_profile.profile_id, method_profile.version, (producer, consumer))
    assert validate_method_state(state) is None
    result = check_composition(producer, consumer)
    assert result.compatible and result.matched == (("materials", "materials"),)
    assert result.conditions == ("sources are reviewed", "scope is stable")
    incompatible = method_element(ref("method", "bad"), "Bad", inputs=(Port("materials", "Claim"),), outputs=())
    result = check_composition(producer, incompatible)
    assert not result.compatible and result.incompatible_types == (("materials", "Material", "Claim"),)
