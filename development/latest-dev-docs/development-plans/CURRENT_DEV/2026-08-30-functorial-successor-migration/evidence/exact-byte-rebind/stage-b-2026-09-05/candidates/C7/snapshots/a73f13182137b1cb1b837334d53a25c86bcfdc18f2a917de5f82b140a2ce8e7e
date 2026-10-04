"""Thin C7/P4 family fragment config for the shared family generator.

This module declares only the C7 family data and differences: family identity,
the C7.1 capability cell spec and runtime kernel ABI inputs, exact binding
targets, the four C7.1-C7.4 cell declarations and the family observation glue
that calls the existing C7 modules.  No full fragment generator is copied;
shared schema/digest/path/authority/check mechanics live in
``shared_family_generator``.
"""

from __future__ import annotations

from typing import Any

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
from app.successor_migration.ingest_recovery_c7 import C7ReconciliationPolicy
from app.successor_migration.legacy_ingest_c7 import capture_legacy_ingest_c7_fixture
from app.successor_migration.search_projector_c7 import (
    build_search_projection,
    rebuild_search_projection,
    search_named_observation_digest,
)
from app.successor_runtime.capabilities import ingest_c7_common as c7
from app.successor_runtime.capabilities import ingest_c7_interpreters as c7i
from app.successor_runtime.capabilities import ingest_c7_program as c7p
from app.successor_runtime.specification.shared_family_generator import (
    BindingTarget,
    CellFragmentConfig,
    FamilyFragmentConfig,
    content_digest,
)

PROJECT_KEY = "p4-c7-fragment"
REGISTRY_REVISION = 1
RESOLVED_SCHEMA = "mrw_p4_c7_fragment"
SCOPE_INCARNATION = "scope-inc-c7-fragment"
FRAGMENT_ID = "p4-c7-ahead-of-time-family-local-scaffolding"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p4_fragment.v1"
FRAGMENT_PHASE = "P4"
FRAGMENT_FAMILY = "C7"
FRAGMENT_STATUS = c7.AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED
FRAGMENT_LIFECYCLE_STATE = "P4_NOT_STARTED"

_EVIDENCE_ROOT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
CELL_SPEC_PATH = f"{_EVIDENCE_ROOT}/capability-specs/C7.1.v1.json"
RUNTIME_KERNEL_ABI_PATH = f"{_EVIDENCE_ROOT}/capability-specs/RuntimeKernelABI.v1.json"
FRAGMENT_OUTPUT_REL = f"{_EVIDENCE_ROOT}/p4-fragments/C7.json"

SCOPE_DIGEST = content_digest(
    {
        "project_key": PROJECT_KEY,
        "resolved_schema": RESOLVED_SCHEMA,
        "registry_revision": REGISTRY_REVISION,
        "scope_incarnation": SCOPE_INCARNATION,
    }
)

_SOURCE_BINDINGS = (
    BindingTarget(
        "main/backend/app/services/ingest/frontdoor_orchestrator.py",
        "frozen_locator_frontdoor_orchestrator",
    ),
    BindingTarget(
        "main/backend/app/models/entities.py",
        "frozen_locator_entities",
    ),
    BindingTarget(
        "main/backend/app/services/graph/persistence/graph_node_writer.py",
        "frozen_locator_graph_persistence",
    ),
    BindingTarget(
        "main/backend/app/services/ingest/digestion_scaffold.py",
        "frozen_locator_dry_run",
    ),
    BindingTarget(
        "main/backend/app/services/ingest/cleanup_executor.py",
        "frozen_locator_cleanup",
    ),
    BindingTarget(
        "main/backend/app/models/base.py",
        "frozen_locator_db_retry",
    ),
    BindingTarget(
        "main/backend/app/services/ingest/frontdoor_rollout.py",
        "frozen_locator_rollout",
    ),
    BindingTarget(
        "main/backend/app/services/ingest/frontdoor_ingress.py",
        "legacy_donor_c7_1",
    ),
    BindingTarget(
        "main/backend/app/services/ingest/postprocess_frontdoor.py",
        "legacy_donor_c7_1_c7_2_writer_zero_replay",
    ),
    BindingTarget(
        "main/backend/app/services/ingest/terminal_writer.py",
        "legacy_donor_c7_2_writer_hard_disabled",
    ),
    BindingTarget(
        "main/backend/app/services/indexer/policy.py",
        "legacy_donor_c7_3_index_policy",
    ),
    BindingTarget(
        "main/backend/app/services/graph/builder.py",
        "legacy_donor_c7_3_graph_builder",
    ),
    BindingTarget(
        f"{_EVIDENCE_ROOT}/p1-fragments/C7.json",
        "p1_fragment_locators",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/language/program.py",
        "shared_program_spec",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/language/compile.py",
        "shared_compiler",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/language/plan.py",
        "shared_execution_plan",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/language/object_contracts.py",
        "shared_document_admission_return_contract_registry",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/runtime/admission.py",
        "shared_commit_intent_verification_binding",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/runtime/reconciliation.py",
        "shared_effect_reconciler",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/runtime/recovery.py",
        "shared_nonstart_proof",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/runtime/assignments.py",
        "shared_runtime_assignment",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/postgres/commit_intents.py",
        "shared_commit_intent_repository",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/substrate/postgres/projection_offsets.py",
        "shared_projection_offset_repository",
    ),
)

