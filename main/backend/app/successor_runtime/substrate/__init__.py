"""Durable substrate contracts for the successor runtime."""

from .postgres import (
    PROJECT_TABLE_NAMES,
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    ProjectTables,
    project_tables,
)

__all__ = [
    "PROJECT_TABLE_NAMES",
    "PUBLIC_METADATA",
    "PUBLIC_TABLES",
    "ProjectTables",
    "project_tables",
]
