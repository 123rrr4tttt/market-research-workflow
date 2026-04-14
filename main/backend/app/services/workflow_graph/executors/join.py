from __future__ import annotations

from typing import Any

from .base import BaseNodeExecutor, NodeExecutionContext


class JoinExecutor(BaseNodeExecutor):
    node_type = "join"

    def execute(self, node: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
        params = dict(node.get("params") or {})
        field = str(params.get("field") or "").strip()

        joined = dict(context.upstream_results)
        if field:
            values = [value.get(field) for value in joined.values() if isinstance(value, dict) and field in value]
            return {
                "node_type": self.node_type,
                "field": field,
                "values": values,
                "sources": sorted(joined.keys()),
                "count": len(values),
            }

        return {
            "node_type": self.node_type,
            "joined": joined,
            "sources": sorted(joined.keys()),
            "count": len(joined),
        }
