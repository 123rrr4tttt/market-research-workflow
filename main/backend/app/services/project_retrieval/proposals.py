"""Rapid proposal contract and adapter to the authoritative topology writer.

The proposal is deliberately below evidence/formalization authority.  It keeps
the provenance chain needed by a later Rapid turn, while persistence remains an
effect of ``InformationTopologyService.apply_batch`` and its repository.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Literal

from functorial_kit import Failure, define_failure_family

from app.services.information_topology.contracts import BoundRef, Element, ElementRef, TopologyState
from app.services.information_topology.modules.retrieval import (
    DomainVocabulary,
    domain_vocabulary_element,
    make_rapid_proposal_profile,
)


RAPID_PROPOSAL_CONTRACT_VERSION = "rapid.proposal.v1"
RAPID_PROPOSAL_CLAIM_CEILING = "expansion_proposal"
RAPID_PROPOSAL_MODULE_ID = "retrieval"
RAPID_PROPOSAL_NAMESPACE = "rapid.proposals"

rapid_proposal_failures = define_failure_family(
    "project_retrieval.rapid_proposal",
    (
        "INVALID_PROPOSAL",
        "SOURCE_CLOSURE_INCOMPLETE",
        "CROSS_PROJECT_REFERENCE",
        "VERSION_CONFLICT",
        "NOT_FOUND",
        "PERSISTENCE_FAILED",
        "PERSISTENCE_UNKNOWN",
        "READBACK_MISMATCH",
    ),
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _strings(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)) or any(not _nonempty(item) for item in value):
        return None
    return tuple(value)


@dataclass(frozen=True, slots=True)
class ProposalFacet:
    facet_ref: str
    source_ref: str

    def to_mapping(self) -> dict[str, Any]:
        return {"facet_ref": self.facet_ref, "source_ref": self.source_ref}


@dataclass(frozen=True, slots=True)
class ProposalQuery:
    query_id: str
    facet_ref: str
    expression: str

    def to_mapping(self) -> dict[str, Any]:
        return {"query_id": self.query_id, "facet_ref": self.facet_ref, "expression": self.expression}


@dataclass(frozen=True, slots=True)
class ProposalSnapshot:
    snapshot_ref: str
    content_digest: str
    source_ref: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "snapshot_ref": self.snapshot_ref,
            "content_digest": self.content_digest,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class ProposalAttempt:
    attempt_id: str
    query_id: str
    outcome: Literal["hit", "miss", "access_failed", "off_topic", "partial", "unknown"]
    snapshot_refs: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "query_id": self.query_id,
            "outcome": self.outcome,
            "snapshot_refs": list(self.snapshot_refs),
        }


@dataclass(frozen=True, slots=True)
class ProposalOccurrence:
    occurrence_id: str
    facet_ref: str
    query_id: str
    attempt_id: str
    snapshot_ref: str
    source_ref: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "occurrence_id": self.occurrence_id,
            "facet_ref": self.facet_ref,
            "query_id": self.query_id,
            "attempt_id": self.attempt_id,
            "snapshot_ref": self.snapshot_ref,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class ProposalDigest:
    digest_id: str
    occurrence_ids: tuple[str, ...]
    summary: str
    classification_proposals: tuple[str, ...]
    analysis_positions: tuple[str, ...]
    coverage_boundary: str
    failure_boundary: str
    query_ids: tuple[str, ...] = ()
    attempt_ids: tuple[str, ...] = ()
    material_refs: tuple[str, ...] = ()
    body_digests: tuple[str, ...] = ()
    gap_ids: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        result = {
            "digest_id": self.digest_id,
            "occurrence_ids": list(self.occurrence_ids),
            "summary": self.summary,
            "classification_proposals": list(self.classification_proposals),
            "analysis_positions": list(self.analysis_positions),
            "coverage_boundary": self.coverage_boundary,
            "failure_boundary": self.failure_boundary,
        }
        if self.query_ids or self.attempt_ids or self.material_refs or self.body_digests or self.gap_ids:
            result.update({
                "query_ids": list(self.query_ids),
                "attempt_ids": list(self.attempt_ids),
                "material_refs": list(self.material_refs),
                "body_digests": list(self.body_digests),
                "gap_ids": list(self.gap_ids),
            })
        return result


@dataclass(frozen=True, slots=True)
class ProposalGap:
    gap_id: str
    facet_ref: str
    description: str
    source_attempt_ids: tuple[str, ...] = ()
    source_occurrence_ids: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "facet_ref": self.facet_ref,
            "description": self.description,
            "source_attempt_ids": list(self.source_attempt_ids),
            "source_occurrence_ids": list(self.source_occurrence_ids),
        }


@dataclass(frozen=True, slots=True)
class ProposalFrontier:
    frontier_id: str
    facet_ref: str
    proposed_query: str
    reason: str
    source_digest_ids: tuple[str, ...] = ()
    source_gap_ids: tuple[str, ...] = ()
    source_occurrence_ids: tuple[str, ...] = ()
    parent_digest_id: str = ""
    gap_id: str = ""
    outline_section: str = ""
    target_edge: str = ""

    def to_mapping(self) -> dict[str, Any]:
        result = {
            "frontier_id": self.frontier_id,
            "facet_ref": self.facet_ref,
            "proposed_query": self.proposed_query,
            "reason": self.reason,
            "source_digest_ids": list(self.source_digest_ids),
            "source_gap_ids": list(self.source_gap_ids),
            "source_occurrence_ids": list(self.source_occurrence_ids),
        }
        if any((self.parent_digest_id, self.gap_id, self.outline_section, self.target_edge)):
            result.update({
                "parent_digest_id": self.parent_digest_id,
                "gap_id": self.gap_id,
                "outline_section": self.outline_section,
                "target_edge": self.target_edge,
            })
        return result


@dataclass(frozen=True, slots=True)
class RapidProposal:
    proposal_id: str
    proposal_version: str
    facets: tuple[ProposalFacet, ...]
    queries: tuple[ProposalQuery, ...]
    snapshots: tuple[ProposalSnapshot, ...]
    attempts: tuple[ProposalAttempt, ...]
    occurrences: tuple[ProposalOccurrence, ...]
    digests: tuple[ProposalDigest, ...]
    gaps: tuple[ProposalGap, ...]
    frontier: tuple[ProposalFrontier, ...]
    claim_ceiling: str = RAPID_PROPOSAL_CLAIM_CEILING
    contract_version: str = RAPID_PROPOSAL_CONTRACT_VERSION

    @property
    def identity(self) -> str:
        return f"{self.proposal_id}@{self.proposal_version}"

    @property
    def content_digest(self) -> str:
        return _digest(self.to_mapping())

    def to_mapping(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "proposal_id": self.proposal_id,
            "proposal_version": self.proposal_version,
            "claim_ceiling": self.claim_ceiling,
            "facets": [item.to_mapping() for item in self.facets],
            "queries": [item.to_mapping() for item in self.queries],
            "snapshots": [item.to_mapping() for item in self.snapshots],
            "attempts": [item.to_mapping() for item in self.attempts],
            "occurrences": [item.to_mapping() for item in self.occurrences],
            "digests": [item.to_mapping() for item in self.digests],
            "gaps": [item.to_mapping() for item in self.gaps],
            "frontier": [item.to_mapping() for item in self.frontier],
        }

    def validate(self) -> Failure | None:
        if (
            self.contract_version != RAPID_PROPOSAL_CONTRACT_VERSION
            or self.claim_ceiling != RAPID_PROPOSAL_CLAIM_CEILING
            or not _nonempty(self.proposal_id)
            or not _nonempty(self.proposal_version)
        ):
            return rapid_proposal_failures.fail(
                "INVALID_PROPOSAL",
                "proposal identity, contract version and expansion-proposal ceiling are required",
            )

        collections: tuple[tuple[str, Sequence[Any], str], ...] = (
            ("facet", self.facets, "facet_ref"),
            ("query", self.queries, "query_id"),
            ("snapshot", self.snapshots, "snapshot_ref"),
            ("attempt", self.attempts, "attempt_id"),
            ("occurrence", self.occurrences, "occurrence_id"),
            ("digest", self.digests, "digest_id"),
            ("gap", self.gaps, "gap_id"),
            ("frontier", self.frontier, "frontier_id"),
        )
        indexes: dict[str, dict[str, Any]] = {}
        for name, values, key in collections:
            index: dict[str, Any] = {}
            for item in values:
                identity = getattr(item, key)
                if not _nonempty(identity) or identity in index:
                    return rapid_proposal_failures.fail(
                        "INVALID_PROPOSAL", f"{name} identities must be nonempty and unique"
                    )
                index[identity] = item
            indexes[name] = index

        if not indexes["facet"] or not indexes["query"] or not indexes["attempt"]:
            return rapid_proposal_failures.fail(
                "SOURCE_CLOSURE_INCOMPLETE", "proposal needs a facet, query and observed attempt"
            )
        for facet in self.facets:
            if not _nonempty(facet.source_ref):
                return rapid_proposal_failures.fail("SOURCE_CLOSURE_INCOMPLETE", "facet source is missing")
        for query in self.queries:
            if query.facet_ref not in indexes["facet"] or not _nonempty(query.expression):
                return rapid_proposal_failures.fail("SOURCE_CLOSURE_INCOMPLETE", "query is not closed over a facet")
        for snapshot in self.snapshots:
            if not _nonempty(snapshot.content_digest) or not _nonempty(snapshot.source_ref):
                return rapid_proposal_failures.fail("SOURCE_CLOSURE_INCOMPLETE", "snapshot source or digest is missing")
        allowed_outcomes = {"hit", "miss", "access_failed", "off_topic", "partial", "unknown"}
        for attempt in self.attempts:
            if (
                attempt.query_id not in indexes["query"]
                or attempt.outcome not in allowed_outcomes
                or any(ref not in indexes["snapshot"] for ref in attempt.snapshot_refs)
                or (attempt.outcome in {"hit", "partial"} and not attempt.snapshot_refs)
            ):
                return rapid_proposal_failures.fail("SOURCE_CLOSURE_INCOMPLETE", "attempt source closure is invalid")
        for occurrence in self.occurrences:
            query = indexes["query"].get(occurrence.query_id)
            attempt = indexes["attempt"].get(occurrence.attempt_id)
            if (
                occurrence.facet_ref not in indexes["facet"]
                or query is None
                or query.facet_ref != occurrence.facet_ref
                or attempt is None
                or attempt.query_id != occurrence.query_id
                or occurrence.snapshot_ref not in indexes["snapshot"]
                or occurrence.snapshot_ref not in attempt.snapshot_refs
                or not _nonempty(occurrence.source_ref)
            ):
                return rapid_proposal_failures.fail("SOURCE_CLOSURE_INCOMPLETE", "occurrence source closure is invalid")
        for digest in self.digests:
            extended = bool(digest.query_ids or digest.attempt_ids or digest.material_refs or digest.body_digests or digest.gap_ids)
            if (
                not (digest.occurrence_ids or (extended and digest.attempt_ids))
                or any(ref not in indexes["occurrence"] for ref in digest.occurrence_ids)
                or not all(_nonempty(value) for value in (
                    digest.summary, digest.coverage_boundary, digest.failure_boundary
                ))
                or any(not _nonempty(value) for value in (*digest.classification_proposals, *digest.analysis_positions))
            ):
                return rapid_proposal_failures.fail("SOURCE_CLOSURE_INCOMPLETE", "digest source closure is invalid")
            if extended:
                observed_queries = {indexes["attempt"][ref].query_id for ref in digest.attempt_ids if ref in indexes["attempt"]}
                observed_snapshots = {
                    ref for attempt_id in digest.attempt_ids if attempt_id in indexes["attempt"]
                    for ref in indexes["attempt"][attempt_id].snapshot_refs
                }
                if (
                    not digest.query_ids or not digest.attempt_ids or not digest.gap_ids
                    or any(ref not in indexes["query"] for ref in digest.query_ids)
                    or any(ref not in indexes["attempt"] for ref in digest.attempt_ids)
                    or set(digest.query_ids) != observed_queries
                    or len(digest.material_refs) != len(digest.body_digests)
                    or any(ref not in observed_snapshots for ref in digest.material_refs)
                    or any(
                        ref not in indexes["snapshot"] or indexes["snapshot"][ref].content_digest != body_digest
                        for ref, body_digest in zip(digest.material_refs, digest.body_digests)
                    )
                    or any(ref not in indexes["gap"] for ref in digest.gap_ids)
                    or any(
                        indexes["query"][query_id].facet_ref != indexes["gap"][gap_id].facet_ref
                        for query_id in digest.query_ids for gap_id in digest.gap_ids
                        if query_id in indexes["query"] and gap_id in indexes["gap"]
                    )
                    or any(
                        indexes["occurrence"][ref].attempt_id not in digest.attempt_ids
                        or indexes["occurrence"][ref].snapshot_ref not in digest.material_refs
                        for ref in digest.occurrence_ids if ref in indexes["occurrence"]
                    )
                    or any(
                        not set(indexes["gap"][ref].source_attempt_ids).intersection(digest.attempt_ids)
                        and not set(indexes["gap"][ref].source_occurrence_ids).intersection(digest.occurrence_ids)
                        for ref in digest.gap_ids
                    )
                ):
                    return rapid_proposal_failures.fail("SOURCE_CLOSURE_INCOMPLETE", "extended digest provenance is invalid")
        for gap in self.gaps:
            if (
                gap.facet_ref not in indexes["facet"]
                or not _nonempty(gap.description)
                or not (gap.source_attempt_ids or gap.source_occurrence_ids)
                or any(ref not in indexes["attempt"] for ref in gap.source_attempt_ids)
                or any(ref not in indexes["occurrence"] for ref in gap.source_occurrence_ids)
            ):
                return rapid_proposal_failures.fail("SOURCE_CLOSURE_INCOMPLETE", "gap source closure is invalid")
        for item in self.frontier:
            if (
                item.facet_ref not in indexes["facet"]
                or not _nonempty(item.proposed_query)
                or not _nonempty(item.reason)
                or not (item.source_digest_ids or item.source_gap_ids or item.source_occurrence_ids)
                or any(ref not in indexes["digest"] for ref in item.source_digest_ids)
                or any(ref not in indexes["gap"] for ref in item.source_gap_ids)
                or any(ref not in indexes["occurrence"] for ref in item.source_occurrence_ids)
            ):
                return rapid_proposal_failures.fail("SOURCE_CLOSURE_INCOMPLETE", "frontier source closure is invalid")
            if any((item.parent_digest_id, item.gap_id, item.outline_section, item.target_edge)):
                digest = indexes["digest"].get(item.parent_digest_id)
                gap = indexes["gap"].get(item.gap_id)
                if (
                    digest is None or gap is None
                    or item.parent_digest_id not in item.source_digest_ids
                    or item.gap_id not in item.source_gap_ids
                    or item.gap_id not in digest.gap_ids
                    or gap.facet_ref != item.facet_ref
                    or not _nonempty(item.outline_section)
                    or not _nonempty(item.target_edge)
                ):
                    return rapid_proposal_failures.fail("SOURCE_CLOSURE_INCOMPLETE", "frontier continuation basis is invalid")
        return None


def _parse_rows(
    raw: Mapping[str, Any],
    key: str,
    fields: set[str],
    factory: Callable[..., Any],
    tuple_fields: tuple[str, ...] = (),
    optional_fields: set[str] = frozenset(),
) -> tuple[Any, ...] | Failure:
    rows = raw.get(key)
    if not isinstance(rows, list):
        return rapid_proposal_failures.fail("INVALID_PROPOSAL", f"{key} must be an array")
    parsed: list[Any] = []
    for row in rows:
        if not isinstance(row, Mapping) or not fields.issubset(row) or not set(row).issubset(fields | optional_fields):
            return rapid_proposal_failures.fail("INVALID_PROPOSAL", f"{key} row has missing or unknown fields")
        values = dict(row)
        for field in tuple_fields:
            if field not in values:
                continue
            converted = _strings(values[field])
            if converted is None:
                return rapid_proposal_failures.fail("INVALID_PROPOSAL", f"{key}.{field} must be a string array")
            values[field] = converted
        try:
            parsed.append(factory(**values))
        except (TypeError, ValueError) as exc:
            return rapid_proposal_failures.fail("INVALID_PROPOSAL", f"invalid {key} row", {"reason": str(exc)})
    return tuple(parsed)


def rapid_proposal_from_mapping(raw: object) -> RapidProposal | Failure:
    if not isinstance(raw, Mapping):
        return rapid_proposal_failures.fail("INVALID_PROPOSAL", "proposal must be an object")
    expected = {
        "contract_version", "proposal_id", "proposal_version", "claim_ceiling",
        "facets", "queries", "snapshots", "attempts", "occurrences", "digests", "gaps", "frontier",
    }
    if set(raw) != expected:
        return rapid_proposal_failures.fail("INVALID_PROPOSAL", "proposal has missing or unknown fields")
    definitions = (
        ("facets", {"facet_ref", "source_ref"}, ProposalFacet, (), set()),
        ("queries", {"query_id", "facet_ref", "expression"}, ProposalQuery, (), set()),
        ("snapshots", {"snapshot_ref", "content_digest", "source_ref"}, ProposalSnapshot, (), set()),
        ("attempts", {"attempt_id", "query_id", "outcome", "snapshot_refs"}, ProposalAttempt, ("snapshot_refs",), set()),
        ("occurrences", {"occurrence_id", "facet_ref", "query_id", "attempt_id", "snapshot_ref", "source_ref"}, ProposalOccurrence, (), set()),
        ("digests", {"digest_id", "occurrence_ids", "summary", "classification_proposals", "analysis_positions", "coverage_boundary", "failure_boundary"}, ProposalDigest, ("occurrence_ids", "classification_proposals", "analysis_positions", "query_ids", "attempt_ids", "material_refs", "body_digests", "gap_ids"), {"query_ids", "attempt_ids", "material_refs", "body_digests", "gap_ids"}),
        ("gaps", {"gap_id", "facet_ref", "description", "source_attempt_ids", "source_occurrence_ids"}, ProposalGap, ("source_attempt_ids", "source_occurrence_ids"), set()),
        ("frontier", {"frontier_id", "facet_ref", "proposed_query", "reason", "source_digest_ids", "source_gap_ids", "source_occurrence_ids"}, ProposalFrontier, ("source_digest_ids", "source_gap_ids", "source_occurrence_ids"), {"parent_digest_id", "gap_id", "outline_section", "target_edge"}),
    )
    parsed: dict[str, tuple[Any, ...]] = {}
    for key, fields, factory, tuple_fields, optional_fields in definitions:
        rows = _parse_rows(raw, key, fields, factory, tuple_fields, optional_fields)
        if isinstance(rows, Failure):
            return rows
        parsed[key] = rows
    proposal = RapidProposal(
        proposal_id=raw["proposal_id"],
        proposal_version=raw["proposal_version"],
        claim_ceiling=raw["claim_ceiling"],
        contract_version=raw["contract_version"],
        **parsed,
    )
    invalid = proposal.validate()
    return invalid if invalid is not None else proposal


def rapid_proposal_element(
    project_key: str,
    proposal: RapidProposal,
    *,
    module_id: str = RAPID_PROPOSAL_MODULE_ID,
    namespace: str = RAPID_PROPOSAL_NAMESPACE,
) -> Element | Failure:
    invalid = proposal.validate()
    if invalid is not None:
        return invalid
    digest = proposal.content_digest
    return Element(
        BoundRef(
            ElementRef(project_key, module_id, namespace, "rapid_proposal", proposal.identity),
            proposal.proposal_version,
            digest,
        ),
        {
            "contract_version": proposal.contract_version,
            "proposal_version": proposal.proposal_version,
            "claim_ceiling": proposal.claim_ceiling,
            "content_digest": digest,
            "payload": proposal.to_mapping(),
        },
    )


def validate_persisted_proposal_attributes(attributes: Mapping[str, Any]) -> str | None:
    expected = {"contract_version", "proposal_version", "claim_ceiling", "content_digest", "payload"}
    if set(attributes) != expected:
        return "rapid proposal attributes are incomplete or unknown"
    proposal = rapid_proposal_from_mapping(attributes.get("payload"))
    if isinstance(proposal, Failure):
        return proposal.message
    if (
        attributes["contract_version"] != proposal.contract_version
        or attributes["proposal_version"] != proposal.proposal_version
        or attributes["claim_ceiling"] != RAPID_PROPOSAL_CLAIM_CEILING
        or attributes["content_digest"] != proposal.content_digest
    ):
        return "rapid proposal envelope differs from its payload"
    return None


ProposalSaveStatus = Literal["persisted", "already_persisted", "conflict", "failed", "unknown"]


@dataclass(frozen=True, slots=True)
class ProposalSaveObservation:
    status: ProposalSaveStatus
    proposal_id: str
    proposal_version: str
    content_digest: str
    topology_ref: Mapping[str, Any]
    revision: int | None = None
    topology_digest: str | None = None
    readback_status: Literal["verified", "not_found", "mismatch", "unavailable", "not_attempted"] = "not_attempted"
    failure: Mapping[str, Any] | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "proposal_id": self.proposal_id,
            "proposal_version": self.proposal_version,
            "content_digest": self.content_digest,
            "topology_ref": dict(self.topology_ref),
            "revision": self.revision,
            "topology_digest": self.topology_digest,
            "readback_status": self.readback_status,
            "failure": dict(self.failure) if self.failure is not None else None,
        }


def _failure_wire(failure: Failure | BaseException, *, fallback_code: str) -> dict[str, Any]:
    if isinstance(failure, Failure):
        return {
            "family": failure.family,
            "code": failure.code,
            "message": failure.message,
            "context": dict(failure.context or {}),
        }
    return {"family": "exception", "code": fallback_code, "message": str(failure), "context": {}}


class RapidProposalTopologyAdapter:
    """One-proposal-per-state adapter over the existing topology service.

    A deterministic state identity supplies idempotency.  Conflicts are read
    once to distinguish a same-payload race from a different payload; writes are
    never blindly replayed after an unknown effect.
    """

    def __init__(self, topology_service: Any):
        self.topology_service = topology_service

    @staticmethod
    def target(proposal_id: str, proposal_version: str) -> dict[str, Any]:
        return {
            "module_id": RAPID_PROPOSAL_MODULE_ID,
            "namespace": RAPID_PROPOSAL_NAMESPACE,
            "state_id": f"{proposal_id}@{proposal_version}",
        }

    def read(self, project_key: str, proposal_id: str, proposal_version: str) -> RapidProposal | Failure:
        target = self.target(proposal_id, proposal_version)
        try:
            result = self.topology_service.read_topology(project_key, target, {"type_ids": ["rapid_proposal"]})
        except Exception as exc:
            return rapid_proposal_failures.fail("PERSISTENCE_UNKNOWN", "proposal readback failed", {"reason": str(exc)})
        if isinstance(result, Failure):
            if result.code == "NOT_FOUND":
                return rapid_proposal_failures.fail("NOT_FOUND", "rapid proposal was not found", {"topology_ref": target})
            return result
        elements = result.get("topology", {}).get("elements", []) if isinstance(result, Mapping) else []
        if len(elements) != 1 or not isinstance(elements[0], Mapping):
            return rapid_proposal_failures.fail("READBACK_MISMATCH", "proposal readback has no unique proposal element")
        attributes = elements[0].get("attributes")
        if not isinstance(attributes, Mapping):
            return rapid_proposal_failures.fail("READBACK_MISMATCH", "proposal readback attributes are missing")
        error = validate_persisted_proposal_attributes(attributes)
        if error is not None:
            return rapid_proposal_failures.fail("READBACK_MISMATCH", error)
        proposal = rapid_proposal_from_mapping(attributes["payload"])
        if isinstance(proposal, Failure):
            return rapid_proposal_failures.fail("READBACK_MISMATCH", proposal.message)
        if (proposal.proposal_id, proposal.proposal_version) != (proposal_id, proposal_version):
            return rapid_proposal_failures.fail("READBACK_MISMATCH", "readback proposal identity differs")
        return proposal

    def save(
        self,
        project_key: str,
        proposal: RapidProposal,
        vocabulary: DomainVocabulary,
    ) -> ProposalSaveObservation:
        target = self.target(proposal.proposal_id, proposal.proposal_version)
        invalid = proposal.validate()
        if invalid is not None:
            return self._observation("failed", proposal, target, failure=invalid)
        if vocabulary.source_ref.ref.project_key != project_key:
            failure = rapid_proposal_failures.fail(
                "CROSS_PROJECT_REFERENCE", "proposal vocabulary belongs to another project"
            )
            return self._observation("failed", proposal, target, failure=failure)

        existing = self.read(project_key, proposal.proposal_id, proposal.proposal_version)
        if not isinstance(existing, Failure):
            status: ProposalSaveStatus = "already_persisted" if existing.content_digest == proposal.content_digest else "conflict"
            failure = None if status == "already_persisted" else rapid_proposal_failures.fail(
                "VERSION_CONFLICT", "proposal identity already has different contents"
            )
            return self._observation(status, proposal, target, readback_status="verified", failure=failure)
        if existing.code != "NOT_FOUND":
            status = "unknown" if existing.code == "PERSISTENCE_UNKNOWN" else "failed"
            return self._observation(status, proposal, target, readback_status="unavailable", failure=existing)

        try:
            profile = make_rapid_proposal_profile(vocabulary)
            proposal_element = rapid_proposal_element(project_key, proposal)
            if isinstance(proposal_element, Failure):
                return self._observation("failed", proposal, target, failure=proposal_element)
            state = TopologyState(
                profile.profile_id,
                profile.version,
                (domain_vocabulary_element(vocabulary), proposal_element),
            )
            initial = {
                "profile_id": state.profile_id,
                "profile_version": state.profile_version,
                "elements": [
                    {
                        "ref": {
                            "ref": {
                                "project_key": element.ref.ref.project_key,
                                "module_id": element.ref.ref.module_id,
                                "namespace": element.ref.ref.namespace,
                                "type_id": element.ref.ref.type_id,
                                "local_id": element.ref.ref.local_id,
                            },
                            "observed_revision": element.ref.observed_revision,
                            "content_digest": element.ref.content_digest,
                        },
                        "attributes": dict(element.attributes),
                        "endpoints": [],
                    }
                    for element in state.elements
                ],
            }
            written = self.topology_service.apply_batch(
                project_key,
                state_patches=({"target": target, "initial_state": initial, "patch": []},),
                link_writes=(),
                read_set=(),
                link_read_set=(),
            )
        except Exception as exc:
            failure = rapid_proposal_failures.fail(
                "PERSISTENCE_UNKNOWN", "proposal write outcome is unknown", {"reason": str(exc), "topology_ref": target}
            )
            return self._observation("unknown", proposal, target, readback_status="unavailable", failure=failure)

        if isinstance(written, Failure):
            if written.code in {"VERSION_CONFLICT", "IDENTITY_CONFLICT"}:
                raced = self.read(project_key, proposal.proposal_id, proposal.proposal_version)
                if not isinstance(raced, Failure) and raced.content_digest == proposal.content_digest:
                    return self._observation("already_persisted", proposal, target, readback_status="verified")
                return self._observation("conflict", proposal, target, readback_status="mismatch", failure=written)
            return self._observation("failed", proposal, target, failure=written)

        state_revisions = written.get("state_revisions") if isinstance(written, Mapping) else None
        if not isinstance(state_revisions, list) or len(state_revisions) != 1:
            failure = rapid_proposal_failures.fail(
                "PERSISTENCE_UNKNOWN", "writer did not return a unique saved state identity", {"topology_ref": target}
            )
            return self._observation("unknown", proposal, target, readback_status="not_attempted", failure=failure)
        revision = state_revisions[0].get("revision")
        readback = self.read(project_key, proposal.proposal_id, proposal.proposal_version)
        if isinstance(readback, Failure):
            failure = rapid_proposal_failures.fail(
                "PERSISTENCE_UNKNOWN",
                "writer returned but proposal readback is unverified",
                {"readback_code": readback.code, "topology_ref": target},
            )
            return self._observation(
                "unknown", proposal, target, revision=revision, readback_status="unavailable", failure=failure
            )
        if readback.content_digest != proposal.content_digest:
            failure = rapid_proposal_failures.fail("READBACK_MISMATCH", "saved proposal digest differs on readback")
            return self._observation(
                "unknown", proposal, target, revision=revision, readback_status="mismatch", failure=failure
            )
        topology_digest = state_revisions[0].get("topology", {}).get("digest")
        return self._observation(
            "persisted",
            proposal,
            target,
            revision=revision,
            topology_digest=topology_digest,
            readback_status="verified",
        )

    @staticmethod
    def _observation(
        status: ProposalSaveStatus,
        proposal: RapidProposal,
        target: Mapping[str, Any],
        *,
        revision: int | None = None,
        topology_digest: str | None = None,
        readback_status: Literal["verified", "not_found", "mismatch", "unavailable", "not_attempted"] = "not_attempted",
        failure: Failure | BaseException | None = None,
    ) -> ProposalSaveObservation:
        return ProposalSaveObservation(
            status=status,
            proposal_id=proposal.proposal_id,
            proposal_version=proposal.proposal_version,
            content_digest=proposal.content_digest,
            topology_ref=dict(target),
            revision=revision,
            topology_digest=topology_digest,
            readback_status=readback_status,
            failure=_failure_wire(failure, fallback_code="PERSISTENCE_FAILED") if failure is not None else None,
        )


VocabularyResolver = Callable[[str], DomainVocabulary | Failure]


__all__ = [
    "ProposalAttempt",
    "ProposalDigest",
    "ProposalFacet",
    "ProposalFrontier",
    "ProposalGap",
    "ProposalOccurrence",
    "ProposalQuery",
    "ProposalSaveObservation",
    "ProposalSnapshot",
    "RAPID_PROPOSAL_CLAIM_CEILING",
    "RAPID_PROPOSAL_CONTRACT_VERSION",
    "RapidProposal",
    "RapidProposalTopologyAdapter",
    "VocabularyResolver",
    "rapid_proposal_element",
    "rapid_proposal_failures",
    "rapid_proposal_from_mapping",
    "validate_persisted_proposal_attributes",
]
