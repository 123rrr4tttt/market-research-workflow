from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from time import monotonic
from typing import Any, Protocol

from .capability_registry import is_read_only_capability_id
from .read_only_tools import ReadOnlyAgentToolRuntime
from .tool_contract import RUN_LOOP_CONTRACT_VERSION
from .tool_execution import ToolCallExecutionRecord, ToolExecutionHooks, ToolExecutionPolicy, is_abort_requested


AgentRunLoopEventSink = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class AgentRunLoopBudget:
    max_iterations: int = 3
    max_tool_calls: int = 8
    max_seconds: float = 20.0
    max_result_chars: int = 12000

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_iterations": self.max_iterations,
            "max_tool_calls": self.max_tool_calls,
            "max_seconds": self.max_seconds,
            "max_result_chars": self.max_result_chars,
        }


@dataclass(frozen=True)
class AgentRunLoopContext:
    turn_id: str
    session_id: str
    project_key: str | None
    message: str
    selected_capability_ids: tuple[str, ...]
    agent_mode: str
    abort_signal: Any | None = None


class AgentRunLoopPlanner(Protocol):
    def plan_next(
        self,
        *,
        context: AgentRunLoopContext,
        available_tools: list[dict[str, Any]],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class HeuristicAgentRunLoopPlanner:
    """Deterministic planner used until the model-native planner is enabled."""

    def plan_next(
        self,
        *,
        context: AgentRunLoopContext,
        available_tools: list[dict[str, Any]],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> dict[str, Any]:
        if transcript:
            return {
                "model_path": "heuristic",
                "tool_calls": [],
                "final_answer": self._final_answer_from_transcript(context, transcript),
                "stop": True,
            }
        available = {str(tool.get("name") or "") for tool in available_tools}
        tool_calls: list[dict[str, Any]] = []
        for capability_id in context.selected_capability_ids:
            if capability_id not in available:
                continue
            if not is_read_only_capability_id(capability_id):
                continue
            tool_calls.append(
                {
                    "tool_name": capability_id,
                    "input": self._default_input(capability_id, context),
                    "reason": "selected by compatibility capability planner",
                }
            )
        return {
            "model_path": "heuristic",
            "tool_calls": tool_calls,
            "final_answer": None,
            "stop": True,
        }

    @staticmethod
    def _final_answer_from_transcript(context: AgentRunLoopContext, transcript: list[dict[str, Any]]) -> str:
        calls = [dict(item.get("call") or {}) for item in transcript[-8:]]
        by_id = {str(call.get("capability_id") or call.get("tool_name") or ""): call for call in calls}
        failed = [
            f"{call.get('capability_id') or call.get('tool_name')}: {call.get('summary') or call.get('status')}"
            for call in calls
            if str(call.get("status") or "") == "failed"
        ]
        if failed:
            return "我查到有工具返回失败，先把可见原因列出来：" + "；".join(failed[:3]) + "。"

        capability_call = by_id.get("agent_runtime.capability.catalog")
        tool_pool_call = by_id.get("agent_runtime.tool_pool.list")
        if capability_call or tool_pool_call:
            capability_total = dict(capability_call.get("result") or {}).get("total") if capability_call else None
            pool = dict(tool_pool_call.get("result") or {}) if tool_pool_call else {}
            counts = dict(pool.get("counts") or {})
            parts = ["可以。我现在可以先回答能力、状态、项目、来源库、workflow、ingest 和 artifact 这类基础问题，不需要提交后台任务。"]
            if capability_total:
                parts.append(f"当前登记了 {capability_total} 个 agent 能力。")
            if counts:
                parts.append(
                    "工具池里有 "
                    f"{counts.get('core') or 0} 个核心工具、{counts.get('deferred') or 0} 个延迟/审批型工具，"
                    f"{counts.get('approval_required') or 0} 个动作需要确认。"
                )
            parts.append("真正会写入、联网或产生成本的动作会先进入审批卡片；普通查询会直接在对话里返回。")
            return "".join(parts)

        source_call = by_id.get("source_library.item.list") or by_id.get("source_library.item.search")
        if source_call:
            result = dict(source_call.get("result") or {})
            items = [dict(item or {}) for item in list(result.get("items") or [])[:5]]
            names = [
                str(item.get("item_key") or item.get("name") or "").strip()
                for item in items
                if str(item.get("item_key") or item.get("name") or "").strip()
            ]
            total = result.get("total")
            sample = "，示例：" + "、".join(names) if names else ""
            return f"我查了当前项目的来源库，可匹配 {total or 0} 个 item{sample}。这一步只是读取目录，没有触发外部采集。"

        bundle_call = by_id.get("project.context.bundle")
        if bundle_call:
            result = dict(bundle_call.get("result") or {})
            categories = dict(result.get("material_categories") or {})
            existing = dict(categories.get("internal_existing") or {})
            generated = dict(categories.get("internal_generated") or {})
            source_catalog = dict(categories.get("source_catalog") or {})
            missing = list(result.get("missing_evidence") or [])
            return (
                "我整理了当前项目材料上下文："
                f"内部已有资料包含 {existing.get('structured_datasets') or 0} 个结构化数据集、"
                f"{existing.get('stored_rows') or 0} 行已存储记录、{existing.get('writing_documents') or 0} 个写作文档；"
                f"内部生成材料包含 {generated.get('artifacts') or 0} 个会话产物；"
                f"来源库/采集入口有 {source_catalog.get('items') or 0} 个 item，它们是采集入口，不等同于已入库资料。"
                + (f" 当前缺口：{'; '.join(str(item) for item in missing[:3])}。" if missing else "")
            )

        structured_call = by_id.get("project.structured_data.search")
        if structured_call:
            result = dict(structured_call.get("result") or {})
            inventory = [dict(item or {}) for item in list(result.get("inventory") or [])[:8]]
            visible = [
                f"{item.get('dataset')}={item.get('total_rows') if item.get('total_rows') is not None else item.get('sample_count')}"
                for item in inventory
                if item.get("dataset")
            ]
            samples = [str(item.get("title") or item.get("record_id") or "").strip() for item in list(result.get("items") or [])[:4]]
            sample_text = "；样本：" + "、".join([item for item in samples if item]) if samples else ""
            return (
                f"我读取了当前项目已入库的结构化数据，模式={result.get('query_mode') or 'search'}，"
                f"可见数据集包括 {', '.join(visible) if visible else '暂无可见样本'}，"
                f"已存储行数 {result.get('total_stored_rows') or 0}，本轮返回样本 {result.get('total_matches') or 0} 条{sample_text}。"
            )

        project_call = by_id.get("project.summary.read")
        if project_call:
            result = dict(project_call.get("result") or {})
            source = dict(result.get("source_library") or {})
            counts = dict(result.get("session_counts") or {})
            return (
                f"当前项目 {result.get('project_key') or context.project_key or '-'} 的来源库共有 {source.get('total') or 0} 个，"
                f"其中启用 {source.get('enabled') or 0} 个；本会话已有 tasks={counts.get('tasks') or 0}、"
                f"events={counts.get('events') or 0}、artifacts={counts.get('artifacts') or 0}。"
            )

        artifact_call = by_id.get("agent_artifact.search") or by_id.get("agent_artifact.read")
        if artifact_call:
            result = dict(artifact_call.get("result") or {})
            items = list(result.get("items") or [])
            artifact = result.get("artifact")
            if isinstance(artifact, dict):
                return f"我找到了目标 artifact：{artifact.get('name') or artifact.get('artifact_type') or artifact.get('artifact_id')}，已把摘要放到结果里。"
            return f"我查了当前会话产物，匹配到 {result.get('total') or len(items)} 个 artifact。"

        workflow_call = by_id.get("workflow_graph.inspect") or by_id.get("workflow_graph.list")
        if workflow_call:
            result = dict(workflow_call.get("result") or {})
            graph = dict(result.get("graph") or {})
            if graph:
                return (
                    f"我检查了 workflow graph {graph.get('graph_id') or '-'}，"
                    f"节点数 {graph.get('node_count') or 0}，输入键 {', '.join(list(graph.get('input_keys') or [])[:8]) or '-'}。"
                )
            return f"我读取了 workflow graph 目录，当前可见 {result.get('total') or 0} 个 graph。"

        ingest_call = by_id.get("ingest.status.read")
        if ingest_call:
            result = dict(ingest_call.get("result") or {})
            return f"我读取了最近 ingest/source-library 运行状态，最近记录 {result.get('total') or 0} 条。"

        summaries: list[str] = []
        for call in calls[-6:]:
            capability_id = str(call.get("capability_id") or call.get("tool_name") or "tool")
            status = str(call.get("status") or "-")
            summary = str(call.get("summary") or "").strip()
            summaries.append(f"{capability_id}: {status}" + (f"; {summary}" if summary else ""))
        if not summaries:
            return "我已完成本轮检查。"
        return "我已完成本轮只读检查：" + "；".join(summaries) + "。"

    @staticmethod
    def _default_input(capability_id: str, context: AgentRunLoopContext) -> dict[str, Any]:
        if capability_id == "source_library.item.list":
            return {"limit": 12}
        if capability_id == "source_library.item.search":
            return {"query": context.message, "limit": 12}
        if capability_id == "project.structured_data.search":
            return {"query": context.message, "limit": 12}
        if capability_id == "project.context.bundle":
            return {"query": context.message, "limit": 8}
        if capability_id == "agent_runtime.tool.search":
            return {"query": context.message, "limit": 12}
        if capability_id == "agent_artifact.search":
            return {"query": context.message, "limit": 8}
        if capability_id == "workflow_graph.list":
            return {"limit": 12}
        if capability_id == "workflow_graph.inspect":
            graph_id = HeuristicAgentRunLoopPlanner._extract_graph_id(context.message)
            return {"graph_id": graph_id} if graph_id else {}
        if capability_id == "ingest.status.read":
            return {"limit": 12}
        return {}

    @staticmethod
    def _extract_graph_id(message: str) -> str | None:
        skip = {"workflow", "workflow_graph", "graph", "run", "运行", "执行", "查看", "检查", "inspect"}
        for token in str(message or "").replace("，", " ").replace(",", " ").split():
            cleaned = token.strip("`'\"：:；;。()[]{}")
            if not cleaned or cleaned.lower() in skip:
                continue
            if any(marker in cleaned.lower() for marker in ("graph", "workflow", "_")) or len(cleaned) >= 4:
                return cleaned
        return None


class JsonModelAgentRunLoopPlanner:
    """Model-backed planner that asks a chat model for JSON tool decisions."""

    def __init__(self, *, chat_model: Any | None = None, chat_model_factory: Callable[[], Any] | None = None) -> None:
        self.chat_model = chat_model
        self.chat_model_factory = chat_model_factory

    def plan_next(
        self,
        *,
        context: AgentRunLoopContext,
        available_tools: list[dict[str, Any]],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> dict[str, Any]:
        model = self._get_model()
        prompt = self._build_prompt(
            context=context,
            available_tools=available_tools,
            transcript=transcript,
            remaining_budget=remaining_budget,
        )
        response = model.invoke(prompt)
        content = getattr(response, "content", None)
        if content is None and isinstance(response, dict):
            content = response.get("content")
        parsed = self._parse_json_content(str(content or ""))
        if parsed is None:
            return {
                "model_path": "json_model",
                "tool_calls": [],
                "final_answer": str(content or "").strip() or "model planner returned an empty response",
                "stop": True,
                "parse_error": "invalid_json",
            }
        parsed.setdefault("model_path", "json_model")
        parsed.setdefault("tool_calls", [])
        parsed.setdefault("stop", True)
        return parsed

    def _get_model(self) -> Any:
        if self.chat_model is not None:
            return self.chat_model
        if self.chat_model_factory is not None:
            self.chat_model = self.chat_model_factory()
            return self.chat_model
        from app.services.llm.provider import get_local_fallback_chat

        self.chat_model = get_local_fallback_chat(temperature=0.0)
        return self.chat_model

    @staticmethod
    def _build_prompt(
        *,
        context: AgentRunLoopContext,
        available_tools: list[dict[str, Any]],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> str:
        payload = {
            "instruction": (
                "You are an agent tool planner. Return only JSON with keys: "
                "tool_calls, final_answer, stop. tool_calls is a list of {tool_name,input,reason}. "
                "Use read-only tools when they answer the user. If enough tool results are present, "
                "return no tool_calls and a final_answer."
            ),
            "user_message": context.message,
            "agent_mode": context.agent_mode,
            "project_key": context.project_key,
            "selected_capability_ids": list(context.selected_capability_ids),
            "available_tools": available_tools,
            "transcript": transcript[-6:],
            "remaining_budget": remaining_budget,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any] | None:
        text = str(content or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            parsed = json.loads(text)
        except Exception:  # noqa: BLE001
            return None
        return parsed if isinstance(parsed, dict) else None


class AgentRunLoop:
    def __init__(
        self,
        *,
        tool_runtime: ReadOnlyAgentToolRuntime,
        planner: AgentRunLoopPlanner | None = None,
        event_sink: AgentRunLoopEventSink | None = None,
        budget: AgentRunLoopBudget | None = None,
        execution_policy: ToolExecutionPolicy | None = None,
        hooks: ToolExecutionHooks | None = None,
    ) -> None:
        self.tool_runtime = tool_runtime
        self.planner = planner or HeuristicAgentRunLoopPlanner()
        self.event_sink = event_sink
        self.budget = budget or AgentRunLoopBudget()
        self.execution_policy = execution_policy or ToolExecutionPolicy()
        self.hooks = hooks or ToolExecutionHooks()
        self.events: list[dict[str, Any]] = []

    def run(self, context: AgentRunLoopContext) -> dict[str, Any]:
        started_at = monotonic()
        transcript: list[dict[str, Any]] = []
        capability_calls: list[dict[str, Any]] = []
        available_tools = self.tool_runtime.list_tool_definitions()
        available_by_name = {str(tool.get("name") or ""): dict(tool or {}) for tool in available_tools}
        concurrency_plan = self.execution_policy.build_concurrency_plan(available_tools)
        tool_call_count = 0
        iterations_used = 0
        stop_reason = "no_more_tools"
        model_path = "run_loop"
        model_final_answer: str | None = None
        first_event_latency_seconds: float | None = None
        first_tool_start_latency_seconds: float | None = None

        self._emit(
            "interactive_agent.model_delta",
            {
                "turn_id": context.turn_id,
                "delta": "selecting tools",
                "model_path": "run_loop",
                "agent_mode": context.agent_mode,
            },
        )
        first_event_latency_seconds = self._seconds_elapsed(started_at)

        for iteration in range(1, max(1, int(self.budget.max_iterations)) + 1):
            iterations_used = iteration
            if self._seconds_elapsed(started_at) > self.budget.max_seconds:
                stop_reason = "max_seconds_exceeded"
                break

            decision = self.planner.plan_next(
                context=context,
                available_tools=available_tools,
                transcript=transcript,
                remaining_budget={
                    **self.budget.to_dict(),
                    "remaining_tool_calls": max(0, self.budget.max_tool_calls - tool_call_count),
                    "elapsed_seconds": self._seconds_elapsed(started_at),
                },
            )
            self._emit(
                "interactive_agent.model_delta",
                {
                    "turn_id": context.turn_id,
                    "delta": "planner decision ready",
                    "model_path": decision.get("model_path") or "unknown",
                    "iteration": iteration,
                    "tool_call_count": len(list(decision.get("tool_calls") or [])),
                    "has_final_answer": bool(decision.get("final_answer")),
                },
            )
            model_path = str(decision.get("model_path") or model_path)
            if decision.get("final_answer"):
                model_final_answer = str(decision.get("final_answer") or "").strip() or None

            tool_calls = [dict(item or {}) for item in list(decision.get("tool_calls") or [])]
            if not tool_calls:
                stop_reason = "final_answer" if decision.get("final_answer") else "no_more_tools"
                break

            scheduled_calls: list[ToolCallExecutionRecord] = []
            budget_stopped = False
            for tool_index, tool_call in enumerate(tool_calls, start=1):
                if tool_call_count + len(scheduled_calls) >= self.budget.max_tool_calls:
                    stop_reason = "max_tool_calls_exceeded"
                    budget_stopped = True
                    break
                if self._seconds_elapsed(started_at) > self.budget.max_seconds:
                    stop_reason = "max_seconds_exceeded"
                    budget_stopped = True
                    break

                tool_name = str(tool_call.get("tool_name") or tool_call.get("capability_id") or "").strip()
                input_payload = dict(tool_call.get("input") or {})
                call_id = f"{context.turn_id}:tool:{iteration}:{tool_index}:{tool_name or 'unknown'}"
                tool_definition = available_by_name.get(tool_name, {})
                self._emit(
                    "interactive_agent.tool_call_requested",
                    {
                        "turn_id": context.turn_id,
                        "call_id": call_id,
                        "tool_name": tool_name,
                        "capability_id": tool_name,
                        "input": input_payload,
                        "reason": tool_call.get("reason"),
                    },
                )
                if is_abort_requested(context.abort_signal):
                    call = self._build_canceled_tool_call(
                        turn_id=context.turn_id,
                        call_id=call_id,
                        tool_name=tool_name,
                        input_payload=input_payload,
                    )
                    tool_call_count += 1
                    capability_calls.append(call)
                    transcript.append({"role": "tool", "tool_name": tool_name, "call": call})
                    self.hooks.emit("on_cancel", {"turn_id": context.turn_id, "call": call})
                    self._emit("interactive_agent.tool_call_result", call)
                    stop_reason = "user_canceled"
                    budget_stopped = True
                    break
                if self.execution_policy.requires_approval(tool_definition):
                    call = {
                        "contract_version": "interactive_agent.capability_call.v1",
                        "turn_id": context.turn_id,
                        "call_id": call_id,
                        "capability_id": tool_name,
                        "tool_name": tool_name,
                        "protocol": "read_only",
                        "stream_state": "needs_approval",
                        "status": "needs_approval",
                        "summary": "tool requires approval before execution",
                        "input": input_payload,
                        "result": {"tool_definition": tool_definition},
                    }
                    tool_call_count += 1
                    capability_calls.append(call)
                    transcript.append({"role": "tool", "tool_name": tool_name, "call": call})
                    self.hooks.emit("on_approval", {"turn_id": context.turn_id, "call": call})
                    self._emit("interactive_agent.tool_call_result", call)
                    stop_reason = "approval_waiting"
                    budget_stopped = True
                    break
                if first_tool_start_latency_seconds is None:
                    first_tool_start_latency_seconds = self._seconds_elapsed(started_at)
                self._emit(
                    "interactive_agent.tool_call_started",
                    {
                        "turn_id": context.turn_id,
                        "call_id": call_id,
                        "tool_name": tool_name,
                        "capability_id": tool_name,
                        "input": input_payload,
                        "stream_state": "started",
                        "protocol": "read_only",
                    },
                )
                scheduled_calls.append(
                    ToolCallExecutionRecord(
                        tool_name=tool_name,
                        call_id=call_id,
                        input_payload=input_payload,
                        reason=str(tool_call.get("reason") or "") or None,
                        tool_definition=tool_definition,
                    )
                )

            if scheduled_calls:
                executed_calls = self._execute_scheduled_tool_calls(context=context, records=scheduled_calls)
                for record, call in zip(scheduled_calls, executed_calls, strict=False):
                    if self._seconds_elapsed(started_at) > self.budget.max_seconds:
                        stop_reason = "max_seconds_exceeded"
                        budget_stopped = True
                        break
                    tool_call_count += 1
                    capability_calls.append(call)
                    transcript.append({"role": "tool", "tool_name": record.tool_name, "call": call})
                    self._emit("interactive_agent.tool_call_result", call)
            if budget_stopped:
                break
            if scheduled_calls and bool(decision.get("stop")):
                continue
            if bool(decision.get("stop")):
                stop_reason = "no_more_tools"
                break
            continue
        else:
            stop_reason = "max_iterations_exceeded"

        self._emit(
            "interactive_agent.model_delta",
            {
                "turn_id": context.turn_id,
                "delta": "run loop stopped",
                "stop_reason": stop_reason,
                "tool_call_count": tool_call_count,
            },
        )
        return {
            "contract_version": RUN_LOOP_CONTRACT_VERSION,
            "turn_id": context.turn_id,
            "agent_mode": context.agent_mode,
            "stop_reason": stop_reason,
            "iterations": iterations_used,
            "tool_call_count": tool_call_count,
            "available_tools": available_tools,
            "capability_calls": capability_calls,
            "events": list(self.events),
            "budget": self.budget.to_dict(),
            "model_path": model_path,
            "model_final_answer": model_final_answer,
            "concurrency_plan": concurrency_plan,
            "metrics": {
                "first_event_latency_seconds": first_event_latency_seconds,
                "first_tool_start_latency_seconds": first_tool_start_latency_seconds,
                "elapsed_seconds": self._seconds_elapsed(started_at),
                "tool_count": tool_call_count,
                "retry_count": 0,
                "approval_count": 0,
                "cancel_count": 0,
                "error_count": sum(1 for call in capability_calls if str(call.get("status") or "") == "failed"),
            },
        }

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"event_type": event_type, "payload": payload}
        self.events.append(event)
        if self.event_sink is not None:
            self.event_sink(event)

    def _execute_scheduled_tool_calls(
        self,
        *,
        context: AgentRunLoopContext,
        records: list[ToolCallExecutionRecord],
    ) -> list[dict[str, Any]]:
        tool_definitions = [record.tool_definition for record in records]
        if len(records) > 1 and self.execution_policy.can_run_parallel(tool_definitions):
            max_workers = max(1, min(len(records), self.budget.max_tool_calls))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = [pool.submit(self._execute_one_tool_call, context, record) for record in records]
                return [future.result() for future in futures]
        return [self._execute_one_tool_call(context, record) for record in records]

    def _execute_one_tool_call(self, context: AgentRunLoopContext, record: ToolCallExecutionRecord) -> dict[str, Any]:
        payload = {
            "turn_id": context.turn_id,
            "session_id": context.session_id,
            "project_key": context.project_key,
            "call_id": record.call_id,
            "tool_name": record.tool_name,
            "input": record.input_payload,
            "tool_definition": record.tool_definition,
        }
        if is_abort_requested(context.abort_signal):
            call = self._build_canceled_tool_call(
                turn_id=context.turn_id,
                call_id=record.call_id,
                tool_name=record.tool_name,
                input_payload=record.input_payload,
            )
            self.hooks.emit("on_cancel", {**payload, "call": call})
            return call
        self.hooks.emit("pre_tool", payload)
        try:
            call = self.tool_runtime.execute(
                tool_name=record.tool_name,
                turn_id=context.turn_id,
                session_id=context.session_id,
                project_key=context.project_key,
                command=context.message,
                input_payload=record.input_payload,
            )
            call["call_id"] = record.call_id
            call["input"] = record.input_payload
            call["result_budget"] = self._result_budget(call.get("result"))
            self.hooks.emit("post_tool", {**payload, "call": call})
            return call
        except Exception as exc:  # noqa: BLE001
            call = {
                "contract_version": "interactive_agent.capability_call.v1",
                "turn_id": context.turn_id,
                "call_id": record.call_id,
                "capability_id": record.tool_name,
                "tool_name": record.tool_name,
                "protocol": "read_only",
                "stream_state": "failed",
                "status": "failed",
                "summary": f"tool execution failed: {exc}",
                "error": {"type": exc.__class__.__name__, "message": str(exc)},
                "result": {},
                "input": record.input_payload,
            }
            self.hooks.emit("on_error", {**payload, "call": call, "error": call["error"]})
            return call

    @staticmethod
    def _build_canceled_tool_call(
        *,
        turn_id: str,
        call_id: str,
        tool_name: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "contract_version": "interactive_agent.capability_call.v1",
            "turn_id": turn_id,
            "call_id": call_id,
            "capability_id": tool_name,
            "tool_name": tool_name,
            "protocol": "read_only",
            "stream_state": "canceled",
            "status": "canceled",
            "summary": "tool execution canceled before completion",
            "input": input_payload,
            "result": {"canceled": True, "recoverable": True},
        }

    def _result_budget(self, result: Any) -> dict[str, Any]:
        encoded = json.dumps(result or {}, ensure_ascii=False, sort_keys=True, default=str)
        size = len(encoded)
        return {
            "chars": size,
            "max_chars": self.budget.max_result_chars,
            "truncated": size > self.budget.max_result_chars,
        }

    @staticmethod
    def _seconds_elapsed(started_at: float) -> float:
        return round(monotonic() - started_at, 6)
