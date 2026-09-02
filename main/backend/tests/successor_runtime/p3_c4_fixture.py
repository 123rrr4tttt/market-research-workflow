"""Shared deterministic fixtures for the P3 C4 agent-batch family line."""

from __future__ import annotations

import dataclasses
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
    build_agent_batch_c4_bundle,
    build_agent_batch_c4_catalog,
    build_agent_batch_c4_registry,
)
from app.successor_runtime.capabilities.agent_batch_c4_program import (
    build_agent_batch_c4_1_program,
    build_agent_batch_c4_2_program,
    compile_agent_batch_c4_program,
)
from app.successor_runtime.capabilities.checksum import sha256_hex
from app.successor_runtime.capabilities.source_library_c2_shared import (
    build_channel_catalog_snapshot,
    project_scope_digest,
)

PROJECT_KEY = "p3-c4-demo"
REGISTRY_REVISION = 3
RESOLVED_SCHEMA = "mrw_p3_c4_demo"
SCOPE_INCARNATION = "scope-inc-c4"
SCOPE_DIGEST = project_scope_digest(
    PROJECT_KEY,
    RESOLVED_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
DEPLOYMENT_CATALOG_DIGEST = sha256_hex(b"mrw.successor.deployment-catalog.c4.v1")
PROGRAM_ID = "program:p3-c4-family"


def bundle() -> Any:
    return build_agent_batch_c4_bundle()


def catalog() -> Any:
    return build_agent_batch_c4_catalog(bundle())


def registry() -> Any:
    return build_agent_batch_c4_registry(bundle())


def contract_ref(kind: str) -> Any:
    ref = catalog().lookup(kind)
    if ref is None:
        raise KeyError(kind)
    return ref


def _source_item(
    item_key: str, *, enabled: bool = True
) -> c2_shared.SourceItemDefinition:
    values = {
        "item_key": item_key,
        "channel_key": "handler.cluster"
        if item_key.startswith("handler")
        else "market.default",
        "enabled": enabled,
        "params": {},
        "extra": {},
        "revision": 3,
        "incarnation": "item-inc-c4",
    }
    values["content_digest"] = c2_shared.source_item_definition_content_digest(values)
    return c2_shared.source_item_definition_from_dict(values)


@dataclasses.dataclass(frozen=True, slots=True)
class C2ProducerSnapshotView:
    """Fixture binding the real C2 producer snapshot and item digests."""

    catalog: c2_shared.ChannelCatalogSnapshot
    source_items: tuple[c2_shared.SourceItemDefinition, ...]


def c2_snapshot(
    *,
    item_keys: tuple[str, ...] = ("handler.cluster.news", "market.default.tech"),
    catalog_revision: int = 9,
    enabled_keys: tuple[str, ...] | None = None,
) -> C2ProducerSnapshotView:
    catalog = build_channel_catalog_snapshot(
        revision=catalog_revision,
        incarnation="channel-catalog-inc-c4",
        entries=(),
    )
    disabled = set(item_keys) - set(enabled_keys or item_keys)
    source_items = tuple(
        _source_item(item_key, enabled=item_key not in disabled)
        for item_key in item_keys
    )
    return C2ProducerSnapshotView(catalog=catalog, source_items=source_items)


def _task(**overrides: Any) -> AgentBatchTask:
    values = {
        "task_id": "search_1",
        "channel": "search.market",
        "query_terms": ("机器人",),
        "max_items": 20,
        "provider": "auto",
        "language": "zh",
        "days_back": 30,
        "item_key": None,
        "scope": None,
        "platforms": (),
        "override_params": {},
    }
    values.update(overrides)
    return AgentBatchTask(**values)


def plan_payload(
    *,
    tasks: tuple[AgentBatchTask, ...] | None = None,
    retrieval_mode: str = "hybrid",
    command: str = "调研机器人产品、公司和最近动态",
    limited_branching: bool = False,
    candidates: Any | None = None,
    max_source_tasks: int = 2,
) -> BatchPlanPayload:
    return BatchPlanPayload(
        schema_version=c4.BATCH_PLAN_PAYLOAD_SCHEMA,
        operation_kind=c4.BATCH_PLAN_KIND,
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        tasks=tasks if tasks is not None else (_task(),),
        retrieval_mode=retrieval_mode,
        command=command,
        language="zh",
        coverage_axes=(),
        candidates=candidates or c2_snapshot(),
        limited_branching_enabled=limited_branching,
        max_source_tasks=max_source_tasks,
    )


def plan_program_and_plan(payload: BatchPlanPayload) -> tuple[Any, Any, Any, Any]:
    program = build_agent_batch_c4_1_program(
        payload=payload,
        catalog=catalog(),
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_agent_batch_c4_program(
        program,
        catalog(),
        operation_contracts=registry(),
    )
    ref = program.root.operation.contract_ref
    payload_ref = program.root.operation.payload_ref
    return program, plan, ref, payload_ref


def retry_payload(
    *,
    tasks: tuple[AgentBatchTask, ...] | None = None,
    action: RetryAction | None = None,
    score: float = 0.5,
    next_action: str = "retry_with_source_library",
    reason_codes: tuple[str, ...] = ("source_backing_missing",),
    budget: RetryBudget | None = None,
    retry_enabled: bool = True,
    dry_run: bool = False,
) -> RetryReducerInput:
    return RetryReducerInput(
        schema_version=c4.RETRY_REDUCER_PAYLOAD_SCHEMA,
        operation_kind=c4.RETRY_REDUCE_KIND,
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        tasks=tasks if tasks is not None else (_task(),),
        critic=CriticDecision(
            score=score,
            next_action=next_action,
            reason_codes=reason_codes,
            rewrite={},
        ),
        retry_action=action
        or RetryAction(
            action="attach_source_library",
            reason="source_backing_missing",
            channel="source_library",
            rewrite={
                "item_key": "handler.cluster.news",
                "query_terms": ("机器人",),
                "max_items": 20,
            },
        ),
        budget=budget or RetryBudget(remaining=1, used=0, max_rounds=1),
        prior_attempt_ref="attempt:round-1",
        command="调研机器人",
        retry_enabled=retry_enabled,
        dry_run=dry_run,
    )


def retry_program_and_plan(payload: RetryReducerInput) -> tuple[Any, Any, Any, Any]:
    program = build_agent_batch_c4_2_program(
        payload=payload,
        catalog=catalog(),
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_agent_batch_c4_program(
        program,
        catalog(),
        operation_contracts=registry(),
    )
    ref = program.root.operation.contract_ref
    payload_ref = program.root.operation.payload_ref
    return program, plan, ref, payload_ref


def payload_value_id(program: Any) -> str:
    return program.root.operation.payload_ref.value_id


def asdict(value: Any) -> dict[str, Any]:
    return dataclasses.asdict(value)
