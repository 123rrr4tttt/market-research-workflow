"""Thin C4/P3 family fragment config for the shared family generator.

This module declares only the C4 family data and differences: family identity,
exact binding targets, the C4.1-C4.3 cell declarations and the family
observation glue that calls the existing C4 capability modules.  No full
fragment generator pipeline is copied; canonical JSON/digest, path
confinement, authority ceiling, determinism and the read-only check gate live
in ``shared_family_generator``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.successor_migration.legacy_agent_batch import (
    LegacyAgentBatchPlanAdapter,
    LegacyAgentBatchRetryAdapter,
)
from app.successor_runtime.capabilities import agent_batch_c4 as c4
from app.successor_runtime.capabilities import (
    agent_batch_c4_interpreters as c4i,
)
from app.successor_runtime.capabilities import agent_batch_c4_program as c4p
from app.successor_runtime.capabilities import source_library_c2_shared as c2_shared
from app.successor_runtime.capabilities.agent_batch_c4_program import (
    build_agent_batch_c4_3_program,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_library_c2_1 import (
    build_channel_catalog_snapshot,
    project_scope_digest,
)
from app.successor_runtime.specification.shared_family_generator import (
    BindingsByKind,
    BindingTarget,
    FamilyFragmentConfig,
)
from tests.successor_runtime.p3_c4_fixture import C2ProducerSnapshotView

PROJECT_KEY = "p3-c4-fragment"
REGISTRY_REVISION = 3
RESOLVED_SCHEMA = "mrw_p3_c4_fragment"
SCOPE_INCARNATION = "scope-inc-c4-fragment"
SCOPE_DIGEST = project_scope_digest(
    PROJECT_KEY, RESOLVED_SCHEMA, REGISTRY_REVISION, SCOPE_INCARNATION
)

FRAGMENT_ID = "p3-c4-family-local-implementation"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p3_fragment.v1"
FRAGMENT_PHASE = "P3"
FRAGMENT_FAMILY = "C4"
FRAGMENT_STATUS = "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"

_EVIDENCE_ROOT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
FRAGMENT_OUTPUT_REL = f"{_EVIDENCE_ROOT}/p3-fragments/C4.json"

AUTHORITY = {
    "production_canonical_write": False,
    "live_provider": False,
    "external_delivery": False,
    "live_credential": False,
    "network": False,
    "cutover": False,
    "authority_transfer": False,
    "legacy_retired": False,
    "p3_promotion": False,
}

OPEN_FINDINGS = (
    {
        "id": "C4_3_DURABLE_ADOPTION_NOT_PROMOTED",
        "severity": "P1",
        "description": (
            "real PostgreSQL idempotency reserve/replay/conflict/terminal, "
            "crash-before-terminal receipt adoption and rollback rehearsal "
            "are verified on the disposable mrw_p3_c4_worker_test "
            "database, but submission adoption, restart recovery and "
            "concurrent duplicate-request claim remain unpromoted; no "
            "promotion claim is made by this fragment"
        ),
    },
    {
        "id": "P3_AUTHORITY_RECORD_DIVERGENCE",
        "severity": "P0",
        "description": (
            "frozen contract and mutable ledger authority still "
            "diverge; promotion requires root/supervisor authority record"
        ),
    },
    {
        "id": "P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED",
        "severity": "P1",
        "description": (
            "capability surface remains untracked; exact review tree pending"
        ),
    },
)

_SOURCE_BINDINGS = (
    BindingTarget(
        f"{_EVIDENCE_ROOT}/P1FunctorizationEligibility.v1.json", "p1_eligibility"
    ),
    BindingTarget(f"{_EVIDENCE_ROOT}/p1-fragments/C4.json", "p1_fragment"),
    BindingTarget(
        "main/backend/app/services/agent_batch/agent_loop.py",
        "legacy_donor_c4_1_c4_2",
    ),
    BindingTarget(
        "main/backend/app/services/agent_batch/task_contract.py",
        "legacy_donor_c4_1_c4_2_c4_3",
    ),
    BindingTarget("main/backend/app/api/agent_batch.py", "legacy_donor_c4_3"),
)

_IMPLEMENTATION_BINDINGS = (
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/agent_batch_c4.py",
        "c4_contracts",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/agent_batch_c4_program.py",
        "c4_program",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/agent_batch_c4_interpreters.py",
        "c4_interpreters",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/legacy_agent_batch.py",
        "c4_legacy_adapter",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/postgres/agent_batch_c4.py",
        "c4_3_submission_repository_scaffold",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/postgres/agent_batch_c4_canary.py",
        "c4_canary_handler",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/postgres/agent_batch_c4_3_handler.py",
        "c4_3_store_rehydrated_handler",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/language/compile.py",
        "shared_compiler_traversal_dependency",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/language/program.py",
        "shared_program_traverse_ordered_dependency",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/postgres/idempotency.py",
        "shared_idempotency_repository_dependency",
    ),
    BindingTarget(
        "main/backend/scripts/generate_successor_p3_c4_fragment.py",
        "evidence_generator",
    ),
)

_TEST_BINDINGS = (
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c4_1_plan.py",
        "c4_1_plan",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c4_1_program.py",
        "c4_1_program",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c4_1_parity.py",
        "c4_1_parity",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c4_2_retry_reducer.py",
        "c4_2_retry_reducer",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c4_3_submission.py",
        "c4_3_submission",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c4_canary.py",
        "c4_canary",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c4_4_postgres.py",
        "c4_3_postgres_idempotency",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c4_5_runtime_postgres.py",
        "c4_3_runtime_node_postgres",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c4_evidence_generator.py",
        "c4_evidence_generator",
    ),
)


def _p1_cells(root: Path) -> dict[str, dict[str, Any]]:
    artifact = json.loads(
        (root / _EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json").read_text(
            encoding="utf-8"
        )
    )
    return {str(cell["cell"]): cell for cell in artifact["cells"]}


def _p1_cell_digest(root: Path, cell_id: str) -> str:
    cell = _p1_cells(root)[cell_id]
    return content_digest(cell)


def _c2_snapshot() -> C2ProducerSnapshotView:
    catalog = build_channel_catalog_snapshot(
        revision=9,
        incarnation="channel-catalog-inc-c4-fragment",
        entries=(),
    )
    source_items = []
    for item_key in ("handler.cluster.news", "market.default.tech"):
        values = {
            "item_key": item_key,
            "channel_key": "handler.cluster"
            if item_key.startswith("handler")
            else "market.default",
            "enabled": True,
            "params": {},
            "extra": {},
            "revision": 3,
            "incarnation": "item-inc-c4-fragment",
        }
        values["content_digest"] = c2_shared.source_item_definition_content_digest(
            values
        )
        source_items.append(c2_shared.source_item_definition_from_dict(values))
    return C2ProducerSnapshotView(catalog=catalog, source_items=tuple(source_items))


def _task(**overrides: Any) -> c4.AgentBatchTask:
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
    return c4.AgentBatchTask(**values)


def _plan_payload() -> c4.BatchPlanPayload:
    return c4.BatchPlanPayload(
        schema_version=c4.BATCH_PLAN_PAYLOAD_SCHEMA,
        operation_kind=c4.BATCH_PLAN_KIND,
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        tasks=(_task(),),
        retrieval_mode="hybrid",
        command="调研机器人产品、公司和厂商",
        language="zh",
        coverage_axes=(),
        candidates=_c2_snapshot(),
        limited_branching_enabled=False,
        max_source_tasks=2,
    )


def _retry_payload() -> c4.RetryReducerInput:
    return c4.RetryReducerInput(
        schema_version=c4.RETRY_REDUCER_PAYLOAD_SCHEMA,
        operation_kind=c4.RETRY_REDUCE_KIND,
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        tasks=(_task(),),
        critic=c4.CriticDecision(
            score=0.5,
            next_action="retry_with_source_library",
            reason_codes=("source_backing_missing",),
            rewrite={},
        ),
        retry_action=c4.RetryAction(
            action="attach_source_library",
            reason="source_backing_missing",
            channel="source_library",
            rewrite={
                "item_key": "handler.cluster.news",
                "query_terms": ("机器人",),
                "max_items": 20,
            },
        ),
        budget=c4.RetryBudget(remaining=1, used=0, max_rounds=1),
        prior_attempt_ref="attempt:p3-c4-fragment:round-1",
        command="调研机器人",
        retry_enabled=True,
        dry_run=False,
    )


def _program_and_plan_digests(payload: Any, builder: Any) -> tuple[str, str]:
    bundle = c4.build_agent_batch_c4_bundle()
    catalog = c4.build_agent_batch_c4_catalog(bundle)
    registry = c4.build_agent_batch_c4_registry(bundle)
    program = builder(
        payload=payload,
        catalog=catalog,
        program_id="p3-c4-fragment.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    compiled = c4p.compile_agent_batch_c4_program(
        program, catalog, operation_contracts=registry
    )
    return program.program_digest, compiled.plan_digest


def _c4_1_plan_observation() -> tuple[dict[str, object], dict[str, object]]:
    payload = _plan_payload()
    program_digest, plan_digest = _program_and_plan_digests(
        payload, c4p.build_agent_batch_c4_1_program
    )
    bundle = c4.build_agent_batch_c4_bundle()
    catalog = c4.build_agent_batch_c4_catalog(bundle)
    registry = c4.build_agent_batch_c4_registry(bundle)
    traversal_program = c4p.build_agent_batch_c4_1_traversal_program(
        payloads=[payload],
        catalog=catalog,
        program_id="p3-c4-fragment.traverse",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    traversal_binding = c4p.traversal_shape_binding([payload])
    traversal_plan = c4p.compile_agent_batch_c4_program(
        traversal_program,
        catalog,
        operation_contracts=registry,
    )
    successor = c4.build_batch_plan(payload)
    legacy_adapter = LegacyAgentBatchPlanAdapter()
    legacy = legacy_adapter.build_plan(
        payload,
        candidate_item_keys=tuple(
            item.item_key for item in payload.candidates.source_items
        ),
    )
    return {
        "program_digest": program_digest,
        "plan_digest": plan_digest,
        "traversal_program_digest": traversal_program.program_digest,
        "traversal_plan_digest": traversal_plan.plan_digest,
        "traversal_shape_digest": traversal_binding["traversal_shape_digest"],
        "traversal_element_count": traversal_binding["traversal_element_count"],
        "result_digest": successor.result_digest,
        "ordered_tasks": len(successor.tasks),
        "supplementation_enabled": successor.supplementation.enabled,
        "branching_enabled": successor.branching.enabled,
        "branching_reason": successor.branching.reason,
        "source_mode_present": False,
    }, {
        "interpreter_id": legacy_adapter.interpreter_id,
        "result_digest": legacy.result_digest,
        "ordered_tasks": len(legacy.tasks),
        "supplementation_enabled": legacy.supplementation.enabled,
        "provider_calls": 0,
    }


def _c4_2_retry_observation() -> tuple[dict[str, object], dict[str, object]]:
    payload = _retry_payload()
    program_digest, plan_digest = _program_and_plan_digests(
        payload, c4p.build_agent_batch_c4_2_program
    )
    successor = c4.reduce_retry_action(payload)
    assert successor.attempt_intent is not None
    legacy_adapter = LegacyAgentBatchRetryAdapter()
    legacy = legacy_adapter.reduce(payload)
    assert legacy.attempt_intent is not None
    return {
        "program_digest": program_digest,
        "plan_digest": plan_digest,
        "transition_digest": successor.transition_digest,
        "kind": successor.kind,
        "attempt_id": successor.attempt_intent.attempt_id,
        "attempt_intent_digest": successor.attempt_intent.attempt_intent_digest,
        "idempotency_key": successor.attempt_intent.idempotency_key,
        "budget_remaining": successor.observations["budget_remaining"],
        "source_mode_present": False,
    }, {
        "interpreter_id": legacy_adapter.interpreter_id,
        "transition_digest": legacy.transition_digest,
        "kind": legacy.kind,
        "attempt_id": legacy.attempt_intent.attempt_id,
        "budget_remaining": legacy.observations["budget_remaining"],
        "provider_calls": 0,
    }


def _submission_payload() -> c4.AgentBatchSubmission:
    import hashlib

    return c4.AgentBatchSubmission(
        schema_version="mrw.successor.agent-batch.c4-3.payload.v1",
        operation_kind="agent_batch.submit.v1",
        submission_id="sub:p3-c4-fragment",
        project_key=PROJECT_KEY,
        resolved_schema=RESOLVED_SCHEMA,
        registry_revision=REGISTRY_REVISION,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        capability_id=c4.SUBMISSION_OWNER,
        logical_request_id="request:p3-c4-fragment",
        request_digest=hashlib.sha256(b"request:p3-c4-fragment").hexdigest(),
        jobs=(
            c4.AgentBatchSubmissionItem(
                job_id="job:1",
                channel="search.market",
                query_terms=("机器人",),
                lane="main",
            ),
        ),
        authority_snapshot_ref="authority:snapshot:p3-c4-fragment",
        resource_request_ref="resource:request:p3-c4-fragment",
    )


def _c4_3_submission_observation() -> dict[str, object]:
    payload = _submission_payload()
    bundle_obj = c4.build_agent_batch_c4_bundle()
    catalog_obj = c4.build_agent_batch_c4_catalog(bundle_obj)
    program = build_agent_batch_c4_3_program(
        payload=payload,
        catalog=catalog_obj,
        program_id="p3-c4-fragment.submission",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = c4p.compile_agent_batch_c4_program(
        program,
        catalog_obj,
        operation_contracts=c4.build_agent_batch_c4_registry(bundle_obj),
    )
    return {
        "contract_owner": c4.SUBMISSION_OWNER,
        "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest,
        "payload_codec_id": c4.SUBMISSION_PAYLOAD_CODEC_ID,
        "generic_idempotency_enum": ("STARTED", "TERMINAL", "SUPERSEDED"),
        "acceptance_status_location": "typed_receipt_only",
        "postgres_repository": "shared_IdempotencyRepository_adapter",
        "runtime_chain_idempotency": "STARTED->TERMINAL_in_store_rehydrated_handler",
        "crash_replay": "persisted_receipt_readback_adoption",
        "rollback_rehearsal": "successor_disabled_legacy_enabled_no_dual_claim",
        "provider_calls": 0,
        "network_required": False,
    }


def _operation_bindings() -> tuple[list[dict[str, object]], ...]:
    bundle = c4.build_agent_batch_c4_bundle()
    plan_bindings = [
        {
            "operation_kind": operation.ref.kind,
            "contract_digest": operation.ref.contract_digest,
            "role": "batch_plan_atom",
        }
        for operation in bundle.operations
        if operation.ref.kind == c4.BATCH_PLAN_KIND
    ]
    retry_bindings = [
        {
            "operation_kind": operation.ref.kind,
            "contract_digest": operation.ref.contract_digest,
            "role": "retry_reducer_atom",
        }
        for operation in bundle.operations
        if operation.ref.kind == c4.RETRY_REDUCE_KIND
    ]
    submit_bindings = [
        {
            "operation_kind": operation.ref.kind,
            "contract_digest": operation.ref.contract_digest,
            "role": "submission_contract",
        }
        for operation in bundle.operations
        if operation.ref.kind == c4.SUBMISSION_KIND
    ]
    return plan_bindings, retry_bindings, submit_bindings


def _build_body(root: Path, bindings: BindingsByKind) -> dict[str, Any]:
    c4_1_successor, c4_1_legacy = _c4_1_plan_observation()
    c4_2_successor, c4_2_legacy = _c4_2_retry_observation()
    c4_3_successor = _c4_3_submission_observation()
    plan_bindings, retry_bindings, submit_bindings = _operation_bindings()

    cells = [
        {
            "cell_id": "C4.1",
            "p1_cell_digest": _p1_cell_digest(root, "C4.1"),
            "operation_bindings": plan_bindings,
            "owner_capability_id": c4.AGENT_BATCH_C4_OWNER,
            "program_digest": {
                "value": c4_1_successor["program_digest"],
                "reason": "single-Atom Program plus STATIC_SHAPE TraverseOrdered program with exact traversal_shape_digest/element_count metadata",
            },
            "plan_digest": {
                "value": c4_1_successor["plan_digest"],
                "reason": "compiled batch-plan plan through the shared compiler; traversal plan digest also bound in successor_observation",
            },
            "legacy_observation": c4_1_legacy,
            "successor_observation": {
                "interpreter_id": c4i.AGENT_BATCH_C4_SUCCESSOR_PLAN_INTERPRETER_ID,
                "result_digest": c4_1_successor["result_digest"],
                "ordered_tasks": c4_1_successor["ordered_tasks"],
                "supplementation_enabled": c4_1_successor["supplementation_enabled"],
                "branching_enabled": c4_1_successor["branching_enabled"],
                "branching_reason": c4_1_successor["branching_reason"],
                "traversal_program_digest": c4_1_successor["traversal_program_digest"],
                "traversal_plan_digest": c4_1_successor["traversal_plan_digest"],
                "traversal_shape_digest": c4_1_successor["traversal_shape_digest"],
                "traversal_element_count": c4_1_successor["traversal_element_count"],
                "source_mode_present": False,
            },
            "rollback_observation": {
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "plan_digest_retained": c4_1_successor["plan_digest"],
                        "no_redispatch": True,
                    }
                ),
                "claim_owner": "legacy",
                "plan_retained": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "not_required",
        },
        {
            "cell_id": "C4.2",
            "p1_cell_digest": _p1_cell_digest(root, "C4.2"),
            "operation_bindings": retry_bindings,
            "owner_capability_id": c4.AGENT_BATCH_C4_OWNER,
            "program_digest": {
                "value": c4_2_successor["program_digest"],
                "reason": "single-Atom Program for the exact retry-reducer payload",
            },
            "plan_digest": {
                "value": c4_2_successor["plan_digest"],
                "reason": "compiled retry-reducer plan through the shared compiler",
            },
            "legacy_observation": c4_2_legacy,
            "successor_observation": {
                "interpreter_id": c4i.AGENT_BATCH_C4_SUCCESSOR_RETRY_INTERPRETER_ID,
                "transition_digest": c4_2_successor["transition_digest"],
                "kind": c4_2_successor["kind"],
                "attempt_id": c4_2_successor["attempt_id"],
                "attempt_intent_digest": c4_2_successor["attempt_intent_digest"],
                "idempotency_key": c4_2_successor["idempotency_key"],
                "budget_remaining": c4_2_successor["budget_remaining"],
                "source_mode_present": False,
            },
            "rollback_observation": {
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "attempt_intent_retained": True,
                        "no_duplicate_dispatch": True,
                    }
                ),
                "claim_owner": "legacy",
                "attempt_retained": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "not_required",
        },
        {
            "cell_id": "C4.3",
            "p1_cell_digest": _p1_cell_digest(root, "C4.3"),
            "operation_bindings": submit_bindings,
            "owner_capability_id": c4.SUBMISSION_OWNER,
            "program_digest": {
                "value": c4_3_successor["program_digest"],
                "reason": "typed single-Atom submission Program compiled through the shared compiler",
            },
            "plan_digest": {
                "value": c4_3_successor["plan_digest"],
                "reason": "compiled submission plan through the shared compiler",
            },
            "legacy_observation": {
                "interpreter_id": "legacy.agent_batch.submit_api.v1",
                "transport": "celery",
                "provider_calls": 0,
                "dispatch_executed": False,
            },
            "successor_observation": c4_3_successor,
            "rollback_observation": {
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "successor_journal_retained": False,
                        "no_api_cutover": True,
                    }
                ),
                "claim_owner": "legacy",
                "no_api_cutover": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "required_and_verified_mrw_p3_c4_worker_test",
        },
    ]

    return {
        "schema": FRAGMENT_SCHEMA,
        "phase": FRAGMENT_PHASE,
        "family": FRAGMENT_FAMILY,
        "fragment_id": FRAGMENT_ID,
        "status": FRAGMENT_STATUS,
        "cells": cells,
        "source_bindings": bindings["source_bindings"],
        "implementation_bindings": bindings["implementation_bindings"],
        "test_bindings": bindings["test_bindings"],
        "authority": dict(AUTHORITY),
        "open_findings": [dict(finding) for finding in OPEN_FINDINGS],
    }


def _self_check(fragment: Mapping[str, Any]) -> None:
    assert fragment["schema"] == FRAGMENT_SCHEMA
    assert fragment["phase"] == FRAGMENT_PHASE
    assert fragment["family"] == FRAGMENT_FAMILY
    assert fragment["status"] == FRAGMENT_STATUS
    body = {key: value for key, value in fragment.items() if key != "content_digest"}
    assert fragment["content_digest"] == content_digest(body)
    required_roots = {
        "schema",
        "phase",
        "family",
        "fragment_id",
        "status",
        "cells",
        "source_bindings",
        "implementation_bindings",
        "test_bindings",
        "authority",
        "open_findings",
        "content_digest",
    }
    assert set(fragment) == required_roots
    cell_ids = [cell["cell_id"] for cell in fragment["cells"]]
    assert cell_ids == ["C4.1", "C4.2", "C4.3"]
    assert all(not value for value in fragment["authority"].values()), (
        "authority flags must all be false"
    )


CONFIG = FamilyFragmentConfig(
    family_id=FRAGMENT_FAMILY,
    phase=FRAGMENT_PHASE,
    schema=FRAGMENT_SCHEMA,
    fragment_id=FRAGMENT_ID,
    status=FRAGMENT_STATUS,
    fragment_output_rel=FRAGMENT_OUTPUT_REL,
    source_bindings=_SOURCE_BINDINGS,
    implementation_bindings=_IMPLEMENTATION_BINDINGS,
    test_bindings=_TEST_BINDINGS,
    authority=AUTHORITY,
    open_findings=OPEN_FINDINGS,
    body_builder=_build_body,
    self_check=_self_check,
)
