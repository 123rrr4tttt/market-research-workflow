from __future__ import annotations

from ..contracts import WorkflowJsonObject, WorkflowJsonValue
from .kernel import NodeExecutionContext, NodeEffectResult, node_success


def run_join_kernel(context: NodeExecutionContext) -> NodeEffectResult:
    field = str(context.params.get("field") or "").strip()
    joined = dict(context.upstream_results)
    sources: list[WorkflowJsonValue] = [node_id for node_id in sorted(joined)]

    if field:
        values: list[WorkflowJsonValue] = [
            value.get(field)
            for value in joined.values()
            if isinstance(value, dict) and field in value
        ]
        payload: WorkflowJsonObject = {
            "node_type": "join",
            "field": field,
            "values": values,
            "sources": sources,
            "count": len(values),
        }
        return node_success(context, payload)

    payload = {
        "node_type": "join",
        "joined": joined,
        "sources": sources,
        "count": len(joined),
    }
    return node_success(context, payload)
