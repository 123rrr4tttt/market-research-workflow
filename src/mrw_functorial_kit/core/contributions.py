"""Project-visible declaration for the kit contribution failure family."""

from __future__ import annotations

from functorial_kit.core.failure import define_failure_family

contribution_failures = define_failure_family(
    "kit.contribution",
    ("CONTRIBUTION_INVALID",),
)

__all__ = ["contribution_failures"]
