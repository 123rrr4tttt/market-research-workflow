from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.services.project_retrieval.execution import (
    RetrievalAttempt,
    _append_attempts,
    _decode_root_retrieval_budget,
    _decode_started_candidate_invocations,
    _encode_control,
    _merge_candidate_outcomes_control,
    _validate_candidate_outcome_identity,
    build_initial_retrieval_program,
    build_retrieval_leaf_invocations,
    build_retrieval_runtime_journal_reader,
    build_retrieval_work_active_child_bytes,
    build_retrieval_work_child_program,
    plan_retrieval_followup,
    review_candidate_work,
)
from app.services.agent_core.query_tools import (
    build_source_candidate_review_decision,
    build_source_discovery_search_queries,
)
from app.models.base import engine as runtime_engine
from app.services.project_retrieval.service import ProjectRetrievalService, RetrievalError
from app.services.project_retrieval.topology import build_topology_service
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest, sha256_hex
from app.successor_runtime.capabilities.retrieval_candidate_native import (
    RETRIEVAL_BUDGET_STATE_TYPE,
    RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
    RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
    RETRIEVAL_CANDIDATE_DISCOVER_V3_OWNER,
    RETRIEVAL_CANDIDATE_INVOCATION_TYPE,
    build_retrieval_candidate_runtime_definition,
    complete_retrieval_candidate_attempt,
)
from app.successor_runtime.capabilities.retrieval_common import (
    Candidate,
    CandidateBundle,
    CandidateSearchRequest,
    RetrievalCandidateInvocation,
    RetrievalCandidateAttemptOutcome,
    RetrievalBudgetState,
    retrieval_budget_id,
)
from app.successor_runtime.capabilities.retrieval_material_native import (
    CANDIDATE_WORK_TYPE,
    RETRIEVAL_CANDIDATE_REVIEW_KIND,
    RETRIEVAL_FOLLOWUP_PLAN_KIND,
    RETRIEVAL_MATERIAL_FORMALIZE_KIND,
    RETRIEVAL_MATERIAL_READ_BODY_KIND,
    RETRIEVAL_MATERIAL_REVALIDATE_KIND,
    RETRIEVAL_TOPOLOGY_COMMIT_KIND,
    CandidateWork,
    RetrievalControl,
    build_candidate_work_codec,
    build_retrieval_leaf_contract,
    build_retrieval_leaf_profiles,
    validate_candidate_work_transition,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.substrate.postgres.first_specimen_activation import (
    ActiveChildTerminalObservation,
)


def _plan(*, max_followups: int = 2) -> dict[str, object]:
    return {
        "plan_id": "plan-1",
        "mode_version": "1",
        "route_id": "route-1",
        "query_ids": ["query-1"],
        "queries": [{
            "query_id": "query-1", "expression": "water policy",
            "source_route_id": "route-1", "language": "bi",
        }],
        "limits": {"max_queries": 3, "max_materials": 2, "max_followups": max_followups},
        "diagnostics": [],
        "topology_seed": {
            "domain_vocabulary": {}, "source_routes": [],
            "keyword_plans": [], "source_registry": [],
        },
    }


def _root():
    return build_initial_retrieval_program(
        project_key="project-a", root_run_id="retrieval:" + "a" * 64,
        plan=_plan(), project_registry_revision=1,
        project_scope_digest="b" * 64, idempotency_key="idem-1",
    )


def _candidate(root, *, material_budget_remaining: int = 2) -> CandidateWork:
    return CandidateWork(
        project_key="project-a", root_run_id=root.run_id,
        retrieval_budget_id=root.budget.budget_id, plan_id="plan-1",
        mode_version="1", route_id="route-1", query_id="query-1",
        query_kind="initial", query_ordinal=1, followup_round=0,
        candidate_ordinal=1, candidate_id="candidate-1",
        material_budget_remaining=material_budget_remaining,
        candidate={"url": "https://example.org/source", "trust": {"status": "pending_review"}},
    )


def test_project_retrieval_service_rejects_invalid_idempotency_before_io():
    service = ProjectRetrievalService(session_factory=lambda: pytest.fail("unexpected IO"))
    with pytest.raises(RetrievalError) as error:
        service.start(
            "project-a", plan_id="plan-a", idempotency_key="", actor_id="actor-a"
        )
    assert (error.value.code, error.value.status) == ("INVALID_IDEMPOTENCY_KEY", 422)


def test_project_retrieval_service_passes_explicit_submission_identity(monkeypatch):
    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalar(self, _statement):
            return SimpleNamespace(payload=_plan())

    class _ConnectionContext:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return None

    class _Engine:
        def connect(self):
            return _ConnectionContext()

    project_scope = SimpleNamespace(
        project_registry_revision=1,
        scope_digest="b" * 64,
    )
    submitted = []

    def submit_installed_program(**kwargs):
        submitted.append(kwargs)
        return ({"run_id": kwargs["run_id"], "state": "PENDING"}, ("work-1",))

    monkeypatch.setattr("app.models.base.engine", _Engine())
    monkeypatch.setattr(
        "app.successor_runtime.substrate.postgres.session.ServerProjectScopeResolver",
        lambda **_kwargs: SimpleNamespace(resolve=lambda _project_key: project_scope),
    )
    monkeypatch.setattr(
        "app.composition.production.submit_installed_program",
        submit_installed_program,
    )

    result = ProjectRetrievalService(session_factory=_Session).start(
        "project-a",
        plan_id="plan-1",
        idempotency_key="idem-explicit",
        actor_id="actor-a",
    )

    assert result["run_id"].startswith("retrieval:")
    assert result["ready_work_item_ids"] == ["work-1"]
    assert len(submitted) == 1
    call = submitted[0]
    assert call["idempotency_id"]
    assert call["identity_capability_id"] == RETRIEVAL_CANDIDATE_DISCOVER_V3_OWNER
    assert call["logical_request_id"] == "idem-explicit"
    assert call["identity_operation_kind"] == RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND
    assert call["run_id"] == result["run_id"]
    assert "idempotency" not in call
    assert "request_digest" not in call


def test_project_retrieval_current_preserves_unresolved_integrity_error(monkeypatch):
    class RacingSession:
        def scalar(self, _statement):
            return None

        def add(self, _row):
            return None

        def commit(self):
            raise IntegrityError("insert mode", {}, RuntimeError("duplicate"))

        def rollback(self):
            return None

    monkeypatch.setattr(
        "app.services.project_retrieval.mode.load_mode",
        lambda _project_key: {
            "mode_id": "mode-1",
            "version": "1",
            "source_revision": "revision-1",
        },
    )
    with pytest.raises(IntegrityError):
        ProjectRetrievalService()._current(RacingSession(), "project-a")  # type: ignore[arg-type]


def test_retrieval_skill_failures_are_lifted_from_registered_family(monkeypatch):
    from app.services.project_retrieval import skill

    monkeypatch.setattr(skill, "current_project_key", lambda: "project-a")
    with pytest.raises(RetrievalError) as mismatch:
        skill._project({"project_key": "project-b"})
    assert (mismatch.value.code, mismatch.value.status) == ("PROJECT_MISMATCH", 404)

    with pytest.raises(RetrievalError) as untrusted:
        skill._actor_id({})
    assert (untrusted.value.code, untrusted.value.status) == ("INVALID_PLAN", 403)


def test_build_topology_service_only_assembles_existing_dependencies():
    service = build_topology_service()
    assert service.dependencies.repository is not None
    assert service.dependencies.io is not None


def test_ret_contract_errors():
    root_run_id = "retrieval:" + "a" * 64
    with pytest.raises(ValueError, match="ceilings"):
        RetrievalBudgetState(
            budget_id=retrieval_budget_id(
                project_key="project-a",
                root_run_id=root_run_id,
                plan_id="plan-1",
                mode_version="1",
            ),
            project_key="project-a",
            root_run_id=root_run_id,
            plan_id="plan-1",
            mode_version="1",
            max_queries=0,
            max_materials=1,
            max_followups=0,
        )
    with pytest.raises(ValueError, match="requires selected queries"):
        build_initial_retrieval_program(
            project_key="project-a",
            root_run_id=root_run_id,
            plan={**_plan(), "query_ids": []},
            project_registry_revision=1,
            project_scope_digest="b" * 64,
            idempotency_key="idem-invalid",
        )
    with pytest.raises(ValueError, match="identities"):
        CandidateWork(
            project_key="",
            root_run_id=root_run_id,
            retrieval_budget_id="budget-1",
            plan_id="plan-1",
            mode_version="1",
            route_id="route-1",
            query_id="query-1",
            query_kind="initial",
            query_ordinal=1,
            followup_round=0,
            candidate_ordinal=1,
            candidate_id="candidate-1",
            material_budget_remaining=1,
            candidate={"url": "https://example.org/source"},
        )


def test_source_discovery_runtime_kernels_preserve_original_pure_decisions():
    queries = build_source_discovery_search_queries(
        topic="water policy",
        query_terms=["water", "policy"],
        source_kinds=["official"],
        limit=1,
    )
    assert queries == [
        {
            "query": '"water policy" official data',
            "source_kind": "official",
            "purpose": "anchor facts in primary or authoritative sources",
            "write_policy": "plan_only_no_fetch",
        }
    ]
    review = build_source_candidate_review_decision(
        project_key="project-a",
        candidate={"url": "https://example.org/source", "title": "Source"},
        decision="approved",
        reviewed_at="2026-10-07T00:00:00Z",
        source_call_id="call-1",
    )
    assert review["decision"] == "approved"
    assert review["ingest_payload"]["url"] == "https://example.org/source"


def test_followup_planner_uses_settled_runtime_budget():
    control = RetrievalControl(
        project_key="project-a",
        root_run_id="retrieval:" + "a" * 64,
        retrieval_budget_id="budget-1",
        plan_id="plan-1",
        mode_version="1",
        route_id="route-1",
        round=1,
        plan_snapshot=_plan(),
    )
    planned = plan_retrieval_followup(
        lambda _control: {
            "attempts": [{"actual_query": "water policy"}],
            "works": [
                {
                    "stage": "formalized",
                    "disposition": "no_claim",
                    "gaps": [{"code": "CLAIM_NOT_SUPPORTED", "detail": "independent evidence"}],
                }
            ],
            "budget": {
                "queries_attempted": 1,
                "materials_accepted": 1,
                "max_queries": 3,
                "max_materials": 2,
            },
        },
        control,
    )
    assert planned.state == "planned"
    assert planned.planned_query is not None
    assert planned.planned_query["query_ordinal"] == 2
    assert planned.planned_query["max_results"] == 1


@pytest.mark.parametrize(
    "budget",
    [
        None,
        {"queries_attempted": 1, "materials_accepted": 1, "max_queries": 3},
        {
            "queries_attempted": 1,
            "materials_accepted": 1,
            "max_queries": 3,
            "max_materials": "2",
        },
        {
            "queries_attempted": 4,
            "materials_accepted": 1,
            "max_queries": 3,
            "max_materials": 2,
        },
    ],
)
def test_followup_planner_rejects_missing_or_drifting_runtime_budget(budget):
    control = RetrievalControl(
        project_key="project-a",
        root_run_id="retrieval:" + "a" * 64,
        retrieval_budget_id="budget-1",
        plan_id="plan-1",
        mode_version="1",
        route_id="route-1",
        round=1,
        plan_snapshot=_plan(),
    )

    with pytest.raises(ValueError, match="budget"):
        plan_retrieval_followup(
            lambda _control: {
                "attempts": [{"actual_query": "water policy"}],
                "works": [],
                "budget": budget,
            },
            control,
        )


def test_runtime_projection_decodes_exact_root_budget_and_started_invocation():
    root = _root()
    control = RetrievalControl(
        project_key="project-a",
        root_run_id=root.run_id,
        retrieval_budget_id=root.budget.budget_id,
        plan_id="plan-1",
        mode_version="1",
        route_id="route-1",
        round=0,
        plan_snapshot=_plan(),
        budget={},
    )
    values = dict(root.values)
    invocation_ref = next(
        ref for ref in values if ref.object_type == RETRIEVAL_CANDIDATE_INVOCATION_TYPE
    )

    budget = _decode_root_retrieval_budget(
        control,
        ((root.budget_ref, values[root.budget_ref]),),
    )
    invocations = _decode_started_candidate_invocations(
        control,
        {"candidate-step": {"attempt_id": "attempt-1"}},
        (("candidate-step", "attempt-1", invocation_ref, values[invocation_ref]),),
    )

    assert budget == root.budget
    assert invocations["candidate-step"].query_id == "query-1"
    assert invocations["candidate-step"].request.topic == "water policy"


def test_runtime_projection_rejects_missing_or_drifting_exact_inputs():
    root = _root()
    control = RetrievalControl(
        project_key="project-a",
        root_run_id=root.run_id,
        retrieval_budget_id=root.budget.budget_id,
        plan_id="plan-1",
        mode_version="1",
        route_id="route-1",
        round=0,
        plan_snapshot=_plan(),
        budget={},
    )
    values = dict(root.values)
    invocation_ref = next(
        ref for ref in values if ref.object_type == RETRIEVAL_CANDIDATE_INVOCATION_TYPE
    )

    with pytest.raises(ValueError, match="one exact static budget"):
        _decode_root_retrieval_budget(control, ())
    with pytest.raises(ValueError, match="ValueRef or bytes drift"):
        _decode_root_retrieval_budget(
            control,
            ((root.budget_ref, values[root.budget_ref] + b" "),),
        )
    with pytest.raises(ValueError, match="one exact semantic input"):
        _decode_started_candidate_invocations(
            control,
            {"candidate-step": {"attempt_id": "attempt-1"}},
            (),
        )
    with pytest.raises(ValueError, match="attempt identity drift"):
        _decode_started_candidate_invocations(
            control,
            {"candidate-step": {"attempt_id": "attempt-1"}},
            (("candidate-step", "attempt-2", invocation_ref, values[invocation_ref]),),
        )


def test_runtime_projection_rejects_candidate_outcome_identity_drift():
    root = _root()
    encoded = _candidate_outcome(root, ("https://example.org/source",))
    outcome = build_retrieval_candidate_runtime_definition().output_codec.decode_payload(encoded)
    invocation = RetrievalCandidateInvocation(
        query_id="query-1",
        route_id="route-1",
        query_kind="initial",
        query_ordinal=1,
        followup_round=0,
        budget_id=root.budget.budget_id,
        request=CandidateSearchRequest(
            topic="water policy",
            project_ref="project-a",
            source_ref="route-1",
        ),
    )

    _validate_candidate_outcome_identity(invocation, outcome)
    with pytest.raises(ValueError, match="executed invocation"):
        _validate_candidate_outcome_identity(invocation, replace(outcome, query_id="query-drift"))


def test_runtime_journal_reader_uses_executed_invocation_for_unknown_attempt(monkeypatch):
    root = _root()
    values = dict(root.values)
    invocation_ref = next(
        ref for ref in values if ref.object_type == RETRIEVAL_CANDIDATE_INVOCATION_TYPE
    )
    control = RetrievalControl(
        project_key="project-a",
        root_run_id=root.run_id,
        retrieval_budget_id=root.budget.budget_id,
        plan_id="plan-1",
        mode_version="1",
        route_id="route-1",
        round=0,
        plan_snapshot=_plan(),
        budget={},
    )
    step = {
        "step_id": "candidate-step",
        "operation_kind": RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
        "failure_digest": "provider-outcome-unknown",
    }
    event = {
        "event_type": "EffectStarted",
        "step_id": "candidate-step",
        "attempt_id": "attempt-1",
        "created_at": "2026-10-07T00:00:00Z",
    }
    monkeypatch.setattr(
        "app.composition.production.read_installed_program",
        lambda **_kwargs: (
            {"run_id": root.run_id, "project_key": "project-a"},
            (step,),
            (event,),
        ),
    )
    monkeypatch.setattr(
        "app.composition.production.read_installed_program_outputs",
        lambda **_kwargs: (),
    )
    input_binding_calls = []

    def read_input_bindings(**kwargs):
        input_binding_calls.append(kwargs)
        return (
            ((root.budget_ref, values[root.budget_ref]),),
            (("candidate-step", "attempt-1", invocation_ref, values[invocation_ref]),),
        )

    monkeypatch.setattr(
        "app.composition.production.read_installed_program_input_bindings",
        read_input_bindings,
    )
    reader = build_retrieval_runtime_journal_reader(
        engine=runtime_engine,
        actor_id="actor-a",
    )

    observation = reader(control)

    assert observation["attempts"] == [
        {
            "attempt_id": "attempt-1",
            "query_id": "query-1",
            "round_id": root.run_id,
            "clue_key": "route-1",
            "executed_at": "2026-10-07T00:00:00Z",
            "tool": "source.web.search",
            "actual_query": "water policy",
            "result": "access_failed",
            "source_ids": [],
            "material_ids": [],
            "next_step": "inspect_provider_diagnostics",
            "result_note": "provider-outcome-unknown",
            "raw_return_location": f"runtime:{root.run_id}:attempt:attempt-1",
        }
    ]
    assert observation["budget"] == {
        "queries_attempted": 1,
        "materials_accepted": 0,
        "followup_rounds_started": 0,
        "max_queries": 3,
        "max_materials": 2,
        "max_followups": 2,
        "remaining_queries": 2,
        "remaining_materials": 2,
        "remaining_followups": 2,
    }
    assert len(input_binding_calls) == 1
    assert input_binding_calls[0] == {
        "engine": runtime_engine,
        "project_key": "project-a",
        "actor_id": "actor-a",
        "run_id": root.run_id,
        "static_input_type": RETRIEVAL_BUDGET_STATE_TYPE,
    }


def test_runtime_journal_reader_rejects_typed_outcome_identity_drift(monkeypatch):
    root = _root()
    values = dict(root.values)
    definition = build_retrieval_candidate_runtime_definition()
    invocation_ref = next(
        ref for ref in values if ref.object_type == RETRIEVAL_CANDIDATE_INVOCATION_TYPE
    )
    invocation = definition.invocation_codec.decode_payload(json.loads(values[invocation_ref]))
    outcome = RetrievalCandidateAttemptOutcome.terminal_without_value(
        replace(invocation, query_id="query-drift"),
        state="failed",
        error_code="PROVIDER_FAILED",
    )
    outcome_bytes = canonical_json(definition.output_codec.encode_payload(outcome)).encode()
    outcome_ref = ValueRef(
        value_id="candidate-outcome",
        project_key="project-a",
        object_type=RETRIEVAL_CANDIDATE_ATTEMPT_OUTCOME_TYPE,
        codec_id=definition.output_codec.codec_id,
        content_digest=sha256_hex(outcome_bytes),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref="project-value:candidate-outcome",
        byte_size=len(outcome_bytes),
        provenance_digest="f" * 64,
    )
    control = RetrievalControl(
        project_key="project-a",
        root_run_id=root.run_id,
        retrieval_budget_id=root.budget.budget_id,
        plan_id="plan-1",
        mode_version="1",
        route_id="route-1",
        round=0,
        plan_snapshot=_plan(),
        budget={},
    )
    monkeypatch.setattr(
        "app.composition.production.read_installed_program",
        lambda **_kwargs: (
            {"run_id": root.run_id, "project_key": "project-a"},
            ({"step_id": "candidate-step", "operation_kind": RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND},),
            ({"event_type": "EffectStarted", "step_id": "candidate-step", "attempt_id": "attempt-1"},),
        ),
    )
    monkeypatch.setattr(
        "app.composition.production.read_installed_program_outputs",
        lambda **_kwargs: (("candidate-step", outcome_ref, outcome_bytes),),
    )
    monkeypatch.setattr(
        "app.composition.production.read_installed_program_input_bindings",
        lambda **_kwargs: (
            ((root.budget_ref, values[root.budget_ref]),),
            (("candidate-step", "attempt-1", invocation_ref, values[invocation_ref]),),
        ),
    )
    reader = build_retrieval_runtime_journal_reader(
        engine=runtime_engine,
        actor_id="actor-a",
    )

    with pytest.raises(ValueError, match="executed invocation"):
        reader(control)


def test_retrieval_runtime_builder_metadata_preserves_semantic_sources():
    reader = build_retrieval_runtime_journal_reader(
        engine=runtime_engine,
        actor_id="actor-a",
    )
    handlers = build_retrieval_leaf_invocations(
        topology_service=build_topology_service(),
        plan_loader=lambda _project_key, _plan_id: _plan(),
        journal_reader=reader,
    )
    assert callable(reader)
    assert set(handlers) == {
        RETRIEVAL_MATERIAL_READ_BODY_KIND,
        RETRIEVAL_MATERIAL_FORMALIZE_KIND,
        RETRIEVAL_MATERIAL_REVALIDATE_KIND,
        RETRIEVAL_FOLLOWUP_PLAN_KIND,
        RETRIEVAL_TOPOLOGY_COMMIT_KIND,
    }


def test_review_leaf_declares_dns_network_without_formalizer_credential():
    profiles = build_retrieval_leaf_profiles(RETRIEVAL_CANDIDATE_REVIEW_KIND)

    assert profiles.effect.network_required is True
    assert profiles.resource.resource_classes == ("NETWORK_IO",)
    assert profiles.authority.credential_refs == ()
    assert profiles.interpreter.credential_requirements_ref is None
    assert profiles.interpreter.dependency_digest == content_digest(
        {
            "interpreter": "services.project_retrieval.execution.review_candidate_work",
            "version": "1.0.0",
        }
    )


def test_root_and_candidate_work_have_one_semantic_return():
    root = _root()
    root_plan = compile_program(
        root.program, root.catalog, operation_contracts=root.registry,
        transform_registry=root.transform_registry, merge_registry=root.merge_registry,
        discriminator_registry=root.discriminator_registry,
    )
    assert len(root_plan.control_root.semantic_return_step_ids) == 1
    assert max(len(ref.value_id) for ref, _ in root.values) <= 128

    child = build_retrieval_work_child_program(
        work=_candidate(root), budget_ref=root.budget_ref,
        budget_bytes=dict(root.values)[root.budget_ref], element_index=0,
        element_digest="c" * 64, program_id="program:retrieval-work:" + "d" * 64,
        child_run_id="retrieval-work:" + "e" * 64,
        project_registry_revision=1, project_scope_digest="b" * 64,
    )
    child_plan = compile_program(
        child.program, root.catalog, operation_contracts=root.registry,
        transform_registry=root.transform_registry, merge_registry=root.merge_registry,
        discriminator_registry=root.discriminator_registry,
    )
    assert len(child_plan.control_root.semantic_return_step_ids) == 1
    assert sum(step.step_kind == "EFFECT" for step in child_plan.ordered_steps) == 5


def test_actual_root_compiles_initial_candidates_in_declared_order():
    plan = _plan(max_followups=0)
    plan["query_ids"] = ["query-1", "query-2"]
    plan["queries"] = [
        {
            "query_id": "query-1", "expression": "water policy",
            "source_route_id": "route-1", "language": "bi",
        },
        {
            "query_id": "query-2", "expression": "water quality",
            "source_route_id": "route-1", "language": "bi",
        },
    ]
    root = build_initial_retrieval_program(
        project_key="project-a",
        root_run_id="retrieval:ordered:" + "a" * 64,
        plan=plan,
        project_registry_revision=1,
        project_scope_digest="b" * 64,
        idempotency_key="idem:ordered",
    )
    compiled = compile_program(
        root.program,
        root.catalog,
        operation_contracts=root.registry,
        transform_registry=root.transform_registry,
        merge_registry=root.merge_registry,
        discriminator_registry=root.discriminator_registry,
    )
    candidate_effects = [
        step
        for step in compiled.ordered_steps
        if step.step_kind == "EFFECT"
        and step.operation_contract_ref is not None
        and step.operation_contract_ref.kind == RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND
    ]

    assert len(candidate_effects) == 2
    assert candidate_effects[1].dependencies == (candidate_effects[0].step_id,)


@pytest.mark.parametrize("max_followups", (0, 1, 2))
def test_root_and_candidate_child_compile_for_each_supported_followup_bound(max_followups):
    root = build_initial_retrieval_program(
        project_key="project-a",
        root_run_id=f"retrieval:{max_followups}:" + "a" * 64,
        plan=_plan(max_followups=max_followups),
        project_registry_revision=1,
        project_scope_digest="b" * 64,
        idempotency_key=f"idem:{max_followups}",
    )
    compiled_root = compile_program(
        root.program,
        root.catalog,
        operation_contracts=root.registry,
        transform_registry=root.transform_registry,
        merge_registry=root.merge_registry,
        discriminator_registry=root.discriminator_registry,
    )
    child = build_retrieval_work_child_program(
        work=_candidate(root),
        budget_ref=root.budget_ref,
        budget_bytes=dict(root.values)[root.budget_ref],
        element_index=0,
        element_digest="c" * 64,
        program_id=f"program:retrieval-work:{max_followups}",
        child_run_id=f"retrieval-work:{max_followups}",
        project_registry_revision=1,
        project_scope_digest="b" * 64,
    )
    compiled_child = compile_program(
        child.program,
        root.catalog,
        operation_contracts=root.registry,
        transform_registry=root.transform_registry,
        merge_registry=root.merge_registry,
        discriminator_registry=root.discriminator_registry,
    )

    assert len(compiled_root.control_root.semantic_return_step_ids) == 1
    assert len(compiled_child.control_root.semantic_return_step_ids) == 1
    assert sum(step.step_kind == "EFFECT" for step in compiled_child.ordered_steps) == 5


def test_rejected_candidate_stops_with_explicit_review_loss(monkeypatch):
    monkeypatch.setattr(
        "app.services.project_retrieval.execution.build_source_candidate_plan",
        lambda **_: {"rejected_urls": [{"status": "rejected"}]},
    )
    reviewed = review_candidate_work(_candidate(_root()), approved_prefix_count=0)
    assert (reviewed.stage, reviewed.disposition) == ("reviewed", "rejected")
    assert reviewed.review is not None and reviewed.review["review_artifact_ref"] is None
    assert reviewed.gaps[0]["code"] == "CANDIDATE_REVIEW_NOT_APPROVED"


def _candidate_outcome(root, urls: tuple[str, ...]) -> dict[str, object]:
    request = CandidateSearchRequest(
        topic="water policy", project_ref="project-a", source_ref="route-1"
    )
    invocation = RetrievalCandidateInvocation(
        query_id="query-1",
        route_id="route-1",
        query_kind="initial",
        query_ordinal=1,
        followup_round=0,
        budget_id=root.budget.budget_id,
        request=request,
    )
    bundle = CandidateBundle(
        request=request,
        candidates=tuple(
            Candidate(url, url, "policy", "test", "water", index, index, 1.0, {})
            for index, url in enumerate(urls, start=1)
        ),
        occurrences=(),
        observations=(),
        stop_reason="candidates_observed",
    )
    outcome = complete_retrieval_candidate_attempt(invocation, bundle)
    return build_retrieval_candidate_runtime_definition().output_codec.encode_payload(outcome)


def _control(root, *, remaining_materials: int) -> dict[str, object]:
    return _encode_control(
        RetrievalControl(
            project_key="project-a",
            root_run_id=root.run_id,
            retrieval_budget_id=root.budget.budget_id,
            plan_id="plan-1",
            mode_version="1",
            route_id="route-1",
            round=1,
            plan_snapshot=_plan(),
            budget={
                "max_queries": 3,
                "max_materials": 2,
                "max_followups": 2,
                "remaining_queries": 2,
                "remaining_materials": remaining_materials,
            },
        )
    )


def test_merge_is_pure_and_review_defers_when_material_budget_is_exhausted(monkeypatch):
    root = _root()
    monkeypatch.setattr(
        "app.services.project_retrieval.execution.build_source_candidate_plan",
        lambda **_: pytest.fail("candidate assessment must remain in the review effect"),
    )
    monkeypatch.setattr(
        "app.services.source_library.external_project.socket.getaddrinfo",
        lambda *_args, **_kwargs: pytest.fail("candidate merge must not resolve DNS"),
    )

    class _SettingsTrap:
        @staticmethod
        def model_dump():
            pytest.fail("candidate merge must not read URL policy settings")

    monkeypatch.setattr(
        "app.services.ingest.meaningful_gate.settings",
        _SettingsTrap(),
    )

    works = _merge_candidate_outcomes_control(
        _candidate_outcome(root, ("https://example.org/accepted",)),
        _control(root, remaining_materials=0),
    )

    assert works[0]["candidate"]["trust"] == {"status": "pending_review"}
    assert works[0]["material_budget_remaining"] == 0

    monkeypatch.setattr(
        "app.services.project_retrieval.execution.build_source_candidate_plan",
        lambda **_: {"candidate_urls": [{"status": "accepted"}]},
    )
    work = build_candidate_work_codec(
        build_retrieval_leaf_contract(RETRIEVAL_CANDIDATE_REVIEW_KIND).ref
    ).decode_payload(works[0])
    reviewed = review_candidate_work(work, approved_prefix_count=0)
    assert reviewed.candidate["trust"]["status"] == "deferred"
    assert reviewed.candidate["trust"]["blocked_reason"] == "retrieval material budget exhausted"


def test_review_requires_valid_prefix_count_before_trust_effect(monkeypatch):
    monkeypatch.setattr(
        "app.services.project_retrieval.execution.build_source_candidate_plan",
        lambda **_: pytest.fail("invalid prefix count must fail before trust review"),
    )
    work = _candidate(_root())

    with pytest.raises(TypeError):
        review_candidate_work(work)  # type: ignore[call-arg]
    for invalid in (True, -1):
        with pytest.raises(
            ValueError,
            match="candidate review requires an exact nonnegative approved prefix count",
        ):
            review_candidate_work(work, approved_prefix_count=invalid)


def test_candidate_work_transition_keeps_round_material_budget_immutable():
    before = _candidate(_root(), material_budget_remaining=1)

    with pytest.raises(
        ValueError,
        match="candidate work transition changed immutable identity",
    ):
        validate_candidate_work_transition(
            before,
            replace(before, material_budget_remaining=0),
        )


def test_rejected_candidate_does_not_consume_material_quota(monkeypatch):
    root = _root()
    works = _merge_candidate_outcomes_control(
        _candidate_outcome(
            root,
            ("https://example.org/rejected", "https://example.org/accepted"),
        ),
        _control(root, remaining_materials=1),
    )

    codec = build_candidate_work_codec(
        build_retrieval_leaf_contract(RETRIEVAL_CANDIDATE_REVIEW_KIND).ref
    )
    decoded = [codec.decode_payload(work) for work in works]
    decisions = iter(
        (
            {"rejected_urls": [{"status": "rejected"}]},
            {"candidate_urls": [{"status": "accepted"}]},
            {"candidate_urls": [{"status": "accepted"}]},
        )
    )
    monkeypatch.setattr(
        "app.services.project_retrieval.execution.build_source_candidate_plan",
        lambda **_: next(decisions),
    )

    rejected = review_candidate_work(decoded[0], approved_prefix_count=0)
    accepted = review_candidate_work(decoded[1], approved_prefix_count=0)
    exhausted = review_candidate_work(decoded[1], approved_prefix_count=1)

    assert rejected.disposition == "rejected"
    assert accepted.disposition == "approved"
    assert exhausted.disposition == "deferred"
    assert exhausted.candidate["trust"]["blocked_reason"] == "retrieval material budget exhausted"


def test_candidate_work_settlement_binds_exact_input_and_result(monkeypatch):
    from app.successor_runtime.language.plan import traversal_element_digests

    root = _root()
    before = replace(_candidate(root), candidate={**_candidate(root).candidate, "title": "供水💧", "rank": 1.0})
    monkeypatch.setattr(
        "app.services.project_retrieval.execution.build_source_candidate_plan",
        lambda **_: {"candidate_urls": [{"status": "accepted"}]},
    )
    reviewed = review_candidate_work(before, approved_prefix_count=0)
    ingested = replace(
        reviewed,
        stage="ingested",
        ingest={"receipt_owner": "acquisition.url.single_url.v1", "document_id": 1},
    )
    body_read = replace(
        ingested,
        stage="body_read",
        body={"status": "read", "document_id": 1, "body_digest": "d" * 64},
        body_text="已保存的供水正文💧",
    )
    formalized = replace(
        body_read,
        stage="formalized",
        disposition="proposed",
        formalization={"status": "proposed", "proposal": {}},
    )
    after = replace(formalized, stage="revalidated", disposition="ready")
    states = (before, reviewed, ingested, body_read, formalized, after)
    for left_index, left in enumerate(states):
        for right in states[left_index:]:
            validate_candidate_work_transition(left, right)
    codec = build_candidate_work_codec(
        build_retrieval_leaf_contract(RETRIEVAL_CANDIDATE_REVIEW_KIND).ref
    )
    before_bytes = canonical_json(codec.encode_payload(before)).encode()
    after_bytes = canonical_json(codec.encode_payload(after)).encode()

    def ref(value_id: str, exact: bytes) -> ValueRef:
        return ValueRef(
            value_id=value_id, project_key="project-a", object_type=CANDIDATE_WORK_TYPE,
            codec_id=codec.codec_id, content_digest=sha256_hex(exact),
            storage_kind="project_value_ref", store_id="successor_values", store_version="1",
            storage_ref=f"project-value:{value_id}", byte_size=len(exact),
            provenance_digest="f" * 64,
        )

    observation = ActiveChildTerminalObservation(
        element_index=0, element_digest=traversal_element_digests((json.loads(before_bytes),))[0],
        child_run_id="retrieval-work:1", state="COMPLETED",
        input_ref=ref("work-before", before_bytes), input_bytes=before_bytes,
        result_ref=ref("work-after", after_bytes), result_bytes=after_bytes,
    )
    settled = build_retrieval_work_active_child_bytes((observation,))
    assert json.loads(settled)[0]["disposition"] == "ready"
    from app.successor_runtime.language.checksum import canonical_bytes
    assert settled == canonical_bytes([codec.encode_payload(after)])
    assert settled != canonical_json([codec.encode_payload(after)]).encode()
    for state in ("FAILED", "CANCELLED"):
        with pytest.raises(
            ValueError,
            match="retrieval work settlement requires completed child observations",
        ):
            build_retrieval_work_active_child_bytes(
                (replace(observation, state=state, result_ref=None, result_bytes=None),)  # type: ignore[arg-type]
            )
    with pytest.raises(ValueError, match="input binding drift"):
        build_retrieval_work_active_child_bytes(
            (replace(observation, element_digest="0" * 64),)
        )


def test_candidate_work_composite_transition_rejects_missing_or_rewritten_review(monkeypatch):
    before = _candidate(_root())
    with pytest.raises(ValueError, match="exact receipt prefix"):
        replace(
            before,
            stage="revalidated",
            disposition="ready",
            ingest={"receipt_owner": "acquisition.url.single_url.v1", "document_id": 1},
            body={"status": "read", "document_id": 1, "body_digest": "d" * 64},
            body_text="persisted document body",
            formalization={"status": "proposed", "proposal": {}},
        )

    monkeypatch.setattr(
        "app.services.project_retrieval.execution.build_source_candidate_plan",
        lambda **_: {"candidate_urls": [{"status": "accepted"}]},
    )
    reviewed = review_candidate_work(before, approved_prefix_count=0)
    assert reviewed.review is not None
    rewritten = replace(
        reviewed,
        review={**reviewed.review, "reason": "rewritten after review"},
    )
    with pytest.raises(ValueError, match="replaced an existing receipt"):
        validate_candidate_work_transition(reviewed, rewritten)

    forged = replace(
        reviewed,
        review={**reviewed.review, "receipt_owner": "unowned.review"},
    )
    with pytest.raises(ValueError, match="trust lacks its exact review receipt"):
        validate_candidate_work_transition(before, forged)


def test_append_attempts_preserves_empty_and_missing_target_outcomes():
    attempt = RetrievalAttempt(
        "attempt-1", "query-1", "retrieval:1", "route-1",
        "2026-10-07T00:00:00+00:00", "source.web.search", "water policy", "hit",
    )
    common = dict(
        topology_service=object(), project_key="project-a", topology_ref=None,
        topology_seed=None, profile_id="", profile_version="", session_id="retrieval:1",
    )
    assert _append_attempts(**common, attempts=()).status == "not_needed"
    missing = _append_attempts(**common, attempts=(attempt,))
    assert (missing.status, missing.error) == ("blocked", {"code": "TOPOLOGY_TARGET_MISSING"})


def test_native_codec_rule_preserves_unicode_work_through_map_to_url(monkeypatch):
    from app.composition.production import _installed_value_encoder
    from app.successor_runtime.runtime.activation import BoundStepValue, activate_plan
    from app.successor_runtime.capabilities.acquisition_url import URL_SINGLE_URL_REQUEST_TYPE
    from app.successor_runtime.language.plan import traversal_element_digests
    from app.services.project_retrieval.execution import validate_retrieval_url_bound_inputs
    from app.successor_runtime.capabilities.acquisition_url import build_url_single_url_contract, build_url_single_url_request_codec

    root = _root()
    before = replace(_candidate(root), candidate={**_candidate(root).candidate, "title": "供水💧", "rank": 1.0})
    codec = build_candidate_work_codec(build_retrieval_leaf_contract(RETRIEVAL_CANDIDATE_REVIEW_KIND).ref)
    child = build_retrieval_work_child_program(
        work=before, budget_ref=root.budget_ref, budget_bytes=dict(root.values)[root.budget_ref],
        element_index=0, element_digest=traversal_element_digests((codec.encode_payload(before),))[0],
        program_id="program:unicode-work", child_run_id="unicode-work",
        project_registry_revision=1, project_scope_digest="b" * 64,
    )
    plan = compile_program(child.program, root.catalog, operation_contracts=root.registry,
        transform_registry=root.transform_registry, merge_registry=root.merge_registry,
        discriminator_registry=root.discriminator_registry)
    monkeypatch.setattr("app.services.project_retrieval.execution.build_source_candidate_plan",
                        lambda **_: {"candidate_urls": [{"status": "accepted"}]})
    reviewed = review_candidate_work(before, approved_prefix_count=0)
    payload = codec.encode_payload(reviewed)
    exact = canonical_json(payload).encode()
    ref = replace(child.invocation_ref, value_id="unicode-review", storage_ref="project-value:unicode-review",
                  content_digest=sha256_hex(exact), byte_size=len(exact))
    review_step = next(step for step in plan.ordered_steps if step.operation_contract_ref == codec.contract_ref)
    encoder = _installed_value_encoder(root.registry.contracts, root.transform_registry, root.merge_registry)
    result = activate_plan(run_id=child.child_run_id, program=child.program, plan=plan,
        completed_outputs=(BoundStepValue(review_step.step_id, ref, payload, exact_bytes=exact),),
        transform_registry=root.transform_registry, merge_registry=root.merge_registry,
        discriminator_registry=root.discriminator_registry, encode_value=encoder)
    request_value = next(value for value in result.materializations if value.value_ref.object_type == URL_SINGLE_URL_REQUEST_TYPE)
    assert request_value.exact_bytes == canonical_json(request_value.value).encode()
    url_codec = build_url_single_url_request_codec(build_url_single_url_contract().ref)
    request = url_codec.decode_payload(json.loads(request_value.exact_bytes))
    validate_retrieval_url_bound_inputs(request, ((root.budget_ref, dict(root.values)[root.budget_ref]),
                                                (request_value.value_ref, request_value.exact_bytes)))
    assert result.activations[0].operation_id == build_url_single_url_contract().ref.kind
    with pytest.raises(ValueError, match="no exact installed endpoint"):
        encoder(replace(URL_SINGLE_URL_REQUEST_TYPE, codec_id="unknown-codec"), request_value.value)
