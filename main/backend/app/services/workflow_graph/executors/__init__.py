from __future__ import annotations

from typing import Any

from .base import BaseNodeExecutor, NodeExecutionContext

__all__ = [
    "BaseNodeExecutor",
    "NodeExecutionContext",
    "JoinExecutor",
    "LLMCallExecutor",
    "VectorSearchExecutor",
]


def __getattr__(name: str) -> Any:
    if name == "JoinExecutor":
        from .join import JoinExecutor

        return JoinExecutor
    if name == "LLMCallExecutor":
        from .llm_call import LLMCallExecutor

        return LLMCallExecutor
    if name == "VectorSearchExecutor":
        from .vector_search import VectorSearchExecutor

        return VectorSearchExecutor
    raise AttributeError(name)  # kit:boundary owner=workflow_graph.executors.lazy_exports class=PROGRAMMER_DEFECT failure_family=none witness=test:test_unknown_lazy_executor_export_raises_attribute_error
