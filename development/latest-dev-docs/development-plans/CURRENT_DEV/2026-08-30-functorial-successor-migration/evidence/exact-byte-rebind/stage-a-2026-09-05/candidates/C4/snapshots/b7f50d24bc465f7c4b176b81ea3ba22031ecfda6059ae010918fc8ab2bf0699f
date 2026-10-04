"""Deterministically generate the normalized P3 C4 evidence fragment.

Root schema: ``mrw.functorial_successor.p3_fragment.v1``, matching the common
P3 family fragment sent to other families.  The generator binds the C4.1 ordered
batch-plan atom, C4.2 retry reducer and C4.3 submission contracts/repository
scaffold, plus exact p1 cell digests, implementations, tests and shared
traversal/idempotency dependencies, without running any live provider,
credential, network or canonical write.  Run from ``main/backend``:

    python3.11 scripts/generate_successor_p3_c4_fragment.py

The generator self-tests determinism (two identical builds) and the
``content_digest`` over the canonical fragment body.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

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
from tests.successor_runtime.p3_c4_fixture import C2ProducerSnapshotView

PROJECT_KEY = "p3-c4-fragment"
REGISTRY_REVISION = 3
RESOLVED_SCHEMA = "mrw_p3_c4_fragment"
SCOPE_INCARNATION = "scope-inc-c4-fragment"
SCOPE_DIGEST = project_scope_digest(
    PROJECT_KEY, RESOLVED_SCHEMA, REGISTRY_REVISION, SCOPE_INCARNATION
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_ROOT = REPOSITORY_ROOT / (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
FRAGMENT_PATH = EVIDENCE_ROOT / "p3-fragments/C4.json"
FRAGMENT_ID = "p3-c4-family-local-implementation"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p3_fragment.v1"
FRAGMENT_PHASE = "P3"
FRAGMENT_FAMILY = "C4"
FRAGMENT_STATUS = "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _bind(path: Path, role: str) -> dict[str, object]:
    relative = path.resolve().relative_to(REPOSITORY_ROOT.resolve())
    data = path.read_bytes()
    return {
        "path": str(relative),
        "sha256": _sha256_bytes(data),
        "bytes": len(data),
        "lines": len(data.splitlines()),
        "role": role,
    }


def _p1_cells() -> dict[str, dict[str, Any]]:
    artifact = json.loads(
        (EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json").read_text()
    )
    return {str(cell["cell"]): cell for cell in artifact["cells"]}


def _p1_cell_digest(cell_id: str) -> str:
    cell = _p1_cells()[cell_id]
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


def _bindings() -> tuple[
    list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]
]:
    source_paths = [
        (EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json", "p1_eligibility"),
        (EVIDENCE_ROOT / "p1-fragments/C4.json", "p1_fragment"),
        (
            REPOSITORY_ROOT / "main/backend/app/services/agent_batch/agent_loop.py",
            "legacy_donor_c4_1_c4_2",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/services/agent_batch/task_contract.py",
            "legacy_donor_c4_1_c4_2_c4_3",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/api/agent_batch.py",
            "legacy_donor_c4_3",
        ),
    ]
    implementation_paths = [
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/agent_batch_c4.py",
            "c4_contracts",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/agent_batch_c4_program.py",
            "c4_program",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/agent_batch_c4_interpreters.py",
            "c4_interpreters",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_migration/legacy_agent_batch.py",
            "c4_legacy_adapter",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/substrate/postgres/agent_batch_c4.py",
            "c4_3_submission_repository_scaffold",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/substrate/postgres/agent_batch_c4_canary.py",
            "c4_canary_handler",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/substrate/postgres/agent_batch_c4_3_handler.py",
            "c4_3_store_rehydrated_handler",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/successor_runtime/language/compile.py",
            "shared_compiler_traversal_dependency",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/successor_runtime/language/program.py",
            "shared_program_traverse_ordered_dependency",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/substrate/postgres/idempotency.py",
            "shared_idempotency_repository_dependency",
        ),
        (Path(__file__).resolve(), "evidence_generator"),
    ]
    test_paths = [
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c4_1_plan.py",
            "c4_1_plan",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c4_1_program.py",
            "c4_1_program",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c4_1_parity.py",
            "c4_1_parity",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c4_2_retry_reducer.py",
            "c4_2_retry_reducer",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c4_3_submission.py",
            "c4_3_submission",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c4_canary.py",
            "c4_canary",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c4_4_postgres.py",
            "c4_3_postgres_idempotency",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c4_5_runtime_postgres.py",
            "c4_3_runtime_node_postgres",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c4_evidence_generator.py",
            "c4_evidence_generator",
        ),
    ]
    return (
        [_bind(path, role) for path, role in source_paths],
        [_bind(path, role) for path, role in implementation_paths],
        [_bind(path, role) for path, role in test_paths],
    )


def build_fragment() -> dict[str, object]:
    c4_1_successor, c4_1_legacy = _c4_1_plan_observation()
    c4_2_successor, c4_2_legacy = _c4_2_retry_observation()
    c4_3_successor = _c4_3_submission_observation()
    plan_bindings, retry_bindings, submit_bindings = _operation_bindings()
    source_bindings, implementation_bindings, test_bindings = _bindings()

    cells = [
        {
            "cell_id": "C4.1",
            "p1_cell_digest": _p1_cell_digest("C4.1"),
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
            "p1_cell_digest": _p1_cell_digest("C4.2"),
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
            "p1_cell_digest": _p1_cell_digest("C4.3"),
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
        "source_bindings": source_bindings,
        "implementation_bindings": implementation_bindings,
        "test_bindings": test_bindings,
        "authority": {
            "production_canonical_write": False,
            "live_provider": False,
            "external_delivery": False,
            "live_credential": False,
            "network": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
            "p3_promotion": False,
        },
        "open_findings": [
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
        ],
        "content_digest": "",
    }


def _self_test(fragment: dict[str, object]) -> None:
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


def _build_with_digest() -> dict[str, object]:
    """Build twice, self-test, and return the digest-bound fragment."""

    first = build_fragment()
    second = build_fragment()
    assert _canonical_json(first) == _canonical_json(second), (
        "non-deterministic fragment"
    )
    digest = content_digest(
        {key: value for key, value in first.items() if key != "content_digest"}
    )
    first["content_digest"] = digest
    _self_test(first)
    return first


def _persisted_snapshot() -> tuple[dict[str, object], bytes, int]:
    stat = FRAGMENT_PATH.stat()
    data = FRAGMENT_PATH.read_bytes()
    return json.loads(data.decode("utf-8")), data, int(stat.st_mtime_ns)


def _check() -> int:
    """Read-only drift gate: compare bytes and mtime against the rebuilt fragment.

    No write occurs.  Exit 1 on any drift or missing file; the persisted bytes
    and mtime are asserted unchanged after the in-memory build.
    """

    if not FRAGMENT_PATH.exists():
        print(f"missing fragment {FRAGMENT_PATH}", file=sys.stderr)
        return 1
    before_bytes = FRAGMENT_PATH.read_bytes()
    before_mtime_ns = FRAGMENT_PATH.stat().st_mtime_ns
    rebuilt = _build_with_digest()
    expected_text = _canonical_json(rebuilt) + "\n"
    try:
        persisted, persisted_bytes, persisted_mtime_ns = _persisted_snapshot()
    except Exception as exc:  # noqa: BLE001 - read-only gate must fail closed
        print(f"cannot read fragment: {exc}", file=sys.stderr)
        return 1
    if persisted_bytes != before_bytes or persisted_mtime_ns != before_mtime_ns:
        print("fragment changed during check", file=sys.stderr)
        return 1
    if persisted_bytes.decode("utf-8") != expected_text:
        print(
            "fragment drift: persisted bytes differ from rebuilt fragment",
            file=sys.stderr,
        )
        return 1
    if _canonical_json(persisted) != _canonical_json(rebuilt):
        print("fragment drift: persisted canonical JSON differs", file=sys.stderr)
        return 1
    print(f"check ok: {FRAGMENT_PATH}")
    print(f"content_digest {rebuilt['content_digest']}")
    print(f"cells {[cell['cell_id'] for cell in rebuilt['cells']]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate_successor_p3_c4_fragment",
        description="Generate or read-only check the P3 C4 evidence fragment",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="read-only drift gate; never writes, exit 1 on drift, 2 on unknown args",
    )
    args = parser.parse_args(argv)
    if args.check:
        return _check()
    first = _build_with_digest()
    FRAGMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = _canonical_json(first) + "\n"
    FRAGMENT_PATH.write_text(text)
    persisted = json.loads(FRAGMENT_PATH.read_text())
    assert _canonical_json(persisted) == _canonical_json(first)
    print(f"wrote {FRAGMENT_PATH}")
    print(f"content_digest {first['content_digest']}")
    print(f"cells {[cell['cell_id'] for cell in first['cells']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
