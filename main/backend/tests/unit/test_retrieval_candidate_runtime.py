"""Pure witnesses for the selected-query candidate search runtime contract."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.successor_runtime.capabilities.retrieval_candidate_native import (
    RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
    RETRIEVAL_CANDIDATE_DISCOVER_V3_VERSION,
    RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
    RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE,
    build_retrieval_candidate_atom,
    build_retrieval_candidate_prefix,
    build_retrieval_candidate_runtime_definition,
    complete_retrieval_candidate_attempt,
)
from app.successor_runtime.capabilities.retrieval_common import (
    Candidate,
    CandidateBundle,
    CandidateOccurrence,
    CandidateSearchRequest,
    ProviderObservation,
    RetrievalBudgetState,
    RetrievalCandidateInvocation,
    retrieval_budget_id,
)
from app.successor_runtime.language.program import program_atoms

pytestmark = pytest.mark.unit


def _request() -> CandidateSearchRequest:
    return CandidateSearchRequest(topic="water", keywords=("supply", "quality"))


def _bundle() -> CandidateBundle:
    request = _request()
    candidate = Candidate(
        resource_uri="https://example.org/a",
        title="A",
        snippet="snippet",
        source="ddg",
        keyword="supply",
        original_rank=1,
        result_rank=1,
        relevance_score=0.9,
        raw={"link": "https://example.org/a"},
    )
    occurrence = CandidateOccurrence(
        resource_uri="https://example.org/a",
        keyword="supply",
        provider="ddg",
        route="web",
        original_rank=1,
        retained=True,
    )
    observation = ProviderObservation(
        provider="ddg",
        route="web",
        keyword="supply",
        status="completed",
        returned_count=1,
    )
    return CandidateBundle(
        request=request,
        candidates=(candidate,),
        occurrences=(occurrence,),
        observations=(observation,),
        stop_reason="candidates_observed",
    )


def _budget() -> RetrievalBudgetState:
    root_run_id = "retrieval-root-1"
    plan_id = "retrieval-plan-1"
    mode_version = "1"
    return RetrievalBudgetState(
        budget_id=retrieval_budget_id(
            project_key="demo_proj",
            root_run_id=root_run_id,
            plan_id=plan_id,
            mode_version=mode_version,
        ),
        project_key="demo_proj",
        root_run_id=root_run_id,
        plan_id=plan_id,
        mode_version=mode_version,
        max_queries=3,
        max_materials=5,
        max_followups=1,
    )


def _invocation() -> RetrievalCandidateInvocation:
    budget = _budget()
    return RetrievalCandidateInvocation(
        query_id="query-1",
        route_id="water",
        query_kind="initial",
        query_ordinal=1,
        followup_round=0,
        budget_id=budget.budget_id,
        request=_request(),
    )


def test_operation_contract_is_v3_network_effect_without_document_write() -> None:
    runtime = build_retrieval_candidate_runtime_definition()
    contract = runtime.operation_contract

    assert contract.ref.kind == RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND
    assert contract.ref.contract_version == RETRIEVAL_CANDIDATE_DISCOVER_V3_VERSION
    assert contract.input_type.type_id == "RetrievalCandidateInvocation.v1"
    assert contract.output_type == RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE
    assert contract.return_contract_ref == "mrw.functorial-successor.return.single-typed-output.v1"
    # The v3 endpoint ObjectType must bind its exact payload codec so the shared
    # value read/publish paths resolve bytes by ObjectType.codec_id.
    assert contract.input_type.codec_id == runtime.invocation_codec.codec_id
    assert contract.output_type.codec_id == runtime.output_codec.codec_id

    effect = runtime.profiles.effect
    assert effect.execution_class == "EFFECTFUL"
    assert effect.network_required is True
    assert effect.external_visibility == "INTERNAL_ONLY"
    assert effect.external_acquisition is False
    assert effect.internal_export_only is True
    assert effect.irreversible is False
    assert effect.human_approval_required is False

    semantic = runtime.profiles.semantic
    assert semantic.reads == (
        "RetrievalCandidateInvocation.v1",
        "RetrievalBudgetState.v1",
    )
    assert semantic.creates == ("RetrievalCandidateAttemptOutcome.v1",)
    assert semantic.creates_relations == ()

    failure = runtime.profiles.failure
    assert failure.retryable is False
    assert "INTERPRETER_UNAVAILABLE" in failure.typed_failures

    resource = runtime.profiles.resource
    assert resource.resource_classes == ("NETWORK_IO",)


def test_bundle_codec_roundtrips_nested_types_and_rejects_non_object() -> None:
    runtime = build_retrieval_candidate_runtime_definition()
    codec = runtime.bundle_codec
    bundle = _bundle()

    decoded = codec.decode_payload(codec.encode_payload(bundle))
    assert decoded == bundle
    assert isinstance(decoded.request, CandidateSearchRequest)
    assert isinstance(decoded.candidates[0], Candidate)
    assert isinstance(decoded.occurrences[0], CandidateOccurrence)
    assert isinstance(decoded.observations[0], ProviderObservation)
    assert decoded.candidates[0].raw == {"link": "https://example.org/a"}

    malformed = dict(codec.encode_payload(bundle))
    malformed["request"] = "not-an-object"
    with pytest.raises(TypeError):
        codec.decode_payload(malformed)


def test_attempt_outcome_codec_roundtrips_completed_bundle() -> None:
    runtime = build_retrieval_candidate_runtime_definition()
    outcome = complete_retrieval_candidate_attempt(_invocation(), _bundle())

    decoded = runtime.output_codec.decode_payload(runtime.output_codec.encode_payload(outcome))

    assert decoded == outcome
    assert decoded.bundle == _bundle()


def test_request_codec_roundtrips() -> None:
    runtime = build_retrieval_candidate_runtime_definition()
    request = CandidateSearchRequest(topic="water", keywords=("supply", "quality"), days_back=7, start_offset=2)
    assert runtime.request_codec.decode_payload(runtime.request_codec.encode_payload(request)) == request


@pytest.mark.parametrize(
    ("candidate_request", "code"),
    (
        (CandidateSearchRequest(topic=1), "INVALID_TOPIC"),  # type: ignore[arg-type]
        (CandidateSearchRequest(topic="water", max_results=True), "INVALID_LIMIT"),
        (CandidateSearchRequest(topic="water", days_back="bad"), "INVALID_DAYS_BACK"),  # type: ignore[arg-type]
        (CandidateSearchRequest(topic="water", start_offset="bad"), "INVALID_OFFSET"),  # type: ignore[arg-type]
        (CandidateSearchRequest(topic="water", keywords=("",)), "INVALID_KEYWORDS"),
    ),
)
def test_candidate_search_request_validation_is_total_and_typed(
    candidate_request: CandidateSearchRequest,
    code: str,
) -> None:
    failure = candidate_request.validation_failure()
    assert failure is not None
    assert failure.code == code


def test_invocation_and_budget_codecs_roundtrip_typed_values() -> None:
    runtime = build_retrieval_candidate_runtime_definition()
    invocation = _invocation()
    budget = _budget()

    assert runtime.invocation_codec.decode_payload(runtime.invocation_codec.encode_payload(invocation)) == invocation
    assert runtime.budget_codec.decode_payload(runtime.budget_codec.encode_payload(budget)) == budget


def test_runtime_definition_builds_catalog_and_registry() -> None:
    runtime = build_retrieval_candidate_runtime_definition()
    catalog = runtime.build_catalog()
    assert catalog.lookup(runtime.operation_contract.ref) == runtime.operation_contract.ref
    registry = runtime.build_registry(catalog)
    assert registry.resolve(runtime.operation_contract.ref) == runtime.operation_contract


def test_candidate_atom_binds_exact_typed_values() -> None:
    runtime = build_retrieval_candidate_runtime_definition()
    child = build_retrieval_candidate_atom(
        invocation=_invocation(),
        budget=_budget(),
        program_id="program:retrieval-candidate-runtime",
        project_key="demo_proj",
        runtime=runtime,
    )

    atoms = program_atoms(child.root)
    assert len(atoms) == 1
    assert atoms[0].input_type.type_id == "RetrievalCandidateInvocation.v1"
    assert atoms[0].output_type == RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE
    assert atoms[0].operation.contract_ref == runtime.operation_contract.ref
    assert atoms[0].input_type.codec_id == runtime.invocation_codec.codec_id
    assert atoms[0].output_type.codec_id == runtime.output_codec.codec_id
    assert atoms[0].operation.payload_ref.object_type.codec_id == runtime.invocation_codec.codec_id
    assert atoms[0].operation.input_refs == (child.budget_ref, child.invocation_ref)
    assert child.values[0][0] == child.budget_ref
    assert child.values[1][0] == child.invocation_ref


def test_bound_input_validator_accepts_exact_budget_and_invocation() -> None:
    runtime = build_retrieval_candidate_runtime_definition()
    child = build_retrieval_candidate_atom(
        invocation=_invocation(),
        budget=_budget(),
        program_id="program:retrieval-candidate-bound-inputs",
        project_key="demo_proj",
        runtime=runtime,
    )

    runtime.validate_bound_inputs(_invocation(), child.values)
    with pytest.raises(ValueError, match="exactly budget and invocation"):
        runtime.validate_bound_inputs(_invocation(), child.values[1:])
    with pytest.raises(ValueError, match="differs from its bound input"):
        runtime.validate_bound_inputs(
            RetrievalCandidateInvocation(
                query_id="query-other",
                route_id="water",
                query_kind="initial",
                query_ordinal=1,
                followup_round=0,
                budget_id=_budget().budget_id,
                request=_request(),
            ),
            child.values,
        )


def test_sibling_candidate_children_share_one_immutable_budget_ref() -> None:
    runtime = build_retrieval_candidate_runtime_definition()
    first = build_retrieval_candidate_atom(
        invocation=_invocation(),
        budget=_budget(),
        program_id="program:retrieval-candidate-first",
        project_key="demo_proj",
        runtime=runtime,
    )
    second_invocation = RetrievalCandidateInvocation(
        query_id="query-2",
        route_id="water",
        query_kind="initial",
        query_ordinal=2,
        followup_round=0,
        budget_id=_budget().budget_id,
        request=CandidateSearchRequest(topic="quality"),
    )
    second = build_retrieval_candidate_atom(
        invocation=second_invocation,
        budget=_budget(),
        program_id="program:retrieval-candidate-second",
        project_key="demo_proj",
        runtime=runtime,
    )

    assert first.budget_ref == second.budget_ref
    assert first.values[0] == second.values[0]
    assert first.invocation_ref != second.invocation_ref


def test_candidate_prefix_orders_atoms_with_one_shared_budget() -> None:
    runtime = build_retrieval_candidate_runtime_definition()
    budget_encode_calls = 0
    encode_budget = runtime.budget_codec.encode

    def count_budget_encode(value):
        nonlocal budget_encode_calls
        budget_encode_calls += 1
        return encode_budget(value)

    runtime = replace(
        runtime,
        budget_codec=replace(runtime.budget_codec, encode=count_budget_encode),
    )
    second_invocation = RetrievalCandidateInvocation(
        query_id="query-2",
        route_id="water",
        query_kind="initial",
        query_ordinal=2,
        followup_round=0,
        budget_id=_budget().budget_id,
        request=CandidateSearchRequest(topic="quality"),
    )
    root = build_retrieval_candidate_prefix(
        invocations=(_invocation(), second_invocation),
        budget=_budget(),
        program_id="program:retrieval-fixed-root",
        project_key="demo_proj",
        runtime=runtime,
    )

    atoms = program_atoms(root.root)

    assert root.root.output_type == RETRIEVAL_CANDIDATE_ATTEMPT_SEQUENCE_TYPE
    assert len(atoms) == 2
    assert [atom.operation.payload_ref for atom in atoms] == [root.values[1][0], root.values[2][0]]
    assert len({atom.operation.operation_id for atom in atoms}) == 2
    assert all(atom.operation.input_refs[0] == root.budget_ref for atom in atoms)
    assert sum(ref == root.budget_ref for ref, _ in root.values) == 1
    assert budget_encode_calls == 1
