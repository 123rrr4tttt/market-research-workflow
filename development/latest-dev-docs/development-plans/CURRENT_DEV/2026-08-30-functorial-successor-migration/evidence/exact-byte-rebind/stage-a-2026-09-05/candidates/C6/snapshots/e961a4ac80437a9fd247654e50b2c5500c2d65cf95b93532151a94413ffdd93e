from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from .contracts import (
    AgentCoreRequest,
    AgentCoreRunResult,
    CoreEvent,
    CoreModelStep,
    CorePermissionRequest,
    CoreProvider,
    CoreToolCall,
    CoreToolExecutor,
    CoreToolResult,
    CoreToolSpec,
    new_core_id,
)
from .validation import summarize_validation_errors, validate_tool_arguments


class AgentCore:
    """Claude Code style model-owned tool loop.

    The provider decides whether to answer or call tools. This class owns only
    event emission, policy checks, tool execution, and pause/resume boundaries.
    """

    def __init__(
        self,
        *,
        provider: CoreProvider,
        tool_registry: CoreToolExecutor,
        tool_specs: list[CoreToolSpec],
        policy_tool_specs: list[CoreToolSpec] | None = None,
    ) -> None:
        self.provider = provider
        self.tool_registry = tool_registry
        self.tool_specs = list(tool_specs)
        self.policy_tool_specs = list(policy_tool_specs) if policy_tool_specs is not None else list(tool_specs)

    def run(self, request: AgentCoreRequest, *, event_sink: Callable[[CoreEvent], None] | None = None) -> AgentCoreRunResult:
        events: list[CoreEvent] = []
        transcript: list[dict[str, Any]] = self._initial_transcript(request)
        tool_results: list[CoreToolResult] = []
        final_answer = ""
        tool_call_count = 0

        def emit(event: CoreEvent) -> None:
            events.append(event)
            if event_sink is not None:
                event_sink(event)

        self._emit(
            emit,
            "session_started",
            request=request,
            payload={"project_key": request.project_key, "core": "agent_core.v1"},
        )
        self._emit(
            emit,
            "user_message",
            request=request,
            actor="user",
            payload={"message": request.message},
        )
        transcript.append({"role": "user", "content": request.message})

        if request.resume is not None:
            resume = request.resume
            if not resume.approved:
                self._emit(
                    emit,
                    "approval_resolved",
                    request=request,
                    call_id=resume.tool_call.call_id,
                    payload={"approval_id": resume.approval_id, "approved": False, "approved_by": resume.approved_by},
                )
                return AgentCoreRunResult(
                    session_id=request.session_id,
                    turn_id=request.turn_id,
                    events=tuple(events),
                    final_answer="已取消需要审批的工具调用。",
                    stop_reason="approval_denied",
                )
            self._emit(
                emit,
                "run_resumed",
                request=request,
                call_id=resume.tool_call.call_id,
                payload={"approval_id": resume.approval_id, "approved_by": resume.approved_by},
            )
            resumed_result = self._execute_tool_call(
                request=request,
                tool_call=resume.resolved_tool_call(),
                emit=emit,
                skip_permission=True,
            )
            tool_results.append(resumed_result)
            transcript.append({"role": "tool", "tool_result": self._tool_result_for_transcript(resumed_result)})
            transcript = self._compact_transcript_if_needed(request=request, transcript=transcript, emit=emit)
            tool_call_count += 1

        for iteration in range(1, max(1, int(request.max_iterations)) + 1):
            if tool_call_count >= request.max_tool_calls:
                self._emit_loop_state(
                    emit,
                    request=request,
                    phase="blocked",
                    iteration=iteration,
                    tool_call_count=tool_call_count,
                    transition_reason="max_tool_calls_exceeded",
                )
                return AgentCoreRunResult(
                    session_id=request.session_id,
                    turn_id=request.turn_id,
                    events=tuple(events),
                    final_answer=final_answer,
                    tool_results=tuple(tool_results),
                    stop_reason="max_tool_calls_exceeded",
                )
            self._emit_loop_state(
                emit,
                request=request,
                phase="model_step",
                iteration=iteration,
                tool_call_count=tool_call_count,
                transition_reason="request_model_step",
            )
            if bool((request.context or {}).get("stream")):
                self._emit(
                    emit,
                    "assistant_delta",
                    request=request,
                    payload={
                        "contract_version": "agent_core.model_step_status.v1",
                        "delta": "",
                        "phase": "model_step",
                        "iteration": iteration,
                        "status": "thinking",
                    },
                )
            step = self.provider.next_step(
                request=request,
                tools=self._tool_specs_for_model(request),
                transcript=transcript,
                remaining_budget={
                    "max_iterations": request.max_iterations,
                    "iteration": iteration,
                    "max_tool_calls": request.max_tool_calls,
                    "remaining_tool_calls": max(0, request.max_tool_calls - tool_call_count),
                },
            )
            self._emit_loop_state(
                emit,
                request=request,
                phase=step.step_type,
                iteration=iteration,
                tool_call_count=tool_call_count,
                pending_tool_count=len(step.tool_calls),
                transition_reason="model_step_received",
            )
            if step.step_type == "assistant_delta":
                self._emit(emit, "assistant_delta", request=request, payload={"delta": step.content, **step.metadata})
                transcript.append({"role": "assistant", "delta": step.content})
                continue
            if step.step_type == "final_answer":
                final_answer = step.content
                final_metadata = dict(step.metadata or {})
                if tool_results and self._is_insubstantial_final_answer(final_answer):
                    final_answer = self._fallback_answer_from_tool_results(request=request, tool_results=tool_results)
                    final_metadata = {
                        **final_metadata,
                        "model_path": "project_tool_result_summary",
                        "fallback_reason": "insubstantial_model_final_answer_after_tools",
                    }
                completion_gap = self._long_task_completion_gap(request=request, final_answer=final_answer, tool_results=tool_results)
                if completion_gap:
                    final_answer = f"{final_answer}\n\n{completion_gap}".strip()
                    final_metadata.setdefault("fallback_reason", "long_task_completion_ledger_missing")
                    final_metadata["long_task_completion_gap"] = True
                self._emit_loop_state(
                    emit,
                    request=request,
                    phase="final_answer",
                    iteration=iteration,
                    tool_call_count=tool_call_count,
                    transition_reason="final_answer",
                    stop_reason="final_answer",
                )
                self._emit_answer_stream_chunks(emit, request=request, final_answer=final_answer, metadata=final_metadata)
                self._emit(emit, "assistant_message", request=request, payload={"content": final_answer, **final_metadata})
                self._emit(emit, "final_answer", request=request, payload={"final_answer": final_answer, **final_metadata})
                return AgentCoreRunResult(
                    session_id=request.session_id,
                    turn_id=request.turn_id,
                    events=tuple(events),
                    final_answer=final_answer,
                    tool_results=tuple(tool_results),
                    stop_reason="final_answer",
                )
            if step.step_type != "tool_calls":
                error = {"code": "unsupported_model_step", "message": f"Unsupported model step: {step.step_type}"}
                self._emit_loop_state(
                    emit,
                    request=request,
                    phase="error",
                    iteration=iteration,
                    tool_call_count=tool_call_count,
                    transition_reason="unsupported_model_step",
                    stop_reason="error",
                )
                self._emit(emit, "error", request=request, payload={"error": error})
                return AgentCoreRunResult(
                    session_id=request.session_id,
                    turn_id=request.turn_id,
                    events=tuple(events),
                    final_answer=final_answer,
                    tool_results=tuple(tool_results),
                    stop_reason="error",
                )
            if not step.tool_calls:
                self._emit_loop_state(
                    emit,
                    request=request,
                    phase="final_answer",
                    iteration=iteration,
                    tool_call_count=tool_call_count,
                    transition_reason="no_more_tools",
                    stop_reason="no_more_tools",
                )
                self._emit_answer_stream_chunks(emit, request=request, final_answer=final_answer, metadata=step.metadata)
                self._emit(emit, "final_answer", request=request, payload={"final_answer": final_answer, **step.metadata})
                return AgentCoreRunResult(
                    session_id=request.session_id,
                    turn_id=request.turn_id,
                    events=tuple(events),
                    final_answer=final_answer,
                    tool_results=tuple(tool_results),
                    stop_reason="no_more_tools",
                )
            for raw_tool_call in step.tool_calls:
                tool_results_before_iteration = len(tool_results)
                tool_call = self._normalize_tool_call_for_request(request=request, tool_call=raw_tool_call)
                if tool_call_count >= request.max_tool_calls:
                    self._emit_loop_state(
                        emit,
                        request=request,
                        phase="blocked",
                        iteration=iteration,
                        tool_call_count=tool_call_count,
                        transition_reason="max_tool_calls_exceeded",
                        stop_reason="max_tool_calls_exceeded",
                    )
                    return AgentCoreRunResult(
                        session_id=request.session_id,
                        turn_id=request.turn_id,
                        events=tuple(events),
                        final_answer=final_answer,
                        tool_results=tuple(tool_results),
                        stop_reason="max_tool_calls_exceeded",
                    )
                validation_result = self._schema_validation_result_if_invalid(tool_call)
                if validation_result is not None:
                    self._emit(
                        emit,
                        "tool_call_requested",
                        request=request,
                        call_id=tool_call.call_id,
                        payload={"tool_call": tool_call.to_dict(), "permission": "not_required", "validation": "failed"},
                    )
                    self._emit(emit, "tool_result", request=request, call_id=tool_call.call_id, payload=validation_result.to_dict())
                    tool_results.append(validation_result)
                    transcript.append({"role": "tool", "tool_result": self._tool_result_for_transcript(validation_result)})
                    tool_call_count += 1
                    continue
                permission = self._permission_request_if_needed(request=request, tool_call=tool_call)
                if permission is not None:
                    self._emit_loop_state(
                        emit,
                        request=request,
                        phase="approval",
                        iteration=iteration,
                        tool_call_count=tool_call_count,
                        pending_tool_count=1,
                        transition_reason="permission_requested",
                        stop_reason="permission_requested",
                    )
                    self._emit(
                        emit,
                        "tool_call_requested",
                        request=request,
                        call_id=tool_call.call_id,
                        payload={"tool_call": tool_call.to_dict(), "permission": "ask"},
                    )
                    self._emit(
                        emit,
                        "permission_requested",
                        request=request,
                        call_id=tool_call.call_id,
                        payload=permission.to_dict(),
                    )
                    return AgentCoreRunResult(
                        session_id=request.session_id,
                        turn_id=request.turn_id,
                        events=tuple(events),
                        final_answer="",
                        tool_results=tuple(tool_results),
                        permission_request=permission,
                        stop_reason="permission_requested",
                    )
                result = self._execute_tool_call(request=request, tool_call=tool_call, emit=emit)
                tool_results.append(result)
                transcript.append({"role": "tool", "tool_result": self._tool_result_for_transcript(result)})
                transcript = self._compact_transcript_if_needed(request=request, transcript=transcript, emit=emit)
                tool_call_count += 1
            if len(tool_results) > tool_results_before_iteration and self._should_auto_answer_after_project_tools(request, tool_results[tool_results_before_iteration:]):
                final_answer = self._fallback_answer_from_tool_results(request=request, tool_results=tool_results)
                self._emit_loop_state(
                    emit,
                    request=request,
                    phase="final_answer",
                    iteration=iteration,
                    tool_call_count=tool_call_count,
                    transition_reason="project_tool_results_summarized",
                    stop_reason="final_answer",
                )
                self._emit_answer_stream_chunks(
                    emit,
                    request=request,
                    final_answer=final_answer,
                    metadata={"model_path": "project_tool_result_summary"},
                )
                self._emit(emit, "assistant_message", request=request, payload={"content": final_answer, "model_path": "project_tool_result_summary"})
                self._emit(emit, "final_answer", request=request, payload={"final_answer": final_answer, "model_path": "project_tool_result_summary"})
                return AgentCoreRunResult(
                    session_id=request.session_id,
                    turn_id=request.turn_id,
                    events=tuple(events),
                    final_answer=final_answer,
                    tool_results=tuple(tool_results),
                    stop_reason="final_answer",
                )

        self._emit_loop_state(
            emit,
            request=request,
            phase="blocked",
            iteration=max(1, int(request.max_iterations)),
            tool_call_count=tool_call_count,
            transition_reason="max_iterations_exceeded",
            stop_reason="max_iterations_exceeded",
        )
        return AgentCoreRunResult(
            session_id=request.session_id,
            turn_id=request.turn_id,
            events=tuple(events),
            final_answer=final_answer,
            tool_results=tuple(tool_results),
            stop_reason="max_iterations_exceeded",
        )

    def _execute_tool_call(
        self,
        *,
        request: AgentCoreRequest,
        tool_call: CoreToolCall,
        emit: Any,
        skip_permission: bool = False,
    ) -> CoreToolResult:
        tool_call = self._normalize_tool_call_for_request(request=request, tool_call=tool_call)
        spec = self._tool_spec(tool_call.tool_name)
        validation_result = self._schema_validation_result_if_invalid(tool_call, tool_spec=spec)
        if validation_result is not None:
            self._emit(
                emit,
                "tool_call_requested",
                request=request,
                call_id=tool_call.call_id,
                payload={"tool_call": tool_call.to_dict(), "permission": "not_required", "validation": "failed"},
            )
            self._emit(emit, "tool_result", request=request, call_id=tool_call.call_id, payload=validation_result.to_dict())
            return validation_result
        if spec.permission == "deny":
            result = CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Tool {tool_call.tool_name} is denied by policy.",
                ui_summary=f"Tool {tool_call.tool_name} is denied by policy.",
                error={"code": "tool_permission_denied", "message": "tool is denied by policy"},
                retry_hint="Use an allowed tool or ask the user to choose a supported action.",
            )
            self._emit(
                emit,
                "tool_call_requested",
                request=request,
                call_id=tool_call.call_id,
                payload={"tool_call": tool_call.to_dict(), "permission": "deny"},
            )
            self._emit(emit, "tool_result", request=request, call_id=tool_call.call_id, payload=result.to_dict())
            return result
        self._emit(
            emit,
            "tool_call_requested",
            request=request,
            call_id=tool_call.call_id,
            payload={"tool_call": tool_call.to_dict(), "permission": self._execution_permission_label(request=request, spec=spec, skip_permission=skip_permission)},
        )
        self._emit(
            emit,
            "tool_call_started",
            request=request,
            call_id=tool_call.call_id,
            payload={"tool_call": tool_call.to_dict(), "tool_spec": spec.to_dict()},
        )
        try:
            result = self.tool_registry.execute_tool(
                tool_call=tool_call,
                tool_spec=spec,
                request=request,
                emit=emit,
            )
        except Exception as exc:  # noqa: BLE001
            result = CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="failed",
                model_summary=f"Tool {tool_call.tool_name} failed: {exc}",
                error={"code": exc.__class__.__name__, "message": str(exc)},
        )
        self._emit(emit, "tool_result", request=request, call_id=tool_call.call_id, payload=result.to_dict())
        return result

    @staticmethod
    def _initial_transcript(request: AgentCoreRequest) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        context = dict(request.context or {})
        for item in list(context.get("prior_transcript") or [])[-10:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            if role not in {"user", "assistant"}:
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            out.append({"role": role, "content": content[:4000]})
        return out

    def _emit_answer_stream_chunks(
        self,
        emit: Callable[[CoreEvent], None],
        *,
        request: AgentCoreRequest,
        final_answer: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit answer text as assistant_delta chunks for UI streaming.

        The current provider boundary returns a complete model step rather than
        raw provider tokens. These chunks are therefore a stable AgentCore
        stream of the final text, and can be replaced by provider-native token
        streaming later without changing frontend event contracts.
        """

        if not bool((request.context or {}).get("stream")):
            return
        text = str(final_answer or "")
        if not text:
            return
        base = dict(metadata or {})
        base.setdefault("contract_version", "agent_core.answer_delta.v1")
        base.setdefault("phase", "final_answer")
        base.setdefault("status", "streaming")
        chunks = list(self._answer_stream_chunks(text))
        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            self._emit(
                emit,
                "assistant_delta",
                request=request,
                payload={
                    **base,
                    "delta": chunk,
                    "chunk_index": index,
                    "chunk_count": total,
                    "stream_kind": "answer_text",
                    "provider_native_tokens": False,
                },
            )

    @staticmethod
    def _answer_stream_chunks(text: str, *, target_chars: int = 10) -> list[str]:
        chunks: list[str] = []
        buffer = ""
        hard_breaks = set("\n。！？!?；;，,、 ")
        for char in text:
            buffer += char
            if len(buffer) >= target_chars or (len(buffer) >= 4 and char in hard_breaks):
                chunks.append(buffer)
                buffer = ""
        if buffer:
            chunks.append(buffer)
        return chunks

    @classmethod
    def _tool_result_for_transcript(cls, result: CoreToolResult) -> dict[str, Any]:
        payload = result.to_dict()
        payload["structured_content"] = cls._compact_structured_content_for_model(
            result.tool_name,
            payload.get("structured_content"),
        )
        return payload

    @classmethod
    def _compact_structured_content_for_model(cls, tool_name: str, value: Any) -> Any:
        name = str(tool_name or "").strip()
        if not isinstance(value, dict):
            return cls._compact_value_for_model(value, max_items=5, max_chars=700)
        payload = dict(value or {})
        wrapped = payload.get("result") if isinstance(payload.get("result"), dict) else None
        body = dict(wrapped or payload)
        if name == "project.structured_data.search":
            compact = {
                "project_key": body.get("project_key"),
                "query": body.get("query"),
                "query_mode": body.get("query_mode"),
                "total_matches": body.get("total_matches"),
                "total_stored_rows": body.get("total_stored_rows"),
                "dataset_counts": dict(body.get("dataset_counts") or {}),
                "dataset_total_rows": dict(body.get("dataset_total_rows") or {}),
                "items": cls._compact_value_for_model(body.get("items"), max_items=8, max_chars=1400),
                "model_evidence_manifest": cls._compact_value_for_model(body.get("model_evidence_manifest"), max_items=12, max_chars=900),
                "inventory": cls._compact_value_for_model(body.get("inventory"), max_items=12, max_chars=700),
                "fallback_used": body.get("fallback_used"),
                "errors": cls._compact_value_for_model(body.get("errors"), max_items=6, max_chars=700),
            }
            compact["omitted_read_handles"] = cls._omitted_read_handles(body.get("model_evidence_manifest"), kept=12)
            return {"result": compact} if wrapped is not None else compact
        if name == "project.context.bundle":
            compact = {
                "project_key": body.get("project_key"),
                "query": body.get("query"),
                "material_intent": cls._compact_value_for_model(body.get("material_intent"), max_items=8, max_chars=700),
                "material_categories": cls._compact_value_for_model(body.get("material_categories"), max_items=8, max_chars=700),
                "model_evidence_manifest": cls._compact_value_for_model(body.get("model_evidence_manifest"), max_items=16, max_chars=900),
                "evidence": cls._compact_value_for_model(body.get("evidence"), max_items=16, max_chars=900),
                "missing_evidence": cls._compact_value_for_model(body.get("missing_evidence"), max_items=6, max_chars=700),
                "source_catalog_note": body.get("source_catalog_note"),
            }
            components = dict(body.get("components") or {})
            structured = dict(components.get("structured_data") or {})
            if structured:
                compact["components"] = {
                    "structured_data": {
                        "total_matches": structured.get("total_matches"),
                        "total_stored_rows": structured.get("total_stored_rows"),
                        "dataset_counts": dict(structured.get("dataset_counts") or {}),
                        "items": cls._compact_value_for_model(structured.get("items"), max_items=6, max_chars=900),
                        "model_evidence_manifest": cls._compact_value_for_model(structured.get("model_evidence_manifest"), max_items=8, max_chars=700),
                    }
                }
            compact["omitted_read_handles"] = cls._omitted_read_handles(body.get("model_evidence_manifest"), kept=16)
            return {"result": compact} if wrapped is not None else compact
        if name in {
            "project.structured_data.item.read",
            "project.structured_data.items.read",
            "project.context.resource.read",
            "writing.document.section.read",
            "writing.document.read",
            "agent_artifact.read",
        }:
            compact = cls._compact_value_for_model(body, max_items=14, max_chars=2500)
            return {"result": compact} if wrapped is not None else compact
        return cls._compact_value_for_model(value, max_items=5, max_chars=700)

    @classmethod
    def _omitted_read_handles(cls, manifest: Any, *, kept: int) -> list[dict[str, Any]]:
        if not isinstance(manifest, list) or len(manifest) <= kept:
            return []
        handles: list[dict[str, Any]] = []
        for item in manifest[kept: kept + 12]:
            if not isinstance(item, dict):
                continue
            handles.append(
                {
                    "item_id": item.get("item_id"),
                    "resource_uri": item.get("resource_uri"),
                    "read_tool": item.get("read_tool"),
                    "read_arguments": item.get("read_arguments"),
                    "title": item.get("title"),
                }
            )
        return handles

    @classmethod
    def _compact_value_for_model(cls, value: Any, *, max_items: int, max_chars: int) -> Any:
        if value is None or isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, str):
            return value[:max_chars] + ("...[truncated]" if len(value) > max_chars else "")
        if isinstance(value, dict):
            items = list(value.items())
            out: dict[str, Any] = {}
            for key, item in items[:max_items]:
                out[str(key)] = cls._compact_value_for_model(item, max_items=max_items, max_chars=max_chars)
            if len(items) > max_items:
                out["_truncated"] = True
                out["_omitted_count"] = len(items) - max_items
            return out
        if isinstance(value, (list, tuple)):
            items = list(value)
            out = [cls._compact_value_for_model(item, max_items=max_items, max_chars=max_chars) for item in items[:max_items]]
            if len(items) > max_items:
                out.append({"_truncated": True, "_omitted_count": len(items) - max_items})
            return out
        text = str(value)
        return text[:max_chars] + ("...[truncated]" if len(text) > max_chars else "")

    @staticmethod
    def _should_auto_answer_after_project_tools(request: AgentCoreRequest, new_results: list[CoreToolResult]) -> bool:
        context = dict(request.context or {})
        if not bool(context.get("agent_core_auto_answer_after_project_tools")):
            return False
        return any(
            result.tool_name
            in {
                "project.summary.read",
                "project.structured_data.search",
                "project.structured_data.quality_audit",
                "project.structured_graph.query",
                "project.graph.search",
                "source_library.item.list",
            }
            for result in new_results
        )

    @staticmethod
    def _fallback_answer_from_tool_results(*, request: AgentCoreRequest, tool_results: list[CoreToolResult]) -> str:
        lines: list[str] = ["我已根据项目里已经存储的数据做了检索和汇总。"]
        for result in tool_results:
            content = dict(result.structured_content or {})
            payload = content.get("result") if isinstance(content.get("result"), dict) else content
            if result.tool_name == "project.summary.read":
                source_library = payload.get("source_library") if isinstance(payload.get("source_library"), dict) else {}
                session_counts = payload.get("session_counts") if isinstance(payload.get("session_counts"), dict) else {}
                if source_library:
                    lines.append(f"- 来源库/采集入口：{source_library.get('total', 0)} 个，启用 {source_library.get('enabled', 0)} 个。")
                if session_counts:
                    lines.append(
                        "- 当前会话数据："
                        f"{session_counts.get('tasks', 0)} 个任务、"
                        f"{session_counts.get('events', 0)} 个事件、"
                        f"{session_counts.get('artifacts', 0)} 个产物。"
                    )
            elif result.tool_name == "source_library.item.list":
                total = payload.get("total")
                if total is not None:
                    lines.append(f"- 来源库条目：共 {total} 个可用条目。")
            elif result.tool_name == "project.structured_data.search":
                query = str(payload.get("query") or request.message or "").strip()
                total_matches = payload.get("total_matches")
                dataset_counts = payload.get("dataset_counts") if isinstance(payload.get("dataset_counts"), dict) else {}
                if total_matches is not None:
                    lines.append(f"- 结构化数据检索：关键词 `{query}` 匹配 {total_matches} 条记录。")
                if dataset_counts:
                    counts = "、".join(f"{key}: {value}" for key, value in list(dataset_counts.items())[:6])
                    lines.append(f"- 命中的数据集：{counts}。")
                items = list(payload.get("items") or []) if isinstance(payload.get("items"), list) else []
                if items:
                    lines.append("- 代表性记录：")
                    for item in items[:5]:
                        if not isinstance(item, dict):
                            continue
                        title = str(item.get("title") or item.get("label") or item.get("record_id") or "未命名记录").strip()
                        dataset = str(item.get("dataset") or "").strip()
                        summary = " ".join(str(item.get("summary") or "").split())[:160]
                        prefix = f"  - `{dataset}` " if dataset else "  - "
                        lines.append(f"{prefix}{title}{f'：{summary}' if summary else ''}")
            elif result.tool_name == "project.structured_data.quality_audit":
                scanned = payload.get("scanned") if isinstance(payload.get("scanned"), dict) else {}
                noisy_count = int(payload.get("noisy_record_count") or 0)
                by_dataset = payload.get("by_dataset") if isinstance(payload.get("by_dataset"), dict) else {}
                by_reason = payload.get("by_reason") if isinstance(payload.get("by_reason"), dict) else {}
                if scanned:
                    scanned_text = "、".join(f"{key}: {value}" for key, value in scanned.items())
                    lines.append(f"- 数据质量审计：扫描 {scanned_text}，发现 {noisy_count} 条疑似网页壳/脚本/CSS/导航噪声记录。")
                else:
                    lines.append(f"- 数据质量审计：发现 {noisy_count} 条疑似网页壳/脚本/CSS/导航噪声记录。")
                if by_dataset:
                    lines.append("- 噪声分布：" + "、".join(f"{key}: {value}" for key, value in by_dataset.items()) + "。")
                if by_reason:
                    lines.append("- 主要原因：" + "、".join(f"{key}: {value}" for key, value in list(by_reason.items())[:5]) + "。")
                samples = [item for item in list(payload.get("samples") or []) if isinstance(item, dict)]
                if samples:
                    lines.append("- 样本记录：")
                    for item in samples[:3]:
                        title = str(item.get("title") or item.get("record_id") or "未命名记录").strip()
                        dataset = str(item.get("dataset") or "").strip()
                        reasons = ", ".join(str(reason) for reason in list(item.get("noise_reasons") or [])[:4])
                        action = str(item.get("recommended_action") or "").strip()
                        lines.append(f"  - `{dataset}` {title}：{reasons}{f'；建议 {action}' if action else ''}")
                actions = [str(item).strip() for item in list(payload.get("recommended_actions") or []) if str(item).strip()]
                if actions:
                    lines.append("- 建议动作：" + "；".join(actions[:3]) + "。")
            elif result.tool_name in {"project.structured_graph.query", "project.graph.search"}:
                count = payload.get("total_matches") or payload.get("count") or payload.get("total")
                if count is not None:
                    lines.append(f"- 图谱/实体结果：找到 {count} 条相关线索。")
        if len(lines) == 1:
            lines.append("工具已经完成，但返回的数据较少；可以继续指定数据集、关键词或要展开的字段。")
        for result in tool_results:
            content = dict(result.structured_content or {})
            payload = content.get("result") if isinstance(content.get("result"), dict) else content
            if result.tool_name == "source.discovery.plan":
                query_count = payload.get("query_count") or payload.get("planned_query_count")
                direction_count = payload.get("direction_count") or payload.get("source_direction_count")
                accepted = payload.get("accepted_urls")
                if query_count or direction_count or accepted is not None:
                    lines.append(
                        "- 外部资料发现计划："
                        f"{query_count or 0} 个检索式、{direction_count or 0} 个方向、"
                        f"已接受候选 {accepted if accepted is not None else 0} 个。"
                    )
            elif result.tool_name == "agent_investigation.leads.append":
                state = payload.get("state") if isinstance(payload.get("state"), dict) else payload
                clue_nodes = state.get("clue_nodes") or state.get("node_count")
                clue_edges = state.get("clue_edges") or state.get("edge_count")
                pending = state.get("pending_questions")
                if clue_nodes is not None or clue_edges is not None:
                    lines.append(f"- 调查线索：记录 {clue_nodes or 0} 个节点、{clue_edges or 0} 条关系，待追问 {pending or 0} 个。")
            elif result.tool_name == "agent_investigation.trace.read":
                nodes = payload.get("clue_nodes") or payload.get("nodes")
                edges = payload.get("clue_edges") or payload.get("edges")
                node_count = len(nodes) if isinstance(nodes, list) else payload.get("node_count")
                edge_count = len(edges) if isinstance(edges, list) else payload.get("edge_count")
                if node_count is not None or edge_count is not None:
                    lines.append(f"- 当前线索图：可继续追踪 {node_count or 0} 个节点、{edge_count or 0} 条边。")
            elif result.tool_name == "writing.document.insert_paragraph":
                doc = payload.get("document") if isinstance(payload.get("document"), dict) else {}
                diff = payload.get("diff") if isinstance(payload.get("diff"), dict) else {}
                title = str(doc.get("title") or payload.get("title") or "写作文档").strip()
                version = doc.get("version") or payload.get("version")
                added = diff.get("added_lines")
                removed = diff.get("removed_lines")
                lines.append(
                    f"- 写作工作台：已更新《{title}》"
                    f"{f' v{version}' if version else ''}"
                    f"{f'，新增 {added} 行、删除 {removed or 0} 行' if added is not None else ''}。"
                )
            elif result.tool_name == "ingest.source_library.run":
                items = payload.get("items")
                task_ids = payload.get("task_ids")
                item_count = len(items) if isinstance(items, list) else 0
                task_count = len(task_ids) if isinstance(task_ids, list) else 0
                lines.append(f"- 来源库采集：已提交 {item_count} 个条目，返回 {task_count} 个任务 ID；后续应读取 ingest 状态或任务产物确认入库结果。")
            elif result.tool_name not in {
                "project.summary.read",
                "source_library.item.list",
                "project.structured_data.search",
                "project.structured_data.quality_audit",
                "project.structured_graph.query",
                "project.graph.search",
            }:
                summary = str(result.model_summary or result.ui_summary or "").strip()
                if summary:
                    lines.append(f"- {result.tool_name}: {summary[:240]}")
        lines.append("可以继续让我按某个数据集、来源或实体线索展开。")
        return "\n".join(lines)

    @staticmethod
    def _is_insubstantial_final_answer(final_answer: str) -> bool:
        text = " ".join(str(final_answer or "").split())
        if not text:
            return True
        normalized = text.strip("。.!！ ")
        formal_answers = {
            "我已经完成本轮处理",
            "已完成本轮处理",
            "已写入并复核工作台文稿",
            "已完成调查、追踪、写作和恢复上下文闭环",
            "长任务多轮工具循环已完成",
            "项目摘要已读取",
            "已直接提交来源库补证据任务",
        }
        if normalized in formal_answers:
            return True
        if len(text) <= 24 and any(token in text for token in ("完成", "已写入", "已提交", "已读取", "queued", "updated")):
            return True
        return False

    @classmethod
    def _long_task_completion_gap(
        cls,
        *,
        request: AgentCoreRequest,
        final_answer: str,
        tool_results: list[CoreToolResult],
    ) -> str:
        context = dict(request.context or {})
        profile = str(context.get("tool_window_profile") or "").lower()
        message = str(request.message or "")
        if "long" not in profile and not any(token in message for token in ("长任务", "持续", "多轮", "追查", "调查", "长程")):
            return ""
        text = str(final_answer or "")
        if not any(token in text.lower() for token in ("完成", "done", "已完成", "闭环")):
            return ""
        has_stage_tool = False
        has_done_stage = False
        for result in tool_results:
            if result.tool_name not in {"agent_long_task.stage.update", "agent_long_task.stage.read"}:
                continue
            has_stage_tool = True
            content = dict(result.structured_content or {})
            state = content.get("state") if isinstance(content.get("state"), dict) else {}
            current_stage = str(state.get("current_stage") or "").strip()
            completed = {str(item or "").strip() for item in list(state.get("completed_stages") or [])}
            if current_stage == "done" or "done" in completed:
                has_done_stage = True
        if has_done_stage:
            return ""
        if has_stage_tool:
            return "长任务阶段 ledger 尚未到达 `done`；本轮不能仅按自然语言视为完全完成，后续需要继续推进未完成 stage 或写入 verification/done 阶段。"
        return "长任务阶段 ledger 尚未写入；本轮只能视为阶段性结果，后续需要调用 `agent_task.plan.append` / `agent_long_task.stage.update` 记录 plan、证据、写作、verification 与 done 状态。"

    def _compact_transcript_if_needed(
        self,
        *,
        request: AgentCoreRequest,
        transcript: list[dict[str, Any]],
        emit: Any,
    ) -> list[dict[str, Any]]:
        context = dict(request.context or {})
        try:
            threshold = int(context.get("agent_core_compact_threshold_chars") or 16000)
        except Exception:
            threshold = 16000
        threshold = max(200, threshold)
        total_chars = sum(len(str(item)) for item in transcript)
        if total_chars <= threshold:
            return transcript

        keep = transcript[-6:]
        older = transcript[:-6]
        summary_lines: list[str] = []
        for item in older[-12:]:
            role = str(item.get("role") or "").strip()
            if role == "tool":
                result = dict(item.get("tool_result") or {})
                summary_lines.append(
                    f"tool {result.get('tool_name')} status={result.get('status')}: {str(result.get('model_summary') or '')[:500]}"
                )
            else:
                summary_lines.append(f"{role}: {str(item.get('content') or item.get('delta') or '')[:500]}")
        compact = {
            "role": "assistant",
            "content": "Reactive compacted prior AgentCore transcript:\n" + "\n".join(line for line in summary_lines if line.strip()),
            "metadata": {
                "compact_kind": "reactive",
                "contract_version": "agent_core.compact_context.v1",
                "compacted_items": len(older),
                "pre_compact_chars": total_chars,
            },
        }
        self._emit(
            emit,
            "run_compacted",
            request=request,
            payload={
                "contract_version": "agent_core.compact_context.v1",
                "compact_kind": "reactive",
                "compacted_items": len(older),
                "pre_compact_chars": total_chars,
                "kept_items": len(keep),
            },
        )
        return [compact, *keep]

    def _emit_loop_state(
        self,
        emit: Any,
        *,
        request: AgentCoreRequest,
        phase: str,
        iteration: int,
        tool_call_count: int,
        transition_reason: str,
        pending_tool_count: int = 0,
        stop_reason: str | None = None,
    ) -> None:
        if not bool((request.context or {}).get("agent_core_emit_turn_state_events")):
            return
        payload = {
            "contract_version": "agent_core.loop_state.v1",
            "phase": phase,
            "iteration": int(iteration),
            "max_iterations": int(request.max_iterations),
            "tool_call_count": int(tool_call_count),
            "max_tool_calls": int(request.max_tool_calls),
            "remaining_tool_calls": max(0, int(request.max_tool_calls) - int(tool_call_count)),
            "pending_tool_count": int(pending_tool_count),
            "transition_reason": transition_reason,
        }
        if stop_reason:
            payload["stop_reason"] = stop_reason
        self._emit(emit, "turn_state", request=request, payload=payload)

    def _permission_request_if_needed(
        self,
        *,
        request: AgentCoreRequest,
        tool_call: CoreToolCall,
    ) -> CorePermissionRequest | None:
        spec = self._tool_spec(tool_call.tool_name)
        if not self._approval_gate_enabled(request):
            return None
        if tool_call.call_id in set(request.approved_call_ids or ()):
            return None
        if spec.permission == "allow":
            if spec.risk == "read_only":
                return None
            if spec.risk == "write_shared" and bool((spec.metadata or {}).get("auto_allow_session_write")):
                return None
        if spec.permission == "deny":
            return None
        if spec.permission in {"ask", "explicit_user_request"} or spec.risk in {"write_shared", "write_external", "privileged"}:
            return CorePermissionRequest(
                approval_id=new_core_id("approval"),
                session_id=request.session_id,
                turn_id=request.turn_id,
                tool_call=tool_call,
                tool_spec=spec,
                reason="tool requires approval before execution",
            )
        return None

    @staticmethod
    def _approval_gate_enabled(request: AgentCoreRequest) -> bool:
        if request.approval_policy == "enabled":
            return True
        context = dict(request.context or {})
        if context.get("agent_core_approval_policy") == "enabled":
            return True
        return False

    def _execution_permission_label(self, *, request: AgentCoreRequest, spec: CoreToolSpec, skip_permission: bool = False) -> str:
        if skip_permission:
            return "allow"
        if spec.permission in {"ask", "explicit_user_request"} and not self._approval_gate_enabled(request):
            return "allow"
        return spec.permission

    def _tool_specs_for_model(self, request: AgentCoreRequest) -> list[CoreToolSpec]:
        if self._approval_gate_enabled(request):
            return list(self.tool_specs)
        out: list[CoreToolSpec] = []
        for spec in self.tool_specs:
            if spec.permission in {"ask", "explicit_user_request"}:
                out.append(
                    replace(
                        spec,
                        permission="allow",
                        metadata={**dict(spec.metadata or {}), "approval_policy": "frozen"},
                    )
                )
            else:
                out.append(spec)
        return out

    def _schema_validation_result_if_invalid(
        self,
        tool_call: CoreToolCall,
        *,
        tool_spec: CoreToolSpec | None = None,
    ) -> CoreToolResult | None:
        spec = tool_spec or self._tool_spec(tool_call.tool_name)
        errors = validate_tool_arguments(arguments=dict(tool_call.arguments or {}), input_schema=spec.input_schema)
        if not errors:
            return None
        summary = summarize_validation_errors(errors)
        return CoreToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="failed",
            model_summary=f"Tool {tool_call.tool_name} arguments failed schema validation: {summary}.",
            ui_summary=f"Tool arguments need correction: {summary}.",
            structured_content={
                "contract_version": "agent_core.tool_schema_validation.v1",
                "tool_name": tool_call.tool_name,
                "validation_errors": errors,
                "recoverable": True,
                "provided_arguments": dict(tool_call.arguments or {}),
            },
            error={
                "code": "tool_schema_validation_failed",
                "message": summary,
                "recoverable": True,
            },
            retry_hint="Retry the tool call with arguments that match input_schema. Ask the user only if required values are not available from context.",
        )

    def _normalize_tool_call_for_request(self, *, request: AgentCoreRequest, tool_call: CoreToolCall) -> CoreToolCall:
        spec = self._tool_spec(tool_call.tool_name)
        schema = dict(spec.input_schema or {})
        properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = set(schema.get("required") or [])
        arguments = dict(tool_call.arguments or {})
        changed = False

        if ("project_key" in required or "project_key" in properties) and not str(arguments.get("project_key") or "").strip():
            if request.project_key:
                arguments["project_key"] = request.project_key
                changed = True

        if tool_call.tool_name == "ingest.source_library.run" and not arguments.get("items"):
            item_key = str(arguments.get("item_key") or "").strip()
            if item_key:
                arguments["items"] = [item_key]
                changed = True

        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            for key in ("project_key", "session_id", "turn_id", "item_key"):
                if key in arguments and key not in properties:
                    arguments.pop(key, None)
                    changed = True

        if not changed:
            return tool_call
        return CoreToolCall(
            tool_name=tool_call.tool_name,
            arguments=arguments,
            call_id=tool_call.call_id,
            reason=tool_call.reason,
        )

    def _tool_spec(self, tool_name: str) -> CoreToolSpec:
        for spec in self.policy_tool_specs:
            if spec.name == tool_name:
                return spec
        return CoreToolSpec(
            name=tool_name,
            title=tool_name,
            description_for_model=f"Unregistered tool {tool_name}",
            source="project",
            risk="privileged",
            permission="ask",
            concurrency="exclusive",
        )

    @staticmethod
    def _emit(
        emit: Any,
        event_type: str,
        *,
        request: AgentCoreRequest,
        payload: dict[str, Any],
        call_id: str | None = None,
        actor: str = "agent_core",
    ) -> None:
        emit(
            CoreEvent(
                event_type=event_type,  # type: ignore[arg-type]
                session_id=request.session_id,
                turn_id=request.turn_id,
                call_id=call_id,
                actor=actor,
                payload=payload,
            )
        )
