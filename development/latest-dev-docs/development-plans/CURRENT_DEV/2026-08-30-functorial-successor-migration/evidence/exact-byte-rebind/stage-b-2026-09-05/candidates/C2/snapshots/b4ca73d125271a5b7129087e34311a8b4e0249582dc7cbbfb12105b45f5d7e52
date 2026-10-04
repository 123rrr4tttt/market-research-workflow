"""Deterministically generate the normalized P3 C2 evidence fragment.

Root schema: ``mrw.functorial_successor.p3_fragment.v1``.  The generator binds
one exact C2.1 resolution through the C2.2 plan, C2.3 fixture receipt and C2.4
projection, plus the exact source/implementation/test bindings, without running
any live provider, credential, network or canonical write.  Run from
``main/backend``:

    python3.11 scripts/generate_successor_p3_c2_fragment.py

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

from app.successor_migration.legacy_source_library_c2_2 import (
    LegacySourceLibraryC2_2Adapter,
)
from app.successor_migration.legacy_source_library_c2_3 import (
    LegacySourceLibraryC2_3Adapter,
)
from app.successor_migration.legacy_source_library_c2_4 import (
    LegacySourceLibraryC2_4Adapter,
)
from app.successor_runtime.capabilities import source_library_c2_1 as c21
from app.successor_runtime.capabilities import source_library_c2_2 as c22
from app.successor_runtime.capabilities import source_library_c2_2_interpreters as c22i
from app.successor_runtime.capabilities import source_library_c2_2_program as c22p
from app.successor_runtime.capabilities import source_library_c2_3 as c23
from app.successor_runtime.capabilities import (
    source_library_c2_3_test_interpreters as c23_fixtures,
)
from app.successor_runtime.capabilities import source_library_c2_4_projection as c24
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_library_c2_1 import (
    source_item_definition_content_digest,
)
from app.successor_runtime.capabilities.source_library_c2_1_interpreters import (
    resolve_source_execution_request,
)
from app.successor_runtime.capabilities.source_library_c2_2 import (
    CollectionCompleted,
    SourceCollectionTerminal,
)
from app.successor_runtime.capabilities.source_library_c2_3 import (
    CapturedSourceRecordRef,
)
from app.successor_runtime.substrate.postgres.source_library_c2_23_canary import (
    build_c2_3_fixture_program,
    compile_c2_3_fixture_program,
)
from app.successor_runtime.substrate.projections.source_library_terminal import (
    rollback_read_routing,
)

PROJECT_KEY = "demo_proj"
REGISTRY_REVISION = 5
RESOLVED_SCHEMA = "mrw_p_demo_proj"
SCOPE_INCARNATION = "scope-inc-5"
SCOPE_DIGEST = c21.project_scope_digest(
    PROJECT_KEY, RESOLVED_SCHEMA, REGISTRY_REVISION, SCOPE_INCARNATION
)
OBSERVED_AT = "2030-09-01T08:00:00Z"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_ROOT = REPOSITORY_ROOT / (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
FRAGMENT_PATH = EVIDENCE_ROOT / "p3-fragments/C2.json"
FRAGMENT_ID = "p3-c2-family-local-implementation"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p3_fragment.v1"


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


def _resolved() -> tuple[
    Any, c21.SourceExecutionRequest, dict[str, Any], list[dict[str, Any]]
]:
    channels = [
        {
            "channel_key": "handler.cluster",
            "provider_type": "native",
            "enabled": True,
            "extra": {"credential_refs": ["credential:/secret-ref/hc-api-key"]},
        },
        {"channel_key": "market.default", "provider_type": "native", "enabled": True},
    ]
    item = {
        "item_key": "handler.cluster.news",
        "channel_key": "handler.cluster",
        "enabled": True,
        "params": {"keywords": ["robotics"], "limit": 9},
        "extra": {
            "stable_handler_cluster": True,
            "expected_entry_type": "search_template",
        },
        "revision": 3,
        "incarnation": "item-inc-3",
    }
    item["content_digest"] = source_item_definition_content_digest(item)
    payload = c21.payload_from_dicts(
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=RESOLVED_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        channels=channels,
        item=item,
        params={
            "query_terms": ["robotics"],
            "site_entries": ["https://example.com/search?q={{q}}"],
        },
    )
    resolved = resolve_source_execution_request(payload)
    assert isinstance(resolved, c21.ResolvedResolution)
    return payload, resolved.request, item, channels


def _planning(
    payload: Any, request: c21.SourceExecutionRequest
) -> c22.SourceModePlanningPayload:
    return c22.SourceModePlanningPayload(
        schema_version=c22.SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA,
        operation_kind=c22i.kind_for_mode(request.source_mode.mode),
        project_scope=request.project_scope,
        execution_request=request,
        execution_request_digest=content_digest(request.to_plain()),
        catalog=payload.catalog,
        item_revision=request.item_revision,
        item_incarnation=request.item_incarnation,
        item_content_digest=request.item_content_digest,
        orchestration_policy_ref="mrw.successor.source-library.c2-2.policy.v1",
        resource_ceiling_digest=c21.resource_ceiling_digest(),
    )


def _plan(payload: Any, request: c21.SourceExecutionRequest) -> c22.SourceModePlan:
    result = c22i.plan_source_mode(_planning(payload, request))
    assert isinstance(result, c22.PlannedPlanning)
    return result.plan


def _c2_2_program_digests(
    planning: c22.SourceModePlanningPayload,
) -> tuple[str, str]:
    bundle = c22.build_source_library_c2_2_bundle()
    catalog = c22.build_source_library_c2_2_catalog(bundle)
    registry = c22.build_source_library_c2_2_registry(bundle)
    program = c22p.build_source_library_c2_2_program(
        payload=planning,
        catalog=catalog,
        program_id="p3-c2-fragment.program",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    compiled = c22p.compile_source_library_c2_2_program(
        program, catalog, operation_contracts=registry
    )
    return program.program_digest, compiled.plan_digest


def _provider_fixture(
    effect_request: c23.ProviderEffectRequest,
) -> c23.ProviderEffectOutcome:
    attempt = c23_fixtures.build_fixture_attempt_ref(effect_request)
    record = CapturedSourceRecordRef(
        record_id="record:p3-c2-4:1",
        content_ref="content:p3-c2-4:1",
        content_digest=content_digest({"fixture": "p3-c2-4"}),
        source_ref="source:handler.cluster",
    )
    return c23_fixtures.build_deterministic_completed_outcome(
        effect_request,
        attempt_ref=attempt,
        records=(record,),
        observed_at=OBSERVED_AT,
    )


def _projection(
    plan: c22.SourceModePlan,
    request: c21.SourceExecutionRequest,
) -> c24.ProjectedWithLoss:
    record = CapturedSourceRecordRef(
        record_id="record:p3-c2-4:1",
        content_ref="content:p3-c2-4:1",
        content_digest=content_digest({"fixture": "p3-c2-4"}),
        source_ref="source:handler.cluster",
    )
    terminal = SourceCollectionTerminal(
        terminal_id="terminal:p3-c2-4",
        mode=plan.mode,
        status="ok",
        records_count=1,
    )
    source = c24.SourceCollectionProjectionSource(
        source_kind="RUNTIME_JOURNAL",
        source_ref="runtime-run:run:p3-c2-4",
        run_id="run:p3-c2-4",
        run_incarnation="run-inc:p3-c2-4",
        source_revision=1,
        source_incarnation="inc:p3-c2-4",
        source_digest="",
        project_key=request.project_scope.project_key,
        project_scope_digest=request.project_scope.scope_digest,
        source_mode=plan.mode,
        collection_outcome=CollectionCompleted(terminal=terminal),
        record_refs=(record,),
        ordered_failures=(),
        provider_handoff=None,
        observed_at=OBSERVED_AT,
    )
    result = c24.project_source_collection(source)
    assert isinstance(result, c24.ProjectedWithLoss)
    return result


def _c2_2_legacy_observation(
    request: c21.SourceExecutionRequest,
    item: dict[str, Any],
    channels: list[dict[str, Any]],
) -> dict[str, object]:
    adapter = LegacySourceLibraryC2_2Adapter()
    channel_map = {channel["channel_key"]: dict(channel) for channel in channels}
    traces, provider_calls = adapter.replay(
        request=request,
        item=item,
        channel_map=channel_map,
        trace_id="p3-c2-fragment.legacy",
    )
    trace_digests = {mode: trace.trace_digest for mode, trace in traces.items()}
    return {
        "interpreter_id": adapter.interpreter_id,
        "trace_digest": content_digest(trace_digests),
        "modes": sorted(trace_digests),
        "provider_calls": len(provider_calls),
    }


def _c2_3_legacy_observation(
    effect_request: c23.ProviderEffectRequest,
) -> dict[str, object]:
    adapter = LegacySourceLibraryC2_3Adapter()
    trace = adapter.replay(
        effect_request,
        fixture_id="provider_harvest_accepted",
        trace_id="p3-c2-fragment.legacy",
    )
    return {
        "interpreter_id": adapter.interpreter_id,
        "trace_digest": trace.trace_digest,
        "fixture_id": trace.fixture_id,
        "provider_calls": 0,
    }


def _c2_4_legacy_observation(result_payload: dict[str, Any]) -> dict[str, object]:
    adapter = LegacySourceLibraryC2_4Adapter()
    trace = adapter.replay(
        result_payload,
        trace_id="p3-c2-fragment.legacy",
        raw_snapshot_ref="content-ref:p3-c2-fragment",
    )
    return {
        "interpreter_id": adapter.interpreter_id,
        "trace_digest": trace.trace_digest,
        "postprocess_calls": 0,
        "uuid_generated": False,
    }


def _bindings() -> tuple[
    list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]
]:
    source_paths = [
        (EVIDENCE_ROOT / "P1FunctorizationEligibility.v1.json", "p1_eligibility"),
        (EVIDENCE_ROOT / "p1-fragments/C2.json", "p1_fragment"),
        (EVIDENCE_ROOT / "P2C21CapabilityPacket.v5.json", "p2_packet"),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c2_1_rehydration_postgres.py",
            "p2_rehydration_test",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/services/source_library/item_resolver.py",
            "legacy_donor_c2_1",
        ),
        (
            REPOSITORY_ROOT / "main/backend/app/services/source_library/resolver.py",
            "legacy_donor_c2_1",
        ),
    ]
    for name in (
        "protocol_search",
        "provider_harvest",
        "site_search",
        "url_execution",
        "single_channel",
    ):
        source_paths.append(
            (
                REPOSITORY_ROOT
                / f"main/backend/app/services/source_library/orchestrators/{name}.py",
                "legacy_donor_c2_2",
            )
        )
    source_paths.extend(
        [
            (
                REPOSITORY_ROOT / "main/backend/app/services/source_library/runner.py",
                "legacy_donor_c2_3",
            ),
            (
                REPOSITORY_ROOT
                / "main/backend/app/services/source_library/terminal_output.py",
                "legacy_donor_c2_4",
            ),
        ]
    )
    implementation_paths = [
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/source_library_c2_shared.py",
            "shared_contracts",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/source_library_c2_2.py",
            "c2_2_contracts",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/source_library_c2_2_interpreters.py",
            "c2_2_interpreters",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/source_library_c2_2_program.py",
            "c2_2_program",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/source_library_c2_3.py",
            "c2_3_contracts",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/source_library_c2_3_ports.py",
            "c2_3_ports",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/source_library_c2_3_test_interpreters.py",
            "c2_3_test_interpreters",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/capabilities/source_library_c2_4_projection.py",
            "c2_4_projection",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/substrate/projections/source_library_terminal.py",
            "c2_4_projection_store",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_runtime/substrate/postgres/source_library_c2_23_canary.py",
            "c2_23_runtime_canary_handlers",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_migration/legacy_source_library_c2_2.py",
            "c2_2_legacy_adapter",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_migration/legacy_source_library_c2_3.py",
            "c2_3_legacy_adapter",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/app/successor_migration/legacy_source_library_c2_4.py",
            "c2_4_legacy_adapter",
        ),
        (Path(__file__).resolve(), "evidence_generator"),
    ]
    test_paths = [
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c2_2_contracts.py",
            "c2_2_contracts",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c2_2_parity.py",
            "c2_2_parity",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c2_3_contracts.py",
            "c2_3_contracts",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c2_3_recovery.py",
            "c2_3_recovery",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c2_3_parity.py",
            "c2_3_parity",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c2_4_projection.py",
            "c2_4_projection",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c2_4_postgres.py",
            "c2_4_postgres",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c2_23_runtime_canary_postgres.py",
            "c2_23_runtime_canary",
        ),
        (
            REPOSITORY_ROOT
            / "main/backend/tests/successor_runtime/test_p3_c2_evidence_generator.py",
            "evidence_generator",
        ),
    ]
    return (
        [_bind(path, role) for path, role in source_paths],
        [_bind(path, role) for path, role in implementation_paths],
        [_bind(path, role) for path, role in test_paths],
    )


def build_fragment() -> dict[str, object]:
    payload, request, item, channels = _resolved()
    planning = _planning(payload, request)
    plan = _plan(payload, request)
    effect_request = plan.ordered_tasks[0].effect_request
    outcome = _provider_fixture(effect_request)
    projection = _projection(plan, request)
    program_digest, plan_digest = _c2_2_program_digests(planning)
    c2_3_catalog_snapshot = c23.build_source_library_c2_3_catalog(
        c23.build_source_library_c2_3_bundle()
    )
    c2_3_registry = c23.build_source_library_c2_3_registry(
        c23.build_source_library_c2_3_bundle()
    )
    c2_3_program = build_c2_3_fixture_program(
        request=effect_request,
        catalog=c2_3_catalog_snapshot,
        program_id="program:p3-c2-fragment:c2-3",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    c2_3_plan = compile_c2_3_fixture_program(
        c2_3_program,
        c2_3_catalog_snapshot,
        operation_contracts=c2_3_registry,
    )

    c2_2_bundle = c22.build_source_library_c2_2_bundle()
    c2_3_bundle = c23.build_source_library_c2_3_bundle()
    c2_2_operation_bindings = [
        {
            "operation_kind": operation.ref.kind,
            "contract_digest": operation.ref.contract_digest,
            "role": "planner_atom",
        }
        for operation in c2_2_bundle.operations
    ]
    c2_3_operation_bindings = [
        {
            "operation_kind": c2_3_bundle.operation.ref.kind,
            "contract_digest": c2_3_bundle.operation.ref.contract_digest,
            "role": "provider_effect_port_contract",
        }
    ]
    c2_4_operation_bindings = [
        {
            "operation_kind": "source_library.project_terminal_compat.v1",
            "contract_digest": None,
            "role": "projector_registry",
            "reason": (
                "terminal/compat projection is executed by the projector "
                "registry, not registered as a Program Atom"
            ),
        }
    ]

    legacy_c2_2 = _c2_2_legacy_observation(request, item, channels)
    legacy_c2_3 = _c2_3_legacy_observation(effect_request)
    legacy_c2_4 = _c2_4_legacy_observation(
        LegacySourceLibraryC2_2Adapter()
        .replay(
            request=request,
            item=item,
            channel_map={channel["channel_key"]: dict(channel) for channel in channels},
            trace_id="p3-c2-fragment.legacy",
        )[0]["site_search"]
        .payload
    )

    source_bindings, implementation_bindings, test_bindings = _bindings()

    cells = [
        {
            "cell_id": "C2.2",
            "p1_cell_digest": _p1_cell_digest("C2.2"),
            "operation_bindings": c2_2_operation_bindings,
            "owner_capability_id": "source_library.c2_2.v1",
            "program_digest": {
                "value": program_digest,
                "reason": "single-Atom Program for the exact C2.1-bound planning payload",
            },
            "plan_digest": {
                "value": plan_digest,
                "reason": "compiled planning plan through the shared compiler",
            },
            "legacy_observation": legacy_c2_2,
            "successor_observation": {
                "interpreter_id": c22i.SOURCE_LIBRARY_C2_2_SUCCESSOR_INTERPRETER_ID,
                "mode": plan.mode,
                "ordered_tasks": len(plan.ordered_tasks),
                "plan_digest": plan.plan_digest,
                "fold_policy": plan.ordered_fold_policy.to_plain(),
                "canary_runtime": {
                    "state": "COMMITTED",
                    "disposition": "SUCCEEDED",
                    "materialized_c2_3_attempt": True,
                    "real_provider_calls": 0,
                },
            },
            "rollback_observation": {
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "plan_digest_retained": plan.plan_digest,
                        "no_redispatch": True,
                    }
                ),
                "claim_owner": "legacy",
                "plan_retained": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "required_and_verified_mrw_p3_c2_worker_test",
        },
        {
            "cell_id": "C2.3",
            "p1_cell_digest": _p1_cell_digest("C2.3"),
            "operation_bindings": c2_3_operation_bindings,
            "owner_capability_id": "source_library.c2_3.v1",
            "program_digest": {
                "value": c2_3_program.program_digest,
                "reason": (
                    "disposable-PG canary fixture single-Atom Program; "
                    "store-rehydrated, not a production composition"
                ),
            },
            "plan_digest": {
                "value": c2_3_plan.plan_digest,
                "reason": "disposable-PG canary compiled plan for the fixture Atom",
            },
            "legacy_observation": legacy_c2_3,
            "successor_observation": {
                "interpreter_id": "successor.source_library.c2_3.provider_effect.v1",
                "outcome_kind": outcome.kind,
                "outcome_digest": outcome.outcome_digest,
                "receipt_digest": outcome.receipt.receipt_digest,
                "credential_refs": [ref.ref for ref in effect_request.credential_refs],
                "secret_bytes_present": False,
                "canary_runtime": {
                    "state": "COMMITTED",
                    "disposition": "SUCCEEDED",
                    "outcome_unknown_reconcile": "COMMITTED_SUCCEEDED",
                    "real_provider_calls": 0,
                },
            },
            "rollback_observation": {
                "rollback_digest": content_digest(
                    {
                        "claim_owner": "legacy",
                        "reconcile_unknown": "OUTCOME_UNKNOWN_UNRESOLVED",
                        "no_duplicate_provider_dispatch": True,
                    }
                ),
                "claim_owner": "legacy",
                "no_duplicate_provider_dispatch": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "required_and_verified_mrw_p3_c2_worker_test",
        },
        {
            "cell_id": "C2.4",
            "p1_cell_digest": _p1_cell_digest("C2.4"),
            "operation_bindings": c2_4_operation_bindings,
            "owner_capability_id": "source_library.c2_4.v1",
            "program_digest": {
                "value": None,
                "reason": "projection is a read-model projector, not a Program Atom",
            },
            "plan_digest": {
                "value": None,
                "reason": "projection consumes an admitted journal closure with offsets",
            },
            "legacy_observation": legacy_c2_4,
            "successor_observation": {
                "projector_id": c24.SOURCE_LIBRARY_C2_4_PROJECTOR_ID,
                "projector_version": c24.SOURCE_LIBRARY_C2_4_PROJECTOR_VERSION,
                "terminal_digest": projection.terminal.projection_digest,
                "compat_digest": projection.compat.compat_digest,
                "summary_digest": projection.summary.projection_digest,
                "loss_profile_ref": c24.DECLARED_LOSS_PROFILE_REF,
                "is_authority": False,
            },
            "rollback_observation": {
                "rollback_digest": rollback_read_routing().rollback_digest,
                "claim_owner": "legacy",
                "projection_rows_retained": True,
            },
            "provider_calls": 0,
            "postgres_requirement": "required_and_verified_mrw_p3_c2_worker_test",
        },
    ]

    return {
        "schema": FRAGMENT_SCHEMA,
        "phase": "P3",
        "family": "C2",
        "fragment_id": FRAGMENT_ID,
        "status": "IMPLEMENTED_CANDIDATE_NOT_PROMOTED",
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
                "id": "P3_AUTHORITY_RECORD_DIVERGENCE",
                "severity": "P0",
                "description": (
                    "frozen 01/02 still bound P0-C; mutable ledger claims P3 "
                    "authorized; promotion requires root/supervisor authority record"
                ),
            },
            {
                "id": "P3_C2_CHAIN_REHYDRATION_LOCAL_ONLY",
                "severity": "P1",
                "description": (
                    "C2.1 project-store rehydration is bound by "
                    "P2C21CapabilityPacket.v5 (content_digest af98e967ce22...); "
                    "v4 remains superseded/invalidated read-only history; "
                    "C2.1->C2.2 durable chaining remains local-only, not live"
                ),
            },
            {
                "id": "P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED",
                "severity": "P1",
                "description": "capability surface remains untracked; exact review tree pending",
            },
            {
                "id": "C2_2_DURABLE_RUNTIME_NODE_LOCAL_ONLY",
                "severity": "P1",
                "description": (
                    "disposable-PG RuntimeNode canary verified locally for one "
                    "materialized C2.3 attempt; production/live promotion remains "
                    "not authorized"
                ),
            },
            {
                "id": "C2_3_LIVE_PROVIDER_AUTHORITY_NOT_FROZEN",
                "severity": "P0",
                "description": (
                    "live provider/credential authority, authoritative readback "
                    "and idempotency/non-start proof are not frozen"
                ),
            },
            {
                "id": "C2_4_SOURCE_CLOSURE_AND_OFFSET_NOT_LIVE",
                "severity": "P1",
                "description": (
                    "source closure, declared-loss profile and offset/rebuild "
                    "are fixture-verified only; no live compat read routing"
                ),
            },
        ],
        "content_digest": "",
    }


def _self_test(fragment: dict[str, object]) -> None:
    assert fragment["schema"] == FRAGMENT_SCHEMA
    assert fragment["phase"] == "P3"
    assert fragment["family"] == "C2"
    assert fragment["status"] == "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
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
    assert cell_ids == ["C2.2", "C2.3", "C2.4"]
    assert all(not value for value in fragment["authority"].values()), (
        "authority flags must all be false"
    )


def _expected_text() -> tuple[dict[str, object], str]:
    first = build_fragment()
    second = build_fragment()
    if _canonical_json(first) != _canonical_json(second):
        raise RuntimeError("non-deterministic fragment")
    digest = content_digest(
        {key: value for key, value in first.items() if key != "content_digest"}
    )
    first["content_digest"] = digest
    _self_test(first)
    return first, _canonical_json(first) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="generate_successor_p3_c2_fragment",
        description="Deterministically generate or read-only check the P3 C2 fragment.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "read-only check: verify bytes and mtime are unchanged; "
            "drift exits 1 without writing, unknown errors exit 2"
        ),
    )
    parser.add_argument(
        "--fragment-path",
        type=Path,
        default=FRAGMENT_PATH,
        help="fragment output path (default: the canonical evidence path)",
    )
    args = parser.parse_args(argv)
    fragment, text = _expected_text()
    target = Path(args.fragment_path)
    if not args.check:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        persisted = json.loads(target.read_text())
        assert _canonical_json(persisted) == _canonical_json(fragment)
        print(f"wrote {target}")
        print(f"content_digest {fragment['content_digest']}")
        print(f"cells {[cell['cell_id'] for cell in fragment['cells']]}")
        return 0

    before_stat = None
    try:
        before_stat = target.stat()
    except FileNotFoundError:
        print(f"check failed: fragment missing at {target}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"check failed: cannot stat {target}: {exc}", file=sys.stderr)
        return 2
    try:
        existing = target.read_bytes()
    except OSError as exc:
        print(f"check failed: cannot read {target}: {exc}", file=sys.stderr)
        return 2
    expected = text.encode("utf-8")
    if existing != expected:
        print(
            "check drift: on-disk fragment bytes differ from deterministic output; "
            "no write performed",
            file=sys.stderr,
        )
        return 1
    try:
        after_stat = target.stat()
    except OSError as exc:
        print(f"check failed: cannot restat {target}: {exc}", file=sys.stderr)
        return 2
    if (
        before_stat.st_mtime_ns != after_stat.st_mtime_ns
        or before_stat.st_size != after_stat.st_size
    ):
        print(
            "check drift: fragment mtime/size changed; no write performed",
            file=sys.stderr,
        )
        return 1
    print(f"check ok: {target} unchanged")
    print(f"content_digest {fragment['content_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
