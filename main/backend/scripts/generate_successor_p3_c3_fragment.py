#!/usr/bin/env python3
"""Deterministic P3 C3 family fragment generator.

The fragment binds the implemented C3.1/C3.2 cells, their source donors, the
read-only shared TraverseOrdered dependency, implementation and test files, and
the authority ceiling.  Every digest is derived from fixed fixture constants
and current file bytes; the output contains no timestamps, process ids, git
state or random values, so two runs produce byte-identical JSON.

The script writes only the topic fragment:
  development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-
  functorial-successor-migration/evidence/p3-fragments/C3.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _ROOT / "main/backend"
_TOPIC = (
    _ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-08-30-functorial-successor-migration/evidence/p3-fragments"
)
_FRAGMENT_PATH = _TOPIC / "C3.json"
_P1_ELIGIBILITY = (
    _ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-08-30-functorial-successor-migration/evidence"
    / "P1FunctorizationEligibility.v1.json"
)
_P1_FRAGMENT = (
    _ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-08-30-functorial-successor-migration/evidence/p1-fragments/C3.json"
)

FRAGMENT_ID = "p3-c3-family-local-implementation"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p3_fragment.v1"
FRAGMENT_STATUS = "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
POSTGRES_REQUIREMENT = "required_and_verified_mrw_p3_c3_worker_test"

LEGACY_SOURCE_FILES = (
    ("main/backend/app/services/collect_runtime/runtime.py", "legacy_donor_c3"),
    ("main/backend/app/services/collect_runtime/contracts.py", "legacy_donor_c3"),
    ("main/backend/app/services/collect_runtime/display_meta.py", "legacy_donor_c3"),
    (
        "main/backend/app/services/collect_runtime/adapters/crawler_scrapy.py",
        "legacy_donor_c3",
    ),
    (
        "main/backend/app/services/collect_runtime/adapters/source_library.py",
        "legacy_donor_c3",
    ),
)

SHARED_TRAVERSAL_DEPENDENCIES = (
    "main/backend/app/successor_runtime/language/compile.py",
    "main/backend/app/successor_runtime/language/program.py",
    "main/backend/app/successor_runtime/language/plan.py",
    "main/backend/app/successor_runtime/language/normalize.py",
    "main/backend/app/successor_runtime/language/validate.py",
    "main/backend/app/successor_runtime/language/transforms.py",
)

IMPLEMENTATION_FILES = (
    (
        "main/backend/app/successor_runtime/capabilities/collect_c3.py",
        "c3_contracts",
    ),
    (
        "main/backend/app/successor_runtime/capabilities/collect_c3_program.py",
        "c3_program",
    ),
    (
        "main/backend/app/successor_runtime/capabilities/collect_c3_interpreters.py",
        "c3_interpreters",
    ),
    (
        "main/backend/app/successor_migration/legacy_collect_runtime.py",
        "c3_legacy_adapter",
    ),
    (
        "main/backend/app/successor_runtime/substrate/postgres/collect_c3_canary.py",
        "c3_postgres_canary",
    ),
    (
        "main/backend/scripts/generate_successor_p3_c3_fragment.py",
        "fragment_generator",
    ),
)

TEST_FILES = (
    (
        "main/backend/tests/successor_runtime/test_p3_c3_contracts.py",
        "c3_contracts_tests",
    ),
    (
        "main/backend/tests/successor_runtime/test_p3_c3_micro.py",
        "c3_micro_tests",
    ),
    (
        "main/backend/tests/successor_runtime/test_p3_c3_replay_shadow.py",
        "c3_replay_shadow_tests",
    ),
    (
        "main/backend/tests/successor_runtime/test_p3_c3_rollback.py",
        "c3_rollback_tests",
    ),
    (
        "main/backend/tests/successor_runtime/test_p3_c3_canary_postgres.py",
        "c3_canary_postgres_tests",
    ),
    (
        "main/backend/tests/successor_runtime/test_p3_c3_fragment.py",
        "c3_fragment_tests",
    ),
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _canonical_digest(value: Any) -> str:
    return _sha256(_canonical_json(value).encode("utf-8"))


def _relative(path: Path) -> str:
    return path.resolve().relative_to(_ROOT.resolve()).as_posix()


def _file_binding(
    path: str,
    role: str,
    *,
    read_only: bool = False,
) -> dict[str, Any]:
    raw = (_ROOT / path).read_bytes()
    binding: dict[str, Any] = {
        "path": path,
        "role": role,
        "sha256": _sha256(raw),
        "bytes": len(raw),
        "lines": len(raw.splitlines()),
    }
    if read_only:
        binding["read_only"] = True
    return binding


def _p1_cell_digest(cell_id: str) -> str:
    data = json.loads(_P1_ELIGIBILITY.read_text(encoding="utf-8"))
    rows = data.get("cells", [])
    row = next(item for item in rows if item.get("cell") == cell_id)
    return _canonical_digest(row)


def _project_scope_digest() -> str:
    return "0" * 64


def _fixture_snapshot() -> dict[str, Any]:
    return {
        "flow": "collect",
        "channel": "search.market",
        "project_key": "demo_proj",
        "query_terms": [
            "t1",
            "t2",
            "t3",
            "t4",
            "t5",
            "t6",
            "t7",
            "t8",
        ],
        "urls": [],
        "limit": 80,
        "options": {},
        "source_context": {},
    }


def _c3_1_fixtures() -> dict[str, Any]:
    from app.successor_runtime.capabilities import collect_c3 as c3
    from app.successor_runtime.capabilities import collect_c3_interpreters as ci
    from app.successor_runtime.capabilities import collect_c3_program as cp

    bundle = c3.build_collect_c3_bundle()
    catalog = c3.build_collect_c3_catalog(bundle)
    registry = c3.build_collect_c3_registry(bundle)
    request_ref = c3.build_collect_request_ref(
        request_id="c3-fragment-request",
        project_key="demo_proj",
        channel="search.market",
    )
    snapshot = c3.CollectLegacyRequestSnapshot(
        schema_version=c3.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        **_fixture_snapshot(),
        snapshot_digest="",
    )
    resource_policy = c3.CollectResourcePolicy(
        schema_ref=c3.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=2,
        deadline_seconds=60,
        cancellation="COORDINATED",
        backpressure=True,
        provider_concurrency_key="search.market",
        policy_digest="",
    )
    plan = c3.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id="c3.fragment.plan",
        resource_policy=resource_policy,
        authority_scope_ref="project:demo_proj",
    )
    element_payloads = tuple(
        c3.collect_batch_element_payload_from_dicts(
            request_ref=request_ref.to_plain(),
            request_snapshot=snapshot.to_plain(),
            element=plan.elements[index].to_plain(),
            resource_policy=resource_policy.to_plain(),
            authority_scope_ref="project:demo_proj",
        )
        for index in range(len(plan.elements))
    )
    payload = element_payloads[0]
    composed_program = cp.build_collect_c3_composed_program(
        element_payloads=element_payloads,
        catalog=catalog,
        program_id="c3.fragment.composed",
        project_key="demo_proj",
        project_registry_revision=5,
        project_scope_digest=_project_scope_digest(),
    )
    composed_plan = cp.compile_collect_c3_program(
        composed_program,
        catalog,
        operation_contracts=registry,
        transform_registry=cp.build_collect_c3_transform_registry(),
    )

    class _FragmentRunner:
        def run(self, element: c3.CollectBatchElement) -> c3.CollectElementOutcome:
            return c3.CollectElementSucceeded(
                schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
                element_id=element.element_id,
                input_index=element.input_index,
                counts=c3.CollectCounts(inserted=len(element.query_terms)),
                links=tuple(
                    f"https://example.com/{term}" for term in element.query_terms
                ),
                legacy_observation_ref="legacy:" + "0" * 64,
                outcome_digest="",
            )

    traversal_result = ci.run_ordered_traversal(plan, _FragmentRunner())
    observation = getattr(traversal_result, "observation", None)
    observation_digest = "" if observation is None else observation.observation_digest

    from app.successor_migration import legacy_collect_runtime as lc

    adapter = lc.LegacyCollectBatchTraverseAdapter()
    trace = adapter._trace(payload, trace_id="c3.1.fragment.trace")
    fold_ref = bundle.operation_c3_2.ref
    legacy_binding = lc.build_legacy_collect_c3_2_binding(
        contract_digest=fold_ref.contract_digest,
        deployment_catalog_digest=c3.deployment_catalog_digest(),
        project_scope_digest=_project_scope_digest(),
    )
    successor_binding = lc.build_successor_collect_c3_2_binding(
        contract_digest=fold_ref.contract_digest,
        deployment_catalog_digest=c3.deployment_catalog_digest(),
        project_scope_digest=_project_scope_digest(),
    )
    legacy_shadow = lc.LegacyComposedCollectInterpreter().interpret(
        program=composed_program,
        plan=composed_plan,
        catalog=catalog,
        binding=legacy_binding,
        element_payloads=element_payloads,
    )
    successor_composed = ci.ComposedCollectSuccessorInterpreter().interpret(
        program=composed_program,
        plan=composed_plan,
        catalog=catalog,
        binding=successor_binding,
        element_payloads=element_payloads,
    )
    if (
        legacy_shadow.disposition != "SUCCEEDED"
        or successor_composed.disposition != "SUCCEEDED"
        or legacy_shadow.value.aggregate_digest
        != successor_composed.value.aggregate_digest
    ):
        raise RuntimeError("composed legacy/successor shadow parity drift")
    return {
        "bundle": bundle,
        "catalog": catalog,
        "registry": registry,
        "payload": payload,
        "plan": plan,
        "composed_program": composed_program,
        "composed_plan": composed_plan,
        "observation_digest": observation_digest,
        "legacy_composed_shadow_digest": legacy_shadow.value.shadow_digest,
        "successor_composed_aggregate_digest": (
            successor_composed.value.aggregate_digest
        ),
        "legacy_trace_digest": trace.trace_digest,
        "provider_calls": 0,
    }


def _c3_2_fixtures() -> dict[str, Any]:
    from app.successor_runtime.capabilities import collect_c3 as c3
    from app.successor_runtime.capabilities import collect_c3_interpreters as ci
    from app.successor_runtime.capabilities import collect_c3_program as cp
    from app.successor_runtime.language.compile import compile_program

    bundle = c3.build_collect_c3_bundle()
    catalog = c3.build_collect_c3_catalog(bundle)
    registry = c3.build_collect_c3_registry(bundle)
    request_ref = c3.build_collect_request_ref(
        request_id="c3-fragment-request",
        project_key="demo_proj",
        channel="search.market",
    )
    succeeded = c3.CollectElementSucceeded(
        schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id="e0",
        input_index=0,
        counts=c3.CollectCounts(inserted=4),
        links=("https://example.com/a", "https://example.com/b"),
        receipt=c3.CollectAttemptReceipt(
            schema_version=c3.COLLECT_ATTEMPT_RECEIPT_SCHEMA_REF,
            receipt_kind="DISPATCH_ACKNOWLEDGEMENT",
            provider_type="search.market",
            provider_job_id="job-fragment-1",
            provider_status="queued",
            attempt_count=1,
            observed_at="2026-09-01T00:00:00Z",
            raw_digest="1" * 64,
            authoritative_readback=False,
            receipt_digest="",
        ),
        legacy_observation_ref="legacy:" + "0" * 64,
        outcome_digest="",
    )
    failed = c3.CollectElementFailed(
        schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id="e1",
        input_index=1,
        error=c3.CollectElementError(
            code="auto_batch_execution_failed",
            message="fragment batch exploded",
            query_terms=("t5",),
            error_digest="",
        ),
        counts=c3.CollectCounts(),
        links=(),
        receipt=None,
        legacy_observation_ref="legacy:" + "1" * 64,
        outcome_digest="",
    )
    sequence = c3.OrderedCollectElementOutcomeSequence(
        schema_version="mrw.successor.collect.c3.outcome-sequence.v1",
        parent_request_ref=request_ref,
        outcomes=(succeeded, failed),
        sequence_digest="",
    )
    payload = c3.build_collect_fold_payload(
        parent_request_ref=request_ref,
        ordered_outcomes=sequence,
    )
    program = cp.build_collect_c3_2_program(
        payload=payload,
        catalog=catalog,
        program_id="c3.fragment.fold",
        project_key="demo_proj",
        project_registry_revision=5,
        project_scope_digest=_project_scope_digest(),
    )
    plan = compile_program(program, catalog, operation_contracts=registry)
    pure_program = cp.build_collect_c3_2_pure_fold_program(
        payload=payload,
        catalog=catalog,
        program_id="c3.fragment.pure-fold",
        project_key="demo_proj",
        project_registry_revision=5,
        project_scope_digest=_project_scope_digest(),
    )
    pure_plan = compile_program(
        pure_program,
        catalog,
        operation_contracts=registry,
        transform_registry=cp.build_collect_c3_transform_registry(),
    )
    aggregate = ci.CollectFoldSuccessorInterpreter().interpret(
        program=program,
        plan=plan,
        contract_ref=program.root.operation.contract_ref,
        payload_ref=program.root.operation.payload_ref,
        payload=payload,
        project_scope=_ProjectScope(),
        catalog=catalog,
        deployment_catalog_digest=c3.deployment_catalog_digest(),
        binding=_successor_fold_binding(bundle),
    )
    aggregate_digest = getattr(aggregate.value, "aggregate_digest", "")

    from app.successor_migration import legacy_collect_runtime as lc

    legacy_binding = lc.build_legacy_collect_c3_2_binding(
        contract_digest=bundle.operation_c3_2.ref.contract_digest,
        deployment_catalog_digest=c3.deployment_catalog_digest(),
        project_scope_digest=_project_scope_digest(),
    )
    adapter = lc.LegacyCollectResultFoldAdapter()
    legacy_result = adapter.fold(
        payload,
        program=program,
        plan=plan,
        contract_ref=program.root.operation.contract_ref,
        payload_ref=program.root.operation.payload_ref,
        project_scope=_ProjectScope(),
        catalog=catalog,
        deployment_catalog_digest=c3.deployment_catalog_digest(),
        binding=legacy_binding,
    )
    legacy_digest = getattr(legacy_result.value, "aggregate_digest", "")
    return {
        "bundle": bundle,
        "catalog": catalog,
        "registry": registry,
        "payload": payload,
        "program": program,
        "plan": plan,
        "pure_program": pure_program,
        "pure_plan": pure_plan,
        "successor_aggregate_digest": aggregate_digest,
        "legacy_aggregate_digest": legacy_digest,
        "provider_calls": 0,
    }


class _ProjectScope:
    project_key = "demo_proj"
    registry_revision = 5
    scope_digest = "0" * 64


def _successor_fold_binding(bundle: Any) -> Any:
    from app.successor_migration import legacy_collect_runtime as lc

    return lc.build_successor_collect_c3_2_binding(
        contract_digest=bundle.operation_c3_2.ref.contract_digest,
        deployment_catalog_digest=_deployment_digest(),
        project_scope_digest=_project_scope_digest(),
    )


def _deployment_digest() -> str:
    from app.successor_runtime.capabilities import collect_c3 as c3

    return c3.deployment_catalog_digest()


def _rollback_digest() -> str:
    return _canonical_digest(
        {
            "mode": "off",
            "route": "legacy",
            "claim_owner": "legacy",
            "journal_readable": True,
            "dual_claim": False,
        }
    )


def _cell_c3_1(fixture: dict[str, Any]) -> dict[str, Any]:
    element_contract = fixture["bundle"].operation_c3_1.ref
    fold_contract = fixture["bundle"].operation_c3_2.ref
    composed_plan = fixture["composed_plan"]
    traverse_step = next(
        step
        for step in composed_plan.ordered_steps
        if step.step_kind == "TRANSFORM"
        and step.transform_ref is not None
        and step.transform_ref.name == "mrw.traverse_ordered.materialize"
    )
    return {
        "cell_id": "C3.1",
        "p1_cell_digest": _p1_cell_digest("C3.1"),
        "operation_bindings": [
            {
                "operation_kind": "collect.execute_batch_element.v1",
                "contract_digest": element_contract.contract_digest,
                "role": "element_atom",
            },
            {
                "operation_kind": "mrw.traverse_ordered.materialize",
                "contract_digest": traverse_step.transform_ref.digest,
                "role": "traversal_materialization",
            },
            {
                "operation_kind": "collect.fold_ordered_results.v1",
                "contract_digest": fold_contract.contract_digest,
                "role": "fold_atom",
            },
        ],
        "owner_capability_id": fixture["bundle"].operation_c3_1.owner_capability_id,
        "program_digest": {
            "value": fixture["composed_program"].program_digest,
            "reason": (
                "composed Then(TraverseOrdered, MapOutput(sequence_to_fold_payload), "
                "FoldAtom) Program binding the actual traversal epoch"
            ),
        },
        "plan_digest": {
            "value": composed_plan.plan_digest,
            "reason": (
                "compiled ExecutionPlan with SUCCESSOR_PROGRAM_EPOCH traversal "
                "materialization and one fold EFFECT step"
            ),
        },
        "legacy_observation": {
            "interpreter_id": "legacy.collect_runtime.batch_traverse.v1",
            "trace_digest": fixture["legacy_trace_digest"],
            "composed_shadow_digest": fixture["legacy_composed_shadow_digest"],
            "provider_calls": 0,
        },
        "successor_observation": {
            "interpreter_id": "successor.collect_runtime.batch_traverse.v1",
            "observation_profile": "collect.batch_traverse.ordered_observation.v1",
            "observation_digest": fixture["observation_digest"],
            "composed_aggregate_digest": fixture["successor_composed_aggregate_digest"],
            "payload_closure_digest": dict(fixture["composed_program"].metadata)[
                "payload_content_digest"
            ],
            "payload_element_count": dict(fixture["composed_program"].metadata)[
                "payload_element_count"
            ],
            "payload_incarnation": dict(fixture["composed_program"].metadata)[
                "payload_incarnation"
            ],
            "provider_calls": 0,
        },
        "rollback_observation": {
            "claim_owner": "legacy",
            "mode": "SUCCESSOR_RUNTIME_COLLECT=off",
            "route": "legacy",
            "journal_readable": True,
            "dual_claim": False,
            "rollback_digest": _rollback_digest(),
        },
        "provider_calls": 0,
        "postgres_requirement": POSTGRES_REQUIREMENT,
    }


def _cell_c3_2(fixture: dict[str, Any]) -> dict[str, Any]:
    fold = fixture["bundle"].operation_c3_2
    pure_plan = fixture["pure_plan"]
    fold_transform_step = next(
        step
        for step in pure_plan.ordered_steps
        if step.step_kind == "TRANSFORM" and step.transform_ref is not None
    )
    return {
        "cell_id": "C3.2",
        "p1_cell_digest": _p1_cell_digest("C3.2"),
        "operation_bindings": [
            {
                "operation_kind": "collect.fold_ordered_results.v1",
                "contract_digest": fold.ref.contract_digest,
                "role": "ordered_fold_atom",
            },
            {
                "operation_kind": "collect.fold_ordered_results",
                "contract_digest": fold_transform_step.transform_ref.digest,
                "role": "named_pure_fold_transform",
            },
        ],
        "owner_capability_id": fold.owner_capability_id,
        "program_digest": {
            "value": fixture["pure_program"].program_digest,
            "reason": "named pure fold Program realized as a registered TRANSFORM",
        },
        "plan_digest": {
            "value": pure_plan.plan_digest,
            "reason": "compiled ExecutionPlan with exactly one PURE_TRANSFORM step",
        },
        "legacy_observation": {
            "interpreter_id": "legacy.collect_runtime.result_fold.v1",
            "aggregate_digest": fixture["legacy_aggregate_digest"],
            "provider_calls": 0,
        },
        "successor_observation": {
            "interpreter_id": "successor.collect_runtime.result_fold.v1",
            "observation_profile": "collect.result_fold.receipt_preservation.v1",
            "aggregate_digest": fixture["successor_aggregate_digest"],
            "fold_realization": "PURE_TRANSFORM",
            "provider_calls": 0,
        },
        "rollback_observation": {
            "claim_owner": "legacy",
            "mode": "SUCCESSOR_RUNTIME_COLLECT=off",
            "route": "legacy",
            "journal_readable": True,
            "dual_claim": False,
            "rollback_digest": _rollback_digest(),
        },
        "provider_calls": 0,
        "postgres_requirement": POSTGRES_REQUIREMENT,
    }


def build_fragment() -> dict[str, Any]:
    """Return the complete deterministic fragment without the digest field."""

    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))

    c3_1 = _c3_1_fixtures()
    c3_2 = _c3_2_fixtures()

    source_bindings = [
        _file_binding(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "P1FunctorizationEligibility.v1.json",
            "p1_eligibility",
        ),
        _file_binding(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "p1-fragments/C3.json",
            "p1_fragment",
        ),
        _file_binding(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "P2C21CapabilityPacket.v4.json",
            "shared_traversal_review_evidence",
            read_only=True,
        ),
        _file_binding(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "P2C21CapabilityPacket.v3.json",
            "shared_traversal_review_superseded",
            read_only=True,
        ),
        _file_binding(
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "P2C21CapabilityPacket.v2.json",
            "shared_traversal_review_superseded",
            read_only=True,
        ),
    ]
    source_bindings.extend(
        _file_binding(path, role) for path, role in LEGACY_SOURCE_FILES
    )
    source_bindings.extend(
        _file_binding(path, "shared_dependency_traverse_ordered", read_only=True)
        for path in SHARED_TRAVERSAL_DEPENDENCIES
    )

    implementation_bindings = [
        _file_binding(path, role) for path, role in IMPLEMENTATION_FILES
    ]
    test_bindings = [_file_binding(path, role) for path, role in TEST_FILES]

    fragment: dict[str, Any] = {
        "schema": FRAGMENT_SCHEMA,
        "phase": "P3",
        "family": "C3",
        "fragment_id": FRAGMENT_ID,
        "status": FRAGMENT_STATUS,
        "cells": [_cell_c3_1(c3_1), _cell_c3_2(c3_2)],
        "source_bindings": source_bindings,
        "implementation_bindings": implementation_bindings,
        "test_bindings": test_bindings,
        "authority": {
            "p3_promotion": False,
            "production_canonical_write": False,
            "live_provider": False,
            "external_delivery": False,
            "live_credential": False,
            "network": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
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
                "id": "C3_POSTGRES_CANARY_DISPOSABLE_ONLY",
                "severity": "P1",
                "description": (
                    "PG canary executed on disposable mrw_p3_c3_worker_test with "
                    "teardown; production database/cutover is not claimed"
                ),
            },
            {
                "id": "C3_LIVE_PROVIDER_AUTHORITY_NOT_FROZEN",
                "severity": "P0",
                "description": (
                    "live provider/network, authoritative provider readback and "
                    "idempotency/non-start proof are not frozen"
                ),
            },
            {
                "id": "C3_DURABLE_RUNTIME_NODE_NOT_PROVEN",
                "severity": "P1",
                "description": (
                    "successor execution is fixture/unit-level only; durable "
                    "runtime-node journal/replay/rollback is not proven"
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
    }
    fragment["content_digest"] = _canonical_digest(
        {key: value for key, value in fragment.items() if key != "content_digest"}
    )
    return fragment


def fragment_bytes(fragment: dict[str, Any]) -> bytes:
    """Canonical file bytes; deterministic for identical fragments."""

    return (
        json.dumps(
            fragment,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def write_fragment() -> Path:
    _TOPIC.mkdir(parents=True, exist_ok=True)
    _FRAGMENT_PATH.write_bytes(fragment_bytes(build_fragment()))
    return _FRAGMENT_PATH


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the deterministic P3 C3 evidence fragment."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the topic fragment matches a fresh deterministic build",
    )
    args = parser.parse_args()
    if args.check:
        expected = fragment_bytes(build_fragment())
        if not _FRAGMENT_PATH.exists():
            print(f"missing fragment: {_FRAGMENT_PATH}")
            return 1
        actual = _FRAGMENT_PATH.read_bytes()
        if actual != expected:
            print("fragment drift detected; rerun without --check")
            return 1
        print("fragment deterministic and current")
        return 0
    path = write_fragment()
    print(f"wrote {_relative(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
