from __future__ import annotations

import re
from typing import Any

from .base import BaseNodeExecutor, NodeExecutionContext


def _invoke_llm(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    top_p: float | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    from app.services.llm.provider import get_chat_model

    chat = get_chat_model(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        **(extra or {}),
    )
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
        _assert_prompt_template_inputs(params=params, context=context)
        prompt = _build_prompt(params=params, context=context)
        normalized = _normalize_provider_params(params)
        model = _as_str_or_none(normalized.get("model"))
        temperature = _to_float(normalized.get("temperature"), default=0.0)
        max_tokens = _to_int_or_none(normalized.get("max_tokens"))
        top_p = _to_float_or_none(normalized.get("top_p"))
        prompt_class = _as_str_or_none(params.get("prompt_class"))
        provider = _as_str_or_none(params.get("provider"))

        try:
            text = _invoke_llm(
                prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                extra={
                    key: value
                    for key, value in normalized.items()
                    if key not in {"provider", "model", "temperature", "top_p", "max_tokens", "prompt_class", "prompt_template", "prompt", "input_vars", "output_vars"}
                },
            )
            degraded = False
            reason = None
        except Exception as exc:  # noqa: BLE001
            degraded = True
            reason = str(exc)
            text = _fallback_text(prompt, context)

        return {
            "node_type": self.node_type,
            "prompt": prompt,
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "prompt_class": prompt_class,
            "text": text,
            "degraded": degraded,
            "degraded_reason": reason,
        }


def _build_prompt(*, params: dict[str, Any], context: NodeExecutionContext) -> str:
    template = str(params.get("prompt_template") or "").strip()
    if template:
        scope = _build_prompt_scope(context=context, params=params)
        return _safe_format(template, scope)

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


def _assert_prompt_template_inputs(*, params: dict[str, Any], context: NodeExecutionContext) -> None:
    template = str(params.get("prompt_template") or "").strip()
    if not template:
        return
    required = _extract_template_variables(template)
    missing = [name for name in required if name not in context.inputs]
    if missing:
        raise ValueError(f"prompt_template_missing_inputs:{','.join(sorted(missing))}")


def _extract_template_variables(template: str) -> set[str]:
    names = set(re.findall(r"{([a-zA-Z_][a-zA-Z0-9_]*)}", template))
    return {name for name in names if name not in {"run_id", "node_id", "prompt_class", "upstream"}}


def _normalize_provider_params(params: dict[str, Any]) -> dict[str, Any]:
    provider = str(params.get("provider") or "").strip().lower()
    normalized = dict(params)
    if provider in {"ollama", "local"}:
        # Keep generic keys for response contract, but allow provider-specific hints.
        if normalized.get("max_tokens") is not None and normalized.get("num_predict") is None:
            normalized["num_predict"] = normalized.get("max_tokens")
    return normalized


def _build_prompt_scope(*, context: NodeExecutionContext, params: dict[str, Any]) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    scope.update(context.inputs)
    scope["node_id"] = context.node_id
    scope["run_id"] = context.run_id
    scope["prompt_class"] = params.get("prompt_class")
    scope["upstream"] = context.upstream_results
    for node_id, value in context.upstream_results.items():
        scope[f"upstream_{node_id}"] = value
    return scope


def _safe_format(template: str, scope: dict[str, Any]) -> str:
    try:
        return template.format(**scope)
    except Exception:
        return template


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


def _to_float_or_none(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _to_int_or_none(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return None
