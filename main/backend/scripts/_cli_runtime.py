"""Backend CLI access to the repository-wide automation helpers."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from scripts._automation_runtime import repo_root  # noqa: E402


T = TypeVar("T")


def initialize_database_cli(
    *,
    project_key: str | None = None,
    name: str | None = None,
) -> dict[str, str]:
    """Run the fail-closed project-schema preflight for a DB-using CLI."""
    from app.services.projects.schema_initialization import initialize_cli_project_schema

    return initialize_cli_project_schema(project_key=project_key, name=name)


def run_database_cli(
    command: Callable[[], T],
    *,
    project_key: str | None = None,
    name: str | None = None,
) -> T:
    """Initialize schema before invoking a database-using CLI command."""
    initialize_database_cli(project_key=project_key, name=name)
    return command()


__all__ = ["initialize_database_cli", "repo_root", "run_database_cli"]
