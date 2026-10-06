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

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Literal, NoReturn, Protocol, TypeGuard, overload

from functorial_kit import Failure

from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
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
    build_profile,
)
from app.successor_runtime.research.object_types import ObjectType
from mrw_functorial_kit.core.material_semantics import MATERIAL_INGEST_STAGE_FAILURE_CODES
from mrw_functorial_kit.core.w06_semantics import material_ingest_contract_failures

__all__ = [
    "MATERIAL_ADMISSION_READBACK_CONTRACT_ID",
    "ADMISSION_WRITE_BOUNDARY",
    "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED",
    "MATERIAL_INGEST_OWNER",
    "HISTORICAL_C7_INGEST_OWNER",
    "MATERIAL_COMMIT_INTENT_CONTRACT_ID",
    "DOCUMENT_CANONICAL_OWNER",
    "MATERIAL_INGEST_STAGES",
    "MATERIAL_INGEST_STAGE_CANDIDATE",
    "MATERIAL_INGEST_STAGE_FETCHED",
    "MATERIAL_INGEST_STAGE_NORMALIZED",
    "MATERIAL_INGEST_STAGE_SUBMITTED",
    "MATERIAL_NONSTART_RECONCILIATION_CONTRACT_ID",
    "MATERIAL_PROJECTION_DIFF_CONTRACT_ID",
    "MATERIAL_READBACK_RECONCILIATION_CONTRACT_ID",
    "STAGED_MATERIAL_CANDIDATE_RESULT_TYPE",
    "MATERIAL_STAGE_CANDIDATE_KIND",
    "MATERIAL_STAGE_CANDIDATE_OPERATION_ID",
    "MATERIAL_STAGE_CANDIDATE_PAYLOAD_CODEC_ID",
    "MATERIAL_STAGE_CANDIDATE_PAYLOAD_TYPE",
    "MaterialIngestCapabilityBundle",
    "MaterialIngestSubmission",
    "MaterialReconciliationDecision",
    "material_ingest_contract_failure",
    "EffectOutcome",
    "NormalizedMaterialDocument",
    "ProjectionDiff",
    "StagedMaterialCandidate",
    "build_material_ingest_bundle",
    "build_material_ingest_catalog",
    "build_material_ingest_registry",
    "canonical_json",
    "content_digest",
    "normalize_ingest_submission",
    "raise_material_ingest_contract_failure",
    "stage_ingest_submission",
]


MATERIAL_INGEST_OWNER = "material.ingest.v2"
HISTORICAL_C7_INGEST_OWNER = "ingest_index.c7.v1"
DOCUMENT_CANONICAL_OWNER = "document.canonical.v1"
ADMISSION_WRITE_BOUNDARY = "material.ingest.admission-write-boundary.v2"
AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED = "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"

MATERIAL_STAGE_CANDIDATE_OPERATION_ID = "ingest_index.stage_candidate"
MATERIAL_STAGE_CANDIDATE_KIND = "ingest_index.stage_candidate.v1"
MATERIAL_STAGE_CANDIDATE_PAYLOAD_CODEC_ID = "mrw.material.ingest.stage-candidate.codec.v2"
MATERIAL_COMMIT_INTENT_CONTRACT_ID = "ingest_index.commit_intent.readback.v1"
MATERIAL_ADMISSION_READBACK_CONTRACT_ID = "ingest_index.admission.readback.v1"
MATERIAL_PROJECTION_DIFF_CONTRACT_ID = "ingest_index.projection_declared_loss.v1"
MATERIAL_READBACK_RECONCILIATION_CONTRACT_ID = "ingest_index.reconcile.readback.v1"
MATERIAL_NONSTART_RECONCILIATION_CONTRACT_ID = "ingest_index.reconcile.nonstart.v1"

MATERIAL_OPERATION_CATALOG_ID = "mrw.material.ingest.operations"
MATERIAL_OPERATION_CATALOG_VERSION = "2.0.0"
MATERIAL_OPERATION_SEMANTIC_IDENTITY = "material.ingest.stage-candidate.v2"
MATERIAL_OBSERVATION_PROFILE = "mrw.material.ingest.observation.v2"
MATERIAL_ADMISSION_RETURN_CONTRACT_REF = DOCUMENT_ADMISSION_RETURN_CONTRACT_REF

