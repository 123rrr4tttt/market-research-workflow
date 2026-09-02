"""Shared real-PostgreSQL fixture for the bounded P0-C specimen.

The fixture is intentionally opt-in.  It refuses a default/production-looking
database and refuses to adopt pre-existing successor tables or its project
schema.  The two legacy rows are not synthetic: their complete INSERT
statements are extracted from the frozen repository seed SQL and checked
against known statement and UTF-8 content digests before every specimen.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_migration.document_canonical_read import (
    PostgresLegacyDocumentCanonicalReadAdapter,
)
from app.successor_runtime.capabilities import (
    build_first_specimen_bundle,
    build_first_specimen_catalog,
)
from app.successor_runtime.capabilities.first_specimen_delivery_gate import (
    DeliveryIntentTemplate,
)
from app.successor_runtime.capabilities.first_specimen_submission import (
    CompileAssignmentRequest,
    FirstSpecimenSubmissionService,
    SubmissionCommand,
    SubmittedRuntimePacket,
)
from app.successor_runtime.language.combinators import default_registries
from app.successor_runtime.research.codec import sha256_hex
from app.successor_runtime.research.inquiries import (
    Inquiry,
    PlanWorkItem,
    ResearchIntent,
    ResearchPlan,
)
from app.successor_runtime.research.sources import SourceRef
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompilerBinding,
    HandlerBindingKind,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    ProjectTables,
    project_tables,
)
from app.successor_runtime.substrate.postgres.owner_bindings import (
    OwnerBindingRecord,
    OwnerBindingRepository,
)
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.research_ledger import (
    ResearchLedgerRepository,
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    AssignmentEnvelope,
    RuntimeLifecycleRepository,
    SubmitRun,
)
from app.successor_runtime.substrate.postgres.session import (
    compute_scope_digest,
    create_runtime_engine,
)
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork
from app.successor_runtime.substrate.postgres.values import ValueRepository

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "p0c-postgres-acceptance"
PROJECT_SCHEMA = "mrw_p0c_postgres_acceptance"
PROJECT_REGISTRY_REVISION = 1
PROJECT_INCARNATION = "p0c-project-incarnation-1"
PROJECT_SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    PROJECT_REGISTRY_REVISION,
    PROJECT_INCARNATION,
)
NOW = datetime(2030, 8, 31, 8, 0, tzinfo=UTC)

SEED_SQL = (
    Path(__file__).resolve().parents[2]
    / "seed_data"
    / "project_demo_proj_v0.9-rc2.0.sql"
)

SEED_STATEMENT_SHA256 = {
    101: "2d784235fbd94613e46782e2016eb7ddebf42e14f1779885ebbaf4576699bb93",
    102: "80ae76aac30d1670b3838079534f550bc01c39f3747428f9b533f99093c812ab",
}
SEED_CONTENT_BYTES = {101: 1153, 102: 50009}
SEED_CONTENT_SHA256 = {
    101: "409789283ff6ee8aabcd5924866199cc6f9bb26f957a99f854708bd4aabb3c40",
    102: "0494ea262e1577dc00cb3241341c4ab8bfe155b5601d61be7bee70407cc4ea6b",
}

SUBMISSION_AUTHORITY_DIGEST = hashlib.sha256(b"p0c-submission-authority").hexdigest()
DELIVERY_AUTHORITY_DIGEST = hashlib.sha256(b"p0c-delivery-authority").hexdigest()
DEPLOYMENT_CATALOG_DIGEST = hashlib.sha256(b"p0c-deployment-catalog").hexdigest()
CLAIM_POLICY_DIGEST = hashlib.sha256(b"p0c-claim-policy").hexdigest()
RESOURCE_POLICY_DIGEST = hashlib.sha256(b"p0c-resource-policy").hexdigest()
QUEUE_ELIGIBILITY_DIGEST = hashlib.sha256(b"p0c-queue-eligibility").hexdigest()


def _require_dedicated_database_url() -> str:
    database_url = os.environ.get(DATABASE_ENV)
    if not database_url:
        pytest.skip(f"{DATABASE_ENV} is not set")
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        pytest.fail(f"{DATABASE_ENV} must use a PostgreSQL driver")
    database_name = url.database or ""
    if database_name in {"postgres", "template0", "template1"} or not re.search(
        r"(?:test|testing|ci)", database_name, re.IGNORECASE
    ):
        pytest.fail(
            f"{DATABASE_ENV} must name a dedicated test/CI database; "
            f"refusing database {database_name!r}"
        )
    return database_url


def _sql_statements(text: str) -> tuple[str, ...]:
    """Split PostgreSQL seed text without corrupting doubled string quotes."""

    statements: list[str] = []
    start = 0
    quoted = False
    index = 0
    while index < len(text):
        character = text[index]
        if character == "'":
            if quoted and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            quoted = not quoted
        elif character == ";" and not quoted:
            statements.append(text[start : index + 1])
            start = index + 1
        index += 1
    if quoted:
        raise AssertionError("seed SQL contains an unterminated string literal")
    return tuple(statements)


def frozen_document_seed_statements() -> dict[int, str]:
    source = SEED_SQL.read_text(encoding="utf-8")
    statements = _sql_statements(source)
    selected: dict[int, str] = {}
    prefix = "INSERT INTO project_demo_proj.documents "
    for document_id in (101, 102):
        matches = [
            statement
            for statement in statements
            if statement.lstrip().startswith(prefix)
            and f"VALUES ({document_id}," in statement
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"expected one exact seed statement for Document {document_id}, "
                f"found {len(matches)}"
            )
        statement = matches[0]
        observed = hashlib.sha256(statement.encode("utf-8")).hexdigest()
        if observed != SEED_STATEMENT_SHA256[document_id]:
            raise AssertionError(
                f"Document {document_id} seed statement drift: {observed}"
            )
        selected[document_id] = statement
    return selected


LEGACY_METADATA = sa.MetaData(schema=PROJECT_SCHEMA)
LEGACY_DOCUMENTS = sa.Table(
    "documents",
    LEGACY_METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("source_id", sa.BigInteger),
    sa.Column("state", sa.Text),
    sa.Column("doc_type", sa.Text),
    sa.Column("title", sa.Text),
    sa.Column("status", sa.Text),
    sa.Column("publish_date", sa.Date),
    sa.Column("content", sa.Text),
    sa.Column("summary", sa.Text),
    sa.Column("text_hash", sa.Text),
    sa.Column("uri", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("extracted_data", sa.dialects.postgresql.JSONB),
)


@dataclass(frozen=True, slots=True)
class LiveP0CDatabase:
    engine: Engine
    project_metadata: sa.MetaData
    project_tables: ProjectTables
    scope: RuntimeScope

    def value_bytes(self, value_id: str) -> bytes:
        with self.engine.connect() as connection:
            row = connection.execute(
                sa.select(
                    self.project_tables.successor_values.c.content_bytes,
                    self.project_tables.successor_values.c.content_digest,
                ).where(
                    self.project_tables.successor_values.c.project_key == PROJECT_KEY,
                    self.project_tables.successor_values.c.value_id == value_id,
                )
            ).mappings().one()
            exact = bytes(row["content_bytes"])
            assert hashlib.sha256(exact).hexdigest() == row["content_digest"]
            return exact

    def submission_service(
        self,
        *,
        document_port: Callable[[RuntimeUnitOfWork], object] | None = None,
        value_port: Callable[[RuntimeUnitOfWork], object] | None = None,
        runtime_port: Callable[[RuntimeUnitOfWork], object] | None = None,
    ) -> FirstSpecimenSubmissionService:
        def uow_factory() -> RuntimeUnitOfWork:
            return RuntimeUnitOfWork(engine=self.engine)

        return FirstSpecimenSubmissionService(
            uow_factory=uow_factory,
            document_port=document_port
            or (
                lambda uow: PostgresLegacyDocumentCanonicalReadAdapter(
                    uow.connection
                )
            ),
            value_port=value_port
            or (lambda uow: ValueRepository(uow.connection, self.project_tables)),
            ledger_port=lambda uow: ResearchLedgerRepository(
                uow.connection, self.project_tables
            ),
            program_port=lambda uow: ProgramRepository(
                uow.connection, self.project_tables
            ),
            runtime_port=runtime_port
            or (
                lambda uow: _SubmissionRuntimeAdapter(
                    uow.connection, self.scope
                )
            ),
            compile_assignment_factory=compile_assignment,
        )


class _SubmissionRuntimeAdapter:
    """Tests-only composition adapter over the production lifecycle repository."""

    def __init__(self, connection: sa.Connection, scope: RuntimeScope) -> None:
        self._repository = RuntimeLifecycleRepository(connection, scope)

    def get_submission(
        self, _scope: RuntimeScope, _submission_id: str
    ) -> None:
        # P0-C submits one new exact logical request per clean fixture.  Durable
        # idempotency/reconstruction is exercised directly by its repositories.
        return None

    def create_submitted(
        self, _scope: RuntimeScope, packet: SubmittedRuntimePacket
    ) -> Any:
        envelope = AssignmentEnvelope(
            assignment=packet.compile_assignment,
            required_node_profile_selector=packet.required_node_profile_selector,
            authority_digest=packet.submission_authority_digest,
            resource_policy_digest=packet.resource_policy_digest,
            fairness_key=packet.fairness_key,
        )
        return self._repository.submit(
            SubmitRun(
                run_id=packet.run_id,
                incarnation=packet.run_incarnation,
                program_id=packet.program_id,
                program_digest=packet.program_digest,
                program_storage_ref=packet.program_storage_ref,
                contract_version=packet.contract_version,
                submission_authority_digest=packet.submission_authority_digest,
                compile_work=envelope,
                due_at=packet.due_at,
            )
        )

    def record_submission(self, _scope: RuntimeScope, _submitted: Any) -> None:
        # The authoritative data already lives in project/public tables.  A
        # Python object cache would be a second truth source.
        return None


def compile_assignment(request: CompileAssignmentRequest) -> RuntimeAssignment:
    command = request.command
    compiler = command.compiler_binding
    if not isinstance(compiler, CompilerBinding):
        raise TypeError("first specimen compile requires CompilerBinding")
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=f"{command.run_id}:compile",
        assignment_kind=AssignmentKind.COMPILE,
        project_key=PROJECT_KEY,
        run_id=command.run_id,
        capability_id="mrw.first-specimen.compile",
        handler_binding_kind=HandlerBindingKind.COMPILER,
        handler_binding_ref=f"handler-binding:sha256:{compiler.binding_digest}",
        handler_binding_digest=compiler.binding_digest,
        handler_binding=compiler,
        program_digest=request.program.program_digest,
        deployment_catalog_digest=command.deployment_catalog_digest,
        execution_epoch=0,
        incarnation=command.run_incarnation,
        input_refs=request.input_refs,
        input_closure_digest=sha256_hex(list(request.input_refs)),
        queue_eligibility_digest=command.queue_eligibility_digest,
        resource_policy_epoch=command.resource_policy_epoch,
        claim_authority_epoch=command.claim_authority_epoch,
        claim_policy_digest=command.claim_policy_digest,
        trace_id=command.trace_id,
    )


def source_ref(document_id: int) -> SourceRef:
    return SourceRef(
        source_ref_id=f"source:document:{document_id}",
        owner_id="legacy_document_store",
        locator=f"document://{PROJECT_KEY}/{document_id}",
        source_class="existing_project_document",
        observed_at=NOW,
        access_profile_ref="DocumentCanonicalReadPort",
    )


def submission_command(*, suffix: str = "1") -> SubmissionCommand:
    bundle = build_first_specimen_bundle()
    catalog = build_first_specimen_catalog(bundle.operations)
    assert catalog.catalog_digest is not None
    compiler = CompilerBinding.from_content(
        compiler_id="mrw.functorial-successor.compiler",
        compiler_version="1.0.0",
        compiler_digest=hashlib.sha256(b"p0c-compiler").hexdigest(),
        operation_catalog_digest=catalog.catalog_digest,
        domain_contract_snapshot_digest=hashlib.sha256(
            b"p0c-domain-contract-snapshot"
        ).hexdigest(),
    )
    intent = ResearchIntent(
        intent_id=f"intent:p0c:{suffix}",
        project_key=PROJECT_KEY,
        purpose="compare the exact frozen Document 101 and 102 captures",
        audience_or_use="internal research review",
        scope={"documents": [101, 102]},
        as_of=NOW,
        constraints={"network": False, "external_delivery": False},
        expected_delivery={"format": "markdown", "channel": "internal_export"},
    )
    inquiry = Inquiry(
        inquiry_id=f"inquiry:p0c:{suffix}",
        intent_ref=intent.intent_id,
        question_or_hypothesis="What claim is supported by both exact documents?",
        acceptance_conditions=("two exact captured inputs",),
        stop_conditions=("claim or explicit gap",),
        uncertainty_ceiling="explicit",
    )
    research_plan = ResearchPlan(
        plan_id=f"research-plan:p0c:{suffix}",
        inquiry_ref=inquiry.inquiry_id,
        work_items=(
            PlanWorkItem("source:a", "capture_read_qualify"),
            PlanWorkItem("source:b", "capture_read_qualify", ("source:a",)),
        ),
        budget={"documents": 2},
        deadline=None,
        replan_policy={"mode": "open_gap"},
    )
    return SubmissionCommand(
        submission_id=f"submission:p0c:{suffix}",
        scope=RuntimeScope(
            ProjectScopeRef(
                project_key=PROJECT_KEY,
                resolved_schema=PROJECT_SCHEMA,
                project_registry_revision=PROJECT_REGISTRY_REVISION,
                incarnation=PROJECT_INCARNATION,
                scope_digest=PROJECT_SCOPE_DIGEST,
            ),
            actor_id="human:p0c-postgres-acceptance",
        ),
        program_id=f"program:p0c:{suffix}",
        run_id=f"run:p0c:{suffix}",
        run_incarnation=f"run-inc:p0c:{suffix}",
        intent=intent,
        inquiry=inquiry,
        research_plan=research_plan,
        source_refs=(source_ref(101), source_ref(102)),
        document_ids=(101, 102),
        delivery_template=DeliveryIntentTemplate(
            value_id=f"delivery-template:p0c:{suffix}",
            delivery_intent_id=f"delivery-intent:p0c:{suffix}",
            audience="internal-review",
            approval_ref=f"approval:p0c:{suffix}",
            authority_digest=DELIVERY_AUTHORITY_DIGEST,
            idempotency_key=f"delivery:p0c:{suffix}",
        ),
        catalog=catalog,
        registries=default_registries(),
        compiler_binding=compiler,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        submission_authority_digest=SUBMISSION_AUTHORITY_DIGEST,
        claim_authority_epoch=7,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        resource_policy_digest=RESOURCE_POLICY_DIGEST,
        resource_policy_epoch=8,
        queue_eligibility_digest=QUEUE_ELIGIBILITY_DIGEST,
        required_node_profile_selector="node-profile:p0c",
        fairness_key="p0c:mrw.first-specimen.compile",
        trace_id=f"trace:p0c:{suffix}",
        due_at=NOW,
    )


def _owner_bindings() -> tuple[tuple[str, str, str], ...]:
    return (
        ("ResearchIntent.v1", "CANONICAL_OWNED", "ResearchLedger"),
        ("Inquiry.v1", "CANONICAL_OWNED", "ResearchLedger"),
        ("ResearchPlan.v1", "CANONICAL_OWNED", "ResearchLedger"),
        (
            "SourceRef.v1",
            "IMMUTABLE_EXTERNAL_REF",
            "legacy_source_or_document_locator",
        ),
        (
            "MaterialRef.v1",
            "IMMUTABLE_EXTERNAL_REF",
            "CapturedMaterialSnapshot",
        ),
        ("Claim.v1", "CANONICAL_OWNED", "ResearchLedger"),
        ("Gap.v1", "CANONICAL_OWNED", "ResearchLedger"),
        (
            "ResearchArtifact.v1",
            "CANONICAL_OWNED",
            "ResearchLedger_plus_project_artifact_store",
        ),
        ("DeliveryIntent.v1", "CANONICAL_OWNED", "ResearchLedger"),
        (
            "DeliveryReceiptRef.v1",
            "IMMUTABLE_EXTERNAL_REF",
            "project_receipt_store",
        ),
    )


def _reset_database(database: LiveP0CDatabase) -> None:
    public = [f'"public"."{name}"' for name in PUBLIC_TABLES]
    project = [
        f'"{PROJECT_SCHEMA}"."{name}"'
        for name in database.project_tables.as_dict()
    ]
    qualified = public + project + [f'"{PROJECT_SCHEMA}"."documents"']
    with database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE " + ", ".join(qualified) + " RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
                project_key=PROJECT_KEY,
                registry_revision=PROJECT_REGISTRY_REVISION,
                resolved_schema=PROJECT_SCHEMA,
                scope_digest=PROJECT_SCOPE_DIGEST,
                incarnation=PROJECT_INCARNATION,
                state="ACTIVE",
                updated_by="p0c-postgres-fixture",
                approval_ref="approval:p0c-project-scope",
            )
        )
        owners = OwnerBindingRepository(connection, database.project_tables)
        for object_type, owner_mode, owner_id in _owner_bindings():
            owners.put_exact(
                database.scope,
                OwnerBindingRecord(
                    object_type=object_type,
                    owner_mode=owner_mode,
                    owner_id=owner_id,
                    owner_epoch=1,
                    readback_profile_ref="p0c-ledger-readback-v1",
                    base_incarnation=PROJECT_INCARNATION,
                    rollback_evidence_ref="rollback:p0c-local-test-only",
                    effective_at=NOW,
                    approval_ref="approval:p0c-owner-matrix",
                ),
                expected_owner_epoch=0,
                expected_base_incarnation=PROJECT_INCARNATION,
            )

        cursor = connection.connection.driver_connection.cursor()
        for document_id, statement in frozen_document_seed_statements().items():
            cursor.execute(
                statement.replace(
                    "project_demo_proj.documents",
                    f'"{PROJECT_SCHEMA}"."documents"',
                    1,
                )
            )
        rows = connection.execute(
            sa.select(LEGACY_DOCUMENTS.c.id, LEGACY_DOCUMENTS.c.content).order_by(
                LEGACY_DOCUMENTS.c.id
            )
        ).all()
        assert [row.id for row in rows] == [101, 102]
        for row in rows:
            exact = row.content.encode("utf-8")
            assert len(exact) == SEED_CONTENT_BYTES[row.id]
            assert hashlib.sha256(exact).hexdigest() == SEED_CONTENT_SHA256[row.id]


@pytest.fixture(scope="module")
def live_p0c_database() -> Iterator[LiveP0CDatabase]:
    database_url = _require_dedicated_database_url()
    engine = create_runtime_engine(database_url, poolclass=NullPool)
    inspector = sa.inspect(engine)
    existing_public = set(inspector.get_table_names(schema="public")) & set(
        PUBLIC_TABLES
    )
    if existing_public:
        engine.dispose()
        pytest.fail(
            "dedicated database already contains successor public tables; "
            f"refusing overwrite: {sorted(existing_public)}"
        )
    if PROJECT_SCHEMA in set(inspector.get_schema_names()):
        engine.dispose()
        pytest.fail(
            f"dedicated database already contains {PROJECT_SCHEMA}; refusing overwrite"
        )

    project_metadata = sa.MetaData()
    bound_project_tables = project_tables(project_metadata, PROJECT_SCHEMA)
    scope = RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=PROJECT_SCHEMA,
            project_registry_revision=PROJECT_REGISTRY_REVISION,
            incarnation=PROJECT_INCARNATION,
            scope_digest=PROJECT_SCOPE_DIGEST,
        ),
        actor_id="human:p0c-postgres-acceptance",
    )
    database = LiveP0CDatabase(
        engine=engine,
        project_metadata=project_metadata,
        project_tables=bound_project_tables,
        scope=scope,
    )
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{PROJECT_SCHEMA}"'))
            PUBLIC_METADATA.create_all(connection, checkfirst=False)
            project_metadata.create_all(connection, checkfirst=False)
            LEGACY_METADATA.create_all(connection, checkfirst=False)
        yield database
    finally:
        with engine.begin() as connection:
            PUBLIC_METADATA.drop_all(connection, checkfirst=True)
            connection.execute(
                sa.text(f'DROP SCHEMA IF EXISTS "{PROJECT_SCHEMA}" CASCADE')
            )
        engine.dispose()


@pytest.fixture
def p0c_database(live_p0c_database: LiveP0CDatabase) -> LiveP0CDatabase:
    _reset_database(live_p0c_database)
    return live_p0c_database


__all__ = [
    "CLAIM_POLICY_DIGEST",
    "DATABASE_ENV",
    "DELIVERY_AUTHORITY_DIGEST",
    "DEPLOYMENT_CATALOG_DIGEST",
    "LEGACY_DOCUMENTS",
    "LiveP0CDatabase",
    "NOW",
    "PROJECT_INCARNATION",
    "PROJECT_KEY",
    "PROJECT_REGISTRY_REVISION",
    "PROJECT_SCHEMA",
    "PROJECT_SCOPE_DIGEST",
    "QUEUE_ELIGIBILITY_DIGEST",
    "RESOURCE_POLICY_DIGEST",
    "SEED_CONTENT_BYTES",
    "SEED_CONTENT_SHA256",
    "SEED_STATEMENT_SHA256",
    "SUBMISSION_AUTHORITY_DIGEST",
    "compile_assignment",
    "frozen_document_seed_statements",
    "live_p0c_database",
    "p0c_database",
    "source_ref",
    "submission_command",
]
