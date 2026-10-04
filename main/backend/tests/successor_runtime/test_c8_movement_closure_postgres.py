"""Disposable PostgreSQL evidence for the C8 production trust-root."""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_runtime.capabilities import knowledge_common as c8
from app.successor_runtime.capabilities.knowledge_consumer import (
    consume_graph_projection,
)
from app.successor_runtime.capabilities.knowledge_graph_projection import (
    project_graph_occurrences,
)
from app.successor_runtime.capabilities.knowledge_report import (
    confirm_report_admission_readback,
)
from app.successor_runtime.capabilities.knowledge_test_interpreter import (
    TestOnlyLossProfileRegistry,
    TestOnlyLossWitness,
    TestOnlyMaterialIssuanceRegistry,
    TestOnlyMaterialWitness,
    TestOnlyVerificationWitness,
    TestOnlyVerifierRegistry,
)
from app.successor_runtime.capabilities.typed_knowledge import (
    StrictReadHandleRegistry,
    UnavailableProjection,
    strict_issued_demand_read,
)
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest
from app.successor_runtime.capabilities.material_ingest_common import (
    MATERIAL_INGEST_OWNER,
    DOCUMENT_CANONICAL_OWNER,
)
from app.successor_runtime.capabilities.material_ingest_movements import (
    DeterministicChunkPort,
    DeterministicExtractPort,
    DeterministicPassThroughPort,
    DeterministicSummarizePort,
    StructuredMaterialCandidate,
    VerifiedMaterialCandidate,
    capture_raw_snapshot_exact,
    execute_material_movement,
    normalize_ingest_envelope,
    select_exactly_one_digestion_alternative,
    verify_structured_candidate,
)
from app.successor_runtime.runtime.assignments import canonical_digest
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.c8_artifact_handler import (
    C8ArtifactIntegrityError,
    C8ArtifactOutcomeUnknownError,
    read_staged_artifact,
    stage_artifact,
    staged_artifact_value_id,
)
from app.successor_runtime.substrate.postgres.c8_graph_projector import (
    C8_GRAPH_VALUE_CODEC_ID,
    C8_GRAPH_VALUE_OBJECT_TYPE,
    KNOWLEDGE_GRAPH_VALUE_SCHEMA,
    C8GraphOffsetCasError,
    C8GraphProjectionUnavailableError,
    LEGACY_C8_GRAPH_PROJECTOR_ID,
    LEGACY_C8_GRAPH_SOURCE_KIND,
    LEGACY_C8_GRAPH_VALUE_CODEC_ID,
    LEGACY_C8_GRAPH_VALUE_OBJECT_TYPE,
    LEGACY_C8_GRAPH_VALUE_SCHEMA,
    graph_value_id,
    read_active_graph,
)
from app.successor_runtime.substrate.postgres.c8_material_handler import (
    C8_KNOWLEDGE_VALUE_CODEC_ID,
    C8_KNOWLEDGE_VALUE_OBJECT_TYPE,
    C8_KNOWLEDGE_VALUE_SCHEMA,
    C8MaterialIntegrityError,
    C8MaterialMissingError,
    C8StoredKnowledgeValue,
    LEGACY_C8_KNOWLEDGE_VALUE_CODEC_ID,
    LEGACY_C8_KNOWLEDGE_VALUE_OBJECT_TYPE,
    LEGACY_C8_KNOWLEDGE_VALUE_SCHEMA,
    read_staged_knowledge_value,
)
from app.successor_runtime.substrate.postgres.c8_production import (
    LEGACY_PRODUCTION_AUTHORITY_DIGEST,
    LEGACY_PRODUCTION_AUTHORITY_ID,
    PRODUCTION_AUTHORITY_ID,
    C8DeliveryUnavailableError,
    C8ProductionRoot,
    C8ProductionTrustRootError,
    ProductionGraphReadHandle,
    ProductionKnowledgeHandle,
    ProductionMaterialHandle,
    ProductionVerifierHandle,
)
from app.successor_runtime.substrate.postgres.commit_intents import (
    CommitIntentRepository,
    CommitIntentStatus,
)
from app.successor_runtime.substrate.postgres.ingest_c7_candidate_values import (
    candidate_value_id,
    candidate_value_incarnation,
    candidate_value_ref,
    store_candidate_value,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
    candidate_evidence_digest,
    candidate_provenance_digest,
    candidate_receipt_digest,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    StaleRevisionError,
)
from app.successor_runtime.substrate.postgres.runtime_values import (
    RuntimeValueBinding,
    RuntimeValueRepository,
)
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
    ProjectionOffsetRepository,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest
from app.successor_runtime.substrate.postgres.values import (
    ValueRepository,
    derive_value_write_intent_digest,
)

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_c8_movement_closure_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "p4-c8-postgres"
RESOLVED_SCHEMA = "mrw_p4_c8_postgres"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "scope-inc-c8-pg"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    RESOLVED_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
CANDIDATE_ID = "ingest-candidate-p4c8-001"
ACTOR_ID = "actor:p4-c8"
AUTHORITY_DIGEST = content_digest({"authority": "c8-pg-fixture"})
AUTHORITY_EPOCH = 7
RUN_ID = "run:c8-pg"
STEP_ID = "step:c8-pg"
ATTEMPT_ID = "attempt:c8-pg"
EXECUTION_EPOCH = 1
PROGRAM_ID = "program:c8-pg"
PLAN_ID = "plan:c8-pg"
PROGRAM_DIGEST = content_digest({"program": "c8-pg"})
PLAN_DIGEST = content_digest({"plan": "c8-pg"})
NOW = datetime(2030, 8, 31, 8, 0, tzinfo=UTC)
FORMATION_PROFILE = c8.FormationProfile(
    profile_id="mrw.c8.formation.structured-material.v1",
    profile_version="1",
)
PROJECT_TABLES = project_tables(sa.MetaData(), RESOLVED_SCHEMA)


def _server_url() -> str:
    env_url = os.environ.get(ENV_URL)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


def _assert_database_absent(server: Engine) -> None:
    with server.connect() as connection:
        row = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
            {"database_name": DATABASE_NAME},
        ).scalar_one_or_none()
        assert row is None


def _assert_database_present(server: Engine) -> None:
    with server.connect() as connection:
        row = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
            {"database_name": DATABASE_NAME},
        ).scalar_one_or_none()
        assert row == 1


def _create_database() -> Engine:
    server = sa.create_engine(
        _server_url(), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
            connection.execute(text("CREATE DATABASE " + DATABASE_NAME))
        _assert_database_present(server)
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        server.dispose()
        pytest.skip(f"cannot create disposable database {DATABASE_NAME}: {exc}")
    return server


def _drop_database(server: Engine) -> None:
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
        _assert_database_absent(server)
    finally:
        server.dispose()


@pytest.fixture(scope="module")
def disposable_database() -> Iterator[Engine]:
    server = _create_database()
    engine = sa.create_engine(
        make_url(_server_url())
        .set(database=DATABASE_NAME)
        .render_as_string(hide_password=False),
        poolclass=NullPool,
    )
    project_metadata = sa.MetaData()
    project_tables(project_metadata, RESOLVED_SCHEMA)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{RESOLVED_SCHEMA}"'))
        PUBLIC_METADATA.create_all(connection, checkfirst=False)
        project_metadata.create_all(connection, checkfirst=False)
        C7_MOVEMENT_CANONICAL_DOCUMENTS.create(connection)
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            PUBLIC_METADATA.drop_all(connection, checkfirst=True)
            connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{RESOLVED_SCHEMA}" CASCADE')
            )
        engine.dispose()
        _drop_database(server)


def _scope(*, project_key: str = PROJECT_KEY) -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=project_key,
            resolved_schema=RESOLVED_SCHEMA,
            project_registry_revision=REGISTRY_REVISION,
            incarnation=SCOPE_INCARNATION,
            scope_digest=SCOPE_DIGEST,
        ),
        actor_id=ACTOR_ID,
    )


