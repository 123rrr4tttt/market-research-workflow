"""Deterministically generate the normalized P4 C7 evidence fragment.

Root schema: ``mrw.functorial_successor.p4_fragment.v1``.  The fragment is
ahead-of-time family-local scaffolding only and stays ``P4_NOT_STARTED``.  It
binds the real shared successor identities used by the C7 slice, the frozen
P1 locators, the compiled EFFECT+ADMISSION plan, typed commit readback,
DocumentRef projection offsets/rebuild, recovery decisions, and the legacy
actual postprocess writer-zero replay without running any provider, canonical
write, index or graph effect.  Run from ``main/backend``:

    python3.11 scripts/generate_successor_p4_c7_fragment.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.successor_migration.document_repository_c7 import (
    CanonicalCommitReadback,
    TestDocumentRepositoryC7,
    document_ref_from_readback,
)
from app.successor_migration.graph_projector_c7 import (
    build_graph_projection,
    graph_named_observation_digest,
    rebuild_graph_projection,
)
from app.successor_migration.ingest_recovery_c7 import (
    C7ReconciliationPolicy,
)
from app.successor_migration.legacy_ingest_c7 import (
    capture_legacy_ingest_c7_fixture,
    frozen_p1_cell_locators,
)
from app.successor_migration.search_projector_c7 import (
    build_search_projection,
    rebuild_search_projection,
    search_named_observation_digest,
)
from app.successor_runtime.capabilities import (
    ingest_c7_common as c7,
)
from app.successor_runtime.capabilities import (
    ingest_c7_interpreters as c7i,
)
from app.successor_runtime.capabilities import (
    ingest_c7_program as c7p,
)

PROJECT_KEY = "p4-c7-fragment"
REGISTRY_REVISION = 1
RESOLVED_SCHEMA = "mrw_p4_c7_fragment"
SCOPE_INCARNATION = "scope-inc-c7-fragment"
SCOPE_DIGEST = c7.content_digest(
    {
        "project_key": PROJECT_KEY,
        "resolved_schema": RESOLVED_SCHEMA,
        "registry_revision": REGISTRY_REVISION,
        "scope_incarnation": SCOPE_INCARNATION,
    }
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_ROOT = (
    REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
FRAGMENT_PATH = EVIDENCE_ROOT / "p4-fragments" / "C7.json"
P1_FRAGMENT_PATH = EVIDENCE_ROOT / "p1-fragments" / "C7.json"
FRAGMENT_ID = "p4-c7-ahead-of-time-family-local-scaffolding"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p4_fragment.v1"
FRAGMENT_PHASE = "P4"
FRAGMENT_FAMILY = "C7"
FRAGMENT_STATUS = c7.AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED
FRAGMENT_LIFECYCLE_STATE = "P4_NOT_STARTED"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_digest(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


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


def _submission() -> c7.C7IngestSubmission:
    return c7.C7IngestSubmission(
        idempotency_key="idem:p4-c7-fragment:001",
        project_key=PROJECT_KEY,
        source_locator="https://example.invalid/report",
        request_key="req:p4-c7-fragment:001",
        raw_payload={
            "title": "Q2 Market",
            "text": "Market grew 12% in Q2.",
        },
    )


def _verification_binding() -> Any:
    from app.successor_runtime.runtime.admission import VerificationBinding

    submission = _submission()
    normalized = c7.normalize_ingest_submission(submission)
    bundle = c7.build_ingest_c7_bundle()
    catalog = c7.build_ingest_c7_catalog(bundle)
    registry = c7.build_ingest_c7_registry(bundle)
    program = c7p.build_ingest_c7_1_program(
        payload=submission,
        catalog=catalog,
        program_id="program:p4-c7-fragment",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = c7p.compile_ingest_c7_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    admission_steps = [
        step for step in plan.ordered_steps if step.step_kind == "ADMISSION"
    ]
    if len(admission_steps) != 1:
        raise AssertionError("C7.1 plan must contain exactly one ADMISSION step")
    events = (
        {
            "seq": 1,
            "event_type": "submitted",
            "payload": {"request_key": submission.request_key},
        },
        {
            "seq": 2,
            "event_type": "fetched",
            "payload": {"source_locator": submission.source_locator},
        },
        {
            "seq": 3,
            "event_type": "normalized",
            "payload": {"content_digest": normalized.content_digest},
        },
        {
            "seq": 4,
            "event_type": "candidate_created",
            "payload": {"candidate_id": "ingest-candidate-p4c7-fragment"},
        },
    )
    return VerificationBinding.from_content(
        program_digest=program.program_digest,
        plan_digest=plan.plan_digest,
        step_id=admission_steps[0].step_id,
        attempt_id=content_digest({"attempt": "p4-c7-fragment:001"}),
        input_closure_digest=program.root.operation.payload_ref.content_digest,
        output_content_digest=normalized.content_digest,
        ordered_event_payloads=events,
        schema_digest=content_digest({"schema": "ingest.c7.admission.v1"}),
        compiler_identity=plan.compiler_id,
        interpreter_identity=bundle.profiles["interpreter"].profile_id,
        verifier_identity="ingest.validator.c7.v1",
        actor_id="actor:p4-c7-fragment",
        project_key=PROJECT_KEY,
        authority_digest=content_digest({"authority": False}),
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        resolved_schema=RESOLVED_SCHEMA,
        canonical_owner=c7.DOCUMENT_CANONICAL_OWNER,
        canonical_object_id="ingest-candidate-p4c7-fragment",
        canonical_base_revision=0,
        canonical_incarnation=SCOPE_INCARNATION,
        evidence_digest=content_digest({"evidence": "c7-fragment"}),
        receipt_digest=content_digest({"receipt": "c7-fragment"}),
        provenance_digest=content_digest({"provenance": "c7-fragment"}),
        qualifier="staged-candidate",
    )


def _commit_intent() -> Any:
    from app.successor_runtime.runtime.admission import (
        CommitIntent,
        CommitIntentState,
    )

    binding = _verification_binding()
    return CommitIntent(
        commit_intent_id="commit:p4-c7-fragment:001",
        canonical_owner=c7.DOCUMENT_CANONICAL_OWNER,
        project_key=PROJECT_KEY,
        object_id="ingest-candidate-p4c7-fragment",
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        expected_base_revision=0,
        expected_incarnation=SCOPE_INCARNATION,
        content_digest=binding.output_content_digest,
        ordered_event_closure_digest=binding.ordered_event_payload_closure_digest,
        verification_binding_digest=binding.binding_digest,
        authority_digest=binding.authority_digest,
        idempotency_key="idem:p4-c7-fragment:001",
        state=CommitIntentState.PREPARED,
    )


def _c7_1_observation() -> tuple[dict[str, object], dict[str, object]]:
    payload = _submission()
    bundle = c7.build_ingest_c7_bundle()
    catalog = c7.build_ingest_c7_catalog(bundle)
    registry = c7.build_ingest_c7_registry(bundle)
    program = c7p.build_ingest_c7_1_program(
        payload=payload,
        catalog=catalog,
        program_id="program:p4-c7-fragment",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = c7p.compile_ingest_c7_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    outcome = c7.stage_ingest_submission(payload)
    legacy, replay = capture_legacy_ingest_c7_fixture(payload)
    effect_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    if len(effect_steps) != 1:
        raise AssertionError("C7.1 plan must contain exactly one EFFECT step")
    effect_step = effect_steps[0]
    return {
        "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest,
        "step_kinds": [step.step_kind for step in plan.ordered_steps],
        "admission_required": True,
        "return_contract_ref": c7.C7_ADMISSION_RETURN_CONTRACT_REF,
        "execution_class": bundle.profiles["effect"].execution_class,
        "runtime_assignment_closure": {
            "program_digest": program.program_digest,
            "plan_digest": plan.plan_digest,
            "step_id": effect_step.step_id,
            "step_role": effect_step.step_kind,
            "operation_contract_digest": (
                effect_step.operation_contract_ref.contract_digest
            ),
            "interpreter_profile_digest": (
                bundle.profiles["interpreter"].profile_digest
            ),
            "verification_binding_digest": _verification_binding().binding_digest,
        },
        "candidate_id": outcome.receipt["candidate_id"],
        "stage": outcome.receipt["stage"],
        "content_digest": outcome.receipt["content_digest"],
        "admission_implied": outcome.receipt["admission_implied"],
        "document_write_boundary": outcome.receipt["document_write_boundary"],
        "provider_calls": 0,
        "authority": False,
    }, {
        "interpreter_id": replay.interpreter_id,
        "postprocess_status": legacy["postprocess_status"],
        "postprocess_admission": legacy["postprocess_admission"],
        "writer_calls": replay.writer_calls,
        "provider_calls": 0,
        "authority": False,
    }


def _c7_2_observation() -> tuple[dict[str, object], dict[str, object]]:
    intent = _commit_intent()
    binding = _verification_binding()
    repo = TestDocumentRepositoryC7()
    readback = repo.prepare(intent, verification_binding=binding)
    outcome = c7i.interpret_commit_readback(
        commit_intent_id=readback.commit_intent_id,
        content_digest_hex=readback.content_digest,
        verification_binding_digest=readback.verification_binding_digest,
        state=readback.state,
    )
    value = outcome.value
    return {
        "commit_intent_id": readback.commit_intent_id,
        "readback_digest": readback.readback_digest,
        "state": readback.state,
        "document_write": value["document_write"],
        "provider_calls": value["provider_calls"],
        "authority": value["authority"],
    }, {
        "interpreter_id": "legacy.ingest_index.postprocess_frontdoor.replay.v1",
        "writer_enabled": False,
        "writer_calls": repo.write_calls,
        "document_write": False,
        "provider_calls": 0,
        "authority": False,
    }


def _c7_3_observation() -> tuple[dict[str, object], dict[str, object]]:
    intent = _commit_intent()
    readback = CanonicalCommitReadback(
        commit_intent_id=intent.commit_intent_id,
        idempotency_key=intent.idempotency_key,
        capability_id=c7.C7_INGEST_OWNER,
        project_key=intent.project_key,
        object_id=intent.object_id,
        committed_revision=1,
        committed_incarnation=intent.expected_incarnation,
        content_digest=intent.content_digest,
        canonical_commit_ref="canonical:document:p4-c7-fragment:1",
    )
    ref = document_ref_from_readback(readback)
    search = build_search_projection(
        ref,
        title="Q2 Market",
        text="Market grew 12% in Q2.",
    )
    graph = build_graph_projection(ref, source_locator=ref.incarnation)
    search_rebuild = rebuild_search_projection(ref)
    graph_rebuild = rebuild_graph_projection(ref)
    return {
        "document_ref": {
            "project_key": ref.project_key,
            "object_id": ref.object_id,
            "revision": ref.revision,
            "incarnation": ref.incarnation,
            "content_digest": ref.content_digest,
            "binding_digest": ref.binding_digest,
        },
        "search_projection_digest": search.projection_digest,
        "graph_projection_digest": graph.projection_digest,
        "search_rebuild_digest": search_rebuild.projection_digest,
        "graph_rebuild_digest": graph_rebuild.projection_digest,
        "search_offset_key": search.source.to_offset_key(),
        "graph_offset_key": graph.source.to_offset_key(),
        "search_offset": {
            "source_revision": readback.committed_revision,
            "source_digest": readback.content_digest,
            "offset_ref": f"document-revision:{readback.committed_revision}",
        },
        "graph_offset": {
            "source_revision": readback.committed_revision,
            "source_digest": readback.content_digest,
            "offset_ref": f"document-revision:{readback.committed_revision}",
        },
        "search_named_observation_digest": search_named_observation_digest(ref),
        "graph_named_observation_digest": graph_named_observation_digest(ref),
        "declared_loss": {
            "search": [item[0] for item in search.declared_loss],
            "graph": [item[0] for item in graph.declared_loss],
        },
        "provider_calls": 0,
        "authority": False,
    }, {
        "interpreter_id": "legacy.ingest_index.index_graph_handoff.observation.v1",
        "index_write": 0,
        "graph_write": 0,
        "provider_calls": 0,
        "authority": False,
    }


def _c7_4_observation() -> tuple[dict[str, object], dict[str, object]]:
    policy = C7ReconciliationPolicy()
    unresolved = policy.terminal_decision(
        __import__(
            "app.successor_runtime.runtime.transitions",
            fromlist=["EffectDisposition"],
        ).EffectDisposition.FAILED
    )
    return {
        "disposition": "OUTCOME_UNKNOWN_REQUIRES_READBACK",
        "new_attempt_allowed": unresolved.new_attempt_allowed,
        "requirement": unresolved.requirement,
        "reason": unresolved.reason,
        "provider_calls": 0,
        "authority": False,
    }, {
        "interpreter_id": "legacy.ingest_index.recovery.observation.v1",
        "readback": None,
        "nonstart_proof": None,
        "provider_calls": 0,
        "authority": False,
    }


def _bindings() -> tuple[
    list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]
]:
    source_paths = [
        (
            BACKEND_ROOT / "app/services/ingest/frontdoor_orchestrator.py",
            "frozen_locator_frontdoor_orchestrator",
        ),
        (
            BACKEND_ROOT / "app/models/entities.py",
            "frozen_locator_entities",
        ),
        (
            BACKEND_ROOT / "app/services/graph/persistence/graph_node_writer.py",
            "frozen_locator_graph_persistence",
        ),
        (
            BACKEND_ROOT / "app/services/ingest/digestion_scaffold.py",
            "frozen_locator_dry_run",
        ),
        (
            BACKEND_ROOT / "app/services/ingest/cleanup_executor.py",
            "frozen_locator_cleanup",
        ),
        (
            BACKEND_ROOT / "app/models/base.py",
            "frozen_locator_db_retry",
        ),
        (
            BACKEND_ROOT / "app/services/ingest/frontdoor_rollout.py",
            "frozen_locator_rollout",
        ),
        (
            BACKEND_ROOT / "app/services/ingest/frontdoor_ingress.py",
            "legacy_donor_c7_1",
        ),
        (
            BACKEND_ROOT / "app/services/ingest/postprocess_frontdoor.py",
            "legacy_donor_c7_1_c7_2_writer_zero_replay",
        ),
        (
            BACKEND_ROOT / "app/services/ingest/terminal_writer.py",
            "legacy_donor_c7_2_writer_hard_disabled",
        ),
        (
            BACKEND_ROOT / "app/services/indexer/policy.py",
            "legacy_donor_c7_3_index_policy",
        ),
        (
            BACKEND_ROOT / "app/services/graph/builder.py",
            "legacy_donor_c7_3_graph_builder",
        ),
        (P1_FRAGMENT_PATH, "p1_fragment_locators"),
        (
            BACKEND_ROOT / "app/successor_runtime/language/program.py",
            "shared_program_spec",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/language/compile.py",
            "shared_compiler",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/language/plan.py",
            "shared_execution_plan",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/language/object_contracts.py",
            "shared_document_admission_return_contract_registry",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/runtime/admission.py",
            "shared_commit_intent_verification_binding",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/runtime/reconciliation.py",
            "shared_effect_reconciler",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/runtime/recovery.py",
            "shared_nonstart_proof",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/runtime/assignments.py",
            "shared_runtime_assignment",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/substrate/postgres/commit_intents.py",
            "shared_commit_intent_repository",
        ),
        (
            BACKEND_ROOT
            / "app/successor_runtime/substrate/postgres/projection_offsets.py",
            "shared_projection_offset_repository",
        ),
    ]
    implementation_paths = [
        (
            BACKEND_ROOT / "app/successor_runtime/capabilities/ingest_c7_common.py",
            "c7_common_contracts",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/capabilities/ingest_c7.py",
            "c7_contracts",
        ),
        (
            BACKEND_ROOT / "app/successor_runtime/capabilities/ingest_c7_program.py",
            "c7_program",
        ),
        (
            BACKEND_ROOT
            / "app/successor_runtime/capabilities/ingest_c7_interpreters.py",
            "c7_interpreters",
        ),
        (
            BACKEND_ROOT / "app/successor_migration/legacy_ingest_c7.py",
            "c7_legacy_adapter",
        ),
        (
            BACKEND_ROOT / "app/successor_migration/document_repository_c7.py",
            "c7_document_repository",
        ),
        (
            BACKEND_ROOT / "app/successor_migration/projection_common_c7.py",
            "c7_projection_common",
        ),
        (
            BACKEND_ROOT / "app/successor_migration/ingest_recovery_c7.py",
            "c7_recovery",
        ),
        (
            BACKEND_ROOT / "app/successor_migration/search_projector_c7.py",
            "c7_search_projector",
        ),
        (
            BACKEND_ROOT / "app/successor_migration/graph_projector_c7.py",
            "c7_graph_projector",
        ),
        (Path(__file__).resolve(), "evidence_generator"),
    ]
    test_paths = [
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p4_c7_0_return_registry.py",
            "c7_0_return_registry_invariants",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p4_c7_1_staged_candidate.py",
            "c7_1_staged_candidate",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p4_c7_1_program.py",
            "c7_1_program",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p4_c7_2_commit_readback.py",
            "c7_2_commit_readback",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p4_c7_3_projection_diff.py",
            "c7_3_projection_diff",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p4_c7_4_reconciliation.py",
            "c7_4_reconciliation",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p4_c7_legacy_writer_spy.py",
            "c7_legacy_writer_spy",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p4_c7_5_evidence_generator.py",
            "c7_evidence_generator",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/test_p4_c7_6_postgres.py",
            "c7_6_disposable_postgres",
        ),
        (
            BACKEND_ROOT / "tests/successor_runtime/p4_c7_fixture.py",
            "c7_shared_fixture",
        ),
    ]
    return (
        [_bind(path, role) for path, role in source_paths],
        [_bind(path, role) for path, role in implementation_paths],
        [_bind(path, role) for path, role in test_paths],
    )


def build_fragment() -> dict[str, object]:
    c7_1_successor, c7_1_legacy = _c7_1_observation()
    c7_2_successor, c7_2_legacy = _c7_2_observation()
    c7_3_successor, c7_3_legacy = _c7_3_observation()
    c7_4_successor, c7_4_legacy = _c7_4_observation()
    source_bindings, implementation_bindings, test_bindings = _bindings()
    p1_locators = frozen_p1_cell_locators()

    fragment: dict[str, object] = {
        "schema": FRAGMENT_SCHEMA,
        "phase": FRAGMENT_PHASE,
        "family": FRAGMENT_FAMILY,
        "fragment_id": FRAGMENT_ID,
        "status": FRAGMENT_STATUS,
        "lifecycle_state": FRAGMENT_LIFECYCLE_STATE,
        "cells": [
            {
                "cell_id": "C7.1",
                "p1_locators": p1_locators["C7.1"],
                "contract_ids": (
                    c7.STAGE_CANDIDATE_KIND,
                    c7.NONSTART_RECONCILIATION_CONTRACT_ID,
                ),
                "legacy_observation": c7_1_legacy,
                "successor_observation": c7_1_successor,
                "rollback_observation": {
                    "rollback_digest": content_digest(
                        {
                            "claim_owner": "legacy",
                            "plan_digest_retained": c7_1_successor["plan_digest"],
                            "no_new_attempt": True,
                        }
                    ),
                    "claim_owner": "legacy",
                    "plan_retained": True,
                },
                "provider_calls": 0,
                "postgres_requirement": "not_required",
            },
            {
                "cell_id": "C7.2",
                "p1_locators": p1_locators["C7.2"],
                "contract_ids": (
                    c7.COMMIT_INTENT_CONTRACT_ID,
                    c7.ADMISSION_READBACK_CONTRACT_ID,
                ),
                "legacy_observation": c7_2_legacy,
                "successor_observation": c7_2_successor,
                "rollback_observation": {
                    "rollback_digest": content_digest(
                        {
                            "claim_owner": "legacy",
                            "document_write": False,
                            "admission_implied": False,
                        }
                    ),
                    "claim_owner": "legacy",
                    "document_write": False,
                },
                "provider_calls": 0,
                "postgres_requirement": "disposable_pg_prepared_readback",
            },
            {
                "cell_id": "C7.3",
                "p1_locators": p1_locators["C7.3"],
                "contract_ids": (c7.PROJECTION_DIFF_CONTRACT_ID,),
                "legacy_observation": c7_3_legacy,
                "successor_observation": c7_3_successor,
                "rollback_observation": {
                    "rollback_digest": content_digest(
                        {
                            "claim_owner": "legacy",
                            "index_write": 0,
                            "graph_write": 0,
                            "projection_rebuild_no_effect": True,
                        }
                    ),
                    "claim_owner": "legacy",
                    "index_write": 0,
                    "graph_write": 0,
                },
                "provider_calls": 0,
                "postgres_requirement": "disposable_pg_projection_offset",
            },
            {
                "cell_id": "C7.4",
                "p1_locators": p1_locators["C7.4"],
                "contract_ids": (
                    c7.READBACK_RECONCILIATION_CONTRACT_ID,
                    c7.NONSTART_RECONCILIATION_CONTRACT_ID,
                ),
                "legacy_observation": c7_4_legacy,
                "successor_observation": c7_4_successor,
                "rollback_observation": {
                    "rollback_digest": content_digest(
                        {
                            "claim_owner": "legacy",
                            "new_attempt_allowed": False,
                            "outcome_unknown": True,
                        }
                    ),
                    "claim_owner": "legacy",
                    "new_attempt_allowed": False,
                },
                "provider_calls": 0,
                "postgres_requirement": "disposable_pg_recovery_readback",
            },
        ],
        "source_bindings": source_bindings,
        "implementation_bindings": implementation_bindings,
        "test_bindings": test_bindings,
        "authority": {
            "canonical_write": False,
            "provider": False,
            "index": False,
            "graph": False,
            "credential": False,
        },
        "open_findings": [
            {
                "id": "C7_AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED",
                "severity": "info",
                "detail": (
                    "P4 C7 files are family-local scaffolding only; no adoption, "
                    "promotion or runtime wiring is claimed."
                ),
            },
            {
                "id": "C7_P4_NOT_STARTED",
                "severity": "info",
                "detail": (
                    "Lifecycle stays P4_NOT_STARTED; shared runtime identities are "
                    "bound, but no canonical/provider/index/graph effect ran."
                ),
            },
        ],
        "content_digest": "",
    }
    fragment["content_digest"] = content_digest(
        {key: value for key, value in fragment.items() if key != "content_digest"}
    )
    return fragment


def _self_test(fragment: dict[str, object]) -> None:
    expected = content_digest(
        {key: value for key, value in fragment.items() if key != "content_digest"}
    )
    assert fragment["content_digest"] == expected
    assert fragment["status"] == FRAGMENT_STATUS
    assert fragment["lifecycle_state"] == FRAGMENT_LIFECYCLE_STATE
    assert all(not value for value in fragment["authority"].values())
    for cell in fragment["cells"]:
        assert cell["provider_calls"] == 0
        assert cell["successor_observation"]["provider_calls"] == 0
        assert cell["legacy_observation"]["provider_calls"] == 0
        assert cell["successor_observation"]["authority"] is False
        assert cell["legacy_observation"]["authority"] is False
        assert cell["rollback_observation"]["rollback_digest"]
        assert cell["p1_locators"]["locator_paths"]


def main() -> None:
    FRAGMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    first = build_fragment()
    second = build_fragment()
    assert _canonical_json(first) == _canonical_json(second)
    _self_test(first)
    FRAGMENT_PATH.write_text(
        _canonical_json(first) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {FRAGMENT_PATH.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
