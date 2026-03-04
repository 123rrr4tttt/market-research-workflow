from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from .base import BaseNodeExecutor, NodeExecutionContext


def _invoke_llm(prompt: str, *, model: str | None = None, temperature: float = 0.0) -> str:
    from app.services.llm.provider import get_chat_model

    chat = get_chat_model(model=model, temperature=temperature)
    resp = chat.invoke(prompt)
    if isinstance(resp, str):
        return resp
    content = getattr(resp, "content", None)
    if content is not None:
        return str(content)
    if isinstance(resp, dict) and "content" in resp:
        return str(resp["content"])
    return str(resp)


class LLMCallExecutor(BaseNodeExecutor):
    node_type = "llm_call"

    def execute(self, node: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
        params = dict(node.get("params") or {})
        prompt = _build_prompt(params=params, context=context)
        model = _as_str_or_none(params.get("model"))
        temperature = _to_float(params.get("temperature"), default=0.0)

        try:
            text = _invoke_llm(prompt, model=model, temperature=temperature)
            degraded = False
            reason = None
        except Exception as exc:  # noqa: BLE001
            degraded = True
            reason = str(exc)
            text = _fallback_text(prompt, context)

        return {
            "node_type": self.node_type,
            "prompt": prompt,
            "model": model,
            "temperature": temperature,
            "text": text,
            "degraded": degraded,
            "degraded_reason": reason,
        }


def _build_prompt(*, params: dict[str, Any], context: NodeExecutionContext) -> str:
    candidates = [params.get("prompt"), context.inputs.get("prompt"), context.inputs.get("query")]
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text

    if context.upstream_results:
        lines: list[str] = ["Summarize upstream workflow results."]
        for node_id, data in context.upstream_results.items():
            lines.append(f"- {node_id}: {str(data)[:300]}")
        return "\n".join(lines)

    return "Generate a concise response."


def _fallback_text(prompt: str, context: NodeExecutionContext) -> str:
    upstream_keys = ", ".join(sorted(context.upstream_results.keys())) or "none"
    return (
        "[fallback-llm] "
        f"prompt={prompt[:120]} | "
        f"upstream={upstream_keys}"
    )


def _as_str_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _to_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return default