def _seed_runtime_rows(connection: sa.Connection) -> None:
    connection.execute(
        PUBLIC_TABLES["project_scope_registry"]
        .insert()
        .values(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=RESOLVED_SCHEMA,
            scope_digest=SCOPE_DIGEST,
            incarnation=SCOPE_INCARNATION,
            state="ACTIVE",
            updated_by="c8-pg-fixture",
            approval_ref="approval:c8-pg",
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_program_refs"]
        .insert()
        .values(
            program_id=PROGRAM_ID,
            project_key=PROJECT_KEY,
            program_digest=PROGRAM_DIGEST,
            project_storage_ref="project-value:program:c8-pg",
            contract_version="mrw.functorial-successor.program-spec.v1",
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_plan_refs"]
        .insert()
        .values(
            plan_id=PLAN_ID,
            project_key=PROJECT_KEY,
            plan_digest=PLAN_DIGEST,
            program_id=PROGRAM_ID,
            program_digest=PROGRAM_DIGEST,
            project_storage_ref="project-value:plan:c8-pg",
            compiler_id="compiler:c8-pg",
            compiler_version="1",
            operation_catalog_id="mrw.knowledge.operations",
            catalog_version="2.0.0",
            catalog_digest=AUTHORITY_DIGEST,
            effect_closure_digest=AUTHORITY_DIGEST,
            authority_closure_digest=AUTHORITY_DIGEST,
            resource_closure_digest=AUTHORITY_DIGEST,
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_runs"]
        .insert()
        .values(
            run_id=RUN_ID,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            resolved_schema=RESOLVED_SCHEMA,
            program_id=PROGRAM_ID,
            program_digest=PROGRAM_DIGEST,
            plan_id=PLAN_ID,
            plan_digest=PLAN_DIGEST,
            state="READY",
            revision=0,
            next_event_seq=1,
            execution_epoch=EXECUTION_EPOCH,
            incarnation="run-inc:c8-pg",
            submission_authority_digest=AUTHORITY_DIGEST,
            qualification_digest=AUTHORITY_DIGEST,
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_steps"]
        .insert()
        .values(
            project_key=PROJECT_KEY,
            run_id=RUN_ID,
            step_id=STEP_ID,
            operation_id="knowledge.report.stage",
            operation_kind="knowledge.report.stage.v2",
            operation_version="1.0.0",
            state="RUNNING",
            revision=0,
            execution_epoch=EXECUTION_EPOCH,
            input_digest=AUTHORITY_DIGEST,
            output_digest=AUTHORITY_DIGEST,
            effect_class="EFFECTFUL",
            resource_class="CPU_LIGHT",
            capability_id="knowledge.report.v2",
            claim_owner="successor",
            claim_authority_epoch=AUTHORITY_EPOCH,
            claim_policy_digest=AUTHORITY_DIGEST,
        )
    )


def _base_pair() -> tuple[StructuredMaterialCandidate, VerifiedMaterialCandidate]:
    snapshot = capture_raw_snapshot_exact(
        project_key=PROJECT_KEY,
        source_locator="https://example.invalid/report",
        raw_bytes=b'{"title": " Q2 Market ", "text": " Market grew 12%  in Q2. "}',
        incarnation="raw-inc-c8-pg",
        mime_type="application/json",
        provenance_refs=("ingest.c8.pg.v1",),
    )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    trace = execute_material_movement(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
        extract=DeterministicExtractPort(),
        chunk=DeterministicChunkPort(),
        summarize=DeterministicSummarizePort(),
        pass_through=DeterministicPassThroughPort(),
    )
    assert isinstance(trace.outcome, StructuredMaterialCandidate)
    verified = verify_structured_candidate(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
        candidate=trace.outcome,
        expected_candidate_digest=trace.outcome.candidate_digest,
        expected_project_key=PROJECT_KEY,
        actor=ACTOR_ID,
        authority_digest=AUTHORITY_DIGEST,
        authority_epoch=AUTHORITY_EPOCH,
        canonical_base_revision=0,
        canonical_base_incarnation=SCOPE_INCARNATION,
        canonical_object_id=CANDIDATE_ID,
    )
    assert isinstance(verified, VerifiedMaterialCandidate)
    return trace.outcome, verified


def _seed_c7_material(connection: sa.Connection) -> None:
    structured, verified = _base_pair()
    store_candidate_value(
        connection,
        scope=_scope(),
        structured=structured,
        verified=verified,
    )
    values: dict[str, object] = {
        "project_key": PROJECT_KEY,
        "object_id": verified.canonical_object_id,
        "commit_intent_id": "commit:c8-pg:c7-seed",
        "canonical_owner": DOCUMENT_CANONICAL_OWNER,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "attempt_id": ATTEMPT_ID,
        "capability_id": MATERIAL_INGEST_OWNER,
        "actor_id": verified.actor,
        "program_digest": PROGRAM_DIGEST,
        "plan_digest": PLAN_DIGEST,
        "step_revision": 0,
        "attempt_revision": 0,
        "execution_epoch": EXECUTION_EPOCH,
        "attempt_incarnation": "attempt-inc:c8-pg",
        "assignment_digest": AUTHORITY_DIGEST,
        "handler_binding_digest": AUTHORITY_DIGEST,
        "handler_realization_digest": AUTHORITY_DIGEST,
        "input_closure_digest": verified.snapshot_identity_digest,
        "revision": 1,
        "incarnation": SCOPE_INCARNATION,
        "expected_base_revision": 0,
        "expected_base_incarnation": SCOPE_INCARNATION,
        "content_digest": verified.payload_content_digest,
        "snapshot_identity_digest": verified.snapshot_identity_digest,
        "raw_content_digest": verified.raw_content_digest,
        "envelope_digest": verified.envelope_digest,
        "payload_content_digest": verified.payload_content_digest,
        "ordered_source_closure_digest": verified.ordered_source_closure_digest,
        "provenance_closure_digest": verified.provenance_closure_digest,
        "decision_digest": verified.decision_digest,
        "candidate_digest": verified.candidate_digest,
        "candidate_verification_digest": verified.verification_digest,
        "ordered_event_closure_digest": AUTHORITY_DIGEST,
        "verification_digest": AUTHORITY_DIGEST,
        "authority_digest": verified.authority_digest,
        "authority_epoch": verified.authority_epoch,
        "candidate_id": verified.candidate_id,
        "snapshot_ref": verified.snapshot_ref,
        "alternative": verified.alternative,
        "verification_profile_ref": verified.verification_profile_ref,
        "verification_receipt": verified.verification_receipt,
        "evidence_digest": candidate_evidence_digest(verified),
        "provenance_digest": candidate_provenance_digest(verified),
        "candidate_receipt_digest": candidate_receipt_digest(verified),
        "value_ref": candidate_value_ref(candidate_value_id(verified.candidate_id)),
        "value_revision": 1,
        "value_incarnation": candidate_value_incarnation(verified),
        "value_digest": verified.payload_content_digest,
        "value_provenance_digest": verified.provenance_closure_digest,
        "canonical_commit_ref": "canonical:document:c8-pg:seed",
        "receipt_digest": content_digest({"receipt": "c8-pg-seed"}),
    }
    values["head_closure_digest"] = canonical_digest(
        {key: value for key, value in values.items() if key != "head_closure_digest"}
    )
    connection.execute(C7_MOVEMENT_CANONICAL_DOCUMENTS.insert().values(**values))


def _reset(engine: Engine) -> None:
    names = tuple(PUBLIC_TABLES) + ("c7_movement_canonical_documents",)
    qualified = ", ".join(
        [f'"public"."{name}"' for name in names]
        + [f'"{RESOLVED_SCHEMA}"."{name}"' for name in PROJECT_TABLES.as_dict()]
    )
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE"))
        _seed_runtime_rows(connection)


@pytest.fixture(autouse=True)
def clean_database(disposable_database: Engine) -> Iterator[None]:
    _reset(disposable_database)
    yield


def _seed_material(engine: Engine) -> None:
    with engine.begin() as connection:
        _seed_c7_material(connection)


def _count_rows(connection: sa.Connection, table: sa.Table) -> int:
    return int(
        connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
    )


def _value_table() -> sa.Table:
    return PROJECT_TABLES.successor_values


def _occurrence(
    occurrence_id: str,
    *,
    source: str = "source:1",
    target: str = "target:1",
    position: int = 1,
    edge_type: str = "references",
) -> c8.GraphOccurrence:
    occurrence = c8.GraphOccurrence(
        occurrence_id=occurrence_id,
        edge_type=edge_type,
        source_identity=source,
        target_identity=target,
        position=position,
    )
    return dataclasses.replace(
        occurrence,
        occurrence_digest=c8.graph_occurrence_digest(occurrence),
    )


def _graph_source() -> dict[str, str]:
    return {
        "source_ref": "c7-snapshot:c8-pg",
        "source_incarnation": SCOPE_INCARNATION,
        "source_digest": "0" * 64,
    }


def _root(connection: sa.Connection) -> C8ProductionRoot:
    return C8ProductionRoot(connection, _scope())


def _material_handle(
    root: C8ProductionRoot,
) -> ProductionMaterialHandle:
    return root.read_material(candidate_id=_base_pair()[1].candidate_id)


def _knowledge_handle(
    root: C8ProductionRoot,
    material_handle: ProductionMaterialHandle | None = None,
    *,
    candidate_id: str = "knowledge-candidate:c8-pg:001",
) -> ProductionKnowledgeHandle:
    material_handle = material_handle or _material_handle(root)
    return root.stage_knowledge(
        material_handle,
        formation_profile=FORMATION_PROFILE,
        candidate_id=candidate_id,
        canonical_statement="Market grew 12% in Q2",
        primary_type_node_key="Topic",
        evidence_refs=("ev:c8-pg:1",),
        fields=("canonical_statement", "evidence_refs"),
    )


def _writing_spec(
    *,
    base_incarnation: str = SCOPE_INCARNATION,
) -> c8.WritingCompositionSpec:
    return c8.WritingCompositionSpec(
        project_key=PROJECT_KEY,
        base_revision=1,
        base_incarnation=base_incarnation,
        byte_ceiling=4096,
        citation_ceiling=1,
    )


def test_public_api_rejects_trust_injection(disposable_database: Engine) -> None:
    with disposable_database.connect() as connection:
        root = _root(connection)
        with pytest.raises(TypeError):
            C8ProductionRoot(connection, _scope(), authority_token=object())  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            C8ProductionRoot(connection, _scope(), registry=object())  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            C8ProductionRoot(connection, _scope(), loss_profile=object())  # type: ignore[call-arg]
        assert root.authority_id == PRODUCTION_AUTHORITY_ID
        assert root.authority_digest


def test_public_imports_expose_no_registry_or_witness_constructors(
    disposable_database: Engine,
) -> None:
    import app.successor_runtime.substrate.postgres.c8_production as production

    exported = set(production.__all__)
    assert "ProductionMaterialWitness" not in exported
    assert "ProductionVerifierWitness" not in exported
    assert "ProductionLossWitness" not in exported
    assert "TestOnlyAuthority" not in exported
    assert "C8_PRODUCTION_AUTHORITY" not in exported


def test_material_read_issues_opaque_witness_and_zero_writes(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.connect() as connection:
        root = _root(connection)
        before = _count_rows(connection, _value_table())
        handle = _material_handle(root)
        assert isinstance(handle, ProductionMaterialHandle)
        assert handle.material.candidate_id == _base_pair()[1].candidate_id
        assert handle.material.value_revision == 1
        assert handle.material.attestation_digest
        after = _count_rows(connection, _value_table())
        assert before == after
        duplicate = _material_handle(root)
        assert duplicate.material == handle.material
        assert duplicate.witness.material_identity == handle.witness.material_identity


def test_nested_payload_mutation_and_noncanonical_values_fail_closed(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.begin() as connection:
        connection.execute(
            _value_table()
            .update()
            .where(
                _value_table().c.project_key == PROJECT_KEY,
                _value_table().c.value_id
                == candidate_value_id(_base_pair()[1].candidate_id),
            )
            .values(content_json={"title": "mutated"})
        )
        with pytest.raises(C8MaterialIntegrityError, match="digest readback"):
            _root(connection).read_material(candidate_id=_base_pair()[1].candidate_id)
    with pytest.raises(TypeError, match="finite"):
        c8.knowledge_canonical_digest({"title": " Q2 Market ", "bad_key": float("nan")})
    with pytest.raises(TypeError, match="string mapping keys"):
        c8.knowledge_canonical_digest({1: "bad-key"})
    with pytest.raises(TypeError, match="unsupported"):
        c8.knowledge_canonical_digest({"bad": object()})


def test_head_value_snapshot_revision_incarnation_provenance_drift_fails_closed(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    cases: tuple[tuple[str, dict[str, object]], ...] = (
        ("content_digest", {"value_digest": "0" * 64}),
        ("revision", {"value_revision": 2}),
        ("incarnation", {"value_incarnation": "c7:structured:other"}),
        ("source_ref", {"snapshot_ref": "snapshot:drifted"}),
        (
            "provenance_digest",
            {"value_provenance_digest": "1" * 64},
        ),
    )
    for label, update in cases:
        _reset(disposable_database)
        with disposable_database.begin() as connection:
            _seed_c7_material(connection)
            head = (
                connection.execute(
                    sa.select(C7_MOVEMENT_CANONICAL_DOCUMENTS).where(
                        C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == PROJECT_KEY,
                        C7_MOVEMENT_CANONICAL_DOCUMENTS.c.candidate_id
                        == _base_pair()[1].candidate_id,
                    )
                )
                .mappings()
                .one()
            )
            fresh = dict(head)
            fresh.update(update)
            fresh["head_closure_digest"] = canonical_digest(
                {
                    key: value
                    for key, value in fresh.items()
                    if key != "head_closure_digest"
                }
            )
            connection.execute(
                C7_MOVEMENT_CANONICAL_DOCUMENTS.update()
                .where(
                    C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == PROJECT_KEY,
                    C7_MOVEMENT_CANONICAL_DOCUMENTS.c.candidate_id
                    == _base_pair()[1].candidate_id,
                )
                .values(**fresh)
            )
            with pytest.raises(C8MaterialIntegrityError, match=label):
                _root(connection).read_material(
                    candidate_id=_base_pair()[1].candidate_id
                )


def test_missing_head_and_value_fail_closed(disposable_database: Engine) -> None:
    _seed_material(disposable_database)
    with disposable_database.begin() as connection:
        connection.execute(
            C7_MOVEMENT_CANONICAL_DOCUMENTS.delete().where(
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == PROJECT_KEY
            )
        )
        with pytest.raises(C8MaterialMissingError):
            _root(connection).read_material(candidate_id=_base_pair()[1].candidate_id)
    with disposable_database.begin() as connection:
        _reset(disposable_database)
        _seed_c7_material(connection)
        connection.execute(
            _value_table().delete().where(_value_table().c.project_key == PROJECT_KEY)
        )
        with pytest.raises(C8MaterialMissingError):
            _root(connection).read_material(candidate_id=_base_pair()[1].candidate_id)


def test_caller_minted_handles_and_copied_witnesses_rejected(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.connect() as connection:
        root = _root(connection)
        handle = _material_handle(root)
        forged = ProductionMaterialHandle(
            material=handle.material,
            witness=handle.witness,
            locator=handle.locator,
            root_id=object(),
            _secret=object(),
        )
        with pytest.raises(C8ProductionTrustRootError, match="not issued"):
            root.stage_knowledge(
                forged,
                formation_profile=FORMATION_PROFILE,
                candidate_id="knowledge-candidate:forged",
                canonical_statement="forged",
                primary_type_node_key="Topic",
                evidence_refs=("ev:1",),
                fields=("canonical_statement",),
            )
        other = _root(connection)
        with pytest.raises(C8ProductionTrustRootError, match="not issued"):
            other.stage_knowledge(
                handle,
                formation_profile=FORMATION_PROFILE,
                candidate_id="knowledge-candidate:cross",
                canonical_statement="cross-root",
                primary_type_node_key="Topic",
                evidence_refs=("ev:1",),
                fields=("canonical_statement",),
            )
        test_witness = TestOnlyMaterialWitness(
            material_identity=handle.material.material_identity,
            attestation_digest=handle.material.attestation_digest,
            _secret=object(),
        )
        with pytest.raises(UnavailableProjection, match="TEST_ONLY"):
            strict_issued_demand_read(
                handle.material,
                test_witness,
                c8.form_typed_knowledge_candidate(
                    handle.material,
                    formation_profile=FORMATION_PROFILE,
                    candidate_id="knowledge-candidate:test",
                    canonical_statement="test",
                    primary_type_node_key="Topic",
                    evidence_refs=("ev:1",),
                ),
                StrictReadHandleRegistry(TestOnlyMaterialIssuanceRegistry()),
                fields=("canonical_statement",),
            )


def test_test_only_registries_rejected_by_production_paths(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.connect() as connection:
        root = _root(connection)
        material = root.read_material(
            candidate_id=_base_pair()[1].candidate_id
        ).material
        test_issuance = TestOnlyMaterialIssuanceRegistry()
        capability = test_issuance.authorize()
        test_witness = test_issuance.register(material, capability)
        with pytest.raises(UnavailableProjection, match="TEST_ONLY"):
            strict_issued_demand_read(
                material,
                test_witness,
                c8.form_typed_knowledge_candidate(
                    material,
                    formation_profile=FORMATION_PROFILE,
                    candidate_id="knowledge-candidate:test",
                    canonical_statement="test",
                    primary_type_node_key="Topic",
                    evidence_refs=("ev:1",),
                ),
                StrictReadHandleRegistry(test_issuance),
                fields=("canonical_statement",),
            )
        test_verifier = TestOnlyVerifierRegistry()
        test_verification = c8.ReportVerification(
            verification_id="verification:test",
            stage_id="stage:test",
            project_key=PROJECT_KEY,
            artifact_digest="0" * 64,
            citation_closure_digest="0" * 64,
            state="VERIFIED",
        )
        test_verifier_witness = TestOnlyVerificationWitness(
            verification_id=test_verification.verification_id,
            object_digest=test_verification.object_digest,
            _secret=test_verifier._authority._secret,
        )
        test_verifier._entries[test_verification.verification_id] = test_verification
        with pytest.raises(UnavailableProjection, match="TEST_ONLY"):
            confirm_report_admission_readback(
                c8.ReportAdmissionIntent(
                    intent_id="admission:test",
                    verification_id=test_verification.verification_id,
                    project_key=PROJECT_KEY,
                    artifact_digest="0" * 64,
                    state="PENDING",
                ),
                witness=test_verifier_witness,
                verifier_registry=test_verifier,
                verification=test_verification,
            )
        test_loss = TestOnlyLossProfileRegistry()
        profile = c8.GraphLossProfile(profile_id="mrw.c8.graph-loss.v1")
        test_loss_witness = TestOnlyLossWitness(
            profile_id=profile.profile_id,
            profile_digest=profile.profile_digest,
            _secret=test_loss._authority._secret,
        )
        test_loss._entries[profile.profile_id] = profile
        with pytest.raises(c8.KnowledgeProjectionError, match="TEST_ONLY"):
            project_graph_occurrences(
                generation_id="gen:test",
                project_key=PROJECT_KEY,
                occurrences=(_occurrence("o:1"),),
                loss_profile=profile,
                loss_profile_registry=test_loss,
                loss_witness=test_loss_witness,
                provenance_digest="0" * 64,
            )
        active_handle = TestOnlyLossWitness(
            profile_id="profile:test",
            profile_digest="0" * 64,
            _secret=object(),
        )
        generation = c8.GraphProjectionGeneration(
            generation_id="gen:1",
            project_key=PROJECT_KEY,
            occurrences=(_occurrence("o:1"),),
            declared_loss=(),
            provenance_digest="0" * 64,
            offset="0",
            authority_kind=PRODUCTION_AUTHORITY_ID,
            authority_digest=root.authority_digest,
            loss_profile_registry_id=(
                "knowledge.graph-loss-profile.knowledge.production.v2"
            ),
            loss_profile_registry_digest="0" * 64,
        )
        with pytest.raises(c8.KnowledgeProjectionError, match="TEST_ONLY"):
            consume_graph_projection(
                consumer_id="consumer:test",
                projection=generation,
                project_key=PROJECT_KEY,
                active_read_handle=active_handle,
            )


def test_knowledge_stage_exact_read_and_handle(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.begin() as connection:
        root = _root(connection)
        handle = _knowledge_handle(root)
        assert isinstance(handle, ProductionKnowledgeHandle)
        assert handle.stored_value.revision == 1
        assert handle.issued_read.handle.authority_kind == PRODUCTION_AUTHORITY_ID
        assert handle.issued_read.witness_marker is not None
        row = (
            connection.execute(
                sa.select(_value_table()).where(
                    _value_table().c.project_key == PROJECT_KEY,
                    _value_table().c.value_id == handle.stored_value.value_id,
                )
            )
            .mappings()
            .one()
        )
        assert row["content_digest"] == handle.issued_read.candidate.candidate_digest
        assert handle.stored_value.value_id.startswith("knowledge:staged-candidate:")
        assert row["object_type"] == C8_KNOWLEDGE_VALUE_OBJECT_TYPE
        assert row["codec_id"] == C8_KNOWLEDGE_VALUE_CODEC_ID
        assert row["provenance_json"]["schema"] == C8_KNOWLEDGE_VALUE_SCHEMA


def test_legacy_staged_knowledge_value_is_exact_read_only(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.begin() as connection:
        material = _material_handle(_root(connection)).material
        candidate = c8.form_typed_knowledge_candidate(
            material,
            formation_profile=FORMATION_PROFILE,
            candidate_id="knowledge-candidate:legacy",
            canonical_statement="Historical staged knowledge",
            primary_type_node_key="Topic",
            evidence_refs=("ev:legacy:1",),
        )
        body = {
            name: value
            for name, value in dataclasses.asdict(candidate).items()
            if name != "candidate_digest"
        }
        exact = canonical_json(body).encode("utf-8")
        legacy_value_id = f"c8:knowledge:{candidate.candidate_id}"
        legacy_incarnation = f"c8:knowledge:{candidate.candidate_digest}"
        provenance = {
            "schema": LEGACY_C8_KNOWLEDGE_VALUE_SCHEMA,
            "material_identity": material.material_identity,
            "candidate_id": candidate.candidate_id,
            "snapshot_ref": material.snapshot_ref,
            "material_value_digest": material.value_digest,
            "material_provenance_digest": material.provenance_digest,
        }
        provenance_digest = content_digest(provenance)
        ValueRepository(connection, PROJECT_TABLES).put_exact(
            _scope(),
            value_id=legacy_value_id,
            object_type=LEGACY_C8_KNOWLEDGE_VALUE_OBJECT_TYPE,
            codec_id=LEGACY_C8_KNOWLEDGE_VALUE_CODEC_ID,
            content=exact,
            expected_digest=candidate.candidate_digest,
            provenance_digest=provenance_digest,
            expected_revision=0,
            expected_incarnation=legacy_incarnation,
            source_ref=material.snapshot_ref,
            provenance=provenance,
        )
        expected = C8StoredKnowledgeValue(
            value_id=legacy_value_id,
            value_ref=f"project-value:{legacy_value_id}",
            revision=1,
            incarnation=legacy_incarnation,
            content_digest=candidate.candidate_digest,
            provenance_digest=provenance_digest,
            source_ref=material.snapshot_ref,
        )
        assert read_staged_knowledge_value(
            connection,
            scope=_scope(),
            material=material,
            candidate=candidate,
            expected_value=expected,
        ) == exact
        current_rows = connection.execute(
            sa.select(sa.func.count())
            .select_from(_value_table())
            .where(
                _value_table().c.value_id
                == f"knowledge:staged-candidate:{candidate.candidate_id}"
            )
        ).scalar_one()
        assert int(current_rows) == 0


def test_writing_resolves_handles_and_rejects_citation_mismatch(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.begin() as connection:
        root = _root(connection)
        knowledge = _knowledge_handle(root)
        writing = root.compose_and_stage_writing(
            artifact_id="draft:c8-pg:001",
            knowledge_handles=(knowledge,),
            citation_ids=("ev:c8-pg:1",),
            spec=_writing_spec(
                base_incarnation=knowledge.issued_read.handle.incarnation
            ),
            run_id=RUN_ID,
            step_id=STEP_ID,
            qualifier_ref="qualifier:c8-pg:draft",
        )
        assert writing.artifact.artifact_digest
        assert writing.artifact.citation_closure.refs[0].citation_id == "ev:c8-pg:1"
        staged_count = _count_rows(
            connection,
            PUBLIC_TABLES["runtime_staged_artifacts"],
        )
        value_count = _count_rows(connection, _value_table())
        replay = root.compose_and_stage_writing(
            artifact_id="draft:c8-pg:001",
            knowledge_handles=(knowledge,),
            citation_ids=("ev:c8-pg:1",),
            spec=_writing_spec(
                base_incarnation=knowledge.issued_read.handle.incarnation
            ),
            run_id=RUN_ID,
            step_id=STEP_ID,
            qualifier_ref="qualifier:c8-pg:draft",
        )
        assert replay == writing
        assert _count_rows(
            connection,
            PUBLIC_TABLES["runtime_staged_artifacts"],
        ) == staged_count
        assert _count_rows(connection, _value_table()) == value_count
        forged = ProductionKnowledgeHandle(
            issued_read=knowledge.issued_read,
            stored_value=knowledge.stored_value,
            material_locator=knowledge.material_locator,
            root_id=object(),
            _secret=object(),
        )
        with pytest.raises(C8ProductionTrustRootError, match="not issued"):
            root.compose_and_stage_writing(
                artifact_id="draft:forged",
                knowledge_handles=(forged,),
                citation_ids=("ev:c8-pg:1",),
                spec=_writing_spec(
                    base_incarnation=knowledge.issued_read.handle.incarnation
                ),
                run_id=RUN_ID,
                step_id=STEP_ID,
                qualifier_ref="qualifier:forged",
            )
        with pytest.raises(C8ProductionTrustRootError, match="citation id"):
            root.compose_and_stage_writing(
                artifact_id="draft:missing",
                knowledge_handles=(knowledge,),
                citation_ids=("ev:missing",),
                spec=_writing_spec(
                    base_incarnation=knowledge.issued_read.handle.incarnation
                ),
                run_id=RUN_ID,
                step_id=STEP_ID,
                qualifier_ref="qualifier:missing",
            )
        with pytest.raises(C8ProductionTrustRootError, match="distinct"):
            root.compose_and_stage_writing(
                artifact_id="draft:dup",
                knowledge_handles=(knowledge, knowledge),
                citation_ids=("ev:c8-pg:1",),
                spec=_writing_spec(
                    base_incarnation=knowledge.issued_read.handle.incarnation
                ),
                run_id=RUN_ID,
                step_id=STEP_ID,
                qualifier_ref="qualifier:dup",
            )


def test_legacy_staged_report_replays_without_current_duplicate(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.begin() as connection:
        root = _root(connection)
        knowledge = _knowledge_handle(root)
        writing = root.compose_and_stage_writing(
            artifact_id="draft:c8-pg:legacy-stage",
            knowledge_handles=(knowledge,),
            citation_ids=("ev:c8-pg:1",),
            spec=_writing_spec(
                base_incarnation=knowledge.issued_read.handle.incarnation
            ),
            run_id=RUN_ID,
            step_id=STEP_ID,
            qualifier_ref="qualifier:legacy-stage",
        )
        artifact = writing.artifact
        current_value_id = staged_artifact_value_id(artifact.artifact_id)
        legacy_value_id = f"c8:staged-artifact:{artifact.artifact_id}"
        legacy_object_type = "ResearchDraftArtifactDraft.v1"
        legacy_codec_id = "mrw.successor.c8.draft-markdown.canonical-utf8.v1"
        legacy_incarnation = f"c8:staged-artifact:{artifact.artifact_digest}"
        legacy_source_ref = f"c8:artifact:{artifact.artifact_id}"
        row = (
            connection.execute(
                sa.select(_value_table()).where(
                    _value_table().c.value_id == current_value_id
                )
            )
            .mappings()
            .one()
        )
        legacy_provenance = dict(row["provenance_json"])
        legacy_provenance["schema"] = "mrw.successor.c8.artifact-lifecycle.v1"
        legacy_provenance_digest = content_digest(legacy_provenance)
        legacy_write_intent = derive_value_write_intent_digest(
            project_key=PROJECT_KEY,
            value_id=legacy_value_id,
            object_type=legacy_object_type,
            codec_id=legacy_codec_id,
            content_digest=str(row["content_digest"]),
            provenance_digest=legacy_provenance_digest,
            source_ref=legacy_source_ref,
            expected_revision=0,
            expected_incarnation=legacy_incarnation,
            state="AVAILABLE",
        )
        connection.execute(
            _value_table()
            .update()
            .where(_value_table().c.value_id == current_value_id)
            .values(
                value_id=legacy_value_id,
                object_type=legacy_object_type,
                codec_id=legacy_codec_id,
                source_ref=legacy_source_ref,
                incarnation=legacy_incarnation,
                provenance_json=legacy_provenance,
                provenance_digest=legacy_provenance_digest,
                write_intent_digest=legacy_write_intent,
            )
        )
        legacy_project_ref = f"project-value:{legacy_value_id}"
        legacy_storage_digest = content_digest(
            {
                "contract": "ProjectRuntimeValueBinding.v1",
                "project_key": PROJECT_KEY,
                "runtime_value_id": legacy_value_id,
                "project_value_ref": legacy_project_ref,
                "content_digest": str(row["content_digest"]),
                "codec_id": legacy_codec_id,
            }
        )
        RuntimeValueRepository(connection, _scope()).put_exact(
            RuntimeValueBinding(
                value_id=legacy_value_id,
                object_type=legacy_object_type,
                codec_id=legacy_codec_id,
                content_digest=str(row["content_digest"]),
                byte_size=int(row["byte_size"]),
                project_value_ref=legacy_project_ref,
                storage_digest=legacy_storage_digest,
                write_intent_digest=legacy_write_intent,
            )
        )
        connection.execute(
            PUBLIC_TABLES["runtime_staged_artifacts"]
            .update()
            .where(
                PUBLIC_TABLES["runtime_staged_artifacts"].c.project_key
                == PROJECT_KEY,
                PUBLIC_TABLES["runtime_staged_artifacts"].c.artifact_id
                == artifact.artifact_id,
            )
            .values(value_id=legacy_value_id)
        )
        connection.execute(
            PUBLIC_TABLES["runtime_values"].delete().where(
                PUBLIC_TABLES["runtime_values"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_values"].c.value_id == current_value_id,
            )
        )
        assert read_staged_artifact(
            connection,
            scope=_scope(),
            artifact_id=artifact.artifact_id,
        ) == artifact
        replay = stage_artifact(
            connection,
            scope=_scope(),
            artifact=artifact,
            run_id=RUN_ID,
            step_id=STEP_ID,
            qualifier_ref="qualifier:legacy-stage",
        )
        assert replay.value_id == legacy_value_id
        current_rows = connection.execute(
            sa.select(sa.func.count())
            .select_from(_value_table())
            .where(_value_table().c.value_id == current_value_id)
        ).scalar_one()
        assert int(current_rows) == 0
        runtime_rows = connection.execute(
            sa.select(PUBLIC_TABLES["runtime_values"]).where(
                PUBLIC_TABLES["runtime_values"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_values"].c.value_id == legacy_value_id,
            )
        ).mappings().all()
        assert len(runtime_rows) == 1
        assert runtime_rows[0]["object_type"] == legacy_object_type
        assert runtime_rows[0]["codec_id"] == legacy_codec_id
        assert runtime_rows[0]["project_value_ref"] == legacy_project_ref


def test_cross_root_writing_and_verifier_rejected(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.connect() as connection:
        root_one = _root(connection)
        knowledge = _knowledge_handle(root_one)
        writing = root_one.compose_and_stage_writing(
            artifact_id="draft:c8-pg:cross-root",
            knowledge_handles=(knowledge,),
            citation_ids=("ev:c8-pg:1",),
            spec=_writing_spec(
                base_incarnation=knowledge.issued_read.handle.incarnation
            ),
            run_id=RUN_ID,
            step_id=STEP_ID,
            qualifier_ref="qualifier:cross-root",
        )
        root_two = _root(connection)
        with pytest.raises(C8ProductionTrustRootError, match="not issued"):
            root_two.verify_report(writing)
        verifier = root_one.verify_report(writing)
        with pytest.raises(C8ProductionTrustRootError, match="not issued"):
            root_two.admit_report(verifier, run_id=RUN_ID, step_id=STEP_ID)


def _report_flow(
    root: C8ProductionRoot,
    *,
    artifact_id: str = "draft:c8-pg:report",
) -> tuple[
    ProductionKnowledgeHandle,
    Any,
    ProductionVerifierHandle,
]:
    material_handle = _material_handle(root)
    knowledge = _knowledge_handle(
        root,
        material_handle,
        candidate_id=f"knowledge:{artifact_id}",
    )
    writing = root.compose_and_stage_writing(
        artifact_id=artifact_id,
        knowledge_handles=(knowledge,),
        citation_ids=("ev:c8-pg:1",),
        spec=_writing_spec(base_incarnation=knowledge.issued_read.handle.incarnation),
        run_id=RUN_ID,
        step_id=STEP_ID,
        qualifier_ref=f"qualifier:{artifact_id}",
    )
    verifier = root.verify_report(
        writing,
        citation_closure=writing.artifact.citation_closure,
    )
    return knowledge, writing, verifier


def test_report_verify_admit_readback_no_caller_positives(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.begin() as connection:
        root = _root(connection)
        _knowledge, _writing, verifier = _report_flow(root)
        assert isinstance(verifier, ProductionVerifierHandle)
        assert verifier.verification.state == "VERIFIED"
        with pytest.raises(TypeError):
            root.admit_report(verifier, run_id=RUN_ID, step_id=STEP_ID, admitted=True)  # type: ignore[call-arg]
        with pytest.raises(TypeError):
            root.admit_report(  # type: ignore[call-arg]
                verifier,
                run_id=RUN_ID,
                step_id=STEP_ID,
                canonical_commit_ref="caller-ref",
            )
        with pytest.raises(TypeError):
            root.admit_report(  # type: ignore[call-arg]
                verifier,
                run_id=RUN_ID,
                step_id=STEP_ID,
                receipt_digest="caller-receipt",
            )
        admission = root.admit_report(verifier, run_id=RUN_ID, step_id=STEP_ID)
        assert admission.readback.state == "ADMITTED"
        assert admission.readback.authority_kind == PRODUCTION_AUTHORITY_ID
        assert admission.artifact_readback.verifier_registry_digest
        assert admission.artifact_readback.production_canonical_authority is False


def test_admission_ack_loss_readback_no_duplicate_effect(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.begin() as connection:
        root = _root(connection)
        _knowledge, _writing, verifier = _report_flow(root)
        first = root.admit_report(verifier, run_id=RUN_ID, step_id=STEP_ID)
        second = root.admit_report(verifier, run_id=RUN_ID, step_id=STEP_ID)
        assert second == first
        assert _count_rows(connection, PUBLIC_TABLES["runtime_commit_intents"]) == 1
        assert _count_rows(connection, PUBLIC_TABLES["runtime_staged_artifacts"]) == 1
        report_rows = connection.execute(
            sa.select(sa.func.count())
            .select_from(_value_table())
            .where(_value_table().c.value_id.startswith("knowledge:report:"))
        ).scalar_one()
        assert int(report_rows) == 1
        readback = root.readback_admission(verifier)
        assert readback.readback == first.readback
        intent = CommitIntentRepository(connection, _scope()).find_for_readback(
            "knowledge.report.v2",
            "knowledge:report:admit:draft:c8-pg:report",
        )
        assert intent["state"] == CommitIntentStatus.COMMITTED.value


def test_admission_finalize_fault_rolls_back_and_never_duplicates(
    disposable_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_material(disposable_database)

    def _fail_result(*_args: object, **_kwargs: object) -> Any:
        raise StaleRevisionError("injected artifact finalize fault")

    monkeypatch.setattr(CommitIntentRepository, "record_result", _fail_result)
    with (
        disposable_database.begin() as connection,
        pytest.raises(C8ArtifactOutcomeUnknownError),
    ):
        root = _root(connection)
        _knowledge, _writing, verifier = _report_flow(root)
        root.admit_report(verifier, run_id=RUN_ID, step_id=STEP_ID)
    with disposable_database.connect() as check:
        assert _count_rows(check, PUBLIC_TABLES["runtime_commit_intents"]) == 0
        report_rows = check.execute(
            sa.select(sa.func.count())
            .select_from(_value_table())
            .where(_value_table().c.value_id.startswith("knowledge:report:"))
        ).scalar_one()
        assert int(report_rows) == 0
        staged_row = (
            check.execute(
                sa.select(PUBLIC_TABLES["runtime_staged_artifacts"]).where(
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_staged_artifacts"].c.artifact_id
                    == "draft:c8-pg:report",
                )
            )
            .mappings()
            .one()
        )
        assert staged_row["state"] == "VERIFIED"


def test_fresh_report_reissue_from_durable_locator(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    artifact_id = "draft:c8-pg:reissue"
    with disposable_database.begin() as connection:
        root_one = _root(connection)
        material = _material_handle(root_one)
        knowledge = _knowledge_handle(
            root_one,
            material,
            candidate_id=f"knowledge:{artifact_id}",
        )
        writing = root_one.compose_and_stage_writing(
            artifact_id=artifact_id,
            knowledge_handles=(knowledge,),
            citation_ids=("ev:c8-pg:1",),
            spec=_writing_spec(
                base_incarnation=knowledge.issued_read.handle.incarnation
            ),
            run_id=RUN_ID,
            step_id=STEP_ID,
            qualifier_ref=f"qualifier:{artifact_id}",
        )
        root_one.verify_report(writing)
    disposable_database.dispose()
    with disposable_database.connect() as connection:
        fresh_root = _root(connection)
        with pytest.raises(C8ProductionTrustRootError, match="not issued"):
            fresh_root.verify_report(writing)
        reissued = fresh_root.reissue_writing(artifact_id)
        assert reissued.artifact_id == artifact_id
        verifier = fresh_root.verify_report(reissued)
        admission = fresh_root.admit_report(
            verifier,
            run_id=RUN_ID,
            step_id=STEP_ID,
        )
        assert admission.readback.state == "ADMITTED"
        readback = fresh_root.readback_admission(verifier)
        assert readback.readback == admission.readback


def test_fresh_reissue_rejects_stale_digest_tamper(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)

    def _stage(connection: sa.Connection, artifact_id: str) -> None:
        root = _root(connection)
        material = _material_handle(root)
        knowledge = _knowledge_handle(
            root,
            material,
            candidate_id=f"knowledge:{artifact_id}",
        )
        root.compose_and_stage_writing(
            artifact_id=artifact_id,
            knowledge_handles=(knowledge,),
            citation_ids=("ev:c8-pg:1",),
            spec=_writing_spec(
                base_incarnation=knowledge.issued_read.handle.incarnation
            ),
            run_id=RUN_ID,
            step_id=STEP_ID,
            qualifier_ref=f"qualifier:{artifact_id}",
        )

    cases: tuple[tuple[str, dict[str, object], str], ...] = (
        (
            "content",
            {"content_bytes": b"# tampered\n"},
            "content digest",
        ),
        (
            "provenance",
            {"provenance_json": {"artifact_id": "draft:other"}},
            "provenance",
        ),
        (
            "incarnation",
            {"incarnation": "knowledge:staged-report:stale"},
            "incarnation",
        ),
        (
            "write_receipt",
            {"write_receipt_digest": "0" * 64},
            "write receipt",
        ),
    )
    for label, update, expected in cases:
        _reset(disposable_database)
        artifact_id = f"draft:c8-pg:tamper-{label}"
        with disposable_database.begin() as connection:
            _seed_c7_material(connection)
            _stage(connection, artifact_id)
            connection.execute(
                _value_table()
                .update()
                .where(
                    _value_table().c.project_key == PROJECT_KEY,
                    _value_table().c.value_id == staged_artifact_value_id(artifact_id),
                )
                .values(**update)
            )
            with pytest.raises(C8ArtifactIntegrityError, match=expected):
                _root(connection).reissue_writing(artifact_id)


def test_internal_delivery_prepared_then_typed_unavailable(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.begin() as connection:
        root = _root(connection)
        _knowledge, _writing, verifier = _report_flow(root)
        admission = root.admit_report(verifier, run_id=RUN_ID, step_id=STEP_ID)
        preparation = root.prepare_internal_export(admission)
        assert preparation.state == "PREPARED"
        intent = root.build_internal_delivery_intent(
            preparation,
            approval_digest="0" * 64,
            approval_epoch=1,
        )
        assert intent.state == "APPROVED"
        with pytest.raises(C8DeliveryUnavailableError, match="typed unavailable"):
            root.attempt_internal_delivery(intent)
        with pytest.raises(C8ProductionTrustRootError, match="external delivery"):
            root.build_external_delivery_intent(
                preparation,
                approval_digest="0" * 64,
                approval_epoch=1,
            )


def test_graph_fixed_family_loss_catalog_and_active_handle(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    source = _graph_source()
    with disposable_database.begin() as connection:
        root = _root(connection)
        with pytest.raises(TypeError):
            root.project_graph(  # type: ignore[call-arg]
                graph_id="graph:c8-pg",
                generation=0,
                occurrences=(_occurrence("o:1"),),
                loss_profile=c8.GraphLossProfile(profile_id="caller-profile"),
                provenance_digest="0" * 64,
                source_revision=1,
                **source,
            )
        first = root.project_graph(
            graph_id="graph:c8-pg",
            generation=0,
            occurrences=(_occurrence("o:1"),),
            provenance_digest="0" * 64,
            source_revision=1,
            **source,
        )
        assert first.generation.authority_kind == PRODUCTION_AUTHORITY_ID
        assert first.authority_digest == root.authority_digest
        assert first.loss_profile_registry_id.startswith(
            "knowledge.graph-loss-profile.knowledge.production.v2"
        )
        graph_row = (
            connection.execute(
                sa.select(_value_table()).where(
                    _value_table().c.value_id
                    == graph_value_id("graph:c8-pg", 0)
                )
            )
            .mappings()
            .one()
        )
        assert graph_row["object_type"] == C8_GRAPH_VALUE_OBJECT_TYPE
        assert graph_row["codec_id"] == C8_GRAPH_VALUE_CODEC_ID
        assert graph_row["provenance_json"]["schema"] == KNOWLEDGE_GRAPH_VALUE_SCHEMA
        active = root.issue_active_graph_handle(
            graph_id="graph:c8-pg",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        assert isinstance(active, ProductionGraphReadHandle)
        result = root.consume_graph(
            active,
            consumer_id="consumer:c8-pg",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        assert result.state == "AVAILABLE"
        assert result.provider_calls == 0
        assert result.store_writes == 0
        assert result.export_calls == 0


def test_graph_stale_active_handle_rejected_and_cas_failure_keeps_old(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    source = _graph_source()
    with disposable_database.begin() as connection:
        root = _root(connection)
        first = root.project_graph(
            graph_id="graph:c8-pg-stale",
            generation=0,
            occurrences=(_occurrence("o:1"),),
            provenance_digest="0" * 64,
            source_revision=1,
            **source,
        )
        active = root.issue_active_graph_handle(
            graph_id="graph:c8-pg-stale",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        root.project_graph(
            graph_id="graph:c8-pg-stale",
            generation=1,
            occurrences=(_occurrence("o:1"), _occurrence("o:2")),
            provenance_digest="0" * 64,
            source_revision=1,
            **source,
        )
        offset_row = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_projection_offsets"]).where(
                    PUBLIC_TABLES["runtime_projection_offsets"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_projection_offsets"].c.projection_offset_id
                    == "knowledge:graph:offset:graph:c8-pg-stale",
                )
            )
            .mappings()
            .one()
        )
        assert int(offset_row["projection_generation"]) == 1
        assert int(offset_row["revision"]) == 1
        assert offset_row["offset_ref"] == (
            f"project-value:{graph_value_id('graph:c8-pg-stale', 1)}"
        )
        with pytest.raises(C8ProductionTrustRootError, match="stale"):
            root.consume_graph(
                active,
                consumer_id="consumer:c8-pg",
                source_ref=source["source_ref"],
                source_incarnation=source["source_incarnation"],
            )
        with pytest.raises(C8GraphOffsetCasError, match="unchanged"):
            root.project_graph(
                graph_id="graph:c8-pg-stale",
                generation=2,
                occurrences=(_occurrence("o:1"),),
                provenance_digest="0" * 64,
                source_revision=1,
                expected_offset_revision=99,
                **source,
            )
        fresh_active = root.issue_active_graph_handle(
            graph_id="graph:c8-pg-stale",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        result = root.consume_graph(
            fresh_active,
            consumer_id="consumer:c8-pg",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        assert result.state == "AVAILABLE"
        assert first.generation.generation_id != result.generation_id
        assert (
            _count_rows(
                connection,
                _value_table(),
            )
            >= 2
        )
    with disposable_database.connect() as check:
        gen2 = check.execute(
            sa.select(sa.func.count())
            .select_from(_value_table())
            .where(_value_table().c.value_id == graph_value_id("graph:c8-pg-stale", 2))
        ).scalar_one()
        assert int(gen2) == 0


def test_legacy_graph_offset_and_value_are_exact_read_only(
    disposable_database: Engine,
) -> None:
    source = _graph_source()
    graph_id = "graph:c8-pg-legacy"
    legacy_value_id = f"c8:graph:{graph_id}:gen:0"
    legacy_offset_ref = f"project-value:{legacy_value_id}"
    legacy_registry_id = "c8.graph-loss-profile.c8.production.v1"
    legacy_registry_digest = c8.knowledge_canonical_digest(
        {
            "registry_id": legacy_registry_id,
            "authority_id": LEGACY_PRODUCTION_AUTHORITY_ID,
            "authority_digest": LEGACY_PRODUCTION_AUTHORITY_DIGEST,
        }
    )
    generation = c8.GraphProjectionGeneration(
        generation_id=f"c8.graph.generation:{graph_id}:0",
        project_key=PROJECT_KEY,
        occurrences=(_occurrence("legacy:o:1"),),
        declared_loss=("c8.graph.historical-loss.v1",),
        provenance_digest="0" * 64,
        offset=legacy_offset_ref,
        authority_kind=LEGACY_PRODUCTION_AUTHORITY_ID,
        authority_digest=LEGACY_PRODUCTION_AUTHORITY_DIGEST,
        loss_profile_registry_id=legacy_registry_id,
        loss_profile_registry_digest=legacy_registry_digest,
    )
    body = {
        "generation_id": generation.generation_id,
        "project_key": generation.project_key,
        "occurrences": [
            {
                "occurrence_id": occurrence.occurrence_id,
                "edge_type": occurrence.edge_type,
                "source_identity": occurrence.source_identity,
                "target_identity": occurrence.target_identity,
                "position": occurrence.position,
                "occurrence_digest": occurrence.occurrence_digest,
            }
            for occurrence in generation.occurrences
        ],
        "declared_loss": list(generation.declared_loss),
        "provenance_digest": generation.provenance_digest,
        "offset": generation.offset,
        "authority_kind": generation.authority_kind,
        "authority_digest": generation.authority_digest,
        "loss_profile_registry_id": generation.loss_profile_registry_id,
        "loss_profile_registry_digest": generation.loss_profile_registry_digest,
    }
    exact = canonical_json(body).encode("utf-8")
    provenance = {
        "schema": LEGACY_C8_GRAPH_VALUE_SCHEMA,
        "graph_value_id": legacy_value_id,
        "generation_id": generation.generation_id,
        "projection_digest": generation.projection_digest,
        "provenance_digest": generation.provenance_digest,
        "source_ref": source["source_ref"],
        "authority_kind": generation.authority_kind,
        "authority_digest": generation.authority_digest,
        "loss_profile_registry_id": generation.loss_profile_registry_id,
        "loss_profile_registry_digest": generation.loss_profile_registry_digest,
    }
    with disposable_database.begin() as connection:
        ValueRepository(connection, PROJECT_TABLES).put_exact(
            _scope(),
            value_id=legacy_value_id,
            object_type=LEGACY_C8_GRAPH_VALUE_OBJECT_TYPE,
            codec_id=LEGACY_C8_GRAPH_VALUE_CODEC_ID,
            content=exact,
            expected_digest=generation.projection_digest,
            provenance_digest=content_digest(provenance),
            expected_revision=0,
            expected_incarnation=f"c8:graph:{generation.projection_digest}",
            source_ref=source["source_ref"],
            provenance=provenance,
        )
        ProjectionOffsetRepository(connection, _scope()).create(
            projection_offset_id=f"c8:graph:offset:{graph_id}",
            key=ProjectionOffsetKey(
                projector_id=LEGACY_C8_GRAPH_PROJECTOR_ID,
                projector_version="1",
                source_kind=LEGACY_C8_GRAPH_SOURCE_KIND,
                source_ref=f"graph:{graph_id}:{source['source_ref']}",
                source_incarnation=source["source_incarnation"],
            ),
            projection_generation=0,
            source_revision=1,
            source_digest=source["source_digest"],
            offset_ref=legacy_offset_ref,
        )
        active = _root(connection).issue_active_graph_handle(
            graph_id=graph_id,
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        assert active.generation_id == generation.generation_id
        assert active.offset == legacy_offset_ref
        current_rows = connection.execute(
            sa.select(sa.func.count())
            .select_from(_value_table())
            .where(_value_table().c.value_id == graph_value_id(graph_id, 0))
        ).scalar_one()
        assert int(current_rows) == 0


def test_graph_wrong_graph_id_cannot_read_other_graph(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    source = _graph_source()
    with disposable_database.begin() as connection:
        root = _root(connection)
        root.project_graph(
            graph_id="graph:c8-pg-a",
            generation=0,
            occurrences=(_occurrence("o:1"),),
            provenance_digest="0" * 64,
            source_revision=1,
            **source,
        )
        with pytest.raises(C8GraphProjectionUnavailableError):
            root.issue_active_graph_handle(
                graph_id="graph:c8-pg-b",
                source_ref=source["source_ref"],
                source_incarnation=source["source_incarnation"],
            )
        with pytest.raises(C8GraphProjectionUnavailableError):
            read_active_graph(
                connection,
                scope=_scope(),
                graph_id="graph:c8-pg-b",
                source_ref=source["source_ref"],
                source_incarnation=source["source_incarnation"],
            )
        active = root.issue_active_graph_handle(
            graph_id="graph:c8-pg-a",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        assert active.graph_id == "graph:c8-pg-a"
        result = root.consume_graph(
            active,
            consumer_id="consumer:c8-pg",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        assert result.state == "AVAILABLE"


def test_graph_consumer_never_synthesizes_evidence(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    source = _graph_source()
    with disposable_database.begin() as connection:
        root = _root(connection)
        root.project_graph(
            graph_id="graph:c8-pg-consumer",
            generation=0,
            occurrences=(_occurrence("o:1"),),
            provenance_digest="0" * 64,
            source_revision=1,
            **source,
        )
        active = root.issue_active_graph_handle(
            graph_id="graph:c8-pg-consumer",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        with pytest.raises(c8.KnowledgeProjectionError, match="never creates claim"):
            root.consume_graph(
                active,
                consumer_id="consumer:c8-pg",
                request_claim_support=True,
                source_ref=source["source_ref"],
                source_incarnation=source["source_incarnation"],
            )


def test_fresh_session_reissues_from_durable_locator_and_rejects_old_witnesses(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    source = _graph_source()
    with disposable_database.begin() as connection:
        root = _root(connection)
        material_handle = _material_handle(root)
        knowledge = _knowledge_handle(root, candidate_id="knowledge-candidate:fresh")
        _knowledge, _writing, verifier = _report_flow(
            root,
            artifact_id="draft:c8-pg:fresh",
        )
        root.admit_report(verifier, run_id=RUN_ID, step_id=STEP_ID)
        root.project_graph(
            graph_id="graph:c8-pg-fresh",
            generation=0,
            occurrences=(_occurrence("o:1"),),
            provenance_digest="0" * 64,
            source_revision=1,
            **source,
        )
        old_graph_handle = root.issue_active_graph_handle(
            graph_id="graph:c8-pg-fresh",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
    disposable_database.dispose()
    with disposable_database.connect() as connection:
        fresh_root = _root(connection)
        reissued = fresh_root.read_material(candidate_id=_base_pair()[1].candidate_id)
        assert reissued.material == material_handle.material
        with pytest.raises(C8ProductionTrustRootError, match="not issued"):
            fresh_root.stage_knowledge(
                material_handle,
                formation_profile=FORMATION_PROFILE,
                candidate_id="knowledge-candidate:old-witness",
                canonical_statement="old",
                primary_type_node_key="Topic",
                evidence_refs=("ev:1",),
                fields=("canonical_statement",),
            )
        with pytest.raises(C8ProductionTrustRootError, match="not issued"):
            fresh_root.consume_graph(
                old_graph_handle,
                consumer_id="consumer:fresh",
                source_ref=source["source_ref"],
                source_incarnation=source["source_incarnation"],
            )
        fresh_graph = fresh_root.issue_active_graph_handle(
            graph_id="graph:c8-pg-fresh",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        result = fresh_root.consume_graph(
            fresh_graph,
            consumer_id="consumer:fresh",
            source_ref=source["source_ref"],
            source_incarnation=source["source_incarnation"],
        )
        assert result.state == "AVAILABLE"
        assert knowledge.issued_read.handle.handle_id


def test_provider_network_external_zero_and_teardown(
    disposable_database: Engine,
) -> None:
    _seed_material(disposable_database)
    with disposable_database.begin() as connection:
        root = _root(connection)
        _knowledge, _writing, verifier = _report_flow(root)
        admission = root.admit_report(verifier, run_id=RUN_ID, step_id=STEP_ID)
        assert admission.artifact_readback.provider_calls == 0
        assert admission.artifact_readback.export_calls == 0
        assert admission.artifact_readback.live_provider is False
        assert admission.artifact_readback.promotion is False
        assert _count_rows(connection, PUBLIC_TABLES["runtime_effect_attempts"]) == 0