MATERIAL_INGEST_STAGE_SUBMITTED = "submitted"
MATERIAL_INGEST_STAGE_FETCHED = "fetched"
MATERIAL_INGEST_STAGE_NORMALIZED = "normalized"
MATERIAL_INGEST_STAGE_CANDIDATE = "candidate"
MATERIAL_INGEST_STAGES: tuple[str, ...] = (
    MATERIAL_INGEST_STAGE_SUBMITTED,
    MATERIAL_INGEST_STAGE_FETCHED,
    MATERIAL_INGEST_STAGE_NORMALIZED,
    MATERIAL_INGEST_STAGE_CANDIDATE,
)

MATERIAL_STAGE_CANDIDATE_PAYLOAD_TYPE = ObjectType("MaterialIngestSubmission.v2")
STAGED_MATERIAL_CANDIDATE_RESULT_TYPE = ObjectType("StagedMaterialCandidate.v2")
_MATERIAL_FAILURE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"


def _empty_object_mapping() -> dict[str, object]:
    return {}


def material_ingest_contract_failure(
    code: str,
    message: str,
    *,
    exception_type: type[Exception] = ValueError,
    public_exception: str | None = None,
    operation: str = "material.ingest.contract",
    site: str = "ingest_c7_common",
    **details: object,
) -> Failure:
    """Construct one closed C7 contract failure before the ABI lift."""

    declared_exception = public_exception or exception_type.__name__
    return material_ingest_contract_failures.fail(
        code,
        message,
        {
            "owner": "material.ingest.contract",
            "effect_boundary": "material.ingest.contract_core",
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "failure_family": material_ingest_contract_failures.name,
            "operation": operation,
            "site": site,
            "public_exception": declared_exception,
            "public_message": message,
            "witness": _MATERIAL_FAILURE_WITNESS,
            **details,
        },
    )


def _is_material_failure(value: object) -> TypeGuard[Failure]:
    return isinstance(value, Failure)


def raise_material_ingest_contract_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
) -> NoReturn:
    """Lift one complete C7 failure at the retained public ABI boundary."""

    if not _is_material_failure(failure):
        # kit:boundary owner=ingest_c7_common.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("C7 contract lift requires a Failure")
    context = failure.context or {}
    if (
        not failure.failure
        or failure.family != material_ingest_contract_failures.name
        or context.get("failure_family") != material_ingest_contract_failures.name
        or context.get("public_exception") != exception_type.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=ingest_c7_common.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("C7 contract lift context is incomplete or inconsistent")
    # kit:boundary owner=ingest_c7_common.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=material.ingest.contract_failure witness=test:test_w06_c2_total_core_failure_lifts
    raise exception_type(str(context["public_message"]))


def _reject_material_contract(
    message: str,
    *,
    code: str = "input_contract_invalid",
    exception_type: type[Exception] = ValueError,
    operation: str = "material.ingest.contract",
    site: str = "ingest_c7_common",
) -> NoReturn:
    raise_material_ingest_contract_failure(
        material_ingest_contract_failure(
            code,
            message,
            exception_type=exception_type,
            operation=operation,
            site=site,
        ),
        exception_type,
    )


# Compatibility spellings used by sibling C7 capability modules.
_contract_failure = material_ingest_contract_failure
_raise_contract_failure = raise_material_ingest_contract_failure


def _is_lowercase_hex_digest(value: object) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True, slots=True)
class MaterialIngestSubmission:
    """Read-only ingress submission; collection does not imply admission."""

    idempotency_key: str
    project_key: str
    source_locator: str
    request_key: str = ""
    raw_payload: Mapping[str, object] = field(default_factory=_empty_object_mapping)
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if not str(self.idempotency_key or "").strip():
            _reject_material_contract(
                "C7IngestSubmission.idempotency_key is required",
                site="input/C7IngestSubmission.idempotency_key",
            )
        if not str(self.project_key or "").strip():
            _reject_material_contract(
                "C7IngestSubmission.project_key is required",
                site="input/C7IngestSubmission.project_key",
            )
        if not str(self.source_locator or "").strip():
            _reject_material_contract(
                "C7IngestSubmission.source_locator is required",
                site="input/C7IngestSubmission.source_locator",
            )
        if self.payload_digest == "":
            plain: dict[str, object] = {
                "idempotency_key": self.idempotency_key,
                "project_key": self.project_key,
                "source_locator": self.source_locator,
                "request_key": self.request_key,
                "raw_payload": self.raw_payload,
            }
            try:
                digest = content_digest(plain)
            except TypeError as exc:
                _reject_material_contract(
                    str(exc),
                    site="digest/C7IngestSubmission.payload_digest",
                    exception_type=TypeError,
                )
            object.__setattr__(self, "payload_digest", digest)
        else:
            if not _is_lowercase_hex_digest(self.payload_digest):
                _reject_material_contract(
                    "C7IngestSubmission.payload_digest must be a 64-char lowercase hex digest",
                    site="digest/C7IngestSubmission.payload_digest",
                )


