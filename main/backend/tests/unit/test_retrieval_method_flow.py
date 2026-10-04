from __future__ import annotations

from dataclasses import replace

import pytest
from functorial_kit.core.failure import Failure

from app.services.information_topology.contracts import BoundRef, Element, ElementRef, Endpoint, TopologyState
from app.services.information_topology.modules.method_flow import (
    BOUNDARY, CONTROL, OCCURRENCE, WIRE, project_retrieval_method_flow,
    structure_signature, validate_retrieval_method_flow,
)
from app.successor_runtime.capabilities.retrieval_candidate_native import CANDIDATE_BUNDLE_TYPE, CANDIDATE_REQUEST_TYPE
from app.successor_runtime.capabilities.retrieval_flow_native import (
    FIXED_CANDIDATE_OPERATION, FlowInterface, FlowOccurrence, FlowOperation,
    FlowPort, FlowThen, PortWire, RetrievalFlowSource, lower_retrieval_flow_source,
)

pytestmark = pytest.mark.unit


def _definition():
    second = FlowOperation(
        "test.echo", "3", FlowInterface((FlowPort("received", CANDIDATE_BUNDLE_TYPE),)),
        FlowInterface((FlowPort("returned", CANDIDATE_BUNDLE_TYPE),)),
        effect_refs=("read.only",), failure_refs=("test.echo.failure",),
        control_kind="macro", entrypoint_ref="agent_core.public_tool",
        authority_ref="agent_core.scope.v1", stop_ref="agent_core.stop.v1",
    )
    source = RetrievalFlowSource(
        "test.flow", "4", "test.owner",
        FlowThen(FlowOccurrence("discover:0", FIXED_CANDIDATE_OPERATION),
                 FlowOccurrence("macro:1", second), (PortWire("candidates", "received"),)),
    )
    definition = lower_retrieval_flow_source(source)
    assert not isinstance(definition, Failure)
    return definition


def _replace_element(state: TopologyState, old: Element, new: Element) -> TopologyState:
    return replace(state, elements=tuple(new if item == old else item for item in state.elements))


def test_projection_preserves_typed_wiring_occurrences_order_and_macro_boundary() -> None:
    state = project_retrieval_method_flow(_definition(), "project-1")
    assert validate_retrieval_method_flow(state) is None
    occurrences = [item for item in state.elements if item.ref.ref.type_id == OCCURRENCE]
    assert [(item.attributes["order"], item.attributes["operation_id"], item.attributes["operation_version"])
            for item in occurrences] == [
                (0, "retrieval.candidate.discover.v1", "1"), (1, "test.echo", "3")
            ]
    assert occurrences[1].attributes["control_kind"] == "macro"
    assert occurrences[1].attributes["effect_refs"] == ["read.only"]
    assert occurrences[1].attributes["failure_refs"] == ["test.echo.failure"]
    assert occurrences[1].attributes["entrypoint_ref"] == "agent_core.public_tool"
    assert len([item for item in state.elements if item.ref.ref.type_id == WIRE]) == 3
    assert len([item for item in state.elements if item.ref.ref.type_id == CONTROL]) == 1
    assert all(not hasattr(item, "run") for item in state.elements)


def test_missing_wiring_is_rejected() -> None:
    state = project_retrieval_method_flow(_definition(), "project-1")
    wire = next(item for item in state.elements if item.ref.ref.type_id == WIRE)
    missing = replace(state, elements=tuple(item for item in state.elements if item != wire))
    assert isinstance(validate_retrieval_method_flow(missing), Failure)


def test_wrong_version_missing_step_and_wrong_order_are_rejected_or_distinct() -> None:
    state = project_retrieval_method_flow(_definition(), "project-1")
    occurrence = next(item for item in state.elements if item.ref.ref.type_id == OCCURRENCE and item.attributes["order"] == 1)
    wrong_version = _replace_element(state, occurrence, replace(
        occurrence, attributes={**occurrence.attributes, "operation_version": "2"}
    ))
    assert isinstance(validate_retrieval_method_flow(wrong_version), Failure)
    missing = replace(state, elements=tuple(item for item in state.elements if item != occurrence))
    assert isinstance(validate_retrieval_method_flow(missing), Failure)
    wrong_order = _replace_element(state, occurrence, replace(
        occurrence, attributes={**occurrence.attributes, "order": 0}
    ))
    assert isinstance(validate_retrieval_method_flow(wrong_order), Failure)


def test_same_name_different_type_wire_is_rejected() -> None:
    state = project_retrieval_method_flow(_definition(), "project-1")
    wire = next(item for item in state.elements if item.ref.ref.type_id == WIRE and item.attributes["source_port"] == "candidates")
    bad = _replace_element(state, wire, replace(wire, attributes={**wire.attributes, "target_port": "query"}))
    assert isinstance(validate_retrieval_method_flow(bad), Failure)


def test_structure_equality_allows_local_occurrence_renaming_only() -> None:
    state = project_retrieval_method_flow(_definition(), "project-1")
    old = next(item for item in state.elements if item.ref.ref.type_id == OCCURRENCE)
    renamed_ref = BoundRef(replace(old.ref.ref, local_id="other-local-id"), old.ref.observed_revision)
    renamed_elements = []
    for item in state.elements:
        new_ref = renamed_ref if item.ref == old.ref else item.ref
        new_endpoints = tuple(Endpoint(end.role, renamed_ref if end.target == old.ref else end.target, end.position)
                              for end in item.endpoints)
        renamed_elements.append(Element(new_ref, item.attributes, new_endpoints))
    renamed = replace(state, elements=tuple(renamed_elements))
    assert structure_signature(state) == structure_signature(renamed)
    macro = next(item for item in state.elements if item.ref.ref.type_id == OCCURRENCE and item.attributes["control_kind"] == "macro")
    changed_macro = _replace_element(state, macro, replace(macro, attributes={**macro.attributes, "stop_ref": "different.stop"}))
    assert structure_signature(state) != structure_signature(changed_macro)
