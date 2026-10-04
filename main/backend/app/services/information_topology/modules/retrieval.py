"""Structural profile for imported information-search graphs.

This module models records only. It never records that a search was executed.
Domain vocabulary is supplied from the source declaration (derived from the
analysis brief); it is not a global MRW enum and this module cannot edit it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from typing import Any, Mapping

from functorial_kit import Failure

from ..contracts import BoundRef, Element, ElementRef, TopologyState, topology_failures, topology_state_codec
from ..profiles import AttributeRule, EndpointRule, ProfileSpec, TypeRule
from ..structural_schema import with_structural_attributes

PROFILE_ID_PREFIX = "retrieval.domain."
PROFILE_VERSION_PREFIX = "1+"
RAPID_PROPOSAL_PROFILE_ID_PREFIX = "retrieval.rapid_proposal."
RAPID_PROPOSAL_PROFILE_VERSION_PREFIX = "1+"


@dataclass(frozen=True, slots=True)
class DomainVocabulary:
    """The seven-field vocabulary emitted from its authoritative domain brief."""

    name: str
    node_types: tuple[str, ...]
    edge_types: tuple[str, ...]
    perspectives: tuple[str, ...]
    outline_sections: tuple[str, ...]
    pools: tuple[str, ...]
    grades: tuple[str, ...]
    source_ref: BoundRef


def _nonempty_strings(value: object) -> bool:
    return isinstance(value, (tuple, list)) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _domain_constraint(vocabulary: DomainVocabulary):
    allowed_nodes = set(vocabulary.node_types)
    allowed_edges = set(vocabulary.edge_types)
    allowed_sections = set(vocabulary.outline_sections)
    allowed_pools = set(vocabulary.pools)
    allowed_grades = set(vocabulary.grades)
    expected_vocabulary = vocabulary_record_attributes(vocabulary)

    def validate(state: TopologyState) -> Failure | None:
        vocabulary_records = [element for element in state.elements
                              if element.ref.ref.type_id == "domain_vocabulary"]
        if len(vocabulary_records) != 1:
            return topology_failures.fail(
                "INVALID_STRUCTURE", "retrieval topology requires exactly one domain vocabulary record"
            )
        if dict(vocabulary_records[0].attributes) != dict(expected_vocabulary):
            return topology_failures.fail(
                "INVALID_STRUCTURE", "domain vocabulary source and fields are immutable within this profile"
            )
        for element in state.elements:
            attrs = element.attributes
            kind = element.ref.ref.type_id
            if kind.startswith("node:") and attrs.get("source_type") not in allowed_nodes:
                return topology_failures.fail("INVALID_STRUCTURE", "node type is outside bound domain vocabulary")
            if kind == "judgment":
                if attrs.get("edge_type") not in allowed_edges or attrs.get("outline_section") not in allowed_sections:
                    return topology_failures.fail("INVALID_STRUCTURE", "judgment classification is outside domain vocabulary")
                if attrs.get("relation_classes") is not None and (
                    not isinstance(attrs["relation_classes"], list)
                    or any(value not in {"线索链", "逻辑依赖", "证据网"} for value in attrs["relation_classes"])
                ):
                    return topology_failures.fail("INVALID_STRUCTURE", "judgment relation classes are invalid")
                pools = attrs.get("pools", [])
                if not isinstance(pools, list) or any(value not in allowed_pools for value in pools):
                    return topology_failures.fail("INVALID_STRUCTURE", "judgment pool is outside domain vocabulary")
                if attrs.get("semantic_successor_of") == element.ref.ref.local_id:
                    return topology_failures.fail("INVALID_STRUCTURE", "judgment cannot succeed itself")
            if kind == "evidence" and attrs.get("grade") not in allowed_grades:
                return topology_failures.fail("INVALID_STRUCTURE", "evidence grade is outside domain vocabulary")
            if kind == "evidence":
                evidence_failure = validate_evidence_v2(attrs)
                if evidence_failure is not None:
                    return evidence_failure
            if kind == "candidate" and attrs.get("status") != "candidate":
                return topology_failures.fail("INVALID_STRUCTURE", "candidate records cannot be promoted to formal evidence")
            if kind == "keyword_plan" and attrs.get("execution_status") == "not_executed" and attrs.get("result"):
                return topology_failures.fail("INVALID_STRUCTURE", "an unexecuted search plan cannot carry a result")
            if kind == "source_registry" and attrs.get("status") == "verified" and not attrs.get("verified_at"):
                return topology_failures.fail("INVALID_STRUCTURE", "verified source requires its verification timestamp")
            if kind == "attempt" and attrs.get("result") not in {"hit", "miss", "access_failed", "off_topic"}:
                return topology_failures.fail("INVALID_STRUCTURE", "attempt result must retain its distinct outcome")
            if kind == "material" and attrs.get("reference_status") != "unresolved_reference" and attrs.get("grade") not in allowed_grades:
                return topology_failures.fail("INVALID_STRUCTURE", "material grade is outside domain vocabulary")
            if kind == "domain_vocabulary" and attrs.get("name") != vocabulary.name:
                return topology_failures.fail("INVALID_STRUCTURE", "domain vocabulary identity mismatch")
        return None

    return validate


def make_retrieval_profile(vocabulary: DomainVocabulary) -> ProfileSpec:
    """Build a domain-specific profile keyed by stable source identity and observation.

    Revisions/digests alter the profile version, preserving older persisted
    states under the same source-derived profile ID.
    """
    if not vocabulary.name.strip() or not all(_nonempty_strings(values) for values in (
        vocabulary.node_types, vocabulary.edge_types, vocabulary.perspectives,
        vocabulary.outline_sections, vocabulary.pools, vocabulary.grades,
    )) or "现场" not in vocabulary.node_types:
        # kit:boundary owner=information_topology.modules.retrieval.make_retrieval_profile.vocabulary class=PROGRAMMER_DEFECT failure_family=none witness=test:test_make_retrieval_profile_rejects_invalid_call_inputs
        raise ValueError("retrieval domain vocabulary must contain all seven nonempty fields and node type 现场")

    source = vocabulary.source_ref
    source_identity = {
        "project_key": source.ref.project_key, "module_id": source.ref.module_id,
        "namespace": source.ref.namespace, "type_id": source.ref.type_id,
        "local_id": source.ref.local_id,
    }
    if any(not isinstance(value, str) or not value.strip() for value in source_identity.values()):
        # kit:boundary owner=information_topology.modules.retrieval.make_retrieval_profile.source_identity class=PROGRAMMER_DEFECT failure_family=none witness=test:test_make_retrieval_profile_rejects_invalid_call_inputs
        raise ValueError("domain vocabulary source reference identity must be complete")
    if not isinstance(source.observed_revision, str) or not source.observed_revision.strip():
        # kit:boundary owner=information_topology.modules.retrieval.make_retrieval_profile.observed_revision class=PROGRAMMER_DEFECT failure_family=none witness=test:test_make_retrieval_profile_rejects_invalid_call_inputs
        raise ValueError("domain vocabulary source reference must include its observed revision")
    if source.content_digest is not None and not isinstance(source.content_digest, str):
        # kit:boundary owner=information_topology.modules.retrieval.make_retrieval_profile.content_digest class=PROGRAMMER_DEFECT failure_family=none witness=test:test_make_retrieval_profile_rejects_invalid_call_inputs
        raise ValueError("domain vocabulary source content digest must be a string when present")
    canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    profile_id = PROFILE_ID_PREFIX + sha256(canonical(source_identity).encode("utf-8")).hexdigest()
    observed_source = {
        "observed_revision": source.observed_revision,
        "content_digest": source.content_digest,
        "vocabulary": {
            "name": vocabulary.name, "node_types": vocabulary.node_types,
            "edge_types": vocabulary.edge_types, "perspectives": vocabulary.perspectives,
            "outline_sections": vocabulary.outline_sections, "pools": vocabulary.pools,
            "grades": vocabulary.grades,
        },
    }
    profile_version = PROFILE_VERSION_PREFIX + sha256(canonical(observed_source).encode("utf-8")).hexdigest()

    node_ids = {f"node:{value}" for value in vocabulary.node_types}
    # The schema has relation categories; domain edge names remain data values.
    types: dict[str, TypeRule] = {
        **{node_id: TypeRule(attributes={"source_type": AttributeRule("string", True), "name": AttributeRule("string", True),
                                         "scene_ref": AttributeRule("string"), "registration": AttributeRule("string"), "note": AttributeRule("string")})
           for node_id in node_ids},
        "judgment": TypeRule(attributes={
            "edge_type": AttributeRule("string", True), "judgment": AttributeRule("string", True),
            "scope": AttributeRule("string", True), "judgment_version": AttributeRule("string", True),
            "semantic_successor_of": AttributeRule("string"), "outline_section": AttributeRule("string", True),
            "pools": AttributeRule("array"), "mediation_status": AttributeRule("string"),
            "relation_classes": AttributeRule("array", True), "evidence_ids": AttributeRule("array", True),
            "registration": AttributeRule("string"), "from_id": AttributeRule("string", True),
            "to_id": AttributeRule("string", True),
        }, endpoints={"from": EndpointRule(frozenset(node_ids | {"judgment"}), 1, 1),
                      "to": EndpointRule(frozenset(node_ids | {"judgment"}), 1, 1)},
            # The domain relation name of a judgment edge is authored in the
            # domain vocabulary's edge_types and instantiated here on the edge.
            relation_token_attribute="edge_type",
            structural_role="relation", relation_axis=("from", "to")),
        "material": TypeRule(attributes={
            "title": AttributeRule("string", True), "url": AttributeRule("string"),
            "grade": AttributeRule("string", True), "outline_section": AttributeRule("string"),
            "reference_status": AttributeRule("string"),
            "node_ids": AttributeRule("array"), "edge_ids": AttributeRule("array"),
            "relation_classes": AttributeRule("array"), "next_hop": AttributeRule("string"),
            "perspective": AttributeRule("string"), "registration": AttributeRule("string"),
            "snapshot_path": AttributeRule("array"), "candidate_key": AttributeRule("string"),
            "candidate_id": AttributeRule("string"),
            "document_ref": AttributeRule("object"),
        }),
        "evidence": TypeRule(attributes={
            "name": AttributeRule("string"),
            "grade": AttributeRule("string", True), "conflict": AttributeRule("boolean", True),
            "effect": AttributeRule("string", True), "original_location": AttributeRule("string", True),
            "original_excerpt": AttributeRule("string", True), "applicable_scope": AttributeRule("string", True),
            "inference_note": AttributeRule("string", True), "proves": AttributeRule("string", True),
            "source_role": AttributeRule("string", True), "independence_group": AttributeRule("string", True),
            "upstream_material_ids": AttributeRule("array"), "conflicting_evidence_ids": AttributeRule("array"),
        }, endpoints={"material": EndpointRule(frozenset({"material"}), 1, 1),
                      "judgment": EndpointRule(frozenset({"judgment"}), 1, 1)},
            # Evidence is the proving relation: its material is the node, the
            # judgment it supports is the relation it points at.
            structural_role="relation", relation_axis=("material", "judgment")),
        "clue": TypeRule(attributes={"clue_id": AttributeRule("string", True), "round_id": AttributeRule("string", True),
                                     "name": AttributeRule("string"),
                                     "scene_id": AttributeRule("string", True), "invalidated": AttributeRule("boolean"),
                                     "external_clue_ids": AttributeRule("array"), "pools": AttributeRule("array"),
                                     "chain_status": AttributeRule("string"), "chain_kind": AttributeRule("string"),
                                     "stop_reason": AttributeRule("string"), "next_hop": AttributeRule("string"),
                                     "gate_skipped": AttributeRule("boolean"), "skip_reason": AttributeRule("string"),
                                     "closing_note": AttributeRule("string"), "generation_date": AttributeRule("string"),
                                     "scene_label": AttributeRule("string")},
                         endpoints={"item": EndpointRule(frozenset(node_ids | {"judgment", "evidence", "clue", "material"}), 2, None, ordered=True)},
                         # The chain is the retrieval thread, not research content.
                         structural_role="annotation"),
        "logical_dependency": TypeRule(attributes={"dependency_id": AttributeRule("string", True), "broken": AttributeRule("boolean", True)},
                                        endpoints={"before": EndpointRule(frozenset(node_ids | {"judgment", "evidence", "clue"}), 1, 1),
                                                   "after": EndpointRule(frozenset(node_ids | {"judgment", "evidence", "clue"}), 1, 1)},
                                        structural_role="relation", relation_axis=("before", "after")),
        "candidate": TypeRule(attributes={"candidate_kind": AttributeRule("string", True), "status": AttributeRule("string", True),
                                           "source_note": AttributeRule("string"), "authority": AttributeRule("string"),
                                           "warnings": AttributeRule("array"), "conflict_records": AttributeRule("array")},
                               endpoints={"refers_to": EndpointRule(frozenset(node_ids | {"judgment", "evidence"}), 1, None)}),
        "gap": TypeRule(attributes={"gap_kind": AttributeRule("string", True), "description": AttributeRule("string", True),
                                    "investigation_gap": AttributeRule("boolean", True), "owner": AttributeRule("string"),
                                    "source": AttributeRule("string"), "status": AttributeRule("string")}),
        "source_route": TypeRule(attributes={"route_id": AttributeRule("string", True), "pool": AttributeRule("string", True),
            "outline_anchor": AttributeRule("string"), "outline_section": AttributeRule("string"),
            "perspective": AttributeRule("string"), "proposed_node_type": AttributeRule("string"),
            "proposed_edge_type": AttributeRule("string"), "entry": AttributeRule("string"),
            "status": AttributeRule("string", True)}, structural_role="annotation"),
        "keyword_plan": TypeRule(attributes={"plan_id": AttributeRule("string", True),
            "kind": AttributeRule("string", True), "expression": AttributeRule("string", True),
            "execution_status": AttributeRule("string", True), "result": AttributeRule("string"),
            "source_route_id": AttributeRule("string")}, structural_role="annotation"),
        "source_registry": TypeRule(attributes={"source_id": AttributeRule("string", True),
            "route_id": AttributeRule("string"), "url": AttributeRule("string", True),
            "status": AttributeRule("string", True), "snapshot_path": AttributeRule("string"),
            "verified_at": AttributeRule("string")}, structural_role="annotation"),
        "attempt": TypeRule(attributes={"attempt_id": AttributeRule("string", True),
            "query_id": AttributeRule("string", True), "round_id": AttributeRule("string", True),
            "clue_key": AttributeRule("string", True), "executed_at": AttributeRule("string", True),
            "tool": AttributeRule("string", True), "actual_query": AttributeRule("string", True),
            "result": AttributeRule("string", True), "source_ids": AttributeRule("array"),
            "material_ids": AttributeRule("array"), "next_step": AttributeRule("string"),
            "result_note": AttributeRule("string"), "raw_return_location": AttributeRule("string")}, structural_role="annotation"),
        "report_source_binding": TypeRule(attributes={"report_ref": AttributeRule("object", True),
            "body_revision": AttributeRule("string", True), "body_digest": AttributeRule("string"),
            "summary": AttributeRule("string"), "summary_source": AttributeRule("string", True)}, structural_role="annotation"),
        "domain_vocabulary": TypeRule(attributes={"name": AttributeRule("string", True), "source_ref": AttributeRule("object", True),
            "node_types": AttributeRule("array", True), "edge_types": AttributeRule("array", True),
            "perspectives": AttributeRule("array", True), "outline_sections": AttributeRule("array", True),
            "pools": AttributeRule("array", True), "grades": AttributeRule("array", True)}, structural_role="annotation"),
    }
    relations = frozenset({"judgment", "evidence", "clue", "logical_dependency", "candidate"})
    return ProfileSpec(
        profile_id, profile_version,
        with_structural_attributes(types), relations, (_domain_constraint(vocabulary),),
    )


def make_rapid_proposal_profile(vocabulary: DomainVocabulary) -> ProfileSpec:
    """Build the versioned storage profile for Rapid proposal envelopes.

    This is a separate profile rather than an in-place change to the existing
    retrieval-domain profile.  Previously persisted graph states therefore keep
    their original schema identity and interpretation.
    """
    base = make_retrieval_profile(vocabulary)
    source_suffix = base.profile_id.removeprefix(PROFILE_ID_PREFIX)
    canonical = json.dumps(
        {
            "base_profile_version": base.version,
            "proposal_contract": "rapid.proposal.v1",
            "claim_ceiling": "expansion_proposal",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    profile_id = RAPID_PROPOSAL_PROFILE_ID_PREFIX + source_suffix
    profile_version = RAPID_PROPOSAL_PROFILE_VERSION_PREFIX + sha256(canonical.encode("utf-8")).hexdigest()
    types = {
        "domain_vocabulary": TypeRule(
            attributes={
                "name": AttributeRule("string", True),
                "source_ref": AttributeRule("object", True),
                "node_types": AttributeRule("array", True),
                "edge_types": AttributeRule("array", True),
                "perspectives": AttributeRule("array", True),
                "outline_sections": AttributeRule("array", True),
                "pools": AttributeRule("array", True),
                "grades": AttributeRule("array", True),
            },
            structural_role="annotation",
        ),
        "rapid_proposal": TypeRule(
            attributes={
                "contract_version": AttributeRule("string", True),
                "proposal_version": AttributeRule("string", True),
                "claim_ceiling": AttributeRule("string", True),
                "content_digest": AttributeRule("string", True),
                "payload": AttributeRule("object", True),
            },
            structural_role="annotation",
        ),
    }
    expected_vocabulary = vocabulary_record_attributes(vocabulary)

    def validate(state: TopologyState) -> Failure | None:
        vocabulary_records = [item for item in state.elements if item.ref.ref.type_id == "domain_vocabulary"]
        proposal_records = [item for item in state.elements if item.ref.ref.type_id == "rapid_proposal"]
        if len(vocabulary_records) != 1 or dict(vocabulary_records[0].attributes) != dict(expected_vocabulary):
            return topology_failures.fail(
                "INVALID_STRUCTURE", "rapid proposal state needs its exact bound domain vocabulary"
            )
        if len(proposal_records) != 1:
            return topology_failures.fail(
                "INVALID_STRUCTURE", "rapid proposal state must contain exactly one proposal"
            )
        proposal_record = proposal_records[0]
        from app.services.project_retrieval.proposals import validate_persisted_proposal_attributes

        message = validate_persisted_proposal_attributes(proposal_record.attributes)
        if message is not None:
            return topology_failures.fail("INVALID_STRUCTURE", message)
        payload = proposal_record.attributes["payload"]
        expected_local_id = f"{payload['proposal_id']}@{payload['proposal_version']}"
        if (
            proposal_record.ref.ref.local_id != expected_local_id
            or proposal_record.ref.observed_revision != payload["proposal_version"]
            or proposal_record.ref.content_digest != proposal_record.attributes["content_digest"]
        ):
            return topology_failures.fail(
                "INVALID_STRUCTURE", "rapid proposal element identity differs from its payload"
            )
        return None

    return ProfileSpec(
        profile_id,
        profile_version,
        with_structural_attributes(types),
        frozenset(),
        (validate,),
    )


def vocabulary_record_attributes(vocabulary: DomainVocabulary) -> Mapping[str, Any]:
    """Return the persisted derived-wordlist record, bound to its source brief."""
    ref = vocabulary.source_ref
    return {
        "name": vocabulary.name,
        "source_ref": {
            "project_key": ref.ref.project_key, "module_id": ref.ref.module_id,
            "namespace": ref.ref.namespace, "type_id": ref.ref.type_id,
            "local_id": ref.ref.local_id, "observed_revision": ref.observed_revision,
            "content_digest": ref.content_digest,
        },
        "node_types": list(vocabulary.node_types), "edge_types": list(vocabulary.edge_types),
        "perspectives": list(vocabulary.perspectives), "outline_sections": list(vocabulary.outline_sections),
        "pools": list(vocabulary.pools), "grades": list(vocabulary.grades),
    }


def make_document_retrieval_profile(vocabulary: DomainVocabulary) -> ProfileSpec:
    """V2 materials are placements of canonical Documents, not source bodies."""
    legacy = make_retrieval_profile(vocabulary)
    types = dict(legacy.types)
    attributes = dict(types["material"].attributes)
    for key in ("title", "url", "content_name", "content_summary", "source_uri", "source_status"):
        attributes.pop(key, None)
    attributes["document_ref"] = AttributeRule("object")
    types["material"] = replace(types["material"], attributes=attributes)

    def validate_documents(state: TopologyState) -> Failure | None:
        for element in state.elements:
            if element.ref.ref.type_id != "material":
                continue
            attrs = element.attributes
            ref = attrs.get("document_ref")
            if attrs.get("reference_status") == "unresolved_reference":
                if ref is not None:
                    return topology_failures.fail("INVALID_STRUCTURE", "unresolved material cannot claim a Document")
                continue
            if (not isinstance(ref, Mapping) or set(ref) != {
                "project_key", "module_id", "namespace", "type_id", "local_id"
            } or ref.get("project_key") != element.ref.ref.project_key
                or (ref.get("module_id"), ref.get("namespace"), ref.get("type_id")) !=
                ("documents", "documents", "document")
                or not isinstance(ref.get("local_id"), str)
                or not ref["local_id"].isdigit() or int(ref["local_id"]) <= 0):
                return topology_failures.fail("INVALID_STRUCTURE", "material requires a canonical project Document reference")
        return None

    return replace(legacy, version="2+" + legacy.version.removeprefix("1+"),
                   types=types, constraints=(*legacy.constraints, validate_documents))


def domain_vocabulary_element(vocabulary: DomainVocabulary) -> Element:
    """Construct the one immutable snapshot element required by this profile."""
    profile = make_retrieval_profile(vocabulary)
    source = vocabulary.source_ref
    local_id = profile.profile_id.rsplit(".", 1)[-1]
    return Element(
        BoundRef(
            ElementRef(source.ref.project_key, "retrieval", profile.profile_id, "domain_vocabulary", local_id),
            profile.version,
        ),
        vocabulary_record_attributes(vocabulary),
    )


def profile_from_state_payload(
    project_key: str,
    profile_id: str,
    profile_version: str,
    payload: object,
) -> ProfileSpec | Failure:
    """Rebuild the exact domain profile from a persisted topology state payload.

    This is a pure snapshot resolver. It does not read the source adapter; an
    explicit refresh from source is a separate operation.
    """
    parsed = topology_state_codec.parse(payload)
    if isinstance(parsed, Failure):
        return topology_failures.fail("INVALID_WIRE_FORMAT", parsed.message, parsed.context)
    records = [element for element in parsed.elements if element.ref.ref.type_id == "domain_vocabulary"]
    if len(records) != 1:
        return topology_failures.fail("INVALID_STRUCTURE", "persisted payload must contain exactly one domain vocabulary")
    if records[0].ref.ref.project_key != project_key:
        return topology_failures.fail("INVALID_STRUCTURE", "persisted domain vocabulary belongs to another project")
    attributes = records[0].attributes
    expected_keys = {
        "name", "source_ref", "node_types", "edge_types", "perspectives",
        "outline_sections", "pools", "grades",
    }
    if set(attributes) != expected_keys:
        return topology_failures.fail("INVALID_STRUCTURE", "persisted domain vocabulary fields are incomplete or unknown")
    raw_ref = attributes["source_ref"]
    ref_keys = {"project_key", "module_id", "namespace", "type_id", "local_id", "observed_revision", "content_digest"}
    if not isinstance(raw_ref, Mapping) or set(raw_ref) != ref_keys:
        return topology_failures.fail("INVALID_STRUCTURE", "persisted domain vocabulary source reference is malformed")
    if raw_ref["project_key"] != project_key or not isinstance(raw_ref["content_digest"], (str, type(None))):
        return topology_failures.fail("INVALID_STRUCTURE", "persisted domain vocabulary source project or digest is invalid")
    source_identity = ("project_key", "module_id", "namespace", "type_id", "local_id", "observed_revision")
    if any(not isinstance(raw_ref[key], str) or not raw_ref[key].strip() for key in source_identity):
        return topology_failures.fail("INVALID_STRUCTURE", "persisted domain vocabulary source identity is incomplete")
    list_fields = ("node_types", "edge_types", "perspectives", "outline_sections", "pools", "grades")
    if any(not isinstance(attributes[key], list) for key in list_fields):
        return topology_failures.fail("INVALID_STRUCTURE", "persisted domain vocabulary fields must be arrays")
    if not isinstance(attributes["name"], str):
        return topology_failures.fail("INVALID_STRUCTURE", "persisted domain vocabulary name must be a string")
    try:
        vocabulary = DomainVocabulary(
            name=attributes["name"],
            node_types=tuple(attributes["node_types"]), edge_types=tuple(attributes["edge_types"]),
            perspectives=tuple(attributes["perspectives"]), outline_sections=tuple(attributes["outline_sections"]),
            pools=tuple(attributes["pools"]), grades=tuple(attributes["grades"]),
            source_ref=BoundRef(
                ElementRef(raw_ref["project_key"], raw_ref["module_id"], raw_ref["namespace"],
                           raw_ref["type_id"], raw_ref["local_id"]),
                raw_ref["observed_revision"], raw_ref["content_digest"],
            ),
        )
        profile = (
            make_rapid_proposal_profile(vocabulary)
            if profile_id.startswith(RAPID_PROPOSAL_PROFILE_ID_PREFIX)
            else (make_document_retrieval_profile(vocabulary)
                  if profile_version.startswith("2+") else make_retrieval_profile(vocabulary))
        )
    except (TypeError, ValueError) as exc:
        return topology_failures.fail("INVALID_STRUCTURE", f"persisted domain vocabulary is invalid: {exc}")
    if (profile.profile_id, profile.version) != (profile_id, profile_version):
        return topology_failures.fail(
            "UNKNOWN_PROFILE", "persisted payload vocabulary does not resolve to its declared profile identity",
            {"profile_id": profile_id, "profile_version": profile_version},
        )
    return profile


def semantic_successor_id(previous_id: str, next_version: str) -> str:
    """Derive a distinct judgment identity; storage revisions are separate."""
    if not previous_id.strip() or not next_version.strip():
        # kit:boundary owner=information_topology.modules.retrieval.semantic_successor_id.identity class=PROGRAMMER_DEFECT failure_family=none witness=test:test_semantic_judgment_successor_is_not_database_revision
        raise ValueError("judgment identity and semantic version must be nonempty")
    return f"{previous_id}~{next_version}"


def validate_evidence_v2(attributes: Mapping[str, Any]) -> Failure | None:
    """Validate source-schema evidence fields, including the two-field original quote."""
    required = ("grade", "conflict", "effect", "original_location", "original_excerpt", "applicable_scope",
                "inference_note", "proves", "source_role", "independence_group")
    if any(key not in attributes for key in required):
        return topology_failures.fail("INVALID_STRUCTURE", "evidence schema v2 required field missing")
    if attributes["effect"] not in {"支持", "反驳", "限定"}:
        return topology_failures.fail("INVALID_STRUCTURE", "evidence effect must preserve support/refute/qualify")
    if attributes["proves"] not in {"事实关系", "表达事实"}:
        return topology_failures.fail("INVALID_STRUCTURE", "unknown evidence proof target")
    if attributes["source_role"] not in {"直接记录", "当事方陈述", "机构自报", "二手转述", "研究推论"}:
        return topology_failures.fail("INVALID_STRUCTURE", "unknown evidence source role")
    if not all(isinstance(attributes[key], str) and attributes[key].strip() for key in
               ("original_location", "original_excerpt", "applicable_scope", "inference_note", "independence_group")):
        return topology_failures.fail("INVALID_STRUCTURE", "evidence quotation, scope and reasoning fields must be nonempty")
    if attributes.get("conflict") and not attributes.get("conflicting_evidence_ids"):
        return topology_failures.fail("INVALID_STRUCTURE", "conflicting evidence references are required")
    return None
