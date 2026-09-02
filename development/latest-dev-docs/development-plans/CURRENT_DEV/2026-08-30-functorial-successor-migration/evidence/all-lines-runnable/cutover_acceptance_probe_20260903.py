"""Bounded real-postgres cutover acceptance probe for the C7 canonical chain.

Reads only.  It does not seed runtime rows, create tables, or write any row.
It exercises the real successor program path far enough to establish whether
the production canonical-write chain is runnable, then records the exact
failure class and the observable schema/runtime precondition state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import text

sys.path.insert(
    0,
    "/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0/main/backend",
)


PROJECT_KEY = "demo_proj_compare_0303_121137"
RESOLVED_SCHEMA = "project_demo_proj_compare_0303_121137"
REQUIRED_CANONICAL_TABLE = "public.c7_movement_canonical_documents"


def main() -> None:
    from app.settings.config import settings
    from app.successor_runtime.substrate.postgres.session import create_runtime_engine

    report: dict[str, object] = {
        "probe": "mrw.all-lines.cutover-acceptance.probe.v1",
        "date": "2026-09-03",
        "target_database": "settings.database_url (backend .env DATABASE_URL)",
        "project_key": PROJECT_KEY,
        "resolved_schema": RESOLVED_SCHEMA,
    }
    engine = create_runtime_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            registry_rows = int(
                connection.execute(
                    text(
                        "SELECT count(*) FROM public.project_scope_registry "
                        "WHERE project_key=:k AND state='ACTIVE'"
                    ),
                    {"k": PROJECT_KEY},
                ).scalar_one()
            )
            authority_rows = int(
                connection.execute(
                    text(
                        "SELECT count(*) FROM public.runtime_capability_authority "
                        "WHERE project_key=:k"
                    ),
                    {"k": PROJECT_KEY},
                ).scalar_one()
            )
            run_rows = int(
                connection.execute(
                    text(
                        "SELECT count(*) FROM public.runtime_runs "
                        "WHERE project_key=:k"
                    ),
                    {"k": PROJECT_KEY},
                ).scalar_one()
            )
            step_rows = int(
                connection.execute(
                    text(
                        "SELECT count(*) FROM public.runtime_steps "
                        "WHERE project_key=:k"
                    ),
                    {"k": PROJECT_KEY},
                ).scalar_one()
            )
            attempt_rows = int(
                connection.execute(
                    text(
                        "SELECT count(*) FROM public.runtime_effect_attempts "
                        "WHERE project_key=:k"
                    ),
                    {"k": PROJECT_KEY},
                ).scalar_one()
            )
            event_rows = int(
                connection.execute(
                    text(
                        "SELECT count(*) FROM public.runtime_events "
                        "WHERE project_key=:k"
                    ),
                    {"k": PROJECT_KEY},
                ).scalar_one()
            )
            program_rows = int(
                connection.execute(
                    text(
                        "SELECT count(*) FROM public.runtime_program_refs "
                        "WHERE project_key=:k"
                    ),
                    {"k": PROJECT_KEY},
                ).scalar_one()
            )
            canonical_table = connection.execute(
                text(
                    "SELECT to_regclass(:t) IS NOT NULL"
                ),
                {"t": REQUIRED_CANONICAL_TABLE},
            ).scalar_one()
            report["precondition_rows"] = {
                "project_scope_registry_ACTIVE": registry_rows,
                "runtime_capability_authority": authority_rows,
                "runtime_runs": run_rows,
                "runtime_steps": step_rows,
                "runtime_effect_attempts": attempt_rows,
                "runtime_events": event_rows,
                "runtime_program_refs": program_rows,
            }
            report["required_canonical_table_exists"] = bool(canonical_table)

            legacy_projects = int(
                connection.execute(text("SELECT count(*) FROM public.projects")).scalar_one()
            )
            legacy_sessions = int(
                connection.execute(
                    text("SELECT count(*) FROM public.agent_sessions")
                ).scalar_one()
            )
            report["legacy_counts"] = {
                "projects": legacy_projects,
                "agent_sessions": legacy_sessions,
            }
    finally:
        engine.dispose()

    # Deterministic probe: attempt the real canonical-document read path that the
    # production C7 admission program touches first.  Read-only SELECT, no rows
    # written, so a missing relation fails closed exactly as the write would.
    outcome: dict[str, object] = {}
    engine2 = create_runtime_engine(settings.database_url)
    try:
        with engine2.connect() as connection:
            connection.execute(
                text("SET LOCAL statement_timeout = '10s'")
            )
            connection.execute(
                text(
                    "SELECT count(*) FROM c7_movement_canonical_documents "
                    "WHERE project_key=:k"
                ),
                {"k": PROJECT_KEY},
            )
            outcome["select_succeeded"] = True
    except sa.exc.ProgrammingError as exc:
        original = str(exc.orig)
        outcome["select_succeeded"] = False
        outcome["error_class"] = "ProgrammingError"
        outcome["missing_relation"] = "42P01" in original and "does not exist" in original
        outcome["error_contains"] = (
            "c7_movement_canonical_documents" in original
            or "does not exist" in original
        )
        outcome["error_condensed"] = original[:500]
    except Exception as exc:  # noqa: BLE001
        outcome["select_succeeded"] = False
        outcome["error_class"] = type(exc).__name__
        outcome["error_condensed"] = str(exc)[:500]
    finally:
        engine2.dispose()

    report["canonical_read_probe"] = outcome
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
