"""Terminal-UoW bridge for first-specimen staged canonical admission.

The effect handler remains deliberately read-only: it proves that a claimed
``VERIFY_ADMIT`` assignment names one exact, already verified staged value and
returns that value's digest.  Canonical mutation is enlisted later by
``PostgresFirstSpecimenTerminalHook`` in the RuntimeNode terminal UoW.  The
hook re-opens current authority/base/event state, uses the existing
``AdmissionCoordinator`` and capability-owned PostgreSQL admission handler,
and finally lets the shared lifecycle repository append the terminal event and
move ``VERIFIED -> ADMITTED`` atomically.

This module does not own transactions, scheduler state, or a second admission
algorithm.  It delegates ``RUNNING -> CommitPrepared -> COMMITTING`` to the
shared lifecycle repository before crossing the canonical admission boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Protocol, Self

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.research.artifacts import (
    DeliveryReceiptRef,
    ResearchArtifact,
)
from app.successor_runtime.research.claims import Claim, Gap
from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.research.evidence import EvidenceQualification, Validity
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import (
    CLAIM_TYPE,
    DELIVERY_RECEIPT_REF_TYPE,
    EVIDENCE_QUALIFICATION_TYPE,
    GAP_TYPE,
    OBJECT_TYPE_BY_ID,
    RESEARCH_ARTIFACT_TYPE,
)
from app.successor_runtime.research.relations import ResearchRelation
from app.successor_runtime.runtime.admission import CommitIntent, VerificationBinding
from app.successor_runtime.runtime.admission_coordinator import (
    AdmissionCoordinator,
    AdmissionProgress,
    AdmissionResult,
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
from app.successor_runtime.runtime.qualification import (
    StepAuthorizationBinding,
    require_current_authority,
)
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    ReconciliationHandlerOutcome,
    ReconciliationResult,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition

from .authority_provider import PostgresAuthorityProvider
from .commit_intents import CommitIntentRepository
from .models import PUBLIC_TABLES, ProjectTables, project_tables
from .plans import PlanRepository
from .research_admission import (
    DeliveryReceiptCandidate,
    EvidenceRelationCandidate,
    PostgresCommitIntentAdapter,
    ResearchObjectCandidate,
    build_first_specimen_admission_registry,
    commit_binding_from_assignment,
)
from .research_ledger import one_mapping
from .runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    validate_authorization_row,
)
from .runtime_lifecycle import (
    ClaimedLifecycle,
    RuntimeLifecycleRepository,
    TerminalOutcome,
)
from .session import ProjectScopeStale, ServerProjectScopeResolver
from .staged_artifacts import StagedArtifactRepository


class FirstSpecimenTerminalError(ExactBindingConflict):
    """The terminal admission closure cannot be reconstructed exactly."""


class FirstSpecimenTerminalLifecycleGap(FirstSpecimenTerminalError):
    """Shared lifecycle has not yet entered the frozen admission state."""


class FirstSpecimenCandidateDecodeError(FirstSpecimenTerminalError):
    """Staged canonical bytes do not decode to the frozen result type."""


class TerminalReadUnitOfWork(Protocol):
    connection: Connection

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


TerminalReadUnitOfWorkFactory = Callable[[], TerminalReadUnitOfWork]


class FirstSpecimenActivationPort(Protocol):
    """Capability-local adapter around the shared ``activate_run`` fold."""

    def activate_after_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        run_id: str,
        observed_at: datetime,
    ) -> object: ...


class DeliveryReceiptContentPort(Protocol):
    """Authoritative internal-export receipt bytes, never a redispatch port."""

    def read_exact_receipt(
        self,
        *,
        scope: RuntimeScope,
        receipt: DeliveryReceiptRef,
    ) -> bytes | dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ExactFirstSpecimenStage:
    """Exact public/project readback of one effect result staged for admission."""

    scope: RuntimeScope
    tables: ProjectTables
    plan: ExecutionPlan
    assignment: RuntimeAssignment
    staged_row: Mapping[str, Any]
    runtime_value_row: Mapping[str, Any]
    project_value_row: Mapping[str, Any]
    effect_step_row: Mapping[str, Any]
    effect_attempt_row: Mapping[str, Any]
    exact_bytes: bytes

    @property
    def artifact_id(self) -> str:
        return str(self.staged_row["artifact_id"])

    @property
    def staged_revision(self) -> int:
        return int(self.staged_row["revision"])

    @property
    def content_digest(self) -> str:
        return str(self.runtime_value_row["content_digest"])

    @property
    def object_type(self) -> str:
        return str(self.runtime_value_row["object_type"])

    @property
    def project_value_ref(self) -> str:
        return str(self.runtime_value_row["project_value_ref"])

    @property
    def provenance_digest(self) -> str:
        return str(self.project_value_row["provenance_digest"])


@dataclass(frozen=True, slots=True)
class ExactAdmissionPacket:
    candidate: object
    intent: CommitIntent
    binding: VerificationBinding
    ordered_event_payloads: tuple[object, ...]
    authorization: StepAuthorizationBinding


class PostgresFirstSpecimenStageReader:
    """Read and validate the compiled effect/admission/staged-value closure."""

    def load_exact(
        self,
        connection: Connection,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        *,
        expected_state: str,
    ) -> ExactFirstSpecimenStage:
        compiled = assignment.compiled_admission_binding
        if (
            assignment.assignment_kind is not AssignmentKind.VERIFY_ADMIT
            or compiled is None
        ):
            raise FirstSpecimenTerminalError(
                "staged admission readback requires VERIFY_ADMIT with compiled binding"
            )
        claim.validate_against(assignment)
        if assignment.step_id != compiled.admission_step_id:
            raise FirstSpecimenTerminalError("compiled admission step identity drift")

        run = self._one(
            connection,
            PUBLIC_TABLES["runtime_runs"],
            project_key=assignment.project_key,
            run_id=assignment.run_id,
        )
        self._require_run_scope(run, scope, assignment)
        if run["plan_digest"] != assignment.plan_digest or run["plan_id"] is None:
            raise FirstSpecimenTerminalError("run/assignment Plan identity drift")
        tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
        plan = PlanRepository(connection, tables).get(scope, str(run["plan_digest"]))
        self._require_compiled_pair(plan, assignment)

        staged_rows = tuple(
            connection.execute(
                select(PUBLIC_TABLES["runtime_staged_artifacts"])
                .where(
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.project_key
                    == assignment.project_key,
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.run_id
                    == assignment.run_id,
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.step_id
                    == compiled.effect_step_id,
                )
                .with_for_update(read=True)
            ).mappings()
        )
        if len(staged_rows) != 1:
            raise FirstSpecimenTerminalError(
                "compiled effect step lacks one exact staged artifact"
            )
        staged = staged_rows[0]
        if staged["state"] != expected_state:
            raise FirstSpecimenTerminalError(
                f"staged artifact must be {expected_state} before VERIFY_ADMIT"
            )
        if not staged["attempt_id"]:
            raise FirstSpecimenTerminalError(
                "staged artifact lacks effect attempt identity"
            )

        effect_step = self._one(
            connection,
            PUBLIC_TABLES["runtime_steps"],
            project_key=assignment.project_key,
            run_id=assignment.run_id,
            step_id=compiled.effect_step_id,
        )
        effect_attempt = self._one(
            connection,
            PUBLIC_TABLES["runtime_effect_attempts"],
            project_key=assignment.project_key,
            attempt_id=staged["attempt_id"],
        )
        runtime_value = self._one(
            connection,
            PUBLIC_TABLES["runtime_values"],
            project_key=assignment.project_key,
            value_id=staged["value_id"],
        )
        project_ref = runtime_value["project_value_ref"]
        if not isinstance(project_ref, str) or not project_ref.startswith(
            "project-value:"
        ):
            raise FirstSpecimenTerminalError(
                "first-specimen staged result is not project-value owned"
            )
        if project_ref not in assignment.input_refs:
            raise FirstSpecimenTerminalError(
                "VERIFY_ADMIT ordered inputs omit the staged project value"
            )
        project_value_id = project_ref.removeprefix("project-value:")
        project_value = self._one(
            connection,
            tables.successor_values,
            project_key=assignment.project_key,
            value_id=project_value_id,
        )
        exact = self._exact_bytes(project_value)
        expected = {
            "stage_value_id": (staged["value_id"], runtime_value["value_id"]),
            "effect_state": (effect_step["state"], "SUCCEEDED"),
            "effect_output": (
                effect_step["output_digest"],
                runtime_value["content_digest"],
            ),
            "effect_attempt": (effect_attempt["attempt_id"], staged["attempt_id"]),
            "effect_disposition": (effect_attempt["disposition"], "SUCCEEDED"),
            "effect_run": (effect_attempt["run_id"], assignment.run_id),
            "effect_step": (effect_attempt["step_id"], compiled.effect_step_id),
            "runtime_state": (runtime_value["state"], "AVAILABLE"),
            "project_state": (project_value["state"], "AVAILABLE"),
            "content_digest": (
                project_value["content_digest"],
                runtime_value["content_digest"],
            ),
            "codec": (project_value["codec_id"], runtime_value["codec_id"]),
            "object_type": (
                project_value["object_type"],
                runtime_value["object_type"],
            ),
        }
        if expected_state != "ADMITTED":
            expected["stage_receipt"] = (
                staged["receipt_ref"],
                effect_attempt["receipt_ref"],
            )
        drift = tuple(name for name, pair in expected.items() if pair[0] != pair[1])
        if drift:
            raise FirstSpecimenTerminalError(
                "staged effect/value exact binding drift: " + ", ".join(drift)
            )
        if len(exact) != int(runtime_value["byte_size"]):
            raise FirstSpecimenTerminalError("staged value byte-size drift")
        if hashlib.sha256(exact).hexdigest() != runtime_value["content_digest"]:
            raise FirstSpecimenTerminalError("staged value content digest drift")
        provenance = project_value["provenance_json"]
        if (
            not isinstance(provenance, Mapping)
            or sha256_hex(dict(provenance)) != (project_value["provenance_digest"])
        ):
            raise FirstSpecimenTerminalError("staged value provenance digest drift")
        return ExactFirstSpecimenStage(
            scope=scope,
            tables=tables,
            plan=plan,
            assignment=assignment,
            staged_row=staged,
            runtime_value_row=runtime_value,
            project_value_row=project_value,
            effect_step_row=effect_step,
            effect_attempt_row=effect_attempt,
            exact_bytes=exact,
        )

    @staticmethod
    def _one(
        connection: Connection, table: Any, **identity: object
    ) -> Mapping[str, Any]:
        statement = select(table)
        for name, value in identity.items():
            statement = statement.where(getattr(table.c, name) == value)
        row = one_mapping(connection.execute(statement.with_for_update(read=True)))
        if row is None:
            rendered = ", ".join(
                f"{name}={value!r}" for name, value in identity.items()
            )
            raise RecordNotFound(
                f"exact terminal row not found: {table.name} {rendered}"
            )
        return row

    @staticmethod
    def _exact_bytes(row: Mapping[str, Any]) -> bytes:
        if row["content_bytes"] is not None and row["content_json"] is None:
            return bytes(row["content_bytes"])
        if row["content_json"] is not None and row["content_bytes"] is None:
            return canonical_bytes(row["content_json"])
        raise FirstSpecimenTerminalError(
            "staged project value must have exactly one canonical representation"
        )

    @staticmethod
    def _require_run_scope(
        run: Mapping[str, Any], scope: RuntimeScope, assignment: RuntimeAssignment
    ) -> None:
        ref = scope.project_scope
        expected = {
            "project_key": assignment.project_key,
            "program_digest": assignment.program_digest,
            "incarnation": assignment.incarnation,
            "execution_epoch": assignment.execution_epoch,
            "project_registry_revision": ref.project_registry_revision,
            "project_scope_digest": ref.scope_digest,
            "resolved_schema": ref.resolved_schema,
        }
        drift = tuple(name for name, value in expected.items() if run[name] != value)
        if drift:
            raise FirstSpecimenTerminalError(
                "run/scope/assignment drift: " + ", ".join(drift)
            )

    @staticmethod
    def _require_compiled_pair(
        plan: ExecutionPlan, assignment: RuntimeAssignment
    ) -> None:
        compiled = assignment.compiled_admission_binding
        assert compiled is not None
        if plan.plan_digest != compiled.plan_digest:
            raise FirstSpecimenTerminalError("compiled admission Plan digest drift")
        effect = tuple(
            step
            for step in plan.ordered_steps
            if step.step_id == compiled.effect_step_id
        )
        admission = tuple(
            step
            for step in plan.ordered_steps
            if step.step_id == compiled.admission_step_id
        )
        if len(effect) != 1 or len(admission) != 1:
            raise FirstSpecimenTerminalError(
                "compiled admission pair is absent from Plan"
            )
        effect_step, admission_step = effect[0], admission[0]
        if (
            effect_step.step_kind != "EFFECT"
            or admission_step.step_kind != "ADMISSION"
            or compiled.effect_step_id not in admission_step.dependencies
            or admission_step.operation_contract_ref
            != assignment.operation_contract_ref
            or admission_step.admission is None
            or admission_step.admission.effect_step_id != compiled.effect_step_id
            or admission_step.admission.admission_step_id != compiled.admission_step_id
        ):
            raise FirstSpecimenTerminalError(
                "compiled effect/admission structure drift"
            )


class PostgresVerifyAdmitHandler(RuntimeHandler):
    """Read-only exact verifier; canonical commit is terminal-hook owned."""

    def __init__(
        self,
        *,
        uow_factory: TerminalReadUnitOfWorkFactory,
        operation_contract_digest: str,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        stage_reader: PostgresFirstSpecimenStageReader | None = None,
    ) -> None:
        require_digest(operation_contract_digest, "operation_contract_digest")
        require_digest(handler_binding_digest, "handler_binding_digest")
        require_digest(interpreter_profile_digest, "interpreter_profile_digest")
        self._uow_factory = uow_factory
        self.operation_contract_digest = operation_contract_digest
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self._stage_reader = stage_reader or PostgresFirstSpecimenStageReader()

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        try:
            self._require_exact(assignment, claim)
            with self._uow_factory() as uow:
                scope = _resolve_scope(
                    uow.connection, assignment, actor_id=context.node.node_id
                )
                staged = self._stage_reader.load_exact(
                    uow.connection,
                    scope,
                    assignment,
                    claim,
                    expected_state="VERIFIED",
                )
            return InterpreterOutcome.succeeded(staged.content_digest)
        except (ExactBindingConflict, ValueError, TypeError) as exc:
            detail = re.sub(r"[^A-Z0-9]+", "_", str(exc).upper()).strip("_")
            code = type(exc).__name__.upper()
            if detail:
                code = f"{code}:{detail[:96]}"
            raise DefiniteInterpreterFailure(code) from exc

    def _require_exact(
        self, assignment: RuntimeAssignment, claim: ClaimBinding
    ) -> None:
        claim.validate_against(assignment)
        binding = assignment.handler_binding
        operation = assignment.operation_contract_ref
        if (
            assignment.assignment_kind is not AssignmentKind.VERIFY_ADMIT
            or assignment.compiled_admission_binding is None
            or operation is None
            or operation.contract_digest != self.operation_contract_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
            or assignment.handler_binding_digest != self.handler_binding_digest
            or getattr(binding, "interpreter_profile_digest", None)
            != self.interpreter_profile_digest
            or claim.interpreter_profile_digest != self.interpreter_profile_digest
        ):
            raise FirstSpecimenTerminalError("exact VERIFY_ADMIT handler binding drift")


class FirstSpecimenCandidateDecoder:
    """Strict decoder from staged canonical bytes to capability candidates."""

    def __init__(
        self, *, delivery_receipts: DeliveryReceiptContentPort | None = None
    ) -> None:
        self._delivery_receipts = delivery_receipts

    def decode_exact(
        self,
        connection: Connection,
        staged: ExactFirstSpecimenStage,
        authorization: StepAuthorizationBinding,
    ) -> object:
        try:
            raw = json.loads(staged.exact_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FirstSpecimenCandidateDecodeError(
                "staged candidate is not canonical JSON"
            ) from exc
        if not isinstance(raw, dict) or canonical_bytes(raw) != staged.exact_bytes:
            raise FirstSpecimenCandidateDecodeError(
                "staged candidate is not a canonical JSON object"
            )
        kind = staged.object_type
        if kind == EVIDENCE_QUALIFICATION_TYPE.type_id:
            qualification = _decode_qualification(raw, staged.content_digest)
            source = _load_current_object(
                connection, staged, qualification.material_ref
            )
            target = _load_current_object(
                connection,
                staged,
                qualification.claim_ref or qualification.inquiry_ref,
            )
            return EvidenceRelationCandidate(
                qualification=qualification,
                source_ref=source,
                target_ref=target,
                expected_revision=authorization.canonical_base_revision,
                expected_incarnation=authorization.canonical_incarnation,
            )
        if kind in {
            CLAIM_TYPE.type_id,
            GAP_TYPE.type_id,
            RESEARCH_ARTIFACT_TYPE.type_id,
        }:
            payload = _decode_object_payload(kind, raw, staged.content_digest)
            object_id = _payload_object_id(payload)
            owner = (
                "ResearchLedger_plus_project_artifact_store"
                if isinstance(payload, ResearchArtifact)
                else "ResearchLedger"
            )
            ref = ResearchObjectRef(
                object_id=object_id,
                object_type=OBJECT_TYPE_BY_ID[kind],
                project_key=staged.assignment.project_key,
                revision=authorization.canonical_base_revision + 1,
                incarnation=authorization.canonical_incarnation,
                owner_binding_ref=owner,
                content_ref=staged.project_value_ref,
                content_digest=staged.content_digest,
                provenance_closure_digest=staged.provenance_digest,
                lifecycle_state="ADMITTED",
            )
            return ResearchObjectCandidate(
                ref=ref,
                payload=payload,
                expected_revision=authorization.canonical_base_revision,
                expected_incarnation=authorization.canonical_incarnation,
            )
        if kind == DELIVERY_RECEIPT_REF_TYPE.type_id:
            receipt = _decode_delivery_receipt(raw, staged.content_digest)
            artifact = _load_delivery_artifact(connection, staged, receipt)
            receipt_ref = ResearchObjectRef(
                object_id=receipt.receipt_ref,
                object_type=DELIVERY_RECEIPT_REF_TYPE,
                project_key=staged.assignment.project_key,
                revision=authorization.canonical_base_revision + 1,
                incarnation=authorization.canonical_incarnation,
                owner_binding_ref="project_receipt_store",
                content_ref=staged.project_value_ref,
                content_digest=staged.content_digest,
                provenance_closure_digest=staged.provenance_digest,
                lifecycle_state="ADMITTED",
            )
            relation_incarnation = "delivered-as-" + authorization.canonical_incarnation
            delivered_as = ResearchRelation(
                relation_id=f"delivered-as:{receipt.receipt_ref}",
                relation_type="delivered_as",
                project_key=staged.assignment.project_key,
                source_ref=artifact,
                target_ref=receipt_ref,
                provenance_closure_digest=canonical_digest(
                    {
                        "artifact_ref": artifact.content_digest,
                        "receipt_ref": receipt.receipt_ref,
                        "receipt_digest": receipt.receipt_digest,
                        "attempt_ref": receipt.attempt_ref,
                    }
                ),
                revision=1,
                incarnation=relation_incarnation,
            )
            content = (
                self._delivery_receipts.read_exact_receipt(
                    scope=staged.scope, receipt=receipt
                )
                if self._delivery_receipts is not None
                else _read_project_provider_receipt(connection, staged, receipt)
            )
            exact_receipt = (
                content if isinstance(content, bytes) else canonical_bytes(content)
            )
            if hashlib.sha256(exact_receipt).hexdigest() != receipt.receipt_digest:
                raise FirstSpecimenCandidateDecodeError(
                    "authoritative delivery receipt bytes drift"
                )
            return DeliveryReceiptCandidate(
                ref=receipt_ref,
                receipt=receipt,
                receipt_content=content,
                artifact_ref=artifact,
                delivered_as=delivered_as,
                expected_revision=authorization.canonical_base_revision,
                expected_incarnation=authorization.canonical_incarnation,
                expected_relation_revision=0,
                expected_relation_incarnation=relation_incarnation,
            )
        raise FirstSpecimenCandidateDecodeError(
            f"unsupported first-specimen admission object type: {kind}"
        )


def _read_project_provider_receipt(
    connection: Connection,
    staged: ExactFirstSpecimenStage,
    receipt: DeliveryReceiptRef,
) -> bytes:
    """Read the exact provider receipt body staged by the delivery handler."""

    provenance = staged.project_value_row["provenance_json"]
    if not isinstance(provenance, Mapping):
        raise FirstSpecimenCandidateDecodeError(
            "delivery candidate provenance is malformed"
        )
    locator = provenance.get("provider_receipt_content_ref")
    declared_digest = provenance.get("provider_receipt_content_digest")
    prefix = "project-value:"
    if (
        not isinstance(locator, str)
        or not locator.startswith(prefix)
        or not isinstance(declared_digest, str)
        or declared_digest != receipt.receipt_digest
    ):
        raise FirstSpecimenCandidateDecodeError(
            "delivery provider receipt content binding is absent"
        )
    row = one_mapping(
        connection.execute(
            select(staged.tables.successor_values).where(
                staged.tables.successor_values.c.project_key
                == staged.assignment.project_key,
                staged.tables.successor_values.c.value_id
                == locator.removeprefix(prefix),
            )
        )
    )
    if (
        row is None
        or row["object_type"] != "InternalExportProviderReceipt.v1"
        or row["content_digest"] != declared_digest
        or row["state"] != "AVAILABLE"
    ):
        raise FirstSpecimenCandidateDecodeError(
            "exact project provider receipt is absent"
        )
    exact = PostgresFirstSpecimenStageReader._exact_bytes(row)
    if hashlib.sha256(exact).hexdigest() != receipt.receipt_digest:
        raise FirstSpecimenCandidateDecodeError(
            "authoritative delivery receipt bytes drift"
        )
    return exact


AdmissionCoordinatorFactory = Callable[
    [Connection, RuntimeScope, ProjectTables], AdmissionCoordinator
]
PlanRepositoryFactory = Callable[[Connection, ProjectTables], Any]


class PostgresFirstSpecimenTerminalHook:
    """Enlist staged lifecycle, canonical admission, and activation in one UoW."""

    def __init__(
        self,
        *,
        bundle: Any,
        activation: FirstSpecimenActivationPort,
        stage_reader: PostgresFirstSpecimenStageReader | None = None,
        candidate_decoder: FirstSpecimenCandidateDecoder | None = None,
        admission_factory: AdmissionCoordinatorFactory | None = None,
        plan_repository_factory: PlanRepositoryFactory | None = None,
        authority_factory: Callable[
            [Connection, RuntimeScope], PostgresAuthorityProvider
        ] = PostgresAuthorityProvider,
    ) -> None:
        self._bundle = bundle
        self._activation = activation
        self._stage_reader = stage_reader or PostgresFirstSpecimenStageReader()
        self._decoder = candidate_decoder or FirstSpecimenCandidateDecoder()
        self._admission_factory = admission_factory or self._default_admission
        self._plan_repository_factory = plan_repository_factory or (
            lambda connection, tables: PlanRepository(connection, tables)
        )
        self._authority_factory = authority_factory

    def prepare_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        claim: Any,
        lifecycle: ClaimedLifecycle,
        outcome: InterpreterOutcome,
        terminal: TerminalOutcome,
    ) -> TerminalOutcome:
        assignment = claim.assignment
        if outcome.disposition is not EffectDisposition.SUCCEEDED:
            return terminal
        if assignment.assignment_kind is AssignmentKind.INTERPRET:
            binding = assignment.return_contract_binding
            if binding is None or not binding.admission_required:
                return terminal
            staged = _load_effect_stage(
                connection,
                scope,
                assignment,
                claim.claim_binding,
                expected_state="STAGED",
            )
            if staged.content_digest != outcome.result_digest:
                raise FirstSpecimenTerminalError(
                    "INTERPRET result digest differs from exact staged value"
                )
            return replace(
                terminal,
                staged_artifact_id=staged.artifact_id,
                expected_staged_revision=staged.staged_revision,
            )
        if assignment.assignment_kind is not AssignmentKind.VERIFY_ADMIT:
            return terminal

        step = _one_public(
            connection,
            "runtime_steps",
            project_key=assignment.project_key,
            run_id=assignment.run_id,
            step_id=assignment.step_id,
        )
        if step["state"] == "RUNNING":
            lifecycle = RuntimeLifecycleRepository(connection, scope).begin_commit(
                lifecycle,
                observed_at=terminal.observed_at,
            )
            terminal = replace(terminal, claimed=lifecycle)
        elif step["state"] != "COMMITTING":
            raise FirstSpecimenTerminalLifecycleGap(
                "VERIFY_ADMIT terminal hook requires shared lifecycle "
                "RUNNING -> CommitPrepared -> COMMITTING before canonical admission"
            )
        staged = self._stage_reader.load_exact(
            connection,
            scope,
            assignment,
            claim.claim_binding,
            expected_state="VERIFIED",
        )
        if staged.content_digest != outcome.result_digest:
            raise FirstSpecimenTerminalError(
                "VERIFY_ADMIT result digest differs from exact staged value"
            )
        packet = self._packet(
            connection=connection,
            scope=scope,
            staged=staged,
            claim=claim.claim_binding,
            observed_at=terminal.observed_at,
        )
        commit = self._commit_packet(
            connection=connection,
            scope=scope,
            staged=staged,
            packet=packet,
        )
        return replace(
            terminal,
            receipt_ref=f"receipt:sha256:{commit.receipt_digest}",
            receipt_digest=commit.receipt_digest,
            staged_artifact_id=staged.artifact_id,
            expected_staged_revision=staged.staged_revision,
            admit_staged=True,
            payload_ref=commit.canonical_ref,
            payload_digest=canonical_digest(commit),
        )

    def recover_admission(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        observed_at: datetime,
    ) -> ReconciliationHandlerOutcome:
        """Recover a VERIFY_ADMIT crash without re-running its verifier.

        The original verifier is read-only. Recovery reconstructs its exact
        admission packet and reuses ``AdmissionCoordinator`` so an existing
        commit intent is read back before any canonical mutation. The staged
        candidate remains ``VERIFIED`` here; only the authoritative runtime
        adoption UoW may advance it to ``ADMITTED`` together with the recovered
        attempt, work, step, run, and event facts.
        """

        if assignment.assignment_kind is not AssignmentKind.VERIFY_ADMIT:
            raise FirstSpecimenTerminalError(
                "admission recovery requires original VERIFY_ADMIT assignment"
            )
        claim.validate_against(assignment)
        compiled = assignment.compiled_admission_binding
        if compiled is None:
            raise FirstSpecimenTerminalError(
                "admission recovery lacks compiled effect/admission binding"
            )
        rows = tuple(
            connection.execute(
                select(PUBLIC_TABLES["runtime_staged_artifacts"])
                .where(
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.project_key
                    == assignment.project_key,
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.run_id
                    == assignment.run_id,
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.step_id
                    == compiled.effect_step_id,
                )
                .with_for_update()
            ).mappings()
        )
        if len(rows) != 1 or rows[0]["state"] != "VERIFIED":
            raise FirstSpecimenTerminalError(
                "admission recovery requires one exact VERIFIED candidate"
            )
        staged = self._stage_reader.load_exact(
            connection,
            scope,
            assignment,
            claim,
            expected_state="VERIFIED",
        )
        packet = self._packet(
            connection=connection,
            scope=scope,
            staged=staged,
            claim=claim,
            observed_at=observed_at,
            require_current_base=False,
            event_cutoff_attempt_id=claim.attempt_id,
        )

        admission_scope = RuntimeScope(
            project_scope=scope.project_scope,
            actor_id=packet.authorization.actor_id,
        )
        intent_repository = CommitIntentRepository(connection, admission_scope)
        try:
            existing_intent = intent_repository.load(packet.intent.commit_intent_id)
        except RecordNotFound:
            existing_intent = None
        if existing_intent is None:
            object_id, _owner = _candidate_identity(packet.candidate)
            _require_current_base(
                connection,
                staged,
                object_id=object_id,
                base_revision=packet.authorization.canonical_base_revision,
                incarnation=packet.authorization.canonical_incarnation,
            )

        commit = self._commit_packet(
            connection=connection,
            scope=scope,
            staged=staged,
            packet=packet,
            waiting_as_result=True,
        )
        if isinstance(commit, AdmissionResult):
            readback = commit.readback
            reason = (
                "CANONICAL_ADMISSION_READBACK_UNAVAILABLE"
                if readback is None or not readback.reason
                else readback.reason
            )
            observation_digest = (
                canonical_digest(
                    {
                        "commit_intent_id": packet.intent.commit_intent_id,
                        "reason": reason,
                    }
                )
                if readback is None
                else readback.observation_digest
            )
            waiting = AuthoritativeEffectReadback(
                attempt_id=claim.attempt_id,
                disposition=EffectDisposition.OUTCOME_UNKNOWN,
                observation_digest=observation_digest,
                reason=reason,
            )
            return ReconciliationHandlerOutcome(
                result=ReconciliationResult(
                    state=ReconciliationState.WAITING,
                    attempt_id=claim.attempt_id,
                    disposition=EffectDisposition.OUTCOME_UNKNOWN,
                    readback=waiting,
                    wait_reason=reason,
                )
            )
        receipt_ref = f"receipt:sha256:{commit.receipt_digest}"

        readback = AuthoritativeEffectReadback(
            attempt_id=claim.attempt_id,
            disposition=EffectDisposition.SUCCEEDED,
            provider_locator=commit.canonical_ref,
            receipt_digest=commit.receipt_digest,
            observation_digest=canonical_digest(
                {
                    "schema_version": "mrw.verify-admit-recovery-readback.v1",
                    "assignment_digest": assignment.assignment_digest,
                    "attempt_id": claim.attempt_id,
                    "artifact_id": staged.artifact_id,
                    "canonical_commit": commit.model_dump(mode="json"),
                }
            ),
        )
        return ReconciliationHandlerOutcome(
            result=ReconciliationResult(
                state=ReconciliationState.RESOLVED,
                attempt_id=claim.attempt_id,
                disposition=EffectDisposition.SUCCEEDED,
                readback=readback,
            ),
            output_digest=staged.content_digest,
            receipt_ref=receipt_ref,
        )

    def _commit_packet(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        staged: ExactFirstSpecimenStage,
        packet: ExactAdmissionPacket,
        waiting_as_result: bool = False,
    ) -> Any:
        admission_scope = RuntimeScope(
            project_scope=scope.project_scope,
            actor_id=packet.authorization.actor_id,
        )
        admission = self._admission_factory(
            connection,
            admission_scope,
            staged.tables,
        )
        prepared = admission.prepare(
            scope=admission_scope,
            assignment=staged.assignment,
            intent=packet.intent,
            candidate=packet.candidate,
            binding=packet.binding,
            current_authority_digest=packet.authorization.binding_digest,
            current_base_revision=packet.authorization.canonical_base_revision,
            current_incarnation=packet.authorization.canonical_incarnation,
            ordered_event_payloads=packet.ordered_event_payloads,
        )
        result = admission.commit_prepared(prepared)
        if result.progress is AdmissionProgress.WAITING_READBACK:
            if waiting_as_result:
                return result
            reason = None if result.readback is None else result.readback.reason
            raise FirstSpecimenTerminalError(
                "canonical readback is unavailable; terminal success is forbidden"
                + (f": {reason}" if reason else "")
            )
        commit = result.canonical_commit
        if commit is None:
            raise FirstSpecimenTerminalError(
                "canonical admission returned no exact commit readback"
            )
        finalized = admission.finalize(prepared, commit)
        if finalized.progress is not AdmissionProgress.FINALIZED:
            raise FirstSpecimenTerminalError("commit intent did not finalize exactly")
        return commit

    def after_terminal(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        claim: Any,
        lifecycle: ClaimedLifecycle,
        outcome: InterpreterOutcome,
        terminal: TerminalOutcome,
    ) -> None:
        del lifecycle, outcome
        if terminal.kind.value != "SUCCEEDED":
            return
        self._activate_and_complete(
            connection=connection,
            scope=scope,
            assignment=claim.assignment,
            authority_digest=terminal.authority_digest,
            observed_at=terminal.observed_at,
        )

    def after_reconciliation(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        claim: Any,
        outcome: ReconciliationHandlerOutcome,
        observed_at: datetime,
    ) -> None:
        if (
            outcome.result.state is not ReconciliationState.RESOLVED
            or outcome.result.disposition is not EffectDisposition.SUCCEEDED
        ):
            return
        if claim.assignment.step_role is not None and (
            claim.assignment.step_role.value == "ADMISSION"
        ):
            self._admit_reconciled_stage(
                connection=connection,
                scope=scope,
                assignment=claim.assignment,
                outcome=outcome,
            )
        self._activate_and_complete(
            connection=connection,
            scope=scope,
            assignment=claim.assignment,
            authority_digest=claim.claim_binding.authorization_digest,
            observed_at=observed_at,
        )

    @staticmethod
    def _admit_reconciled_stage(
        *,
        connection: Connection,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        outcome: ReconciliationHandlerOutcome,
    ) -> None:
        if assignment.plan_digest is None or outcome.receipt_ref is None:
            raise FirstSpecimenTerminalError(
                "reconciled admission lacks Plan identity or canonical receipt"
            )
        tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
        plan = PlanRepository(connection, tables).get(scope, assignment.plan_digest)
        admission_steps = tuple(
            step
            for step in plan.ordered_steps
            if step.step_id == assignment.step_id and step.admission is not None
        )
        if len(admission_steps) != 1:
            raise FirstSpecimenTerminalError(
                "reconciled admission step is absent from exact Plan"
            )
        effect_step_id = admission_steps[0].admission.effect_step_id
        rows = tuple(
            connection.execute(
                select(PUBLIC_TABLES["runtime_staged_artifacts"])
                .where(
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.project_key
                    == assignment.project_key,
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.run_id
                    == assignment.run_id,
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.step_id
                    == effect_step_id,
                )
                .with_for_update()
            ).mappings()
        )
        if len(rows) != 1:
            raise FirstSpecimenTerminalError(
                "reconciled admission lacks one exact staged candidate"
            )
        stage = rows[0]
        if stage["state"] == "VERIFIED":
            StagedArtifactRepository(connection, scope).transition(
                str(stage["artifact_id"]),
                expected_revision=int(stage["revision"]),
                expected_state="VERIFIED",
                target_state="ADMITTED",
                receipt_ref=outcome.receipt_ref,
            )
            return
        if stage["state"] != "ADMITTED" or stage["receipt_ref"] != outcome.receipt_ref:
            raise FirstSpecimenTerminalError(
                "reconciled admission staged candidate binding drift"
            )

    def _activate_and_complete(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        authority_digest: str,
        observed_at: datetime | None,
    ) -> None:
        observed = observed_at or datetime.now().astimezone()
        self._activation.activate_after_terminal(
            connection=connection,
            scope=scope,
            run_id=assignment.run_id,
            observed_at=observed,
        )
        if assignment.plan_digest is None:
            raise FirstSpecimenTerminalError(
                "terminal completion requires exact Plan identity"
            )
        tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
        plan = self._plan_repository_factory(connection, tables).get(
            scope, assignment.plan_digest
        )
        required_step_ids = frozenset(
            step.step_id
            for step in plan.ordered_steps
            if step.step_kind in {"EFFECT", "ADMISSION"}
        )
        RuntimeLifecycleRepository(connection, scope).complete_if_satisfied(
            assignment.run_id,
            required_step_ids=required_step_ids,
            authority_digest=authority_digest,
            observed_at=observed,
        )

    def _packet(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        staged: ExactFirstSpecimenStage,
        claim: ClaimBinding,
        observed_at: datetime | None,
        require_current_base: bool = True,
        event_cutoff_attempt_id: str | None = None,
    ) -> ExactAdmissionPacket:
        assignment = staged.assignment
        stored = _load_exact_authorization(connection, assignment)
        authority_scope = RuntimeScope(
            project_scope=scope.project_scope,
            actor_id=stored.actor_id,
        )
        current = self._authority_factory(
            connection,
            authority_scope,
        ).current_step_binding(
            assignment.run_id,
            assignment.step_id or "",
            now=observed_at,
        )
        require_current_authority(stored, current, now=observed_at)
        if current.binding_digest != claim.authorization_digest:
            raise FirstSpecimenTerminalError(
                "claim authorization differs from current exact step binding"
            )
        candidate = self._decoder.decode_exact(connection, staged, current)
        object_id, owner = _candidate_identity(candidate)
        if require_current_base:
            _require_current_base(
                connection,
                staged,
                object_id=object_id,
                base_revision=current.canonical_base_revision,
                incarnation=current.canonical_incarnation,
            )
        events = _ordered_runtime_event_payloads(
            connection,
            assignment,
            cutoff_before_terminal_attempt_id=event_cutoff_attempt_id,
        )
        operation = assignment.operation_contract_ref
        assert operation is not None
        plan = staged.plan
        evidence = canonical_digest(
            {
                "staged_artifact": _bounded_stage_payload(staged.staged_row),
                "runtime_value": _bounded_value_payload(staged.runtime_value_row),
                "effect_step": _bounded_step_payload(staged.effect_step_row),
                "effect_attempt": _bounded_attempt_payload(staged.effect_attempt_row),
            }
        )
        verification_receipt = canonical_digest(
            {
                "schema_version": "mrw.first-specimen.verification-receipt.v1",
                "assignment_digest": assignment.assignment_digest,
                "attempt_id": claim.attempt_id,
                "artifact_id": staged.artifact_id,
                "content_digest": staged.content_digest,
                "authorization_digest": current.binding_digest,
                "ordered_event_count": len(events),
            }
        )
        binding = VerificationBinding.from_content(
            program_digest=assignment.program_digest,
            plan_digest=assignment.plan_digest,
            step_id=assignment.step_id,
            attempt_id=claim.attempt_id,
            input_closure_digest=assignment.input_closure_digest,
            output_content_digest=staged.content_digest,
            ordered_event_payloads=events,
            schema_digest=canonical_digest(
                {
                    "object_type": staged.object_type,
                    "codec_id": staged.runtime_value_row["codec_id"],
                    "operation_contract_digest": operation.contract_digest,
                }
            ),
            compiler_identity=f"{plan.compiler_id}@{plan.compiler_version}",
            interpreter_identity=(
                f"handler-binding:sha256:{assignment.handler_binding_digest}"
            ),
            verifier_identity="successor-native.verify-admit@1.0.0",
            actor_id=current.actor_id,
            project_key=assignment.project_key,
            authority_digest=current.binding_digest,
            project_registry_revision=scope.project_scope.project_registry_revision,
            project_scope_digest=scope.project_scope.scope_digest,
            resolved_schema=scope.project_scope.resolved_schema,
            canonical_owner=owner,
            canonical_object_id=object_id,
            canonical_base_revision=current.canonical_base_revision,
            canonical_incarnation=current.canonical_incarnation,
            evidence_digest=evidence,
            receipt_digest=verification_receipt,
            provenance_digest=staged.provenance_digest,
            declared_loss_profile_ref=staged.staged_row["loss_profile_ref"],
            qualifier=str(staged.staged_row["qualifier_ref"]),
        )
        intent_id = "commit:" + canonical_digest(
            {
                "assignment_digest": assignment.assignment_digest,
                "artifact_id": staged.artifact_id,
                "verification_binding_digest": binding.binding_digest,
                "canonical_object_id": object_id,
            }
        )
        intent = CommitIntent(
            commit_intent_id=intent_id,
            canonical_owner=owner,
            project_key=assignment.project_key,
            object_id=object_id,
            project_registry_revision=scope.project_scope.project_registry_revision,
            project_scope_digest=scope.project_scope.scope_digest,
            expected_base_revision=current.canonical_base_revision,
            expected_incarnation=current.canonical_incarnation,
            content_digest=staged.content_digest,
            ordered_event_closure_digest=(binding.ordered_event_payload_closure_digest),
            verification_binding_digest=binding.binding_digest,
            authority_digest=current.binding_digest,
            idempotency_key="admit:"
            + canonical_digest(
                {
                    "project_key": assignment.project_key,
                    "object_id": object_id,
                    "incarnation": current.canonical_incarnation,
                    "content_digest": staged.content_digest,
                }
            ),
        )
        return ExactAdmissionPacket(candidate, intent, binding, events, current)

    def _default_admission(
        self, connection: Connection, scope: RuntimeScope, tables: ProjectTables
    ) -> AdmissionCoordinator:
        return AdmissionCoordinator(
            registry=build_first_specimen_admission_registry(
                connection=connection,
                tables=tables,
                bundle=self._bundle,
            ),
            commit_intents=PostgresCommitIntentAdapter(
                CommitIntentRepository(connection, scope)
            ),
            commit_binding_factory=commit_binding_from_assignment,
        )


def _resolve_scope(
    connection: Connection,
    assignment: RuntimeAssignment,
    *,
    actor_id: str,
) -> RuntimeScope:
    run = _one_public(
        connection,
        "runtime_runs",
        project_key=assignment.project_key,
        run_id=assignment.run_id,
    )
    resolver = ServerProjectScopeResolver(connection=connection)
    resolved = resolver.resolve_expected(
        assignment.project_key,
        int(run["project_registry_revision"]),
        str(run["project_scope_digest"]),
    )
    if (
        isinstance(resolved, ProjectScopeStale)
        or resolver.resolve(assignment.project_key) != resolved
    ):
        raise FirstSpecimenTerminalError("VERIFY_ADMIT project scope is stale")
    if resolved.resolved_schema != run["resolved_schema"]:
        raise FirstSpecimenTerminalError("VERIFY_ADMIT resolved schema drift")
    return RuntimeScope(project_scope=resolved, actor_id=actor_id)


def _load_effect_stage(
    connection: Connection,
    scope: RuntimeScope,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
    *,
    expected_state: str,
) -> ExactFirstSpecimenStage:
    if assignment.step_id is None:
        raise FirstSpecimenTerminalError("INTERPRET terminal lacks step identity")
    rows = tuple(
        connection.execute(
            select(PUBLIC_TABLES["runtime_staged_artifacts"])
            .where(
                PUBLIC_TABLES["runtime_staged_artifacts"].c.project_key
                == assignment.project_key,
                PUBLIC_TABLES["runtime_staged_artifacts"].c.run_id == assignment.run_id,
                PUBLIC_TABLES["runtime_staged_artifacts"].c.step_id
                == assignment.step_id,
                PUBLIC_TABLES["runtime_staged_artifacts"].c.attempt_id
                == claim.attempt_id,
            )
            .with_for_update(read=True)
        ).mappings()
    )
    if len(rows) != 1 or rows[0]["state"] != expected_state:
        raise FirstSpecimenTerminalError(
            "INTERPRET success lacks one exact STAGED result"
        )
    staged_row = rows[0]
    runtime_value = _one_public(
        connection,
        "runtime_values",
        project_key=assignment.project_key,
        value_id=staged_row["value_id"],
    )
    project_ref = runtime_value["project_value_ref"]
    if not isinstance(project_ref, str) or not project_ref.startswith("project-value:"):
        raise FirstSpecimenTerminalError("staged INTERPRET value is not project-owned")
    tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
    project_value = one_mapping(
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key == assignment.project_key,
                tables.successor_values.c.value_id
                == project_ref.removeprefix("project-value:"),
            )
        )
    )
    if project_value is None:
        raise RecordNotFound("staged INTERPRET project value is absent")
    exact = PostgresFirstSpecimenStageReader._exact_bytes(project_value)
    effect_step = _one_public(
        connection,
        "runtime_steps",
        project_key=assignment.project_key,
        run_id=assignment.run_id,
        step_id=assignment.step_id,
    )
    effect_attempt = _one_public(
        connection,
        "runtime_effect_attempts",
        project_key=assignment.project_key,
        attempt_id=claim.attempt_id,
    )
    run = _one_public(
        connection,
        "runtime_runs",
        project_key=assignment.project_key,
        run_id=assignment.run_id,
    )
    plan = PlanRepository(connection, tables).get(scope, str(run["plan_digest"]))
    if (
        runtime_value["content_digest"] != project_value["content_digest"]
        or hashlib.sha256(exact).hexdigest() != runtime_value["content_digest"]
    ):
        raise FirstSpecimenTerminalError("staged INTERPRET value digest drift")
    return ExactFirstSpecimenStage(
        scope,
        tables,
        plan,
        assignment,
        staged_row,
        runtime_value,
        project_value,
        effect_step,
        effect_attempt,
        exact,
    )


def _load_exact_authorization(
    connection: Connection, assignment: RuntimeAssignment
) -> StepAuthorizationBinding:
    table = PUBLIC_TABLES["runtime_step_authorizations"]
    rows = tuple(
        connection.execute(
            select(table).where(
                table.c.project_key == assignment.project_key,
                table.c.run_id == assignment.run_id,
                table.c.step_id == assignment.step_id,
                table.c.claim_authority_epoch == assignment.claim_authority_epoch,
            )
        ).mappings()
    )
    if len(rows) != 1:
        raise FirstSpecimenTerminalError(
            "VERIFY_ADMIT lacks one exact persisted step authorization"
        )
    binding = validate_authorization_row(rows[0])
    expected = {
        "operation_kind": assignment.operation_contract_ref.kind,
        "operation_contract_digest": assignment.operation_contract_digest,
        "capability_id": assignment.capability_id,
        "claim_policy_digest": assignment.claim_policy_digest,
        "payload_digest": assignment.payload_digest,
        "project_key": assignment.project_key,
        "interpreter_binding_digest": assignment.handler_binding_digest,
        "deployment_catalog_digest": assignment.deployment_catalog_digest,
        "resource_policy_epoch": assignment.resource_policy_epoch,
        "queue_eligibility_digest": assignment.queue_eligibility_digest,
    }
    drift = tuple(
        name for name, value in expected.items() if getattr(binding, name) != value
    )
    if drift:
        raise FirstSpecimenTerminalError(
            "assignment/authorization drift: " + ", ".join(drift)
        )
    return binding


def _ordered_runtime_event_payloads(
    connection: Connection,
    assignment: RuntimeAssignment,
    *,
    cutoff_before_terminal_attempt_id: str | None = None,
) -> tuple[object, ...]:
    table = PUBLIC_TABLES["runtime_events"]
    rows = tuple(
        connection.execute(
            select(table)
            .where(
                table.c.project_key == assignment.project_key,
                table.c.run_id == assignment.run_id,
            )
            .order_by(table.c.seq)
            .with_for_update(read=True)
        ).mappings()
    )
    if not rows or tuple(int(row["seq"]) for row in rows) != tuple(
        range(1, len(rows) + 1)
    ):
        raise FirstSpecimenTerminalError(
            "runtime event stream is empty or non-contiguous"
        )
    if cutoff_before_terminal_attempt_id is not None:
        terminal_rows = tuple(
            row
            for row in rows
            if row["attempt_id"] == cutoff_before_terminal_attempt_id
            and row["event_type"]
            in {
                "EffectReceiptLost",
                "CommitOrDeliveryOutcomeUnknown",
            }
        )
        if len(terminal_rows) != 1:
            raise FirstSpecimenTerminalError(
                "recovery event prefix lacks one exact original unknown boundary"
            )
        cutoff_seq = int(terminal_rows[0]["seq"])
        rows = tuple(row for row in rows if int(row["seq"]) < cutoff_seq)
        if not rows:
            raise FirstSpecimenTerminalError(
                "recovery event prefix is empty before original unknown boundary"
            )
    return tuple(
        {
            "seq": int(row["seq"]),
            "event_type": row["event_type"],
            "schema_version": row["schema_version"],
            "step_id": row["step_id"],
            "attempt_id": row["attempt_id"],
            "event_metadata": dict(row["event_metadata_json"]),
            "payload_ref": row["payload_ref"],
            "payload_digest": row["payload_digest"],
            "authority_digest": row["authority_digest"],
        }
        for row in rows
    )


def _require_current_base(
    connection: Connection,
    staged: ExactFirstSpecimenStage,
    *,
    object_id: str,
    base_revision: int,
    incarnation: str,
) -> None:
    table = (
        staged.tables.research_relations
        if staged.object_type == EVIDENCE_QUALIFICATION_TYPE.type_id
        else staged.tables.research_objects
    )
    id_column = (
        table.c.relation_id
        if staged.object_type == EVIDENCE_QUALIFICATION_TYPE.type_id
        else table.c.object_id
    )
    rows = tuple(
        connection.execute(
            select(table)
            .where(
                table.c.project_key == staged.assignment.project_key,
                id_column == object_id,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
            .with_for_update()
        ).mappings()
    )
    if base_revision == 0:
        if rows:
            raise FirstSpecimenTerminalError(
                "canonical base expected absence but exists"
            )
        return
    if (
        len(rows) != 1
        or int(rows[0]["revision"]) != base_revision
        or rows[0]["incarnation"] != incarnation
    ):
        raise FirstSpecimenTerminalError("canonical base revision/incarnation drift")


def _load_current_object(
    connection: Connection, staged: ExactFirstSpecimenStage, object_id: str
) -> ResearchObjectRef:
    table = staged.tables.research_objects
    row = one_mapping(
        connection.execute(
            select(table)
            .where(
                table.c.project_key == staged.assignment.project_key,
                table.c.object_id == object_id,
                table.c.lifecycle_state.in_(("DRAFT", "ADMITTED")),
            )
            .order_by(table.c.revision.desc())
            .limit(1)
            .with_for_update(read=True)
        )
    )
    if row is None:
        raise FirstSpecimenCandidateDecodeError(
            f"canonical relation endpoint is absent: {object_id}"
        )
    object_type = OBJECT_TYPE_BY_ID.get(str(row["object_type"]))
    if object_type is None:
        raise FirstSpecimenCandidateDecodeError(
            f"unknown relation endpoint object type: {row['object_type']}"
        )
    return ResearchObjectRef(
        object_id=str(row["object_id"]),
        object_type=object_type,
        project_key=str(row["project_key"]),
        revision=int(row["revision"]),
        incarnation=str(row["incarnation"]),
        owner_binding_ref=str(row["owner_binding_ref"]),
        content_ref=str(row["content_ref"]),
        content_digest=str(row["content_digest"]),
        provenance_closure_digest=str(row["provenance_closure_digest"]),
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        lifecycle_state=str(row["lifecycle_state"]),
    )


def _load_delivery_artifact(
    connection: Connection,
    staged: ExactFirstSpecimenStage,
    receipt: DeliveryReceiptRef,
) -> ResearchObjectRef:
    intent = _load_current_object(connection, staged, receipt.delivery_intent_ref)
    project_ref = intent.content_ref
    if not project_ref.startswith("project-value:"):
        raise FirstSpecimenCandidateDecodeError(
            "DeliveryIntent content ref is not project-owned"
        )
    row = one_mapping(
        connection.execute(
            select(staged.tables.successor_values).where(
                staged.tables.successor_values.c.project_key
                == staged.assignment.project_key,
                staged.tables.successor_values.c.value_id
                == project_ref.removeprefix("project-value:"),
                staged.tables.successor_values.c.content_digest
                == intent.content_digest,
            )
        )
    )
    if row is None:
        raise FirstSpecimenCandidateDecodeError("DeliveryIntent exact bytes are absent")
    exact = PostgresFirstSpecimenStageReader._exact_bytes(row)
    try:
        artifact_locator = json.loads(exact)["artifact_ref"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise FirstSpecimenCandidateDecodeError(
            "DeliveryIntent artifact binding is malformed"
        ) from exc
    match = re.fullmatch(r"(.+)@(\d+):sha256:([0-9a-f]{64})", artifact_locator)
    if match is None:
        raise FirstSpecimenCandidateDecodeError(
            "DeliveryIntent artifact_ref is not an exact revision/digest locator"
        )
    artifact = _load_current_object(connection, staged, match.group(1))
    if artifact.revision != int(
        match.group(2)
    ) or artifact.content_digest != match.group(3):
        raise FirstSpecimenCandidateDecodeError(
            "DeliveryIntent canonical artifact drift"
        )
    return artifact


def _decode_qualification(
    raw: Mapping[str, Any], expected_digest: str
) -> EvidenceQualification:
    try:
        validity = raw["validity"]
        value = EvidenceQualification(
            qualification_id=raw["qualification_id"],
            project_key=raw["project_key"],
            material_ref=raw["material_ref"],
            inquiry_ref=raw["inquiry_ref"],
            claim_ref=raw["claim_ref"],
            direction=raw["direction"],
            scope_statement_ref=raw["scope_statement_ref"],
            uncertainty_profile_ref=raw["uncertainty_profile_ref"],
            verifier_profile_ref=raw["verifier_profile_ref"],
            provenance_closure_digest=raw["provenance_closure_digest"],
            validity=Validity(
                _optional_datetime(validity["valid_from"]),
                _optional_datetime(validity["valid_to"]),
            ),
            source_time=_optional_datetime(raw["source_time"]),
            observed_at=_optional_datetime(raw["observed_at"]),
            revision=raw["revision"],
            incarnation=raw["incarnation"],
            state=raw["state"],
            qualification_digest=expected_digest,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FirstSpecimenCandidateDecodeError(
            "EvidenceQualification staged bytes are malformed"
        ) from exc
    return value


def _decode_object_payload(kind: str, raw: Mapping[str, Any], digest: str) -> object:
    try:
        if kind == CLAIM_TYPE.type_id:
            return Claim(
                claim_id=raw["claim_id"],
                statement_ref=raw["statement_ref"],
                support_relation_refs=tuple(raw["support_relation_refs"]),
                contradiction_relation_refs=tuple(raw["contradiction_relation_refs"]),
                uncertainty_profile_ref=raw["uncertainty_profile_ref"],
                lifecycle_state=raw["lifecycle_state"],
                scope=dict(raw["scope"]),
                content_digest=digest,
            )
        if kind == GAP_TYPE.type_id:
            return Gap(
                gap_id=raw["gap_id"],
                inquiry_ref=raw["inquiry_ref"],
                requirement=raw["requirement"],
                reason=raw["reason"],
                closure_condition=raw["closure_condition"],
                reopen_policy=dict(raw["reopen_policy"]),
                missing_evidence_or_decision=raw["missing_evidence_or_decision"],
                content_digest=digest,
            )
        return ResearchArtifact(
            artifact_id=raw["artifact_id"],
            content_ref=raw["content_ref"],
            content_digest=digest,
            claim_closure=tuple(raw["claim_closure"]),
            evidence_relation_closure=tuple(raw["evidence_relation_closure"]),
            citation_closure=tuple(raw["citation_closure"]),
            format=raw["format"],
            revision=raw["revision"],
            lifecycle_state=raw["lifecycle_state"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FirstSpecimenCandidateDecodeError(
            f"{kind} staged bytes are malformed"
        ) from exc


def _decode_delivery_receipt(raw: Mapping[str, Any], digest: str) -> DeliveryReceiptRef:
    try:
        return DeliveryReceiptRef(
            receipt_ref=raw["receipt_ref"],
            delivery_intent_ref=raw["delivery_intent_ref"],
            attempt_ref=raw["attempt_ref"],
            provider_locator=raw["provider_locator"],
            receipt_digest=raw["receipt_digest"],
            outcome_time=_required_datetime(raw["outcome_time"]),
            content_digest=digest,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FirstSpecimenCandidateDecodeError(
            "DeliveryReceiptRef staged bytes are malformed"
        ) from exc


def _payload_object_id(payload: object) -> str:
    if isinstance(payload, Claim):
        return payload.claim_id
    if isinstance(payload, Gap):
        return payload.gap_id
    if isinstance(payload, ResearchArtifact):
        return payload.artifact_id
    raise TypeError("unsupported research object candidate")


def _candidate_identity(candidate: object) -> tuple[str, str]:
    if isinstance(candidate, EvidenceRelationCandidate):
        return candidate.qualification.qualification_id, "ResearchLedger"
    if isinstance(candidate, ResearchObjectCandidate):
        owner = (
            "ResearchLedger_plus_project_artifact_store"
            if isinstance(candidate.payload, ResearchArtifact)
            else "ResearchLedger"
        )
        return candidate.ref.object_id, owner
    if isinstance(candidate, DeliveryReceiptCandidate):
        return candidate.ref.object_id, "project_receipt_store"
    raise FirstSpecimenCandidateDecodeError("unknown admission candidate kind")


def _one_public(
    connection: Connection, table_name: str, **identity: object
) -> Mapping[str, Any]:
    table = PUBLIC_TABLES[table_name]
    statement = select(table)
    for name, value in identity.items():
        statement = statement.where(getattr(table.c, name) == value)
    row = one_mapping(connection.execute(statement.with_for_update(read=True)))
    if row is None:
        raise RecordNotFound(f"public {table_name} exact row is absent")
    return row


def _bounded_stage_payload(row: Mapping[str, Any]) -> dict[str, object]:
    return {
        name: row[name]
        for name in (
            "artifact_id",
            "run_id",
            "step_id",
            "attempt_id",
            "value_id",
            "receipt_ref",
            "qualifier_ref",
            "loss_profile_ref",
            "state",
            "revision",
        )
    }


def _bounded_value_payload(row: Mapping[str, Any]) -> dict[str, object]:
    return {
        name: row[name]
        for name in (
            "value_id",
            "object_type",
            "codec_id",
            "content_digest",
            "byte_size",
            "project_value_ref",
            "storage_digest",
            "state",
            "revision",
        )
    }


def _bounded_step_payload(row: Mapping[str, Any]) -> dict[str, object]:
    return {
        name: row[name]
        for name in (
            "run_id",
            "step_id",
            "operation_kind",
            "state",
            "revision",
            "execution_epoch",
            "output_digest",
        )
    }


def _bounded_attempt_payload(row: Mapping[str, Any]) -> dict[str, object]:
    return {
        name: row[name]
        for name in (
            "attempt_id",
            "run_id",
            "step_id",
            "assignment_digest",
            "handler_binding_digest",
            "authorization_digest",
            "disposition",
            "receipt_ref",
            "receipt_digest",
            "revision",
        )
    }


def _required_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("datetime must be an ISO string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return parsed


def _optional_datetime(value: object) -> datetime | None:
    return None if value is None else _required_datetime(value)


__all__ = [
    "DeliveryReceiptContentPort",
    "ExactAdmissionPacket",
    "ExactFirstSpecimenStage",
    "FirstSpecimenActivationPort",
    "FirstSpecimenCandidateDecodeError",
    "FirstSpecimenCandidateDecoder",
    "FirstSpecimenTerminalError",
    "FirstSpecimenTerminalLifecycleGap",
    "PostgresFirstSpecimenStageReader",
    "PostgresFirstSpecimenTerminalHook",
    "PostgresVerifyAdmitHandler",
]
