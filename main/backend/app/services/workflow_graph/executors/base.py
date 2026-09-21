from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeExecutionContext:
    run_id: str
    node_id: str
    workflow: dict[str, Any]
    inputs: dict[str, Any] = field(default_factory=dict)
    input_trace: dict[str, Any] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    upstream_results: dict[str, Any] = field(default_factory=dict)


class BaseNodeExecutor(ABC):
    node_type: str = ""

    def supports(self, node_type: str) -> bool:
        return str(node_type or "").strip().lower() == self.node_type

    @abstractmethod
    def execute(self, node: dict[str, Any], context: NodeExecutionContext) -> Any:
        raise NotImplementedError  # kit:boundary owner=workflow_graph.executors.base class=PROGRAMMER_DEFECT failure_family=none witness=test:test_base_node_executor_abstract_execute_is_not_implemented
