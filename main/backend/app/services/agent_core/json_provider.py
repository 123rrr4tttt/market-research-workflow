from __future__ import annotations

import json
import re
from typing import Any

from .contracts import AgentCoreRequest, CoreModelStep, CoreProvider, CoreToolCall, CoreToolSpec
from .tool_window import extract_source_library_item_key


class JsonCoreProvider(CoreProvider):
    """Model provider adapter using an explicit JSON tool-call protocol.

    This is a temporary provider for Codex/OpenAI chat adapters that do not yet
    expose native tool calling through the local app bridge. It is still
    model-owned: the prompt shows tool schemas, and the model returns either a
    final answer or tool calls. No keyword classifier participates.
    """

    _shared_model_key: tuple[Any, ...] | None = None
    _shared_model: Any | None = None

    def __init__(self, *, chat_model: Any | None = None, chat_model_factory: Any | None = None) -> None:
        self.chat_model = chat_model
        self.chat_model_factory = chat_model_factory

    def next_step(
        self,
        *,
        request: AgentCoreRequest,
        tools: list[CoreToolSpec],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> CoreModelStep:
        model = self._get_model()
        text = ""
        parsed: dict[str, Any] | None = None
        invalid_responses: list[str] = []
        for attempt in range(1, 3):
            prompt = self._build_prompt(
                request=request,
                tools=tools,
                transcript=transcript,
                remaining_budget=remaining_budget,
                invalid_response=invalid_responses[-1] if invalid_responses else None,
            )
            response = model.invoke(prompt)
            content = getattr(response, "content", None)
            if content is None and isinstance(response, dict):
                content = response.get("content")
            text = str(content or "").strip()
            parsed = self._parse_json_content(text)
            if parsed is not None:
                break
            invalid_responses.append(text[:2000])
            if attempt == 1 and self._fallback_tool_step_if_protocol_violated(
                request=request,
                tools=tools,
                transcript=transcript,
                invalid_text=text,
            ) is not None:
                continue
            break
        if parsed is None:
            fallback = self._fallback_tool_step_if_protocol_violated(
                request=request,
                tools=tools,
                transcript=transcript,
                invalid_text=text,
            )
            if fallback is not None:
                return fallback
            return CoreModelStep.final(text or "我现在无法生成有效回答。", model_path="json_core_provider", parse_error="invalid_json")
        step_type = str(parsed.get("type") or parsed.get("step_type") or parsed.get("action") or "").strip()
        if step_type in {"final", "final_answer", "answer_direct", "assistant_message"}:
            final_content = str(parsed.get("content") or parsed.get("answer") or parsed.get("final_answer") or "").strip()
            writing_create_step = self._writing_create_step_if_needed(
                request=request,
                tools=tools,
                transcript=transcript,
                final_content=final_content,
            )
            if writing_create_step is not None:
                return writing_create_step
            read_step = self._followup_read_step_if_needed(request=request, tools=tools, transcript=transcript)
            if read_step is not None:
                return read_step
            fallback = self._fallback_tool_step_if_protocol_violated(
                request=request,
                tools=tools,
                transcript=transcript,
                invalid_text=final_content,
            )
            if fallback is not None:
                return fallback
            return CoreModelStep.final(final_content, model_path="json_core_provider")
        if step_type in {"tool_calls", "call_tools"}:
            writing_done_step = self._writing_create_done_final_if_needed(request=request, transcript=transcript)
            if writing_done_step is not None:
                return writing_done_step
            writing_create_step = self._writing_create_step_if_needed(
                request=request,
                tools=tools,
                transcript=transcript,
                final_content="",
            )
            if writing_create_step is not None:
                return writing_create_step
            tool_calls: list[CoreToolCall] = []
            for index, item in enumerate(list(parsed.get("tool_calls") or parsed.get("tools") or []), start=1):
                if not isinstance(item, dict):
                    continue
                tool_name = str(item.get("tool_name") or item.get("name") or "").strip()
                if not tool_name:
                    continue
                arguments = item.get("arguments") or item.get("args") or {}
                if not isinstance(arguments, dict):
                    arguments = {}
                tool_calls.append(
                    CoreToolCall(
                        tool_name=tool_name,
                        arguments=dict(arguments),
                        call_id=str(item.get("call_id") or f"{request.turn_id}:tool:{index}:{tool_name}"),
                        reason=str(item.get("reason") or "").strip() or None,
                    )
                )
            return CoreModelStep.tools(*tool_calls, model_path="json_core_provider")
        return CoreModelStep.final(str(parsed.get("content") or text or "").strip(), model_path="json_core_provider", parse_error="unknown_step")

    @staticmethod
    def _writing_create_done_final_if_needed(
        *,
        request: AgentCoreRequest,
        transcript: list[dict[str, Any]],
    ) -> CoreModelStep | None:
        if not JsonCoreProvider._asks_to_create_workbench_document(str(request.message or ""), transcript):
            return None
        for item in reversed(list(transcript or [])):
            if not isinstance(item, dict) or item.get("role") != "tool" or not isinstance(item.get("tool_result"), dict):
                continue
            result = dict(item.get("tool_result") or {})
            if str(result.get("tool_name") or "") != "writing.document.create":
                continue
            if str(result.get("status") or "") != "completed":
                return None
            structured = result.get("structured_content") if isinstance(result.get("structured_content"), dict) else {}
            document = structured.get("document") if isinstance(structured.get("document"), dict) else {}
            doc_id = structured.get("doc_id") or document.get("id")
            title = str(document.get("title") or structured.get("title") or "新建稿件").strip()
            source_refs = structured.get("source_refs") if isinstance(structured.get("source_refs"), list) else []
            refs = f"；引用线索 {len(source_refs)} 条" if source_refs else ""
            return CoreModelStep.final(
                f"已在写作工作台新建文档《{title}》（ID: {doc_id}）{refs}。正文已经写入该文档。",
                model_path="json_core_provider",
                protocol_guardrail="writing_create_done_final",
            )
        return None

    @staticmethod
    def _writing_create_step_if_needed(
        *,
        request: AgentCoreRequest,
        tools: list[CoreToolSpec],
        transcript: list[dict[str, Any]],
        final_content: str,
    ) -> CoreModelStep | None:
        available = {tool.name for tool in tools}
        if "writing.document.create" not in available:
            return None
        executed_tools = {
            str((item.get("tool_result") or {}).get("tool_name") or "").strip()
            for item in list(transcript or [])
            if isinstance(item, dict) and item.get("role") == "tool" and isinstance(item.get("tool_result"), dict)
        }
        if "writing.document.create" in executed_tools:
            return None
        message = str(request.message or "").strip()
        if not JsonCoreProvider._asks_to_create_workbench_document(message, transcript):
            return None
        body_md = JsonCoreProvider._draft_body_for_writing_create(final_content=final_content, transcript=transcript)
        if not body_md:
            return None
        title = JsonCoreProvider._title_for_writing_create(message=message, body_md=body_md)
        source_refs = sorted({f"record:{item}" for item in re.findall(r"记录\s*([0-9A-Za-z_-]+)", body_md)})
        return CoreModelStep.tools(
            CoreToolCall(
                tool_name="writing.document.create",
                arguments={
                    "project_key": request.project_key,
                    "title": title,
                    "body_md": body_md,
                    "source_refs": source_refs,
                    "provenance": {
                        "created_from": "agent_core_chat",
                        "guardrail": "writing_create_intent",
                        "turn_id": request.turn_id,
                    },
                },
                call_id=f"{request.turn_id}:guardrail:writing.document.create",
                reason="Writing guardrail: user asked to create or write a draft into the writing workbench.",
            ),
            model_path="json_core_provider",
            protocol_guardrail="writing_create_intent",
        )

    @staticmethod
    def _asks_to_create_workbench_document(message: str, transcript: list[dict[str, Any]]) -> bool:
        text = str(message or "").strip()
        recent_user = " ".join(
            str(item.get("content") or "")
            for item in list(transcript or [])[-6:]
            if isinstance(item, dict) and item.get("role") == "user"
        )
        combined = f"{recent_user}\n{text}".lower()
        mentions_workbench = any(token in combined for token in ("写作工作台", "工作台", "writing workbench", "workbench"))
        mentions_document = any(token in combined for token in ("文档", "稿件", "文稿", "正文", "文章", "draft", "document"))
        create_or_write = any(
            token in combined
            for token in (
                "新建",
                "创建",
                "建立",
                "写入",
                "贴进去",
                "放进去",
                "保存到",
                "加入",
                "输出新的",
                "新的写作",
                "new draft",
                "create",
                "save into",
            )
        )
        return create_or_write and (mentions_workbench or mentions_document or "写作" in combined)

    @classmethod
    def _draft_body_for_writing_create(cls, *, final_content: str, transcript: list[dict[str, Any]]) -> str:
        candidates = [str(final_content or "")]
        candidates.extend(
            str(item.get("content") or "")
            for item in reversed(list(transcript or []))
            if isinstance(item, dict) and item.get("role") == "assistant"
        )
        for candidate in candidates:
            body = cls._extract_markdown_draft(candidate)
            if body:
                return body[:50000]
        return ""

    @staticmethod
    def _extract_markdown_draft(text: str) -> str:
        body = str(text or "").strip()
        if not body:
            return ""
        heading = re.search(r"(?m)^#\s+.+$", body)
        if not heading:
            return ""
        body = body[heading.start() :].strip()
        body = re.sub(r"\n+如果你愿意，.*$", "", body, flags=re.DOTALL).strip()
        if len(body) < 20:
            return ""
        return body

    @staticmethod
    def _title_for_writing_create(*, message: str, body_md: str) -> str:
        heading = re.search(r"(?m)^#\s+(.+)$", body_md)
        if heading:
            return heading.group(1).strip()[:180]
        clean = re.sub(r"\s+", " ", str(message or "")).strip()
        return (clean or "Agent 新建稿件")[:180]

    def _followup_read_step_if_needed(
        self,
        *,
        request: AgentCoreRequest,
        tools: list[CoreToolSpec],
        transcript: list[dict[str, Any]],
    ) -> CoreModelStep | None:
        available = {tool.name for tool in tools}
        if not available:
            return None
        executed_tools = {
            str((item.get("tool_result") or {}).get("tool_name") or "").strip()
            for item in list(transcript or [])
            if isinstance(item, dict) and item.get("role") == "tool" and isinstance(item.get("tool_result"), dict)
        }
        if executed_tools.intersection({"project.structured_data.item.read", "project.structured_data.items.read", "project.context.resource.read", "writing.document.read", "writing.document.section.read"}):
            return None
        calls: list[CoreToolCall] = []
        for item in reversed(list(transcript or [])):
            if not isinstance(item, dict) or item.get("role") != "tool" or not isinstance(item.get("tool_result"), dict):
                continue
            result = dict(item.get("tool_result") or {})
            structured = result.get("structured_content")
            if not isinstance(structured, dict):
                continue
            payload = structured.get("result") if isinstance(structured.get("result"), dict) else structured
            manifest = payload.get("model_evidence_manifest") if isinstance(payload, dict) else None
            if not isinstance(manifest, list):
                continue
            for index, evidence in enumerate(manifest[:2], start=1):
                if not isinstance(evidence, dict):
                    continue
                read_tool = str(evidence.get("read_tool") or "").strip()
                arguments = evidence.get("read_arguments")
                if not read_tool or read_tool not in available or not isinstance(arguments, dict):
                    continue
                calls.append(
                    CoreToolCall(
                        tool_name=read_tool,
                        arguments=dict(arguments),
                        call_id=f"{request.turn_id}:demand-read:{index}:{read_tool}",
                        reason="Demand-read guardrail: inspect concrete evidence before final synthesis.",
                    )
                )
            if calls:
                return CoreModelStep.tools(
                    *calls,
                    model_path="json_core_provider",
                    protocol_guardrail="demand_read_before_final_answer",
                )
        return None

    def _get_model(self) -> Any:
        if self.chat_model is not None:
            return self.chat_model
        if self.chat_model_factory is not None:
            self.chat_model = self.chat_model_factory()
            return self.chat_model
        from app.services.llm.provider import get_local_fallback_chat
        from app.settings.config import settings

        timeout = int(getattr(settings, "agent_chat_model_answer_timeout_seconds", 45) or 45)
        cache_key = (
            str(getattr(settings, "llm_provider", "") or "").lower(),
            str(getattr(settings, "openai_api_base", "") or ""),
            bool(getattr(settings, "openai_api_key", None)),
            str(getattr(settings, "codex_cli_llm_model", "") or ""),
            str(getattr(settings, "codex_cli_llm_reasoning_effort", "") or ""),
            timeout,
        )
        if JsonCoreProvider._shared_model is not None and JsonCoreProvider._shared_model_key == cache_key:
            self.chat_model = JsonCoreProvider._shared_model
            return self.chat_model
        self.chat_model = get_local_fallback_chat(
            temperature=0.0,
            max_tokens=1200,
            timeout_seconds=timeout,
            codex_cli_timeout_seconds=timeout,
            codex_cli_reasoning_effort=str(getattr(settings, "codex_cli_llm_reasoning_effort", "none") or "none"),
        )
        JsonCoreProvider._shared_model_key = cache_key
        JsonCoreProvider._shared_model = self.chat_model
        return self.chat_model

    @staticmethod
    def _build_prompt(
        *,
        request: AgentCoreRequest,
        tools: list[CoreToolSpec],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
        invalid_response: str | None = None,
    ) -> str:
        repair_instruction = ""
        if invalid_response:
            repair_instruction = (
                "Your previous response was rejected because it was not valid JSON for the tool protocol. "
                "Do not write prose outside JSON. If tools are needed, return type=tool_calls now. "
                f"Rejected response excerpt: {invalid_response[:1000]}"
            )
        if not tools:
            payload = {
                "role": "agent_core_provider",
                "instruction": (
                    "Answer as the model core of an interactive project agent. "
                    "No tools are visible for this turn, so answer directly from general knowledge and the recent transcript. "
                    "Return only JSON in this shape: {\"type\":\"final_answer\",\"content\":\"natural answer\"}. "
                    "Use prior transcript to resolve follow-up messages such as summarize, continue, expand, '这些', '总结一些', or '继续'."
                ),
                "repair_instruction": repair_instruction,
                "user_message": request.message,
                "project_key": request.project_key,
                "transcript": transcript[-6:],
                "remaining_budget": dict(remaining_budget or {}),
            }
            return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        payload = {
            "role": "agent_core_provider",
            "instruction": (
                "You are the model core of a Claude Code style project agent. "
                "Return only JSON. You own the decision: answer normally, or call tools when project/session/tool data is needed. "
                "Use prior_transcript/context to resolve follow-up messages such as 'summarize', 'continue', 'expand', '这些', '总结一些', or '继续'. "
                "If prior context is enough, answer directly from it instead of asking a generic clarification question. "
                "Do not use tools for ordinary world facts, greetings, or general explanations. "
                "Use project read-only tools for questions about current project data, source-library items, workflow graphs, artifacts, ingest status, or session state. "
                "Treat material requests through three dimensions: origin is internal project material, source-library/catalog entrypoint, or external/web source; state is existing/stored/generated, catalog-only, or to_collect; context is writing, investigation, project read, or general conversation. "
                "Generic material/data/evidence supplementation means gathering usable context; start from internal project context, then plan external discovery if the request is general collection or a gap remains. Do not automatically equate it with source-library execution. "
                "For writing/text/draft/report-context material requests, inspect internal project data, graph, artifacts, and writing documents first unless the user explicitly says external/web/new/outside collection; only plan external discovery after internal evidence is absent, insufficient, or explicitly rejected by the user. "
                "Already collected/stored/ingested material belongs to internal existing project material even if it originally came from external sources; source-library items remain collection entrypoints, not already available evidence. "
                "For questions about data records already stored in the project/database, prefer project.structured_data.search and answer from its result. "
                "When project.structured_data.search or project.context.bundle returns model_evidence_manifest/read_arguments, use project.structured_data.item.read, project.structured_data.items.read, project.context.resource.read, writing.document.read, or writing.document.section.read to inspect the specific records needed for a substantive answer. "
                "For stored-data quality, noise, or cleaning-audit questions, call project.structured_data.quality_audit when visible. "
                "For graph/entity/clue tracing or mixed local-data investigation, prefer project.structured_graph.query or project.graph.search. "
                "For long-running writing, investigation, clue tracing, or multi-step work, call agent_task.plan.append to create a durable plan before proceeding when that tool is available. "
                "For those long tasks, call agent_long_task.stage.update after each meaningful stage: plan, internal_evidence, gap_analysis, external_discovery, source_intake, clue_trace, draft_output, verification, or done. "
                "When continuing after page switch, hard refresh, or a follow-up like 'continue', call agent_long_task.stage.read or agent_session.resume_bundle before taking the next action. "
                "When an investigation follows or rejects leads, call agent_investigation.leads.append to persist clue graph, pending questions, followed leads, rejected leads, and citations in the session. "
                "For autonomous external source discovery or candidate URL vetting, call source.discovery.plan first; it is no-fetch/no-write and returns trust gates before any ingest tool. "
                "For research, source discovery, material supplementation, comparison, verification, or multi-source evidence tasks, use a capability matrix rather than one serial query: decompose intent facets, pass multiple query_variants/source_kinds where useful, consider internal tools plus source.web.search, preserve provider diagnostics, and merge/rank candidates before concluding. "
                "When source.web.search is visible and the user explicitly asks for external/web/new material or the internal pass exposes a gap, call source.web.search after the discovery plan to get concrete external candidate titles/URLs/snippets before ingest; for broad requests set matrix_mode=true or provide query_variants/providers instead of one broad query. "
                "If source.web.search returns zero candidates, treat that as provider/config/rate-limit uncertainty. Use provider_diagnostics and empty_result_guidance; do not claim the topic has no external evidence. "
                "When the user approves, defers, or rejects a concrete source candidate, call source.candidate.review if visible. Approved URL candidates should produce a URL-pool ingest payload; approved source-library item candidates should produce an ingest.source_library.run payload. "
                "When source.candidate.review returns next_gate=run_ingest.url_pool.submit_with_payload, call ingest.url_pool.submit with that ingest_payload when the user chose collection or asked to proceed; prefer async_mode=true. "
                "When the user asks whether a just-submitted URL-pool candidate has completed, or asks to replace pending writing evidence, call ingest.url_pool.status before writing. "
                "When continuing source work across turns or sessions, call source.history.read if visible before re-searching; use it to recover prior candidate reviews and URL-pool submissions. "
                "When the user asks to use a just-submitted/previously collected URL-pool candidate in writing, read source.history.read or the submission artifact with agent_artifact.search/read, then call ingest.url_pool.status, then use project.context.bundle or writing.document.read/list as needed before writing.document.insert_paragraph; mark pending sources as pending until ingest completion is confirmed. "
                "For writing workbench requests, read/list writing documents first; when the user asks to create/register/save/write/paste a new draft into the workbench, call writing.document.create. Empty document list means create a new document, not that writing is impossible. Use writing.document.insert_paragraph only when the user asks to modify an existing draft; the tool enforces version locks and write boundaries. "
                "When the user asks to add/attach/use material cards, citation cards, source cards, reference cards, 引用卡, 资料卡, or 引用框 in the writing workbench, call writing.document.citations.upsert after you know doc_id; source_refs on document create/insert are provenance hints, not the formal citation basket. "
                "For collection, report generation, workflow execution, writing mutation, or external actions, call the relevant tool when the user explicitly asks to execute; the runtime enforces schema, budget, and tool-level boundaries without an approval pause by default. "
                "If the user asks to run or supplement evidence from a source-library item and gives an item key, you MUST call ingest.source_library.run with items as a list and project_key from this request when that tool is available. "
                "A final answer saying the source-library run tool is unavailable is invalid if ingest.source_library.run is in available_tool_names. "
                "Do not answer that you lack access to a tool that is present in the tools list; select the tool and let policy or the tool result establish the boundary. "
                "Valid JSON shapes: "
                "{\"type\":\"final_answer\",\"content\":\"natural answer\"} or "
                "{\"type\":\"tool_calls\",\"tool_calls\":[{\"tool_name\":\"name\",\"arguments\":{},\"reason\":\"why\"}]}. "
                "After tool results are present in transcript, produce a natural final_answer that explains the result without exposing backend internals. "
                "If local data was read, synthesize patterns, concrete examples, implications, and limits from the actual items; do not stop at dataset names, counts, or a menu of possible next actions. "
                "Do not give a merely formal status such as only 'completed', 'queued', or 'updated'. "
                "The final_answer must include user-usable substance: name the concrete object/data affected, include useful counts/snippets/result IDs from tool output, and give the real next inspectable state or next step."
                " For project data inventory/search requests, prefer one or two high-signal read tools before final_answer; do not fan out across every visible read tool unless the user explicitly asks for an exhaustive audit."
            ),
            "repair_instruction": repair_instruction,
            "user_message": request.message,
            "project_key": request.project_key,
            "context": dict(request.context or {}),
            "available_tool_names": [tool.name for tool in tools],
            "tool_selection_rules": [
                {
                    "when": "The user explicitly asks to execute, collect, run, supplement evidence, generate a report, mutate project state, or use external sources.",
                    "then": "Return tool_calls, not final_answer. Do not ask for approval first; execute the visible tool and let the tool result establish the boundary.",
                },
                {
                    "when": "The user mentions a source-library item key such as market.general.baseline and asks to run or supplement evidence.",
                    "then": "Call ingest.source_library.run with arguments {\"project_key\": project_key, \"items\": [item_key], \"async_mode\": true}.",
                },
                {
                    "when": "The user asks what data, source-library items, workflow graphs, artifacts, ingest status, or session context exist in the current project.",
                    "then": "Call suitable read-only project tools before answering.",
                },
                {
                    "when": "The user asks to supplement, find, collect, or search for material/data/evidence without explicitly saying source-library or external/web.",
                    "then": "Treat this as material gathering. Start with project.context.bundle or project.structured_data.search when visible, then use source.discovery.plan with matrix_mode=true for external candidates when the request is general collection or the internal pass shows a gap. Do not jump straight to source-library execution unless a concrete source-library item or ingest action is requested.",
                },
                {
                    "when": "The request is in a writing/text/draft/report context and asks for material, evidence, or data.",
                    "then": "Prefer internal existing project material first: project.context.bundle, project.structured_data.search, project.structured_graph.query/project.graph.search, agent_artifact.search, and writing.document.read/list as applicable. If the user explicitly asks for external/web/new/outside material, or the internal pass exposes a gap, use source.discovery.plan and source.web.search when visible, then governed collection only when needed.",
                },
                {
                    "when": "The user asks about existing/stored project records, structured data, database contents, or what data is available for analysis.",
                    "then": "Call project.structured_data.search. Use an empty query for inventory questions and a focused query for topic-specific data questions.",
                },
                {
                    "when": "A previous tool result includes model_evidence_manifest or read_arguments and the user asks to summarize/analyze/explain the material.",
                    "then": "Read the most relevant concrete item(s) before final_answer unless the snippets already contain enough substance. The final answer must include synthesis, not only counts.",
                },
                {
                    "when": "The user asks whether stored project data is noisy, dirty, script/CSS-heavy, or asks for a cleaning/quality audit.",
                    "then": "Call project.structured_data.quality_audit when it is available.",
                },
                {
                    "when": "The user asks for graph, entity, relation, clue tracing, multi-round investigation, or research context across local materials.",
                    "then": "Call project.structured_graph.query or project.graph.search before answering.",
                },
                {
                    "when": "The user asks for long-running writing, investigation, source tracing, or work that should continue across turns.",
                    "then": "Call agent_task.plan.append with a concise durable task plan, then call agent_long_task.stage.update(stage=plan) when available, then continue with read-only project tools as needed.",
                },
                {
                    "when": "The user says continue/resume or the session has existing long-task stages.",
                    "then": "Call agent_long_task.stage.read or agent_session.resume_bundle before deciding the next stage.",
                },
                {
                    "when": "The tool results identify clues, pending questions, followed leads, rejected leads, or citations during a multi-round investigation.",
                    "then": "Call agent_investigation.leads.append to persist the investigation trail before final_answer.",
                },
                {
                    "when": "The user asks to find, discover, vet, trust-check, or expand external sources before collection.",
                    "then": "Call source.discovery.plan before any source-library execution or external ingest. Use its capability_matrix/search_queries to build source.web.search query_variants/providers with matrix_mode=true when concrete external candidates are needed; source.web.search is search-only and does not ingest. If this is an investigation and agent_investigation.leads.append is available, persist the planned or searched candidate leads before trace.read or final_answer.",
                },
                {
                    "when": "The user approves, defers, rejects,采集,暂缓, or refuses a concrete source.web.search/source.discovery.plan candidate.",
                    "then": "Call source.candidate.review with the candidate object and decision. Use its ingest_payload and next_gate in the final answer instead of pretending the candidate has already been ingested.",
                },
                {
                    "when": "source.candidate.review returns an approved URL-pool ingest_payload and the user has chosen collection or asked to proceed.",
                    "then": "Call ingest.url_pool.submit with {\"project_key\": project_key, \"ingest_payload\": ingest_payload, \"async_mode\": true}. Report the returned task_id or next inspectable ingest state.",
                },
                {
                    "when": "The user asks to put a just-submitted URL-pool/source candidate into a writing document.",
                    "then": "Read the relevant submission artifact with agent_artifact.search/read, then read/list the writing document and call writing.document.insert_paragraph. If the ingest task is only queued, write it as pending evidence rather than a verified citation.",
                },
                {
                    "when": "The user asks to create, establish, save, paste, or write a new draft/document into the writing workbench, especially phrases like 新建稿件, 写入写作工作台, or 把内容贴进去.",
                    "then": "Call writing.document.create with project_key, title, body_md/content_md, and source_refs. An empty writing.document.list result means create a new document, not that writing is impossible.",
                },
                {
                    "when": "The user asks to add, attach, preserve, or use material cards/citation cards/source cards/reference cards/资料卡/引用卡/引用框 with a writing document.",
                    "then": "After writing.document.list/read/create gives doc_id, call writing.document.citations.upsert with doc_id and citations/material_cards/source_refs so the workbench citation basket is updated.",
                },
                {
                    "when": "The user asks whether a URL-pool/source candidate has completed, or asks to replace pending evidence with verified writing evidence.",
                    "then": "Call ingest.url_pool.status. If next_gate is verified_evidence_ready_for_writing, use the returned evidence_items before writing. If it is wait_for_ingest_completion_or_retry_status, keep the writing marked pending.",
                },
                {
                    "when": "The user asks to continue prior source investigation, reuse earlier candidates, summarize collected candidates, or write from previous candidate decisions.",
                    "then": "Call source.history.read with include_recent_sessions=true when visible. Use approved reviews and submissions as history; call ingest.url_pool.status before treating queued URLs as verified evidence.",
                },
                {
                    "when": "The user asks to edit, append, insert, or rewrite writing workbench content.",
                    "then": "Call writing.document.list/read to identify version and etag, then call writing.document.insert_paragraph for mutation.",
                },
            ],
            "high_priority_tool_names": [
                tool.name
                for tool in tools
                if tool.name
                in {
                    "agent_task.plan.append",
                    "agent_long_task.stage.update",
                    "agent_long_task.stage.read",
                    "agent_session.resume_bundle",
                    "agent_investigation.leads.append",
                    "project.summary.read",
                    "project.structured_graph.query",
                    "project.graph.search",
                    "project.structured_data.search",
                    "agent_session.context.read",
                    "source_library.item.list",
                    "source_library.item.search",
                    "source.discovery.plan",
                    "source.candidate.review",
                    "ingest.url_pool.submit",
                    "ingest.url_pool.status",
                    "source.history.read",
                    "ingest.status.read",
                    "writing.document.list",
                    "writing.document.read",
                    "writing.document.create",
                    "writing.document.insert_paragraph",
                    "writing.document.citations.upsert",
                    "ingest.source_library.run",
                    "workflow_graph.run",
                    "report.generate",
                    "mcp.service.catalog",
                }
            ],
            "tools": [tool.to_model_tool() for tool in tools],
            "transcript": transcript[-8:],
            "remaining_budget": dict(remaining_budget or {}),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any] | None:
        text = str(content or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z0-9_-]*", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            parsed = json.loads(text)
        except Exception:  # noqa: BLE001
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _fallback_tool_step_if_protocol_violated(
        *,
        request: AgentCoreRequest,
        tools: list[CoreToolSpec],
        transcript: list[dict[str, Any]],
        invalid_text: str,
    ) -> CoreModelStep | None:
        """Last-resort protocol guardrail when the model violates JSON mode.

        This does not participate in normal routing. It only prevents a
        non-JSON or tool-avoiding response from being accepted as truth when
        the user asked about current project state or an explicit execution.
        """

        available = {tool.name for tool in tools}
        message = str(request.message or "").strip()
        lowered = f"{message}\n{invalid_text}".lower()
        if not message:
            return None

        writing_create_step = JsonCoreProvider._writing_create_step_if_needed(
            request=request,
            tools=tools,
            transcript=transcript,
            final_content=invalid_text,
        )
        if writing_create_step is not None:
            return writing_create_step

        if any(isinstance(item, dict) and item.get("role") == "tool" for item in transcript):
            return None

        query = JsonCoreProvider._project_query_from_message_and_transcript(message, transcript)
        source_item_key = extract_source_library_item_key(message)
        asks_source_execution = (
            source_item_key
            and "ingest.source_library.run" in available
            and any(token in lowered for token in ("补", "证据", "run", "execute", "采集", "collect", "来源库", "source-library", "source library"))
        )
        if asks_source_execution:
            return CoreModelStep.tools(
                CoreToolCall(
                    tool_name="ingest.source_library.run",
                    arguments={"project_key": request.project_key, "items": [source_item_key], "async_mode": True},
                    call_id=f"{request.turn_id}:guardrail:ingest.source_library.run",
                    reason="Protocol guardrail: explicit source-library execution request requires governed tool call.",
                ),
                model_path="json_core_provider",
                protocol_guardrail="tool_required_after_invalid_json",
            )

        project_context_tokens = (
            "项目",
            "数据",
            "来源库",
            "source library",
            "source-library",
            "workflow",
            "artifact",
            "会话",
            "采集状态",
            "ingest",
            "检索",
            "搜索",
            "查找",
            "关键词",
            "试试看",
            "下一步",
            "继续",
            "结构化数据",
            "stored data",
            "structured data",
            "database",
            "数据库",
            "工具",
            "能力",
            "写作",
            "文稿",
            "工作台",
            "段落",
            "调查",
            "线索",
            "追查",
            "graph",
            "clue",
            "writing",
            "document",
            "workbench",
        )
        asks_project_context = any(token in lowered for token in project_context_tokens)
        if not asks_project_context:
            return None

        preferred = [
            ("agent_session.resume_bundle", {"limit": 10}),
            ("project.summary.read", {}),
            ("project.context.bundle", {"query": query, "limit": 12}),
            ("project.structured_graph.query", {"query": query, "limit": 12}),
            ("project.graph.search", {"query": query, "limit": 12}),
            ("project.structured_data.search", {"query": query, "limit": 12}),
            ("writing.document.list", {"project_key": request.project_key, "limit": 20}),
            ("agent_session.context.read", {"session_id": request.session_id}),
            ("source_library.item.list", {"project_key": request.project_key, "limit": 20}),
            ("ingest.status.read", {"session_id": request.session_id}),
        ]
        calls = [
            CoreToolCall(
                tool_name=name,
                arguments={key: value for key, value in arguments.items() if value is not None},
                call_id=f"{request.turn_id}:guardrail:{name}",
                reason="Protocol guardrail: current project question requires read-only project context.",
            )
            for name, arguments in preferred
            if name in available
        ]
        if calls:
            return CoreModelStep.tools(
                *calls,
                model_path="json_core_provider",
                protocol_guardrail="tool_required_after_invalid_json",
            )
        return None

    @staticmethod
    def _project_query_from_message_and_transcript(message: str, transcript: list[dict[str, Any]]) -> str:
        text = str(message or "").strip()
        generic_followup = (
            len(text) <= 24
            and any(token in text for token in ("下一步", "继续", "试试看", "检索", "搜索", "查找", "关键词", "不可能"))
        )
        if not generic_followup:
            return text
        snippets: list[str] = []
        for item in reversed(list(transcript or [])[-8:]):
            if not isinstance(item, dict):
                continue
            if item.get("role") not in {"user", "assistant"}:
                continue
            content = " ".join(str(item.get("content") or "").split())
            if not content:
                continue
            snippets.append(content[:260])
            if len(snippets) >= 3:
                break
        combined = " ".join(reversed(snippets)).strip()
        return combined[:500] or text
