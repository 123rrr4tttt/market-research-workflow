from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .contracts import AgentCoreRequest, CoreModelStep, CoreProvider, CoreToolCall, CoreToolSpec
from .json_provider import JsonCoreProvider


class NativeToolCallingCoreProvider(CoreProvider):
    """OpenAI/LangChain native tool-calling provider with JSON fallback.

    When the configured chat model exposes ``bind_tools`` we use the provider's
    native tool-call protocol. Local Codex CLI fallback currently has only
    ``invoke`` semantics, so it intentionally falls back to ``JsonCoreProvider``.
    """

    _shared_model_key: tuple[Any, ...] | None = None
    _shared_model: Any | None = None

    def __init__(
        self,
        *,
        chat_model: Any | None = None,
        chat_model_factory: Any | None = None,
        fallback_provider: CoreProvider | None = None,
    ) -> None:
        self.chat_model = chat_model
        self.chat_model_factory = chat_model_factory
        self.fallback_provider = fallback_provider or JsonCoreProvider()

    def next_step(
        self,
        *,
        request: AgentCoreRequest,
        tools: list[CoreToolSpec],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> CoreModelStep:
        try:
            model = self._get_model()
        except Exception as exc:  # noqa: BLE001
            return self._fallback_next_step(
                request=request,
                tools=tools,
                transcript=transcript,
                remaining_budget=remaining_budget,
                reason=f"native_model_unavailable:{exc.__class__.__name__}",
            )
        if not hasattr(model, "bind_tools"):
            return self._fallback_next_step(
                request=request,
                tools=tools,
                transcript=transcript,
                remaining_budget=remaining_budget,
                reason="native_bind_tools_unavailable",
            )

        native_tools, name_map = self._to_native_tools(tools)
        try:
            bound_model = model.bind_tools(native_tools) if native_tools else model
            response = bound_model.invoke(
                self._build_messages(
                    request=request,
                    tools=tools,
                    transcript=transcript,
                    remaining_budget=remaining_budget,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return self._fallback_next_step(
                request=request,
                tools=tools,
                transcript=transcript,
                remaining_budget=remaining_budget,
                reason=f"native_invoke_failed:{exc.__class__.__name__}",
            )

        calls = self._extract_tool_calls(response=response, name_map=name_map, request=request)
        if calls:
            return CoreModelStep.tools(*calls, model_path="native_tool_calling_provider")
        content = self._content_to_text(getattr(response, "content", ""))
        guardrail = JsonCoreProvider._fallback_tool_step_if_protocol_violated(
            request=request,
            tools=tools,
            transcript=transcript,
            invalid_text=content,
        )
        if guardrail is not None:
            metadata = dict(guardrail.metadata or {})
            metadata.setdefault("native_guardrail_reason", "project_context_requires_tool_result")
            return CoreModelStep(
                step_type=guardrail.step_type,
                content=guardrail.content,
                tool_calls=guardrail.tool_calls,
                metadata=metadata,
            )
        return CoreModelStep.final(content, model_path="native_tool_calling_provider")

    def _fallback_next_step(
        self,
        *,
        request: AgentCoreRequest,
        tools: list[CoreToolSpec],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
        reason: str,
    ) -> CoreModelStep:
        step = self.fallback_provider.next_step(
            request=request,
            tools=tools,
            transcript=transcript,
            remaining_budget=remaining_budget,
        )
        metadata = dict(step.metadata or {})
        metadata.setdefault("native_fallback_reason", reason)
        return CoreModelStep(
            step_type=step.step_type,
            content=step.content,
            tool_calls=step.tool_calls,
            metadata=metadata,
        )

    def _get_model(self) -> Any:
        if self.chat_model is not None:
            return self.chat_model
        if self.chat_model_factory is not None:
            self.chat_model = self.chat_model_factory()
            return self.chat_model
        from app.services.llm.provider import get_chat_model
        from app.settings.config import settings

        cache_key = (
            str(getattr(settings, "llm_provider", "") or "").lower(),
            str(getattr(settings, "openai_api_base", "") or ""),
            bool(getattr(settings, "openai_api_key", None)),
            str(getattr(settings, "litellm_api_base", "") or ""),
            bool(getattr(settings, "litellm_api_key", None)),
            str(getattr(settings, "codex_cli_llm_model", "") or ""),
        )
        if NativeToolCallingCoreProvider._shared_model is not None and NativeToolCallingCoreProvider._shared_model_key == cache_key:
            self.chat_model = NativeToolCallingCoreProvider._shared_model
            return self.chat_model
        self.chat_model = get_chat_model(temperature=0.0, max_tokens=1200)
        NativeToolCallingCoreProvider._shared_model_key = cache_key
        NativeToolCallingCoreProvider._shared_model = self.chat_model
        return self.chat_model

    @staticmethod
    def _build_messages(
        *,
        request: AgentCoreRequest,
        tools: list[CoreToolSpec],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> list[dict[str, str]]:
        system = (
            "You are the model core of a Claude Code style project agent. "
            "Answer normally for greetings and general facts. "
            "Use the recent prior transcript to resolve follow-up messages such as summarizing, continuing, expanding, '这些', '总结一些', or '继续'. "
            "If the prior transcript gives enough context, do not ask a generic clarification question. "
            "Call visible tools when current project/session/source-library/workflow/artifact data is needed. "
            "Treat material requests through origin/state/context dimensions: internal existing project material, source-library/catalog entrypoint, external/web source, existing/generated/catalog/to_collect state, and writing/investigation/project-read context. "
            "Generic material/data/evidence supplementation means gathering usable context: inspect internal project context first, then plan external discovery if this is general collection or a gap remains. Do not automatically equate material supplementation with source-library execution. "
            "For writing/text/draft/report-context material requests, prefer internal project data, graph, artifacts, and writing documents first unless the user explicitly asks for external/web/new/outside material; already collected/stored/ingested material is internal existing evidence, while source-library items are collection entrypoints. "
            "For existing project database records or structured data questions, prefer project.structured_data.search when visible. "
            "When project.structured_data.search or project.context.bundle returns model_evidence_manifest/read_arguments, use project.structured_data.item.read, project.structured_data.items.read, project.context.resource.read, writing.document.read, or writing.document.section.read to inspect concrete records before summarizing or analyzing them. "
            "For stored-data quality, noise, or cleaning-audit questions, call project.structured_data.quality_audit when visible. "
            "For research, source discovery, material supplementation, comparison, verification, or multi-source evidence tasks, use a capability matrix rather than one serial query: decompose intent facets, pass multiple query_variants/source_kinds where useful, consider internal tools plus source.web.search, preserve provider diagnostics, and merge/rank candidates before concluding. "
            "For multi-step investigation or explicit external writing supplementation, if source.discovery.plan returns source directions or candidate leads and source.web.search is visible, use source.web.search with matrix_mode=true when concrete external candidate URLs/snippets are needed; then persist those leads with agent_investigation.leads.append before reading agent_investigation.trace.read or finalizing. "
            "If source.web.search returns zero candidates, treat it as provider/config/rate-limit uncertainty and use provider_diagnostics/empty_result_guidance; do not claim the topic has no external evidence. "
            "When the user approves, defers, or rejects a concrete external source candidate, call source.candidate.review if visible and use its ingest_payload/next_gate; do not claim the candidate is ingested until a later ingest tool actually runs. "
            "When source.candidate.review returns next_gate=run_ingest.url_pool.submit_with_payload and the user chose collection or asked to proceed, call ingest.url_pool.submit with the returned ingest_payload and async_mode=true. "
            "When the user asks whether a just-submitted URL-pool candidate has completed, or asks to replace pending writing evidence, call ingest.url_pool.status first. "
            "When continuing source work across turns or sessions, call source.history.read if visible before re-searching; use it to recover prior candidate reviews and URL-pool submissions. "
            "When the user asks to use a just-submitted URL-pool candidate in writing, read source.history.read or the submission artifact with agent_artifact.search/read, then call ingest.url_pool.status, then write through writing.document.insert_paragraph; label queued sources as pending until ingest completion is confirmed. "
            "When the user asks to add material cards, citation cards, source cards, reference cards, 资料卡, 引用卡, or 引用框 to a writing document, call writing.document.citations.upsert after you know doc_id; source_refs on prose writes are provenance hints, not the formal citation basket. "
            "For explicit execution, collection, report generation, workflow runs, or external actions, call the relevant visible tool directly; the runtime enforces schema, budget, and tool-level boundaries without an approval pause by default. "
            "After tool results are present, produce a natural final answer without exposing backend internals. "
            "If local data was read, synthesize patterns, concrete examples, implications, and limits from the actual items; do not stop at dataset names, counts, or a menu of possible next actions. "
            "Do not give a merely formal status such as only 'completed', 'queued', or 'updated'. "
            "Your final answer must include user-usable substance: name the concrete object/data affected, include any useful counts/snippets/result IDs from tool output, and give the real next inspectable state or next step. "
            f"Visible tool names: {', '.join(tool.name for tool in tools) or '(none)'}."
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        model_context = NativeToolCallingCoreProvider._context_for_model(request.context)
        if model_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"Session/project context JSON:\n{json.dumps(model_context, ensure_ascii=False, default=str)}",
                }
            )
        for item in list(transcript or [])[-8:]:
            role = str(item.get("role") or "").strip()
            if role == "user":
                messages.append({"role": "user", "content": str(item.get("content") or "")})
            elif role == "assistant":
                messages.append({"role": "assistant", "content": str(item.get("content") or item.get("delta") or "")})
            elif role == "tool":
                messages.append({"role": "user", "content": f"Tool result:\n{json.dumps(item.get('tool_result') or {}, ensure_ascii=False, default=str)}"})
        if not any(item.get("role") == "user" and item.get("content") == request.message for item in messages):
            messages.append({"role": "user", "content": request.message})
        messages.append({"role": "system", "content": f"Project key: {request.project_key or ''}. Budget: {json.dumps(remaining_budget or {}, ensure_ascii=False)}"})
        return messages

    @staticmethod
    def _context_for_model(context: dict[str, Any] | None) -> dict[str, Any]:
        raw = dict(context or {})
        if not raw:
            return {}
        summary = dict(raw.get("session_context_summary") or {})
        stable = dict(summary.get("stable_summary") or {})
        project_context = dict(summary.get("project_context") or {})
        tool_use = dict(summary.get("tool_use_summary") or {})
        budgeted = dict(summary.get("budgeted_context") or {})
        return {
            "runtime_variant": raw.get("runtime_variant"),
            "stream": raw.get("stream"),
            "root_task_id": raw.get("root_task_id"),
            "project_key": raw.get("project_key"),
            "contextual_followup": bool(raw.get("contextual_followup")),
            "session_context_policy": raw.get("session_context_policy"),
            "session": dict(stable.get("session") or {}),
            "counts": dict(stable.get("counts") or {}),
            "latest_user_instruction": stable.get("latest_user_instruction"),
            "history_summary": stable.get("history_summary"),
            "project_context": project_context,
            "tool_use_summary": tool_use,
            "budgeted_context_text": str(budgeted.get("text") or "")[:5000],
            "prior_transcript_count": len(list(raw.get("prior_transcript") or [])),
        }

    @staticmethod
    def _to_native_tools(tools: list[CoreToolSpec]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        native_tools: list[dict[str, Any]] = []
        name_map: dict[str, str] = {}
        used: set[str] = set()
        for spec in tools:
            native_name = _native_tool_name(spec.name)
            if native_name in used:
                native_name = f"{native_name[:48]}_{hashlib.sha1(spec.name.encode('utf-8')).hexdigest()[:8]}"
            used.add(native_name)
            name_map[native_name] = spec.name
            native_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": native_name,
                        "description": f"Canonical tool name: {spec.name}. {spec.description_for_model}",
                        "parameters": dict(spec.input_schema or {"type": "object", "properties": {}}),
                    },
                }
            )
        return native_tools, name_map

    @staticmethod
    def _extract_tool_calls(*, response: Any, name_map: dict[str, str], request: AgentCoreRequest) -> list[CoreToolCall]:
        raw_calls = getattr(response, "tool_calls", None)
        if raw_calls is None:
            additional = getattr(response, "additional_kwargs", None)
            if isinstance(additional, dict):
                raw_calls = additional.get("tool_calls")
        calls: list[CoreToolCall] = []
        for index, raw in enumerate(list(raw_calls or []), start=1):
            name = ""
            args: Any = {}
            call_id = ""
            if isinstance(raw, dict):
                if isinstance(raw.get("function"), dict):
                    function = dict(raw.get("function") or {})
                    name = str(function.get("name") or raw.get("name") or "").strip()
                    args = function.get("arguments") or raw.get("args") or {}
                else:
                    name = str(raw.get("name") or "").strip()
                    args = raw.get("args") or raw.get("arguments") or {}
                call_id = str(raw.get("id") or raw.get("call_id") or f"{request.turn_id}:native:{index}:{name}").strip()
            if not name:
                continue
            canonical = name_map.get(name, name)
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:  # noqa: BLE001
                    args = {}
            if not isinstance(args, dict):
                args = {}
            calls.append(CoreToolCall(tool_name=canonical, arguments=dict(args), call_id=call_id))
        return calls

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(item or ""))
            return "\n".join(part for part in parts if part).strip()
        return str(content or "").strip()


def _native_tool_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name or "tool")).strip("_")
    if not base:
        base = "tool"
    if not re.match(r"^[A-Za-z_]", base):
        base = f"tool_{base}"
    return base[:60]
