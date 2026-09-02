"""Restartable store-rehydrated RuntimeHandler for the frozen C2.1 resolve atom.

The local canary handler captured Program/Plan/payload objects at construction.
This production-shape handler captures no run fixture: every ``execute`` opens
a fresh read-only unit of work, re-resolves the current project scope from the
public registry, reloads the exact canonical Program, ExecutionPlan and payload
bytes from the project stores, revalidates operation/deployment catalog and
payload codec identities, checks the frozen resource ceiling, and only then
invokes the pure successor interpreter.  There is no legacy service, provider,
network, credential or fixture-closure fallback.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, NoReturn

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities import source_library_c2_1 as c2_1
from app.successor_runtime.capabilities.checksum import (
    canonical_json as checksum_canonical_json,
)
from app.successor_runtime.capabilities.checksum import (
    content_digest as checksum_content_digest,
)
from app.successor_runtime.capabilities.source_library_c2_1 import (
    build_source_library_c2_1_bundle,
    build_source_library_c2_1_catalog,
)
from app.successor_runtime.capabilities.source_library_c2_1_interpreters import (
    InterpreterFailure,
    SourceLibraryC2_1SuccessorInterpreter,
    require_resource_ceiling,
)
from app.successor_runtime.capabilities.source_library_c2_1_program import (
    exact_contract_ref,
    payload_value_ref,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    RuntimeAssignment,
    require_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.nodes import DeploymentCatalogRepository
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.research_ledger import (
    ExactContentConflict,
    ProjectRecordNotFound,
    ProjectScopeMismatch,
)
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
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork
from app.successor_runtime.substrate.postgres.values import (
    ValueRepository,
    derive_value_write_intent_digest,
)

C2_1_ASSIGNMENT_BINDING_MISSING = "C2_1_ASSIGNMENT_BINDING_MISSING"
C2_1_RUN_STORE_DRIFT = "C2_1_RUN_STORE_DRIFT"
C2_1_SCOPE_REHYDRATION_DRIFT = "C2_1_SCOPE_REHYDRATION_DRIFT"
C2_1_PROGRAM_STORE_DRIFT = "C2_1_PROGRAM_STORE_DRIFT"
C2_1_PLAN_STORE_DRIFT = "C2_1_PLAN_STORE_DRIFT"
C2_1_OPERATION_CATALOG_DRIFT = "C2_1_OPERATION_CATALOG_DRIFT"
C2_1_DEPLOYMENT_CATALOG_DRIFT = "C2_1_DEPLOYMENT_CATALOG_DRIFT"
C2_1_PAYLOAD_STORE_DRIFT = "C2_1_PAYLOAD_STORE_DRIFT"
C2_1_PAYLOAD_CODEC_DRIFT = "C2_1_PAYLOAD_CODEC_DRIFT"
C2_1_STORE_REHYDRATION_REJECTED = "C2_1_STORE_REHYDRATION_REJECTED"

_PAYLOAD_VALUE_ID_SUFFIX = ":payload:c2-1"
_PAYLOAD_VALUE_IDENTITY_SCHEMA = (
    "mrw.successor.source-library.c2-1.payload-value-identity.v1"
)
_C2_1_EXPECTED_VALUE_REVISION = 1
_PAYLOAD_IDENTITY_METADATA_FIELDS = (
    "payload_value_id",
    "payload_storage_ref",
    "payload_content_digest",
    "payload_provenance_digest",
    "project_registry_revision",
    "resolved_schema",
    "project_scope_incarnation",
    "project_scope_digest",
    "catalog_revision",
    "catalog_incarnation",
    "catalog_digest",
    "item_revision",
    "item_incarnation",
    "item_content_digest",
)


def _reject(code: str, exc: BaseException) -> NoReturn:
    raise DefiniteInterpreterFailure(code) from exc


@dataclass(frozen=True, slots=True)
class _LoadedClosure:
    program: ProgramSpec
    plan: ExecutionPlan
    contract_ref: Any
    payload_ref: ValueRef
    payload: c2_1.SourceResolutionPayload
    catalog: OperationContractCatalogSnapshot
    project_scope: ProjectScopeRef


@dataclass(frozen=True, slots=True)
class C2_1PayloadValueIdentity:
    """Immutable closure-derived identity of the exact C2.1 payload value."""

    program_id: str
    project_key: str
    value_id: str
    storage_ref: str
    object_type: str
    codec_id: str
    content_digest: str
    provenance_digest: str
    revision: int
    incarnation: str
    identity_digest: str
    write_intent_digest: str
    provenance: dict[str, Any]


def c2_1_expected_payload_value_identity(
    program: ProgramSpec,
) -> C2_1PayloadValueIdentity:
    """Derive the exact payload-value identity from the immutable Program.

    The expected revision, incarnation, write-intent digest and provenance
    digest are never read from the mutable successor_values row.  They are
    computed from the persisted canonical Program metadata and the payload
    ValueRef closure so any row-level rewrite (including ABA back to a row
    with a different generation) fails closed.
    """

    metadata = dict(program.metadata or {})
    missing = [
        name for name in _PAYLOAD_IDENTITY_METADATA_FIELDS if name not in metadata
    ]
    if missing:
        raise ValueError(
            "C2.1 Program metadata lacks payload identity fields: " + ", ".join(missing)
        )
    program_id = program.program_id
    project_key = program.project_key
    value_id = str(metadata["payload_value_id"])
    expected_value_id = f"{program_id}{_PAYLOAD_VALUE_ID_SUFFIX}"
    storage_ref = str(metadata["payload_storage_ref"])
    content_digest_hex = str(metadata["payload_content_digest"])
    provenance_digest_hex = str(metadata["payload_provenance_digest"])
    if value_id != expected_value_id:
        raise ValueError("Program payload_value_id does not match canonical identity")
    require_digest(content_digest_hex, "payload_content_digest")
    require_digest(provenance_digest_hex, "payload_provenance_digest")
    provenance: dict[str, Any] = {
        "schema": "mrw.successor.source-library.c2-1.payload-provenance.v1",
        "program_id": program_id,
        "project_key": project_key,
        "project_registry_revision": metadata["project_registry_revision"],
        "resolved_schema": metadata["resolved_schema"],
        "project_scope_incarnation": metadata["project_scope_incarnation"],
        "project_scope_digest": metadata["project_scope_digest"],
        "catalog_revision": metadata["catalog_revision"],
        "catalog_incarnation": metadata["catalog_incarnation"],
        "catalog_digest": metadata["catalog_digest"],
        "item_revision": metadata["item_revision"],
        "item_incarnation": metadata["item_incarnation"],
        "item_content_digest": metadata["item_content_digest"],
        "content_digest": content_digest_hex,
    }
    if checksum_content_digest(provenance) != provenance_digest_hex:
        raise ValueError("Program payload provenance digest drift")
    identity_digest = checksum_content_digest(
        {
            "schema": _PAYLOAD_VALUE_IDENTITY_SCHEMA,
            "program_id": program_id,
            "project_key": project_key,
            "value_id": value_id,
            "content_digest": content_digest_hex,
            "provenance_digest": provenance_digest_hex,
        }
    )
    incarnation = f"payload-inc:{identity_digest}"
    write_intent_digest = derive_value_write_intent_digest(
        project_key=project_key,
        value_id=value_id,
        object_type=c2_1.SOURCE_LIBRARY_C2_1_PAYLOAD_TYPE.type_id,
        codec_id=c2_1.SOURCE_LIBRARY_C2_1_PAYLOAD_CODEC_ID,
        content_digest=content_digest_hex,
        provenance_digest=provenance_digest_hex,
        source_ref=storage_ref,
        expected_revision=0,
        expected_incarnation=incarnation,
        state="AVAILABLE",
    )
    return C2_1PayloadValueIdentity(
        program_id=program_id,
        project_key=project_key,
        value_id=value_id,
        storage_ref=storage_ref,
        object_type=c2_1.SOURCE_LIBRARY_C2_1_PAYLOAD_TYPE.type_id,
        codec_id=c2_1.SOURCE_LIBRARY_C2_1_PAYLOAD_CODEC_ID,
        content_digest=content_digest_hex,
        provenance_digest=provenance_digest_hex,
        revision=_C2_1_EXPECTED_VALUE_REVISION,
        incarnation=incarnation,
        identity_digest=identity_digest,
        write_intent_digest=write_intent_digest,
        provenance=provenance,
    )


class SourceLibraryC2_1StoreRehydratedHandler(RuntimeHandler):
    """Exact installed realization that rehydrates every run from stores.

    The constructor accepts only immutable deployment facts and a fresh-UoW
    factory.  No Program, Plan, payload, catalog or binding object is captured;
    ``execute`` reloads them from the public registry/refs and the exact
    project stores on every call.
    """

    def __init__(
        self,
        *,
        uow_factory: Callable[[], RuntimeUnitOfWork],
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
    ) -> None:
        require_digest(
            handler_binding_digest,
            "C2.1 store handler binding digest",
        )
        require_digest(
            interpreter_profile_digest,
            "C2.1 store interpreter profile digest",
        )
        require_digest(
            operation_contract_digest,
            "C2.1 store operation contract digest",
        )
        require_digest(
            deployment_catalog_digest,
            "C2.1 store deployment catalog digest",
        )
        self.uow_factory = uow_factory
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.operation_contract_digest = operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest
        self.provider_calls = 0

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        if claim.assignment_digest != assignment.assignment_digest:
            raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
        if claim.claim_authority_epoch != assignment.claim_authority_epoch:
            raise DefiniteInterpreterFailure("CLAIM_AUTHORITY_EPOCH_DRIFT")
        if (
            assignment.handler_binding_digest != self.handler_binding_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
        ):
            raise DefiniteInterpreterFailure("EXACT_C2_1_HANDLER_BINDING_DRIFT")
        if assignment.deployment_catalog_digest != self.deployment_catalog_digest:
            raise DefiniteInterpreterFailure("EXACT_C2_1_DEPLOYMENT_CATALOG_DRIFT")

        loaded = self._load_exact_closure(assignment, context.node.node_id)
        ceiling_rejection = require_resource_ceiling(loaded.payload)
        if ceiling_rejection is not None:
            raise DefiniteInterpreterFailure("RESOURCE_CEILING_EXCEEDED")

        outcome = SourceLibraryC2_1SuccessorInterpreter().interpret(
            program=loaded.program,
            plan=loaded.plan,
            contract_ref=loaded.contract_ref,
            payload_ref=loaded.payload_ref,
            payload=loaded.payload,
            project_scope=loaded.payload.project_scope,
            catalog=loaded.catalog,
            deployment_catalog_digest=self.deployment_catalog_digest,
            binding=assignment.handler_binding,
        )
        if isinstance(outcome, InterpreterFailure):
            raise DefiniteInterpreterFailure(outcome.code)
        return InterpreterOutcome.succeeded(outcome.value.observation_digest)

    def _load_exact_closure(
        self,
        assignment: RuntimeAssignment,
        actor_id: str,
    ) -> _LoadedClosure:
        if (
            assignment.assignment_kind is not AssignmentKind.INTERPRET
            or assignment.step_role is not CompiledStepRole.EFFECT
            or assignment.operation_contract_ref is None
            or assignment.plan_digest is None
            or assignment.payload_ref is None
            or assignment.payload_digest is None
        ):
            raise DefiniteInterpreterFailure(C2_1_ASSIGNMENT_BINDING_MISSING)
        try:
            with self.uow_factory() as uow:
                connection = uow.connection
                run = self._load_run(connection, assignment)
                scope = self._resolve_scope(
                    connection,
                    run,
                    assignment,
                    actor_id=actor_id,
                )
                tables = project_tables(
                    sa.MetaData(),
                    scope.project_scope.resolved_schema,
                )
                program_ref = self._program_ref(connection, assignment)
                program = self._load_program(
                    connection,
                    tables,
                    scope,
                    assignment,
                    program_ref,
                )
                try:
                    payload_identity = c2_1_expected_payload_value_identity(program)
                except ValueError as exc:
                    _reject(C2_1_PROGRAM_STORE_DRIFT, exc)
                self._require_assignment_payload_binding(
                    assignment,
                    payload_identity,
                )
                plan_ref = self._plan_ref(connection, run, assignment, program_ref)
                project_plan_row = self._project_plan_row(
                    connection,
                    tables,
                    assignment,
                    plan_ref,
                    program_ref,
                )
                plan = self._load_plan(
                    connection,
                    tables,
                    scope,
                    assignment,
                    plan_ref,
                    program_ref,
                )
                catalog, contract_ref, codec = self._installed_closure(plan_ref)
                self._require_operation_catalog(
                    plan_ref,
                    project_plan_row,
                    catalog,
                    contract_ref,
                    assignment,
                )
                runtime_value = self._runtime_value(
                    connection,
                    assignment,
                    payload_identity,
                )
                project_value = self._project_value(
                    connection,
                    tables,
                    payload_identity,
                    runtime_value,
                )
                payload_bytes = self._exact_payload_bytes(
                    connection,
                    tables,
                    scope,
                    project_value,
                    runtime_value,
                    payload_identity,
                )
                payload = self._decode_payload(codec, payload_bytes, assignment)
                payload_ref = self._rebuild_payload_ref(
                    payload,
                    runtime_value,
                    project_value,
                    payload_identity,
                )
                self._require_payload_scope(payload, scope)
                self._require_deployment_catalog(connection, assignment)
                return _LoadedClosure(
                    program=program,
                    plan=plan,
                    contract_ref=contract_ref,
                    payload_ref=payload_ref,
                    payload=payload,
                    catalog=catalog,
                    project_scope=scope.project_scope,
                )
        except DefiniteInterpreterFailure:
            raise
        except Exception as exc:
            raise DefiniteInterpreterFailure(C2_1_STORE_REHYDRATION_REJECTED) from exc

    def _load_run(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
    ) -> Mapping[str, Any]:
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
            _reject(
                C2_1_RUN_STORE_DRIFT,
                RecordNotFound(f"runtime run absent: {assignment.run_id}"),
            )
        if (
            run["incarnation"] != assignment.incarnation
            or run["program_digest"] != assignment.program_digest
            or run["plan_digest"] != assignment.plan_digest
            or int(run["execution_epoch"]) != assignment.execution_epoch
            or run["plan_id"] is None
        ):
            _reject(
                C2_1_RUN_STORE_DRIFT,
                ExactBindingConflict("runtime run exact identity drift"),
            )
        return run

    def _resolve_scope(
        self,
        connection: Connection,
        run: Mapping[str, Any],
        assignment: RuntimeAssignment,
        *,
        actor_id: str,
    ) -> RuntimeScope:
        try:
            resolver = ServerProjectScopeResolver(connection=connection)
            expected = resolver.resolve_expected(
                assignment.project_key,
                int(run["project_registry_revision"]),
                str(run["project_scope_digest"]),
            )
            if isinstance(expected, ProjectScopeStale):
                raise ExactBindingConflict("runtime run project scope is stale")
            current = resolver.resolve(assignment.project_key)
            if current != expected or current.resolved_schema != run["resolved_schema"]:
                raise ExactBindingConflict(
                    "runtime run project scope is no longer current"
                )
            return RuntimeScope(project_scope=current, actor_id=actor_id)
        except DefiniteInterpreterFailure:
            raise
        except Exception as exc:  # noqa: BLE001 - scope rehydration must fail closed
            _reject(C2_1_SCOPE_REHYDRATION_DRIFT, exc)

    def _program_ref(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
    ) -> Mapping[str, Any]:
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
            _reject(
                C2_1_PROGRAM_STORE_DRIFT,
                RecordNotFound("exact public Program ref not found"),
            )
        return row

    def _load_program(
        self,
        connection: Connection,
        tables: Any,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        program_ref: Mapping[str, Any],
    ) -> ProgramSpec:
        try:
            program = ProgramRepository(connection, tables).get(
                scope.project_scope,
                str(program_ref["program_id"]),
                expected_digest=assignment.program_digest,
            )
        except (
            ExactContentConflict,
            ProjectRecordNotFound,
            ProjectScopeMismatch,
        ) as exc:
            _reject(C2_1_PROGRAM_STORE_DRIFT, exc)
        if (
            program.program_id != program_ref["program_id"]
            or program.program_digest != assignment.program_digest
            or program.contract_version != program_ref["contract_version"]
            or program_ref["project_storage_ref"]
            != f"project-value:{program.program_id}"
        ):
            _reject(
                C2_1_PROGRAM_STORE_DRIFT,
                ExactBindingConflict("public Program ref identity drift"),
            )
        return program

    def _plan_ref(
        self,
        connection: Connection,
        run: Mapping[str, Any],
        assignment: RuntimeAssignment,
        program_ref: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        assert assignment.plan_digest is not None
        refs = _table("runtime_plan_refs")
        row = _one_mapping(
            connection.execute(
                sa.select(refs).where(
                    refs.c.project_key == assignment.project_key,
                    refs.c.plan_digest == assignment.plan_digest,
                )
            )
        )
        if row is None:
            _reject(
                C2_1_PLAN_STORE_DRIFT,
                RecordNotFound("exact public Plan ref not found"),
            )
        if (
            row["plan_id"] != run["plan_id"]
            or row["program_id"] != program_ref["program_id"]
            or row["program_digest"] != assignment.program_digest
        ):
            _reject(
                C2_1_PLAN_STORE_DRIFT,
                ExactBindingConflict("public Plan ref identity drift"),
            )
        return row

    def _project_plan_row(
        self,
        connection: Connection,
        tables: Any,
        assignment: RuntimeAssignment,
        plan_ref: Mapping[str, Any],
        program_ref: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        assert assignment.plan_digest is not None
        plans = tables.research_execution_plans
        row = _one_mapping(
            connection.execute(
                sa.select(plans).where(
                    plans.c.project_key == assignment.project_key,
                    plans.c.plan_digest == assignment.plan_digest,
                )
            )
        )
        if row is None:
            _reject(
                C2_1_PLAN_STORE_DRIFT,
                ProjectRecordNotFound("exact project Plan row not found"),
            )
        identity = {
            "plan_id": row["plan_id"],
            "program_id": row["program_id"],
            "program_digest": row["program_digest"],
            "operation_catalog_id": row["operation_catalog_id"],
            "catalog_version": row["catalog_version"],
            "catalog_digest": row["catalog_digest"],
            "effect_closure_digest": row["effect_closure_digest"],
            "authority_closure_digest": row["authority_closure_digest"],
            "resource_closure_digest": row["resource_closure_digest"],
        }
        expected = {
            "plan_id": plan_ref["plan_id"],
            "program_id": program_ref["program_id"],
            "program_digest": assignment.program_digest,
            "operation_catalog_id": plan_ref["operation_catalog_id"],
            "catalog_version": plan_ref["catalog_version"],
            "catalog_digest": plan_ref["catalog_digest"],
            "effect_closure_digest": plan_ref["effect_closure_digest"],
            "authority_closure_digest": plan_ref["authority_closure_digest"],
            "resource_closure_digest": plan_ref["resource_closure_digest"],
        }
        if identity != expected:
            _reject(
                C2_1_PLAN_STORE_DRIFT,
                ExactBindingConflict("project/public Plan identity drift"),
            )
        return row

    def _load_plan(
        self,
        connection: Connection,
        tables: Any,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        plan_ref: Mapping[str, Any],
        program_ref: Mapping[str, Any],
    ) -> ExecutionPlan:
        assert assignment.plan_digest is not None
        try:
            plan = PlanRepository(connection, tables).get(
                scope.project_scope,
                assignment.plan_digest,
            )
        except (ExactContentConflict, ProjectRecordNotFound) as exc:
            _reject(C2_1_PLAN_STORE_DRIFT, exc)
        if (
            plan.plan_id != plan_ref["plan_id"]
            or plan.plan_digest != assignment.plan_digest
            or plan.program_id != program_ref["program_id"]
            or plan.program_digest != assignment.program_digest
            or plan.effect_closure_digest != plan_ref["effect_closure_digest"]
            or plan.authority_closure_digest != plan_ref["authority_closure_digest"]
            or plan.resource_closure_digest != plan_ref["resource_closure_digest"]
        ):
            _reject(
                C2_1_PLAN_STORE_DRIFT,
                ExactBindingConflict("exact ExecutionPlan identity drift"),
            )
        return plan

    def _installed_closure(
        self,
        plan_ref: Mapping[str, Any],
    ) -> tuple[
        OperationContractCatalogSnapshot,
        Any,
        Any,
    ]:
        bundle = build_source_library_c2_1_bundle()
        catalog = build_source_library_c2_1_catalog(bundle)
        contract_ref = exact_contract_ref(catalog)
        codec = bundle.payload_codec()
        if (
            codec.codec_id != c2_1.SOURCE_LIBRARY_C2_1_PAYLOAD_CODEC_ID
            or catalog.catalog_id != plan_ref["operation_catalog_id"]
            or catalog.catalog_version != plan_ref["catalog_version"]
            or catalog.catalog_digest != plan_ref["catalog_digest"]
        ):
            _reject(
                C2_1_OPERATION_CATALOG_DRIFT,
                ExactBindingConflict("installed operation catalog identity drift"),
            )
        return catalog, contract_ref, codec

    def _require_operation_catalog(
        self,
        plan_ref: Mapping[str, Any],
        project_plan_row: Mapping[str, Any],
        catalog: OperationContractCatalogSnapshot,
        contract_ref: Any,
        assignment: RuntimeAssignment,
    ) -> None:
        op = assignment.operation_contract_ref
        if (
            op is None
            or op.kind != contract_ref.kind
            or op.contract_version != contract_ref.contract_version
            or op.contract_digest != contract_ref.contract_digest
            or assignment.operation_contract_digest != contract_ref.contract_digest
            or catalog.lookup(contract_ref) is None
            or catalog.lookup(contract_ref).contract_digest
            != contract_ref.contract_digest
        ):
            _reject(
                C2_1_OPERATION_CATALOG_DRIFT,
                ExactBindingConflict("operation contract identity drift"),
            )
        for row in (plan_ref, project_plan_row):
            if (
                row["operation_catalog_id"] != plan_ref["operation_catalog_id"]
                or row["catalog_version"] != plan_ref["catalog_version"]
                or row["catalog_digest"] != plan_ref["catalog_digest"]
            ):
                _reject(
                    C2_1_OPERATION_CATALOG_DRIFT,
                    ExactBindingConflict("operation catalog identity drift"),
                )

    def _runtime_value(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
        payload_identity: C2_1PayloadValueIdentity,
    ) -> Mapping[str, Any]:
        values = _table("runtime_values")
        row = _one_mapping(
            connection.execute(
                sa.select(values).where(
                    values.c.project_key == assignment.project_key,
                    values.c.project_value_ref == payload_identity.storage_ref,
                    values.c.content_digest == payload_identity.content_digest,
                )
            )
        )
        if row is None:
            _reject(
                C2_1_PAYLOAD_STORE_DRIFT,
                RecordNotFound("exact runtime payload value not found"),
            )
        if (
            row["value_id"] != payload_identity.value_id
            or row["object_type"] != payload_identity.object_type
            or row["content_digest"] != payload_identity.content_digest
            or row["project_value_ref"] != payload_identity.storage_ref
            or row["state"] != "AVAILABLE"
            or row["write_intent_digest"] != payload_identity.write_intent_digest
        ):
            _reject(
                C2_1_PAYLOAD_STORE_DRIFT,
                ExactBindingConflict(
                    "runtime payload value/ref/codec/write-intent drift"
                ),
            )
        if row["codec_id"] != payload_identity.codec_id:
            _reject(
                C2_1_PAYLOAD_CODEC_DRIFT,
                ExactBindingConflict("runtime payload codec drift"),
            )
        return row

    def _project_value(
        self,
        connection: Connection,
        tables: Any,
        payload_identity: C2_1PayloadValueIdentity,
        runtime_value: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        values = tables.successor_values
        row = _one_mapping(
            connection.execute(
                sa.select(values).where(
                    values.c.project_key == payload_identity.project_key,
                    values.c.value_id == payload_identity.value_id,
                    values.c.content_digest == payload_identity.content_digest,
                    values.c.codec_id == payload_identity.codec_id,
                )
            )
        )
        if row is None:
            _reject(
                C2_1_PAYLOAD_STORE_DRIFT,
                ProjectRecordNotFound("exact project payload value not found"),
            )
        if (
            row["object_type"] != payload_identity.object_type
            or row["state"] != "AVAILABLE"
            or row["source_ref"] != payload_identity.storage_ref
            or int(row["byte_size"]) != int(runtime_value["byte_size"])
            or row["provenance_digest"] != payload_identity.provenance_digest
            or int(row["revision"]) != payload_identity.revision
            or row["incarnation"] != payload_identity.incarnation
            or row["write_intent_digest"] != payload_identity.write_intent_digest
            or checksum_canonical_json(row["provenance_json"])
            != checksum_canonical_json(payload_identity.provenance)
        ):
            _reject(
                C2_1_PAYLOAD_STORE_DRIFT,
                ExactBindingConflict(
                    "project payload provenance/revision/incarnation/write-intent drift"
                ),
            )
        return row

    def _exact_payload_bytes(
        self,
        connection: Connection,
        tables: Any,
        scope: RuntimeScope,
        project_value: Mapping[str, Any],
        runtime_value: Mapping[str, Any],
        payload_identity: C2_1PayloadValueIdentity,
    ) -> bytes:
        try:
            payload_bytes = ValueRepository(connection, tables).get_exact(
                scope.project_scope,
                payload_identity.value_id,
                expected_revision=payload_identity.revision,
                expected_incarnation=payload_identity.incarnation,
                expected_digest=payload_identity.content_digest,
            )
        except (
            ExactContentConflict,
            ProjectRecordNotFound,
        ) as exc:
            _reject(C2_1_PAYLOAD_STORE_DRIFT, exc)
        expected_size = int(project_value["byte_size"])
        if len(payload_bytes) != expected_size or expected_size != int(
            runtime_value["byte_size"]
        ):
            _reject(
                C2_1_PAYLOAD_STORE_DRIFT,
                ExactContentConflict("payload byte_size drift"),
            )
        return payload_bytes

    def _decode_payload(
        self,
        codec: Any,
        payload_bytes: bytes,
        assignment: RuntimeAssignment,
    ) -> c2_1.SourceResolutionPayload:
        assert assignment.payload_digest is not None
        try:
            payload = codec.decode_payload(json.loads(payload_bytes.decode("utf-8")))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            _reject(C2_1_PAYLOAD_CODEC_DRIFT, exc)
        if (
            not isinstance(payload, c2_1.SourceResolutionPayload)
            or payload.payload_digest != assignment.payload_digest
        ):
            _reject(
                C2_1_PAYLOAD_CODEC_DRIFT,
                ValueError("decoded payload digest drift"),
            )
        return payload

    def _rebuild_payload_ref(
        self,
        payload: c2_1.SourceResolutionPayload,
        runtime_value: Mapping[str, Any],
        project_value: Mapping[str, Any],
        payload_identity: C2_1PayloadValueIdentity,
    ) -> ValueRef:
        payload_ref = payload_value_ref(
            payload,
            program_id=payload_identity.program_id,
            project_key=payload_identity.project_key,
        )
        if (
            payload_ref.storage_ref != payload_identity.storage_ref
            or payload_ref.content_digest != payload_identity.content_digest
            or payload_ref.codec_id != payload_identity.codec_id
            or payload_ref.object_type.type_id != payload_identity.object_type
            or payload_ref.provenance_digest != payload_identity.provenance_digest
            or payload_ref.byte_size != int(project_value["byte_size"])
            or payload_ref.value_id != payload_identity.value_id
        ):
            _reject(
                C2_1_PAYLOAD_STORE_DRIFT,
                ExactBindingConflict("payload ref identity drift"),
            )
        return payload_ref

    def _require_assignment_payload_binding(
        self,
        assignment: RuntimeAssignment,
        payload_identity: C2_1PayloadValueIdentity,
    ) -> None:
        if assignment.payload_ref != payload_identity.storage_ref:
            _reject(
                C2_1_ASSIGNMENT_BINDING_MISSING,
                ExactBindingConflict(
                    "assignment payload ref differs from Program closure"
                ),
            )

    def _require_payload_scope(
        self,
        payload: c2_1.SourceResolutionPayload,
        scope: RuntimeScope,
    ) -> None:
        current = scope.project_scope
        bound = payload.project_scope
        if (
            bound.project_key != current.project_key
            or bound.registry_revision != current.project_registry_revision
            or bound.incarnation != current.incarnation
            or bound.scope_digest != current.scope_digest
            or bound.resolved_schema != current.resolved_schema
        ):
            _reject(
                C2_1_SCOPE_REHYDRATION_DRIFT,
                ExactBindingConflict("payload project scope drift"),
            )

    def _require_deployment_catalog(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
    ) -> None:
        try:
            row = DeploymentCatalogRepository(connection).load(
                assignment.deployment_catalog_digest
            )
        except (RecordNotFound, ExactBindingConflict) as exc:
            _reject(C2_1_DEPLOYMENT_CATALOG_DRIFT, exc)
        if row["catalog_digest"] != assignment.deployment_catalog_digest:
            _reject(
                C2_1_DEPLOYMENT_CATALOG_DRIFT,
                ExactBindingConflict("deployment catalog digest drift"),
            )


__all__ = [
    "C2_1_ASSIGNMENT_BINDING_MISSING",
    "C2_1_DEPLOYMENT_CATALOG_DRIFT",
    "C2_1_OPERATION_CATALOG_DRIFT",
    "C2_1_PAYLOAD_CODEC_DRIFT",
    "C2_1_PAYLOAD_STORE_DRIFT",
    "C2_1_PLAN_STORE_DRIFT",
    "C2_1_PROGRAM_STORE_DRIFT",
    "C2_1_RUN_STORE_DRIFT",
    "C2_1_SCOPE_REHYDRATION_DRIFT",
    "C2_1_STORE_REHYDRATION_REJECTED",
    "C2_1PayloadValueIdentity",
    "SourceLibraryC2_1StoreRehydratedHandler",
    "c2_1_expected_payload_value_identity",
]
