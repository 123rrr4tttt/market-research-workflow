"""C9 family assembly: installable facade validation route handler.

The facade validation route is installed only when an exact facade closure is
supplied; without it C9.1 stays unwired and lists the missing closure.  Router
mounting belongs to WP-I1-06 and is never performed here.  C9.2 is carried by
an explicit ``KernelWiring`` declaration over the implemented frontend-modern
typed contract; it is not a family ``RuntimeHandler``.  C9.3 declares projector
wiring without inventing per-run keys; when the run owner supplies an exact
source_ref/source_incarnation it registers one read-only projector contract in
the family registry and becomes INSTALLED without adopting a PostgreSQL write.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.successor_runtime.assembly.base import (
    PROJECTOR_REGISTRY_INCARNATION,
    C9AssemblyOptions,
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
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.runtime.assignments import RuntimeAssignment
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.facade import (
    SuccessorRuntimeFacade,
    error_envelope_v2,
)
from app.successor_runtime.runtime.facade_contracts import (
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
from app.successor_runtime.substrate.postgres.c9_projection_sources import (
    C9_CLOSURE_MANIFEST_SCHEMA,
    C9_SEMANTIC_SOURCE_KIND,
    C9_TYPED_SOURCE_PROJECTOR_ID,
    C9_TYPED_SOURCE_PROJECTOR_VERSION,
)
from app.successor_runtime.substrate.projections.registry import (
    ProjectorRegistry,
    validate_projector_contract,
)

C9_FAMILY_ID = "C9"

C9_ROLLBACK_REF = (
    "main/backend/tests/successor_runtime/"
    "test_p4_c9_5_p1_consistency_and_public_payload.py"
)

C9_DEPLOYMENT_CATALOG_DIGEST = sha256_hex("mrw.successor.deployment-catalog.c9.v1")
C9_AUTHORITY_REQUIREMENT_DIGEST = sha256_hex("mrw.successor.c9.authority.v1")
C9_1_OPERATION_CONTRACT_DIGEST = sha256_hex("facade.query.read-only.v1")
C9_1_INTERPRETER_PROFILE_DIGEST = sha256_hex("successor.c9.facade-validation.v1")
C9_LOCAL_ONLY_SCOPE_DIGEST = local_assembly_scope_digest()

C9_3_DECLARED_LOSS = (
    "c9.external-sink-elasticsearch-qdrant-graph-provider-declared-loss-no-call.v1",
    "c9.agent-session-bounded-fields-not-full-journal.v1",
    "c9.local-graph-search-bounded-fields-not-canonical-knowledge.v1",
)

C9_1_OPERATION_CONTRACT_REFS = (
    "facade.command.description-validation.execute-false.v1",
    "facade.query.read-only.v1",
    "api.envelope.status-data-error-meta.v1",
    "api.status.ok-error-unavailable-blocked-waiting.v1",
    "facade.sse.after-seq-exclusive.v1",
    "facade.response.control-feedback-forbidden.v1",
    "api.external.dto.forbid-scope-schema-actor-authority-control.v1",
    "api.internal.server.inject-scope-actor-idempotency-revision-approval.v1",
)

C9_2_OPERATION_CONTRACT_REFS = (
    "frontend.observation.six-states.v1",
    "frontend.interaction.command_submit.v1",
    "frontend.no_control_feedback.v1",
    "frontend.design_only_typed_contract.v1",
)

C9_2_KERNEL_ID = "mrw.successor.frontend.c9-2.typed-contract.v1"
C9_2_KERNEL_VERSION = "1.0.0"

C9_2_FRONTEND_FILE_SHA256 = (
    (
        "main/frontend-modern/src/lib/api/domains/successor-runtime.ts",
        "cfd390ee67a183e9052a802e79ed0e33da492c3bafb7bdbf27c757a500901436",
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
        "f3d423b6be77b4578682c224d04d27f4d82b44bc0c2dc0fa94295f6bbd7c7065",
    ),
)

C9_2_KERNEL_REFS = tuple(path for path, _ in C9_2_FRONTEND_FILE_SHA256)

C9_2_ROLLBACK_PATHS = C9_2_KERNEL_REFS + (
    (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/i1-successor-assembly/"
        "C9_2FrontendMilestone.v1.json"
    ),
)

C9_2_REQUIRED_WIRING = (
    (
        "explicit C9.2 frontend typed-contract kernel wiring "
        "(mrw.successor.frontend.c9-2.typed-contract.v1)"
    ),
    "no independent RuntimeHandler; frontend-modern sources and e2e specs carry the implementation",
)

C9_3_OPERATION_CONTRACT_REFS = (
    "projector.registry.exact_key.v1",
    "projector.offset.cas_advance.v1",
    "projector.offset.aba_stale.v1",
    "projector.rebuild.plan_only.v1",
    "projector.source_offsets.snapshot.v1",
)


class _MemoryQueryReadPort(QueryReadPort):
    """Minimal deterministic QueryReadPort; no PostgreSQL or other sink."""

    def read(self, query: FacadeQueryV2) -> QueryResult:
        meta = ProjectionResponseMetaV2(
            project_key=query.meta.project_key,
            trace_id=query.meta.trace_id,
            projection_id=query.query_id,
            project_scope_ref=query.meta.project_scope_ref,
            projector_id="c9.local-offline.validation.projector.v1",
            projector_version="1.0.0",
            source_kind="CANONICAL_OWNER",
            source_ref="local-offline:facade-validation",
            source_incarnation="local-offline:facade-validation-inc-1",
            projection_generation=0,
            offset_revision=0,
            projection_revision=1,
            source_digest=sha256_hex("mrw.successor.c9.local-offline.source.v1"),
            cursor=0,
        )
        return QueryResult(
            data={
                "project_key": query.meta.project_key,
                "projection_id": query.query_id,
                "query_kind": query.query_kind,
                "cells": {
                    "C9.1": "INSTALLED",
                    "C9.2": "INSTALLED",
                    "C9.3": "PROJECTOR_WIRING_DECLARED",
                },
                "no_postgres_write": True,
            },
            meta=meta,
        )


class _MemoryCommandSubmissionPort(CommandSubmissionPort):
    """Minimal deterministic CommandSubmissionPort; never reached by the route."""

    def submit(self, command: FacadeCommandV2) -> CommandReceipt:
        return CommandReceipt(
            receipt_ref="receipt:local-offline:c9-validation",
            command_id=command.command_id,
            request_digest=sha256_hex("mrw.successor.c9.local-offline.command.v1"),
            state="TERMINAL",
            idempotency_id=command.idempotency_key,
            logical_request_id="logical:local-offline:c9-validation",
            observed_at="2026-09-02T00:00:00+00:00",
        )


def _deterministic_local_scope() -> ProjectScopeRef:
    return ProjectScopeRef(
        project_key="mrw-successor-c9-local",
        resolved_schema="mrw.successor.c9.local-offline",
        project_registry_revision=0,
        incarnation="local-offline-facade-inc-1",
        scope_digest=C9_LOCAL_ONLY_SCOPE_DIGEST,
    )


def _kernel_file_sha_digest(
    kernel_id: str,
    files: tuple[tuple[str, str], ...],
) -> str:
    """Deterministic sha256 digest over kernel id and sorted path:sha pairs."""

    return sha256_hex(
        "mrw.successor.assembly.kernel-wiring.file-sha.v1|"
        + kernel_id
        + "|"
        + "|".join(f"{path}:{file_sha}" for path, file_sha in sorted(files))
    )


C9_2_KERNEL_WIRING = KernelWiring(
    cell_id="C9.2",
    kernel_id=C9_2_KERNEL_ID,
    kernel_version=C9_2_KERNEL_VERSION,
    binding_digest=_kernel_file_sha_digest(
        C9_2_KERNEL_ID,
        C9_2_FRONTEND_FILE_SHA256,
    ),
    binding_refs=C9_2_KERNEL_REFS,
    note=(
        "C9.2 frontend typed contract implemented by frontend-modern; digest "
        "is sha256 over kernel id plus sorted path:file-sha pairs "
        "(successor-runtime.ts, SuccessorRuntimeObservation.tsx, observation "
        "and client e2e specs); milestone evidence: "
        "C9_2FrontendMilestone.v1.json"
    ),
)


def build_deterministic_facade_validation_query() -> FacadeQueryV2:
    """Deterministic read-only query for the LOCAL_OFFLINE validation route."""

    scope = _deterministic_local_scope()
    query_id = "q:successor-runtime-status"
    return FacadeQueryV2(
        query_id=query_id,
        query_kind="successor_runtime.status.v1",
        project_scope_ref=scope,
        actor_ref="local-offline-validation",
        meta=QueryMetaV2(
            project_key=scope.project_key,
            trace_id="trace:local-offline:c9-validation",
            query_id=query_id,
            project_scope_ref=scope,
        ),
        params={"cell_ids": ("C9.1", "C9.2", "C9.3")},
        read_only=True,
    )


def build_deterministic_facade_closure() -> SuccessorRuntimeFacade:
    """LOCAL_OFFLINE facade bound only to minimal in-memory ports."""

    return SuccessorRuntimeFacade(
        submission_port=_MemoryCommandSubmissionPort(),
        query_port=_MemoryQueryReadPort(),
    )


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
        raise DefiniteInterpreterFailure("EXACT_C9_1_FACADE_BINDING_DRIFT")
    if assignment.deployment_catalog_digest != handler.deployment_catalog_digest:
        raise DefiniteInterpreterFailure("EXACT_C9_1_FACADE_DEPLOYMENT_CATALOG_DRIFT")


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
        message="facade.query.read-only.v1 validates commands without submitting them",
    )


class C9_1FacadeValidationRouteHandler(RuntimeHandler):
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
    ) -> None:
        if facade is None or query is None:
            raise ValueError("C9.1 route handler requires facade and query closure")
        self.facade = facade
        self.query = query
        self.handler_binding_digest = binding.binding_digest
        self.interpreter_profile_digest = binding.interpreter_profile_digest
        self.operation_contract_digest = binding.operation_contract_digest
        self.deployment_catalog_digest = binding.deployment_catalog_digest

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        _validate_exact_facade_binding(assignment, claim, self)
        if isinstance(self.query, FacadeCommandV2):
            envelope = _reject_command(self.query)
        elif isinstance(self.query, FacadeQueryV2):
            envelope = self.facade.query(self.query)
        else:
            raise DefiniteInterpreterFailure("C9_1_FACADE_PAYLOAD_UNSUPPORTED")
        return InterpreterOutcome.succeeded(content_digest(envelope))


def _build_c9_1_route_handler(
    *,
    facade: SuccessorRuntimeFacade,
) -> C9_1FacadeValidationRouteHandler:
    binding = successor_binding(
        operation_contract_digest=C9_1_OPERATION_CONTRACT_DIGEST,
        interpreter_profile_digest=C9_1_INTERPRETER_PROFILE_DIGEST,
        deployment_catalog_digest=C9_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=C9_LOCAL_ONLY_SCOPE_DIGEST,
        authority_requirement_digest=C9_AUTHORITY_REQUIREMENT_DIGEST,
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )
    return C9_1FacadeValidationRouteHandler(
        facade=facade,
        query=build_deterministic_facade_validation_query(),
        binding=binding,
    )


def _unwired_c9_1_cell() -> CellBinding:
    return CellBinding(
        cell_id="C9.1",
        family_id=C9_FAMILY_ID,
        status="UNWIRED_DECLARED",
        operation_contract_refs=C9_1_OPERATION_CONTRACT_REFS,
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


def _installed_c9_1_cell(handler: C9_1FacadeValidationRouteHandler) -> CellBinding:
    return CellBinding(
        cell_id="C9.1",
        family_id=C9_FAMILY_ID,
        status="INSTALLED",
        operation_contract_refs=C9_1_OPERATION_CONTRACT_REFS,
        handler_binding_digest=handler.handler_binding_digest,
        required_wiring=("NO_ROUTE_OR_CONTROL_EFFECT 保持",),
        note=(
            "LOCAL_OFFLINE facade validation route handler installed; read-only "
            "query path only; router 挂载属于 WP-I1-06，本 assembly 不装路由"
        ),
    )


def build_c9_assembly(
    *,
    options: C9AssemblyOptions | None = None,
    projector_source_keys: Mapping[str, ProjectorSourceKey] | None = None,
) -> FamilyAssembly:
    """Build the C9 family assembly with optional facade route installation.

    C9.3 stays ``PROJECTOR_WIRING_DECLARED`` until the run owner supplies a
    per-run source key; with a key it registers one read-only projector
    contract in the family registry and becomes ``INSTALLED``.
    """

    opts = options or C9AssemblyOptions()
    handlers: list[Any] = []
    c9_1_cell = _unwired_c9_1_cell()
    if opts.facade is not None:
        if not isinstance(opts.facade, SuccessorRuntimeFacade):
            raise TypeError("C9.1 options facade must be a SuccessorRuntimeFacade")
        handler = _build_c9_1_route_handler(facade=opts.facade)
        c9_1_cell = _installed_c9_1_cell(handler)
        handlers.append(handler)

    c9_3_wiring = ProjectorWiring(
        cell_id="C9.3",
        projector_id=C9_TYPED_SOURCE_PROJECTOR_ID,
        projector_version=C9_TYPED_SOURCE_PROJECTOR_VERSION,
        source_kind=C9_SEMANTIC_SOURCE_KIND,
        projection_id=C9_CLOSURE_MANIFEST_SCHEMA,
        projection_schema_ref=C9_CLOSURE_MANIFEST_SCHEMA,
        declared_loss=C9_3_DECLARED_LOSS,
        note=(
            "registry has no default registration; no PostgreSQL write is "
            "adopted; exact per-run source key is supplied by the runner"
        ),
    )
    c9_3_source_key = (projector_source_keys or {}).get("C9.3")
    if c9_3_source_key is None:
        c9_3_status = "PROJECTOR_WIRING_DECLARED"
        c9_3_binding_digest = None
        c9_3_required_wiring: tuple[str, ...] = (
            "默认 projector 注册",
            "offset CAS 生产接线",
            "C9_NO_POSTGRES_WRITE_UNADOPTED 保持",
        )
        c9_3_note = (
            "缺 默认注册与 per-run projector/source key；no PostgreSQL write adopted"
        )
        c9_3_registry = None
    else:
        c9_3_contract = c9_3_wiring.to_contract(c9_3_source_key)
        c9_3_validation = validate_projector_contract(c9_3_contract)
        if not c9_3_validation.valid:
            raise ValueError(
                "C9.3 projector contract invalid: "
                + "; ".join(item.message for item in c9_3_validation.violations)
            )
        c9_3_binding_digest = c9_3_wiring.registration_digest(c9_3_contract)
        c9_3_registry = ProjectorRegistry(
            revision=0,
            incarnation=PROJECTOR_REGISTRY_INCARNATION,
            projectors=(c9_3_contract,),
        )
        c9_3_status = "INSTALLED"
        c9_3_required_wiring = ()
        c9_3_note = (
            "REGISTRY_REGISTRATION_ONLY_NO_PG_WRITE_AUTHORITY_CLOSED: "
            "per-run source_ref/source_incarnation bound; no PostgreSQL write "
            "adopted"
        )

    cells = (
        c9_1_cell,
        CellBinding(
            cell_id="C9.2",
            family_id=C9_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=C9_2_OPERATION_CONTRACT_REFS,
            handler_binding_digest=C9_2_KERNEL_WIRING.binding_digest,
            recovery_binding_ref="mrw.successor.frontend.c9-2.recovery.v1",
            rollback_binding_refs=C9_2_ROLLBACK_PATHS,
            required_wiring=C9_2_REQUIRED_WIRING,
            note=(
                "C9.2 frontend typed contract INSTALLED via explicit "
                "KernelWiring; implementation evidence: "
                "C9_2FrontendMilestone.v1.json; no route, provider, network, "
                "canonical write or control feedback adopted"
            ),
        ),
        CellBinding(
            cell_id="C9.3",
            family_id=C9_FAMILY_ID,
            status=c9_3_status,
            operation_contract_refs=C9_3_OPERATION_CONTRACT_REFS,
            handler_binding_digest=c9_3_binding_digest,
            required_wiring=c9_3_required_wiring,
            note=c9_3_note,
        ),
    )
    c9_3_wiring_tuple = (c9_3_wiring,)
    rollback_bindings = (
        RollbackBindingDeclaration(
            cell_id="C9.1",
            status="PRESENT",
            binding_refs=(C9_ROLLBACK_REF,),
        ),
        RollbackBindingDeclaration(
            cell_id="C9.2",
            status="PRESENT",
            binding_refs=C9_2_ROLLBACK_PATHS,
            note=(
                "C9.2 frontend typed contract rollback binding present: "
                "frontend-modern implementation, e2e specs and frontend "
                "milestone evidence"
            ),
        ),
        RollbackBindingDeclaration(
            cell_id="C9.3",
            status="PRESENT",
            binding_refs=(C9_ROLLBACK_REF,),
        ),
    )
    return FamilyAssembly(
        family_id=C9_FAMILY_ID,
        cells=cells,
        handlers=tuple(handlers),
        kernel_wiring=(C9_2_KERNEL_WIRING,),
        projector_wiring=c9_3_wiring_tuple,
        projector_registry=c9_3_registry,
        rollback_bindings=rollback_bindings,
    )


__all__ = [
    "C9_1_OPERATION_CONTRACT_REFS",
    "C9_2_OPERATION_CONTRACT_REFS",
    "C9_2_KERNEL_ID",
    "C9_2_KERNEL_VERSION",
    "C9_2_KERNEL_WIRING",
    "C9_2_REQUIRED_WIRING",
    "C9_2_ROLLBACK_PATHS",
    "C9_3_DECLARED_LOSS",
    "C9_3_OPERATION_CONTRACT_REFS",
    "C9_FAMILY_ID",
    "C9_ROLLBACK_REF",
    "C9_1FacadeValidationRouteHandler",
    "build_c9_assembly",
    "build_deterministic_facade_closure",
    "build_deterministic_facade_validation_query",
]
