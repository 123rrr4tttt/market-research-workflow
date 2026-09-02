"""C8.2/C8.3 staged artifact and local report admission PostgreSQL effect slice.

The slice persists exact Markdown draft bytes through :class:`ValueRepository`
plus the public ``runtime_staged_artifacts`` lifecycle, verifies staged bytes
against a root-issued ``ReportVerification``, and admits a verified report
through a local same-transaction ``CommitIntent`` plus a canonical report value
with authoritative readback.  The slice accepts no caller positive booleans,
commit refs or receipt refs; the production composition root owns verifier
authority and performs the pure admission readback confirmation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, Self

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities import c8_common as c8
from app.successor_runtime.capabilities.c8_program import (
    C8_3_KIND,
    C8_ADMISSION_KIND,
    C8_DELIVERY_INTENT_PREPARE_KIND,
    C8_VERIFY_KIND,
)
from app.successor_runtime.capabilities.c8_report import (
    build_c8_research_artifact_candidate,
    build_report_stage,
    research_artifact_from_candidate,
    verify_report_stage,
)
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.research.artifacts import ResearchArtifact
from app.successor_runtime.research.codec import (
    canonical_bytes as research_canonical_bytes,
)
from app.successor_runtime.research.codec import dataclass_to_json
from app.successor_runtime.research.object_types import (
    CANONICAL_CODEC_ID,
    RESEARCH_ARTIFACT_TYPE,
    ObjectType,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    RuntimeAssignment,
    canonical_digest,
    require_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.commit_intents import (
    CommitIntentBinding,
    CommitIntentRepository,
    CommitIntentStatus,
)
from app.successor_runtime.substrate.postgres.first_specimen_handlers import (
    FirstSpecimenHandlerError,
    PostgresFirstSpecimenEffectReplay,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_TABLES,
    ProjectTables,
    project_tables,
)
from app.successor_runtime.substrate.postgres.research_ledger import (
    ExactContentConflict,
    ProjectCASConflict,
    ProjectRecordNotFound,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
)
from app.successor_runtime.substrate.postgres.runtime_values import (
    RuntimeValueBinding,
    RuntimeValueRepository,
)
from app.successor_runtime.substrate.postgres.staged_artifacts import (
    StagedArtifactBinding,
    StagedArtifactRepository,
)
from app.successor_runtime.substrate.postgres.values import (
    ValueRepository,
    derive_value_write_intent_digest,
)

__all__ = [
    "C8_ARTIFACT_OWNER",
    "C8_REPORT_VALUE_CODEC_ID",
    "C8_REPORT_VALUE_OBJECT_TYPE",
    "C8_STAGED_ARTIFACT_CODEC_ID",
    "C8_STAGED_ARTIFACT_OBJECT_TYPE",
    "C8ArtifactHandlerError",
    "C8ArtifactIdempotencyConflictError",
    "C8ArtifactIntegrityError",
    "C8ArtifactLifecycleError",
    "C8ArtifactMissingError",
    "C8ArtifactOutcomeUnknownError",
    "C8ArtifactReadback",
    "C8BridgeEffectHandler",
    "C8BridgeEffectStore",
    "C8BridgeHandlerInstallation",
    "C8StagedArtifactRef",
    "admit_artifact",
    "artifact_idempotency_key",
    "read_staged_artifact",
    "readback_artifact",
    "report_value_id",
    "stage_artifact",
    "staged_artifact_value_id",
    "verify_artifact",
]

C8_ARTIFACT_OWNER = "report.c8.3.v1"
C8_STAGED_ARTIFACT_OBJECT_TYPE = "ResearchDraftArtifactDraft.v1"
C8_STAGED_ARTIFACT_CODEC_ID = "mrw.successor.c8.draft-markdown.canonical-utf8.v1"
C8_REPORT_VALUE_OBJECT_TYPE = "ResearchDraftArtifact.v1"
C8_REPORT_VALUE_CODEC_ID = "mrw.successor.c8.report-artifact.canonical-json.v1"
C8_ARTIFACT_SCHEMA = "mrw.successor.c8.artifact-lifecycle.v1"
C8_VALUE_REF_PREFIX = "project-value:"
C8_BRIDGE_EFFECT_OPERATION_KINDS = frozenset(
    {
        C8_3_KIND,
        C8_VERIFY_KIND,
        C8_ADMISSION_KIND,
        C8_DELIVERY_INTENT_PREPARE_KIND,
    }
)


class C8ArtifactHandlerError(RuntimeError):
    """Base fail-closed C8 artifact handler error."""


class C8ArtifactIntegrityError(C8ArtifactHandlerError):
    """Artifact bytes/digest/provenance/identity drift."""


class C8ArtifactMissingError(C8ArtifactHandlerError):
    """Required staged artifact or commit intent is absent."""


class C8ArtifactLifecycleError(C8ArtifactHandlerError):
    """Staged artifact lifecycle transition is not permitted."""


class C8ArtifactIdempotencyConflictError(C8ArtifactHandlerError):
    """Same artifact idempotency key is bound to different exact content."""


class C8ArtifactOutcomeUnknownError(C8ArtifactHandlerError):
    """Commit outcome is unknown; no speculative retry is allowed."""


@dataclass(frozen=True, slots=True)
class C8BridgeHandlerInstallation:
    """One exact C8 delivery-bridge operation realization."""

    operation_kind: str
    operation_contract_digest: str
    handler_binding_digest: str
    interpreter_profile_digest: str
    output_type: ObjectType
    admission_required: bool = False

    def __post_init__(self) -> None:
        if self.operation_kind not in C8_BRIDGE_EFFECT_OPERATION_KINDS:
            raise ValueError("unsupported C8 bridge effect operation")
        for field_name in (
            "operation_contract_digest",
            "handler_binding_digest",
            "interpreter_profile_digest",
        ):
            require_digest(getattr(self, field_name), field_name)
        if self.admission_required != (self.operation_kind == C8_ADMISSION_KIND):
            raise ValueError(
                "only c8.report.admission.v1 stages ResearchArtifact admission"
            )


class C8BridgeUnitOfWork(Protocol):
    connection: Connection

    def __enter__(self) -> Self: ...

    def commit(self) -> None: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class C8BridgeUnitOfWorkFactory(Protocol):
    def __call__(self) -> C8BridgeUnitOfWork: ...


@dataclass(frozen=True, slots=True)
class C8StagedArtifactRef:
    artifact_id: str
    value_id: str
    value_ref: str
    revision: int
    incarnation: str
    content_digest: str
    state: str


@dataclass(frozen=True, slots=True)
class C8ArtifactReadback:
    commit_intent_id: str
    idempotency_key: str
    capability_id: str
    project_key: str
    artifact_id: str
    artifact_digest: str
    canonical_commit_ref: str
    receipt_digest: str
    verification_id: str
    authority_kind: str
    authority_digest: str
    verifier_registry_id: str
    verifier_registry_digest: str
    readback_digest: str
    production_canonical_authority: Literal[False] = False
    live_provider: Literal[False] = False
    promotion: Literal[False] = False
    disposable: Literal[True] = True
    provider_calls: Literal[0] = 0
    store_writes: Literal[0] = 0
    export_calls: Literal[0] = 0


def staged_artifact_value_id(artifact_id: str) -> str:
    return f"c8:staged-artifact:{artifact_id}"


def report_value_id(artifact_id: str) -> str:
    return f"c8:report:{artifact_id}"


def _bridge_result_value_id(assignment: RuntimeAssignment) -> str:
    if assignment.step_id is None:
        raise C8ArtifactIntegrityError("C8 bridge assignment lacks step identity")
    return (
        f"result:{assignment.run_id}:{assignment.step_id}:"
        f"epoch-{assignment.execution_epoch}"
    )


def _bridge_result_incarnation(assignment: RuntimeAssignment) -> str:
    return (
        f"result:{assignment.incarnation}:{assignment.step_id}:"
        f"epoch-{assignment.execution_epoch}"
    )


def _bridge_stage_id(assignment: RuntimeAssignment) -> str:
    return (
        f"stage:{assignment.run_id}:{assignment.step_id}:"
        f"epoch-{assignment.execution_epoch}"
    )


def _bridge_output_provenance(
    installation: C8BridgeHandlerInstallation,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
) -> dict[str, object]:
    return {
        "contract": "C8ResearchArtifactDeliveryBridgeOutput.v1",
        "operation_kind": installation.operation_kind,
        "project_key": assignment.project_key,
        "run_id": assignment.run_id,
        "step_id": assignment.step_id,
        "execution_epoch": assignment.execution_epoch,
        "assignment_incarnation": assignment.incarnation,
        "assignment_digest": assignment.assignment_digest,
        "attempt_id": claim.attempt_id,
        "handler_binding_digest": installation.handler_binding_digest,
        "interpreter_profile_digest": installation.interpreter_profile_digest,
        "operation_contract_digest": installation.operation_contract_digest,
        "payload_ref": assignment.payload_ref,
        "payload_digest": assignment.payload_digest,
        "ordered_input_refs": list(assignment.input_refs),
        "input_closure_digest": assignment.input_closure_digest,
        "admission_required": installation.admission_required,
    }


def _bridge_project_value_row(
    connection: Connection,
    *,
    scope: RuntimeScope,
    locator: str,
) -> Mapping[str, Any]:
    if not locator.startswith(C8_VALUE_REF_PREFIX):
        raise C8ArtifactIntegrityError("C8 bridge input is not project-value owned")
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    row = (
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key
                == scope.project_scope.project_key,
                tables.successor_values.c.value_id
                == locator.removeprefix(C8_VALUE_REF_PREFIX),
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None or row["state"] != "AVAILABLE":
        raise C8ArtifactMissingError(f"C8 bridge input value is absent: {locator}")
    exact = (
        bytes(row["content_bytes"])
        if row["content_bytes"] is not None
        else research_canonical_bytes(row["content_json"])
    )
    if hashlib.sha256(exact).hexdigest() != row["content_digest"]:
        raise C8ArtifactIntegrityError("C8 bridge input content digest drift")
    provenance = row["provenance_json"]
    if (
        not isinstance(provenance, Mapping)
        or content_digest(dict(provenance)) != row["provenance_digest"]
    ):
        raise C8ArtifactIntegrityError("C8 bridge input provenance digest drift")
    return {**dict(row), "_exact_bytes": exact}


def _bridge_json(row: Mapping[str, Any], label: str) -> dict[str, Any]:
    try:
        value = json.loads(bytes(row["_exact_bytes"]))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C8ArtifactIntegrityError(f"{label} is not canonical JSON") from exc
    if (
        not isinstance(value, dict)
        or research_canonical_bytes(value) != row["_exact_bytes"]
    ):
        raise C8ArtifactIntegrityError(f"{label} is not a canonical JSON object")
    return value


@dataclass(frozen=True, slots=True)
class _C8BridgeProduct:
    object_type: ObjectType
    exact_bytes: bytes
    content_digest: str
    provenance: dict[str, object]
    source_ref: str | None = None


class C8BridgeEffectStore:
    """Deterministic C8 stage/verify/admission/prepare RuntimeNode effects."""

    def __init__(self, uow_factory: C8BridgeUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory
        self._scope_replay = PostgresFirstSpecimenEffectReplay()

    def execute_exact(
        self,
        installation: C8BridgeHandlerInstallation,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        _require_exact_bridge_handler(installation, assignment, claim)
        with self._uow_factory() as uow:
            scope, tables = self._scope_replay.resolve_scope(
                uow.connection,
                assignment,
                actor_id=context.node.node_id,
            )
            existing = self._readback(
                uow.connection,
                scope,
                installation,
                assignment,
                claim,
            )
            if existing is not None:
                uow.commit()
                return InterpreterOutcome.succeeded(existing)
            product = self._interpret(
                uow.connection,
                scope,
                tables,
                installation,
                assignment,
                claim,
            )
            digest = self._persist(
                uow.connection,
                scope,
                tables,
                installation,
                assignment,
                claim,
                product,
            )
            uow.commit()
            return InterpreterOutcome.succeeded(digest)

    def _interpret(
        self,
        connection: Connection,
        scope: RuntimeScope,
        tables: ProjectTables,
        installation: C8BridgeHandlerInstallation,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> _C8BridgeProduct:
        if installation.operation_kind == C8_3_KIND:
            return self._stage(connection, scope, installation, assignment, claim)
        if installation.operation_kind == C8_VERIFY_KIND:
            return self._verify(connection, scope, installation, assignment, claim)
        if installation.operation_kind == C8_ADMISSION_KIND:
            return self._admission(connection, scope, installation, assignment, claim)
        if installation.operation_kind == C8_DELIVERY_INTENT_PREPARE_KIND:
            return self._prepare(
                connection,
                scope,
                tables,
                installation,
                assignment,
                claim,
            )
        raise C8ArtifactIntegrityError("unsupported C8 bridge operation")

    @staticmethod
    def _stage(
        connection: Connection,
        scope: RuntimeScope,
        installation: C8BridgeHandlerInstallation,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> _C8BridgeProduct:
        if assignment.payload_ref is None:
            raise C8ArtifactIntegrityError("C8 report stage lacks payload ref")
        payload_row = _bridge_project_value_row(
            connection, scope=scope, locator=assignment.payload_ref
        )
        payload = _bridge_json(payload_row, "C8 report stage payload")
        report_id = payload.get("report_id")
        if not isinstance(report_id, str) or payload.get("project_key") != (
            scope.project_scope.project_key
        ):
            raise C8ArtifactIntegrityError("C8 report stage payload scope/id drift")
        artifact = read_staged_artifact(
            connection,
            scope=scope,
            artifact_id=report_id,
        )
        staged_row = _bridge_project_value_row(
            connection,
            scope=scope,
            locator=f"{C8_VALUE_REF_PREFIX}{staged_artifact_value_id(report_id)}",
        )
        body = {
            "schema": "mrw.successor.c8.report-stage-runtime.v1",
            "project_key": artifact.project_key,
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.artifact_digest,
            "markdown_ref": (
                f"{C8_VALUE_REF_PREFIX}{staged_artifact_value_id(report_id)}"
            ),
            "markdown_digest": hashlib.sha256(artifact.markdown_bytes).hexdigest(),
            "provenance_digest": str(staged_row["provenance_digest"]),
        }
        exact = research_canonical_bytes(body)
        provenance = _bridge_output_provenance(installation, assignment, claim)
        provenance.update(body)
        return _C8BridgeProduct(
            object_type=installation.output_type,
            exact_bytes=exact,
            content_digest=hashlib.sha256(exact).hexdigest(),
            provenance=provenance,
            source_ref=body["markdown_ref"],
        )

    @staticmethod
    def _verified_marker(
        connection: Connection,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
    ) -> tuple[dict[str, Any], c8.ResearchDraftArtifact, c8.ReportVerification]:
        if len(assignment.input_refs) < 2:
            raise C8ArtifactIntegrityError(
                "C8 verification/admission lacks dynamic stage input"
            )
        stage_row = _bridge_project_value_row(
            connection, scope=scope, locator=assignment.input_refs[0]
        )
        marker = _bridge_json(stage_row, "C8 report stage result")
        artifact_id = marker.get("artifact_id")
        if not isinstance(artifact_id, str):
            raise C8ArtifactIntegrityError("C8 stage result lacks artifact identity")
        artifact = read_staged_artifact(
            connection,
            scope=scope,
            artifact_id=artifact_id,
        )
        if (
            marker.get("project_key") != artifact.project_key
            or marker.get("artifact_digest") != artifact.artifact_digest
            or marker.get("markdown_digest")
            != hashlib.sha256(artifact.markdown_bytes).hexdigest()
        ):
            raise C8ArtifactIntegrityError("C8 stage result/draft drift")
        stage = build_report_stage(
            stage_id=f"runtime-stage:{assignment.run_id}:{artifact.artifact_id}",
            project_key=artifact.project_key,
            artifact=artifact,
            citation_closure=artifact.citation_closure,
        )
        verification = verify_report_stage(
            stage,
            citation_closure=artifact.citation_closure,
            artifact=artifact,
        )
        if verification.state != "VERIFIED":
            raise C8ArtifactIntegrityError(
                verification.failure_reason or "C8 structural verification failed"
            )
        return marker, artifact, verification

    @classmethod
    def _verify(
        cls,
        connection: Connection,
        scope: RuntimeScope,
        installation: C8BridgeHandlerInstallation,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> _C8BridgeProduct:
        marker, artifact, verification = cls._verified_marker(
            connection, scope, assignment
        )
        body = {
            "schema": "mrw.successor.c8.report-verification-runtime.v1",
            "project_key": artifact.project_key,
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.artifact_digest,
            "verification_id": verification.verification_id,
            "verification_digest": verification.object_digest,
            "markdown_ref": marker["markdown_ref"],
            "markdown_digest": marker["markdown_digest"],
            "provenance_digest": marker["provenance_digest"],
        }
        exact = research_canonical_bytes(body)
        provenance = _bridge_output_provenance(installation, assignment, claim)
        provenance.update(body)
        return _C8BridgeProduct(
            object_type=installation.output_type,
            exact_bytes=exact,
            content_digest=hashlib.sha256(exact).hexdigest(),
            provenance=provenance,
            source_ref=str(marker["markdown_ref"]),
        )

    @staticmethod
    def _admission(
        connection: Connection,
        scope: RuntimeScope,
        installation: C8BridgeHandlerInstallation,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> _C8BridgeProduct:
        if len(assignment.input_refs) < 2:
            raise C8ArtifactIntegrityError(
                "C8 report admission lacks dynamic verification input"
            )
        verification_row = _bridge_project_value_row(
            connection, scope=scope, locator=assignment.input_refs[0]
        )
        marker = _bridge_json(verification_row, "C8 verification result")
        artifact_id = marker.get("artifact_id")
        if not isinstance(artifact_id, str):
            raise C8ArtifactIntegrityError("C8 verification lacks artifact identity")
        artifact = read_staged_artifact(
            connection,
            scope=scope,
            artifact_id=artifact_id,
        )
        stage = build_report_stage(
            stage_id=f"runtime-stage:{assignment.run_id}:{artifact.artifact_id}",
            project_key=artifact.project_key,
            artifact=artifact,
            citation_closure=artifact.citation_closure,
        )
        verification = verify_report_stage(
            stage,
            citation_closure=artifact.citation_closure,
            artifact=artifact,
        )
        if (
            verification.state != "VERIFIED"
            or marker.get("project_key") != artifact.project_key
            or marker.get("artifact_digest") != artifact.artifact_digest
            or marker.get("verification_id") != verification.verification_id
            or marker.get("verification_digest") != verification.object_digest
        ):
            raise C8ArtifactIntegrityError(
                "C8 report admission verification/draft drift"
            )
        candidate = build_c8_research_artifact_candidate(
            candidate_id=f"research-artifact:{artifact.artifact_id}",
            draft=artifact,
            verification=verification,
            markdown_ref=str(marker["markdown_ref"]),
            markdown_digest=str(marker["markdown_digest"]),
            provenance_digest=str(marker["provenance_digest"]),
            canonical_revision=1,
            canonical_incarnation=f"c8:{assignment.run_id}:research-artifact:1",
        )
        research_artifact = dataclasses.replace(
            research_artifact_from_candidate(candidate),
            content_ref=f"sha256:{candidate.markdown_digest}",
            content_digest=None,
        )
        exact = research_canonical_bytes(
            dataclass_to_json(research_artifact, ("content_digest",))
        )
        if hashlib.sha256(exact).hexdigest() != research_artifact.content_digest:
            raise C8ArtifactIntegrityError(
                "C8 ResearchArtifact canonical metadata digest drift"
            )
        provenance = _bridge_output_provenance(installation, assignment, claim)
        provenance.update(
            {
                "semantic_object_id": research_artifact.artifact_id,
                "semantic_content_digest": research_artifact.content_digest,
                "source_draft_digest": candidate.source_draft_digest,
                "verification_digest": candidate.verification_digest,
                "markdown_ref": candidate.markdown_ref,
                "markdown_digest": candidate.markdown_digest,
                "artifact_exact_bytes_ref": candidate.markdown_ref,
                "artifact_exact_bytes_digest": candidate.markdown_digest,
                "candidate_metadata_digest": candidate.canonical_metadata_digest,
                "provenance_closure_digest": candidate.provenance_digest,
            }
        )
        return _C8BridgeProduct(
            object_type=RESEARCH_ARTIFACT_TYPE,
            exact_bytes=exact,
            content_digest=research_artifact.content_digest or "",
            provenance=provenance,
            source_ref=candidate.markdown_ref,
        )

    @staticmethod
    def _prepare(
        connection: Connection,
        scope: RuntimeScope,
        tables: ProjectTables,
        installation: C8BridgeHandlerInstallation,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> _C8BridgeProduct:
        if len(assignment.input_refs) < 2:
            raise C8ArtifactIntegrityError(
                "C8 delivery preparation lacks admitted artifact input"
            )
        artifact_row = _bridge_project_value_row(
            connection, scope=scope, locator=assignment.input_refs[0]
        )
        raw = _bridge_json(artifact_row, "C8 ResearchArtifact result")
        try:
            artifact = ResearchArtifact(
                artifact_id=raw["artifact_id"],
                content_ref=raw["content_ref"],
                content_digest=hashlib.sha256(
                    bytes(artifact_row["_exact_bytes"])
                ).hexdigest(),
                claim_closure=tuple(raw["claim_closure"]),
                evidence_relation_closure=tuple(raw["evidence_relation_closure"]),
                citation_closure=tuple(raw["citation_closure"]),
                format=raw["format"],
                revision=int(raw["revision"]),
                lifecycle_state=raw["lifecycle_state"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise C8ArtifactIntegrityError(
                "C8 ResearchArtifact result is malformed"
            ) from exc
        table = tables.research_objects
        rows = tuple(
            connection.execute(
                select(table).where(
                    table.c.project_key == scope.project_scope.project_key,
                    table.c.object_id == artifact.artifact_id,
                    table.c.object_type == RESEARCH_ARTIFACT_TYPE.type_id,
                    table.c.content_digest == artifact.content_digest,
                    table.c.revision == artifact.revision,
                )
            ).mappings()
        )
        if len(rows) != 1 or rows[0]["lifecycle_state"] != "ADMITTED":
            raise C8ArtifactIntegrityError(
                "delivery preparation requires authoritative ResearchArtifact readback"
            )
        canonical = rows[0]
        body = {
            "schema": "mrw.successor.c8.delivery-intent-preparation-runtime.v1",
            "project_key": scope.project_scope.project_key,
            "artifact_id": artifact.artifact_id,
            "artifact_revision": artifact.revision,
            "artifact_incarnation": str(canonical["incarnation"]),
            "artifact_digest": artifact.content_digest,
            "state": "DELIVERY_PENDING_HUMAN_APPROVAL",
            "external_delivery": False,
        }
        exact = research_canonical_bytes(body)
        provenance = _bridge_output_provenance(installation, assignment, claim)
        provenance.update(body)
        return _C8BridgeProduct(
            object_type=installation.output_type,
            exact_bytes=exact,
            content_digest=hashlib.sha256(exact).hexdigest(),
            provenance=provenance,
            source_ref=f"research-object:{artifact.artifact_id}",
        )

    @staticmethod
    def _persist(
        connection: Connection,
        scope: RuntimeScope,
        tables: ProjectTables,
        installation: C8BridgeHandlerInstallation,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        product: _C8BridgeProduct,
    ) -> str:
        value_id = _bridge_result_value_id(assignment)
        provenance_digest = content_digest(product.provenance)
        stored = ValueRepository(connection, tables).put_exact(
            scope,
            value_id=value_id,
            object_type=product.object_type.type_id,
            codec_id=CANONICAL_CODEC_ID,
            content=product.exact_bytes,
            expected_digest=product.content_digest,
            provenance_digest=provenance_digest,
            expected_revision=0,
            expected_incarnation=_bridge_result_incarnation(assignment),
            source_ref=product.source_ref,
            provenance=product.provenance,
        )
        if stored.content_digest != product.content_digest:
            raise C8ArtifactIntegrityError("C8 bridge project output write drift")
        project_row = (
            connection.execute(
                select(tables.successor_values).where(
                    tables.successor_values.c.project_key == assignment.project_key,
                    tables.successor_values.c.value_id == value_id,
                )
            )
            .mappings()
            .one()
        )
        project_ref = f"{C8_VALUE_REF_PREFIX}{value_id}"
        storage_digest = canonical_digest(
            {
                "contract": "ProjectRuntimeValueBinding.v1",
                "project_key": assignment.project_key,
                "runtime_value_id": value_id,
                "project_value_ref": project_ref,
                "content_digest": product.content_digest,
                "codec_id": CANONICAL_CODEC_ID,
                "assignment_digest": assignment.assignment_digest,
                "attempt_id": claim.attempt_id,
                "handler_binding_digest": installation.handler_binding_digest,
            }
        )
        RuntimeValueRepository(connection, scope).put_exact(
            RuntimeValueBinding(
                value_id=value_id,
                object_type=product.object_type.type_id,
                codec_id=CANONICAL_CODEC_ID,
                content_digest=product.content_digest,
                byte_size=len(product.exact_bytes),
                project_value_ref=project_ref,
                storage_digest=storage_digest,
                write_intent_digest=str(project_row["write_intent_digest"]),
            )
        )
        if installation.admission_required:
            StagedArtifactRepository(connection, scope).stage(
                StagedArtifactBinding(
                    artifact_id=_bridge_stage_id(assignment),
                    run_id=assignment.run_id,
                    step_id=assignment.step_id or "",
                    attempt_id=claim.attempt_id,
                    value_id=value_id,
                    qualifier_ref=(
                        f"staged:qualifier:{installation.operation_kind}:"
                        f"sha256:{installation.handler_binding_digest}"
                    ),
                )
            )
        return product.content_digest

    @staticmethod
    def _readback(
        connection: Connection,
        scope: RuntimeScope,
        installation: C8BridgeHandlerInstallation,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> str | None:
        value_id = _bridge_result_value_id(assignment)
        runtime_values = PUBLIC_TABLES["runtime_values"]
        public = (
            connection.execute(
                select(runtime_values).where(
                    runtime_values.c.project_key == assignment.project_key,
                    runtime_values.c.value_id == value_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if public is None:
            return None
        row = _bridge_project_value_row(
            connection,
            scope=scope,
            locator=str(public["project_value_ref"]),
        )
        provenance = row["provenance_json"]
        expected = _bridge_output_provenance(installation, assignment, claim)
        if any(provenance.get(key) != value for key, value in expected.items()):
            raise C8ArtifactIdempotencyConflictError(
                "C8 bridge output is bound to a different assignment/attempt"
            )
        if (
            public["content_digest"] != row["content_digest"]
            or public["object_type"] != installation.output_type.type_id
            or public["codec_id"] != CANONICAL_CODEC_ID
        ):
            raise C8ArtifactIntegrityError("C8 bridge public/project output drift")
        if installation.admission_required:
            staged = StagedArtifactRepository(connection, scope).load(
                _bridge_stage_id(assignment)
            )
            if (
                staged["state"] != "STAGED"
                or staged["attempt_id"] != claim.attempt_id
                or staged["value_id"] != value_id
            ):
                raise C8ArtifactIntegrityError(
                    "C8 bridge admission staging readback drift"
                )
        return str(row["content_digest"])


class C8BridgeEffectHandler(RuntimeHandler):
    """RuntimeNode handler for one exact C8 bridge operation."""

    def __init__(
        self,
        installation: C8BridgeHandlerInstallation,
        effects: C8BridgeEffectStore,
    ) -> None:
        self.installation = installation
        self.handler_binding_digest = installation.handler_binding_digest
        self.interpreter_profile_digest = installation.interpreter_profile_digest
        self.operation_contract_digest = installation.operation_contract_digest
        self._effects = effects

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        try:
            _require_exact_bridge_handler(self.installation, assignment, claim)
            return self._effects.execute_exact(
                self.installation,
                assignment,
                claim,
                context,
            )
        except (
            C8ArtifactHandlerError,
            FirstSpecimenHandlerError,
            TypeError,
            ValueError,
        ) as exc:
            detail = re.sub(r"[^A-Z0-9]+", "_", str(exc).upper()).strip("_")
            code = type(exc).__name__.upper()
            if detail:
                code = f"{code}:{detail[:96]}"
            raise DefiniteInterpreterFailure(code) from exc


def _require_exact_bridge_handler(
    installation: C8BridgeHandlerInstallation,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
) -> None:
    claim.validate_against(assignment)
    ref = assignment.operation_contract_ref
    binding = assignment.handler_binding
    returns = assignment.return_contract_binding
    if (
        assignment.assignment_kind is not AssignmentKind.INTERPRET
        or ref is None
        or ref.kind != installation.operation_kind
        or ref.contract_digest != installation.operation_contract_digest
        or assignment.operation_contract_digest
        != installation.operation_contract_digest
        or assignment.handler_binding_digest != installation.handler_binding_digest
        or getattr(binding, "interpreter_profile_digest", None)
        != installation.interpreter_profile_digest
        or claim.interpreter_profile_digest != installation.interpreter_profile_digest
        or returns is None
        or returns.admission_required != installation.admission_required
    ):
        raise C8ArtifactIntegrityError("exact C8 bridge handler binding drift")


def require_exact_artifact(
    artifact: c8.ResearchDraftArtifact,
    project_key: str,
) -> None:
    if artifact.project_key != project_key:
        raise C8ArtifactIntegrityError("artifact project scope mismatch")
    expected = c8.research_draft_artifact_digest(artifact)
    if artifact.artifact_digest != expected:
        raise C8ArtifactIntegrityError("artifact digest mismatch")


def _report_body(artifact: c8.ResearchDraftArtifact) -> dict[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "project_key": artifact.project_key,
        "markdown_bytes": artifact.markdown_bytes.decode("utf-8"),
        "base_revision": artifact.base_revision,
        "base_incarnation": artifact.base_incarnation,
        "provenance_closure": [
            {
                "identity": entry.identity,
                "digest": entry.digest,
                "revision": entry.revision,
                "incarnation": entry.incarnation,
                "handle_id": entry.handle_id,
                "fields_digest": entry.fields_digest,
            }
            for entry in artifact.provenance_closure
        ],
        "citation_closure": [
            {
                "citation_id": ref.citation_id,
                "source_identity": ref.source_identity,
                "source_digest": ref.source_digest,
                "position": ref.position,
            }
            for ref in artifact.citation_closure.refs
        ],
        "declared_legacy_metadata_loss": list(artifact.declared_legacy_metadata_loss),
    }


def _report_bytes(artifact: c8.ResearchDraftArtifact) -> bytes:
    return canonical_json(_report_body(artifact)).encode("utf-8")


def _staged_provenance(
    artifact: c8.ResearchDraftArtifact,
) -> dict[str, object]:
    return {
        "schema": C8_ARTIFACT_SCHEMA,
        "artifact_id": artifact.artifact_id,
        "artifact_digest": artifact.artifact_digest,
        "project_key": artifact.project_key,
        "base_revision": artifact.base_revision,
        "base_incarnation": artifact.base_incarnation,
        "provenance_closure": [
            {
                "identity": entry.identity,
                "digest": entry.digest,
                "revision": entry.revision,
                "incarnation": entry.incarnation,
                "handle_id": entry.handle_id,
                "fields_digest": entry.fields_digest,
            }
            for entry in artifact.provenance_closure
        ],
        "citation_closure": [
            {
                "citation_id": ref.citation_id,
                "source_identity": ref.source_identity,
                "source_digest": ref.source_digest,
                "position": ref.position,
                "source_revision": ref.source_revision,
                "source_incarnation": ref.source_incarnation,
                "handle_id": ref.handle_id,
                "fields_digest": ref.fields_digest,
            }
            for ref in artifact.citation_closure.refs
        ],
        "declared_legacy_metadata_loss": list(artifact.declared_legacy_metadata_loss),
    }


def _report_provenance(
    artifact: c8.ResearchDraftArtifact,
) -> dict[str, object]:
    return {
        "schema": "mrw.successor.c8.report-value.v1",
        "artifact_id": artifact.artifact_id,
        "artifact_digest": artifact.artifact_digest,
        "project_key": artifact.project_key,
        "base_revision": artifact.base_revision,
        "base_incarnation": artifact.base_incarnation,
    }


def _put_value(
    connection: Connection,
    *,
    scope: RuntimeScope,
    value_id: str,
    object_type: str,
    codec_id: str,
    content: bytes,
    expected_digest: str,
    provenance_digest: str,
    incarnation: str,
    source_ref: str,
    provenance: Mapping[str, object],
) -> object:
    try:
        return ValueRepository(
            connection,
            project_tables(MetaData(), scope.project_scope.resolved_schema),
        ).put_exact(
            scope,
            value_id=value_id,
            object_type=object_type,
            codec_id=codec_id,
            content=content,
            expected_digest=expected_digest,
            provenance_digest=provenance_digest,
            expected_revision=0,
            expected_incarnation=incarnation,
            source_ref=source_ref,
            provenance=provenance,
            state="AVAILABLE",
        )
    except (ExactContentConflict, ProjectCASConflict, ProjectRecordNotFound) as exc:
        raise C8ArtifactIntegrityError(str(exc)) from exc


def _runtime_value_index(
    connection: Connection,
    *,
    scope: RuntimeScope,
    value_id: str,
    object_type: str,
    codec_id: str,
    content_digest_value: str,
    byte_size: int,
) -> Mapping[str, object]:
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    project_ref = f"{C8_VALUE_REF_PREFIX}{value_id}"
    storage_digest = content_digest(
        {
            "contract": "ProjectRuntimeValueBinding.v1",
            "project_key": scope.project_scope.project_key,
            "runtime_value_id": value_id,
            "project_value_ref": project_ref,
            "content_digest": content_digest_value,
            "codec_id": codec_id,
        }
    )
    project_row = (
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key
                == scope.project_scope.project_key,
                tables.successor_values.c.value_id == value_id,
            )
        )
        .mappings()
        .one()
    )
    return RuntimeValueRepository(connection, scope).put_exact(
        RuntimeValueBinding(
            value_id=value_id,
            object_type=object_type,
            codec_id=codec_id,
            content_digest=content_digest_value,
            byte_size=byte_size,
            project_value_ref=project_ref,
            storage_digest=storage_digest,
            write_intent_digest=str(project_row["write_intent_digest"]),
        )
    )


def stage_artifact(
    connection: Connection,
    *,
    scope: RuntimeScope,
    artifact: c8.ResearchDraftArtifact,
    run_id: str,
    step_id: str,
    attempt_id: str | None = None,
    qualifier_ref: str,
) -> C8StagedArtifactRef:
    """Stage exact Markdown bytes and the runtime staged-artifact row."""

    require_exact_artifact(artifact, scope.project_scope.project_key)
    value_id = staged_artifact_value_id(artifact.artifact_id)
    exact = artifact.markdown_bytes
    content_digest_value = sha256_hex(exact)
    incarnation = f"c8:staged-artifact:{artifact.artifact_digest}"
    provenance = _staged_provenance(artifact)
    provenance_digest = content_digest(provenance)
    stored = _put_value(
        connection,
        scope=scope,
        value_id=value_id,
        object_type=C8_STAGED_ARTIFACT_OBJECT_TYPE,
        codec_id=C8_STAGED_ARTIFACT_CODEC_ID,
        content=exact,
        expected_digest=content_digest_value,
        provenance_digest=provenance_digest,
        incarnation=incarnation,
        source_ref=f"c8:artifact:{artifact.artifact_id}",
        provenance=provenance,
    )
    _runtime_value_index(
        connection,
        scope=scope,
        value_id=value_id,
        object_type=C8_STAGED_ARTIFACT_OBJECT_TYPE,
        codec_id=C8_STAGED_ARTIFACT_CODEC_ID,
        content_digest_value=content_digest_value,
        byte_size=len(exact),
    )
    staged = StagedArtifactRepository(connection, scope).stage(
        StagedArtifactBinding(
            artifact_id=artifact.artifact_id,
            run_id=run_id,
            step_id=step_id,
            attempt_id=attempt_id,
            value_id=value_id,
            qualifier_ref=qualifier_ref,
        )
    )
    return C8StagedArtifactRef(
        artifact_id=artifact.artifact_id,
        value_id=value_id,
        value_ref=C8_VALUE_REF_PREFIX + value_id,
        revision=stored.revision,
        incarnation=stored.incarnation,
        content_digest=content_digest_value,
        state=str(staged["state"]),
    )


def _load_staged(
    connection: Connection,
    scope: RuntimeScope,
    artifact_id: str,
    *,
    for_update: bool = False,
) -> Mapping[str, object]:
    try:
        return StagedArtifactRepository(connection, scope).load(
            artifact_id,
            for_update=for_update,
        )
    except RecordNotFound as exc:
        raise C8ArtifactMissingError(
            f"staged artifact not found: {artifact_id}"
        ) from exc


def read_staged_artifact(
    connection: Connection,
    *,
    scope: RuntimeScope,
    artifact_id: str,
) -> c8.ResearchDraftArtifact:
    """Exact-read the durable staged artifact and rebuild its DTO."""

    staged = _load_staged(connection, scope, artifact_id)
    value_id = staged_artifact_value_id(artifact_id)
    if str(staged["value_id"]) != value_id:
        raise C8ArtifactIntegrityError("staged artifact value identity drift")
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    row = (
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key
                == scope.project_scope.project_key,
                tables.successor_values.c.value_id == value_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise C8ArtifactMissingError(f"staged artifact value not found: {artifact_id}")
    if (
        str(row["object_type"]) != C8_STAGED_ARTIFACT_OBJECT_TYPE
        or str(row["codec_id"]) != C8_STAGED_ARTIFACT_CODEC_ID
    ):
        raise C8ArtifactIntegrityError("staged artifact value codec/object type drift")
    if str(row["state"]) != "AVAILABLE":
        raise C8ArtifactIntegrityError("staged artifact value state drift")
    if int(row["revision"]) != 1:
        raise C8ArtifactIntegrityError("staged artifact value revision drift")
    if str(row["source_ref"]) != f"c8:artifact:{artifact_id}":
        raise C8ArtifactIntegrityError("staged artifact value source ref drift")
    if row["content_json"] is not None:
        raise C8ArtifactIntegrityError(
            "staged artifact value must be stored as content_bytes"
        )
    raw = row["content_bytes"]
    if raw is None:
        raise C8ArtifactIntegrityError(
            "staged artifact value is not stored as content_bytes"
        )
    markdown_bytes = bytes(raw)
    if sha256_hex(markdown_bytes) != str(row["content_digest"]):
        raise C8ArtifactIntegrityError(
            "staged artifact value bytes fail content digest readback"
        )
    provenance = row["provenance_json"]
    if not isinstance(provenance, dict):
        raise C8ArtifactIntegrityError("staged artifact provenance is not an object")
    if content_digest(dict(provenance)) != str(row["provenance_digest"]):
        raise C8ArtifactIntegrityError(
            "staged artifact provenance fails digest readback"
        )
    if (
        str(provenance.get("schema")) != C8_ARTIFACT_SCHEMA
        or str(provenance.get("artifact_id")) != artifact_id
        or str(provenance.get("project_key")) != scope.project_scope.project_key
    ):
        raise C8ArtifactIntegrityError("staged artifact provenance identity drift")
    provenance_closure = tuple(
        c8.ProvenanceClosureEntry(
            identity=str(entry["identity"]),
            digest=str(entry["digest"]),
            revision=int(entry["revision"]),
            incarnation=str(entry["incarnation"]),
            handle_id=str(entry["handle_id"]),
            fields_digest=str(entry["fields_digest"]),
        )
        for entry in provenance["provenance_closure"]
    )
    citation_closure = c8.CitationClosure(
        tuple(
            c8.CitationRef(
                citation_id=str(ref["citation_id"]),
                source_identity=str(ref["source_identity"]),
                source_digest=str(ref["source_digest"]),
                position=int(ref["position"]),
                source_revision=int(ref["source_revision"]),
                source_incarnation=str(ref["source_incarnation"]),
                handle_id=str(ref["handle_id"]),
                fields_digest=str(ref["fields_digest"]),
            )
            for ref in provenance["citation_closure"]
        )
    )
    artifact = c8.ResearchDraftArtifact(
        artifact_id=artifact_id,
        project_key=scope.project_scope.project_key,
        markdown_bytes=markdown_bytes,
        base_revision=int(provenance["base_revision"]),
        base_incarnation=str(provenance["base_incarnation"]),
        provenance_closure=provenance_closure,
        citation_closure=citation_closure,
        declared_legacy_metadata_loss=tuple(
            str(item) for item in provenance["declared_legacy_metadata_loss"]
        ),
    )
    artifact = dataclasses.replace(
        artifact,
        artifact_digest=c8.research_draft_artifact_digest(artifact),
    )
    if artifact.artifact_digest != str(provenance["artifact_digest"]):
        raise C8ArtifactIntegrityError(
            "staged artifact digest drift on durable readback"
        )
    if str(row["incarnation"]) != f"c8:staged-artifact:{artifact.artifact_digest}":
        raise C8ArtifactIntegrityError("staged artifact value incarnation drift")
    expected_write_intent = derive_value_write_intent_digest(
        project_key=scope.project_scope.project_key,
        value_id=value_id,
        object_type=C8_STAGED_ARTIFACT_OBJECT_TYPE,
        codec_id=C8_STAGED_ARTIFACT_CODEC_ID,
        content_digest=str(row["content_digest"]),
        provenance_digest=str(row["provenance_digest"]),
        source_ref=f"c8:artifact:{artifact_id}",
        expected_revision=0,
        expected_incarnation=f"c8:staged-artifact:{artifact.artifact_digest}",
        state="AVAILABLE",
    )
    if str(row["write_intent_digest"]) != expected_write_intent:
        raise C8ArtifactIntegrityError(
            "staged artifact value write intent digest drift"
        )
    if row["write_receipt_digest"] is not None:
        raise C8ArtifactIntegrityError(
            "staged artifact value has an unexpected write receipt"
        )
    return artifact


def _require_verified(verification: c8.ReportVerification) -> None:
    if verification.state != "VERIFIED":
        raise C8ArtifactIntegrityError("artifact verification is not in VERIFIED state")
    if not (
        verification.authority_kind
        and verification.authority_digest
        and verification.verifier_registry_id
        and verification.verifier_registry_digest
    ):
        raise C8ArtifactIntegrityError(
            "artifact verification lacks root-issued authority/registry fields"
        )


def verify_artifact(
    connection: Connection,
    *,
    scope: RuntimeScope,
    artifact: c8.ResearchDraftArtifact,
    verification: c8.ReportVerification,
) -> Mapping[str, object]:
    """Verify staged bytes and advance STAGED -> VERIFIED."""

    require_exact_artifact(artifact, scope.project_scope.project_key)
    _require_verified(verification)
    staged = _load_staged(
        connection,
        scope,
        artifact.artifact_id,
        for_update=True,
    )
    if str(staged["state"]) == "VERIFIED":
        return staged
    if str(staged["state"]) != "STAGED":
        raise C8ArtifactLifecycleError(
            f"verify requires STAGED, observed {staged['state']}"
        )
    value_id = staged_artifact_value_id(artifact.artifact_id)
    if str(staged["value_id"]) != value_id:
        raise C8ArtifactIntegrityError("staged artifact value identity drift")
    try:
        exact = ValueRepository(
            connection,
            project_tables(MetaData(), scope.project_scope.resolved_schema),
        ).get_exact(
            scope,
            value_id,
            expected_revision=1,
            expected_incarnation=f"c8:staged-artifact:{artifact.artifact_digest}",
            expected_digest=sha256_hex(artifact.markdown_bytes),
        )
    except ProjectRecordNotFound as exc:
        raise C8ArtifactIntegrityError(
            "staged artifact value does not match the exact artifact"
        ) from exc
    except (ExactContentConflict, ProjectCASConflict) as exc:
        raise C8ArtifactIntegrityError(str(exc)) from exc
    if exact != artifact.markdown_bytes:
        raise C8ArtifactIntegrityError("staged artifact bytes drift")
    return StagedArtifactRepository(connection, scope).transition(
        artifact.artifact_id,
        expected_revision=int(staged["revision"]),
        expected_state="STAGED",
        target_state="VERIFIED",
    )


def artifact_idempotency_key(artifact_id: str) -> str:
    return f"c8:report:admit:{artifact_id}"


def _commit_binding(
    artifact: c8.ResearchDraftArtifact,
    *,
    verification: c8.ReportVerification,
    run_id: str,
    step_id: str,
    idempotency_key: str,
) -> CommitIntentBinding:
    return CommitIntentBinding(
        commit_intent_id=f"commit:c8:report:{artifact.artifact_id}",
        run_id=run_id,
        step_id=step_id,
        capability_id=C8_ARTIFACT_OWNER,
        canonical_owner_ref=C8_ARTIFACT_OWNER,
        object_identity_ref=f"c8:report:{artifact.artifact_id}",
        expected_base_revision=artifact.base_revision,
        expected_base_incarnation=artifact.base_incarnation,
        content_digest=artifact.artifact_digest,
        event_digest=content_digest(
            {
                "schema": "mrw.successor.c8.report-admission.v1",
                "artifact_id": artifact.artifact_id,
                "artifact_digest": artifact.artifact_digest,
                "project_key": artifact.project_key,
                "verification_id": verification.verification_id,
                "authority_kind": verification.authority_kind,
                "authority_digest": verification.authority_digest,
                "verifier_registry_id": verification.verifier_registry_id,
                "verifier_registry_digest": verification.verifier_registry_digest,
            }
        ),
        verification_digest=verification.object_digest,
        authority_digest=verification.authority_digest,
        idempotency_key=idempotency_key,
    )


def _artifact_readback(
    connection: Connection,
    *,
    scope: RuntimeScope,
    artifact: c8.ResearchDraftArtifact,
    verification: c8.ReportVerification,
    idempotency_key: str,
) -> C8ArtifactReadback:
    intent = CommitIntentRepository(connection, scope).find_for_readback(
        C8_ARTIFACT_OWNER,
        idempotency_key,
    )
    if str(intent["state"]) != CommitIntentStatus.COMMITTED.value:
        raise C8ArtifactOutcomeUnknownError(
            "report readback requires a committed commit intent"
        )
    if (
        str(intent["object_identity_ref"]) != f"c8:report:{artifact.artifact_id}"
        or intent["content_digest"] != artifact.artifact_digest
        or int(intent["expected_base_revision"]) != artifact.base_revision
        or intent["expected_base_incarnation"] != artifact.base_incarnation
        or intent["authority_digest"] != verification.authority_digest
        or intent["verification_digest"] != verification.object_digest
    ):
        raise C8ArtifactIdempotencyConflictError(
            "committed intent no longer matches the exact artifact/authority"
        )
    staged = _load_staged(connection, scope, artifact.artifact_id)
    if str(staged["state"]) != "ADMITTED":
        raise C8ArtifactIntegrityError(
            f"readback requires ADMITTED, observed {staged['state']}"
        )
    try:
        canonical = ValueRepository(
            connection,
            project_tables(MetaData(), scope.project_scope.resolved_schema),
        ).get_exact(
            scope,
            report_value_id(artifact.artifact_id),
            expected_revision=1,
            expected_incarnation=f"c8:report:{artifact.artifact_digest}",
            expected_digest=artifact.artifact_digest,
        )
    except ProjectRecordNotFound as exc:
        raise C8ArtifactIntegrityError(
            "canonical report value is absent or drifted"
        ) from exc
    except (ExactContentConflict, ProjectCASConflict) as exc:
        raise C8ArtifactIntegrityError(str(exc)) from exc
    if canonical != _report_bytes(artifact):
        raise C8ArtifactIntegrityError("canonical report value bytes drift")
    readback_digest = content_digest(
        {
            "schema": "mrw.successor.c8.report-readback.v1",
            "commit_intent_id": intent["commit_intent_id"],
            "idempotency_key": idempotency_key,
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.artifact_digest,
            "canonical_commit_ref": intent["canonical_commit_ref"],
            "receipt_digest": intent["receipt_digest"],
            "verification_id": verification.verification_id,
            "authority_digest": verification.authority_digest,
            "verifier_registry_digest": verification.verifier_registry_digest,
        }
    )
    return C8ArtifactReadback(
        commit_intent_id=str(intent["commit_intent_id"]),
        idempotency_key=idempotency_key,
        capability_id=C8_ARTIFACT_OWNER,
        project_key=artifact.project_key,
        artifact_id=artifact.artifact_id,
        artifact_digest=artifact.artifact_digest,
        canonical_commit_ref=str(intent["canonical_commit_ref"]),
        receipt_digest=str(intent["receipt_digest"]),
        verification_id=verification.verification_id,
        authority_kind=verification.authority_kind,
        authority_digest=verification.authority_digest,
        verifier_registry_id=verification.verifier_registry_id,
        verifier_registry_digest=verification.verifier_registry_digest,
        readback_digest=readback_digest,
    )


def admit_artifact(
    connection: Connection,
    *,
    scope: RuntimeScope,
    artifact: c8.ResearchDraftArtifact,
    verification: c8.ReportVerification,
    run_id: str,
    step_id: str,
) -> C8ArtifactReadback:
    """Admit a verified report; all commit/receipt refs are derived internally."""

    require_exact_artifact(artifact, scope.project_scope.project_key)
    _require_verified(verification)
    idempotency_key = artifact_idempotency_key(artifact.artifact_id)
    staged = _load_staged(
        connection,
        scope,
        artifact.artifact_id,
        for_update=True,
    )
    if str(staged["state"]) not in {"VERIFIED", "ADMITTED"}:
        raise C8ArtifactLifecycleError(
            f"admit requires VERIFIED, observed {staged['state']}"
        )
    canonical_commit_ref = (
        f"canonical:report:{artifact.project_key}:{artifact.artifact_id}:1"
    )
    receipt_digest = content_digest(
        {
            "schema": "mrw.successor.c8.report-receipt.v1",
            "artifact_id": artifact.artifact_id,
            "artifact_digest": artifact.artifact_digest,
            "project_key": artifact.project_key,
            "verification_id": verification.verification_id,
            "authority_digest": verification.authority_digest,
            "verifier_registry_digest": verification.verifier_registry_digest,
        }
    )
    repo = CommitIntentRepository(connection, scope)
    try:
        existing = repo.find_for_readback(C8_ARTIFACT_OWNER, idempotency_key)
    except RecordNotFound:
        existing = None
    if existing is not None and (
        existing["state"] == CommitIntentStatus.COMMITTED.value
    ):
        return _artifact_readback(
            connection,
            scope=scope,
            artifact=artifact,
            verification=verification,
            idempotency_key=idempotency_key,
        )
    binding = _commit_binding(
        artifact,
        verification=verification,
        run_id=run_id,
        step_id=step_id,
        idempotency_key=idempotency_key,
    )
    report_value = report_value_id(artifact.artifact_id)
    report_exact = _report_bytes(artifact)
    report_provenance = _report_provenance(artifact)
    try:
        with connection.begin_nested():
            try:
                repo.prepare(binding)
            except ExactBindingConflict as exc:
                raise C8ArtifactIdempotencyConflictError(
                    "artifact idempotency key is bound to different exact content"
                ) from exc
            _put_value(
                connection,
                scope=scope,
                value_id=report_value,
                object_type=C8_REPORT_VALUE_OBJECT_TYPE,
                codec_id=C8_REPORT_VALUE_CODEC_ID,
                content=report_exact,
                expected_digest=artifact.artifact_digest,
                provenance_digest=content_digest(report_provenance),
                incarnation=f"c8:report:{artifact.artifact_digest}",
                source_ref=f"c8:artifact:{artifact.artifact_id}",
                provenance=report_provenance,
            )
            _runtime_value_index(
                connection,
                scope=scope,
                value_id=report_value,
                object_type=C8_REPORT_VALUE_OBJECT_TYPE,
                codec_id=C8_REPORT_VALUE_CODEC_ID,
                content_digest_value=artifact.artifact_digest,
                byte_size=len(report_exact),
            )
            StagedArtifactRepository(connection, scope).transition(
                artifact.artifact_id,
                expected_revision=int(staged["revision"]),
                expected_state="VERIFIED",
                target_state="ADMITTED",
            )
            repo.record_result(
                binding.commit_intent_id,
                expected_revision=0,
                status=CommitIntentStatus.COMMITTED,
                canonical_commit_ref=canonical_commit_ref,
                receipt_digest=receipt_digest,
            )
    except StaleRevisionError as exc:
        raise C8ArtifactOutcomeUnknownError(
            "commit intent CAS failed after canonical report write"
        ) from exc
    except C8ArtifactHandlerError:
        raise
    except RecordNotFound as exc:
        raise C8ArtifactMissingError(
            "admission runtime step binding is absent"
        ) from exc
    return _artifact_readback(
        connection,
        scope=scope,
        artifact=artifact,
        verification=verification,
        idempotency_key=idempotency_key,
    )


def readback_artifact(
    connection: Connection,
    *,
    scope: RuntimeScope,
    artifact: c8.ResearchDraftArtifact,
    verification: c8.ReportVerification,
) -> C8ArtifactReadback:
    """Authoritative stored-fact readback of an admitted report."""

    require_exact_artifact(artifact, scope.project_scope.project_key)
    _require_verified(verification)
    idempotency_key = artifact_idempotency_key(artifact.artifact_id)
    try:
        return _artifact_readback(
            connection,
            scope=scope,
            artifact=artifact,
            verification=verification,
            idempotency_key=idempotency_key,
        )
    except RecordNotFound as exc:
        raise C8ArtifactMissingError(
            "report readback intent not found for artifact"
        ) from exc
