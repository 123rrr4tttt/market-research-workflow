from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

import pytest
from functorial_kit.core.failure import Failure

from app.services.search.candidate_contracts import CandidateBundle, CandidateSearchRequest
from app.services.discovery.adapters import candidate_flow_binding
from app.successor_runtime.capabilities.retrieval_candidate_native import (
    CANDIDATE_BUNDLE_TYPE, CANDIDATE_REQUEST_TYPE, CandidateSearchBinding,
    DEFAULT_CANDIDATE_NATIVE_SOURCE, lower_candidate_native_source,
)
from app.successor_runtime.capabilities.retrieval_flow_native import (
    DEFAULT_RETRIEVAL_FLOW_SOURCE, FIXED_CANDIDATE_OPERATION,
    FlowIdentity, FlowInterface, FlowOccurrence, FlowOperation, FlowPort, FlowThen,
    PortWire, RetrievalFlowAssemblyContext, RetrievalFlowSource,
    compile_retrieval_flow_native, lower_retrieval_flow_source,
)
from app.successor_runtime.research.object_types import ObjectType

pytestmark = pytest.mark.unit


def _step(name: str, input_type: ObjectType, output_type: ObjectType) -> FlowOccurrence:
    return FlowOccurrence(name, FlowOperation(
        f"test.{name}", "1", FlowInterface((FlowPort("incoming", input_type),)),
        FlowInterface((FlowPort("outgoing", output_type),)),
    ))


def _then(first, second) -> FlowThen:
    return FlowThen(first, second, (PortWire("outgoing", "incoming"),))


def test_explicit_differently_named_ports_and_repeated_operation_occurrences() -> None:
    operation = FlowOperation("test.same", "1", FlowInterface((FlowPort("in", CANDIDATE_REQUEST_TYPE),)),
                              FlowInterface((FlowPort("out", CANDIDATE_REQUEST_TYPE),)))
    expression = FlowThen(FlowOccurrence("a", operation), FlowOccurrence("b", operation), (PortWire("out", "in"),))
    definition = lower_retrieval_flow_source(RetrievalFlowSource("test.repeat", "1", "test", expression))
    assert not isinstance(definition, Failure)
    assert [item.occurrence_id for item in definition.occurrences] == ["a", "b"]
    assert any(edge.source.occurrence_id == "a" and edge.target.occurrence_id == "b" for edge in definition.edges)


def test_same_name_different_type_and_incomplete_wiring_rejected() -> None:
    left = _step("left", CANDIDATE_REQUEST_TYPE, CANDIDATE_BUNDLE_TYPE)
    right = _step("right", CANDIDATE_REQUEST_TYPE, CANDIDATE_BUNDLE_TYPE)
    bad_type = lower_retrieval_flow_source(RetrievalFlowSource("test.bad", "1", "test", _then(left, right)))
    assert isinstance(bad_type, Failure)
    no_wire = lower_retrieval_flow_source(RetrievalFlowSource("test.bad", "1", "test", FlowThen(left, right, ())))
    assert isinstance(no_wire, Failure)


def test_one_operation_identity_cannot_have_two_contracts() -> None:
    first = FlowOperation("test.same", "1", FlowInterface((FlowPort("in", CANDIDATE_REQUEST_TYPE),)),
                          FlowInterface((FlowPort("out", CANDIDATE_REQUEST_TYPE),)))
    changed = replace(first, effect_refs=("different.effect",))
    expression = FlowThen(FlowOccurrence("a", first), FlowOccurrence("b", changed), (PortWire("out", "in"),))
    assert isinstance(lower_retrieval_flow_source(RetrievalFlowSource("test.conflict", "1", "test", expression)), Failure)


def test_identity_and_three_step_rebracketing_preserve_order_and_wires() -> None:
    middle = ObjectType("Intermediate.v1")
    final = ObjectType("Final.v1")
    a = _step("a", CANDIDATE_REQUEST_TYPE, middle)
    b = _step("b", middle, final)
    c = _step("c", final, CANDIDATE_BUNDLE_TYPE)
    left = lower_retrieval_flow_source(RetrievalFlowSource("test.assoc", "1", "test", _then(_then(a, b), c)))
    right = lower_retrieval_flow_source(RetrievalFlowSource("test.assoc", "1", "test", _then(a, _then(b, c))))
    assert not isinstance(left, Failure) and not isinstance(right, Failure)
    assert left.occurrences == right.occurrences
    assert set(left.edges) == set(right.edges)
    identity = FlowIdentity(a.operation.inputs)
    with_identity = lower_retrieval_flow_source(RetrievalFlowSource(
        "test.identity", "1", "test", FlowThen(identity, a, (PortWire("incoming", "incoming"),)),
    ))
    bare = lower_retrieval_flow_source(RetrievalFlowSource("test.identity", "1", "test", a))
    assert not isinstance(with_identity, Failure) and not isinstance(bare, Failure)
    assert with_identity.occurrences == bare.occurrences
    assert set(with_identity.edges) == set(bare.edges)


def test_nondefault_flow_uses_same_rule_and_original_candidate_binding() -> None:
    candidate_definition = lower_candidate_native_source(DEFAULT_CANDIDATE_NATIVE_SOURCE)
    assert not isinstance(candidate_definition, Failure)
    request = CandidateSearchRequest(topic="robotics")
    expected = CandidateBundle(request, (), (), (), "no_candidates_observed", ())
    discover = Mock(return_value=expected)
    candidate = CandidateSearchBinding(candidate_definition, discover)
    nondefault_operation = replace(FIXED_CANDIDATE_OPERATION,
        inputs=FlowInterface((FlowPort("different_query_name", CANDIDATE_REQUEST_TYPE),)),
        outputs=FlowInterface((FlowPort("different_result_name", CANDIDATE_BUNDLE_TYPE),)),
    )
    source = RetrievalFlowSource("test.nondefault", "2", "test.owner", FlowOccurrence("search:1", nondefault_operation))
    native = compile_retrieval_flow_native(source)
    assert not isinstance(native, Failure)
    assert native.projection.id == "test.nondefault.2"
    binding = native.assemble(RetrievalFlowAssemblyContext((candidate_flow_binding(candidate),)))
    assert not isinstance(binding, Failure)
    assert binding.run(request) == expected
    discover.assert_called_once_with(request)


def test_wrong_operation_version_and_macro_without_entrypoint_rejected() -> None:
    default_native = compile_retrieval_flow_native(DEFAULT_RETRIEVAL_FLOW_SOURCE)
    assert not isinstance(default_native, Failure)
    candidate_definition = lower_candidate_native_source(DEFAULT_CANDIDATE_NATIVE_SOURCE)
    assert not isinstance(candidate_definition, Failure)
    wrong_binding = replace(candidate_flow_binding(CandidateSearchBinding(candidate_definition, Mock(return_value=None))), version="2")
    assert isinstance(default_native.assemble(RetrievalFlowAssemblyContext((wrong_binding,))), Failure)
    macro = replace(FIXED_CANDIDATE_OPERATION, control_kind="macro", entrypoint_ref="")
    invalid = lower_retrieval_flow_source(RetrievalFlowSource("test.macro", "1", "test", FlowOccurrence("m", macro)))
    assert isinstance(invalid, Failure)
