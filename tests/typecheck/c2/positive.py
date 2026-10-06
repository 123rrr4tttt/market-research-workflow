from sqlalchemy.engine import Result, RowMapping

from app.successor_runtime.capabilities import source_resolution as resolution
from app.successor_runtime.capabilities.source_resolution_interpreters import (
    InterpreterOutcome,
    SourceResolutionSuccessorInterpreter,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.language.plan import ExecutionPlan
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.runtime.assignments import InterpreterBinding
from app.successor_runtime.substrate.postgres.runtime_journal import one_mapping


def exact_row(result: Result[tuple[object, ...]]) -> RowMapping | None:
    return one_mapping(result)


def exact_interpret(
    interpreter: SourceResolutionSuccessorInterpreter,
    program: ProgramSpec,
    plan: ExecutionPlan,
    contract_ref: OperationContractRef,
    payload_ref: ValueRef,
    payload: resolution.SourceResolutionPayload,
    catalog: OperationContractCatalogSnapshot,
    binding: InterpreterBinding,
    deployment_catalog_digest: str,
) -> InterpreterOutcome[resolution.SourceResolutionResult]:
    return interpreter.interpret(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=payload.project_scope,
        catalog=catalog,
        deployment_catalog_digest=deployment_catalog_digest,
        binding=binding,
    )
