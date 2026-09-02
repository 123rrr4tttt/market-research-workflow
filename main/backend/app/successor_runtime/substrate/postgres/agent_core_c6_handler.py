"""Store-rehydrated RuntimeHandler for the P3 C6 family-local canary.

The handler captures no Program, Plan, payload, catalog or binding object:
``execute`` opens a fresh unit of work, resolves the current project scope,
reloads the exact canonical Program, ExecutionPlan and payload bytes from the
project stores, revalidates operation/deployment catalog identities and the
payload codec, and only then invokes the cell-specific successor interpreter.
The only captured values are immutable deployment facts plus deterministic,
in-memory interpreter fixtures: a scripted model-step source and the C2.1 pure
tool specimen for C6.1, a receipt-only provider port for C6.2, and an
ephemeral raw observation for C6.3 (never persisted or returned).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities import (
    agent_core_c6_1 as c6_1,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_1_interpreters as c6_1i,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_1_program as c6_1p,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_2 as c6_2,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_2_interpreters as c6_2i,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_2_program as c6_2p,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_3 as c6_3,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_3_interpreters as c6_3i,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_3_program as c6_3p,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    ProjectScope,
)
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
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.models import project_tables
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

C6_ASSIGNMENT_BINDING_MISSING = "C6_ASSIGNMENT_BINDING_MISSING"
C6_RUN_STORE_DRIFT = "C6_RUN_STORE_DRIFT"
C6_SCOPE_REHYDRATION_DRIFT = "C6_SCOPE_REHYDRATION_DRIFT"
C6_PROGRAM_STORE_DRIFT = "C6_PROGRAM_STORE_DRIFT"
C6_PLAN_STORE_DRIFT = "C6_PLAN_STORE_DRIFT"
C6_OPERATION_CATALOG_DRIFT = "C6_OPERATION_CATALOG_DRIFT"
C6_DEPLOYMENT_CATALOG_DRIFT = "C6_DEPLOYMENT_CATALOG_DRIFT"
C6_PAYLOAD_STORE_DRIFT = "C6_PAYLOAD_STORE_DRIFT"
C6_PAYLOAD_CODEC_DRIFT = "C6_PAYLOAD_CODEC_DRIFT"
C6_STORE_REHYDRATION_REJECTED = "C6_STORE_REHYDRATION_REJECTED"

_CELLS = frozenset({"c6_1", "c6_2", "c6_3"})
_VALUE_ID_PREFIX = "project-value:"


def _reject(code: str, exc: BaseException) -> None:
    raise DefiniteInterpreterFailure(code) from exc


def _family_scope(scope: RuntimeScope) -> ProjectScope:
    ref = scope.project_scope
    return ProjectScope(
        project_key=ref.project_key,
        registry_revision=ref.project_registry_revision,
        resolved_schema=ref.resolved_schema,
        incarnation=ref.incarnation,
        scope_digest=ref.scope_digest,
    )


@dataclass(frozen=True, slots=True)
class _LoadedClosure:
    program: ProgramSpec
    plan: ExecutionPlan
    contract_ref: Any
    payload_ref: Any
    payload: Any
    catalog: OperationContractCatalogSnapshot
    project_scope: ProjectScope


class AgentCoreC6StoreRehydratedHandler(RuntimeHandler):
    """Exact installed realization that rehydrates every C6 run from stores."""

    def __init__(
        self,
        *,
        uow_factory: Callable[[], RuntimeUnitOfWork],
        cell: str,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
        model_step_source: Any = None,
        tool_specimens: tuple[Any, ...] = (),
        permission_policy: Any = None,
        redactor: Any = None,
        provider_port: Any = None,
        raw_observation: dict[str, Any] | None = None,
    ) -> None:
        if cell not in _CELLS:
            raise ValueError(f"unsupported C6 handler cell {cell!r}")
        if cell == "c6_1" and (
            model_step_source is None
            or not tool_specimens
            or permission_policy is None
            or redactor is None
        ):
            raise ValueError("c6_1 handler requires deterministic loop fixtures")
        if cell == "c6_2" and provider_port is None:
            raise ValueError("c6_2 handler requires an injected provider port")
        if cell == "c6_3" and raw_observation is None:
            raise ValueError("c6_3 handler requires an ephemeral raw observation")
        require_digest(handler_binding_digest, "C6 store handler binding digest")
        require_digest(
            interpreter_profile_digest, "C6 store interpreter profile digest"
        )
        require_digest(operation_contract_digest, "C6 store operation contract digest")
        require_digest(deployment_catalog_digest, "C6 store deployment catalog digest")
        self.uow_factory = uow_factory
        self.cell = cell
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.operation_contract_digest = operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest
        self.model_step_source = model_step_source
        self.tool_specimens = tuple(tool_specimens)
        self.permission_policy = permission_policy
        self.redactor = redactor
        self.provider_port = provider_port
        self.raw_observation = raw_observation
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
            raise DefiniteInterpreterFailure("EXACT_C6_HANDLER_BINDING_DRIFT")
        if assignment.deployment_catalog_digest != self.deployment_catalog_digest:
            raise DefiniteInterpreterFailure("EXACT_C6_DEPLOYMENT_CATALOG_DRIFT")

        loaded = self._load_exact_closure(assignment, context.node.node_id)
        common = {
            "program": loaded.program,
            "plan": loaded.plan,
            "contract_ref": loaded.contract_ref,
            "payload_ref": loaded.payload_ref,
            "payload": loaded.payload,
            "project_scope": loaded.project_scope,
            "catalog": loaded.catalog,
            "deployment_catalog_digest": self.deployment_catalog_digest,
            "binding": assignment.handler_binding,
        }
        if self.cell == "c6_1":
            outcome = c6_1i.AgentCoreEpisodeInterpreter().interpret(
                **common,
                model_step_source=self.model_step_source,
                tool_specimens=self.tool_specimens,
                permission_policy=self.permission_policy,
                redactor=self.redactor,
            )
            if isinstance(outcome, c6_1i.InterpreterFailure):
                raise DefiniteInterpreterFailure(outcome.code)
            output_digest = outcome.value.episode_digest
        elif self.cell == "c6_2":
            outcome = c6_2i.NamedProviderModelStepInterpreter().interpret(
                **common,
                port=self.provider_port,
                attempt_id=f"attempt:{assignment.run_id}:{assignment.step_id}",
            )
            if isinstance(outcome, c6_2i.InterpreterFailure):
                raise DefiniteInterpreterFailure(outcome.code)
            output_digest = outcome.value.result_digest
            self.provider_calls += int(getattr(self.provider_port, "provider_calls", 0))
        else:
            assert self.raw_observation is not None
            outcome = c6_3i.VersionedRedactionEvidenceInterpreter().interpret(
                **common,
                raw_observation=self.raw_observation,
            )
            if isinstance(outcome, c6_3i.InterpreterFailure):
                raise DefiniteInterpreterFailure(outcome.code)
            output_digest = outcome.value.receipt_digest
        return InterpreterOutcome.succeeded(output_digest)

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
            raise DefiniteInterpreterFailure(C6_ASSIGNMENT_BINDING_MISSING)
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
                plan_ref = self._plan_ref(connection, assignment, program_ref)
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
                    catalog,
                    contract_ref,
                    assignment,
                )
                payload_bytes = self._exact_payload_bytes(
                    connection,
                    tables,
                    scope,
                    assignment,
                )
                payload = self._decode_payload(codec, payload_bytes, assignment)
                payload_ref = self._rebuild_payload_ref(
                    payload,
                    program,
                    assignment,
                    payload_bytes,
                )
                self._require_deployment_catalog(connection, assignment)
                self._require_interpreter_binding(
                    program,
                    plan,
                    contract_ref,
                    payload_ref,
                    payload,
                    scope,
                    catalog,
                    assignment,
                )
                return _LoadedClosure(
                    program=program,
                    plan=plan,
                    contract_ref=contract_ref,
                    payload_ref=payload_ref,
                    payload=payload,
                    catalog=catalog,
                    project_scope=_family_scope(scope),
                )
        except DefiniteInterpreterFailure:
            raise
        except Exception as exc:
            raise DefiniteInterpreterFailure(C6_STORE_REHYDRATION_REJECTED) from exc

    def _load_run(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
    ) -> Any:
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
                C6_RUN_STORE_DRIFT,
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
                C6_RUN_STORE_DRIFT,
                ExactBindingConflict("runtime run exact identity drift"),
            )
        return run

    def _resolve_scope(
        self,
        connection: Connection,
        run: Any,
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
            _reject(C6_SCOPE_REHYDRATION_DRIFT, exc)

    def _program_ref(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
    ) -> Any:
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
                C6_PROGRAM_STORE_DRIFT,
                RecordNotFound("exact public Program ref not found"),
            )
        return row

    def _load_program(
        self,
        connection: Connection,
        tables: Any,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        program_ref: Any,
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
            _reject(C6_PROGRAM_STORE_DRIFT, exc)
        if (
            program.program_id != program_ref["program_id"]
            or program.program_digest != assignment.program_digest
            or program.contract_version != program_ref["contract_version"]
            or program_ref["project_storage_ref"]
            != f"project-value:{program.program_id}"
        ):
            _reject(
                C6_PROGRAM_STORE_DRIFT,
                ExactBindingConflict("public Program ref identity drift"),
            )
        return program

    def _plan_ref(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
        program_ref: Any,
    ) -> Any:
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
                C6_PLAN_STORE_DRIFT,
                RecordNotFound("exact public Plan ref not found"),
            )
        return row

    def _load_plan(
        self,
        connection: Connection,
        tables: Any,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        plan_ref: Any,
        program_ref: Any,
    ) -> ExecutionPlan:
        assert assignment.plan_digest is not None
        try:
            plan = PlanRepository(connection, tables).get(
                scope.project_scope,
                assignment.plan_digest,
            )
        except (ExactContentConflict, ProjectRecordNotFound) as exc:
            _reject(C6_PLAN_STORE_DRIFT, exc)
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
                C6_PLAN_STORE_DRIFT,
                ExactBindingConflict("exact ExecutionPlan identity drift"),
            )
        return plan

    def _installed_closure(self, plan_ref: Any) -> tuple[Any, Any, Any]:
        if self.cell == "c6_1":
            bundle = c6_1.build_agent_core_c6_1_bundle()
            catalog = c6_1.build_agent_core_c6_1_catalog(bundle)
            contract_ref = c6_1p.exact_contract_ref(catalog)
            codec = bundle.payload_codec()
            expected_codec = c6_1.AGENT_CORE_C6_1_PAYLOAD_CODEC_ID
        elif self.cell == "c6_2":
            bundle = c6_2.build_agent_core_c6_2_bundle()
            catalog = c6_2.build_agent_core_c6_2_catalog(bundle)
            contract_ref = c6_2p.exact_contract_ref(catalog)
            codec = bundle.payload_codec()
            expected_codec = c6_2.AGENT_CORE_C6_2_PAYLOAD_CODEC_ID
        else:
            bundle = c6_3.build_agent_core_c6_3_bundle()
            catalog = c6_3.build_agent_core_c6_3_catalog(bundle)
            contract_ref = c6_3p.exact_contract_ref(catalog)
            codec = bundle.payload_codec()
            expected_codec = c6_3.AGENT_CORE_C6_3_PAYLOAD_CODEC_ID
        if (
            codec.codec_id != expected_codec
            or catalog.catalog_id != plan_ref["operation_catalog_id"]
            or catalog.catalog_version != plan_ref["catalog_version"]
            or catalog.catalog_digest != plan_ref["catalog_digest"]
        ):
            _reject(
                C6_OPERATION_CATALOG_DRIFT,
                ExactBindingConflict("installed operation catalog identity drift"),
            )
        return catalog, contract_ref, codec

    def _require_operation_catalog(
        self,
        plan_ref: Any,
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
        ):
            _reject(
                C6_OPERATION_CATALOG_DRIFT,
                ExactBindingConflict("assignment/operation contract drift"),
            )
        catalog_ref = catalog.lookup(contract_ref)
        if (
            catalog_ref is None
            or catalog_ref.contract_digest != contract_ref.contract_digest
        ):
            _reject(
                C6_OPERATION_CATALOG_DRIFT,
                ExactBindingConflict("catalog/contract ref drift"),
            )

    def _exact_payload_bytes(
        self,
        connection: Connection,
        tables: Any,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
    ) -> bytes:
        assert assignment.payload_ref is not None
        if not assignment.payload_ref.startswith(_VALUE_ID_PREFIX):
            _reject(
                C6_PAYLOAD_STORE_DRIFT,
                ExactBindingConflict("payload ref is not a bounded project value"),
            )
        value_id = assignment.payload_ref[len(_VALUE_ID_PREFIX) :]
        try:
            table = tables.successor_values
            row = _one_mapping(
                connection.execute(
                    sa.select(table).where(
                        table.c.project_key == assignment.project_key,
                        table.c.value_id == value_id,
                        table.c.revision == 1,
                        table.c.incarnation == f"payload-inc:{self.cell}-canary",
                    )
                )
            )
            if row is None:
                raise ProjectRecordNotFound(f"exact value not found: {value_id}")
            exact = (
                bytes(row["content_bytes"])
                if row["content_bytes"] is not None
                else json.dumps(
                    row["content_json"],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            )
            return exact
        except (ExactContentConflict, ProjectRecordNotFound) as exc:
            _reject(C6_PAYLOAD_STORE_DRIFT, exc)

    def _decode_payload(
        self,
        codec: Any,
        payload_bytes: bytes,
        assignment: RuntimeAssignment,
    ) -> Any:
        try:
            payload = codec.decode_payload(json.loads(payload_bytes.decode("utf-8")))
        except Exception as exc:  # noqa: BLE001 - codec drift must fail closed
            _reject(C6_PAYLOAD_CODEC_DRIFT, exc)
        if getattr(payload, "payload_digest", "") != assignment.payload_digest:
            _reject(
                C6_PAYLOAD_CODEC_DRIFT,
                ExactBindingConflict("decoded payload digest drift"),
            )
        return payload

    def _rebuild_payload_ref(
        self,
        payload: Any,
        program: ProgramSpec,
        assignment: RuntimeAssignment,
        payload_bytes: bytes,
    ) -> Any:
        if self.cell == "c6_1":
            rebuilt = c6_1p.payload_value_ref(
                payload,
                program_id=program.program_id,
                project_key=assignment.project_key,
            )
        elif self.cell == "c6_2":
            rebuilt = c6_2p.payload_value_ref(
                payload,
                program_id=program.program_id,
                project_key=assignment.project_key,
            )
        else:
            rebuilt = c6_3p.payload_value_ref(
                payload,
                program_id=program.program_id,
                project_key=assignment.project_key,
            )
        if getattr(payload, "payload_digest", "") != assignment.payload_digest:
            _reject(
                C6_PAYLOAD_STORE_DRIFT,
                ExactBindingConflict("decoded payload self-digest drift"),
            )
        if rebuilt.content_digest != hashlib.sha256(payload_bytes).hexdigest():
            _reject(
                C6_PAYLOAD_STORE_DRIFT,
                ExactBindingConflict("stored payload bytes digest drift"),
            )
        return rebuilt

    def _require_deployment_catalog(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
    ) -> None:
        table = _table("runtime_deployment_catalogs")
        row = _one_mapping(
            connection.execute(
                sa.select(table).where(
                    table.c.catalog_digest == assignment.deployment_catalog_digest
                )
            )
        )
        if row is None:
            _reject(
                C6_DEPLOYMENT_CATALOG_DRIFT,
                RecordNotFound("exact deployment catalog not installed"),
            )

    def _require_interpreter_binding(
        self,
        program: ProgramSpec,
        plan: ExecutionPlan,
        contract_ref: Any,
        payload_ref: Any,
        payload: Any,
        scope: RuntimeScope,
        catalog: OperationContractCatalogSnapshot,
        assignment: RuntimeAssignment,
    ) -> None:
        binding = assignment.handler_binding
        common = {
            "program": program,
            "plan": plan,
            "contract_ref": contract_ref,
            "payload_ref": payload_ref,
            "payload": payload,
            "project_scope": _family_scope(scope),
            "catalog": catalog,
            "deployment_catalog_digest": self.deployment_catalog_digest,
            "binding": binding,
        }
        if self.cell == "c6_1":
            c6_1i.require_exact_episode_binding(
                **common,
                expected_interpreter_profile_digest=(
                    c6_1i.successor_interpreter_profile_digest()
                ),
            )
        elif self.cell == "c6_2":
            c6_2i.require_exact_provider_binding(
                **common,
                expected_interpreter_profile_digest=(
                    c6_2i.successor_interpreter_profile_digest()
                ),
            )
        else:
            c6_3i.require_exact_redaction_binding(
                **common,
                expected_interpreter_profile_digest=(
                    c6_3i.successor_interpreter_profile_digest()
                ),
            )
