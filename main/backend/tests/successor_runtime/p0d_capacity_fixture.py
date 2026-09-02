"""Dedicated local PostgreSQL fixture for the P0-D capacity envelope.

The fixture never adopts existing tables, schemas, or roles.  When the local
test connection is a superuser it creates one exact, temporary non-superuser
measurement role and removes only that role during teardown.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_runtime.substrate.postgres.capacity import (
    CapacityEnvironmentGuard,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
)
from app.successor_runtime.substrate.postgres.session import create_runtime_engine

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
CAPACITY_ROLE = "mrw_p0d_capacity_runner"
PROJECT_PREFIX = "p0d-capacity-"
SCHEMA_PREFIX = "mrw_p0d_capacity_"
NODE_PREFIX = "p0d-capacity-node-"
CATALOG_REF_PREFIX = "p0d-capacity://"
PROJECTS = ("p0d-capacity-project-a", "p0d-capacity-project-b")
PROJECT_SCHEMAS = ("mrw_p0d_capacity_a", "mrw_p0d_capacity_b")
NODE_IDS = ("p0d-capacity-node-a", "p0d-capacity-node-b")
CAPABILITIES = (
    "p0d-capacity-compile",
    "p0d-capacity-compile-alternate",
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


NODE_PROFILE_DIGEST = _digest("p0d-capacity-node-profile")
CATALOG_DIGEST = _digest("p0d-capacity-catalog")
SECURITY_PROFILE_DIGEST = _digest("p0d-capacity-security-profile")
RESOURCE_PROFILE_DIGEST = _digest("p0d-capacity-resource-profile")
AUTHORITY_DIGEST = _digest("p0d-capacity-authority")
CLAIM_POLICY_DIGEST = _digest("p0d-capacity-claim-policy")
RESOURCE_POLICY_DIGEST = _digest("p0d-capacity-resource-policy")
HANDLER_DIGEST = _digest("p0d-capacity-compiler-handler")


@dataclass(frozen=True, slots=True)
class P0DCapacityDatabase:
    engine: Engine
    guard: CapacityEnvironmentGuard
    database_url: str


def _require_local_test_url() -> str:
    database_url = os.environ.get(DATABASE_ENV)
    if not database_url:
        pytest.skip(f"{DATABASE_ENV} is not set")
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        pytest.fail(f"{DATABASE_ENV} must use PostgreSQL")
    database_name = url.database or ""
    if database_name in {"postgres", "template0", "template1"} or not re.search(
        r"(?:test|testing|ci)", database_name, re.IGNORECASE
    ):
        pytest.fail(f"refusing non-test database {database_name!r}")
    if url.host not in (None, ""):
        pytest.fail("P0-D capacity fixture forbids TCP PostgreSQL URLs")
    return database_url


def _seed_capacity_rows(engine: Engine) -> None:
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_deployment_catalogs"]).values(
                catalog_digest=CATALOG_DIGEST,
                catalog_version="p0d-capacity-v1",
                catalog_ref="p0d-capacity://deployment-catalog/v1",
                node_profile_digest=NODE_PROFILE_DIGEST,
                security_profile_digest=SECURITY_PROFILE_DIGEST,
                resource_profile_digest=RESOURCE_PROFILE_DIGEST,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_nodes"]),
            [
                {
                    "node_id": node_id,
                    "node_profile_digest": NODE_PROFILE_DIGEST,
                    "deployment_catalog_digest": CATALOG_DIGEST,
                    "runtime_protocol_version": "1",
                    "state": "ACTIVE",
                    "heartbeat_at": now,
                    "started_at": now,
                    "current_claim_count": 0,
                    "revision": 0,
                }
                for node_id in NODE_IDS
            ],
        )

        for ordinal, (project_key, project_schema) in enumerate(
            zip(PROJECTS, PROJECT_SCHEMAS, strict=True),
            start=1,
        ):
            scope_digest = _digest(f"scope:{project_key}")
            program_id = f"p0d-capacity-program-{ordinal}"
            program_digest = _digest(f"program:{project_key}")
            connection.execute(
                sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
                    project_key=project_key,
                    registry_revision=1,
                    resolved_schema=project_schema,
                    scope_digest=scope_digest,
                    incarnation=f"p0d-capacity-incarnation-{ordinal}",
                    state="ACTIVE",
                    updated_by="p0d-capacity-fixture",
                    approval_ref="approval:p0d-capacity-local-only",
                )
            )
            connection.execute(
                sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
                    program_id=program_id,
                    project_key=project_key,
                    program_digest=program_digest,
                    project_storage_ref=(
                        f"{project_schema}.research_program_specs:{program_id}"
                    ),
                    contract_version="1.0.0",
                )
            )
            for row_ordinal in range(6):
                run_id = f"p0d-capacity-run-{ordinal}-{row_ordinal}"
                connection.execute(
                    sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
                        run_id=run_id,
                        project_key=project_key,
                        project_registry_revision=1,
                        project_scope_digest=scope_digest,
                        resolved_schema=project_schema,
                        program_id=program_id,
                        program_digest=program_digest,
                        state="SUBMITTED",
                        revision=0,
                        next_event_seq=1,
                        execution_epoch=0,
                        incarnation=f"p0d-capacity-run-inc-{ordinal}-{row_ordinal}",
                        submission_authority_digest=AUTHORITY_DIGEST,
                        cancellation_requested=False,
                    )
                )
                terminal = row_ordinal >= 4
                work_item_id = f"p0d-capacity-work-{ordinal}-{row_ordinal}"
                assignment_digest = _digest(f"assignment:{work_item_id}")
                connection.execute(
                    sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(
                        work_item_id=work_item_id,
                        project_key=project_key,
                        run_id=run_id,
                        step_id=None,
                        assignment_kind="COMPILE",
                        capability_id=CAPABILITIES[row_ordinal % len(CAPABILITIES)],
                        assignment_digest=assignment_digest,
                        assignment_binding_json={
                            "fixture": "p0d-capacity",
                            "assignment_digest": assignment_digest,
                        },
                        execution_epoch=0,
                        assignment_incarnation=(
                            f"p0d-capacity-assignment-inc-{ordinal}-{row_ordinal}"
                        ),
                        claim_authority_epoch=1,
                        claim_policy_digest=CLAIM_POLICY_DIGEST,
                        handler_binding_kind="COMPILER",
                        handler_binding_ref=(
                            f"handler-binding:sha256:{HANDLER_DIGEST}"
                        ),
                        handler_binding_digest=HANDLER_DIGEST,
                        deployment_catalog_digest=CATALOG_DIGEST,
                        runtime_protocol_version="1",
                        required_node_profile_selector=NODE_PROFILE_DIGEST,
                        program_digest=program_digest,
                        authority_digest=AUTHORITY_DIGEST,
                        resource_policy_digest=RESOURCE_POLICY_DIGEST,
                        fairness_key=project_key,
                        state="COMPLETED" if terminal else "READY",
                        wait_reason=None,
                        declared_priority=row_ordinal,
                        enqueued_at=now - timedelta(seconds=20 + row_ordinal),
                        due_at=now - timedelta(seconds=5),
                        deadline_at=now + timedelta(minutes=10),
                        attempt_count=0,
                        revision=0,
                    )
                )


@pytest.fixture(scope="module")
def p0d_capacity_database() -> Iterator[P0DCapacityDatabase]:
    admin_url = _require_local_test_url()
    admin_engine = create_runtime_engine(admin_url, poolclass=NullPool)
    url = make_url(admin_url)
    database_name = url.database or ""
    inspector = sa.inspect(admin_engine)
    existing_public = set(inspector.get_table_names(schema="public"))
    if existing_public:
        admin_engine.dispose()
        pytest.fail(
            "capacity fixture refuses existing public tables: "
            f"{sorted(existing_public)}"
        )
    conflicting = set(PROJECT_SCHEMAS) & set(inspector.get_schema_names())
    if conflicting:
        admin_engine.dispose()
        pytest.fail(f"capacity fixture refuses existing schemas: {sorted(conflicting)}")

    with admin_engine.connect() as connection:
        admin = (
            connection.execute(
                sa.text(
                    "SELECT current_user AS role, rolsuper "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
            .mappings()
            .one()
        )
    created_role = bool(admin["rolsuper"])
    measurement_role = CAPACITY_ROLE if created_role else str(admin["role"])
    if created_role:
        with admin_engine.begin() as connection:
            exists = connection.execute(
                sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
                {"role": CAPACITY_ROLE},
            ).first()
            if exists is not None:
                pytest.fail(f"capacity fixture refuses existing role {CAPACITY_ROLE!r}")
            connection.execute(
                sa.text(
                    f'CREATE ROLE "{CAPACITY_ROLE}" LOGIN NOSUPERUSER '
                    "NOCREATEDB NOCREATEROLE NOINHERIT"
                )
            )

    measurement_engine: Engine | None = None
    try:
        with admin_engine.begin() as connection:
            for schema in PROJECT_SCHEMAS:
                connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
            PUBLIC_METADATA.create_all(connection, checkfirst=False)
        _seed_capacity_rows(admin_engine)
        if created_role:
            with admin_engine.begin() as connection:
                connection.execute(
                    sa.text(
                        f'GRANT CONNECT ON DATABASE "{database_name}" TO "{CAPACITY_ROLE}"'
                    )
                )
                connection.execute(
                    sa.text(f'GRANT USAGE ON SCHEMA public TO "{CAPACITY_ROLE}"')
                )
                connection.execute(
                    sa.text(
                        f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{CAPACITY_ROLE}"'
                    )
                )
                # PostgreSQL requires UPDATE privilege for SELECT ... FOR UPDATE.
                # The role exists only in this empty fixture database and the
                # observer still executes no DML; teardown removes the grant.
                connection.execute(
                    sa.text(
                        f'GRANT UPDATE ON TABLE public.runtime_work_items TO "{CAPACITY_ROLE}"'
                    )
                )
        measurement_url = url.set(username=measurement_role, password=None)
        measurement_engine = create_runtime_engine(
            measurement_url.render_as_string(hide_password=False),
            poolclass=NullPool,
        )
        guard = CapacityEnvironmentGuard(
            expected_database_name=database_name,
            expected_role=measurement_role,
            allowed_project_prefix=PROJECT_PREFIX,
            allowed_schema_prefix=SCHEMA_PREFIX,
            allowed_node_prefix=NODE_PREFIX,
            allowed_catalog_ref_prefix=CATALOG_REF_PREFIX,
        )
        yield P0DCapacityDatabase(
            engine=measurement_engine,
            guard=guard,
            database_url=measurement_url.render_as_string(hide_password=False),
        )
    finally:
        if measurement_engine is not None:
            measurement_engine.dispose()
        with admin_engine.begin() as connection:
            PUBLIC_METADATA.drop_all(connection, checkfirst=True)
            for schema in PROJECT_SCHEMAS:
                connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            if created_role:
                connection.execute(sa.text(f'DROP OWNED BY "{CAPACITY_ROLE}"'))
                connection.execute(sa.text(f'DROP ROLE "{CAPACITY_ROLE}"'))
        admin_engine.dispose()


__all__ = [
    "CAPABILITIES",
    "CAPACITY_ROLE",
    "DATABASE_ENV",
    "NODE_IDS",
    "NODE_PROFILE_DIGEST",
    "P0DCapacityDatabase",
    "p0d_capacity_database",
]
