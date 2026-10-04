from dataclasses import replace

import pytest
from functorial_kit import Failure

from app.services.information_topology.contracts import BoundRef, Element, ElementRef, Endpoint, TopologyState
from app.services.information_topology.profiles import ProfileSpec, validate_state
from app.services.information_topology.modules.retrieval import (
    DomainVocabulary, domain_vocabulary_element, make_retrieval_profile,
    profile_from_state_payload, semantic_successor_id, validate_evidence_v2,
    vocabulary_record_attributes,
)
from app.services.information_topology.contracts import topology_state_codec
from app.services.information_topology.structural_schema import derive_read_model_attributes


def bound(kind: str, local: str, revision: str = "r1") -> BoundRef:
    return BoundRef(ElementRef("p", "retrieval", "graph", kind, local), revision)


def vocabulary(name: str = "域甲") -> DomainVocabulary:
    return DomainVocabulary(name, ("现场", "材料"), ("supports", "context"), ("制度",),
                            ("背景",), ("池甲",), ("A", "D"), bound("source", "brief"))


def state_for(profile, elements, vocab=None):
    domain = vocab or vocabulary()
    return TopologyState(profile.profile_id, profile.version,
                         (domain_vocabulary_element(domain), *tuple(elements)))


def test_domain_vocabularies_are_bound_and_do_not_leak_between_profiles():
    one = vocabulary("域甲")
    two = DomainVocabulary("域乙", ("现场", "机构"), ("contests",), ("制度",),
                           ("背景",), ("池乙",), ("B",), bound("source", "brief-b"))
    profile_one, profile_two = make_retrieval_profile(one), make_retrieval_profile(two)
    state = state_for(profile_one, (
        Element(bound("node:现场", "scene"), {"source_type": "现场", "name": "现场"}),
        Element(bound("judgment", "e1"), {"from_id": "scene", "to_id": "scene", "edge_type": "supports", "judgment": "判断", "scope": "范围",
                "judgment_version": "v1", "outline_section": "背景", "pools": ["池甲"],
                "relation_classes": ["证据网"], "evidence_ids": []},
                (Endpoint("from", bound("node:现场", "scene")), Endpoint("to", bound("node:现场", "scene")))),
    ))
    assert validate_state(profile_one, state) is None
    assert validate_state(profile_two, state).code == "UNKNOWN_PROFILE"
    record = vocabulary_record_attributes(one)
    assert set(record) == {"name", "source_ref", "node_types", "edge_types", "perspectives", "outline_sections", "pools", "grades"}
    assert record["source_ref"]["local_id"] == "brief"


def test_profile_identity_is_source_scoped_and_observation_versioned():
    base = vocabulary("同名域")
    source_other_project = BoundRef(ElementRef("project-b", "retrieval", "briefs", "source", "brief"), "r1", "digest-a")
    other_project = DomainVocabulary(base.name, base.node_types, base.edge_types, base.perspectives,
        base.outline_sections, base.pools, base.grades, source_other_project)
    source_revision_2 = BoundRef(base.source_ref.ref, "r2", base.source_ref.content_digest)
    revised = DomainVocabulary(base.name, base.node_types, base.edge_types, base.perspectives,
        base.outline_sections, base.pools, base.grades, source_revision_2)
    source_digest_2 = BoundRef(base.source_ref.ref, base.source_ref.observed_revision, "digest-2")
    redigested = DomainVocabulary(base.name, base.node_types, base.edge_types, base.perspectives,
        base.outline_sections, base.pools, base.grades, source_digest_2)

    original_profile = make_retrieval_profile(base)
    cross_project_profile = make_retrieval_profile(other_project)
    revised_profile = make_retrieval_profile(revised)
    redigested_profile = make_retrieval_profile(redigested)
    assert original_profile.profile_id != cross_project_profile.profile_id
    assert original_profile.profile_id == revised_profile.profile_id == redigested_profile.profile_id
    assert original_profile.version != revised_profile.version
    assert original_profile.version != redigested_profile.version
    old_state = state_for(original_profile, (), base)
    assert validate_state(original_profile, old_state) is None
    assert validate_state(revised_profile, old_state).code == "UNKNOWN_PROFILE"


