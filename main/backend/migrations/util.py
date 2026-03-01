"""Shared migration utilities for idempotent upgrades."""

import sqlalchemy as sa


def table_exists(conn, name: str, schema: str = "public") -> bool:
    """Check if a table exists in the given schema."""
    r = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :name LIMIT 1"
        ),
        {"schema": schema, "name": name},
    ).fetchone()
    return r is not None