@dataclass(frozen=True, slots=True)
class NormalizedMaterialDocument:
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
class StagedMaterialCandidate:
    candidate_id: str
    submission_id: str
    project_key: str
    source_locator: str
    normalized: NormalizedMaterialDocument
    stage: str = MATERIAL_INGEST_STAGE_CANDIDATE

    def __post_init__(self) -> None:
        if not str(self.candidate_id or "").strip():
            _reject_material_contract(
                "StagedIngestCandidate.candidate_id is required",
                site="input/StagedIngestCandidate.candidate_id",
            )
        if not str(self.submission_id or "").strip():
            _reject_material_contract(
                "StagedIngestCandidate.submission_id is required",
                site="input/StagedIngestCandidate.submission_id",
            )
        if self.stage not in MATERIAL_INGEST_STAGES:
            _reject_material_contract(
                f"unsupported ingest stage: {self.stage}",
                code="stage_invalid",
                site="stage/StagedIngestCandidate.stage",
            )


@dataclass(frozen=True, slots=True)
class EffectOutcome:
    disposition: Literal[
        "NOT_STARTED", "IN_FLIGHT", "SUCCEEDED", "FAILED", "OUTCOME_UNKNOWN"
    ]
    receipt: Mapping[str, object] = field(default_factory=_empty_object_mapping)


@dataclass(frozen=True, slots=True)
class ProjectionDiff:
    source_identity: str
    projection_kind: str
    source_digest: str
    projection_digest: str
    declared_loss: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MaterialReconciliationDecision:
    new_attempt_allowed: bool
    requirement: str
    reason: str


@dataclass(frozen=True, slots=True)
class MaterialIngestCapabilityBundle:
    bundle_id: str
    operations: tuple[OperationContract, ...]
    codecs: tuple[PayloadCodec[MaterialIngestSubmission]]
    profiles: dict[str, object]

    @overload
    def codec_by_kind(
        self,
        kind: Literal["ingest_index.stage_candidate.v1"],
    ) -> PayloadCodec[MaterialIngestSubmission]: ...

    @overload
    def codec_by_kind(
        self, kind: str
    ) -> PayloadCodec[MaterialIngestSubmission]: ...

    def codec_by_kind(
        self, kind: str
    ) -> PayloadCodec[MaterialIngestSubmission]:
        for codec in self.codecs:
            if codec.contract_ref.kind == kind:
                return codec
        _reject_material_contract(
            f"no C7 payload codec for kind {kind}",
            code="lookup_not_found",
            exception_type=KeyError,
            operation="material.ingest.codec_lookup",
            site="lookup/C7IngestCapabilityBundle.codec_by_kind",
        )


class _ProfileRefSource(Protocol):
    @property
    def profile_id(self) -> str: ...

    @property
    def profile_version(self) -> str: ...

    @property
    def profile_digest(self) -> str: ...


def _profile_ref(profile: _ProfileRefSource) -> ContractProfileRef:
    return ContractProfileRef(
        profile.profile_id,
        profile.profile_version,
        profile.profile_digest,
    )


