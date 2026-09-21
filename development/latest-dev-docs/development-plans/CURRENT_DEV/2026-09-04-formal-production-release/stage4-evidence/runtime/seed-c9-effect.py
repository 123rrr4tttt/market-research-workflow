"""Seed only the task-local C9 projection source and authority prerequisites.

Run inside the final Stage 4 backend image after the task-local database has
been initialized.  No credential or HTTP request body is written by this
script; the actor is derived from the injected bearer at runtime.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import types

import sqlalchemy as sa


class _Mark:
    def __getattr__(self, _name):
        return lambda function: function


sys.modules["pytest"] = types.SimpleNamespace(
    mark=_Mark(),
    fixture=lambda *args, **kwargs: (lambda function: function),
    skip=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("skip")),
)

from sqlalchemy import MetaData, delete, text  # noqa: E402

from app.models.base import engine  # noqa: E402
from app.services.request_identity import actor_id_from_secret  # noqa: E402
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope  # noqa: E402
from app.successor_runtime.substrate.postgres.models import (  # noqa: E402
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest  # noqa: E402
from tests.successor_runtime import test_c9_movement_closure_backend_postgres as c9  # noqa: E402


PROJECT_KEY = "stage4_s4_20260913"
PROJECT_SCHEMA = "project_stage4_s4_20260913"
INCARNATION = "incarnation:stage4-c9-effect:v1"
REGISTRY_REVISION = 1
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY, PROJECT_SCHEMA, REGISTRY_REVISION, INCARNATION
)
ACTOR = actor_id_from_secret("codex_auth_token", os.environ["CODEX_AUTH_TOKENS"])

c9.PROJECT_KEY = PROJECT_KEY
c9.PROJECT_SCHEMA = PROJECT_SCHEMA
c9.SCOPE_INCARNATION = INCARNATION
c9.SCOPE_DIGEST = SCOPE_DIGEST
c9.SOURCE_REF = f"project:{PROJECT_KEY}:semantic-sources"
c9.RUN_ID = "run:stage4:c9"
c9.PROGRAM_ID = "program:stage4:c9"
c9.GRANT_ID = "grant:stage4:c9"
c9.APPROVAL_ID = "approval:stage4:c9"
c9.NOW = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)
c9.ACTOR = ACTOR
c9.SCOPE = RuntimeScope(
    ProjectScopeRef(
        PROJECT_KEY,
        PROJECT_SCHEMA,
        REGISTRY_REVISION,
        INCARNATION,
        SCOPE_DIGEST,
    ),
    ACTOR,
)
c9.SOURCE_IDENTITY = {
    "projector_id": c9.PROJECTOR_ID,
    "projector_version": c9.PROJECTOR_VERSION,
    "source_kind": "successor_values",
    "source_ref": c9.SOURCE_REF,
    "source_incarnation": INCARNATION,
}

with engine.begin() as connection:
    for table in (
        PUBLIC_TABLES["runtime_projection_offsets"],
        PUBLIC_TABLES["runtime_idempotency"],
        PUBLIC_TABLES["runtime_authority_grants"],
        PUBLIC_TABLES["runtime_approvals"],
        PUBLIC_TABLES["runtime_step_authorizations"],
        PUBLIC_TABLES["runtime_capability_authority"],
        PUBLIC_TABLES["runtime_events"],
        PUBLIC_TABLES["runtime_steps"],
        PUBLIC_TABLES["runtime_runs"],
        PUBLIC_TABLES["runtime_program_refs"],
        PUBLIC_TABLES["project_scope_registry"],
        c9.C7_MOVEMENT_CANONICAL_DOCUMENTS,
    ):
        connection.execute(delete(table).where(table.c.project_key == PROJECT_KEY))
    connection.execute(text(f'DROP SCHEMA IF EXISTS "{PROJECT_SCHEMA}" CASCADE'))
    connection.execute(text(f'CREATE SCHEMA "{PROJECT_SCHEMA}"'))
    project = project_tables(MetaData(schema=PROJECT_SCHEMA), PROJECT_SCHEMA)
    project.research_objects.metadata.create_all(connection)
    c9.C7_MOVEMENT_CANONICAL_DOCUMENTS.create(connection, checkfirst=True)
    c9._seed_authority(connection)
    source_digest, source_revision = c9._seed_sources(
        connection, project, source_ref=c9.SOURCE_REF
    )
    c9._initialize_offset(
        connection,
        project,
        source_digest,
        source_ref=c9.SOURCE_REF,
    )
    effect_command = c9._command(
        command_id="cmd:stage4:c9:rebuild",
        actor_ref=ACTOR,
        approval_locator="approval:stage4:c9:effect",
        expected_base_token=(
            f"generation:0|revision:0|incarnation:{INCARNATION}"
        ),
    )
    c9._seed_exact_effect_authority(
        connection,
        effect_command,
        approval_id="approval:stage4:c9:effect",
        step_id="step:stage4:c9:rebuild",
    )

print(
    json.dumps(
        {
            "project_key": PROJECT_KEY,
            "resolved_schema": PROJECT_SCHEMA,
            "scope_digest": SCOPE_DIGEST,
            "source_ref": c9.SOURCE_REF,
            "source_revision": source_revision,
            "source_digest": source_digest,
            "effect_command_id": effect_command.command_id,
            "effect_approval_id": effect_command.approval_locator,
            "effect_request_digest": effect_command.idempotency_key,
            "actor_derived": True,
            "credentials_persisted": False,
        },
        sort_keys=True,
    )
)