def test_make_retrieval_profile_rejects_invalid_call_inputs():
    base = vocabulary()
    with pytest.raises(ValueError, match="all seven nonempty fields"):
        make_retrieval_profile(replace(base, node_types=()))
    incomplete_ref = BoundRef(ElementRef("", "retrieval", "briefs", "source", "brief"), "r1")
    with pytest.raises(ValueError, match="identity must be complete"):
        make_retrieval_profile(replace(base, source_ref=incomplete_ref))
    with pytest.raises(ValueError, match="observed revision"):
        make_retrieval_profile(replace(base, source_ref=replace(base.source_ref, observed_revision="")))
    with pytest.raises(ValueError, match="content digest"):
        make_retrieval_profile(replace(base, source_ref=replace(base.source_ref, content_digest=42)))


def test_domain_vocabulary_snapshot_is_unique_immutable_and_resolves_profile():
    from dataclasses import replace

    vocab = vocabulary()
    profile = make_retrieval_profile(vocab)
    snapshot = domain_vocabulary_element(vocab)
    state = state_for(profile, (), vocab)
    assert validate_state(profile, state) is None

    payload = topology_state_codec.to_wire(state)
    restored = profile_from_state_payload("p", profile.profile_id, profile.version, payload)
    assert not isinstance(restored, Failure)
    assert (restored.profile_id, restored.version, restored.types, restored.relation_types) == (
        profile.profile_id, profile.version, profile.types, profile.relation_types)
    assert validate_state(restored, state) is None
    assert isinstance(profile_from_state_payload("other-project", profile.profile_id, profile.version, payload), Failure)

    tampered = replace(snapshot, attributes={**snapshot.attributes, "pools": ["changed"]})
    assert validate_state(profile, replace(state, elements=(tampered,))).code == "INVALID_STRUCTURE"
    assert validate_state(profile, replace(state, elements=(snapshot, snapshot))).code == "INVALID_STRUCTURE"

    # A changed vocabulary snapshot cannot claim the old stored profile identity.
    tampered_wire = dict(payload)
    tampered_wire["elements"] = [dict(payload["elements"][0], attributes={**payload["elements"][0]["attributes"], "pools": ["changed"]})]
    assert isinstance(profile_from_state_payload("p", profile.profile_id, profile.version, tampered_wire), Failure)


def test_evidence_v2_retains_three_distinct_roles_and_source_pair():
    attrs = {"grade": "D", "conflict": False, "effect": "限定", "original_location": "p.2",
             "original_excerpt": "原文", "applicable_scope": "范围", "inference_note": "推论",
             "proves": "表达事实", "source_role": "直接记录", "independence_group": "未知"}
    assert validate_evidence_v2(attrs) is None
    for effect in ("支持", "反驳"):
        assert validate_evidence_v2({**attrs, "effect": effect}) is None
    assert validate_evidence_v2({**attrs, "effect": "支持/反驳"}).code == "INVALID_STRUCTURE"
    assert validate_evidence_v2({key: value for key, value in attrs.items() if key != "original_excerpt"}).code == "INVALID_STRUCTURE"
    assert validate_evidence_v2({**attrs, "conflict": True}).code == "INVALID_STRUCTURE"


def test_semantic_judgment_successor_is_not_database_revision():
    assert semantic_successor_id("e:12", "v2") == "e:12~v2"
    assert semantic_successor_id("e:12", "v2") != "e:12"
    # A storage revision remains a BoundRef property and does not change its stable identity.
    old, new_storage_revision = bound("judgment", "e:12", "1"), bound("judgment", "e:12", "2")
    assert old.ref == new_storage_revision.ref
    assert semantic_successor_id("e:12", "v2") != new_storage_revision.ref.local_id
    with pytest.raises(ValueError, match="identity and semantic version"):
        semantic_successor_id("", "v2")
    with pytest.raises(ValueError, match="identity and semantic version"):
        semantic_successor_id("e:12", "")


