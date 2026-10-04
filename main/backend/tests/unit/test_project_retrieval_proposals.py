from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

from functorial_kit import Failure

from app.services.information_topology.contracts import BoundRef, ElementRef, topology_failures
from app.services.information_topology.modules.retrieval import (
    DomainVocabulary,
    domain_vocabulary_element,
    make_rapid_proposal_profile,
    profile_from_state_payload,
)
from app.services.information_topology.profiles import validate_state
from app.services.project_retrieval.proposals import (
    ProposalAttempt,
    ProposalDigest,
    ProposalFacet,
    ProposalFrontier,
    ProposalGap,
    ProposalOccurrence,
    ProposalQuery,
    ProposalSnapshot,
    RapidProposal,
    RapidProposalTopologyAdapter,
    rapid_proposal_element,
    rapid_proposal_from_mapping,
)


def vocabulary(project_key: str = "project_a") -> DomainVocabulary:
    return DomainVocabulary(
        name="Example",
        node_types=("现场", "机构"),
        edge_types=("影响",),
        perspectives=("治理",),
        outline_sections=("背景",),
        pools=("档案",),
        grades=("A", "B"),
        source_ref=BoundRef(
            ElementRef(project_key, "retrieval", "source", "domain_brief", "domain"),
            "source-r1",
            "a" * 64,
        ),
    )


def proposal(*, summary: str = "A bounded synthesis") -> RapidProposal:
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
            "digest:1",
            ("occurrence:1",),
            summary,
            ("policy",),
            ("analysis:governance",),
            "one observed snapshot",
            "no independent corroboration",
        ),),
        gaps=(ProposalGap("gap:1", "facet:policy@1", "Need a second source", ("attempt:1",), ()),),
        frontier=(ProposalFrontier(
            "frontier:1",
            "facet:policy@1",
            "water governance independent archive",
            "close the corroboration gap",
            ("digest:1",),
            ("gap:1",),
            (),
        ),),
    )


def _wire_digest(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class FakeTopologyService:
    def __init__(self) -> None:
        self.states: dict[tuple[str, str, str, str], dict] = {}
        self.raise_on_write = False

    def read_topology(self, project_key, target, filters):
        key = (project_key, target["module_id"], target["namespace"], target["state_id"])
        row = self.states.get(key)
        if row is None:
            return topology_failures.fail("NOT_FOUND", "missing")
        topology = row["topology"]
        type_ids = filters.get("type_ids")
        elements = topology["elements"]
        if type_ids is not None:
            elements = [item for item in elements if item["ref"]["ref"]["type_id"] in type_ids]
        return {
            "topology": {**topology, "elements": elements},
            "revision": row["revision"],
            "digest": row["digest"],
        }

    def apply_batch(self, project_key, *, state_patches, link_writes, read_set, link_read_set):
        if self.raise_on_write:
            raise RuntimeError("connection lost after dispatch")
        patch = state_patches[0]
        target = patch["target"]
        key = (project_key, target["module_id"], target["namespace"], target["state_id"])
        if key in self.states:
            return topology_failures.fail("IDENTITY_CONFLICT", "already exists")
        topology = dict(patch["initial_state"])
        digest = _wire_digest(topology)
        self.states[key] = {"topology": topology, "revision": 1, "digest": digest}
        return {"state_revisions": [{"target": dict(target), "revision": 1, "topology": topology}], "link_revisions": []}


def test_rapid_proposal_roundtrip_closes_every_source_layer() -> None:
    value = proposal()
    assert value.validate() is None
    restored = rapid_proposal_from_mapping(value.to_mapping())
    assert restored == value
    assert restored.content_digest == value.content_digest
    assert restored.claim_ceiling == "expansion_proposal"

    broken_attempt = replace(value, attempts=(replace(value.attempts[0], snapshot_refs=("missing",)),))
    failure = broken_attempt.validate()
    assert isinstance(failure, Failure) and failure.code == "SOURCE_CLOSURE_INCOMPLETE"

    broken_ceiling = replace(value, claim_ceiling="formal_evidence")
    failure = broken_ceiling.validate()
    assert isinstance(failure, Failure) and failure.code == "INVALID_PROPOSAL"


def test_rapid_proposal_uses_a_separate_versioned_profile() -> None:
    domain = vocabulary()
    profile = make_rapid_proposal_profile(domain)
    element = rapid_proposal_element("project_a", proposal())
    assert not isinstance(element, Failure)
    state = __import__(
        "app.services.information_topology.contracts", fromlist=["TopologyState"]
    ).TopologyState(profile.profile_id, profile.version, (domain_vocabulary_element(domain), element))
    assert profile.profile_id.startswith("retrieval.rapid_proposal.")
    assert validate_state(profile, state) is None

    wire = {
        "kind": "information_topology.state.v1",
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
        "elements": [
            {
                "ref": {
                    "ref": {
                        "project_key": item.ref.ref.project_key,
                        "module_id": item.ref.ref.module_id,
                        "namespace": item.ref.ref.namespace,
                        "type_id": item.ref.ref.type_id,
                        "local_id": item.ref.ref.local_id,
                    },
                    "observed_revision": item.ref.observed_revision,
                    "content_digest": item.ref.content_digest,
                },
                "attributes": dict(item.attributes),
                "endpoints": [],
            }
            for item in state.elements
        ],
    }
    rebuilt = profile_from_state_payload("project_a", profile.profile_id, profile.version, wire)
    assert not isinstance(rebuilt, Failure)
    assert (rebuilt.profile_id, rebuilt.version) == (profile.profile_id, profile.version)


def test_topology_adapter_confirms_readback_and_preserves_idempotency_conflict() -> None:
    service = FakeTopologyService()
    adapter = RapidProposalTopologyAdapter(service)
    value = proposal()

    first = adapter.save("project_a", value, vocabulary())
    assert (first.status, first.readback_status, first.revision) == ("persisted", "verified", 1)
    assert adapter.read("project_a", "rp-1", "v1") == value

    repeated = adapter.save("project_a", value, vocabulary())
    assert (repeated.status, repeated.readback_status) == ("already_persisted", "verified")

    conflict = adapter.save("project_a", proposal(summary="Different bytes"), vocabulary())
    assert conflict.status == "conflict"
    assert conflict.failure["code"] == "VERSION_CONFLICT"


def test_topology_adapter_keeps_unknown_effect_unconfirmed() -> None:
    service = FakeTopologyService()
    service.raise_on_write = True
    observation = RapidProposalTopologyAdapter(service).save("project_a", proposal(), vocabulary())
    assert observation.status == "unknown"
    assert observation.readback_status == "unavailable"
    assert observation.failure["code"] == "PERSISTENCE_UNKNOWN"


def test_topology_adapter_rejects_cross_project_vocabulary() -> None:
    observation = RapidProposalTopologyAdapter(FakeTopologyService()).save(
        "project_a", proposal(), vocabulary("project_b")
    )
    assert observation.status == "failed"
    assert observation.failure["code"] == "CROSS_PROJECT_REFERENCE"
