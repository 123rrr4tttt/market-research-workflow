from __future__ import annotations

import re
from typing import Never

from functorial_kit import Failure

from ..contracts import WorkflowGraphCompileError, raise_workflow_graph_legacy, workflow_graph_failure
from ..schema import try_parse_workflow_json_object
from .kernel import NodeExecutionContext, NodeEffectResult, node_failed


_OWNER = "workflow_graph.kernel.llm_call"
_MISSING_BINDING = "workflow.llm_call requires an Agent Cell execution binding; no model was called"
_BINDING_DETAILS = {"capability": "workflow.llm_call", "binding": "agent_cell"}
_TEMPLATE_CONTEXT_NAMES = frozenset({"run_id", "node_id", "prompt_class", "upstream"})


def invoke_workflow_llm_call_skill(payload: object) -> None:
    parsed = try_parse_workflow_json_object(payload, field="workflow.llm_call.payload")
    if isinstance(parsed, Failure):
        _raise_skill_failure(
            "contract_invalid",
            "workflow.llm_call.payload must be a JSON object",
            field="workflow.llm_call.payload",
            index=-1,
        )
    if not str(parsed.get("prompt") or "").strip():
        _raise_skill_failure("contract_invalid", "prompt is required", field="prompt", index=-1)
    _raise_skill_failure("executor_not_registered", _MISSING_BINDING, **_BINDING_DETAILS)


def _raise_skill_failure(code: str, message: str, **details: str | int) -> Never:
    raise_workflow_graph_legacy(
        workflow_graph_failure(
            code,
            message,
            owner=_OWNER,
            public_exception=WorkflowGraphCompileError,
            **details,
        )
    )


def run_llm_call_kernel(context: NodeExecutionContext) -> NodeEffectResult:
    template = str(context.params.get("prompt_template") or "").strip()
    variables = set(re.findall(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", template))
    missing = sorted(variables - _TEMPLATE_CONTEXT_NAMES - context.inputs.keys())
    if missing:
        return node_failed(
            context,
            "required_input_missing",
            f"prompt_template_missing_inputs:{','.join(missing)}",
            owner=_OWNER,
            details={"field": "prompt_template", "index": -1, "missing": missing},
        )
    return node_failed(
        context,
        "executor_not_registered",
        _MISSING_BINDING,
        owner=_OWNER,
        details=dict(_BINDING_DETAILS),
    )
