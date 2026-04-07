from __future__ import annotations

from typing import Any


def run_agent_batch_nl_command_loop(*args: Any, **kwargs: Any) -> dict[str, Any]:
    # Keep package import lightweight to avoid skill_runtime <-> agent_loop circular import during test collection.
    from .agent_loop import run_agent_batch_nl_command_loop as _run_agent_batch_nl_command_loop

    return _run_agent_batch_nl_command_loop(*args, **kwargs)


__all__ = ["run_agent_batch_nl_command_loop"]
