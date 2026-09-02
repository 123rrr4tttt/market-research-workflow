"""Exact PostgreSQL RuntimeHandler for the first-specimen internal delivery.

This module is the production effect boundary for ``delivery.internal_export.v1``.
It replays every authoritative input on a fresh caller-owned UoW before the
filesystem effect, then publishes only a non-canonical receipt candidate.  It
never admits the receipt to the Research Ledger and has no network/provider
dependency.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol, Self

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.first_specimen import (
    InternalExportInput,
    build_first_specimen_bundle,
)
from app.successor_runtime.language.object_contracts import (
    build_first_specimen_return_contract_registry,
)
from app.successor_runtime.language.program import (
    Atom,
    Decide,
    MapOutput,
    ProgramNode,
    Then,
    TraverseOrdered,
    ZipOrdered,
)
from app.successor_runtime.research.artifacts import (
    DeliveryIntent,
    DeliveryReceiptRef,
    ResearchArtifact,
    artifact_exact_ref,
)
from app.successor_runtime.research.codec import (
    canonical_bytes,
    dataclass_to_json,
    sha256_hex,
)
from app.successor_runtime.research.object_types import (
    CANONICAL_CODEC_ID,
    DELIVERY_INTENT_TYPE,
    DELIVERY_RECEIPT_REF_TYPE,
    RESEARCH_ARTIFACT_TYPE,
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
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportBindingConflict,
    InternalExportError,
    InternalExportExecutionContext,
    InternalExportInterpreter,
    InternalExportOutcome,
    InternalExportReadbackUnavailable,
    InternalExportRequest,
)

from .approvals import ApprovalRepository
from .authority_provider import PostgresAuthorityProvider
from .models import PUBLIC_TABLES, ProjectTables, project_tables
from .plans import PlanRepository
from .programs import ProgramRepository
from .research_ledger import one_mapping
from .runtime_journal import ExactBindingConflict
from .runtime_values import RuntimeValueBinding, RuntimeValueRepository
from .session import ProjectScopeStale, ServerProjectScopeResolver
from .staged_artifacts import StagedArtifactBinding, StagedArtifactRepository
from .values import ValueRepository

DELIVERY_OPERATION = "delivery.internal_export.v1"
_ARTIFACT_REF = re.compile(
    r"^(?P<artifact_id>.+)@(?P<revision>[1-9][0-9]*):sha256:"
    r"(?P<digest>[0-9a-f]{64})$"
)


class DeliveryHandlerError(RuntimeError):
    """The exact delivery effect cannot safely execute or be adopted."""


class DeliveryReplayDrift(DeliveryHandlerError):
    """Persisted Program/Plan/value/authority/claim closure drifted."""


class DeliveryOutputDrift(DeliveryHandlerError):
    """A receipt candidate identity was reused for different exact content."""


@dataclass(frozen=True, slots=True)
class InstalledFirstSpecimenDeliveryHandler:
    handler_binding_digest: str
    interpreter_profile_digest: str
    operation_contract_digest: str
    payload_codec_id: str
    payload_codec_digest: str
    admission_required: bool
    operation_kind: str = DELIVERY_OPERATION

    def __post_init__(self) -> None:
        for name in (
            "handler_binding_digest",
            "interpreter_profile_digest",
            "operation_contract_digest",
            "payload_codec_digest",
        ):
            require_digest(getattr(self, name), name)
        operation = build_first_specimen_bundle().operation_by_kind(
            DELIVERY_OPERATION
        )
        codec = build_first_specimen_bundle().codec_by_kind(DELIVERY_OPERATION)
        returns = build_first_specimen_return_contract_registry().resolve_required(
            operation.return_contract_ref
        )
        if self.operation_contract_digest != operation.ref.contract_digest:
            raise ValueError("installed delivery operation contract digest drift")
        if self.payload_codec_id != codec.codec_id:
            raise ValueError("installed delivery payload codec id drift")
        if self.payload_codec_digest != codec.codec_digest:
            raise ValueError("installed delivery payload codec digest drift")
        if self.admission_required != returns.admission_required:
            raise ValueError("installed delivery return admission requirement drift")

    @classmethod
    def bind(
        cls,
        *,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
    ) -> InstalledFirstSpecimenDeliveryHandler:
        bundle = build_first_specimen_bundle()
        operation = bundle.operation_by_kind(DELIVERY_OPERATION)
        codec = bundle.codec_by_kind(DELIVERY_OPERATION)
        returns = build_first_specimen_return_contract_registry().resolve_required(
            operation.return_contract_ref
        )
        return cls(
            handler_binding_digest=handler_binding_digest,
            interpreter_profile_digest=interpreter_profile_digest,
            operation_contract_digest=operation.ref.contract_digest,
            payload_codec_id=codec.codec_id,
            payload_codec_digest=codec.codec_digest,
            admission_required=returns.admission_required,
        )


@dataclass(frozen=True, slots=True)
class FirstSpecimenDeliveryReplay:
    scope: RuntimeScope
    tables: ProjectTables
    payload: InternalExportInput
    delivery_intent: DeliveryIntent
    artifact: ResearchArtifact
    artifact_bytes: bytes
    request: InternalExportRequest
    approvals: ApprovalRepository


class DeliveryHandlerUnitOfWork(Protocol):
    connection: Connection

    def __enter__(self) -> Self: ...

    def commit(self) -> None: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class DeliveryHandlerUnitOfWorkFactory(Protocol):
    def __call__(self) -> DeliveryHandlerUnitOfWork: ...


class DeliveryReplayPort(Protocol):
    def load_exact(
        self,
        connection: Connection,
        installation: InstalledFirstSpecimenDeliveryHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> FirstSpecimenDeliveryReplay: ...


class DeliveryEffectPort(Protocol):
    def execute_exact(
        self,
        installation: InstalledFirstSpecimenDeliveryHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome: ...


def _atoms(node: ProgramNode) -> tuple[Atom, ...]:
    if isinstance(node, Atom):
        return (node,)
    if isinstance(node, Then):
        return _atoms(node.first) + _atoms(node.second)
    if isinstance(node, MapOutput):
        return _atoms(node.source)
    if isinstance(node, ZipOrdered):
        return _atoms(node.left) + _atoms(node.right)
    if isinstance(node, TraverseOrdered):
        return _atoms(node.element_program)
    if isinstance(node, Decide):
        return tuple(
            atom for branch in node.branches for atom in _atoms(branch.program)
        )
    return ()


def _value_id(locator: str) -> str:
    prefix = "project-value:"
    if not locator.startswith(prefix) or locator == prefix:
        raise DeliveryReplayDrift("delivery value is not a project successor value")
    return locator.removeprefix(prefix)


def _exact_project_value(
    connection: Connection,
    tables: ProjectTables,
    *,
    project_key: str,
    locator: str,
    expected_digest: str | None = None,
) -> tuple[bytes, dict[str, Any], Any]:
    value_id = _value_id(locator)
    row = one_mapping(
        connection.execute(
            select(tables.successor_values).where(
                tables.successor_values.c.project_key == project_key,
                tables.successor_values.c.value_id == value_id,
                tables.successor_values.c.state == "AVAILABLE",
            )
        )
    )
    if row is None or row["content_bytes"] is None or row["content_json"] is not None:
        raise DeliveryReplayDrift(f"exact delivery value is absent: {value_id}")
    exact = bytes(row["content_bytes"])
    actual = hashlib.sha256(exact).hexdigest()
    if actual != row["content_digest"] or (
        expected_digest is not None and actual != expected_digest
    ):
        raise DeliveryReplayDrift(f"delivery value content digest drift: {value_id}")
    if len(exact) != row["byte_size"]:
        raise DeliveryReplayDrift(f"delivery value byte size drift: {value_id}")
    provenance = dict(row["provenance_json"])
    if sha256_hex(provenance) != row["provenance_digest"]:
        raise DeliveryReplayDrift(f"delivery value provenance digest drift: {value_id}")
    return exact, provenance, row


def _decode_payload(
    installation: InstalledFirstSpecimenDeliveryHandler,
    exact: bytes,
    provenance: dict[str, Any],
) -> InternalExportInput:
    codec = build_first_specimen_bundle().codec_by_kind(DELIVERY_OPERATION)
    if (
        provenance.get("operation_kind") != DELIVERY_OPERATION
        or provenance.get("codec_id") != installation.payload_codec_id
        or provenance.get("codec_digest") != installation.payload_codec_digest
    ):
        raise DeliveryReplayDrift("typed internal-export payload binding drift")
    try:
        raw = json.loads(exact)
        if not isinstance(raw, dict):
            raise TypeError("payload root is not an object")
        payload = codec.decode_payload(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DeliveryReplayDrift("typed internal-export payload is malformed") from exc
    if not isinstance(payload, InternalExportInput):
        raise DeliveryReplayDrift("delivery payload decoded to the wrong type")
    if canonical_bytes(codec.encode_payload(payload)) != exact:
        raise DeliveryReplayDrift("typed internal-export payload round-trip drift")
    return payload


def _decode_intent(exact: bytes) -> DeliveryIntent:
    try:
        raw = json.loads(exact)
        intent = DeliveryIntent(
            delivery_intent_id=raw["delivery_intent_id"],
            artifact_ref=raw["artifact_ref"],
            audience=raw["audience"],
            channel=raw["channel"],
            format=raw["format"],
            approval_refs=tuple(raw["approval_refs"]),
            authority_digest=raw["authority_digest"],
            idempotency_key=raw["idempotency_key"],
            irreversibility_profile=raw["irreversibility_profile"],
            content_digest=raw["content_digest"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DeliveryReplayDrift("stored DeliveryIntent is malformed") from exc
    if canonical_bytes(intent) != exact:
        raise DeliveryReplayDrift("stored DeliveryIntent bytes are not canonical")
    return intent


def _decode_artifact(exact: bytes) -> ResearchArtifact:
    try:
        raw = json.loads(exact)
        digest = hashlib.sha256(exact).hexdigest()
        artifact = ResearchArtifact(
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
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DeliveryReplayDrift("stored ResearchArtifact is malformed") from exc
    expected = canonical_bytes(dataclass_to_json(artifact, ("content_digest",)))
    if expected != exact:
        raise DeliveryReplayDrift("stored ResearchArtifact bytes are not canonical")
    return artifact


class PostgresFirstSpecimenDeliveryReplay:
    """Re-open the exact delivery closure on the effect UoW."""

    def load_exact(
        self,
        connection: Connection,
        installation: InstalledFirstSpecimenDeliveryHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> FirstSpecimenDeliveryReplay:
        _require_exact_handler(installation, assignment, claim)
        runs = PUBLIC_TABLES["runtime_runs"]
        run = one_mapping(
            connection.execute(
                select(runs).where(
                    runs.c.project_key == assignment.project_key,
                    runs.c.run_id == assignment.run_id,
                )
            )
        )
        if run is None:
            raise DeliveryReplayDrift("delivery run is absent")
        if (
            run["program_digest"] != assignment.program_digest
            or run["plan_digest"] != assignment.plan_digest
            or run["incarnation"] != assignment.incarnation
        ):
            raise DeliveryReplayDrift("delivery run/program/plan identity drift")
        resolver = ServerProjectScopeResolver(connection=connection)
        resolved = resolver.resolve_expected(
            assignment.project_key,
            int(run["project_registry_revision"]),
            str(run["project_scope_digest"]),
        )
        if isinstance(resolved, ProjectScopeStale) or resolver.resolve(
            assignment.project_key
        ) != resolved:
            raise DeliveryReplayDrift("delivery project scope is stale")
        scope = RuntimeScope(
            project_scope=resolved,
            actor_id=context.node.node_id,
        )
        tables = project_tables(MetaData(), resolved.resolved_schema)

        self._require_persisted_claim(connection, assignment, claim)
        delivery_atom = self._require_program_plan(
            connection, scope, tables, installation, assignment
        )

        if assignment.payload_ref is None or assignment.payload_digest is None:
            raise DeliveryReplayDrift("delivery assignment lacks typed payload")
        payload_bytes, payload_provenance, payload_row = _exact_project_value(
            connection,
            tables,
            project_key=assignment.project_key,
            locator=assignment.payload_ref,
            expected_digest=assignment.payload_digest,
        )
        codec = build_first_specimen_bundle().codec_by_kind(DELIVERY_OPERATION)
        if (
            payload_row["object_type"] != codec.payload_type_id
            or payload_row["codec_id"] != codec.codec_id
        ):
            raise DeliveryReplayDrift("delivery payload type/codec drift")
        payload = _decode_payload(installation, payload_bytes, payload_provenance)

        if len(assignment.input_refs) != 2:
            raise DeliveryReplayDrift("delivery requires artifact and intent inputs")
        if canonical_digest(assignment.input_refs) != assignment.input_closure_digest:
            raise DeliveryReplayDrift("delivery ordered input closure drift")
        intent_bytes, _, intent_row = _exact_project_value(
            connection,
            tables,
            project_key=assignment.project_key,
            locator=assignment.input_refs[1],
        )
        if (
            intent_row["object_type"] != DELIVERY_INTENT_TYPE.type_id
            or intent_row["codec_id"] != DELIVERY_INTENT_TYPE.codec_id
        ):
            raise DeliveryReplayDrift("DeliveryIntent type/codec drift")
        intent = _decode_intent(intent_bytes)
        artifact, artifact_bytes, artifact_incarnation = self._load_current_artifact(
            connection,
            tables,
            assignment,
            payload,
            assignment.input_refs[0],
        )
        _require_semantic_closure(payload, intent, artifact, artifact_bytes)

        binding = assignment.handler_binding
        if getattr(binding, "authority_requirement_digest", None) != intent.authority_digest:
            raise DeliveryReplayDrift("delivery handler authority requirement drift")
        current = PostgresAuthorityProvider(connection, scope).current_step_binding(
            assignment.run_id,
            assignment.step_id or "",
            now=context.observed_at,
        )
        if (
            current.binding_digest != claim.authorization_digest
            or current.capability_id != assignment.capability_id
            or current.claim_authority_epoch != assignment.claim_authority_epoch
            or current.claim_policy_digest != assignment.claim_policy_digest
            or current.payload_digest
            != delivery_atom.operation.payload_ref.content_digest
            or current.interpreter_binding_digest != assignment.handler_binding_digest
            or tuple(current.approval_refs) != payload.approval_refs
            or current.canonical_base_revision != artifact.revision
            or current.canonical_incarnation != artifact_incarnation
        ):
            raise DeliveryReplayDrift("current delivery authority binding drift")

        approvals = ApprovalRepository(connection, scope)
        assert intent.content_digest is not None
        request = InternalExportRequest(
            project_key=assignment.project_key,
            project_scope_digest=resolved.scope_digest,
            run_id=assignment.run_id,
            step_id=assignment.step_id or "",
            attempt_id=claim.attempt_id,
            assignment_digest=assignment.assignment_digest,
            operation_contract_ref=assignment.operation_contract_ref,
            handler_binding_digest=assignment.handler_binding_digest,
            delivery_intent=intent,
            artifact_bytes=artifact_bytes,
            artifact_digest=hashlib.sha256(artifact_bytes).hexdigest(),
            # Human approval is intentionally bound to the finalized intent,
            # while assignment.payload_digest binds the typed runtime payload.
            payload_digest=intent.content_digest,
        )
        return FirstSpecimenDeliveryReplay(
            scope=scope,
            tables=tables,
            payload=payload,
            delivery_intent=intent,
            artifact=artifact,
            artifact_bytes=artifact_bytes,
            request=request,
            approvals=approvals,
        )

    @staticmethod
    def _require_persisted_claim(
        connection: Connection,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> Atom:
        work = one_mapping(
            connection.execute(
                select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.project_key
                    == assignment.project_key,
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                    == assignment.work_item_id,
                )
            )
        )
        attempt = one_mapping(
            connection.execute(
                select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                    == assignment.project_key,
                    PUBLIC_TABLES["runtime_effect_attempts"].c.attempt_id
                    == claim.attempt_id,
                )
            )
        )
        if work is None or attempt is None:
            raise DeliveryReplayDrift("persisted delivery assignment/attempt is absent")
        try:
            stored_assignment = RuntimeAssignment.model_validate(
                work["assignment_binding_json"]
            )
            stored_claim = ClaimBinding.model_validate(attempt["claim_binding_json"])
        except (TypeError, ValueError) as exc:
            raise DeliveryReplayDrift("persisted assignment/claim is malformed") from exc
        if (
            stored_assignment != assignment
            or stored_claim != claim
            or work["assignment_digest"] != assignment.assignment_digest
            or attempt["assignment_digest"] != assignment.assignment_digest
            or attempt["handler_binding_digest"]
            != assignment.handler_binding_digest
            or attempt["handler_realization_digest"]
            != assignment.handler_binding_digest
        ):
            raise DeliveryReplayDrift("persisted assignment/claim/handler drift")

    @staticmethod
    def _require_program_plan(
        connection: Connection,
        scope: RuntimeScope,
        tables: ProjectTables,
        installation: InstalledFirstSpecimenDeliveryHandler,
        assignment: RuntimeAssignment,
    ) -> None:
        run = one_mapping(
            connection.execute(
                select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.project_key
                    == assignment.project_key,
                    PUBLIC_TABLES["runtime_runs"].c.run_id == assignment.run_id,
                )
            )
        )
        assert run is not None
        program = ProgramRepository(connection, tables).get(
            scope,
            str(run["program_id"]),
            expected_digest=assignment.program_digest,
        )
        if assignment.plan_digest is None or assignment.step_id is None:
            raise DeliveryReplayDrift("delivery assignment lacks Plan/step identity")
        plan = PlanRepository(connection, tables).get(scope, assignment.plan_digest)
        steps = tuple(
            step for step in plan.ordered_steps if step.step_id == assignment.step_id
        )
        if len(steps) != 1 or steps[0].operation_id is None:
            raise DeliveryReplayDrift("Plan lacks one exact delivery step")
        step = steps[0]
        if (
            step.operation_contract_ref is None
            or step.operation_contract_ref.contract_digest
            != installation.operation_contract_digest
        ):
            raise DeliveryReplayDrift("Plan delivery operation contract drift")
        atoms = tuple(
            atom
            for atom in _atoms(program.root)
            if atom.operation.operation_id == step.operation_id
        )
        if (
            len(atoms) != 1
            or atoms[0].operation.contract_ref.kind != DELIVERY_OPERATION
            or atoms[0].operation.contract_ref.contract_digest
            != installation.operation_contract_digest
        ):
            raise DeliveryReplayDrift("Program lacks one exact delivery Atom")
        return atoms[0]

    @staticmethod
    def _load_current_artifact(
        connection: Connection,
        tables: ProjectTables,
        assignment: RuntimeAssignment,
        payload: InternalExportInput,
        artifact_content_locator: str,
    ) -> tuple[ResearchArtifact, bytes, str]:
        match = _ARTIFACT_REF.fullmatch(payload.artifact_ref)
        if match is None:
            raise DeliveryReplayDrift("typed payload artifact exact ref is malformed")
        artifact_id = match.group("artifact_id")
        expected_revision = int(match.group("revision"))
        expected_digest = match.group("digest")
        rows = connection.execute(
            select(tables.research_objects)
            .where(
                tables.research_objects.c.project_key == assignment.project_key,
                tables.research_objects.c.object_id == artifact_id,
            )
            .order_by(tables.research_objects.c.revision.desc())
        ).mappings().all()
        if not rows:
            raise DeliveryReplayDrift("canonical delivery artifact is absent")
        current = rows[0]
        if (
            current["object_type"] != RESEARCH_ARTIFACT_TYPE.type_id
            or int(current["revision"]) != expected_revision
            or current["content_digest"] != expected_digest
            or current["lifecycle_state"] != "ADMITTED"
            or current["content_ref"] != artifact_content_locator
        ):
            raise DeliveryReplayDrift("canonical admitted artifact/base drift")
        metadata, provenance, metadata_row = _exact_project_value(
            connection,
            tables,
            project_key=assignment.project_key,
            locator=artifact_content_locator,
            expected_digest=expected_digest,
        )
        if metadata_row["object_type"] != RESEARCH_ARTIFACT_TYPE.type_id:
            raise DeliveryReplayDrift("artifact metadata value type drift")
        artifact = _decode_artifact(metadata)
        if artifact_exact_ref(artifact) != payload.artifact_ref:
            raise DeliveryReplayDrift("artifact metadata/exact ref drift")
        exact_locator = provenance.get("artifact_exact_bytes_ref")
        exact_digest = provenance.get("artifact_exact_bytes_digest")
        if not isinstance(exact_locator, str) or not isinstance(exact_digest, str):
            raise DeliveryReplayDrift("artifact exact bytes binding is absent")
        artifact_bytes, _, _ = _exact_project_value(
            connection,
            tables,
            project_key=assignment.project_key,
            locator=exact_locator,
            expected_digest=exact_digest,
        )
        if artifact.content_ref != f"sha256:{exact_digest}":
            raise DeliveryReplayDrift("artifact content_ref/exact bytes drift")
        return artifact, artifact_bytes, str(current["incarnation"])


def _require_semantic_closure(
    payload: InternalExportInput,
    intent: DeliveryIntent,
    artifact: ResearchArtifact,
    artifact_bytes: bytes,
) -> None:
    expected = (
        (payload.delivery_intent_id, intent.delivery_intent_id, "intent id"),
        (payload.artifact_ref, intent.artifact_ref, "artifact ref"),
        (payload.artifact_ref, artifact_exact_ref(artifact), "canonical artifact"),
        (payload.audience, intent.audience, "audience"),
        (payload.approval_refs, intent.approval_refs, "approval refs"),
        (payload.idempotency_key, intent.idempotency_key, "idempotency key"),
    )
    drift = [label for left, right, label in expected if left != right]
    if drift:
        raise DeliveryReplayDrift("delivery semantic closure drift: " + ", ".join(drift))
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    if artifact.content_ref != f"sha256:{digest}":
        raise DeliveryReplayDrift("delivery artifact bytes drift")


class FirstSpecimenDeliveryEffectStore:
    """Execute/read back the internal effect and stage its exact receipt."""

    def __init__(
        self,
        uow_factory: DeliveryHandlerUnitOfWorkFactory,
        *,
        replay: DeliveryReplayPort,
        interpreter: InternalExportInterpreter,
    ) -> None:
        self._uow_factory = uow_factory
        self._replay = replay
        self._interpreter = interpreter

    def execute_exact(
        self,
        installation: InstalledFirstSpecimenDeliveryHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        with self._uow_factory() as uow:
            replay = self._replay.load_exact(
                uow.connection, installation, assignment, claim, context
            )
            try:
                effect = self._interpreter.execute(
                    replay.request,
                    InternalExportExecutionContext(
                        scope=replay.scope,
                        approvals=replay.approvals,
                        now=context.observed_at,
                    ),
                )
            except (ExactBindingConflict, InternalExportBindingConflict) as exc:
                raise DeliveryReplayDrift(str(exc)) from exc
            except InternalExportReadbackUnavailable:
                return InterpreterOutcome.outcome_unknown(
                    self._interpreter.readback_locator(replay.request)
                )
            except InternalExportError:
                return InterpreterOutcome.outcome_unknown(
                    self._interpreter.readback_locator(replay.request)
                )
            except OSError:
                return InterpreterOutcome.outcome_unknown(
                    self._interpreter.readback_locator(replay.request)
                )
            if not isinstance(effect, InternalExportOutcome):
                raise DeliveryOutputDrift("internal export returned no exact outcome")
            try:
                self._persist_receipt(
                    uow.connection,
                    installation,
                    assignment,
                    claim,
                    replay,
                    effect.receipt,
                )
                uow.commit()
            except Exception:  # noqa: BLE001 - effect already crossed boundary
                # The filesystem effect is authoritative.  A failed candidate
                # publication cannot be reported as a definite effect failure.
                return InterpreterOutcome.outcome_unknown(
                    self._interpreter.readback_locator(replay.request)
                )
            return InterpreterOutcome.succeeded(
                effect.receipt.content_digest or "",
                receipt_ref=effect.receipt.receipt_ref,
            )

    @staticmethod
    def _persist_receipt(
        connection: Connection,
        installation: InstalledFirstSpecimenDeliveryHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        replay: FirstSpecimenDeliveryReplay,
        receipt: DeliveryReceiptRef,
    ) -> None:
        if receipt.content_digest is None:
            raise DeliveryOutputDrift("delivery receipt lacks canonical content digest")
        exact = canonical_bytes(dataclass_to_json(receipt, ("content_digest",)))
        if hashlib.sha256(exact).hexdigest() != receipt.content_digest:
            raise DeliveryOutputDrift("delivery receipt canonical digest drift")
        value_id = _result_value_id(assignment)
        provider_receipt_body = _provider_receipt_body(replay.request, receipt)
        provider_receipt_exact = canonical_bytes(provider_receipt_body)
        provider_receipt_digest = hashlib.sha256(
            provider_receipt_exact
        ).hexdigest()
        if provider_receipt_digest != receipt.receipt_digest:
            raise DeliveryOutputDrift("provider receipt body digest drift")
        provider_receipt_value_id = (
            f"provider-receipt-body:sha256:{provider_receipt_digest}"
        )
        provider_receipt_content_ref = (
            f"project-value:{provider_receipt_value_id}"
        )
        provider_receipt_provenance = {
            "contract": "InternalExportProviderReceiptBody.v1",
            "project_key": assignment.project_key,
            "run_id": assignment.run_id,
            "step_id": assignment.step_id,
            "assignment_digest": assignment.assignment_digest,
            "attempt_id": claim.attempt_id,
            "handler_binding_digest": installation.handler_binding_digest,
            "delivery_intent_ref": receipt.delivery_intent_ref,
            "provider_locator": receipt.provider_locator,
            "provider_receipt_digest": provider_receipt_digest,
        }
        provider_receipt_provenance_digest = sha256_hex(
            provider_receipt_provenance
        )
        provenance = {
            "contract": "FirstSpecimenDeliveryReceiptCandidate.v1",
            "operation_kind": DELIVERY_OPERATION,
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
            "delivery_intent_ref": receipt.delivery_intent_ref,
            "receipt_ref": receipt.receipt_ref,
            "provider_locator": receipt.provider_locator,
            "provider_receipt_digest": receipt.receipt_digest,
            "provider_receipt_content_ref": provider_receipt_content_ref,
            "provider_receipt_content_digest": provider_receipt_digest,
            "admission_required": installation.admission_required,
        }
        provenance_digest = sha256_hex(provenance)
        values = ValueRepository(connection, replay.tables)
        provider_stored = values.put_exact(
            replay.scope,
            value_id=provider_receipt_value_id,
            object_type="InternalExportProviderReceipt.v1",
            codec_id="mrw.internal-export.receipt.v1",
            content=provider_receipt_exact,
            expected_digest=provider_receipt_digest,
            provenance_digest=provider_receipt_provenance_digest,
            expected_revision=0,
            expected_incarnation=(
                f"provider-receipt-body:sha256:{provider_receipt_digest}"
            ),
            source_ref=receipt.delivery_intent_ref,
            provenance=provider_receipt_provenance,
            write_receipt_digest=provider_receipt_digest,
        )
        if provider_stored.content_digest != provider_receipt_digest:
            raise DeliveryOutputDrift("provider receipt body write/readback drift")
        stored = values.put_exact(
            replay.scope,
            value_id=value_id,
            object_type=DELIVERY_RECEIPT_REF_TYPE.type_id,
            codec_id=CANONICAL_CODEC_ID,
            content=exact,
            expected_digest=receipt.content_digest,
            provenance_digest=provenance_digest,
            expected_revision=0,
            expected_incarnation=_result_incarnation(assignment),
            source_ref=receipt.delivery_intent_ref,
            provenance=provenance,
            write_receipt_digest=receipt.receipt_digest,
        )
        project_ref = f"project-value:{value_id}"
        project_row = one_mapping(
            connection.execute(
                select(replay.tables.successor_values).where(
                    replay.tables.successor_values.c.project_key
                    == assignment.project_key,
                    replay.tables.successor_values.c.value_id == value_id,
                )
            )
        )
        if project_row is None or stored.content_digest != receipt.content_digest:
            raise DeliveryOutputDrift("project receipt candidate write/readback drift")
        storage_digest = canonical_digest(
            {
                "contract": "ProjectRuntimeValueBinding.v1",
                "project_key": assignment.project_key,
                "runtime_value_id": value_id,
                "project_value_ref": project_ref,
                "content_digest": receipt.content_digest,
                "codec_id": CANONICAL_CODEC_ID,
            }
        )
        RuntimeValueRepository(connection, replay.scope).put_exact(
            RuntimeValueBinding(
                value_id=value_id,
                object_type=DELIVERY_RECEIPT_REF_TYPE.type_id,
                codec_id=CANONICAL_CODEC_ID,
                content_digest=receipt.content_digest,
                byte_size=len(exact),
                project_value_ref=project_ref,
                storage_digest=storage_digest,
                write_intent_digest=str(project_row["write_intent_digest"]),
                write_receipt_digest=receipt.receipt_digest,
            )
        )
        StagedArtifactRepository(connection, replay.scope).stage(
            StagedArtifactBinding(
                artifact_id=_stage_id(assignment),
                run_id=assignment.run_id,
                step_id=assignment.step_id or "",
                attempt_id=claim.attempt_id,
                value_id=value_id,
                receipt_ref=receipt.receipt_ref,
                qualifier_ref=(
                    f"staged:qualifier:{DELIVERY_OPERATION}:"
                    f"sha256:{installation.handler_binding_digest}"
                ),
            )
        )


def _provider_receipt_body(
    request: InternalExportRequest,
    receipt: DeliveryReceiptRef,
) -> dict[str, object]:
    """Reconstruct the exact body hashed by InternalExportInterpreter."""

    return {
        "schema_version": "mrw.internal-export.receipt.v1",
        "delivery_intent_ref": request.delivery_intent.delivery_intent_id,
        "attempt_ref": request.attempt_id,
        "provider_locator": receipt.provider_locator,
        "artifact_digest": request.artifact_digest,
        "request_digest": request.request_digest,
        # InternalExportInterpreter hashes the marker's ISO text, not a
        # re-canonicalized datetime object.  ``_prepared_marker`` always uses
        # datetime.isoformat(), so reconstruct that exact lexical form.
        "outcome_time": receipt.outcome_time.isoformat(),
    }


class PostgresFirstSpecimenDeliveryHandler(RuntimeHandler):
    """RuntimeNode handler for one exact installed internal-export realization."""

    def __init__(
        self,
        installation: InstalledFirstSpecimenDeliveryHandler,
        effects: DeliveryEffectPort,
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
            _require_exact_handler(self.installation, assignment, claim)
            return self._effects.execute_exact(
                self.installation, assignment, claim, context
            )
        except DeliveryHandlerError as exc:
            detail = re.sub(r"[^A-Z0-9]+", "_", str(exc).upper()).strip("_")
            code = type(exc).__name__.upper()
            if detail:
                code = f"{code}:{detail[:96]}"
            raise DefiniteInterpreterFailure(code) from exc


def _require_exact_handler(
    installation: InstalledFirstSpecimenDeliveryHandler,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
) -> None:
    claim.validate_against(assignment)
    ref = assignment.operation_contract_ref
    binding = assignment.handler_binding
    if (
        assignment.assignment_kind is not AssignmentKind.INTERPRET
        or ref is None
        or ref.kind != DELIVERY_OPERATION
        or ref.contract_digest != installation.operation_contract_digest
        or assignment.operation_contract_digest != installation.operation_contract_digest
        or assignment.handler_binding_digest != installation.handler_binding_digest
        or getattr(binding, "interpreter_profile_digest", None)
        != installation.interpreter_profile_digest
        or claim.interpreter_profile_digest != installation.interpreter_profile_digest
        or assignment.return_contract_binding is None
        or assignment.return_contract_binding.admission_required
        != installation.admission_required
    ):
        raise DeliveryReplayDrift("exact internal-delivery handler binding drift")


def _result_value_id(assignment: RuntimeAssignment) -> str:
    return (
        f"result:{assignment.run_id}:{assignment.step_id}:"
        f"epoch-{assignment.execution_epoch}"
    )


def _result_incarnation(assignment: RuntimeAssignment) -> str:
    return (
        f"result:{assignment.incarnation}:{assignment.step_id}:"
        f"epoch-{assignment.execution_epoch}"
    )


def _stage_id(assignment: RuntimeAssignment) -> str:
    return (
        f"stage:{assignment.run_id}:{assignment.step_id}:"
        f"epoch-{assignment.execution_epoch}"
    )


__all__ = [
    "DeliveryHandlerError",
    "DeliveryOutputDrift",
    "DeliveryReplayDrift",
    "FirstSpecimenDeliveryEffectStore",
    "FirstSpecimenDeliveryReplay",
    "InstalledFirstSpecimenDeliveryHandler",
    "PostgresFirstSpecimenDeliveryHandler",
    "PostgresFirstSpecimenDeliveryReplay",
]
