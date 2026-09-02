"""PostgreSQL evidence loader for pure failure-policy derivation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.research.codec import canonical_bytes
from app.successor_runtime.runtime.failure_policy import (
    FailurePolicyDecision,
    FailurePolicyDerivationError,
    derive_failure_policy,
)
from app.successor_runtime.runtime.ports import RuntimeScope

from .models import PUBLIC_TABLES, project_tables
from .plans import decode_plan
from .runtime_journal import ExactBindingConflict, validate_qualification_row


class PersistedFailurePolicyError(ExactBindingConflict):
    """Persisted evidence is absent, cross-scoped, or digest-inconsistent."""


def _one(result: Any, *, label: str) -> Mapping[str, Any]:
    rows = result.mappings().all()
    if len(rows) != 1:
        raise PersistedFailurePolicyError(
            f"{label} must resolve to exactly one persisted row; observed {len(rows)}"
        )
    return rows[0]


def _require_equal(
    observed: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    label: str,
) -> None:
    drift = tuple(key for key, value in expected.items() if observed.get(key) != value)
    if drift:
        raise PersistedFailurePolicyError(f"{label} drift: {', '.join(drift)}")


class PostgresFailurePolicyLoader:
    """Lock exact persisted run/plan/qualification evidence and derive policy.

    The loader owns no transaction.  Its caller must use the same
    ``RuntimeUnitOfWork`` connection that will append ``RequiredStepFailed``;
    row locks prevent a policy proof from being detached from the terminal
    transition CAS.
    """

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def load(self, run_id: str, step_id: str) -> FailurePolicyDecision:
        if not run_id or not step_id:
            raise PersistedFailurePolicyError(
                "persisted failure policy requires run_id and step_id"
            )
        scope = self.scope.project_scope
        project_key = scope.project_key

        registry = _one(
            self.connection.execute(
                select(PUBLIC_TABLES["project_scope_registry"])
                .where(
                    PUBLIC_TABLES["project_scope_registry"].c.project_key
                    == project_key,
                    PUBLIC_TABLES["project_scope_registry"].c.registry_revision
                    == scope.project_registry_revision,
                    PUBLIC_TABLES["project_scope_registry"].c.resolved_schema
                    == scope.resolved_schema,
                    PUBLIC_TABLES["project_scope_registry"].c.scope_digest
                    == scope.scope_digest,
                    PUBLIC_TABLES["project_scope_registry"].c.incarnation
                    == scope.incarnation,
                    PUBLIC_TABLES["project_scope_registry"].c.state == "ACTIVE",
                )
                .with_for_update()
            ),
            label="current ProjectScopeRef",
        )
        _require_equal(
            registry,
            {
                "project_key": project_key,
                "registry_revision": scope.project_registry_revision,
                "resolved_schema": scope.resolved_schema,
                "scope_digest": scope.scope_digest,
                "incarnation": scope.incarnation,
                "state": "ACTIVE",
            },
            label="ProjectScopeRef",
        )

        runs = PUBLIC_TABLES["runtime_runs"]
        run = _one(
            self.connection.execute(
                select(runs)
                .where(runs.c.project_key == project_key, runs.c.run_id == run_id)
                .with_for_update()
            ),
            label="runtime run",
        )
        _require_equal(
            run,
            {
                "run_id": run_id,
                "project_key": project_key,
                "project_registry_revision": scope.project_registry_revision,
                "project_scope_digest": scope.scope_digest,
                "resolved_schema": scope.resolved_schema,
            },
            label="runtime run scope",
        )
        required_run_fields = (
            "program_id",
            "program_digest",
            "plan_id",
            "plan_digest",
            "qualification_digest",
        )
        missing = tuple(field for field in required_run_fields if not run.get(field))
        if missing:
            raise PersistedFailurePolicyError(
                "runtime run lacks exact plan/qualification fields: "
                + ", ".join(missing)
            )

        plan_refs = PUBLIC_TABLES["runtime_plan_refs"]
        public_plan = _one(
            self.connection.execute(
                select(plan_refs)
                .where(
                    plan_refs.c.project_key == project_key,
                    plan_refs.c.plan_id == run["plan_id"],
                    plan_refs.c.plan_digest == run["plan_digest"],
                    plan_refs.c.program_id == run["program_id"],
                    plan_refs.c.program_digest == run["program_digest"],
                )
                .with_for_update()
            ),
            label="public ExecutionPlan ref",
        )

        tables = project_tables(MetaData(), scope.resolved_schema)
        plans = tables.research_execution_plans
        project_plan = _one(
            self.connection.execute(
                select(plans)
                .where(
                    plans.c.project_key == project_key,
                    plans.c.plan_id == run["plan_id"],
                    plans.c.plan_digest == run["plan_digest"],
                    plans.c.program_id == run["program_id"],
                    plans.c.program_digest == run["program_digest"],
                )
                .with_for_update()
            ),
            label="project ExecutionPlan",
        )
        plan_columns = (
            "project_key",
            "plan_id",
            "plan_digest",
            "program_id",
            "program_digest",
            "compiler_id",
            "compiler_version",
            "operation_catalog_id",
            "catalog_version",
            "catalog_digest",
            "effect_closure_digest",
            "authority_closure_digest",
            "resource_closure_digest",
        )
        drift = tuple(
            column
            for column in plan_columns
            if public_plan.get(column) != project_plan.get(column)
        )
        if drift:
            raise PersistedFailurePolicyError(
                "public/project ExecutionPlan ref drift: " + ", ".join(drift)
            )
        raw_plan = project_plan.get("plan_json")
        if not isinstance(raw_plan, Mapping):
            raise PersistedFailurePolicyError(
                "project ExecutionPlan lacks canonical plan_json"
            )
        try:
            exact_plan = decode_plan(dict(raw_plan))
        except Exception as exc:
            raise PersistedFailurePolicyError(
                "project ExecutionPlan structural digest readback failed"
            ) from exc
        if canonical_bytes(raw_plan) != canonical_bytes(exact_plan):
            raise PersistedFailurePolicyError(
                "project ExecutionPlan canonical bytes drift"
            )
        _require_equal(
            project_plan,
            {
                "plan_id": exact_plan.plan_id,
                "plan_digest": exact_plan.plan_digest,
                "program_id": exact_plan.program_id,
                "program_digest": exact_plan.program_digest,
                "compiler_id": exact_plan.compiler_id,
                "compiler_version": exact_plan.compiler_version,
                "effect_closure_digest": exact_plan.effect_closure_digest,
                "authority_closure_digest": exact_plan.authority_closure_digest,
                "resource_closure_digest": exact_plan.resource_closure_digest,
            },
            label="ExecutionPlan duplicated columns",
        )

        qualifications = PUBLIC_TABLES["runtime_qualifications"]
        qualification_row = _one(
            self.connection.execute(
                select(qualifications)
                .where(
                    qualifications.c.project_key == project_key,
                    qualifications.c.run_id == run_id,
                    qualifications.c.plan_id == exact_plan.plan_id,
                    qualifications.c.plan_digest == exact_plan.plan_digest,
                    qualifications.c.qualification_digest
                    == run["qualification_digest"],
                    qualifications.c.decision == "QUALIFIED",
                )
                .with_for_update()
            ),
            label="exact QualifiedPlan",
        )
        try:
            qualification = validate_qualification_row(qualification_row)
        except ExactBindingConflict as exc:
            raise PersistedFailurePolicyError(
                "exact qualification binding readback failed"
            ) from exc
        context = qualification.authority_context
        _require_equal(
            qualification_row,
            {
                "project_key": project_key,
                "run_id": run_id,
                "plan_id": exact_plan.plan_id,
                "plan_digest": exact_plan.plan_digest,
                "qualification_digest": run["qualification_digest"],
                "decision": "QUALIFIED",
            },
            label="QualifiedPlan duplicated columns",
        )
        if (
            qualification.project_key != project_key
            or qualification.run_id != run_id
            or qualification.plan_id != exact_plan.plan_id
            or qualification.plan_digest != exact_plan.plan_digest
            or context.project_key != project_key
            or context.resolved_schema != scope.resolved_schema
            or context.project_registry_revision != scope.project_registry_revision
            or context.project_scope_digest != scope.scope_digest
        ):
            raise PersistedFailurePolicyError(
                "qualification run/plan/ProjectScopeRef drift"
            )
        for binding in qualification.qualified_plan.step_bindings:
            if (
                binding.run_id != run_id
                or binding.project_key != project_key
                or binding.actor_id != context.actor_id
                or binding.project_registry_revision != scope.project_registry_revision
                or binding.project_scope_digest != scope.scope_digest
            ):
                raise PersistedFailurePolicyError(
                    f"QualifiedPlan step scope drift for {binding.step_id}"
                )

        try:
            decision = derive_failure_policy(
                exact_plan, qualification.qualified_plan, step_id
            )
        except FailurePolicyDerivationError as exc:
            raise PersistedFailurePolicyError(
                "persisted failure policy derivation failed"
            ) from exc
        if decision.run_id != run_id:
            raise PersistedFailurePolicyError(
                "derived failure policy run identity drift"
            )
        return decision

    def load_decision(self, run_id: str, step_id: str) -> FailurePolicyDecision:
        """Explicit alias for lifecycle callers."""

        return self.load(run_id, step_id)


__all__ = ["PersistedFailurePolicyError", "PostgresFailurePolicyLoader"]
