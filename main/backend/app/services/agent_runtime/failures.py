from __future__ import annotations

from typing import Any

from functorial_kit import Failure
from mrw_functorial_kit.core.agent_service_semantics import agent_runtime_failures


def runtime_failure(
    code: str,
    message: str,
    context: dict[str, Any] | None = None,
) -> Failure:
    """Construct the closed failure shared by current agent-runtime services."""

    return agent_runtime_failures.fail(code, message, context)
