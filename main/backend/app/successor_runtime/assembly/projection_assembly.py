"""Material-projection family assembly from one authored native definition.

The source author owns the family identity, three business cell identities,
client kernel contract and exact read-model anchor.  The assembly installs the
local command/query validation handler and registers the authored read model
without adopting PostgreSQL write authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from app.successor_runtime.assembly.base import (
    PROJECTOR_REGISTRY_INCARNATION,
    ProjectionAssemblyOptions,
    CellBinding,
    FamilyAssembly,
    KernelWiring,
    ProjectorSourceKey,
    ProjectorWiring,
    RollbackBindingDeclaration,
    local_assembly_scope_digest,
    sha256_hex,
    successor_binding,
)
from app.successor_runtime.capabilities import request_identity_port
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.runtime.assignments import RuntimeAssignment
from app.successor_runtime.runtime.projection_native_contribution import (
    PROJECTION_CLIENT_CONTRACT_CELL_ID,
    PROJECTION_COMMAND_QUERY_CELL_ID,
    PROJECTION_FAMILY_ID,
    PROJECTION_READ_MODEL_CELL_ID,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.facade import (
    SuccessorRuntimeFacade,
    error_envelope_v2,
)
from app.successor_runtime.runtime.facade_contracts import (
    MATERIAL_PROJECTION_CLOSURE_ID,
    MATERIAL_PROJECTION_PROJECTOR_ID,
    MATERIAL_PROJECTION_PROJECTOR_VERSION,
    MATERIAL_PROJECTION_SOURCE_KIND,
    ApiEnvelopeV2,
    CommandReceipt,
    CommandSubmissionPort,
    FacadeCommandV2,
    FacadeQueryV2,
    ProjectionResponseMetaV2,
    QueryMetaV2,
    QueryReadPort,
    QueryResult,
    validate_command_v2,
)
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef
from app.successor_runtime.substrate.projections.evidence_matrix import (
    C9EvidenceMatrixRouteHandler,
)
from app.successor_runtime.substrate.projections.registry import (
    ProjectorRegistry,
    validate_projector_contract,
)

PROJECTION_FAMILY_ID = PROJECTION_FAMILY_ID

PROJECTION_ROLLBACK_REF = "main/backend/tests/successor_runtime/test_p4_c9_5_p1_consistency_and_public_payload.py"

PROJECTION_DEPLOYMENT_CATALOG_DIGEST = sha256_hex("mrw.projection.material-closure.deployment-catalog.v2")
PROJECTION_AUTHORITY_REQUIREMENT_DIGEST = sha256_hex("mrw.projection.command-query.authority.v2")
PROJECTION_COMMAND_QUERY_OPERATION_CONTRACT_DIGEST = sha256_hex("projection.command-query.v2")
PROJECTION_COMMAND_QUERY_INTERPRETER_PROFILE_DIGEST = sha256_hex("projection.command-query.validation.v2")
PROJECTION_LOCAL_ONLY_SCOPE_DIGEST = local_assembly_scope_digest()

PROJECTION_READ_MODEL_DECLARED_LOSS = (
    "projection.external-realization.declared-loss-no-call.v2",
    "projection.task-view.bounded-fields.v2",
    "projection.knowledge-material-views.bounded-fields.v2",
)

PROJECTION_COMMAND_QUERY_OPERATION_CONTRACT_REFS = (
    "projection.command.validation-only.v2",
    "projection.query.read-only.v2",
    "projection.api.envelope.status-data-error-meta.v2",
    "projection.request.server-bound-scope-actor-identity.v2",
    "projection.response.control-feedback-forbidden.v2",
)
PROJECTION_COMMAND_QUERY_TRUSTED_ACTOR_REQUIRED = (
    "PROJECTION_COMMAND_QUERY_TRUSTED_ACTOR_REQUIRED"
)
PROJECTION_COMMAND_QUERY_ACTOR_BINDING_MISMATCH = (
    "PROJECTION_COMMAND_QUERY_ACTOR_BINDING_MISMATCH"
)
PROJECTION_COMMAND_QUERY_PAYLOAD_UNSUPPORTED = (
    "PROJECTION_COMMAND_QUERY_PAYLOAD_UNSUPPORTED"
)
PROJECTION_COMMAND_QUERY_FACADE_BINDING_DRIFT = (
    "PROJECTION_COMMAND_QUERY_FACADE_BINDING_DRIFT"
)
PROJECTION_COMMAND_QUERY_DEPLOYMENT_CATALOG_DRIFT = (
    "PROJECTION_COMMAND_QUERY_DEPLOYMENT_CATALOG_DRIFT"
)

PROJECTION_CLIENT_CONTRACT_OPERATION_CONTRACT_REFS = (
    "projection.client.observation.six-states.v2",
    "projection.client.command-submit.v2",
    "projection.client.pending-current-and-historical-decode.v2",
    "projection.client.no-control-feedback.v2",
)

PROJECTION_CLIENT_CONTRACT_KERNEL_ID = "mrw.projection.client-contract.kernel.v2"
PROJECTION_CLIENT_CONTRACT_KERNEL_VERSION = "2.0.0"

PROJECTION_CLIENT_CONTRACT_FRONTEND_FILE_SHA256 = (
    (
        "main/frontend-modern/src/lib/api/domains/successor-runtime.ts",
        "3e993324522b755fdf71f1d719da56137b82270494c0645026f2cdfd7a194ae0",
    ),
    (
        "main/frontend-modern/src/components/SuccessorRuntimeObservation.tsx",
        "c88c30aa6ddbef9135d6cb720bb95a9f7bfbe5d59541be10dce157f952c1a533",
    ),
    (
        "main/frontend-modern/tests/e2e/successor-runtime-observation.spec.ts",
        "0c822a1b1e6f5cee6cd87bd3e3bc51f7170cf8a32de41b649a67544d1322810d",
    ),
    (
        "main/frontend-modern/tests/e2e/successor-runtime-client.spec.ts",
        "dae9ac22a0a8f3392ed1a822894cd97603f286590d38f7258b33bbe5e57e0f72",
    ),
)

PROJECTION_CLIENT_CONTRACT_KERNEL_REFS = tuple(path for path, _ in PROJECTION_CLIENT_CONTRACT_FRONTEND_FILE_SHA256)

PROJECTION_CLIENT_CONTRACT_ROLLBACK_PATHS = PROJECTION_CLIENT_CONTRACT_KERNEL_REFS + (
    (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/i1-successor-assembly/"
        "C9_2FrontendMilestone.v1.json"
    ),
)

PROJECTION_CLIENT_CONTRACT_REQUIRED_WIRING = (
    ("explicit material projection client-contract kernel wiring (mrw.projection.client-contract.kernel.v2)"),
    "no independent RuntimeHandler; frontend-modern sources and e2e specs carry the implementation",
)

PROJECTION_READ_MODEL_OPERATION_CONTRACT_REFS = (
    "projection.read-model.exact-source-key.v2",
    "projection.read-model.offset-cas.v2",
    "projection.read-model.active-material-selector.v2",
    "projection.read-model.current-and-historical-readback.v2",
)
PROJECTION_EVIDENCE_MATRIX_OPERATION_REF = "c9.evidence_matrix.read.v1"
PROJECTION_EVIDENCE_MATRIX_OPERATION_DIGEST = sha256_hex("mrw.successor.c9-1.evidence-matrix.operation.v1")
PROJECTION_EVIDENCE_MATRIX_INTERPRETER_DIGEST = sha256_hex("successor.c9.evidence-matrix.v1")
PROJECTION_EVIDENCE_MATRIX_AUTHORITY_DIGEST = sha256_hex("mrw.successor.c9-1.evidence-matrix.authority.v1")
PROJECTION_EVIDENCE_MATRIX_HANDLER_MODULE = "main/backend/app/successor_runtime/substrate/projections/evidence_matrix.py"


class _MemoryQueryReadPort(QueryReadPort):
    """Minimal deterministic QueryReadPort; no PostgreSQL or other sink."""

    def read(self, query: FacadeQueryV2) -> QueryResult:
        meta = ProjectionResponseMetaV2(
            project_key=query.meta.project_key,
            trace_id=query.meta.trace_id,
            projection_id=MATERIAL_PROJECTION_CLOSURE_ID,
            project_scope_ref=query.meta.project_scope_ref,
            projector_id=MATERIAL_PROJECTION_PROJECTOR_ID,
            projector_version=MATERIAL_PROJECTION_PROJECTOR_VERSION,
            source_kind=MATERIAL_PROJECTION_SOURCE_KIND,
            source_ref="projection:material-projection-local:source",
            source_incarnation="local-offline:material-projection-inc-2",
            projection_generation=0,
            offset_revision=0,
            projection_revision=1,
            source_digest=sha256_hex("mrw.projection.local-offline.source.v2"),
            cursor=0,
        )
        return QueryResult(
            data={
                "project_key": query.meta.project_key,
                "projection_id": MATERIAL_PROJECTION_CLOSURE_ID,
                "query_kind": query.query_kind,
                "cells": {
                    PROJECTION_COMMAND_QUERY_CELL_ID: "INSTALLED",
                    PROJECTION_CLIENT_CONTRACT_CELL_ID: "INSTALLED",
                    PROJECTION_READ_MODEL_CELL_ID: "INSTALLED",
                },
                "no_postgres_write": True,
            },
            meta=meta,
        )


class _MemoryCommandSubmissionPort(CommandSubmissionPort):
    """Minimal deterministic CommandSubmissionPort; never reached by the route."""

    def submit(self, command: FacadeCommandV2) -> CommandReceipt:
        return CommandReceipt(
            receipt_ref="material-projection-receipt:local-offline-validation",
            command_id=command.command_id,
            request_digest=sha256_hex("mrw.projection.local-offline.command.v2"),
            state="TERMINAL",
            idempotency_id=command.idempotency_key,
            logical_request_id="logical:local-offline:material-projection-validation",
            observed_at="2026-09-02T00:00:00+00:00",
        )


def _deterministic_local_scope() -> ProjectScopeRef:
    return ProjectScopeRef(
        project_key="mrw-material-projection-local",
        resolved_schema="mrw_projection_local_offline",
        project_registry_revision=0,
        incarnation="local-offline-material-projection-inc-2",
        scope_digest=PROJECTION_LOCAL_ONLY_SCOPE_DIGEST,
    )


def _kernel_file_sha_digest(
    kernel_id: str,
    files: tuple[tuple[str, str], ...],
) -> str:
    """Deterministic sha256 digest over kernel id and sorted path:sha pairs."""

    return sha256_hex(
        "mrw.projection.assembly.kernel-wiring.file-sha.v2|"
        + kernel_id
        + "|"
        + "|".join(f"{path}:{file_sha}" for path, file_sha in sorted(files))
    )


PROJECTION_CLIENT_CONTRACT_KERNEL_WIRING = KernelWiring(
    cell_id=PROJECTION_CLIENT_CONTRACT_CELL_ID,
    kernel_id=PROJECTION_CLIENT_CONTRACT_KERNEL_ID,
    kernel_version=PROJECTION_CLIENT_CONTRACT_KERNEL_VERSION,
    binding_digest=_kernel_file_sha_digest(
        PROJECTION_CLIENT_CONTRACT_KERNEL_ID,
        PROJECTION_CLIENT_CONTRACT_FRONTEND_FILE_SHA256,
    ),
    binding_refs=PROJECTION_CLIENT_CONTRACT_KERNEL_REFS,
    note=(
        "projection client contract implemented by frontend-modern; digest "
        "is sha256 over kernel id plus sorted path:file-sha pairs "
        "(successor-runtime.ts, SuccessorRuntimeObservation.tsx, observation "
        "and client e2e specs); milestone evidence: "
        "C9_2FrontendMilestone.v1.json"
    ),
)


def build_deterministic_facade_validation_query() -> Annotated[
    FacadeQueryV2,
    "kit:prepared-command "
    "effect_boundary=successor_runtime.projection_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Deterministic read-only query for the LOCAL_OFFLINE validation route."""

    scope = _deterministic_local_scope()
    query_id = "query:material-projection-status"
    return FacadeQueryV2(
        query_id=query_id,
        query_kind="projection_snapshot",
        project_scope_ref=scope,
        actor_ref="local-offline-validation",
        meta=QueryMetaV2(
            project_key=scope.project_key,
            trace_id="trace:local-offline:material-projection-validation",
            query_id=query_id,
            project_scope_ref=scope,
        ),
        params={
            "cell_ids": (
                PROJECTION_COMMAND_QUERY_CELL_ID,
                PROJECTION_CLIENT_CONTRACT_CELL_ID,
                PROJECTION_READ_MODEL_CELL_ID,
            )
        },
        read_only=True,
    )


