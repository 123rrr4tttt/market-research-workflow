from __future__ import annotations

from dataclasses import replace

import pytest
from functorial_kit import Failure

from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
from app.services.agent_core.macro_tools import (
    facility_tool_projection,
    information_topology_read_facility,
    project_retrieval_current_facility,
    rapid_proposal_readback_facility,
    rapid_proposal_save_facility,
)
from app.services.information_topology.contracts import BoundRef, ElementRef, topology_failures
from app.services.information_topology.modules.retrieval import DomainVocabulary
from app.services.project_retrieval.proposals import (
    ProposalAttempt,
    ProposalDigest,
    ProposalFacet,
    ProposalFrontier,
    ProposalGap,
    ProposalOccurrence,
    ProposalQuery,
    ProposalSaveObservation,
    ProposalSnapshot,
    RapidProposal,
)


class CurrentService:
    def __init__(self) -> None:
        self.seen = None

    def current(self, project_key):
        self.seen = project_key
        return {"mode_id": "mode", "version": "2"}


class TopologyReadService:
    def __init__(self) -> None:
        self.seen = None

    def read_topology(self, project_key, topology_ref, filters):
        self.seen = (project_key, topology_ref, filters)
        return {"revision": 3, "digest": "d", "topology": {"elements": []}}


class ProposalAdapter:
    def __init__(self, proposal) -> None:
        self.proposal = proposal
        self.saved = None

    def save(self, project_key, proposal, vocabulary):
        self.saved = (project_key, proposal, vocabulary)
        return ProposalSaveObservation(
            status="persisted",
            proposal_id=proposal.proposal_id,
            proposal_version=proposal.proposal_version,
            content_digest=proposal.content_digest,
            topology_ref={"module_id": "retrieval", "namespace": "rapid.proposals", "state_id": proposal.identity},
            revision=1,
            readback_status="verified",
        )

    def read(self, project_key, proposal_id, proposal_version):
        assert project_key == "trusted_project"
        if (proposal_id, proposal_version) == (self.proposal.proposal_id, self.proposal.proposal_version):
            return self.proposal
        return topology_failures.fail("NOT_FOUND", "missing")


def _proposal():
    return RapidProposal(
        proposal_id="rp-1",
        proposal_version="v1",
        facets=(ProposalFacet("facet:policy@1", "analysis-topology:policy"),),
        queries=(ProposalQuery("query:1", "facet:policy@1", "water governance archive"),),
        snapshots=(ProposalSnapshot("snapshot:1", "b" * 64, "https://example.invalid/source"),),
        attempts=(ProposalAttempt("attempt:1", "query:1", "hit", ("snapshot:1",)),),
        occurrences=(ProposalOccurrence(
            "occurrence:1", "facet:policy@1", "query:1", "attempt:1", "snapshot:1", "candidate:1"
        ),),
        digests=(ProposalDigest(
            "digest:1", ("occurrence:1",), "Synthesis", ("policy",),
            ("analysis:governance",), "one snapshot", "uncorroborated",
        ),),
        gaps=(ProposalGap("gap:1", "facet:policy@1", "Need another source", ("attempt:1",), ()),),
        frontier=(ProposalFrontier(
            "frontier:1", "facet:policy@1", "independent archive", "close gap",
            ("digest:1",), ("gap:1",), (),
        ),),
    )


def _vocabulary(project_key: str) -> DomainVocabulary:
    return DomainVocabulary(
        "Example", ("现场",), ("影响",), ("治理",), ("背景",), ("档案",), ("A",),
        BoundRef(ElementRef(project_key, "retrieval", "source", "domain_brief", "domain"), "r1", "a" * 64),
    )


def _invoke(binding, arguments, *, project_key="trusted_project"):
    spec, handler = facility_tool_projection(binding)
    call = CoreToolCall(tool_name=spec.name, arguments=arguments, call_id="call-1")
    request = AgentCoreRequest(message="do it", session_id="session-1", project_key=project_key)
    return handler(call, spec, request, lambda _: None)


@pytest.mark.parametrize("field", [
    "binding_id", "version", "executor_ref", "scope_source",
    "permission_source", "failure_family", "readback_semantics",
])
def test_facility_binding_rejects_invalid_authoring(field) -> None:
    binding = project_retrieval_current_facility(CurrentService())
    with pytest.raises(ValueError, match="identity and semantic references"):
        replace(binding, **{field: " "})
    with pytest.raises(TypeError, match="actual handler"):
        replace(binding, handler=None)
    with pytest.raises(ValueError, match="executor_ref"):
        replace(binding, executor_ref="unrelated.service")
    for forbidden in ("project_key", "permissions", "permission", "actor_role"):
        spec = replace(binding.tool_spec, input_schema={"properties": {forbidden: {}}})
        with pytest.raises(ValueError, match="cannot grant scope or permission"):
            replace(binding, tool_spec=spec)
    spec = replace(binding.tool_spec, risk="write", permission="allow")
    with pytest.raises(ValueError, match="explicit permission boundary"):
        replace(binding, tool_spec=spec)


def test_current_and_topology_facilities_take_scope_from_request() -> None:
    current = CurrentService()
    current_binding = project_retrieval_current_facility(current)
    assert "project_key" not in current_binding.tool_spec.input_schema["properties"]
    result = _invoke(current_binding, {})
    assert result.status == "completed" and current.seen == "trusted_project"

    topology = TopologyReadService()
    topology_binding = information_topology_read_facility(topology)
    result = _invoke(topology_binding, {
        "topology_ref": {"module_id": "retrieval", "namespace": "rapid.proposals", "state_id": "rp@v1"},
        "filters": {"type_ids": ["rapid_proposal"]},
    })
    assert result.status == "completed"
    assert topology.seen[0] == "trusted_project"


def test_facility_rejects_missing_trusted_project_scope() -> None:
    result = _invoke(project_retrieval_current_facility(CurrentService()), {}, project_key=None)
    assert result.status == "failed"
    assert result.error["code"] == "project_scope_required"


def test_save_and_readback_facilities_keep_proposal_ceiling_and_readback() -> None:
    value = _proposal()
    adapter = ProposalAdapter(value)
    save = rapid_proposal_save_facility(adapter, _vocabulary)
    properties = save.tool_spec.input_schema["properties"]
    assert set(properties) == {"proposal"}
    assert save.tool_spec.permission == "ask" and save.tool_spec.risk == "write_shared"
    result = _invoke(save, {"proposal": value.to_mapping()})
    assert result.status == "completed"
    assert result.structured_content["save_observation"]["readback_status"] == "verified"
    assert adapter.saved[0] == "trusted_project"

    readback = rapid_proposal_readback_facility(adapter)
    result = _invoke(readback, {"proposal_id": "rp-1", "proposal_version": "v1"})
    assert result.status == "completed"
    assert result.structured_content["claim_ceiling"] == "expansion_proposal"


def test_readback_facility_preserves_original_failure_code() -> None:
    adapter = ProposalAdapter(_proposal())
    result = _invoke(
        rapid_proposal_readback_facility(adapter),
        {"proposal_id": "missing", "proposal_version": "v1"},
    )
    assert result.status == "failed"
    assert result.error["code"] == "NOT_FOUND"


def test_facility_projection_has_actual_handler_and_authority_sources() -> None:
    binding = project_retrieval_current_facility(CurrentService())
    spec, handler = facility_tool_projection(binding)
    assert callable(handler) and spec is binding.tool_spec
    projected = binding.to_projection()
    assert projected["scope_source"] == "AgentCoreRequest.project_key"
    assert projected["permission_source"]
    assert "handler" not in projected
