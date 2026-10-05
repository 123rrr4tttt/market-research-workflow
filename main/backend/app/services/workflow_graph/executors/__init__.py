from __future__ import annotations

from typing import Any

from .kernel import (
    NodeEffectFailure,
    NodeEffectResult,
    NodeExecutionContext,
    execute_node,
    to_workflow_graph_failure,
)

__all__ = [
    "NodeExecutionContext",
    "NodeEffectFailure",
    "NodeEffectResult",
    "execute_node",
    "to_workflow_graph_failure",
]


def __getattr__(name: str) -> Any:
    raise AttributeError(name)  # kit:boundary owner=workflow_graph.executors.lazy_exports class=PROGRAMMER_DEFECT failure_family=none witness=test:test_unknown_lazy_executor_export_raises_attribute_error