def _semantic_profile() -> SemanticProfile:
    values: dict[str, object] = {
        "semantic_profile_id": "material.ingest.stage.semantic.v2",
        "semantic_profile_version": "2.0.0",
        "reads": ("MaterialIngestSubmission.v2",),
        "creates": ("StagedMaterialCandidate.v2",),
        "creates_relations": (),
        "declared_loss": (),
        "observation_profile_ref": MATERIAL_OBSERVATION_PROFILE,
    }
    return build_profile(
        SemanticProfile,
        **values,
        profile_digest=content_digest(values),
    )


def _effect_profile() -> EffectProfile:
    values: dict[str, object] = {
        "effect_profile_id": "material.ingest.stage.effect.v2",
        "effect_profile_version": "2.0.0",
        "execution_class": "EFFECTFUL",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": (),
        "internal_export_only": False,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "mrw.material.ingest.idempotency.v2",
    }
    return build_profile(
        EffectProfile,
        **values,
        profile_digest=content_digest(values),
    )


def _resource_profile() -> ResourceProfile:
    values: dict[str, object] = {
        "resource_profile_id": "material.ingest.stage.resource.v2",
        "resource_profile_version": "2.0.0",
        "resource_classes": ("CPU_LIGHT",),
        "concurrency_key": "material.ingest.stage",
        "budget_units": "units",
        "default_soft_limit_seconds": 5,
        "default_hard_limit_seconds": 30,
        "node_profile_selector": "any",
        "budget_ref": "mrw.material.ingest.budget.v2",
        "deadline_policy_ref": "mrw.material.ingest.deadline.v2",
        "node_profile_requirements": ("any",),
        "units": 1,
    }
    return build_profile(
        ResourceProfile,
        **values,
        profile_digest=content_digest(values),
    )


def _failure_profile() -> FailureProfile:
    values: dict[str, object] = {
        "failure_profile_id": "material.ingest.stage.failure.v2",
        "failure_profile_version": "2.0.0",
        "typed_failures": MATERIAL_INGEST_STAGE_FAILURE_CODES,
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": True,
        "readback_or_compensation": "readback",
        "failure_union_ref": "mrw.material.ingest.failures.v2",
        "retryable_failure_kinds": (),
        "readback_profile_ref": MATERIAL_READBACK_RECONCILIATION_CONTRACT_ID,
        "compensation_profile_ref": None,
    }
    return build_profile(
        FailureProfile,
        **values,
        profile_digest=content_digest(values),
    )


def _authority_profile() -> AuthorityProfile:
    values: dict[str, object] = {
        "authority_profile_id": "material.ingest.stage.authority.v2",
        "authority_profile_version": "2.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": MATERIAL_INGEST_OWNER,
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    return build_profile(
        AuthorityProfile,
        **values,
        profile_digest=content_digest(values),
    )


def _interpreter_profile() -> InterpreterProfile:
    dependency_digest = content_digest(
        {
            "interpreter": "material-native.ingest",
            "version": "2.0.0",
            "boundary": "pure staged candidate; no legacy writer import",
        }
    )
    values: dict[str, object] = {
        "interpreter_profile_id": "material.ingest.pure.v2",
        "interpreter_profile_version": "2.0.0",
        "supported_contract_kinds": (MATERIAL_STAGE_CANDIDATE_KIND,),
        "supported_contract_refs": (),
        "dependency_digest": dependency_digest,
        "security_profile_ref": "mrw.material.ingest.security.pure.v2",
        "resource_profile_ref": "material.ingest.stage.resource.v2@2.0.0",
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "step_boundary",
        "idempotency_profile_ref": "logical_request_id",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": MATERIAL_OBSERVATION_PROFILE,
    }
    return build_profile(
        InterpreterProfile,
        **values,
        profile_digest=content_digest(values),
    )


def _observation_profile() -> ObservationProfile:
    values: dict[str, object] = {
        "observation_profile_id": MATERIAL_OBSERVATION_PROFILE,
        "observation_profile_version": "2.0.0",
        "dimensions": (
            "staged_candidate",
            "admission_implied_absent",
            "projection_declared_loss",
            "reconciliation_decision",
            "provider_calls_zero",
        ),
        "compatible_with_legacy": True,
        "observation_schema_ref": MATERIAL_OBSERVATION_PROFILE,
    }
    return build_profile(
        ObservationProfile,
        **values,
        profile_digest=content_digest(values),
    )


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
        return_contract_ref=MATERIAL_ADMISSION_RETURN_CONTRACT_REF,
        semantic_profile_ref=_profile_ref(semantic),
        effect_profile_ref=_profile_ref(effect),
        resource_profile_ref=_profile_ref(resource),
        failure_profile_ref=_profile_ref(failure),
        authority_profile_ref=_profile_ref(authority),
        interpreter_compatibility_ref=_profile_ref(interpreter),
        observation_profile_ref=_profile_ref(observation),
        allowed_override_schema_ref="mrw.material.ingest.override.none.v2",
        owner_capability_id=owner,
    )