def test_candidate_and_logical_dependency_are_separate_relation_types():
    profile = make_retrieval_profile(vocabulary())
    left, right = bound("node:材料", "a"), bound("node:材料", "b")
    state = state_for(profile, (
        Element(left, {"source_type": "材料", "name": "A"}),
        Element(right, {"source_type": "材料", "name": "B"}),
        Element(bound("logical_dependency", "dep:1"), {"dependency_id": "dep:1", "broken": False},
                (Endpoint("before", left), Endpoint("after", right))),
        Element(bound("candidate", "cand:1"), {"candidate_kind": "judgment", "status": "candidate"},
                (Endpoint("refers_to", left),)),
    ))
    assert validate_state(profile, state) is None


def test_routes_plans_registry_attempt_material_and_report_binding_are_distinct():
    profile = make_retrieval_profile(vocabulary())
    state = state_for(profile, (
        Element(bound("source_route", "route:1"), {"route_id": "route:1", "pool": "池甲", "status": "planned"}),
        Element(bound("keyword_plan", "query:1"), {"plan_id": "query:1", "kind": "query",
                "expression": "示例检索式", "execution_status": "not_executed"}),
        Element(bound("source_registry", "src:1"), {"source_id": "src:1", "url": "https://example.invalid",
                "status": "candidate"}),
        Element(bound("attempt", "attempt:1"), {"attempt_id": "attempt:1", "query_id": "query:1",
                "round_id": "run:2026-09-24:1", "clue_key": "clue:1", "executed_at": "imported-value",
                "tool": "source-record", "actual_query": "recorded query", "result": "access_failed"}),
        Element(bound("material", "item:1"), {"title": "Imported material", "grade": "A"}),
        Element(bound("gap", "gap:1"), {"gap_kind": "format", "description": "missing source field",
                "investigation_gap": False, "owner": "format"}),
        Element(bound("report_source_binding", "report:1"), {"report_ref": {"id": "report:1"},
                "body_revision": "r4", "summary_source": "report.md#摘要"}),
    ))
    assert validate_state(profile, state) is None
    unexecuted_with_result = Element(bound("keyword_plan", "query:2"), {"plan_id": "query:2", "kind": "query",
        "expression": "计划", "execution_status": "not_executed", "result": "miss"})
    assert validate_state(profile, state_for(profile, state.elements + (unexecuted_with_result,))).code == "INVALID_STRUCTURE"
    missing_timestamp = Element(bound("source_registry", "src:2"), {"source_id": "src:2", "url": "url", "status": "verified"})
    assert validate_state(profile, state_for(profile, state.elements + (missing_timestamp,))).code == "INVALID_STRUCTURE"


def test_formal_judgment_preserves_schema_fields_and_semantic_successor():
    profile = make_retrieval_profile(vocabulary())
    scene = bound("node:现场", "scene")
    state = state_for(profile, (
        Element(scene, {"source_type": "现场", "name": "场景", "scene_ref": "现场:x", "registration": "用户", "note": "保留"}),
        Element(bound("judgment", "e:2"), {"from_id": "n:1", "to_id": "n:2", "edge_type": "supports",
            "outline_section": "背景", "relation_classes": ["证据网"], "evidence_ids": ["ev:1"],
            "judgment": "判断", "scope": "范围", "judgment_version": "v2", "semantic_successor_of": "e:1",
            "pools": ["池甲"], "registration": "检索", "mediation_status": "仍在"},
            (Endpoint("from", scene), Endpoint("to", scene))),
    ))
    assert validate_state(profile, state) is None


def test_declared_relation_token_is_projected_into_the_read_model():
    """A profile declares its domain relation token once; readers get it derived."""
    profile = make_retrieval_profile(vocabulary())
    judgment_rule = profile.types["judgment"]
    assert judgment_rule.relation_token_attribute == "edge_type"
    assert profile.types["evidence"].relation_token_attribute is None

    attributes = {"edge_type": "支配", "judgment": "判断文本"}
    derived = derive_read_model_attributes("judgment", attributes, judgment_rule)
    assert derived["relation_token"] == "支配"
    assert derived["content_name"] == "判断文本"
    # The authored payload is untouched: derivation never rewrites source data.
    assert attributes == {"edge_type": "支配", "judgment": "判断文本"}

    undeclared = derive_read_model_attributes("evidence", {"effect": "支持"}, profile.types["evidence"])
    assert "relation_token" not in undeclared


