from __future__ import annotations

from collections import deque
from typing import Any

from .contracts import AgentCoreRequest, CoreModelStep, CoreProvider, CoreToolSpec


class FakeCoreProvider(CoreProvider):
    """Deterministic provider for contract and route tests."""

    def __init__(self, steps: list[CoreModelStep] | tuple[CoreModelStep, ...]) -> None:
        self.steps = deque(steps)
        self.calls: list[dict[str, Any]] = []

    def next_step(
        self,
        *,
        request: AgentCoreRequest,
        tools: list[CoreToolSpec],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> CoreModelStep:
        self.calls.append(
            {
                "message": request.message,
                "context": dict(request.context or {}),
                "tool_names": [tool.name for tool in tools],
                "transcript": list(transcript),
                "remaining_budget": dict(remaining_budget),
            }
        )
        if self.steps:
            return self.steps.popleft()
        return CoreModelStep.final("我已经完成本轮处理。", model_path="fake_core_provider")
