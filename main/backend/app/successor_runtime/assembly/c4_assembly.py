"""C4 family assembly: exact handler installation for the three C4 cells.

C4.3 is always installed as the store-rehydrated submission handler.  C4.1 and
C4.2 canary handlers are installed only when the caller supplies the exact
deterministic payload; otherwise they are fail-closed as
``FIXTURE_CLOSURE_REQUIRED``.

The C4 deployment catalog digest has no production constant yet.  The existing
canary fixture (``p3_c4_fixture.py``, consumed by ``test_p3_c4_canary.py``)
derives it from the exact identity ``mrw.successor.deployment-catalog.c4.v1``;
this module repeats that identity without importing test code.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from app.successor_runtime.capabilities import agent_batch_c4 as c4
from app.successor_runtime.capabilities import source_library_c2_shared as c2_shared
from app.successor_runtime.capabilities.agent_batch_c4 import (
    AgentBatchTask,
    BatchPlanPayload,
    CriticDecision,
    RetryAction,
    RetryBudget,
    RetryReducerInput,
)
from app.successor_runtime.capabilities.agent_batch_c4_interpreters import (
    authority_requirement_digest,
    successor_plan_interpreter_profile_digest,
    successor_retry_interpreter_profile_digest,
    successor_submission_interpreter_profile_digest,
)
from app.successor_runtime.capabilities.agent_batch_c4_program import (
    build_agent_batch_c4_1_program,
    build_agent_batch_c4_2_program,
    compile_agent_batch_c4_program,
)
from app.successor_runtime.substrate.postgres.agent_batch_c4_3_handler import (
    C4_3SubmissionStoreRehydratedHandler,
)
from app.successor_runtime.substrate.postgres.agent_batch_c4_canary import (
    C4_1_BatchPlanRuntimeHandler,
    C4_2_RetryRuntimeHandler,
)
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork

from .base import (
    C4AssemblyOptions,
    CellBinding,
    FamilyAssembly,
    RollbackBindingDeclaration,
    require_assembly_digest,
    sha256_hex,
    successor_binding,
)

_C4_DEPLOYMENT_CATALOG_DIGEST = sha256_hex("mrw.successor.deployment-catalog.c4.v1")
_C4_PROGRAM_ID = "program:i1-c4-family"
_C4_FRAGMENT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C4.json"
)
_LEGACY_AGENT_BATCH = "main/backend/app/successor_migration/legacy_agent_batch.py"
_C4_3_HANDLER = (
    "main/backend/app/successor_runtime/substrate/postgres/agent_batch_c4_3_handler.py"
)

PROJECT_KEY = "i1-local-c4"
REGISTRY_REVISION = 3
RESOLVED_SCHEMA = "mrw_i1_local_c4"
SCOPE_INCARNATION = "scope-inc-i1-c4"
I1_C4_SCOPE_DIGEST = c2_shared.project_scope_digest(
    project_key=PROJECT_KEY,
    resolved_schema=RESOLVED_SCHEMA,
    project_registry_revision=REGISTRY_REVISION,
    incarnation=SCOPE_INCARNATION,
)


@dataclasses.dataclass(frozen=True, slots=True)
class _I1C4SourceCandidateView:
    """Deterministic C2 candidate snapshot used by the C4 fixture payloads."""

    catalog: Any
    source_items: tuple[Any, ...]


def _i1_c4_source_item(
    item_key: str, *, enabled: bool = True
) -> c2_shared.SourceItemDefinition:
    values = {
        "item_key": item_key,
        "channel_key": (
            "handler.cluster" if item_key.startswith("handler") else "market.default"
        ),
        "enabled": enabled,
        "params": {},
        "extra": {},
        "revision": REGISTRY_REVISION,
        "incarnation": "item-inc-i1-c4",
    }
    values["content_digest"] = c2_shared.source_item_definition_content_digest(values)
    return c2_shared.source_item_definition_from_dict(values)


def _i1_c4_snapshot() -> _I1C4SourceCandidateView:
    catalog = c2_shared.build_channel_catalog_snapshot(
        revision=9,
        incarnation="channel-catalog-inc-i1-c4",
        entries=(),
    )
    source_items = (
        _i1_c4_source_item("handler.cluster.news"),
        _i1_c4_source_item("market.default.tech"),
    )
    return _I1C4SourceCandidateView(catalog=catalog, source_items=source_items)


def _i1_c4_task() -> AgentBatchTask:
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


def build_deterministic_plan_payload(scope_digest: str) -> BatchPlanPayload:
    """Build the deterministic I1 C4.1 plan payload for one exact scope."""

    payload = BatchPlanPayload(
        schema_version=c4.BATCH_PLAN_PAYLOAD_SCHEMA,
        operation_kind=c4.BATCH_PLAN_KIND,
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=scope_digest,
        tasks=(_i1_c4_task(),),
        retrieval_mode="hybrid",
        command="调研机器人产品、公司和最近动态",
        language="zh",
        coverage_axes=(),
        candidates=_i1_c4_snapshot(),
        limited_branching_enabled=False,
        max_source_tasks=2,
    )
    if payload.scope_digest != scope_digest:
        raise ValueError(
            "deterministic plan payload scope digest must equal the requested scope"
        )
    return payload


def build_deterministic_retry_payload(scope_digest: str) -> RetryReducerInput:
    """Build the deterministic I1 C4.2 retry payload for one exact scope."""

    payload = RetryReducerInput(
        schema_version=c4.RETRY_REDUCER_PAYLOAD_SCHEMA,
        operation_kind=c4.RETRY_REDUCE_KIND,
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=scope_digest,
        tasks=(_i1_c4_task(),),
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
) -> Any:
    """Build one exact canary closure from the deterministic payload."""

    if _payload_scope_digest(payload) != project_scope_digest:
        raise ValueError(
            "C4 canary payload scope digest must equal the assembly project scope digest"
        )
    bundle = c4.build_agent_batch_c4_bundle()
    catalog = c4.build_agent_batch_c4_catalog(bundle)
    registry = c4.build_agent_batch_c4_registry(bundle)
    program = program_builder(
        payload=payload,
        catalog=catalog,
        program_id=_C4_PROGRAM_ID,
        project_key=payload.project_key,
        project_registry_revision=payload.registry_revision,
        project_scope_digest=project_scope_digest,
    )
    plan = compile_agent_batch_c4_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    contract_ref = program.root.operation.contract_ref
    payload_ref = program.root.operation.payload_ref
    binding = successor_binding(
        operation_contract_digest=contract_ref.contract_digest,
        interpreter_profile_digest=interpreter_profile_digest,
        deployment_catalog_digest=_C4_DEPLOYMENT_CATALOG_DIGEST,
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
        deployment_catalog_digest=_C4_DEPLOYMENT_CATALOG_DIGEST,
    )


def _rollback_bindings() -> tuple[RollbackBindingDeclaration, ...]:
    return (
        RollbackBindingDeclaration(
            cell_id="C4.1",
            status="PRESENT",
            binding_refs=(_C4_FRAGMENT, _LEGACY_AGENT_BATCH),
        ),
        RollbackBindingDeclaration(
            cell_id="C4.2",
            status="PRESENT",
            binding_refs=(_C4_FRAGMENT, _LEGACY_AGENT_BATCH),
        ),
        RollbackBindingDeclaration(
            cell_id="C4.3",
            status="PRESENT",
            binding_refs=(_C4_FRAGMENT, _LEGACY_AGENT_BATCH, _C4_3_HANDLER),
        ),
    )


def build_c4_assembly(
    *,
    uow_factory: Callable[[], RuntimeUnitOfWork],
    project_scope_digest: str,
    options: C4AssemblyOptions | None = None,
) -> FamilyAssembly:
    """Install the C4.3 store handler and, when payloads are supplied, the canaries."""

    require_assembly_digest(project_scope_digest, "C4 assembly project scope digest")
    opts = options or C4AssemblyOptions()
    cells: list[CellBinding] = []
    handlers: list[Any] = []

    if opts.plan_payload is None:
        cells.append(
            CellBinding(
                cell_id="C4.1",
                family_id="C4",
                status="FIXTURE_CLOSURE_REQUIRED",
                operation_contract_refs=("agent_batch.build_batch_plan.v1",),
                recovery_binding_ref="mrw.successor.agent-batch.c4-1.recovery.v1",
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
            payload=opts.plan_payload,
            program_builder=build_agent_batch_c4_1_program,
            interpreter_profile_digest=successor_plan_interpreter_profile_digest(),
            handler_cls=C4_1_BatchPlanRuntimeHandler,
            project_scope_digest=project_scope_digest,
        )
        handlers.append(handler)
        cells.append(
            CellBinding(
                cell_id="C4.1",
                family_id="C4",
                status="INSTALLED",
                operation_contract_refs=("agent_batch.build_batch_plan.v1",),
                handler_binding_digest=handler.handler_binding_digest,
                recovery_binding_ref="mrw.successor.agent-batch.c4-1.recovery.v1",
                required_wiring=("plan handler installation", "recovery binding"),
                note="LOCAL_OFFLINE deterministic fixture closure only",
            )
        )

    if opts.retry_payload is None:
        cells.append(
            CellBinding(
                cell_id="C4.2",
                family_id="C4",
                status="FIXTURE_CLOSURE_REQUIRED",
                operation_contract_refs=("agent_batch.reduce_retry_action.v1",),
                recovery_binding_ref="mrw.successor.agent-batch.c4-2.recovery.v1",
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
            payload=opts.retry_payload,
            program_builder=build_agent_batch_c4_2_program,
            interpreter_profile_digest=successor_retry_interpreter_profile_digest(),
            handler_cls=C4_2_RetryRuntimeHandler,
            project_scope_digest=project_scope_digest,
        )
        handlers.append(handler)
        cells.append(
            CellBinding(
                cell_id="C4.2",
                family_id="C4",
                status="INSTALLED",
                operation_contract_refs=("agent_batch.reduce_retry_action.v1",),
                handler_binding_digest=handler.handler_binding_digest,
                recovery_binding_ref="mrw.successor.agent-batch.c4-2.recovery.v1",
                required_wiring=(
                    "retry reducer handler installation",
                    "recovery binding",
                ),
                note="LOCAL_OFFLINE deterministic fixture closure only",
            )
        )

    bundle = c4.build_agent_batch_c4_bundle()
    catalog = c4.build_agent_batch_c4_catalog(bundle)
    contract_ref = catalog.lookup(c4.SUBMISSION_KIND)
    if contract_ref is None:
        raise KeyError(f"C4.3 submission contract not found: {c4.SUBMISSION_KIND}")
    submission_binding = successor_binding(
        operation_contract_digest=contract_ref.contract_digest,
        interpreter_profile_digest=successor_submission_interpreter_profile_digest(),
        deployment_catalog_digest=_C4_DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=authority_requirement_digest(),
    )
    submission_handler = C4_3SubmissionStoreRehydratedHandler(
        uow_factory=uow_factory,
        handler_binding_digest=submission_binding.binding_digest,
        interpreter_profile_digest=submission_binding.interpreter_profile_digest,
        operation_contract_digest=contract_ref.contract_digest,
        deployment_catalog_digest=_C4_DEPLOYMENT_CATALOG_DIGEST,
    )
    handlers.append(submission_handler)
    cells.append(
        CellBinding(
            cell_id="C4.3",
            family_id="C4",
            status="INSTALLED",
            operation_contract_refs=("agent_batch.submit.v1",),
            handler_binding_digest=submission_handler.handler_binding_digest,
            recovery_binding_ref="mrw.successor.agent-batch.c4-3.recovery.v1",
            required_wiring=(
                "submission handler installation",
                "readback + recovery binding",
            ),
            note=(
                "LOCAL_OFFLINE store-rehydrated handler; digest from "
                "build_successor_agent_batch_c4_submission_binding"
            ),
        )
    )

    return FamilyAssembly(
        family_id="C4",
        cells=tuple(cells),
        handlers=tuple(handlers),
        rollback_bindings=_rollback_bindings(),
    )


__all__ = [
    "I1_C4_SCOPE_DIGEST",
    "PROJECT_KEY",
    "REGISTRY_REVISION",
    "RESOLVED_SCHEMA",
    "SCOPE_INCARNATION",
    "build_c4_assembly",
    "build_deterministic_plan_payload",
    "build_deterministic_retry_payload",
]
