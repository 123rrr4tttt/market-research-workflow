from __future__ import annotations

from dataclasses import replace
from functorial_kit import Failure

from app.services.project_retrieval.proposals import rapid_proposal_from_mapping
from app.services.project_retrieval.rapid_macro import (
    build_round_proposal,
    continuation_plan_from_saved_frontier,
)


def _plan():
    return {
        "plan_id": "plan:1", "mode_id": "mode:1", "mode_version": "1", "route_id": "route:1",
        "query_ids": ["query:1"],
        "queries": [{"query_id": "query:1", "route_id": "route:1", "expression": "water policy", "language": "en"}],
        "limits": {"max_queries": 1, "max_materials": 1, "max_followups": 0},
        "binding_snapshot": {"routes": [{
            "route_id": "route:1", "outline_sections": ["Background"], "target_edges": ["influences"],
        }]},
        "topology_ref": {"module_id": "retrieval", "namespace": "rapid", "state_id": "retrieval-run:first"},
    }


def _round_result():
    return {
        "plan_id": "plan:1", "run_id": "retrieval:1",
        "attempts": [{
            "attempt_id": "attempt:1", "query_id": "query:1", "actual_query": "water policy", "result": "hit",
            "round_id": "retrieval:1", "tool": "source.web.search",
            "raw_return_location": "runtime:retrieval:1:attempt:attempt:1",
        }],
        "candidates": [{"candidate_id": "candidate:1", "query_id": "query:1"}],
        "materials": [{
            "candidate_id": "candidate:1", "status": "body_read",
            "body_read": {
                "status": "read", "document_id": 42, "uri": "https://example.org/1", "body_digest": "a" * 64,
            },
        }],
    }


def _proposal():
    return build_round_proposal(
        plan=_plan(), result=_round_result(), proposal_id="proposal:1", proposal_version="1",
        facet_ref="facet:1", facet_source_ref="analysis:1", digest_summary="Observed one policy source",
        classification_proposals=("policy",), analysis_positions=("Background",),
        coverage_boundary="one source", failure_boundary="independent source absent",
        gap_description="Find an independent source", proposed_query="water independent report",
        next_query_reason="first query reached only the policy source",
        outline_section="Background", target_edge="influences",
    )


class _SavedAdapter:
    def __init__(self, proposal):
        self.proposal = proposal
        self.reads = []

    def read(self, project_key, proposal_id, proposal_version):
        self.reads.append((project_key, proposal_id, proposal_version))
        return self.proposal


def test_round_digest_and_frontier_have_closed_observed_provenance():
    proposal = _proposal()
    assert not isinstance(proposal, Failure)
    assert proposal.validate() is None
    digest = proposal.digests[0]
    frontier = proposal.frontier[0]
    assert digest.query_ids == ("query:1",)
    assert digest.attempt_ids == ("attempt:1",)
    assert digest.material_refs == (f"document:42@{'a' * 64}",)
    assert digest.body_digests == ("a" * 64,)
    assert digest.gap_ids == (proposal.gaps[0].gap_id,)
    assert (frontier.parent_digest_id, frontier.gap_id) == (digest.digest_id, proposal.gaps[0].gap_id)
    assert (frontier.outline_section, frontier.target_edge, frontier.reason) == (
        "Background", "influences", "first query reached only the policy source",
    )
    assert rapid_proposal_from_mapping(proposal.to_mapping()) == proposal
    assert proposal.claim_ceiling == "expansion_proposal"
    altered_body = replace(proposal, digests=(replace(digest, body_digests=("b" * 64,)),))
    assert altered_body.validate().code == "SOURCE_CLOSURE_INCOMPLETE"
    altered_gap = replace(proposal, frontier=(replace(frontier, gap_id="other"),))
    assert altered_gap.validate().code == "SOURCE_CLOSURE_INCOMPLETE"


def test_miss_still_yields_gap_digest_without_invented_material():
    result = _round_result()
    result["attempts"][0]["result"] = "miss"
    result["candidates"] = []
    result["materials"] = []
    value = build_round_proposal(
        plan=_plan(), result=result, proposal_id="proposal:miss", proposal_version="1",
        facet_ref="facet:1", facet_source_ref="analysis:1", digest_summary="No result",
        classification_proposals=(), analysis_positions=("Background",),
        coverage_boundary="search attempted", failure_boundary="no material found",
        gap_description="No material", proposed_query="water archive", next_query_reason="initial search missed",
        outline_section="Background", target_edge="influences",
    )
    assert not isinstance(value, Failure)
    assert value.digests[0].material_refs == ()
    assert value.digests[0].body_digests == ()
    assert value.frontier[0].source_occurrence_ids == ()


