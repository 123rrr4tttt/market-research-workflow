"""Exact immutable ExecutionPlan repository."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.language.plan import (
    CompiledAdmission,
    CompiledControlNode,
    CompiledDecisionBranch,
    CompiledStep,
    CompletionPolicy,
    ExecutionPlan,
    FrozenDependencyIndex,
    PlanReturnPolicy,
    ProgramPlanSourceMap,
    with_plan_digest,
)
from app.successor_runtime.language.transforms import TransformRef
from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.research.object_types import ObjectType
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope

from .research_ledger import (
    ExactContentConflict,
    ProjectRecordNotFound,
    assert_table_scope,
    one_mapping,
    project_table,
    utcnow,
)


def _otype(value: dict[str, Any]) -> ObjectType:
    return ObjectType(**value)


def _transform(value: dict[str, Any] | None) -> TransformRef | None:
    return None if value is None else TransformRef(**value)


def _contract_ref(value: dict[str, Any] | None) -> OperationContractRef | None:
    return None if value is None else OperationContractRef(**value)


def _return(value: dict[str, Any]) -> ReturnContract:
    return ReturnContract(
        success_modes=tuple(value["success_modes"]),
        failure_modes=tuple(value["failure_modes"]),
        admission_required=value["admission_required"],
        wait_modes=tuple(value["wait_modes"]),
        cancel_modes=tuple(value["cancel_modes"]),
    )


def _admission(value: dict[str, Any] | None) -> CompiledAdmission | None:
    if value is None:
        return None
    return CompiledAdmission(
        effect_step_id=value["effect_step_id"],
        admission_step_id=value["admission_step_id"],
        operation_id=value["operation_id"],
        operation_contract_ref=OperationContractRef(**value["operation_contract_ref"]),
        return_contract=_return(value["return_contract"]),
    )


def _step(value: dict[str, Any]) -> CompiledStep:
    return CompiledStep(
        step_id=value["step_id"],
        step_kind=value["step_kind"],
        source_path=tuple(value["source_path"]),
        input_type=_otype(value["input_type"]),
        output_type=_otype(value["output_type"]),
        dependencies=tuple(value["dependencies"]),
        operation_id=value["operation_id"],
        operation_contract_ref=_contract_ref(value["operation_contract_ref"]),
        transform_ref=_transform(value["transform_ref"]),
        effect_profile_ref=value["effect_profile_ref"],
        resource_profile_ref=value["resource_profile_ref"],
        failure_profile_ref=value["failure_profile_ref"],
        authority_profile_ref=value["authority_profile_ref"],
        return_contract=_return(value["return_contract"]),
        semantic_return_barrier=value["semantic_return_barrier"],
        staged_output_only=value["staged_output_only"],
        return_contract_ref=value["return_contract_ref"],
        admission=_admission(value["admission"]),
        branch_id=value["branch_id"],
        guard=value["guard"],
        disposition=value["disposition"],
        branch_control_id=value["branch_control_id"],
        branch_entry=value["branch_entry"],
        branch_order=value["branch_order"],
    )


def _control(value: dict[str, Any]) -> CompiledControlNode:
    return CompiledControlNode(
        control_id=value["control_id"],
        node_kind=value["node_kind"],
        source_path=tuple(value["source_path"]),
        input_type=_otype(value["input_type"]),
        output_type=_otype(value["output_type"]),
        children=tuple(_control(child) for child in value["children"]),
        step_ids=tuple(value["step_ids"]),
        semantic_return_step_ids=tuple(value["semantic_return_step_ids"]),
        source_digest=value["source_digest"],
        attributes=tuple(tuple(item) for item in value["attributes"]),
        discriminator_ref=_transform(value["discriminator_ref"]),
        decision_branches=tuple(
            CompiledDecisionBranch(
                branch_id=item["branch_id"],
                guard=item["guard"],
                step_ids=tuple(item["step_ids"]),
                entry_step_ids=tuple(item["entry_step_ids"]),
            )
            for item in value["decision_branches"]
        ),
        control_digest=value["control_digest"],
    )


def decode_plan(value: dict[str, Any]) -> ExecutionPlan:
    plan = ExecutionPlan(
        plan_id=value["plan_id"],
        program_id=value["program_id"],
        program_digest=value["program_digest"],
        input_type=_otype(value["input_type"]),
        output_type=_otype(value["output_type"]),
        compiler_id=value["compiler_id"],
        compiler_version=value["compiler_version"],
        control_root=_control(value["control_root"]),
        ordered_steps=tuple(_step(item) for item in value["ordered_steps"]),
        dependency_index=FrozenDependencyIndex(
            tuple((item[0], tuple(item[1])) for item in value["dependency_index"]["entries"])
        ),
        ready_order=tuple(value["ready_order"]),
        source_map=tuple(
            ProgramPlanSourceMap(
                source_path=tuple(item["source_path"]),
                source_kind=item["source_kind"],
                source_digest=item["source_digest"],
                control_id=item["control_id"],
                step_ids=tuple(item["step_ids"]),
                semantic_return_step_ids=tuple(item["semantic_return_step_ids"]),
                branch_id=item["branch_id"],
            )
            for item in value["source_map"]
        ),
        return_policy=PlanReturnPolicy(
            success_modes=tuple(value["return_policy"]["success_modes"]),
            failure_modes=tuple(value["return_policy"]["failure_modes"]),
            wait_modes=tuple(value["return_policy"]["wait_modes"]),
            cancel_modes=tuple(value["return_policy"]["cancel_modes"]),
            exported_barrier_step_ids=tuple(
                value["return_policy"]["exported_barrier_step_ids"]
            ),
        ),
        completion_policy=CompletionPolicy(**value["completion_policy"]),
        effect_closure_digest=value["effect_closure_digest"],
        authority_closure_digest=value["authority_closure_digest"],
        resource_closure_digest=value["resource_closure_digest"],
        plan_digest=value["plan_digest"],
    )
    if with_plan_digest(plan).plan_digest != plan.plan_digest:
        raise ExactContentConflict("stored ExecutionPlan fails structural digest readback")
    return plan


class PlanRepository:
    def __init__(self, connection: Connection, tables: Any) -> None:
        self.connection = connection
        self.tables = tables

    def put_exact(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        plan: ExecutionPlan,
        expected_digest: str,
        *,
        operation_catalog_id: str,
        catalog_version: str,
        catalog_digest: str,
    ) -> ExecutionPlan:
        table = project_table(self.tables, "research_execution_plans")
        project_key = assert_table_scope(table, scope)
        if plan.plan_digest != expected_digest or with_plan_digest(plan).plan_digest != expected_digest:
            raise ExactContentConflict("ExecutionPlan digest does not bind exact plan")
        payload_bytes = canonical_bytes(plan)
        payload = json.loads(payload_bytes)
        rows = (
            one_mapping(self.connection.execute(select(table).where(table.c.project_key == project_key, table.c.plan_id == plan.plan_id))),
            one_mapping(self.connection.execute(select(table).where(table.c.project_key == project_key, table.c.plan_digest == expected_digest))),
        )
        for row in rows:
            if row is None:
                continue
            stored = canonical_bytes(row["plan_json"])
            if row["plan_id"] != plan.plan_id or stored != payload_bytes:
                raise ExactContentConflict("same Plan identity/digest has different canonical bytes")
        if rows[0] is not None:
            return plan
        now = utcnow()
        self.connection.execute(insert(table).values(
            project_key=project_key, plan_id=plan.plan_id, plan_digest=expected_digest,
            program_id=plan.program_id, program_digest=plan.program_digest,
            compiler_id=plan.compiler_id, compiler_version=plan.compiler_version,
            operation_catalog_id=operation_catalog_id, catalog_version=catalog_version,
            catalog_digest=catalog_digest, plan_json=payload,
            effect_closure_digest=plan.effect_closure_digest,
            authority_closure_digest=plan.authority_closure_digest,
            resource_closure_digest=plan.resource_closure_digest,
            created_at=now, updated_at=now,
        ))
        return plan

    def get(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        plan_digest: str,
    ) -> ExecutionPlan:
        table = project_table(self.tables, "research_execution_plans")
        project_key = assert_table_scope(table, scope)
        row = one_mapping(self.connection.execute(select(table).where(
            table.c.project_key == project_key, table.c.plan_digest == plan_digest
        )))
        if row is None:
            raise ProjectRecordNotFound(f"exact ExecutionPlan not found: {plan_digest}")
        return decode_plan(row["plan_json"])


__all__ = ["PlanRepository", "decode_plan"]
