"""Shared real-PostgreSQL fixture for the bounded specimen.

The fixture is intentionally opt-in.  It refuses a default/production-looking
database and refuses to adopt pre-existing successor tables or its project
schema. The two legacy documents are frozen as complete rows, independently
of the deployable demo dataset. Their exact UTF-8 content is checked after
insertion, before the specimen consumes it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_migration.document_canonical_read import (
    PostgresLegacyDocumentCanonicalReadAdapter,
)
from app.successor_runtime.capabilities.first_specimen_interpreters import (
    derive_material_ref,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.materials import CapturedMaterialSnapshot, MaterialRef
from app.successor_runtime.research.object_types import (
    CAPTURED_MATERIAL_SNAPSHOT_TYPE,
    MATERIAL_REF_TYPE,
    ObjectType,
    SOURCE_REF_TYPE,
)
from app.successor_runtime.research.sources import SourceRef
from app.successor_runtime.runtime.ports import (
    CanonicalDocumentRead,
    ProjectScopeRef,
    RuntimeScope,
)
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
from app.successor_runtime.substrate.postgres.research_ledger import (
    ResearchLedgerRepository,
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


def frozen_document_rows() -> list[dict]:
    path = Path(__file__).resolve().parents[1] / "fixtures/successor_runtime/capture_documents.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        for timestamp in ("created_at", "updated_at"):
            row[timestamp] = datetime.fromisoformat(row[timestamp])
    return rows


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
    sa.Column("extracted_data", sa.dialects.postgresql.JSONB(none_as_null=True)),
)


@dataclass(frozen=True, slots=True)
class RuntimeCapture:
    source_ref: SourceRef
    observation: CanonicalDocumentRead
    snapshot: CapturedMaterialSnapshot
    snapshot_value_ref: ValueRef
    source_value_ref: ValueRef
    material: MaterialRef
    material_value_ref: ValueRef
    material_object_ref: ResearchObjectRef


def _value_ref_from_row(row: sa.RowMapping) -> ValueRef:
    return ValueRef(
        value_id=str(row["value_id"]),
        project_key=PROJECT_KEY,
        object_type={
            CAPTURED_MATERIAL_SNAPSHOT_TYPE.type_id: CAPTURED_MATERIAL_SNAPSHOT_TYPE,
            SOURCE_REF_TYPE.type_id: SOURCE_REF_TYPE,
            MATERIAL_REF_TYPE.type_id: MATERIAL_REF_TYPE,
        }[str(row["object_type"])],
        codec_id=str(row["codec_id"]),
        content_digest=str(row["content_digest"]),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{row['value_id']}",
        byte_size=int(row["byte_size"]),
        provenance_digest=str(row["provenance_digest"]),
    )


def _value_ref(
    *, value_id: str, object_type: ObjectType, exact: bytes, provenance: dict[str, object]
) -> ValueRef:
    return ValueRef(
        value_id=value_id,
        project_key=PROJECT_KEY,
        object_type=object_type,
        codec_id=object_type.codec_id,
        content_digest=hashlib.sha256(exact).hexdigest(),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact),
        provenance_digest=sha256_hex(provenance),
    )


def _capture_from_rows(
    rows: dict[str, sa.RowMapping], *, suffix: str, label: str, document_id: int
) -> RuntimeCapture:
    source = source_ref(document_id)
    snapshot_row = rows[f"capture:{suffix}:snapshot:{label}"]
    source_row = rows[source.source_ref_id]
    exact = bytes(snapshot_row["content_bytes"])
    provenance = dict(snapshot_row["provenance_json"])
    observation = CanonicalDocumentRead(
        document_id=document_id,
        text_hash=provenance.get("observed_text_hash"),
        updated_at=datetime.fromisoformat(str(provenance["observed_updated_at"])),
        exact_bytes=exact,
    )
    snapshot_ref = _value_ref_from_row(snapshot_row)
    snapshot = CapturedMaterialSnapshot(
        value_ref=snapshot_ref.storage_ref,
        document_id=document_id,
        observed_text_hash=observation.text_hash,
        observed_updated_at=observation.updated_at,
        byte_size=len(exact),
    )
    material = derive_material_ref(
        source_ref=source.source_ref_id,
        snapshot=snapshot,
        owner_id=source.owner_id,
        locator=source.locator,
        observed_at=source.observed_at.isoformat(),
    )
    material_ref = _value_ref_from_row(rows[material.material_ref_id])
    material_object_ref = ResearchObjectRef(
        object_id=material.material_ref_id,
        object_type=MATERIAL_REF_TYPE,
        project_key=PROJECT_KEY,
        revision=1,
        incarnation=f"capture:{suffix}:object:{material.material_ref_id}",
        owner_binding_ref="CapturedMaterialSnapshot",
        content_ref=material_ref.storage_ref,
        content_digest=material_ref.content_digest,
        provenance_closure_digest=material_ref.provenance_digest,
        lifecycle_state="ADMITTED",
    )
    return RuntimeCapture(
        source_ref=source,
        observation=observation,
        snapshot=snapshot,
        snapshot_value_ref=snapshot_ref,
        source_value_ref=_value_ref_from_row(source_row),
        material=material,
        material_value_ref=material_ref,
        material_object_ref=material_object_ref,
    )


@dataclass(frozen=True, slots=True)
class LiveResearchRuntimeDatabase:
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

    def capture_documents(
        self,
        *,
        suffix: str = "1",
        submission_id: str | None = None,
        document_port: Callable[[RuntimeUnitOfWork], object] | None = None,
    ) -> tuple[RuntimeCapture, RuntimeCapture]:
        snapshot_ids = tuple(
            f"capture:{suffix}:snapshot:{label}" for label in ("a", "b")
        )
        with RuntimeUnitOfWork(engine=self.engine) as uow:
            table = self.project_tables.successor_values
            existing = tuple(
                uow.connection.execute(
                    sa.select(table).where(
                        table.c.project_key == PROJECT_KEY,
                        table.c.value_id.in_(snapshot_ids),
                    )
                ).mappings()
            )
            if existing:
                if len(existing) != 2:
                    raise AssertionError("partial document capture closure")
                all_ids = (*snapshot_ids, *(source_ref(item).source_ref_id for item in (101, 102)))
                rows = {
                    str(row["value_id"]): row
                    for row in uow.connection.execute(
                        sa.select(table).where(
                            table.c.project_key == PROJECT_KEY,
                            sa.or_(
                                table.c.value_id.in_(all_ids),
                                table.c.object_type == MATERIAL_REF_TYPE.type_id,
                            ),
                        )
                    ).mappings()
                }
                return tuple(
                    _capture_from_rows(
                        rows, suffix=suffix, label=label, document_id=document_id
                    )
                    for label, document_id in zip(("a", "b"), (101, 102), strict=True)
                )

            documents = (
                document_port(uow)
                if document_port is not None
                else PostgresLegacyDocumentCanonicalReadAdapter(uow.connection)
            )
            values = ValueRepository(uow.connection, self.project_tables)
            ledger = ResearchLedgerRepository(uow.connection, self.project_tables)
            captures: list[RuntimeCapture] = []
            for label, document_id in zip(("a", "b"), (101, 102), strict=True):
                source = source_ref(document_id)
                observation = documents.read_document(self.scope, document_id)
                snapshot_provenance = {
                    (
                        "submission_id" if submission_id is not None else "capture_id"
                    ): submission_id or f"capture:{suffix}",
                    "document_id": document_id,
                    "source_ref": source.source_ref_id,
                    "observed_text_hash": observation.text_hash,
                    "observed_updated_at": observation.updated_at.isoformat(),
                }
                snapshot_id = f"capture:{suffix}:snapshot:{label}"
                snapshot_ref = _value_ref(
                    value_id=snapshot_id,
                    object_type=CAPTURED_MATERIAL_SNAPSHOT_TYPE,
                    exact=observation.exact_bytes,
                    provenance=snapshot_provenance,
                )
                values.put_exact(
                    self.scope,
                    value_id=snapshot_id,
                    object_type=snapshot_ref.object_type.type_id,
                    codec_id=snapshot_ref.codec_id,
                    content=observation.exact_bytes,
                    expected_digest=snapshot_ref.content_digest,
                    provenance_digest=snapshot_ref.provenance_digest,
                    expected_revision=0,
                    expected_incarnation=(
                        f"p0c:{submission_id}:{snapshot_id}"
                        if submission_id is not None
                        else f"capture:{suffix}:{snapshot_id}"
                    ),
                    source_ref=source.source_ref_id,
                    provenance=snapshot_provenance,
                )
                snapshot = CapturedMaterialSnapshot(
                    value_ref=snapshot_ref.storage_ref,
                    document_id=document_id,
                    observed_text_hash=observation.text_hash,
                    observed_updated_at=observation.updated_at,
                    byte_size=len(observation.exact_bytes),
                )
                material = derive_material_ref(
                    source_ref=source.source_ref_id,
                    snapshot=snapshot,
                    owner_id=source.owner_id,
                    locator=source.locator,
                    observed_at=source.observed_at.isoformat(),
                )
                source_exact = canonical_bytes(source)
                source_provenance = {
                    (
                        "submission_id" if submission_id is not None else "capture_id"
                    ): submission_id or f"capture:{suffix}",
                    "document_id": document_id,
                    "owner_id": source.owner_id,
                }
                source_value = _value_ref(
                    value_id=source.source_ref_id,
                    object_type=SOURCE_REF_TYPE,
                    exact=source_exact,
                    provenance=source_provenance,
                )
                material_exact = canonical_bytes(material)
                material_provenance = {
                    (
                        "submission_id" if submission_id is not None else "capture_id"
                    ): submission_id or f"capture:{suffix}",
                    "source_ref": source.source_ref_id,
                    "snapshot_value_ref": snapshot.value_ref,
                    "snapshot_digest": snapshot_ref.content_digest,
                }
                material_value = _value_ref(
                    value_id=material.material_ref_id,
                    object_type=MATERIAL_REF_TYPE,
                    exact=material_exact,
                    provenance=material_provenance,
                )
                for ref, exact, provenance in (
                    (source_value, source_exact, source_provenance),
                    (material_value, material_exact, material_provenance),
                ):
                    values.put_exact(
                        self.scope,
                        value_id=ref.value_id,
                        object_type=ref.object_type.type_id,
                        codec_id=ref.codec_id,
                        content=exact,
                        expected_digest=ref.content_digest,
                        provenance_digest=ref.provenance_digest,
                        expected_revision=0,
                        expected_incarnation=(
                            f"p0c:{submission_id}:{ref.value_id}"
                            if submission_id is not None
                            else f"capture:{suffix}:{ref.value_id}"
                        ),
                        source_ref=source.source_ref_id,
                        provenance=provenance,
                    )
                material_object = ResearchObjectRef(
                    object_id=material.material_ref_id,
                    object_type=MATERIAL_REF_TYPE,
                    project_key=PROJECT_KEY,
                    revision=1,
                    incarnation=f"capture:{suffix}:object:{material.material_ref_id}",
                    owner_binding_ref="CapturedMaterialSnapshot",
                    content_ref=material_value.storage_ref,
                    content_digest=material_value.content_digest,
                    provenance_closure_digest=material_value.provenance_digest,
                    lifecycle_state="ADMITTED",
                )
                ledger.put_object(
                    self.scope,
                    material_object,
                    expected_revision=0,
                    expected_incarnation=material_object.incarnation,
                )
                captures.append(
                    RuntimeCapture(
                        source_ref=source,
                        observation=observation,
                        snapshot=snapshot,
                        snapshot_value_ref=snapshot_ref,
                        source_value_ref=source_value,
                        material=material,
                        material_value_ref=material_value,
                        material_object_ref=material_object,
                    )
                )
            uow.commit()
            return captures[0], captures[1]


def source_ref(document_id: int) -> SourceRef:
    return SourceRef(
        source_ref_id=f"source:document:{document_id}",
        owner_id="legacy_document_store",
        locator=f"document://{PROJECT_KEY}/{document_id}",
        source_class="existing_project_document",
        observed_at=NOW,
        access_profile_ref="DocumentCanonicalReadPort",
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


def _reset_database(database: LiveResearchRuntimeDatabase) -> None:
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

        connection.execute(sa.insert(LEGACY_DOCUMENTS), frozen_document_rows())
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
def live_research_runtime_database() -> Iterator[LiveResearchRuntimeDatabase]:
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
    database = LiveResearchRuntimeDatabase(
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
def research_runtime_database(live_research_runtime_database: LiveResearchRuntimeDatabase) -> LiveResearchRuntimeDatabase:
    _reset_database(live_research_runtime_database)
    return live_research_runtime_database


__all__ = [
    "CLAIM_POLICY_DIGEST",
    "DATABASE_ENV",
    "DELIVERY_AUTHORITY_DIGEST",
    "DEPLOYMENT_CATALOG_DIGEST",
    "LEGACY_DOCUMENTS",
    "LiveResearchRuntimeDatabase",
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
    "SUBMISSION_AUTHORITY_DIGEST",
    "frozen_document_rows",
    "live_research_runtime_database",
    "research_runtime_database",
    "source_ref",
]
