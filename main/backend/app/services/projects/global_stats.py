"""Canonical cross-project count projection for the dashboard global API."""

from __future__ import annotations

from sqlalchemy import text

from ...models.base import engine
from .context import (
    PG_IDENTIFIER_RE,
    is_allowed_project_schema,
    project_failure,
    raise_project_failure,
)


_FORBIDDEN_STORED_SCHEMAS = frozenset({"public", "aggregator"})
_GLOBAL_TABLES = ("materials", "market_metric_points", "price_observations")


def _quoted_identifier(schema_name: str) -> str:
    return '"' + schema_name.replace('"', '""') + '"'


def _validate_stored_schema(project_key: str, schema_name: object) -> str:
    schema = str(schema_name or "").strip()
    if not schema or schema in _FORBIDDEN_STORED_SCHEMAS or not is_allowed_project_schema(schema):
        raise_project_failure(project_failure(
            "schema_binding_conflict", f"project has invalid stored schema: {project_key}",
            operation="global_stats", site="projects.global_stats", public_exception="ValueError",
        ))
    if not PG_IDENTIFIER_RE.fullmatch(schema):
        raise_project_failure(project_failure(
            "schema_binding_conflict", f"project stored schema is not a PostgreSQL identifier: {project_key}",
            operation="global_stats", site="projects.global_stats", public_exception="ValueError",
        ))
    return schema


def query_global_canonical_stats() -> dict[str, int]:
    """Count three current tenant tables under one read-only snapshot."""

    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            projects = connection.execute(
                text(
                    """
                    SELECT project_key, schema_name
                    FROM public.projects
                    WHERE enabled = true
                    ORDER BY project_key
                    """
                )
            ).all()

            parts: list[str] = []
            params: dict[str, str] = {}
            for index, row in enumerate(projects):
                project_key, stored_schema = row
                schema = _validate_stored_schema(str(project_key), stored_schema)
                quoted = _quoted_identifier(schema)
                params[f"project_{index}"] = str(project_key)
                parts.extend(
                    f"SELECT :project_{index} AS project_key, '{table}' AS object_name, "
                    f"COUNT(*) AS total FROM {quoted}.{table}"
                    for table in _GLOBAL_TABLES
                )

            totals = {"materials_total": 0, "metrics_total": 0, "prices_total": 0}
            if parts:
                union_sql = "\nUNION ALL\n".join(parts)
                rows = connection.execute(text(union_sql), params).mappings().all()
                for row in rows:
                    field = {
                        "materials": "materials_total",
                        "market_metric_points": "metrics_total",
                        "price_observations": "prices_total",
                    }[str(row["object_name"])]
                    totals[field] += int(row["total"] or 0)
            return totals
