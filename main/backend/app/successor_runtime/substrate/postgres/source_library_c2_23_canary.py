"""Family-local RuntimeNode canary handlers for C2.2 -> C2.3.

This module is the disposable-PG canary realization only: it never runs a live
provider, credential resolver, network call or canonical write.  C2.2 plans
are produced by the pure planner; C2.3 effects are executed by a deterministic
fixture gateway with a scripted receipt, and OUTCOME_UNKNOWN is converged by a
readback-only RECONCILE handler that never re-executes the effect.
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa

from app.successor_runtime.capabilities import source_library_c2_2 as c22
from app.successor_runtime.capabilities import source_library_c2_2_interpreters as c22i
from app.successor_runtime.capabilities import source_library_c2_2_program as c22p
from app.successor_runtime.capabilities import source_library_c2_3 as c23
from app.successor_runtime.capabilities import (
    source_library_c2_3_test_interpreters as c23_fixtures,
)
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
    sha256_hex,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    OperationContractResolver,
)
from app.successor_runtime.language.program import ProgramSpec, atom_node
from app.successor_runtime.runtime.assignments import (
    InterpreterBinding,
    RecoveryBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    OutcomeUncertain,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    ReconciliationHandlerOutcome,
    ReconciliationResult,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    _one_mapping,
    _table,
)
from app.successor_runtime.substrate.postgres.session import (
    ProjectScopeStale,
    ServerProjectScopeResolver,
)

__all__ = [
    "PAYLOAD_PUT_REVISION",
    "PAYLOAD_VALUE_INCARNATION",
    "PAYLOAD_VALUE_REVISION",
    "C2_2PlannerHandler",
    "C2_2StoreRehydratedHandler",
    "C2_3FixtureProviderEffectHandler",
    "C2_3ReconcileHandler",
    "C2_3StoreRehydratedHandler",
    "build_c2_3_fixture_program",
    "build_c2_3_payload_value_ref",
    "build_legacy_c2_2_binding",
    "build_legacy_c2_3_binding",
    "build_recovery_c2_3_binding",
    "build_successor_c2_2_binding",
    "build_successor_c2_3_binding",
]


def build_successor_c2_2_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    interpreter_digest = (
        c22.build_source_library_c2_2_bundle().profiles["interpreter"].profile_digest
    )
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=interpreter_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=c22i.successor_planning_interpreter_profile_digest(),
    )


def build_successor_c2_3_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    interpreter_digest = (
        c23.build_source_library_c2_3_bundle().profiles["interpreter"].profile_digest
    )
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=interpreter_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=interpreter_digest,
    )


def build_recovery_c2_3_binding(
    *,
    interpreter_profile_digest: str,
) -> RecoveryBinding:
    return RecoveryBinding.from_content(
        recovery_handler_id="recovery.source_library.c2_3.fixture_readback.v1",
        recovery_handler_version="1",
        interpreter_profile_digest=interpreter_profile_digest,
        authoritative_readback_profile_ref=(
            "mrw.successor.source-library.c2-3.readback.v1"
        ),
    )


def build_c2_3_payload_value_ref(
    request: c23.ProviderEffectRequest,
    *,
    program_id: str,
    project_key: str,
) -> ValueRef:
    exact_text = canonical_json(request.to_plain())
    exact_bytes = exact_text.encode("utf-8")
    content_digest_hex = sha256_hex(exact_bytes)
    value_id = f"{program_id}:payload:c2-3"
    provenance_digest = content_digest(
        {
            "schema": "mrw.successor.source-library.c2-3.payload-provenance.v1",
            "program_id": program_id,
            "project_key": project_key,
            "request_digest": request.request_digest,
            "content_digest": content_digest_hex,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=c23.SOURCE_LIBRARY_C2_3_PAYLOAD_TYPE,
        codec_id=c23.SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID,
        content_digest=content_digest_hex,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def build_c2_3_fixture_program(
    *,
    request: c23.ProviderEffectRequest,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> ProgramSpec:
    ref = catalog.lookup(c23.SOURCE_LIBRARY_C2_3_KIND)
    if ref is None:
        raise ValueError(
            f"contract {c23.SOURCE_LIBRARY_C2_3_KIND} missing from catalog"
        )
    value_ref = build_c2_3_payload_value_ref(
        request, program_id=program_id, project_key=project_key
    )
    operation = OperationSpec(
        operation_id=c23.SOURCE_LIBRARY_C2_3_OPERATION_ID,
        contract_ref=ref,
        input_refs=(value_ref,),
        payload_ref=value_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=c23.SOURCE_LIBRARY_C2_3_PAYLOAD_TYPE,
        output_type=c23.SOURCE_LIBRARY_C2_3_OUTCOME_TYPE,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.successor.source-library.c2-3.program-metadata.v1",
            "operation_kind": c23.SOURCE_LIBRARY_C2_3_KIND,
            "project_registry_revision": project_registry_revision,
            "resolved_schema": request.project_scope.resolved_schema,
            "project_scope_incarnation": request.project_scope.incarnation,
            "project_scope_digest": project_scope_digest,
            "request_digest": request.request_digest,
            "catalog_revision": request.catalog_revision,
            "catalog_incarnation": request.catalog_incarnation,
            "catalog_digest": request.catalog_digest,
            "payload_value_id": value_ref.value_id,
            "payload_storage_ref": value_ref.storage_ref,
            "payload_content_digest": value_ref.content_digest,
            "payload_provenance_digest": value_ref.provenance_digest,
            "canonical_owner": c23.SOURCE_LIBRARY_C2_3_OWNER,
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity="source-library.execute-provider-effect",
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(),
        observation_profile=c23.SOURCE_PROVIDER_EFFECT_OBSERVATION_PROFILE,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def compile_c2_3_fixture_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver,
) -> Any:
    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )


class _ExactBindingHandler:
    def _require_exact(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> None:
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
        ):
            raise DefiniteInterpreterFailure("EXACT_C2_HANDLER_BINDING_DRIFT")
        if assignment.deployment_catalog_digest != self.deployment_catalog_digest:
            raise DefiniteInterpreterFailure("EXACT_C2_DEPLOYMENT_CATALOG_DRIFT")


class C2_2PlannerHandler(_ExactBindingHandler, RuntimeHandler):
    """Exact installed realization of the pure C2.2 planner atom."""

    def __init__(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: OperationContractRef,
        payload_ref: ValueRef,
        payload: c22.SourceModePlanningPayload,
        catalog: OperationContractCatalogSnapshot,
        binding: InterpreterBinding,
        deployment_catalog_digest: str,
    ) -> None:
        self.program = program
        self.plan = plan
        self.contract_ref = contract_ref
        self.payload_ref = payload_ref
        self.payload = payload
        self.catalog = catalog
        self.binding = binding
        self.deployment_catalog_digest = deployment_catalog_digest
        self.handler_binding_digest = binding.binding_digest
        self.interpreter_profile_digest = binding.interpreter_profile_digest
        self.operation_contract_digest = contract_ref.contract_digest
        self.provider_calls = 0

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        self._require_exact(assignment, claim)
        result = c22i.SourceLibraryC2_2SuccessorInterpreter().interpret(
            self.payload,
            program=self.program,
            plan=self.plan,
            contract_ref=self.contract_ref,
            payload_ref=self.payload_ref,
            project_scope=self.payload.project_scope,
            catalog=self.catalog,
            deployment_catalog_digest=self.deployment_catalog_digest,
            binding=self.binding,
            expected_interpreter_profile_digest=self.interpreter_profile_digest,
        )
        if isinstance(result, c22i.InterpreterFailure):
            raise DefiniteInterpreterFailure(result.code)
        return InterpreterOutcome.succeeded(
            result.value.plan_digest,
            receipt_ref=f"receipt:sha256:{result.value.plan_digest}",
        )


class C2_3FixtureProviderEffectHandler(_ExactBindingHandler, RuntimeHandler):
    """Deterministic fixture/receipt-only C2.3 provider effect handler."""

    def __init__(
        self,
        *,
        requests_by_run: dict[str, c23.ProviderEffectRequest],
        binding: InterpreterBinding,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
        gateway: c23_fixtures.FixtureProviderEffectGateway,
    ) -> None:
        self.requests_by_run = requests_by_run
        self.binding = binding
        self.operation_contract_digest = operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest
        self.gateway = gateway
        self.handler_binding_digest = binding.binding_digest
        self.interpreter_profile_digest = binding.interpreter_profile_digest
        self.fixture_calls: list[str] = []
        self.real_provider_calls = 0

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        self._require_exact(assignment, claim)
        request = self.requests_by_run[assignment.run_id]
        outcome = self.gateway.execute(request, {"authority": "c2-3-canary"})
        self.fixture_calls.append(request.request_id)
        if isinstance(
            outcome, (c23.CompletedProviderEffect, c23.AcceptedProviderEffect)
        ):
            return InterpreterOutcome.succeeded(
                outcome.outcome_digest,
                receipt_ref=f"receipt:sha256:{outcome.outcome_digest}",
            )
        if isinstance(outcome, c23.OutcomeUnknownProviderEffect):
            raise OutcomeUncertain("C2_3_READBACK_REQUIRED")
        if isinstance(outcome, (c23.RejectedProviderEffect, c23.FailedProviderEffect)):
            raise DefiniteInterpreterFailure(outcome.code)
        raise DefiniteInterpreterFailure("UNSUPPORTED_FIXTURE_OUTCOME")


class C2_3ReconcileHandler(_ExactBindingHandler, RuntimeHandler):
    """Readback-only RECONCILE handler; never re-executes the provider effect."""

    def __init__(
        self,
        *,
        request: c23.ProviderEffectRequest,
        binding: RecoveryBinding,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
        readback: c23_fixtures.FixtureProviderReadbackPort,
        observed_at: str = "2030-09-01T08:00:00Z",
    ) -> None:
        self.request = request
        self.binding = binding
        self.operation_contract_digest = operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest
        self.readback = readback
        self.observed_at = observed_at
        self.handler_binding_digest = binding.binding_digest
        self.interpreter_profile_digest = binding.interpreter_profile_digest
        self.readback_calls: list[str] = []
        self.execute_calls: list[str] = []

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> ReconciliationHandlerOutcome:
        self._require_exact(assignment, claim)
        target = assignment.reconciliation_attempt_id
        if not target:
            raise DefiniteInterpreterFailure("RECONCILE_TARGET_ATTEMPT_MISSING")
        attempt = c23.ProviderAttemptRef(
            attempt_id=target,
            request_digest=self.request.request_digest,
            provider=self.request.provider,
            epoch=1,
        )
        readback_result = self.readback.readback(attempt, self.request)
        self.readback_calls.append(target)
        if not isinstance(readback_result, c23.ReadbackTerminal):
            raise DefiniteInterpreterFailure("C2_3_READBACK_NOT_TERMINAL")
        readback = readback_result.readback
        if readback.attempt_ref != target:
            raise DefiniteInterpreterFailure("C2_3_READBACK_ATTEMPT_MISMATCH")
        if readback.terminal_status == "COMPLETED":
            authoritative = AuthoritativeEffectReadback(
                attempt_id=target,
                disposition=EffectDisposition.SUCCEEDED,
                provider_locator=f"fixture:provider:{self.request.provider}",
                receipt_digest=readback.readback_digest,
                observation_digest=readback.readback_digest,
            )
            result = ReconciliationResult(
                state=ReconciliationState.RESOLVED,
                attempt_id=target,
                disposition=EffectDisposition.SUCCEEDED,
                readback=authoritative,
                non_start_proof=None,
                wait_reason=None,
            )
            return ReconciliationHandlerOutcome(
                result=result,
                output_digest=readback.readback_digest,
                receipt_ref=f"receipt:sha256:{readback.readback_digest}",
            )
        if readback.terminal_status == "FAILED":
            authoritative = AuthoritativeEffectReadback(
                attempt_id=target,
                disposition=EffectDisposition.FAILED,
                provider_locator=f"fixture:provider:{self.request.provider}",
                failure_digest=readback.readback_digest,
                observation_digest=readback.readback_digest,
            )
            result = ReconciliationResult(
                state=ReconciliationState.RESOLVED,
                attempt_id=target,
                disposition=EffectDisposition.FAILED,
                readback=authoritative,
                non_start_proof=None,
                wait_reason=None,
            )
            return ReconciliationHandlerOutcome(
                result=result,
                output_digest=None,
                receipt_ref=None,
            )
        raise DefiniteInterpreterFailure("C2_3_READBACK_NOT_TERMINAL")


PAYLOAD_PUT_REVISION = 0
PAYLOAD_VALUE_REVISION = 1
PAYLOAD_VALUE_INCARNATION = "payload-inc:p3-c2-23"


def build_legacy_c2_2_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    interpreter_digest = content_digest(
        {
            "interpreter_id": "legacy.source_library.c2_2.four_modes.v1",
            "version": "1.0.0",
            "boundary": "sibling fixture replay only",
        }
    )
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=interpreter_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=interpreter_digest,
    )


def build_legacy_c2_3_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    interpreter_digest = content_digest(
        {
            "interpreter_id": "legacy.source_library.c2_3.provider_effect.v1",
            "version": "1.0.0",
            "boundary": "donor fixture readback only",
        }
    )
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=interpreter_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=interpreter_digest,
    )


class _StoreRehydratedBase:
    """Shared exact store-rehydration loader; no constructor fixture closure."""

    def __init__(
        self,
        *,
        uow_factory: Any,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
    ) -> None:
        require_hex64(handler_binding_digest, "handler binding digest")
        require_hex64(interpreter_profile_digest, "interpreter profile digest")
        require_hex64(operation_contract_digest, "operation contract digest")
        require_hex64(deployment_catalog_digest, "deployment catalog digest")
        self.uow_factory = uow_factory
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.operation_contract_digest = operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest

    def _require_exact(
        self, assignment: RuntimeAssignment, claim: ClaimBinding
    ) -> None:
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
        ):
            raise DefiniteInterpreterFailure("EXACT_C2_HANDLER_BINDING_DRIFT")
        if assignment.deployment_catalog_digest != self.deployment_catalog_digest:
            raise DefiniteInterpreterFailure("EXACT_C2_DEPLOYMENT_CATALOG_DRIFT")

    def _load_run(self, connection: Any, assignment: RuntimeAssignment) -> Any:
        runs = _table("runtime_runs")
        run = _one_mapping(
            connection.execute(
                sa.select(runs).where(
                    runs.c.project_key == assignment.project_key,
                    runs.c.run_id == assignment.run_id,
                )
            )
        )
        if run is None:
            raise RecordNotFound(f"runtime run absent: {assignment.run_id}")
        if (
            run["incarnation"] != assignment.incarnation
            or run["program_digest"] != assignment.program_digest
            or run["plan_digest"] != assignment.plan_digest
            or int(run["execution_epoch"]) != assignment.execution_epoch
        ):
            raise ExactBindingConflict("runtime run exact identity drift")
        return run

    def _resolve_scope(self, connection: Any, run: Any, actor_id: str) -> Any:
        resolver = ServerProjectScopeResolver(connection=connection)
        expected = resolver.resolve_expected(
            str(run["project_key"]),
            int(run["project_registry_revision"]),
            str(run["project_scope_digest"]),
        )
        if isinstance(expected, ProjectScopeStale):
            raise ExactBindingConflict("runtime run project scope is stale")
        from app.successor_runtime.runtime.ports import RuntimeScope

        return RuntimeScope(project_scope=expected, actor_id=actor_id)

    def _program_ref(self, connection: Any, assignment: RuntimeAssignment) -> Any:
        refs = _table("runtime_program_refs")
        row = _one_mapping(
            connection.execute(
                sa.select(refs).where(
                    refs.c.project_key == assignment.project_key,
                    refs.c.program_digest == assignment.program_digest,
                )
            )
        )
        if row is None:
            raise RecordNotFound("exact public Program ref not found")
        return row

    def _load_program(
        self,
        connection: Any,
        tables: Any,
        scope: Any,
        assignment: RuntimeAssignment,
        program_ref: Any,
    ) -> ProgramSpec:
        return ProgramRepository(connection, tables).get(
            scope.project_scope,
            str(program_ref["program_id"]),
            expected_digest=assignment.program_digest,
        )

    def _load_plan(
        self, connection: Any, tables: Any, scope: Any, assignment: RuntimeAssignment
    ) -> Any:
        assert assignment.plan_digest is not None
        return PlanRepository(connection, tables).get(
            scope.project_scope, assignment.plan_digest
        )

    def _load_payload_bytes(
        self,
        connection: Any,
        tables: Any,
        scope: Any,
        assignment: RuntimeAssignment,
        *,
        value_id: str,
    ) -> bytes:
        assert assignment.payload_digest is not None
        row = _one_mapping(
            connection.execute(
                sa.select(tables.successor_values).where(
                    tables.successor_values.c.project_key
                    == scope.project_scope.project_key,
                    tables.successor_values.c.value_id == value_id,
                    tables.successor_values.c.revision == PAYLOAD_VALUE_REVISION,
                    tables.successor_values.c.incarnation == PAYLOAD_VALUE_INCARNATION,
                )
            )
        )
        if row is None:
            raise RecordNotFound(
                f"payload row absent: value_id={value_id} "
                f"revision={PAYLOAD_VALUE_REVISION} "
                f"incarnation={PAYLOAD_VALUE_INCARNATION}"
            )
        stored = row["content_bytes"]
        if stored is None:
            stored = canonical_json(row["content_json"]).encode("utf-8")
        else:
            stored = bytes(stored)
        return stored


class C2_2StoreRehydratedHandler(_StoreRehydratedBase, RuntimeHandler):
    """C2.2 planner handler that reloads Program/Plan/payload from stores."""

    def __init__(
        self,
        *,
        uow_factory: Any,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
    ) -> None:
        super().__init__(
            uow_factory=uow_factory,
            handler_binding_digest=handler_binding_digest,
            interpreter_profile_digest=interpreter_profile_digest,
            operation_contract_digest=operation_contract_digest,
            deployment_catalog_digest=deployment_catalog_digest,
        )
        self.provider_calls = 0

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        self._require_exact(assignment, claim)
        try:
            with self.uow_factory() as uow:
                connection = uow.connection
                run = self._load_run(connection, assignment)
                scope = self._resolve_scope(connection, run, context.node.node_id)
                tables = project_tables(
                    sa.MetaData(), scope.project_scope.resolved_schema
                )
                program_ref = self._program_ref(connection, assignment)
                program = self._load_program(
                    connection, tables, scope, assignment, program_ref
                )
                plan = self._load_plan(connection, tables, scope, assignment)
                if (
                    plan.program_digest != program.program_digest
                    or plan.program_id != program.program_id
                ):
                    raise DefiniteInterpreterFailure(
                        "C2_2_PLAN_PROGRAM_BINDING_MISMATCH"
                    )
                payload_bytes = self._load_payload_bytes(
                    connection,
                    tables,
                    scope,
                    assignment,
                    value_id=dict(program.metadata)["payload_value_id"],
                )
        except DefiniteInterpreterFailure:
            raise
        except Exception as exc:
            raise DefiniteInterpreterFailure(
                f"STORE_REHYDRATION_REJECTED:{type(exc).__name__}:{exc}"
            ) from exc
        from app.successor_runtime.capabilities import (
            source_library_c2_shared as _shared,
        )

        try:
            planning = _shared.source_mode_planning_payload_from_plain(
                json.loads(payload_bytes.decode("utf-8"))
            )
            if planning.payload_digest != assignment.payload_digest:
                raise DefiniteInterpreterFailure("C2_2_PAYLOAD_DIGEST_DRIFT")
            catalog = c22.build_source_library_c2_2_catalog(
                c22.build_source_library_c2_2_bundle()
            )
            contract_ref = catalog.lookup(planning.operation_kind)
            if contract_ref is None:
                raise DefiniteInterpreterFailure("C2_2_OPERATION_CONTRACT_MISSING")
            payload_ref = c22p.planning_payload_value_ref(
                planning,
                program_id=program.program_id,
                project_key=assignment.project_key,
            )
            result = c22i.SourceLibraryC2_2SuccessorInterpreter().interpret(
                planning,
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                project_scope=planning.project_scope,
                catalog=catalog,
                deployment_catalog_digest=self.deployment_catalog_digest,
                binding=assignment.handler_binding,
                expected_interpreter_profile_digest=self.interpreter_profile_digest,
            )
            if isinstance(result, c22i.InterpreterFailure):
                raise DefiniteInterpreterFailure(result.code)
        except DefiniteInterpreterFailure:
            raise
        except Exception as exc:
            raise DefiniteInterpreterFailure(
                f"C2_2_STORE_INTERPRET_REJECTED:{type(exc).__name__}:{exc}"
            ) from exc
        return InterpreterOutcome.succeeded(
            result.value.plan_digest,
            receipt_ref=f"receipt:sha256:{result.value.plan_digest}",
        )


class C2_3StoreRehydratedHandler(_StoreRehydratedBase, RuntimeHandler):
    """C2.3 provider-effect handler that reloads request/payload from stores."""

    def __init__(
        self,
        *,
        uow_factory: Any,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
        gateway: c23_fixtures.FixtureProviderEffectGateway,
    ) -> None:
        super().__init__(
            uow_factory=uow_factory,
            handler_binding_digest=handler_binding_digest,
            interpreter_profile_digest=interpreter_profile_digest,
            operation_contract_digest=operation_contract_digest,
            deployment_catalog_digest=deployment_catalog_digest,
        )
        self.gateway = gateway
        self.fixture_calls: list[str] = []
        self.real_provider_calls = 0

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        self._require_exact(assignment, claim)
        try:
            with self.uow_factory() as uow:
                connection = uow.connection
                run = self._load_run(connection, assignment)
                scope = self._resolve_scope(connection, run, context.node.node_id)
                tables = project_tables(
                    sa.MetaData(), scope.project_scope.resolved_schema
                )
                program_ref = self._program_ref(connection, assignment)
                program = self._load_program(
                    connection, tables, scope, assignment, program_ref
                )
                self._load_plan(connection, tables, scope, assignment)
                payload_bytes = self._load_payload_bytes(
                    connection,
                    tables,
                    scope,
                    assignment,
                    value_id=dict(program.metadata)["payload_value_id"],
                )
                request = c23.provider_effect_request_from_plain(
                    json.loads(payload_bytes.decode("utf-8"))
                )
        except DefiniteInterpreterFailure:
            raise
        except Exception as exc:
            raise DefiniteInterpreterFailure(
                f"STORE_REHYDRATION_REJECTED:{type(exc).__name__}:{exc}"
            ) from exc
        if request.request_digest != assignment.payload_digest:
            raise DefiniteInterpreterFailure("C2_3_REQUEST_DIGEST_DRIFT")
        outcome = self.gateway.execute(request, {"authority": "c2-3-canary"})
        self.fixture_calls.append(request.request_id)
        if isinstance(
            outcome, (c23.CompletedProviderEffect, c23.AcceptedProviderEffect)
        ):
            return InterpreterOutcome.succeeded(
                outcome.outcome_digest,
                receipt_ref=f"receipt:sha256:{outcome.outcome_digest}",
            )
        if isinstance(outcome, c23.OutcomeUnknownProviderEffect):
            raise OutcomeUncertain("C2_3_READBACK_REQUIRED")
        if isinstance(outcome, (c23.RejectedProviderEffect, c23.FailedProviderEffect)):
            raise DefiniteInterpreterFailure(outcome.code)
        raise DefiniteInterpreterFailure("UNSUPPORTED_FIXTURE_OUTCOME")