def test_saved_frontier_consumes_separate_followup_budget_and_rejects_unbound_scope():
    proposal = _proposal()
    assert not isinstance(proposal, Failure)
    adapter = _SavedAdapter(proposal)
    frontier_id = proposal.frontier[0].frontier_id
    planned = continuation_plan_from_saved_frontier(
        adapter=adapter, project_key="project:1", proposal_id=proposal.proposal_id,
        proposal_version=proposal.proposal_version, frontier_id=frontier_id,
        base_plan=_plan(), remaining_followup_budget=2,
    )
    assert not isinstance(planned, Failure)
    assert adapter.reads == [("project:1", "proposal:1", "1")]
    assert planned["queries"][0]["expression"] == "water independent report"
    assert planned["rapid_continuation"]["parent_digest_id"] == proposal.digests[0].digest_id
    assert planned["rapid_continuation"]["gap_id"] == proposal.gaps[0].gap_id
    assert planned["rapid_continuation"]["remaining_followup_budget"] == 1
    assert planned["limits"]["max_queries"] == 1
    assert planned["limits"]["max_followups"] == 0
    assert planned["topology_ref"]["state_id"] != _plan()["topology_ref"]["state_id"]
    exhausted = continuation_plan_from_saved_frontier(
        adapter=adapter, project_key="project:1", proposal_id="proposal:1", proposal_version="1",
        frontier_id=frontier_id, base_plan=_plan(), remaining_followup_budget=0,
    )
    assert isinstance(exhausted, Failure) and exhausted.code == "CONTINUATION_BUDGET_EXHAUSTED"
    outside = _plan()
    outside["binding_snapshot"] = {"routes": [{
        "route_id": "route:1", "outline_sections": ["Other"], "target_edges": ["influences"],
    }]}
    rejected = continuation_plan_from_saved_frontier(
        adapter=adapter, project_key="project:1", proposal_id="proposal:1", proposal_version="1",
        frontier_id=frontier_id, base_plan=outside, remaining_followup_budget=1,
    )
    assert isinstance(rejected, Failure) and rejected.code == "CONTINUATION_INVALID"


def test_skill_adapter_forwards_project_bound_continuation(monkeypatch):
    from app.services.project_retrieval import skill

    observed = {}

    class Service:
        def continue_saved_frontier(self, project_key, **kwargs):
            observed.update({"project_key": project_key, **kwargs})
            return {"status": "completed"}

    monkeypatch.setattr(skill, "current_project_key", lambda: "project:1")
    monkeypatch.setattr(skill, "ProjectRetrievalService", Service)
    from app.services.request_identity import RequestActorContext

    result = skill.continue_saved_frontier(
        {
            "plan_id": "plan:1",
            "proposal_id": "proposal:1",
            "proposal_version": "1",
            "frontier_id": "frontier:1",
            "remaining_followup_budget": 2,
        },
        invocation_context={
            "actor_context": RequestActorContext(
                actor_id="actor:1", actor_source="authenticated_session",
                actor_trusted=True, actor_auth_mode="session",
            )
        },
    )
    assert result == {"status": "completed"}
    assert observed == {
        "project_key": "project:1",
        "plan_id": "plan:1",
        "proposal_id": "proposal:1",
        "proposal_version": "1",
        "frontier_id": "frontier:1",
        "remaining_followup_budget": 2,
        "actor_id": "actor:1",
    }


def test_continuation_skill_projects_exact_native_tool_schema():
    from app.services.agent_core.project_tools import _spec_from_skill
    from app.services.skill_runtime import list_registered_skills

    skill = next(
        item
        for item in list_registered_skills()
        if item["skill_id"] == "project_retrieval.continue_saved_frontier"
    )
    spec = _spec_from_skill(skill)
    assert spec.name == "skill.project_retrieval.continue_saved_frontier"
    assert spec.input_schema["required"] == [
        "plan_id",
        "proposal_id",
        "proposal_version",
        "frontier_id",
        "remaining_followup_budget",
    ]
    assert spec.input_schema["properties"]["remaining_followup_budget"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 20,
    }


def test_retrieval_persistence_and_provider_skills_declare_effect_labels():
    from app.services.skill_runtime import list_registered_skills

    expected = {
        "project_retrieval.current": ("write_shared", "optional"),
        "project_retrieval.preview": ("write_shared", "optional"),
        "project_retrieval.formalize_material": ("write_external", "optional"),
        "project_retrieval.formalize_document": ("write_external", "optional"),
    }
    by_skill = {item["skill_id"]: item for item in list_registered_skills()}
    for skill_id, (concurrency_class, approval_default) in expected.items():
        skill = by_skill[skill_id]
        assert skill["concurrency_class"] == concurrency_class
        assert skill["approval_policy"]["default"] == approval_default