_IMPLEMENTATION_BINDINGS = (
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/ingest_c7_common.py",
        "c7_common_contracts",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/ingest_c7.py",
        "c7_contracts",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/ingest_c7_program.py",
        "c7_program",
    ),
    BindingTarget(
        "main/backend/app/successor_runtime/capabilities/ingest_c7_interpreters.py",
        "c7_interpreters",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/legacy_ingest_c7.py",
        "c7_legacy_adapter",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/document_repository_c7.py",
        "c7_document_repository",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/projection_common_c7.py",
        "c7_projection_common",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/ingest_recovery_c7.py",
        "c7_recovery",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/search_projector_c7.py",
        "c7_search_projector",
    ),
    BindingTarget(
        "main/backend/app/successor_migration/graph_projector_c7.py",
        "c7_graph_projector",
    ),
    BindingTarget(
        "main/backend/scripts/generate_successor_p4_c7_fragment.py",
        "evidence_generator",
    ),
)

_TEST_BINDINGS = (
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c7_0_return_registry.py",
        "c7_0_return_registry_invariants",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c7_1_staged_candidate.py",
        "c7_1_staged_candidate",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c7_1_program.py",
        "c7_1_program",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c7_2_commit_readback.py",
        "c7_2_commit_readback",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c7_3_projection_diff.py",
        "c7_3_projection_diff",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c7_4_reconciliation.py",
        "c7_4_reconciliation",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c7_legacy_writer_spy.py",
        "c7_legacy_writer_spy",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c7_5_evidence_generator.py",
        "c7_evidence_generator",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p4_c7_6_postgres.py",
        "c7_6_disposable_postgres",
    ),
    BindingTarget(
        "main/backend/tests/successor_runtime/p4_c7_fixture.py",
        "c7_shared_fixture",
    ),
)

_CELLS = (
    CellFragmentConfig(
        cell_id="C7.1",
        contract_ids=(
            c7.STAGE_CANDIDATE_KIND,
            c7.NONSTART_RECONCILIATION_CONTRACT_ID,
        ),
        p1_locator_paths=(
            "main/backend/app/services/ingest/frontdoor_orchestrator.py",
            "main/backend/app/services/ingest/terminal_writer.py",
        ),
        p1_locator_status=(
            "FROZEN_LOCATORS_PRESENT; frozen hashes for 06 and 13 match manifest; "
            "FrontDoorOrchestrator is repository-observed only in its unit test, "
            "while the live postprocess path calls terminal_writer directly"
        ),
        postgres_requirement="not_required",
    ),
    CellFragmentConfig(
        cell_id="C7.2",
        contract_ids=(
            c7.COMMIT_INTENT_CONTRACT_ID,
            c7.ADMISSION_READBACK_CONTRACT_ID,
        ),
        p1_locator_paths=(
            "main/backend/app/services/ingest",
            "main/backend/app/models/entities.py",
        ),
        p1_locator_status=(
            "FROZEN_LOCATORS_PRESENT; live persistence exists, but quality "
            "admission, canonical verification and commit are not separate "
            "contracts"
        ),
        postgres_requirement="disposable_pg_prepared_readback",
    ),
    CellFragmentConfig(
        cell_id="C7.3",
        contract_ids=(c7.PROJECTION_DIFF_CONTRACT_ID,),
        p1_locator_paths=(
            "main/backend/app/services/indexer",
            "main/backend/app/services/graph",
        ),
        p1_locator_status=(
            "FROZEN_LOCATORS_PRESENT; index and graph implementations are live "
            "but independent; no durable index-to-graph handoff, shared source "
            "binding or projection offset contract is observed"
        ),
        postgres_requirement="disposable_pg_projection_offset",
    ),
    CellFragmentConfig(
        cell_id="C7.4",
        contract_ids=(
            c7.READBACK_RECONCILIATION_CONTRACT_ID,
            c7.NONSTART_RECONCILIATION_CONTRACT_ID,
        ),
        p1_locator_paths=(
            "main/backend/app/services/ingest",
            "main/backend/app/services/indexer",
            "main/backend/app/services/graph",
        ),
        p1_locator_status=(
            "FROZEN_LOCATORS_PRESENT; retry classification, cleanup retry and "
            "local transaction rollback fragments exist, but no family-wide "
            "durable attempt, authoritative readback or crash-reconciliation "
            "path is observed"
        ),
        postgres_requirement="disposable_pg_recovery_readback",
    ),
)


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
    from app.successor_runtime.runtime.transitions import EffectDisposition

    policy = C7ReconciliationPolicy()
    unresolved = policy.terminal_decision(EffectDisposition.FAILED)
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


