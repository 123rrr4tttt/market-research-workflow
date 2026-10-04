"""Family-local canonical common contracts for the C7 ingest-index slice.

This module is the only cross-module sharing point for the C7 capability
files.  It owns the C7.1 staged candidate vocabulary, the C7.3 declared-loss
projection DTO, and the C7-owned operation contract/bundle/catalog/registry
used to compile one exact shared ``ProgramSpec``.  The canonical commit
intent, verification binding, document ref and recovery contracts live in the
sibling migration adapters and reuse the shared runtime contracts.

The module performs no network, database, provider, index, graph, credential
or canonical write work.  Staging a candidate never implies admission, and
every authority/effect field stays false/zero until an explicit, separately
reviewed adoption milestone.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
)
from app.successor_runtime.capabilities.codecs import PayloadCodec, dataclass_codec
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.object_contracts import (
    DOCUMENT_ADMISSION_RETURN_CONTRACT_REF,
    OperationContract,
    make_operation_contract,
)
from app.successor_runtime.language.profiles import (
    AuthorityProfile,
    ContractProfileRef,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "ADMISSION_READBACK_CONTRACT_ID",
    "ADMISSION_WRITE_BOUNDARY",
    "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED",
    "C7_INGEST_OWNER",
    "COMMIT_INTENT_CONTRACT_ID",
    "DOCUMENT_CANONICAL_OWNER",
    "INGEST_STAGES",
    "INGEST_STAGE_CANDIDATE",
    "INGEST_STAGE_FETCHED",
    "INGEST_STAGE_NORMALIZED",
    "INGEST_STAGE_SUBMITTED",
    "NONSTART_RECONCILIATION_CONTRACT_ID",
    "PROJECTION_DIFF_CONTRACT_ID",
    "READBACK_RECONCILIATION_CONTRACT_ID",
    "STAGED_CANDIDATE_RESULT_TYPE",
    "STAGE_CANDIDATE_KIND",
    "STAGE_CANDIDATE_OPERATION_ID",
    "STAGE_CANDIDATE_PAYLOAD_CODEC_ID",
    "STAGE_CANDIDATE_PAYLOAD_TYPE",
    "C7IngestCapabilityBundle",
    "C7IngestSubmission",
    "C7ReconciliationDecision",
    "EffectOutcome",
    "NormalizedIngestDocument",
    "ProjectionDiff",
    "StagedIngestCandidate",
    "build_ingest_c7_bundle",
    "build_ingest_c7_catalog",
    "build_ingest_c7_registry",
    "canonical_json",
    "content_digest",
    "normalize_ingest_submission",
    "stage_ingest_submission",
]


C7_INGEST_OWNER = "ingest_index.c7.v1"
DOCUMENT_CANONICAL_OWNER = "document.canonical.v1"
ADMISSION_WRITE_BOUNDARY = "ingest_index.c7.v2.admission_write_boundary"
AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED = "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"

STAGE_CANDIDATE_OPERATION_ID = "ingest_index.stage_candidate"
STAGE_CANDIDATE_KIND = "ingest_index.stage_candidate.v1"
STAGE_CANDIDATE_PAYLOAD_CODEC_ID = "mrw.successor.ingest-c7.c7-1.payload.codec.v1"
COMMIT_INTENT_CONTRACT_ID = "ingest_index.commit_intent.readback.v1"
ADMISSION_READBACK_CONTRACT_ID = "ingest_index.admission.readback.v1"
PROJECTION_DIFF_CONTRACT_ID = "ingest_index.projection_declared_loss.v1"
READBACK_RECONCILIATION_CONTRACT_ID = "ingest_index.reconcile.readback.v1"
NONSTART_RECONCILIATION_CONTRACT_ID = "ingest_index.reconcile.nonstart.v1"

C7_OPERATION_CATALOG_ID = "mrw.functorial-successor.ingest-c7.operations"
C7_OPERATION_CATALOG_VERSION = "1.0.0"
C7_OPERATION_SEMANTIC_IDENTITY = "ingest-index.stage-candidate"
C7_OBSERVATION_PROFILE = "mrw.successor.ingest-c7.c7-1.observation.v1"
C7_ADMISSION_RETURN_CONTRACT_REF = DOCUMENT_ADMISSION_RETURN_CONTRACT_REF

INGEST_STAGE_SUBMITTED = "submitted"
INGEST_STAGE_FETCHED = "fetched"
INGEST_STAGE_NORMALIZED = "normalized"
INGEST_STAGE_CANDIDATE = "candidate"
INGEST_STAGES: tuple[str, ...] = (
    INGEST_STAGE_SUBMITTED,
    INGEST_STAGE_FETCHED,
    INGEST_STAGE_NORMALIZED,
    INGEST_STAGE_CANDIDATE,
)

STAGE_CANDIDATE_PAYLOAD_TYPE = ObjectType("C7IngestSubmission.v1")
STAGED_CANDIDATE_RESULT_TYPE = ObjectType("StagedIngestCandidate.v1")


@dataclass(frozen=True, slots=True)
class C7IngestSubmission:
    """Read-only ingress submission; collection does not imply admission."""

    idempotency_key: str
    project_key: str
    source_locator: str
    request_key: str = ""
    raw_payload: Mapping[str, Any] = field(default_factory=dict)
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if not str(self.idempotency_key or "").strip():
            raise ValueError("C7IngestSubmission.idempotency_key is required")
        if not str(self.project_key or "").strip():
            raise ValueError("C7IngestSubmission.project_key is required")
        if not str(self.source_locator or "").strip():
            raise ValueError("C7IngestSubmission.source_locator is required")
        if self.payload_digest == "":
            plain = {
                field_def.name: getattr(self, field_def.name)
                for field_def in dataclasses.fields(self)
                if field_def.name != "payload_digest"
            }
            object.__setattr__(self, "payload_digest", content_digest(plain))
        else:
            require_hex64(self.payload_digest, "C7IngestSubmission.payload_digest")


@dataclass(frozen=True, slots=True)
class NormalizedIngestDocument:
    source_locator: str
    title: str
    text: str
    content_digest: str = ""

    def __post_init__(self) -> None:
        if self.content_digest == "":
            object.__setattr__(
                self,
                "content_digest",
                content_digest(
                    {
                        "source_locator": self.source_locator,
                        "title": self.title,
                        "text": self.text,
                    }
                ),
            )


@dataclass(frozen=True, slots=True)
class StagedIngestCandidate:
    candidate_id: str
    submission_id: str
    project_key: str
    source_locator: str
    normalized: NormalizedIngestDocument
    stage: str = INGEST_STAGE_CANDIDATE

    def __post_init__(self) -> None:
        if not str(self.candidate_id or "").strip():
            raise ValueError("StagedIngestCandidate.candidate_id is required")
        if not str(self.submission_id or "").strip():
            raise ValueError("StagedIngestCandidate.submission_id is required")
        if self.stage not in INGEST_STAGES:
            raise ValueError(f"unsupported ingest stage: {self.stage}")


@dataclass(frozen=True, slots=True)
class EffectOutcome:
    disposition: Literal[
        "NOT_STARTED", "IN_FLIGHT", "SUCCEEDED", "FAILED", "OUTCOME_UNKNOWN"
    ]
    receipt: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProjectionDiff:
    source_identity: str
    projection_kind: str
    source_digest: str
    projection_digest: str
    declared_loss: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class C7ReconciliationDecision:
    new_attempt_allowed: bool
    requirement: str
    reason: str


@dataclass(frozen=True, slots=True)
class C7IngestCapabilityBundle:
    bundle_id: str
    operations: tuple[OperationContract, ...]
    codecs: tuple[PayloadCodec, ...]
    profiles: dict[str, object]

    def codec_by_kind(self, kind: str) -> PayloadCodec:
        for codec in self.codecs:
            if codec.contract_ref.kind == kind:
                return codec
        raise KeyError(f"no C7 payload codec for kind {kind}")


def _profile_ref(profile: Any) -> ContractProfileRef:
    return ContractProfileRef(
        profile.profile_id,
        profile.profile_version,
        profile.profile_digest,
    )


def _semantic_profile() -> SemanticProfile:
    values = {
        "semantic_profile_id": "ingest_index.c7.stage.semantic",
        "semantic_profile_version": "1.0.0",
        "reads": ("C7IngestSubmission.v1",),
        "creates": ("StagedIngestCandidate.v1",),
        "creates_relations": (),
        "declared_loss": (),
        "observation_profile_ref": C7_OBSERVATION_PROFILE,
    }
    return SemanticProfile(**values, profile_digest=content_digest(values))


def _effect_profile() -> EffectProfile:
    values = {
        "effect_profile_id": "ingest_index.c7.stage.effect",
        "effect_profile_version": "1.0.0",
        "execution_class": "EFFECTFUL",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": (),
        "internal_export_only": False,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "mrw.successor.ingest-c7.idempotency.v1",
    }
    return EffectProfile(**values, profile_digest=content_digest(values))


def _resource_profile() -> ResourceProfile:
    values = {
        "resource_profile_id": "ingest_index.c7.stage.resource",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("CPU_LIGHT",),
        "concurrency_key": "ingest_index.c7.stage",
        "budget_units": "units",
        "default_soft_limit_seconds": 5,
        "default_hard_limit_seconds": 30,
        "node_profile_selector": "any",
        "budget_ref": "mrw.functorial-successor.budget.c7.v1",
        "deadline_policy_ref": "mrw.functorial-successor.deadline.c7.v1",
        "node_profile_requirements": ("any",),
        "units": 1,
    }
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile() -> FailureProfile:
    values = {
        "failure_profile_id": "ingest_index.c7.stage.failure",
        "failure_profile_version": "1.0.0",
        "typed_failures": (
            "INGEST_SUBMISSION_INVALID",
            "STAGED_CANDIDATE_FAILED",
            "COMMIT_INTENT_READBACK_UNAVAILABLE",
            "PROJECTION_OFFSET_DRIFT",
            "RECONCILIATION_TERMINAL_READBACK_REQUIRED",
            "RECONCILIATION_AUTHORITY_MISMATCH",
        ),
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": True,
        "readback_or_compensation": "readback",
        "failure_union_ref": "mrw.functorial-successor.failures.c7.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": READBACK_RECONCILIATION_CONTRACT_ID,
        "compensation_profile_ref": None,
    }
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile() -> AuthorityProfile:
    values = {
        "authority_profile_id": "ingest_index.c7.stage.authority",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": C7_INGEST_OWNER,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile() -> InterpreterProfile:
    values = {
        "interpreter_profile_id": "successor.ingest_index.c7.pure.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (STAGE_CANDIDATE_KIND,),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "successor-native.ingest_index.c7",
                "version": "1.0.0",
                "boundary": "pure staged candidate; no legacy writer import",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.pure.v1",
        "resource_profile_ref": "ingest_index.c7.stage.resource@1.0.0",
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "step_boundary",
        "idempotency_profile_ref": "logical_request_id",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": C7_OBSERVATION_PROFILE,
    }
    return InterpreterProfile(**values, profile_digest=content_digest(values))


def _observation_profile() -> ObservationProfile:
    values = {
        "observation_profile_id": C7_OBSERVATION_PROFILE,
        "observation_profile_version": "1.0.0",
        "dimensions": (
            "staged_candidate",
            "admission_implied_absent",
            "projection_declared_loss",
            "reconciliation_decision",
            "provider_calls_zero",
        ),
        "compatible_with_legacy": True,
        "observation_schema_ref": "mrw.successor.ingest-c7.c7-1.observation.v1",
    }
    return ObservationProfile(**values, profile_digest=content_digest(values))


def _make_contract(
    *,
    kind: str,
    input_type: ObjectType,
    output_type: ObjectType,
    semantic: SemanticProfile,
    effect: EffectProfile,
    resource: ResourceProfile,
    failure: FailureProfile,
    authority: AuthorityProfile,
    interpreter: InterpreterProfile,
    observation: ObservationProfile,
    owner: str,
) -> OperationContract:
    return make_operation_contract(
        kind=kind,
        contract_version="1.0.0",
        input_type=input_type,
        output_type=output_type,
        return_contract_ref=C7_ADMISSION_RETURN_CONTRACT_REF,
        semantic_profile_ref=_profile_ref(semantic).to_ref_string(),
        effect_profile_ref=_profile_ref(effect).to_ref_string(),
        resource_profile_ref=_profile_ref(resource).to_ref_string(),
        failure_profile_ref=_profile_ref(failure).to_ref_string(),
        authority_profile_ref=_profile_ref(authority).to_ref_string(),
        interpreter_compatibility_ref=_profile_ref(interpreter).to_ref_string(),
        observation_profile_ref=_profile_ref(observation).to_ref_string(),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=owner,
    )


def build_ingest_c7_bundle() -> C7IngestCapabilityBundle:
    semantic = _semantic_profile()
    effect = _effect_profile()
    resource = _resource_profile()
    failure = _failure_profile()
    authority = _authority_profile()
    interpreter = _interpreter_profile()
    observation = _observation_profile()
    stage_contract = _make_contract(
        kind=STAGE_CANDIDATE_KIND,
        input_type=STAGE_CANDIDATE_PAYLOAD_TYPE,
        output_type=STAGED_CANDIDATE_RESULT_TYPE,
        semantic=semantic,
        effect=effect,
        resource=resource,
        failure=failure,
        authority=authority,
        interpreter=interpreter,
        observation=observation,
        owner=C7_INGEST_OWNER,
    )
    stage_codec = dataclass_codec(
        codec_id=STAGE_CANDIDATE_PAYLOAD_CODEC_ID,
        codec_version="1",
        contract_ref=stage_contract.ref,
        payload_type_id=STAGE_CANDIDATE_PAYLOAD_TYPE.type_id,
        dto_cls=C7IngestSubmission,
    )
    return C7IngestCapabilityBundle(
        bundle_id="mrw.functorial-successor.ingest-c7",
        operations=(stage_contract,),
        codecs=(stage_codec,),
        profiles={
            "semantic": semantic,
            "effect": effect,
            "resource": resource,
            "failure": failure,
            "authority": authority,
            "interpreter": interpreter,
            "observation": observation,
        },
    )


def build_ingest_c7_catalog(
    bundle: C7IngestCapabilityBundle,
) -> OperationContractCatalogSnapshot:
    return OperationContractCatalogSnapshot(
        catalog_id=C7_OPERATION_CATALOG_ID,
        catalog_version=C7_OPERATION_CATALOG_VERSION,
        entries=tuple(
            (
                operation.ref.kind,
                operation.ref.contract_version,
                operation.ref.contract_digest,
                operation.owner_capability_id,
            )
            for operation in bundle.operations
        ),
    )


def build_ingest_c7_registry(
    bundle: C7IngestCapabilityBundle,
) -> OperationContractRegistry:
    return OperationContractRegistry(
        build_ingest_c7_catalog(bundle),
        bundle.operations,
    )


def normalize_ingest_submission(
    submission: C7IngestSubmission,
) -> NormalizedIngestDocument:
    """Deterministic pure normalization with the raw boundary preserved."""

    raw = dict(submission.raw_payload or {})
    title = str(raw.get("title") or "").strip()
    text = " ".join(str(raw.get("text") or "").split())
    return NormalizedIngestDocument(
        source_locator=str(submission.source_locator or "").strip(),
        title=title,
        text=text,
    )


def stage_ingest_submission(
    submission: C7IngestSubmission,
    *,
    candidate_id: str | None = None,
) -> EffectOutcome:
    """Create one staged candidate; no downstream admission is implied."""

    normalized = normalize_ingest_submission(submission)
    request_key = (
        str(submission.request_key or "").strip() or submission.idempotency_key
    )
    resolved_candidate_id = candidate_id or (
        "ingest-candidate-"
        + hashlib.sha256(request_key.encode("utf-8")).hexdigest()[:16]
    )
    candidate = StagedIngestCandidate(
        candidate_id=resolved_candidate_id,
        submission_id=request_key,
        project_key=submission.project_key,
        source_locator=normalized.source_locator,
        normalized=normalized,
        stage=INGEST_STAGE_CANDIDATE,
    )
    return EffectOutcome(
        disposition="SUCCEEDED",
        receipt={
            "candidate_id": candidate.candidate_id,
            "submission_id": candidate.submission_id,
            "project_key": candidate.project_key,
            "stage": candidate.stage,
            "content_digest": candidate.normalized.content_digest,
            "admission_implied": False,
            "document_write_boundary": False,
            "provider_calls": 0,
            "authority": False,
        },
    )
