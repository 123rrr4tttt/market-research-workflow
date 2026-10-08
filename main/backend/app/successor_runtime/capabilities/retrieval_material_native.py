"""Shared typed state and leaf declarations for formal project retrieval.

One ``CandidateWork`` value crosses review, URL acquisition, authoritative body
read, formalization and source revalidation. ``RetrievalControl`` carries only
bounded follow-up and topology decisions; the Runtime journal remains the
consumption and completion evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from typing import Annotated, Generic, Literal, overload, TypeVar

from app.successor_runtime.capabilities.checksum import (
    CanonicalJsonArray,  # noqa: F401 - resolved by dataclass_codec get_type_hints
    CanonicalJsonObject,
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.capabilities.codecs import PayloadCodec, dataclass_codec
from app.successor_runtime.capabilities.profiles import OperationProfiles, build_operation_profiles
from app.successor_runtime.capabilities.retrieval_common import raise_retrieval_contract_error
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    OperationContract,
    OperationContractRef,
)
from app.successor_runtime.language.program import sequence_object_type
from app.successor_runtime.research.object_types import ObjectType

_CANONICAL_JSON_ARRAY_TYPE = CanonicalJsonArray

CandidateStage = Literal["candidate", "reviewed", "ingested", "body_read", "formalized", "revalidated"]
CandidateDisposition = Literal[
    "pending",
    "approved",
    "deferred",
    "rejected",
    "budget_exhausted",
    "ingest_failed",
    "body_missing",
    "body_failed",
    "proposed",
    "no_claim",
    "formalization_failed",
    "ready",
    "source_changed",
]
ControlState = Literal["request", "planned", "skipped", "topology_committed", "topology_failed"]

CANDIDATE_WORK_CODEC_ID = "project_retrieval.candidate-work.v1"
RETRIEVAL_CONTROL_CODEC_ID = "project_retrieval.control.v1"
CANDIDATE_WORK_TYPE = ObjectType(
    "CandidateWork.v1", codec_id=CANDIDATE_WORK_CODEC_ID, canonical_codec_version="1"
)
RETRIEVAL_CONTROL_TYPE = ObjectType(
    "RetrievalControl.v1", codec_id=RETRIEVAL_CONTROL_CODEC_ID, canonical_codec_version="1"
)
CANDIDATE_WORK_SEQUENCE_TYPE = sequence_object_type(CANDIDATE_WORK_TYPE, version="2")

RETRIEVAL_CANDIDATE_REVIEW_KIND = "project_retrieval.candidate.review.v1"
RETRIEVAL_MATERIAL_READ_BODY_KIND = "project_retrieval.material.read_body.v1"
RETRIEVAL_MATERIAL_FORMALIZE_KIND = "project_retrieval.material.formalize.v1"
RETRIEVAL_MATERIAL_REVALIDATE_KIND = "project_retrieval.material.revalidate.v1"
RETRIEVAL_FOLLOWUP_PLAN_KIND = "project_retrieval.followup.plan.v1"
RETRIEVAL_TOPOLOGY_COMMIT_KIND = "project_retrieval.topology.commit.v1"

WorkLeafKind = Literal[
    "project_retrieval.candidate.review.v1",
    "project_retrieval.material.read_body.v1",
    "project_retrieval.material.formalize.v1",
    "project_retrieval.material.revalidate.v1",
]
ControlLeafKind = Literal[
    "project_retrieval.followup.plan.v1",
    "project_retrieval.topology.commit.v1",
]
WORK_LEAF_KINDS: tuple[WorkLeafKind, ...] = (
    RETRIEVAL_CANDIDATE_REVIEW_KIND,
    RETRIEVAL_MATERIAL_READ_BODY_KIND,
    RETRIEVAL_MATERIAL_FORMALIZE_KIND,
    RETRIEVAL_MATERIAL_REVALIDATE_KIND,
)
CONTROL_LEAF_KINDS: tuple[ControlLeafKind, ...] = (
    RETRIEVAL_FOLLOWUP_PLAN_KIND, RETRIEVAL_TOPOLOGY_COMMIT_KIND,
)
RETRIEVAL_LEAF_KINDS = WORK_LEAF_KINDS + CONTROL_LEAF_KINDS


def _empty_object() -> CanonicalJsonObject:
    return {}


@dataclass(frozen=True, slots=True)
class CandidateWork:
    project_key: str
    root_run_id: str
    retrieval_budget_id: str
    plan_id: str
    mode_version: str
    route_id: str
    query_id: str
    query_kind: Literal["initial", "followup"]
    query_ordinal: int
    followup_round: int
    candidate_ordinal: int
    candidate_id: str
    material_budget_remaining: int
    candidate: CanonicalJsonObject
    stage: CandidateStage = "candidate"
    disposition: CandidateDisposition = "pending"
    review: CanonicalJsonObject | None = None
    ingest: CanonicalJsonObject | None = None
    body: CanonicalJsonObject | None = None
    body_text: str | None = None
    formalization: CanonicalJsonObject | None = None
    error: CanonicalJsonObject | None = None
    gaps: tuple[CanonicalJsonObject, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        identities = (
            self.project_key,
            self.root_run_id,
            self.retrieval_budget_id,
            self.plan_id,
            self.mode_version,
            self.route_id,
            self.query_id,
            self.candidate_id,
        )
        if any(not value.strip() for value in identities):
            raise_retrieval_contract_error(ValueError, 'candidate work identities must be nonempty')
        if self.query_kind not in {"initial", "followup"}:
            raise_retrieval_contract_error(ValueError, 'candidate work query kind is invalid')
        if type(self.query_ordinal) is not int or self.query_ordinal < 1:
            raise_retrieval_contract_error(ValueError, 'candidate work query ordinal must be positive')
        if type(self.followup_round) is not int or self.followup_round < 0:
            raise_retrieval_contract_error(ValueError, 'candidate work followup round must be nonnegative')
        if self.query_kind == "initial" and self.followup_round != 0:
            raise_retrieval_contract_error(ValueError, 'initial candidate work cannot carry a followup round')
        if self.query_kind == "followup" and self.followup_round < 1:
            raise_retrieval_contract_error(ValueError, 'followup candidate work requires a positive round')
        if type(self.candidate_ordinal) is not int or self.candidate_ordinal < 1:
            raise_retrieval_contract_error(ValueError, 'candidate work ordinal must be positive')
        if type(self.material_budget_remaining) is not int or self.material_budget_remaining < 0:
            raise_retrieval_contract_error(
                ValueError,
                "candidate work material budget must be a nonnegative integer",
            )
        url = str(self.candidate.get("url") or self.candidate.get("resource_uri") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise_retrieval_contract_error(ValueError, 'candidate work requires an http(s) URL')
        if self.body_text is not None and not self.body_text.strip():
            raise_retrieval_contract_error(ValueError, 'candidate work body text must be nonempty when present')
        stage_contracts = {
            "candidate": ({"pending"}, ()),
            "reviewed": ({"approved", "deferred", "rejected", "budget_exhausted"}, ("review",)),
            "ingested": ({"approved", "ingest_failed"}, ("review", "ingest")),
            "body_read": ({"approved", "body_missing", "body_failed"}, ("review", "ingest", "body")),
            "formalized": (
                {"proposed", "no_claim", "formalization_failed"},
                ("review", "ingest", "body", "formalization"),
            ),
            "revalidated": (
                {"ready", "source_changed", "no_claim", "formalization_failed"},
                ("review", "ingest", "body", "formalization"),
            ),
        }
        allowed_dispositions, required_receipts = stage_contracts[self.stage]
        if self.disposition not in allowed_dispositions:
            raise_retrieval_contract_error(ValueError, 'candidate work stage has an invalid disposition')
        for name in ("review", "ingest", "body", "formalization"):
            if (name in required_receipts) != isinstance(getattr(self, name), dict):
                raise_retrieval_contract_error(ValueError, 'candidate work stage lacks its exact receipt prefix')
        if self.disposition in {"proposed", "ready"} and self.formalization is None:
            raise_retrieval_contract_error(ValueError, 'proposed candidate work requires a formalization receipt')
        if self.disposition == "ready" and (self.body is None or self.body_text is None):
            raise_retrieval_contract_error(ValueError, 'ready candidate work requires its exact body receipt')


@dataclass(frozen=True, slots=True)
class RetrievalControl:
    project_key: str
    root_run_id: str
    retrieval_budget_id: str
    plan_id: str
    mode_version: str
    route_id: str
    round: int
    plan_snapshot: CanonicalJsonObject
    state: ControlState = "request"
    planned_query: CanonicalJsonObject | None = None
    budget: CanonicalJsonObject = field(default_factory=_empty_object)
    topology: CanonicalJsonObject | None = None

    def __post_init__(self) -> None:
        identities = (
            self.project_key,
            self.root_run_id,
            self.retrieval_budget_id,
            self.plan_id,
            self.mode_version,
            self.route_id,
        )
        if any(not value.strip() for value in identities):
            raise_retrieval_contract_error(ValueError, 'retrieval control identities must be nonempty')
        if type(self.round) is not int or not 0 <= self.round <= 2:
            raise_retrieval_contract_error(ValueError, 'retrieval control round must be between zero and two')
        if self.state == "planned" and self.planned_query is None:
            raise_retrieval_contract_error(ValueError, 'planned retrieval control requires a query')
        if self.state != "planned" and self.planned_query is not None:
            raise_retrieval_contract_error(ValueError, 'only planned retrieval control may carry a query')
        if self.state in {"topology_committed", "topology_failed"} and self.topology is None:
            raise_retrieval_contract_error(ValueError, 'settled topology control requires its observation')


LeafPayload = TypeVar("LeafPayload", CandidateWork, RetrievalControl)


@dataclass(frozen=True, slots=True)
class RetrievalLeafDefinition(Generic[LeafPayload]):
    kind: str
    contract: OperationContract
    input_codec: PayloadCodec[LeafPayload]
    output_codec: PayloadCodec[LeafPayload]
    profiles: OperationProfiles


@dataclass(frozen=True, slots=True)
class _LeafFacts:
    reads: tuple[str, ...]
    creates: tuple[str, ...]
    resource_classes: tuple[str, ...]
    concurrency_key: str
    network_required: bool
    credential_ref: str | None
    irreversible: bool
    typed_failures: tuple[str, ...]
    degraded_acceptable: bool
    unknown_outcome_supported: bool
    readback: str
    dependency: str
    observation_dimensions: tuple[str, ...]


_LEAF_FACTS: dict[str, _LeafFacts] = {
    RETRIEVAL_CANDIDATE_REVIEW_KIND: _LeafFacts(
        (CANDIDATE_WORK_TYPE.type_id, "source.candidate.review.v1"),
        (CANDIDATE_WORK_TYPE.type_id,),
        ("NETWORK_IO",),
        "project:retrieval-candidate",
        True,
        None,
        False,
        ("INVALID_INPUT", "REVIEW_DECISION_FAILED"),
        True,
        False,
        "runtime_typed_output",
        "services.project_retrieval.execution.review_candidate_work",
        ("candidate_id", "decision", "review_key", "review_artifact_ref"),
    ),
    RETRIEVAL_MATERIAL_READ_BODY_KIND: _LeafFacts(
        (CANDIDATE_WORK_TYPE.type_id, "models.entities.Document"),
        (CANDIDATE_WORK_TYPE.type_id,),
        ("CPU_LIGHT",),
        "project:document",
        False,
        None,
        False,
        ("INVALID_INPUT", "DOCUMENT_NOT_FOUND", "DOCUMENT_BODY_EMPTY", "DOCUMENT_READ_FAILED"),
        True,
        False,
        "document_readback",
        "services.project_retrieval.execution.read_candidate_work_body",
        ("candidate_id", "document_id", "body_digest", "document_updated_at"),
    ),
    RETRIEVAL_MATERIAL_FORMALIZE_KIND: _LeafFacts(
        (CANDIDATE_WORK_TYPE.type_id, "project_retrieval.formalize_material"),
        (CANDIDATE_WORK_TYPE.type_id,),
        ("LLM_CALL",),
        "project:retrieval-formalization",
        True,
        "formalization_provider",
        False,
        ("INVALID_INPUT", "FORMALIZATION_FAILED", "PROVIDER_FAILED"),
        True,
        True,
        "runtime_typed_output",
        "services.project_retrieval.execution.formalize_candidate_work",
        ("candidate_id", "formalization_status", "provider_calls", "gap_count"),
    ),
    RETRIEVAL_MATERIAL_REVALIDATE_KIND: _LeafFacts(
        (CANDIDATE_WORK_TYPE.type_id, "models.entities.Document"),
        (CANDIDATE_WORK_TYPE.type_id,),
        ("CPU_LIGHT",),
        "project:document",
        False,
        None,
        False,
        ("INVALID_INPUT", "DOCUMENT_NOT_FOUND", "SOURCE_CHANGED", "DOCUMENT_READ_FAILED"),
        True,
        False,
        "document_readback",
        "services.project_retrieval.execution.revalidate_candidate_work",
        ("candidate_id", "document_id", "body_digest", "disposition"),
    ),
    RETRIEVAL_FOLLOWUP_PLAN_KIND: _LeafFacts(
        (RETRIEVAL_CONTROL_TYPE.type_id, "runtime_journal", "source.discovery.plan"),
        (RETRIEVAL_CONTROL_TYPE.type_id,),
        ("CPU_LIGHT",),
        "project:retrieval-root",
        False,
        None,
        False,
        ("INVALID_INPUT", "JOURNAL_READ_FAILED", "FOLLOWUP_PLAN_FAILED"),
        True,
        False,
        "runtime_journal",
        "services.project_retrieval.execution.plan_retrieval_followup",
        ("round", "state", "queries_attempted", "materials_accepted", "gap_count"),
    ),
    RETRIEVAL_TOPOLOGY_COMMIT_KIND: _LeafFacts(
        (RETRIEVAL_CONTROL_TYPE.type_id, "runtime_journal", "information_topology"),
        (RETRIEVAL_CONTROL_TYPE.type_id, "information_topology"),
        ("DB_WRITE",),
        "project:information-topology",
        False,
        None,
        True,
        ("INVALID_INPUT", "JOURNAL_READ_FAILED", "TOPOLOGY_COMMIT_FAILED", "TOPOLOGY_READBACK_FAILED"),
        False,
        True,
        "information_topology_readback",
        "services.project_retrieval.execution.commit_retrieval_topology",
        ("state", "attempt_count", "formal_graph_count", "state_digest", "state_revision"),
    ),
}


def _leaf_types(kind: str) -> tuple[ObjectType, ObjectType, str]:
    if kind in WORK_LEAF_KINDS:
        return CANDIDATE_WORK_TYPE, CANDIDATE_WORK_TYPE, CANDIDATE_WORK_CODEC_ID
    if kind in CONTROL_LEAF_KINDS:
        return RETRIEVAL_CONTROL_TYPE, RETRIEVAL_CONTROL_TYPE, RETRIEVAL_CONTROL_CODEC_ID
    raise_retrieval_contract_error(KeyError, f'unknown retrieval leaf kind: {kind}')


@cache
def build_retrieval_leaf_profiles(kind: str) -> Annotated[
    OperationProfiles,
    "kit:non-authoritative derived_as=view fact_source=retrieval_leaf_facts+kind witness=test:test_root_and_candidate_work_have_one_semantic_return",
]:
    facts = _LEAF_FACTS[kind]
    _, _, codec_id = _leaf_types(kind)
    observation_ref = f"{kind}.observation.v1"
    return build_operation_profiles(
        identity=kind,
        semantic={
            "reads": facts.reads,
            "creates": facts.creates,
            "creates_relations": (),
            "declared_loss": (("session_review_artifact_ref",) if kind == RETRIEVAL_CANDIDATE_REVIEW_KIND else ()),
            "observation_profile_ref": observation_ref,
        },
        effect={
            "execution_class": "EFFECTFUL",
            "external_visibility": "INTERNAL_ONLY",
            "network_required": facts.network_required,
            "irreversible": facts.irreversible,
            "cancellation_points": ("step_boundary",),
            "internal_export_only": True,
            "human_approval_required": False,
            "external_acquisition": False,
            "idempotency_profile_ref": "logical_request_id",
        },
        resource={
            "resource_classes": facts.resource_classes,
            "concurrency_key": facts.concurrency_key,
            "budget_units": "retrieval_leaf",
            "default_soft_limit_seconds": 60 if facts.network_required else 10,
            "default_hard_limit_seconds": 180 if facts.network_required else 30,
            "node_profile_selector": "any",
            "budget_ref": "RetrievalBudgetState.v1",
            "deadline_policy_ref": f"{kind}.deadline-policy.v1",
            "node_profile_requirements": ("any",),
            "units": 1,
        },
        failure={
            "typed_failures": facts.typed_failures,
            "retryable": False,
            "degraded_acceptable": facts.degraded_acceptable,
            "unknown_outcome_supported": facts.unknown_outcome_supported,
            "readback_or_compensation": facts.readback,
            "failure_union_ref": f"{kind}.failures.v1",
            "retryable_failure_kinds": (),
            "readback_profile_ref": observation_ref,
            "compensation_profile_ref": None,
        },
        authority={
            "grant_scopes": ("project",),
            "approval_required": False,
            "approval_kinds": (),
            "credential_refs": ((facts.credential_ref,) if facts.credential_ref else ()),
            "canonical_owner": kind,
            "revalidation_points": ("claim_time",),
            "authority_epoch": 1,
        },
        interpreter={
            "supported_contract_kinds": (kind,),
            "supported_contract_refs": (),
            "dependency_digest": content_digest({"interpreter": facts.dependency, "version": "1.0.0"}),
            "security_profile_ref": "mrw.project-retrieval.security.v1",
            "resource_profile_ref": f"{kind}.resource",
            "credential_requirements_ref": facts.credential_ref,
            "cancellation_profile_ref": "step_boundary",
            "idempotency_profile_ref": "logical_request_id",
            "authoritative_readback_profile_ref": observation_ref,
            "receipt_codec_ref": codec_id,
        },
        observation={
            "dimensions": facts.observation_dimensions,
            "compatible_with_legacy": False,
            "observation_schema_ref": observation_ref,
        },
    )


@cache
def build_retrieval_leaf_contract(kind: str) -> Annotated[
    OperationContract,
    "kit:non-authoritative derived_as=view fact_source=retrieval_leaf_profiles+endpoint_types witness=test:test_root_and_candidate_work_have_one_semantic_return",
]:
    input_type, output_type, _ = _leaf_types(kind)
    return build_retrieval_leaf_profiles(kind).contract(
        kind=kind,
        contract_version="1.0.0",
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=kind,
    )


def build_candidate_work_codec(contract_ref: OperationContractRef) -> Annotated[
    PayloadCodec[CandidateWork],
    "kit:non-authoritative derived_as=view fact_source=candidate_work_schema+contract_ref witness=test:test_candidate_work_settlement_binds_exact_input_and_result",
]:
    return dataclass_codec(
        codec_id=CANDIDATE_WORK_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=CANDIDATE_WORK_TYPE.type_id,
        dto_cls=CandidateWork,
    )


def build_retrieval_control_codec(contract_ref: OperationContractRef) -> Annotated[
    PayloadCodec[RetrievalControl],
    "kit:non-authoritative derived_as=view fact_source=retrieval_control_schema+contract_ref witness=test:test_root_and_candidate_work_have_one_semantic_return",
]:
    return dataclass_codec(
        codec_id=RETRIEVAL_CONTROL_CODEC_ID,
        codec_version="1",
        contract_ref=contract_ref,
        payload_type_id=RETRIEVAL_CONTROL_TYPE.type_id,
        dto_cls=RetrievalControl,
    )


@overload
def build_retrieval_leaf_definition(kind: WorkLeafKind) -> Annotated[RetrievalLeafDefinition[CandidateWork], "kit:non-authoritative derived_as=composition fact_source=retrieval_leaf_contract+codec+profiles witness=test:test_root_and_candidate_work_have_one_semantic_return"]: ...


@overload
def build_retrieval_leaf_definition(kind: ControlLeafKind) -> Annotated[RetrievalLeafDefinition[RetrievalControl], "kit:non-authoritative derived_as=composition fact_source=retrieval_leaf_contract+codec+profiles witness=test:test_root_and_candidate_work_have_one_semantic_return"]: ...


@overload
def build_retrieval_leaf_definition(
    kind: str,
) -> Annotated[RetrievalLeafDefinition[CandidateWork] | RetrievalLeafDefinition[RetrievalControl], "kit:non-authoritative derived_as=composition fact_source=retrieval_leaf_contract+codec+profiles witness=test:test_root_and_candidate_work_have_one_semantic_return"]: ...


@cache
def build_retrieval_leaf_definition(kind: str) -> Annotated[
    RetrievalLeafDefinition[CandidateWork] | RetrievalLeafDefinition[RetrievalControl],
    "kit:non-authoritative derived_as=composition fact_source=retrieval_leaf_contract+codec+profiles witness=test:test_root_and_candidate_work_have_one_semantic_return",
]:
    contract = build_retrieval_leaf_contract(kind)
    profiles = build_retrieval_leaf_profiles(kind)
    if kind in WORK_LEAF_KINDS:
        codec = build_candidate_work_codec(contract.ref)
        return RetrievalLeafDefinition(kind, contract, codec, codec, profiles)
    codec = build_retrieval_control_codec(contract.ref)
    return RetrievalLeafDefinition(kind, contract, codec, codec, profiles)


def retrieval_payload_value(
    *,
    value: CandidateWork | RetrievalControl,
    contract_ref: OperationContractRef,
    value_id: str,
    project_key: str,
) -> tuple[ValueRef, bytes]:
    if isinstance(value, CandidateWork):
        codec = build_candidate_work_codec(contract_ref)
        object_type = CANDIDATE_WORK_TYPE
        exact = canonical_json(codec.encode_payload(value)).encode("utf-8")
    else:
        codec = build_retrieval_control_codec(contract_ref)
        object_type = RETRIEVAL_CONTROL_TYPE
        exact = canonical_json(codec.encode_payload(value)).encode("utf-8")
    if value.project_key != project_key:
        raise_retrieval_contract_error(ValueError, 'retrieval payload crosses its project')
    digest = sha256_hex(exact)
    compact_value_id = "retrieval-payload:" + content_digest(
        {
            "schema": "mrw.project-retrieval.payload-identity.v1",
            "declared_value_id": value_id,
            "project_key": project_key,
            "object_type": object_type.type_id,
            "digest": digest,
        }
    )
    ref = ValueRef(
        value_id=compact_value_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=codec.codec_id,
        content_digest=digest,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{compact_value_id}",
        byte_size=len(exact),
        provenance_digest=content_digest(
            {
                "schema": "mrw.project-retrieval.payload-provenance.v1",
                "declared_value_id": value_id,
                "value_id": compact_value_id,
                "digest": digest,
            }
        ),
    )
    return ref, exact


def validate_candidate_work_transition(before: CandidateWork, after: CandidateWork) -> None:
    stages = ("candidate", "reviewed", "ingested", "body_read", "formalized", "revalidated")
    stage_index = {stage: index for index, stage in enumerate(stages)}
    identity_fields = (
        "project_key",
        "root_run_id",
        "retrieval_budget_id",
        "plan_id",
        "mode_version",
        "route_id",
        "query_id",
        "query_kind",
        "query_ordinal",
        "followup_round",
        "candidate_ordinal",
        "candidate_id",
        "material_budget_remaining",
    )
    if any(getattr(before, name) != getattr(after, name) for name in identity_fields):
        raise_retrieval_contract_error(ValueError, 'candidate work transition changed immutable identity')
    if stage_index[after.stage] < stage_index[before.stage]:
        raise_retrieval_contract_error(ValueError, 'candidate work transition moved backward')
    for name in ("review", "ingest", "body", "body_text", "formalization"):
        if getattr(before, name) is not None and getattr(after, name) != getattr(before, name):
            raise_retrieval_contract_error(ValueError, 'candidate work transition replaced an existing receipt')
    if after.stage != "candidate":
        review = after.review
        assert isinstance(review, dict)
        receipt_reference = review.get("receipt_reference")
        reviewed_candidate = review.get("candidate")
        trust = after.candidate.get("trust")
        reviewed_trust = (
            reviewed_candidate.get("trust")
            if isinstance(reviewed_candidate, dict)
            else None
        )
        approved_prefix_count = review.get("approved_prefix_count")
        approved_prefix_count_valid = (
            approved_prefix_count >= 0
            if type(approved_prefix_count) is int
            else False
        )
        decision = str(review.get("decision") or "")
        trust_status = str(trust.get("status") or "") if isinstance(trust, dict) else ""
        allowed_trust = {
            "approved": {"accepted", "approved"},
            "deferred": {"deferred", "pending", "pending_review"},
            "rejected": {"rejected"},
        }
        if (
            review.get("contract_version") != "project_retrieval.candidate.review.v1"
            or review.get("receipt_owner") != RETRIEVAL_CANDIDATE_REVIEW_KIND
            or not isinstance(receipt_reference, dict)
            or receipt_reference.get("kind") != "runtime_step_output"
            or receipt_reference.get("root_run_id") != after.root_run_id
            or receipt_reference.get("candidate_id") != after.candidate_id
            or review.get("material_budget_remaining") != after.material_budget_remaining
            or not approved_prefix_count_valid
            or reviewed_trust != trust
            or trust_status not in allowed_trust.get(decision, set())
            or (after.stage != "reviewed" and decision != "approved")
        ):
            raise_retrieval_contract_error(ValueError, 'candidate work trust lacks its exact review receipt')
    if before.candidate != after.candidate:
        before_candidate = dict(before.candidate)
        after_candidate = dict(after.candidate)
        before_trust = before_candidate.pop("trust", None)
        after_trust = after_candidate.pop("trust", None)
        trust_review_transition = (
            before.stage == "candidate"
            and stage_index[after.stage] >= stage_index["reviewed"]
            and before_candidate == after_candidate
            and isinstance(before_trust, dict)
            and before_trust == {"status": "pending_review"}
            and isinstance(after_trust, dict)
        )
        if not trust_review_transition:
            raise_retrieval_contract_error(
                ValueError,
                "candidate work transition changed immutable candidate facts",
            )


__all__ = [
    "CANDIDATE_WORK_CODEC_ID",
    "CANDIDATE_WORK_SEQUENCE_TYPE",
    "CANDIDATE_WORK_TYPE",
    "CONTROL_LEAF_KINDS",
    "RETRIEVAL_CANDIDATE_REVIEW_KIND",
    "RETRIEVAL_CONTROL_CODEC_ID",
    "RETRIEVAL_CONTROL_TYPE",
    "RETRIEVAL_FOLLOWUP_PLAN_KIND",
    "RETRIEVAL_LEAF_KINDS",
    "RETRIEVAL_MATERIAL_FORMALIZE_KIND",
    "RETRIEVAL_MATERIAL_READ_BODY_KIND",
    "RETRIEVAL_MATERIAL_REVALIDATE_KIND",
    "RETRIEVAL_TOPOLOGY_COMMIT_KIND",
    "WORK_LEAF_KINDS",
    "CandidateWork",
    "RetrievalControl",
    "RetrievalLeafDefinition",
    "build_candidate_work_codec",
    "build_retrieval_control_codec",
    "build_retrieval_leaf_contract",
    "build_retrieval_leaf_definition",
    "build_retrieval_leaf_profiles",
    "retrieval_payload_value",
    "validate_candidate_work_transition",
]
