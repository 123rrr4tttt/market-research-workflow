from __future__ import annotations

from app.services.information_topology.contracts import BoundRef, ElementRef, TopologyState, topology_failures, topology_state_codec
from app.services.information_topology.modules.report import empty_outline, report_profile
from app.services.information_topology.modules.retrieval import (
    DomainVocabulary,
    domain_vocabulary_element,
    make_retrieval_profile,
    profile_from_state_payload,
)
from app.services.information_topology.profiles import ProfileSpec, TypeRule
from app.services.information_topology.profiles import validate_state
from app.services.information_topology.repository import InformationTopologyRepository, StateWrite


def _retrieval_snapshot():
    vocabulary = DomainVocabulary(
        "测试域", ("现场", "材料"), ("supports",), ("制度",), ("背景",), ("pool-a",), ("A",),
        BoundRef(ElementRef("project-a", "briefs", "domain", "source", "brief-1"), "brief-r4", "abc123"),
    )
    profile = make_retrieval_profile(vocabulary)
    state = TopologyState(profile.profile_id, profile.version, (domain_vocabulary_element(vocabulary),))
    payload = topology_state_codec.to_wire(state)
    return vocabulary, profile, state, payload


def test_repository_resolves_dynamic_retrieval_profile_from_payload_snapshot():
    _, expected, state, payload = _retrieval_snapshot()
    calls = []

    def resolver(project_key, profile_id, profile_version, persisted_payload, source_ref=None):
        calls.append((project_key, profile_id, profile_version, persisted_payload, source_ref))
        return profile_from_state_payload(project_key, profile_id, profile_version, persisted_payload)

    repository = InformationTopologyRepository(profile_resolver=resolver)
    resolved = repository.resolve_profile("project-a", state.profile_id, state.profile_version, payload)
    assert (resolved.profile_id, resolved.version) == (expected.profile_id, expected.version)
    assert resolved.types == expected.types
    assert validate_state(resolved, state) is None
    assert calls == [("project-a", state.profile_id, state.profile_version, payload, None)]


def test_mismatched_dynamic_profile_version_is_rejected_before_repository_write():
    _, profile, state, _ = _retrieval_snapshot()
    repository = InformationTopologyRepository()
    stale_state = TopologyState(state.profile_id, "1+wrong-observation", state.elements)
    result = repository.prepare_state_write(
        StateWrite(("project-a", "retrieval", "domain", "state-1"), stale_state, None)
    )
    assert getattr(result, "code", None) == "UNKNOWN_PROFILE"


def test_static_report_profile_remains_compatible_without_dynamic_resolver():
    repository = InformationTopologyRepository({(report_profile.profile_id, report_profile.version): report_profile})
    state = empty_outline("project-a", "outline-1")
    payload = repository.prepare_state_write(
        StateWrite(("project-a", "report", "outline", "outline-1"), state, None)
    )
    assert isinstance(payload, dict)
    assert payload["profile_id"] == report_profile.profile_id


def test_custom_resolver_failure_is_returned_without_static_fallback():
    static = ProfileSpec("static.profile", "1", {"node": TypeRule()}, frozenset())
    failure = topology_failures.fail("UNKNOWN_PROFILE", "resolver rejected profile")

    def resolver(*_args):
        return failure

    repository = InformationTopologyRepository({("static.profile", "1"): static}, profile_resolver=resolver)
    resolved = repository.resolve_profile("project-a", "dynamic.profile", "7", {"kind": "candidate"})
    assert resolved is failure