def build_observations(cell_id: str) -> tuple[dict[str, object], dict[str, object]]:
    """Return the declared (successor, legacy) observation pair for a cell."""

    builders = {
        "C7.1": _c7_1_observation,
        "C7.2": _c7_2_observation,
        "C7.3": _c7_3_observation,
        "C7.4": _c7_4_observation,
    }
    builder = builders.get(cell_id)
    if builder is None:
        raise ValueError(f"unknown C7 cell_id: {cell_id}")
    return builder()


def build_rollback_observation(
    cell_id: str,
    successor: dict[str, object],
    legacy: dict[str, object],
) -> dict[str, object]:
    """Declare each cell's rollback claim and compute its rollback digest."""

    del legacy
    if cell_id == "C7.1":
        return {
            "rollback_digest": content_digest(
                {
                    "claim_owner": "legacy",
                    "plan_digest_retained": successor["plan_digest"],
                    "no_new_attempt": True,
                }
            ),
            "claim_owner": "legacy",
            "plan_retained": True,
        }
    if cell_id == "C7.2":
        return {
            "rollback_digest": content_digest(
                {
                    "claim_owner": "legacy",
                    "document_write": False,
                    "admission_implied": False,
                }
            ),
            "claim_owner": "legacy",
            "document_write": False,
        }
    if cell_id == "C7.3":
        return {
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
        }
    if cell_id == "C7.4":
        return {
            "rollback_digest": content_digest(
                {
                    "claim_owner": "legacy",
                    "new_attempt_allowed": False,
                    "outcome_unknown": True,
                }
            ),
            "claim_owner": "legacy",
            "new_attempt_allowed": False,
        }
    raise ValueError(f"unknown C7 cell_id: {cell_id}")


CONFIG = FamilyFragmentConfig(
    family_id=FRAGMENT_FAMILY,
    phase=FRAGMENT_PHASE,
    schema=FRAGMENT_SCHEMA,
    fragment_id=FRAGMENT_ID,
    status=FRAGMENT_STATUS,
    lifecycle_state=FRAGMENT_LIFECYCLE_STATE,
    project_key=PROJECT_KEY,
    registry_revision=REGISTRY_REVISION,
    resolved_schema=RESOLVED_SCHEMA,
    scope_incarnation=SCOPE_INCARNATION,
    cell_spec_path=CELL_SPEC_PATH,
    runtime_kernel_abi_path=RUNTIME_KERNEL_ABI_PATH,
    fragment_output_rel=FRAGMENT_OUTPUT_REL,
    source_bindings=_SOURCE_BINDINGS,
    implementation_bindings=_IMPLEMENTATION_BINDINGS,
    test_bindings=_TEST_BINDINGS,
    authority={
        "canonical_write": False,
        "credential": False,
        "graph": False,
        "index": False,
        "provider": False,
    },
    open_findings=(
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
    ),
    cells=_CELLS,
    build_observations=build_observations,
    build_rollback_observation=build_rollback_observation,
)
