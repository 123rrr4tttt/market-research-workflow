"""Real-postgres registry-backed projection read probe (Projection Read Lane).

Reads only.  It opens one PostgreSQL transaction in READ ONLY mode, resolves
the ACTIVE project scope from the public project-scope registry and drives the
repository-owned ``C7ProjectorDriver.read_document`` path to read the committed
canonical C7 acceptance document back from the real database.

No row is written, no migration is executed, no legacy table is touched and no
secret is printed.  Output is a minimal JSON report for the lane evidence.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from sqlalchemy import text

from app.settings.config import settings
from app.successor_runtime.substrate.postgres.c7_production_admission import (
    resolve_active_scope,
)
from app.successor_runtime.substrate.postgres.c7_projector_driver import (
    C7ProjectorDriver,
)
from app.successor_runtime.substrate.postgres.session import create_runtime_engine


PROJECT_KEY = "demo_proj_compare_0303_121137"
OBJECT_ID = "ingest-doc:c7-production-cutover-acceptance-2026-09-03"
ACTOR_ID = "actor:projection-read-supervisor"
EXPECTED_CONTENT_DIGEST = (
    "d2495d61135d7e2436a97b4da2b2d64b04767f25881eeb65e2d7a1a018310337"
)
EXPECTED_REVISION = 1
PROJECT_SCHEMA = "project_demo_proj_compare_0303_121137"


def _scalar_int(
    connection: sa.engine.Connection,
    statement: str,
    params: dict[str, str] | None = None,
) -> int:
    return int(
        connection.execute(text(statement), params or {}).scalar_one()
    )


def main() -> None:
    engine = create_runtime_engine(settings.database_url)
    report: dict[str, object] = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            read_only_setting = str(
                connection.execute(
                    text("SELECT current_setting('transaction_read_only')")
                ).scalar_one()
            )

            scope = resolve_active_scope(
                connection,
                project_key=PROJECT_KEY,
                actor_id=ACTOR_ID,
            )

            canonical_filtered_rows = _scalar_int(
                connection,
                "SELECT count(*) FROM public.c7_movement_canonical_documents "
                "WHERE project_key = :project_key AND object_id = :object_id",
                {"project_key": PROJECT_KEY, "object_id": OBJECT_ID},
            )
            registry_active_rows = _scalar_int(
                connection,
                "SELECT count(*) FROM public.project_scope_registry "
                "WHERE project_key = :project_key AND state = 'ACTIVE'",
                {"project_key": PROJECT_KEY},
            )

            driver = C7ProjectorDriver(connection, scope)
            document_ref = driver.read_document(OBJECT_ID)

            digest_matches = (
                document_ref.content_digest == EXPECTED_CONTENT_DIGEST
            )
            revision_matches = document_ref.revision == EXPECTED_REVISION

            report.update(
                {
                    "status": "PASS_PROJECTION_READ_REAL_DB",
                    "probe": "mrw.all-lines.projection-read.probe.v1",
                    "path_selected": (
                        "repository-owned C7ProjectorDriver.read_document over "
                        "public.c7_movement_canonical_documents (C7.3 search/graph "
                        "projection source read)"
                    ),
                    "transaction_read_only": read_only_setting == "on",
                    "project_key": PROJECT_KEY,
                    "resolved_schema": scope.project_scope.resolved_schema,
                    "registry_revision": scope.project_scope.project_registry_revision,
                    "registry_incarnation": scope.project_scope.incarnation,
                    "scope_digest": scope.project_scope.scope_digest,
                    "object_refs": [
                        {
                            "object_id": document_ref.object_id,
                            "revision": document_ref.revision,
                            "incarnation": document_ref.incarnation,
                            "content_digest": document_ref.content_digest,
                            "canonical_owner": document_ref.canonical_owner,
                        }
                    ],
                    "rows_read": {
                        "c7_movement_canonical_documents_filtered": (
                            canonical_filtered_rows
                        ),
                        "project_scope_registry_active": registry_active_rows,
                    },
                    "digest_assert": {
                        "expected": EXPECTED_CONTENT_DIGEST,
                        "observed": document_ref.content_digest,
                        "match": digest_matches,
                    },
                    "revision_assert": {
                        "expected": EXPECTED_REVISION,
                        "observed": document_ref.revision,
                        "match": revision_matches,
                    },
                    "read_only_verified": read_only_setting == "on"
                    and canonical_filtered_rows >= 1
                    and digest_matches
                    and revision_matches,
                    "exit_code": 0,
                }
            )
    except Exception as exc:  # noqa: BLE001
        report["status"] = "BLOCK_PROJECTION_READ_REAL_DB"
        report["error_class"] = type(exc).__name__
        report["error_condensed"] = str(exc)[:500]
        report["exit_code"] = 1
    finally:
        engine.dispose()

    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