def test_relation_token_declaration_must_name_a_declared_attribute():
    profile = make_retrieval_profile(vocabulary())
    broken = ProfileSpec(
        profile.profile_id, profile.version,
        {**profile.types, "judgment": replace(profile.types["judgment"], relation_token_attribute="missing")},
        profile.relation_types, profile.constraints,
    )
    state = state_for(profile, (
        Element(bound("judgment", "e:1"), {"from_id": "n:1", "to_id": "n:2", "edge_type": "dominates",
            "outline_section": "背景", "relation_classes": ["证据网"], "evidence_ids": [],
            "judgment": "判断", "scope": "范围", "judgment_version": "v1"},
            (Endpoint("from", bound("node:现场", "scene")), Endpoint("to", bound("node:现场", "scene")))),
    ))
    failure = validate_state(broken, state)
    assert failure is not None and failure.code == "INVALID_STRUCTURE"
    assert failure.context["path"] == "profile.types.judgment.relation_token_attribute"


def test_relation_types_declare_a_structural_role_and_axis():
    """Relation realization is declared once, then derived for readers."""
    profile = make_retrieval_profile(vocabulary())
    assert profile.types["judgment"].structural_role == "relation"
    assert profile.types["judgment"].relation_axis == ("from", "to")
    assert profile.types["evidence"].relation_axis == ("material", "judgment")
    assert profile.types["material"].structural_role is None

    derived = derive_read_model_attributes(
        "evidence", {"effect": "支持", "name": "证据"}, profile.types["evidence"])
    assert derived["structural_role"] == "relation"
    assert derived["relation_axis"] == ["material", "judgment"]

    node_derived = derive_read_model_attributes(
        "material", {"title": "材料"}, profile.types["material"])
    assert "structural_role" not in node_derived
    assert "relation_axis" not in node_derived

    authored = derive_read_model_attributes(
        "judgment", {"edge_type": "支配", "judgment": "文本", "structural_role": "annotation"},
        profile.types["judgment"])
    # An authored structural role stays authoritative over the declared default.
    assert authored["structural_role"] == "annotation"
    assert "relation_axis" not in authored


def test_relation_axis_declaration_is_validated():
    profile = make_retrieval_profile(vocabulary())
    state = state_for(profile, ())

    undeclared_role = ProfileSpec(
        profile.profile_id, profile.version,
        {**profile.types, "evidence": replace(
            profile.types["evidence"], structural_role="relation", relation_axis=("material", "missing"))},
        profile.relation_types, profile.constraints,
    )
    failure = validate_state(undeclared_role, state)
    assert failure is not None and failure.context["path"] == "profile.types.evidence.relation_axis"

    wrong_role = ProfileSpec(
        profile.profile_id, profile.version,
        {**profile.types, "evidence": replace(profile.types["evidence"], structural_role=None)},
        profile.relation_types, profile.constraints,
    )
    assert validate_state(wrong_role, state) is not None


def test_retrieval_process_types_are_declared_as_annotations():
    """Process records stay in the read model but out of the event graph."""
    profile = make_retrieval_profile(vocabulary())
    annotated = ("attempt", "domain_vocabulary", "clue", "source_route",
                 "keyword_plan", "source_registry", "report_source_binding")
    for type_id in annotated:
        assert profile.types[type_id].structural_role == "annotation", type_id
        derived = derive_read_model_attributes(type_id, {}, profile.types[type_id])
        assert derived.get("structural_role") == "annotation", type_id
        assert "relation_axis" not in derived, type_id
    for type_id in ("material", "candidate", "gap"):
        assert profile.types[type_id].structural_role is None, type_id
        assert "structural_role" not in derive_read_model_attributes(type_id, {}, profile.types[type_id])
