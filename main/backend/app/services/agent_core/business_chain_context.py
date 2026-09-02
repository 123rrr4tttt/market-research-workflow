"""Read-only business-chain context for the agent core model prompt.

The agent core decides whether to answer or call project tools.  When the
provider is the local Codex CLI wrapper, the prompt benefits from a small,
read-only snapshot of the MRW business-chain data that the tools operate on:
active project scope registry rows, committed C7 canonical documents and
journal/runtime progress, plus legacy top-level tables.  Every read is best
effort and fail-closed: a missing table, DB outage or import error surfaces an
``unavailable`` marker instead of breaking the turn or leaking internals.
No secret values are ever read.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import text

_SNAPSHOT_SCHEMA = "mrw.successor.agent-core.business-chain-snapshot.v1"
_logger = logging.getLogger(__name__)

_PUBLIC_TABLE_COUNTS = (
    "projects",
    "agent_sessions",
    "ingest_submission_registry",
    "project_scope_registry",
    "c7_movement_canonical_documents",
    "runtime_runs",
    "runtime_steps",
    "runtime_effect_attempts",
    "runtime_events",
)


def _registry_summary() -> dict[str, Any]:
    """Deterministic successor surface/port registry summary (no DB access)."""

    try:
        from app.successor_runtime.assembly.s1_horizontal_port_assembly import (
            build_s1_horizontal_port_registry,
            s1_horizontal_port_registry_digest,
        )
        from app.successor_runtime.assembly.s2c_ops_domain_surface_assembly import (
            build_s2c_ops_domain_surface_registry,
            s2c_ops_domain_surface_registry_digest,
        )

        s1 = build_s1_horizontal_port_registry()
        s2c = build_s2c_ops_domain_surface_registry()
        return {
            "available": True,
            "s1_port_ids": [item.port_id for item in s1],
            "s1_registry_digest": s1_horizontal_port_registry_digest(s1),
            "s2c_surface_ids": [item.surface_id for item in s2c],
            "s2c_registry_digest": s2c_ops_domain_surface_registry_digest(s2c),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "error": f"{exc.__class__.__name__}: {str(exc)[:200]}",
        }


def _safe_count(connection: Any, table_name: str) -> dict[str, Any]:
    """Return row count when the table exists; fail closed otherwise."""

    table = str(table_name or "").strip()
    if not table:
        return {"table": table, "rows": None, "available": False}
    exists = connection.execute(
        text("SELECT to_regclass(:qualified)"),
        {"qualified": f"public.{table}"},
    ).scalar()
    if not exists:
        return {"table": table, "rows": None, "available": False}
    rows = connection.execute(text(f'SELECT count(*) FROM "public"."{table}"')).scalar()
    return {"table": table, "rows": int(rows or 0), "available": True}


def _active_registry_rows(connection: Any) -> list[dict[str, Any]]:
    """ACTIVE project scope registry rows (identity fields only)."""

    exists = connection.execute(
        text("SELECT to_regclass('public.project_scope_registry')")
    ).scalar()
    if not exists:
        return []
    rows = (
        connection.execute(
            text(
                "SELECT project_key, resolved_schema, registry_revision, "
                "incarnation FROM public.project_scope_registry "
                "WHERE state = 'ACTIVE' ORDER BY project_key"
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def build_business_chain_snapshot(
    *,
    session_factory: Callable[[], Any] | None = None,
    project_key: str | None = None,
) -> dict[str, Any]:
    """Build a bounded read-only business-chain snapshot for the agent prompt.

    ``session_factory`` is injectable for tests; by default the standard
    database session is opened lazily.  Any read error is captured per surface
    and never raises.
    """

    snapshot: dict[str, Any] = {
        "schema": _SNAPSHOT_SCHEMA,
        "project_key": project_key,
        "registry": _registry_summary(),
        "database": None,
        "available": False,
    }
    if session_factory is None:
        try:
            from app.models.base import SessionLocal

            session_factory = SessionLocal
        except Exception as exc:  # noqa: BLE001
            snapshot["database"] = {
                "available": False,
                "error": f"{exc.__class__.__name__}: {str(exc)[:200]}",
            }
            return snapshot

    session = session_factory()
    try:
        connection = session.connection()
        counts = [_safe_count(connection, name) for name in _PUBLIC_TABLE_COUNTS]
        snapshot["database"] = {
            "available": True,
            "table_counts": counts,
            "active_registry_rows": _active_registry_rows(connection),
        }
        snapshot["available"] = True
        return snapshot
    except Exception as exc:  # noqa: BLE001
        snapshot["database"] = {
            "available": False,
            "error": f"{exc.__class__.__name__}: {str(exc)[:200]}",
        }
        return snapshot
    finally:
        try:
            session.close()
        except Exception as exc:  # noqa: BLE001
            _logger.debug("business-chain snapshot session close failed: %s", exc)


def business_chain_snapshot_json(
    *,
    session_factory: Callable[[], Any] | None = None,
    project_key: str | None = None,
    max_chars: int = 6000,
) -> str:
    """Compact JSON text for the model prompt (bounded, no secrets)."""

    snapshot = build_business_chain_snapshot(
        session_factory=session_factory,
        project_key=project_key,
    )
    prefix = (
        "Business-chain read-only snapshot (registry/project/canonical/runtime "
        "row-level state; use it to answer project inventory questions and to "
        "choose project read tools; it never contains secrets):\n"
    )
    json_text = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    budget = max(0, int(max_chars) - len(prefix))
    if len(json_text) > budget:
        json_text = json_text[:budget] + "..."
    return prefix + json_text
