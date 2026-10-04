"""Batch-task family assembly: exact handler installation for three slots.

C4.3 is always installed as the store-rehydrated submission handler.  C4.1 and
C4.2 canary handlers are installed only when the caller supplies the exact
deterministic payload; otherwise they are fail-closed as
``FIXTURE_CLOSURE_REQUIRED``.

The deployment catalog digest is derived from the native batch-task family
identity and is consumed by exact handlers and the default assembly.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Annotated, Any

from functorial_kit.core.failure import Failure

from app.successor_runtime.capabilities import batch_task as batch_task
from app.successor_runtime.capabilities import source_contracts as source_contracts
from app.successor_runtime.capabilities.batch_task import (
    AgentBatchTask,
    BatchPlanPayload,
    CriticDecision,
    RetryAction,
    RetryBudget,
    RetryReducerInput,
)
from app.successor_runtime.capabilities.batch_task_interpreters import (
    authority_requirement_digest,
    successor_plan_interpreter_profile_digest,
    successor_retry_interpreter_profile_digest,
    successor_submission_interpreter_profile_digest,
)
from app.successor_runtime.capabilities.batch_task_native_contribution import (
    DEFAULT_BATCH_TASK_NATIVE_SOURCE,
    compile_batch_task_native_contribution,
)
from app.successor_runtime.capabilities.batch_task_program import (
    build_batch_task_plan_program,
    build_batch_task_retry_program,
    compile_batch_task_program,
)
from app.successor_runtime.substrate.postgres.batch_task_submission_handler import (
    BatchTaskSubmissionStoreRehydratedHandler,
)
from app.successor_runtime.substrate.postgres.batch_task_canary_handlers import (
    BatchTaskPlanRuntimeHandler,
    BatchTaskRetryRuntimeHandler,
)
from app.successor_runtime.substrate.postgres.batch_task_quality_promotion_handler import (
    BatchTaskQualityPromotionRuntimeHandler,
)
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork

from .base import (
    BatchTaskAssemblyOptions,
    CellBinding,
    FamilyAssembly,
    RollbackBindingDeclaration,
    require_assembly_digest,
    sha256_hex,
    successor_binding,
)

_BATCH_TASK_DEPLOYMENT_CATALOG_DIGEST = sha256_hex(batch_task.BATCH_TASK_DEPLOYMENT_CATALOG_ID)
_BATCH_TASK_QUALITY_PROMOTION_OPERATION_DIGEST = sha256_hex(
    batch_task.QUALITY_PROMOTION_OPERATION_ID
)
_BATCH_TASK_QUALITY_PROMOTION_INTERPRETER_DIGEST = sha256_hex(
    batch_task.QUALITY_PROMOTION_INTERPRETER_ID
)
_BATCH_TASK_QUALITY_PROMOTION_AUTHORITY_DIGEST = sha256_hex(
    batch_task.QUALITY_PROMOTION_AUTHORITY_ID
)
_BATCH_TASK_PROGRAM_ID = "program:batch-task.v2"
_BATCH_TASK_FRAGMENT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C4.json"
)
_LEGACY_BATCH = "main/backend/app/successor_migration/legacy_agent_batch.py"
_BATCH_TASK_SUBMISSION_HANDLER_PATH = (
    "main/backend/app/successor_runtime/substrate/postgres/agent_batch_c4_3_handler.py"
)

PROJECT_KEY = "batch-task-local"
REGISTRY_REVISION = 3
RESOLVED_SCHEMA = "mrw_batch_task_local"
SCOPE_INCARNATION = "scope-inc-batch-task-local"
DEFAULT_BATCH_TASK_SCOPE_DIGEST = source_contracts.project_scope_digest(
    project_key=PROJECT_KEY,
    resolved_schema=RESOLVED_SCHEMA,
    project_registry_revision=REGISTRY_REVISION,
    incarnation=SCOPE_INCARNATION,
)


@dataclasses.dataclass(frozen=True, slots=True)
class _I1BatchTaskSourceCandidateView:
    """Deterministic C2 candidate snapshot used by the C4 fixture payloads."""

    catalog: Any
    source_items: tuple[Any, ...]


def _i1_batch_task_source_item(
    item_key: str, *, enabled: bool = True
) -> source_contracts.SourceItemDefinition:
    values = {
        "item_key": item_key,
        "channel_key": (
            "handler.cluster" if item_key.startswith("handler") else "market.default"
        ),
        "enabled": enabled,
        "params": {},
        "extra": {},
        "revision": REGISTRY_REVISION,
        "incarnation": "item-inc-batch-task-local",
    }
    values["content_digest"] = source_contracts.source_item_definition_content_digest(values)
    return source_contracts.source_item_definition_from_dict(values)


def _i1_batch_task_snapshot() -> _I1BatchTaskSourceCandidateView:
    catalog = source_contracts.build_channel_catalog_snapshot(
        revision=9,
        incarnation="channel-catalog-inc-batch-task-local",
        entries=(),
    )
    source_items = (
        _i1_batch_task_source_item("handler.cluster.news"),
        _i1_batch_task_source_item("market.default.tech"),
    )
    return _I1BatchTaskSourceCandidateView(catalog=catalog, source_items=source_items)


def _i1_batch_task_task() -> AgentBatchTask:
    return AgentBatchTask(
        task_id="search_1",
        channel="search.market",
        query_terms=("机器人",),
        max_items=20,
        provider="auto",
        language="zh",
        days_back=30,
        item_key=None,
        scope=None,
        platforms=(),
        override_params={},
    )


def build_deterministic_plan_payload(scope_digest: str) -> Annotated[
    BatchPlanPayload,
    "kit:prepared-command effect_boundary=successor_runtime.c4_assembly "
    "witness=test:test_c4_assembly_installs_with_production_fixture_builder",
]:
    """Build the deterministic batch-task plan payload for one exact scope."""

    payload = BatchPlanPayload(
        schema_version=batch_task.BATCH_PLAN_PAYLOAD_SCHEMA,
        operation_kind=batch_task.BATCH_PLAN_KIND,
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=scope_digest,
        tasks=(_i1_batch_task_task(),),
        retrieval_mode="hybrid",
        command="调研机器人产品、公司和最近动态",
        language="zh",
        coverage_axes=(),
        candidates=_i1_batch_task_snapshot(),
        limited_branching_enabled=False,
        max_source_tasks=2,
    )
    if payload.scope_digest != scope_digest:
        raise ValueError(
            "deterministic plan payload scope digest must equal the requested scope"
        )
    return payload


def build_deterministic_retry_payload(scope_digest: str) -> Annotated[
    RetryReducerInput,
    "kit:prepared-command effect_boundary=successor_runtime.c4_assembly "
    "witness=test:test_c4_assembly_installs_with_production_fixture_builder",
]:
    """Build the deterministic batch-task retry payload for one exact scope."""

    payload = RetryReducerInput(
        schema_version=batch_task.RETRY_REDUCER_PAYLOAD_SCHEMA,
        operation_kind=batch_task.RETRY_REDUCE_KIND,
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=scope_digest,
        tasks=(_i1_batch_task_task(),),
        critic=CriticDecision(
            score=0.5,
            next_action="retry_with_source_library",
            reason_codes=("source_backing_missing",),
            rewrite={},
        ),
        retry_action=RetryAction(
            action="attach_source_library",
            reason="source_backing_missing",
            channel="source_library",
            rewrite={
                "item_key": "handler.cluster.news",
                "query_terms": ("机器人",),
                "max_items": 20,
            },
        ),
        budget=RetryBudget(remaining=1, used=0, max_rounds=1),
        prior_attempt_ref="attempt:round-1",
        command="调研机器人",
        retry_enabled=True,
        dry_run=False,
    )
    if payload.scope_digest != scope_digest:
        raise ValueError(
            "deterministic retry payload scope digest must equal the requested scope"
        )
    return payload


def _payload_scope_digest(payload: Any) -> str:
    scope = getattr(payload, "scope_digest", None)
    if not isinstance(scope, str) or len(scope) != 64:
        raise ValueError("C4 canary payload requires an exact scope_digest")
    return scope


def _canary_handler(
    *,
    payload: Any,
    program_builder: Callable[..., Any],
    interpreter_profile_digest: str,
    handler_cls: type[Any],
    project_scope_digest: str,
    native_definition: Any,
) -> Any:
    """Build one exact canary closure from the deterministic payload."""

    deployment_catalog_digest = native_definition.source.deployment_catalog_digest

    if _payload_scope_digest(payload) != project_scope_digest:
        raise ValueError(
            "C4 canary payload scope digest must equal the assembly project scope digest"
        )
    bundle = native_definition.bundle
    catalog = native_definition.catalog
    registry = native_definition.registry
    program = program_builder(
        payload=payload,
        catalog=catalog,
        program_id=native_definition.source.program_id,
        project_key=payload.project_key,
        project_registry_revision=payload.registry_revision,
        project_scope_digest=project_scope_digest,
    )
    plan = compile_batch_task_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    contract_ref = program.root.operation.contract_ref
    payload_ref = program.root.operation.payload_ref
    binding = successor_binding(
        operation_contract_digest=contract_ref.contract_digest,
        interpreter_profile_digest=interpreter_profile_digest,
        deployment_catalog_digest=deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=authority_requirement_digest(),
    )
    return handler_cls(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=payload_ref,
        payload=payload,
        catalog=catalog,
        binding=binding,
        deployment_catalog_digest=deployment_catalog_digest,
    )


def _rollback_bindings(
    cell_ids: tuple[str, str, str],
) -> tuple[RollbackBindingDeclaration, ...]:
    plan_cell_id, retry_cell_id, submit_cell_id = cell_ids
    return (
        RollbackBindingDeclaration(
            cell_id=plan_cell_id,
            status="PRESENT",
            binding_refs=(_BATCH_TASK_FRAGMENT, _LEGACY_BATCH),
        ),
        RollbackBindingDeclaration(
            cell_id=retry_cell_id,
            status="PRESENT",
            binding_refs=(_BATCH_TASK_FRAGMENT, _LEGACY_BATCH),
        ),
        RollbackBindingDeclaration(
            cell_id=submit_cell_id,
            status="PRESENT",
            binding_refs=(_BATCH_TASK_FRAGMENT, _LEGACY_BATCH, _BATCH_TASK_SUBMISSION_HANDLER_PATH),
        ),
    )


def build_batch_task_assembly(
    *,
    uow_factory: Callable[[], RuntimeUnitOfWork],
    project_scope_digest: str,
    options: BatchTaskAssemblyOptions | None = None,
    native_definition: Any | None = None,
) -> Annotated[
    FamilyAssembly,
    "kit:prepared-command effect_boundary=successor_runtime.c4_assembly "
    "witness=test:test_c4_assembly_installs_with_production_fixture_builder",
]:
    """Install submission and, when payloads are supplied, the canaries."""

    require_assembly_digest(project_scope_digest, "batch task assembly scope digest")
    opts = options or BatchTaskAssemblyOptions()
    if native_definition is None:
        native_result = compile_batch_task_native_contribution(DEFAULT_BATCH_TASK_NATIVE_SOURCE)
        if isinstance(native_result, Failure):
            raise ValueError(native_result.message)
        native_definition = native_result.definition
    cell_ids = tuple(
        operation.operation_id for operation in native_definition.source.operations
    )
    if len(cell_ids) != 3:
        raise ValueError("batch task native definition requires three ordered cells")
    plan_cell_id, retry_cell_id, submit_cell_id = cell_ids
    cells: list[CellBinding] = []
    handlers: list[Any] = []

    if opts.plan_payload is None:
        cells.append(
            CellBinding(
                cell_id=plan_cell_id,
                family_id=batch_task.BATCH_TASK_FAMILY_ID,
                status="FIXTURE_CLOSURE_REQUIRED",
                operation_contract_refs=(batch_task.BATCH_PLAN_KIND,),
                recovery_binding_ref="mrw.batch.task-plan.recovery.v2",
                required_wiring=("plan handler installation", "recovery binding"),
                note=(
                    "FIXTURE_CLOSURE_REQUIRED: C4_1_BatchPlanRuntimeHandler needs "
                    "a deterministic plan_payload fixture closure; "
                    "options.plan_payload not provided"
                ),
            )
        )
    else:
        handler = _canary_handler(
            native_definition=native_definition,
            payload=opts.plan_payload,
            program_builder=build_batch_task_plan_program,
            interpreter_profile_digest=successor_plan_interpreter_profile_digest(),
            handler_cls=BatchTaskPlanRuntimeHandler,
            project_scope_digest=project_scope_digest,
        )
        handlers.append(handler)
        cells.append(
            CellBinding(
                cell_id=plan_cell_id,
                family_id=batch_task.BATCH_TASK_FAMILY_ID,
                status="INSTALLED",
                operation_contract_refs=(batch_task.BATCH_PLAN_KIND,),
                handler_binding_digest=handler.handler_binding_digest,
                recovery_binding_ref="mrw.batch.task-plan.recovery.v2",
                required_wiring=("plan handler installation", "recovery binding"),
                note="LOCAL_OFFLINE deterministic fixture closure only",
            )
        )

    if opts.retry_payload is None:
        cells.append(
            CellBinding(
                cell_id=retry_cell_id,
                family_id=batch_task.BATCH_TASK_FAMILY_ID,
                status="FIXTURE_CLOSURE_REQUIRED",
                operation_contract_refs=(batch_task.RETRY_REDUCE_KIND,),
                recovery_binding_ref="mrw.batch.retry-action.recovery.v2",
                required_wiring=(
                    "retry reducer handler installation",
                    "recovery binding",
                ),
                note=(
                    "FIXTURE_CLOSURE_REQUIRED: C4_2_RetryRuntimeHandler needs "
                    "a deterministic retry_payload fixture closure; "
                    "options.retry_payload not provided"
                ),
            )
        )
    else:
        handler = _canary_handler(
            native_definition=native_definition,
            payload=opts.retry_payload,
            program_builder=build_batch_task_retry_program,
            interpreter_profile_digest=successor_retry_interpreter_profile_digest(),
            handler_cls=BatchTaskRetryRuntimeHandler,
            project_scope_digest=project_scope_digest,
        )
        handlers.append(handler)
        cells.append(
            CellBinding(
                cell_id=retry_cell_id,
                family_id=batch_task.BATCH_TASK_FAMILY_ID,
                status="INSTALLED",
                operation_contract_refs=(batch_task.RETRY_REDUCE_KIND,),
                handler_binding_digest=handler.handler_binding_digest,
                recovery_binding_ref="mrw.batch.retry-action.recovery.v2",
                required_wiring=(
                    "retry reducer handler installation",
                    "recovery binding",
                ),
                note="LOCAL_OFFLINE deterministic fixture closure only",
            )
        )

    bundle = native_definition.bundle
    catalog = native_definition.catalog
    contract_ref = catalog.lookup(batch_task.SUBMISSION_KIND)
    if contract_ref is None:
        raise KeyError(
            f"batch task submission contract not found: {batch_task.SUBMISSION_KIND}"
        )
    submission_binding = successor_binding(
        operation_contract_digest=contract_ref.contract_digest,
        interpreter_profile_digest=successor_submission_interpreter_profile_digest(),
        deployment_catalog_digest=native_definition.source.deployment_catalog_digest,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=authority_requirement_digest(),
    )
    submission_definition = native_definition.operation_by_slot("SUBMIT")
    if (
        submission_definition is None
        or submission_definition.source.receipt_codec_id is None
        or submission_definition.source.receipt_provenance_schema is None
    ):
        raise ValueError("batch task submission receipt declaration is missing")
    submission_handler = BatchTaskSubmissionStoreRehydratedHandler(
        uow_factory=uow_factory,
        handler_binding_digest=submission_binding.binding_digest,
        interpreter_profile_digest=submission_binding.interpreter_profile_digest,
        operation_contract_digest=contract_ref.contract_digest,
        deployment_catalog_digest=native_definition.source.deployment_catalog_digest,
        receipt_codec_id=submission_definition.source.receipt_codec_id,
        receipt_provenance_schema=(
            submission_definition.source.receipt_provenance_schema
        ),
    )
    handlers.append(submission_handler)
    quality_installed = opts.quality_evidence is not None
    if quality_installed:
        quality_binding = successor_binding(
            operation_contract_digest=native_definition.source.quality_promotion.operation_digest,
            interpreter_profile_digest=native_definition.source.quality_promotion.interpreter_digest,
            deployment_catalog_digest=native_definition.source.deployment_catalog_digest,
            project_scope_digest=project_scope_digest,
            authority_requirement_digest=native_definition.source.quality_promotion.authority_digest,
        )
        quality_handler = BatchTaskQualityPromotionRuntimeHandler(
            evidence=opts.quality_evidence,
            handler_binding_digest=quality_binding.binding_digest,
            interpreter_profile_digest=quality_binding.interpreter_profile_digest,
            operation_contract_digest=quality_binding.operation_contract_digest,
            deployment_catalog_digest=quality_binding.deployment_catalog_digest,
        )
        handlers.append(quality_handler)
    cells.append(
        CellBinding(
            cell_id=submit_cell_id,
            family_id=batch_task.BATCH_TASK_FAMILY_ID,
            status="INSTALLED",
            operation_contract_refs=(batch_task.SUBMISSION_KIND,),
            handler_binding_digest=submission_handler.handler_binding_digest,
            recovery_binding_ref="mrw.batch.task-submission.recovery.v2",
            required_wiring=(
                "submission handler installation",
                "readback + recovery binding",
            ),
            note=(
                "LOCAL_OFFLINE store-rehydrated handler; digest from "
                "build_successor_agent_batch_c4_submission_binding"
                + (
                    "; QUALITY_PROMOTION_HANDLER_INSTALLED_READBACK_ONLY"
                    if quality_installed
                    else ""
                )
            ),
        )
    )

    return FamilyAssembly(
        family_id=batch_task.BATCH_TASK_FAMILY_ID,
        cells=tuple(cells),
        handlers=tuple(handlers),
        rollback_bindings=_rollback_bindings(cell_ids),
    )


__all__ = [
    "DEFAULT_BATCH_TASK_SCOPE_DIGEST",
    "PROJECT_KEY",
    "REGISTRY_REVISION",
    "RESOLVED_SCHEMA",
    "SCOPE_INCARNATION",
    "build_batch_task_assembly",
    "build_deterministic_plan_payload",
    "build_deterministic_retry_payload",
]