def build_material_ingest_bundle() -> Annotated[MaterialIngestCapabilityBundle, Literal["kit:non-authoritative derived_as=view fact_source=C7_ingest_contract_constants witness=test:test_w06_successor_authority_metadata"]]:
    semantic = _semantic_profile()
    effect = _effect_profile()
    resource = _resource_profile()
    failure = _failure_profile()
    authority = _authority_profile()
    interpreter = _interpreter_profile()
    observation = _observation_profile()
    stage_contract = _make_contract(
        kind=MATERIAL_STAGE_CANDIDATE_KIND,
        input_type=MATERIAL_STAGE_CANDIDATE_PAYLOAD_TYPE,
        output_type=STAGED_MATERIAL_CANDIDATE_RESULT_TYPE,
        semantic=semantic,
        effect=effect,
        resource=resource,
        failure=failure,
        authority=authority,
        interpreter=interpreter,
        observation=observation,
        owner=MATERIAL_INGEST_OWNER,
    )
    stage_codec = dataclass_codec(
        codec_id=MATERIAL_STAGE_CANDIDATE_PAYLOAD_CODEC_ID,
        codec_version="2",
        contract_ref=stage_contract.ref,
        payload_type_id=MATERIAL_STAGE_CANDIDATE_PAYLOAD_TYPE.type_id,
        dto_cls=MaterialIngestSubmission,
    )
    return MaterialIngestCapabilityBundle(
        bundle_id="mrw.material.ingest",
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


def build_material_ingest_catalog(
    bundle: MaterialIngestCapabilityBundle,
) -> Annotated[OperationContractCatalogSnapshot, Literal["kit:non-authoritative derived_as=view fact_source=C7_ingest_contract_constants witness=test:test_w06_successor_authority_metadata"]]:
    return OperationContractCatalogSnapshot(
        catalog_id=MATERIAL_OPERATION_CATALOG_ID,
        catalog_version=MATERIAL_OPERATION_CATALOG_VERSION,
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


def build_material_ingest_registry(
    bundle: MaterialIngestCapabilityBundle,
) -> Annotated[OperationContractRegistry, Literal["kit:non-authoritative derived_as=view fact_source=C7_ingest_contract_constants witness=test:test_w06_successor_authority_metadata"]]:
    return OperationContractRegistry(
        build_material_ingest_catalog(bundle),
        bundle.operations,
    )


def normalize_ingest_submission(
    submission: MaterialIngestSubmission,
) -> NormalizedMaterialDocument:
    """Deterministic pure normalization with the raw boundary preserved."""

    raw = dict(submission.raw_payload or {})
    title = str(raw.get("title") or "").strip()
    text = " ".join(str(raw.get("text") or "").split())
    return NormalizedMaterialDocument(
        source_locator=str(submission.source_locator or "").strip(),
        title=title,
        text=text,
    )


def stage_ingest_submission(
    submission: MaterialIngestSubmission,
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
    candidate = StagedMaterialCandidate(
        candidate_id=resolved_candidate_id,
        submission_id=request_key,
        project_key=submission.project_key,
        source_locator=normalized.source_locator,
        normalized=normalized,
        stage=MATERIAL_INGEST_STAGE_CANDIDATE,
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
