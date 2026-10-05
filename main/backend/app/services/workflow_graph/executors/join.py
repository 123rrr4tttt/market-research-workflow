from __future__ import annotations

from .kernel import NodeExecutionContext, NodeEffectResult, node_success


def run_join_kernel(context: NodeExecutionContext) -> NodeEffectResult:
    field = str(context.params.get("field") or "").strip()
    joined = dict(context.upstream_results)

    if field:
        values = [
            value.get(field)
            for value in joined.values()
            if isinstance(value, dict) and field in value
        ]
        return node_success(context, {
            "node_type": "join",
            "field": field,
            "values": values,
            "sources": sorted(joined.keys()),
            "count": len(values),
        })

    return node_success(context, {
        "node_type": "join",
        "joined": joined,
        "sources": sorted(joined.keys()),
        "count": len(joined),
    })