def build_deterministic_facade_closure() -> Annotated[
    SuccessorRuntimeFacade,
    "kit:prepared-command "
    "effect_boundary=successor_runtime.projection_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """LOCAL_OFFLINE facade bound only to minimal in-memory ports."""

    return SuccessorRuntimeFacade(
        submission_port=_MemoryCommandSubmissionPort(),
        query_port=_MemoryQueryReadPort(),
    )


def build_deterministic_command_submission_port() -> Annotated[
    CommandSubmissionPort,
    "kit:prepared-command "
    "effect_boundary=successor_runtime.projection_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Return the deterministic no-write command submission port.

    The registry-backed HTTP facade reuses this port so commands stay
    validation-only and never perform a write while the read facade is being
    wired to real PostgreSQL reads.
    """

    return _MemoryCommandSubmissionPort()


def _validate_exact_facade_binding(
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
    handler: Any,
) -> None:
    if claim.assignment_digest != assignment.assignment_digest:
        raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
    if claim.claim_authority_epoch != assignment.claim_authority_epoch:
        raise DefiniteInterpreterFailure("CLAIM_AUTHORITY_EPOCH_DRIFT")
    if (
        assignment.handler_binding_digest != handler.handler_binding_digest
        or assignment.operation_contract_digest != handler.operation_contract_digest
    ):
        raise DefiniteInterpreterFailure(
            PROJECTION_COMMAND_QUERY_FACADE_BINDING_DRIFT
        )
    if assignment.deployment_catalog_digest != handler.deployment_catalog_digest:
        raise DefiniteInterpreterFailure(
            PROJECTION_COMMAND_QUERY_DEPLOYMENT_CATALOG_DRIFT
        )


def _reject_command(command: FacadeCommandV2) -> ApiEnvelopeV2:
    violations = validate_command_v2(command).violations
    if violations:
        return error_envelope_v2(
            status="error",
            meta=command.meta,
            code="COMMAND_CONTRACT_VIOLATION",
            message=violations[0].message,
            details={"violations": [violation.message for violation in violations]},
        )
    return error_envelope_v2(
        status="error",
        meta=command.meta,
        code="QUERY_ROUTE_REJECTS_COMMAND",
        message=("projection.command-query.v2 validates commands without submitting them"),
    )


class ProjectionCommandQueryValidationRouteHandler(RuntimeHandler):
    """Read-only facade validation route handler over one captured payload.

    ``query`` may be a deterministic FacadeQueryV2 (executed through the
    facade) or a FacadeCommandV2 (validated and rejected without submit).
    """

    def __init__(
        self,
        *,
        facade: SuccessorRuntimeFacade,
        query: FacadeQueryV2 | FacadeCommandV2,
        binding: Any,
        request_identity_observation: request_identity_port.RequestIdentityObservation | None = None,
        request_identity_require_trusted: bool = True,
    ) -> None:
        if facade is None or query is None:
            raise ValueError("projection command/query handler requires facade and query closure")
        self.facade = facade
        self.query = query
        self.handler_binding_digest = binding.binding_digest
        self.interpreter_profile_digest = binding.interpreter_profile_digest
        self.operation_contract_digest = binding.operation_contract_digest
        self.deployment_catalog_digest = binding.deployment_catalog_digest
        self.request_identity_observation = (
            request_identity_observation
            if request_identity_observation is not None
            else request_identity_port.RequestIdentityObservation(
                actor_id="local-offline-validation",
                actor_source="local_offline_validation",
                actor_trusted=True,
            )
        )
        self.request_identity_require_trusted = request_identity_require_trusted
        self.request_identity_calls = 0
        self.last_actor_context: request_identity_port.RequestActorContext | None = None

    def _resolve_request_actor(self) -> request_identity_port.RequestActorContext:
        """Consume the horizontal request-identity port before facade handling."""

        try:
            context = request_identity_port.resolve_request_actor_context(self.request_identity_observation)
            self.request_identity_calls += 1
            if self.request_identity_require_trusted:
                context = request_identity_port.require_trusted_actor_context(context)
        except request_identity_port.TrustedActorRequired as exc:
            raise DefiniteInterpreterFailure(
                PROJECTION_COMMAND_QUERY_TRUSTED_ACTOR_REQUIRED
            ) from exc
        self.last_actor_context = context
        return context

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        _validate_exact_facade_binding(assignment, claim, self)
        actor_context = self._resolve_request_actor()
        expected_actor_ref = getattr(self.query, "actor_ref", "")
        if actor_context.actor_id != expected_actor_ref:
            raise DefiniteInterpreterFailure(
                PROJECTION_COMMAND_QUERY_ACTOR_BINDING_MISMATCH
            )
        if isinstance(self.query, FacadeCommandV2):
            envelope = _reject_command(self.query)
        elif isinstance(self.query, FacadeQueryV2):
            envelope = self.facade.query(self.query)
        else:
            raise DefiniteInterpreterFailure(
                PROJECTION_COMMAND_QUERY_PAYLOAD_UNSUPPORTED
            )
        return InterpreterOutcome.succeeded(content_digest(envelope))


def _resolve_c9_native_definition(native_definition: object | None) -> object | None:
    """Resolve an optional typed C9 native definition."""

    from app.successor_runtime.runtime.projection_native_contribution import (
        DEFAULT_PROJECTION_NATIVE_SOURCE,
        ProjectionNativeDefinition,
        compile_projection_native_contribution,
    )

    if native_definition is None:
        native_result = compile_projection_native_contribution(DEFAULT_PROJECTION_NATIVE_SOURCE)
        if not isinstance(native_result, ProjectionNativeDefinition):
            native_definition = getattr(native_result, "definition", native_result)
        else:
            return native_result
    candidate = getattr(native_definition, "definition", native_definition)
    if not isinstance(candidate, ProjectionNativeDefinition):
        raise TypeError("C9 assembly native_definition must be a ProjectionNativeDefinition")
    return candidate


def _c9_authority_digest(definition: object) -> str:
    return content_digest((definition.source.facade, definition.source.frontend, definition.source.anchor))


def validate_projection_assembly_native_definition(
    definition: object,
    assembly: object,
) -> None:
    """Validate lowered C9 slot identities against the real family assembly."""

    from app.successor_runtime.runtime.projection_native_contribution import (
        ASSEMBLY_CELL_IDS,
        ProjectionNativeDefinition,
    )

    if not isinstance(definition, ProjectionNativeDefinition):
        raise TypeError("validate_projection_assembly_native_definition requires ProjectionNativeDefinition")
    if not isinstance(assembly, FamilyAssembly) or assembly.family_id != definition.source.family_id:
        raise ValueError("projection native validator requires its authored FamilyAssembly")
    if tuple(cell.cell_id for cell in assembly.cells) != ASSEMBLY_CELL_IDS:
        raise ValueError("projection native cell order drift")
    if not definition.facade_validation.valid:
        raise ValueError("C9 native facade DTO validation drift")
    if definition.projector_key != definition.current_offset.key:
        raise ValueError("C9 native projector/offset key drift")
    if any(cell.family_id != definition.source.family_id for cell in assembly.cells):
        raise ValueError("projection assembly family ownership drift")
    if tuple(item.cell_id for item in assembly.kernel_wiring) != (definition.source.cell_ids[1],):
        raise ValueError("projection client-contract kernel wiring drift")
    if len(assembly.projector_wiring) != 1:
        raise ValueError("projection read-model wiring is missing or duplicated")
    wiring = assembly.projector_wiring[0]
    anchor = definition.source.anchor
    if (
        wiring.cell_id,
        wiring.projection_id,
        wiring.projection_schema_ref,
        wiring.projector_id,
        wiring.projector_version,
        wiring.source_kind,
    ) != (
        definition.source.cell_ids[2],
        definition.source.projection_contract,
        anchor.projection_schema_ref,
        anchor.projector_id,
        anchor.projector_version,
        anchor.source_kind,
    ):
        raise ValueError("projection read-model native identity drift")


def _build_c9_1_route_handler(
    *,
    facade: SuccessorRuntimeFacade,
    request_identity_observation: request_identity_port.RequestIdentityObservation | None = None,
    request_identity_require_trusted: bool = True,
    native_definition: object | None = None,
) -> ProjectionCommandQueryValidationRouteHandler:
    binding = successor_binding(
        operation_contract_digest=PROJECTION_COMMAND_QUERY_OPERATION_CONTRACT_DIGEST,
        interpreter_profile_digest=PROJECTION_COMMAND_QUERY_INTERPRETER_PROFILE_DIGEST,
        deployment_catalog_digest=PROJECTION_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=PROJECTION_LOCAL_ONLY_SCOPE_DIGEST,
        authority_requirement_digest=(
            _c9_authority_digest(native_definition)
            if native_definition is not None
            else PROJECTION_AUTHORITY_REQUIREMENT_DIGEST
        ),
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    return ProjectionCommandQueryValidationRouteHandler(
        facade=facade,
        query=build_deterministic_facade_validation_query(),
        binding=binding,
        request_identity_observation=request_identity_observation,
        request_identity_require_trusted=request_identity_require_trusted,
    )


def _unwired_c9_1_cell(*, family_id: str, cell_id: str) -> CellBinding:
    return CellBinding(
        cell_id=cell_id,
        family_id=family_id,
        status="UNWIRED_DECLARED",
        operation_contract_refs=PROJECTION_COMMAND_QUERY_OPERATION_CONTRACT_REFS,
        required_wiring=(
            "facade command/query repository 接线",
            "NO_ROUTE_OR_CONTROL_EFFECT 保持",
        ),
        note=(
            "缺 facade 纯验证 closure（SuccessorRuntimeFacade + 最小内存 "
            "query/submission port）；router 挂载属于 WP-I1-06，本 assembly "
            "不装路由"
        ),
    )


def _installed_c9_1_cell(
    handler: ProjectionCommandQueryValidationRouteHandler,
    *,
    family_id: str,
    cell_id: str,
) -> CellBinding:
    return CellBinding(
        cell_id=cell_id,
        family_id=family_id,
        status="INSTALLED",
        operation_contract_refs=PROJECTION_COMMAND_QUERY_OPERATION_CONTRACT_REFS,
        handler_binding_digest=handler.handler_binding_digest,
        required_wiring=("NO_ROUTE_OR_CONTROL_EFFECT 保持",),
        note=(
            "LOCAL_OFFLINE facade validation route handler installed; read-only "
            "query path only; projection request-identity port consumed before facade "
            "handling with trusted-actor fail-closed binding; router 挂载属于 "
            "WP-I1-06，本 assembly 不装路由"
        ),
    )


def build_projection_assembly(
    *,
    options: ProjectionAssemblyOptions | None = None,
    projector_source_keys: Mapping[str, ProjectorSourceKey] | None = None,
    native_definition: object | None = None,
) -> Annotated[
    FamilyAssembly,
    "kit:prepared-command "
    "effect_boundary=successor_runtime.projection_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Build the authored material-projection family assembly.

    The native source owns the family, three business cell ids and default
    read-model source key.  Explicit options may replace the local facade or
    the default source key without changing those authored identities.
    """

    opts = options or ProjectionAssemblyOptions()
    definition = _resolve_c9_native_definition(native_definition)
    family_id = definition.source.family_id
    command_cell_id, client_cell_id, read_cell_id = definition.source.cell_ids
    handlers: list[Any] = []
    bound_facade = opts.facade or build_deterministic_facade_closure()
    if not isinstance(bound_facade, SuccessorRuntimeFacade):
        raise TypeError("projection command/query options facade must be a SuccessorRuntimeFacade")
    handler = _build_c9_1_route_handler(
        facade=bound_facade,
        native_definition=definition,
    )
    command_query_cell = _installed_c9_1_cell(
        handler,
        family_id=family_id,
        cell_id=command_cell_id,
    )
    handlers.append(handler)

    evidence_matrix_note = ""
    if opts.evidence_records is not None:
        evidence_binding = successor_binding(
            operation_contract_digest=PROJECTION_EVIDENCE_MATRIX_OPERATION_DIGEST,
            interpreter_profile_digest=PROJECTION_EVIDENCE_MATRIX_INTERPRETER_DIGEST,
            deployment_catalog_digest=PROJECTION_DEPLOYMENT_CATALOG_DIGEST,
            project_scope_digest=PROJECTION_LOCAL_ONLY_SCOPE_DIGEST,
            authority_requirement_digest=PROJECTION_EVIDENCE_MATRIX_AUTHORITY_DIGEST,
        )
        evidence_handler = C9EvidenceMatrixRouteHandler(
            records=tuple(opts.evidence_records),
            handler_binding_digest=evidence_binding.binding_digest,
            interpreter_profile_digest=evidence_binding.interpreter_profile_digest,
            operation_contract_digest=evidence_binding.operation_contract_digest,
            deployment_catalog_digest=evidence_binding.deployment_catalog_digest,
        )
        handlers.append(evidence_handler)
        evidence_matrix_note = (
            "; historical evidence-matrix read-only route handler carried by "
            "the family; seven-line projection over typed runtime/readback "
            "records; no DB/scheduler/executor/canonical write adopted"
        )

    native_anchor = definition.source.anchor
    read_model_wiring = ProjectorWiring(
        cell_id=read_cell_id,
        projector_id=native_anchor.projector_id,
        projector_version=native_anchor.projector_version,
        source_kind=native_anchor.source_kind,
        projection_id=native_anchor.projection_id,
        projection_schema_ref=native_anchor.projection_schema_ref,
        declared_loss=PROJECTION_READ_MODEL_DECLARED_LOSS,
        note=("read-model registration binds the authored exact source key; no PostgreSQL write authority is adopted"),
    )
    source_keys = projector_source_keys or {}
    read_model_source_key = source_keys.get(read_cell_id) or source_keys.get("C9.3")
    if read_model_source_key is None:
        read_model_source_key = ProjectorSourceKey(
            source_ref=native_anchor.source_ref,
            source_incarnation=native_anchor.source_incarnation,
        )
    read_model_contract = read_model_wiring.to_contract(read_model_source_key)
    read_model_validation = validate_projector_contract(read_model_contract)
    if not read_model_validation.valid:
        raise ValueError(
            "projection read-model projector contract invalid: "
            + "; ".join(item.message for item in read_model_validation.violations)
        )
    read_model_binding_digest = read_model_wiring.registration_digest(read_model_contract)
    read_model_registry = ProjectorRegistry(
        revision=0,
        incarnation=PROJECTOR_REGISTRY_INCARNATION,
        projectors=(read_model_contract,),
    )
    read_model_status = "INSTALLED"
    read_model_required_wiring: tuple[str, ...] = ()
    read_model_note = (
        "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED: exact "
        "source_ref/source_incarnation bound from the authored native source; "
        "no PostgreSQL write adopted"
    )

    cells = (
        command_query_cell,
        CellBinding(
            cell_id=client_cell_id,
            family_id=family_id,
            status="INSTALLED",
            operation_contract_refs=PROJECTION_CLIENT_CONTRACT_OPERATION_CONTRACT_REFS,
            handler_binding_digest=PROJECTION_CLIENT_CONTRACT_KERNEL_WIRING.binding_digest,
            recovery_binding_ref="mrw.projection.client-contract.recovery.v2",
            rollback_binding_refs=PROJECTION_CLIENT_CONTRACT_ROLLBACK_PATHS,
            required_wiring=PROJECTION_CLIENT_CONTRACT_REQUIRED_WIRING,
            note=(
                "projection client contract INSTALLED via explicit "
                "KernelWiring; implementation evidence: "
                "C9_2FrontendMilestone.v1.json; no route, provider, network, "
                "canonical write or control feedback adopted"
            ),
        ),
        CellBinding(
            cell_id=read_cell_id,
            family_id=family_id,
            status=read_model_status,
            operation_contract_refs=PROJECTION_READ_MODEL_OPERATION_CONTRACT_REFS,
            handler_binding_digest=read_model_binding_digest,
            required_wiring=read_model_required_wiring,
            note=read_model_note + evidence_matrix_note,
        ),
    )
    read_model_wiring_tuple = (read_model_wiring,)
    read_model_rollback_refs = (PROJECTION_ROLLBACK_REF,)
    if evidence_matrix_note:
        read_model_rollback_refs += (PROJECTION_EVIDENCE_MATRIX_HANDLER_MODULE,)
    rollback_bindings = (
        RollbackBindingDeclaration(
            cell_id=command_cell_id,
            status="PRESENT",
            binding_refs=(PROJECTION_ROLLBACK_REF,),
        ),
        RollbackBindingDeclaration(
            cell_id=client_cell_id,
            status="PRESENT",
            binding_refs=PROJECTION_CLIENT_CONTRACT_ROLLBACK_PATHS,
            note=(
                "projection client contract rollback binding present: "
                "frontend-modern implementation, e2e specs and frontend "
                "milestone evidence"
            ),
        ),
        RollbackBindingDeclaration(
            cell_id=read_cell_id,
            status="PRESENT",
            binding_refs=read_model_rollback_refs,
        ),
    )
    return FamilyAssembly(
        family_id=family_id,
        cells=cells,
        handlers=tuple(handlers),
        kernel_wiring=(PROJECTION_CLIENT_CONTRACT_KERNEL_WIRING,),
        projector_wiring=read_model_wiring_tuple,
        projector_registry=read_model_registry,
        rollback_bindings=rollback_bindings,
    )


__all__ = [
    "PROJECTION_COMMAND_QUERY_OPERATION_CONTRACT_REFS",
    "PROJECTION_CLIENT_CONTRACT_KERNEL_ID",
    "PROJECTION_CLIENT_CONTRACT_KERNEL_VERSION",
    "PROJECTION_CLIENT_CONTRACT_KERNEL_WIRING",
    "PROJECTION_CLIENT_CONTRACT_OPERATION_CONTRACT_REFS",
    "PROJECTION_CLIENT_CONTRACT_REQUIRED_WIRING",
    "PROJECTION_CLIENT_CONTRACT_ROLLBACK_PATHS",
    "PROJECTION_READ_MODEL_DECLARED_LOSS",
    "PROJECTION_READ_MODEL_OPERATION_CONTRACT_REFS",
    "PROJECTION_EVIDENCE_MATRIX_OPERATION_REF",
    "PROJECTION_FAMILY_ID",
    "PROJECTION_ROLLBACK_REF",
    "ProjectionCommandQueryValidationRouteHandler",
    "PROJECTION_COMMAND_QUERY_ACTOR_BINDING_MISMATCH",
    "PROJECTION_COMMAND_QUERY_DEPLOYMENT_CATALOG_DRIFT",
    "PROJECTION_COMMAND_QUERY_FACADE_BINDING_DRIFT",
    "PROJECTION_COMMAND_QUERY_PAYLOAD_UNSUPPORTED",
    "PROJECTION_COMMAND_QUERY_TRUSTED_ACTOR_REQUIRED",
    "build_projection_assembly",
    "validate_projection_assembly_native_definition",
    "build_deterministic_facade_closure",
    "build_deterministic_facade_validation_query",
    "build_deterministic_command_submission_port",
]
