from __future__ import annotations

from collections.abc import Iterable
import json
import re
from typing import Any, Protocol

from .capability_registry import (
    classify_goal,
    is_social_chat_goal,
    list_interactive_agent_capabilities,
    select_capabilities_for_goal,
)
from .material_ontology import classify_material_intent


TURN_DECISION_CONTRACT_VERSION = "interactive_agent.turn_decision.v1"
TURN_DECISION_ACTIONS = frozenset(
    {
        "answer_direct",
        "call_tools",
        "ask_clarification",
        "request_approval",
        "decline_or_safe_complete",
    }
)


class AgentTurnDecisionPlanner(Protocol):
    def decide(
        self,
        *,
        message: str,
        project_key: str | None,
        routing_hints: dict[str, Any],
        tool_pool: dict[str, Any],
    ) -> dict[str, Any]:
        ...


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    return _text(value).lower()


def _contains_any(text: str, tokens: Iterable[str]) -> bool:
    return any(token in text for token in tokens)


def _capability_map() -> dict[str, dict[str, Any]]:
    return {str(item.get("capability_id") or ""): dict(item) for item in list_interactive_agent_capabilities()}


def _capabilities_by_id(capability_ids: Iterable[str]) -> list[dict[str, Any]]:
    capabilities = _capability_map()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for capability_id in capability_ids:
        key = str(capability_id or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        capability = dict(capabilities.get(key) or {"capability_id": key, "name": key})
        capability.setdefault("selection_reason", "selected by model-first turn decision")
        out.append(capability)
    return out


def build_routing_hints(message: str) -> dict[str, Any]:
    candidate_capabilities = select_capabilities_for_goal(message)
    goal_class = classify_goal(message)
    return {
        "contract_version": "interactive_agent.routing_hints.v1",
        "goal_class": goal_class,
        "candidate_capability_ids": [
            str(item.get("capability_id") or "") for item in candidate_capabilities if str(item.get("capability_id") or "")
        ],
        "candidate_capabilities": candidate_capabilities,
        "rule_source": "classify_goal/select_capabilities_for_goal",
        "role": "hint_only_guardrails_not_primary_router",
    }


def normalize_turn_decision(
    decision: dict[str, Any],
    *,
    message: str,
    routing_hints: dict[str, Any],
) -> dict[str, Any]:
    action = str(decision.get("action") or decision.get("decision") or "").strip()
    if action not in TURN_DECISION_ACTIONS:
        action = "ask_clarification"
    agent_mode = str(decision.get("agent_mode") or "").strip()
    if agent_mode not in {"conversation", "read_only", "control", "execute"}:
        if action in {"answer_direct", "ask_clarification", "decline_or_safe_complete"}:
            agent_mode = "conversation"
        elif action == "call_tools":
            agent_mode = "read_only"
        else:
            agent_mode = "execute"
    selected_ids = [
        str(item or "").strip()
        for item in list(decision.get("selected_capability_ids") or decision.get("capability_ids") or [])
        if str(item or "").strip()
    ]
    if action == "call_tools" and selected_ids and _has_project_data_read_capability(selected_ids):
        selected_capabilities = _capabilities_by_id(selected_ids)
        if selected_capabilities and all(
            str(item.get("concurrency_class") or "").strip() == "read_only"
            and str(item.get("approval_level") or "none").strip() == "none"
            for item in selected_capabilities
        ):
            agent_mode = "read_only"
    confidence = decision.get("confidence")
    try:
        confidence_value = max(0.0, min(1.0, float(confidence)))
    except Exception:  # noqa: BLE001
        confidence_value = 0.5
    answer_source = _text(decision.get("answer_source")) or ("model" if bool(decision.get("requires_model_answer")) else "direct")
    direct_answer = _text(decision.get("direct_answer"))
    requires_model_answer = bool(decision.get("requires_model_answer")) or (answer_source == "model" and not direct_answer)
    return {
        "contract_version": TURN_DECISION_CONTRACT_VERSION,
        "action": action,
        "agent_mode": agent_mode,
        "confidence": confidence_value,
        "reason": _text(decision.get("reason")) or "turn decision normalized by model-first router",
        "selected_capability_ids": selected_ids,
        "direct_answer": direct_answer,
        "clarifying_question": _text(decision.get("clarifying_question")),
        "answer_source": answer_source,
        "requires_model_answer": requires_model_answer,
        "model_error": decision.get("model_error") if isinstance(decision.get("model_error"), dict) else None,
        "repair_reason": _text(decision.get("repair_reason")),
        "routing_hints": routing_hints,
        "model_path": _text(decision.get("model_path")) or "unknown",
        "user_message": message,
    }


def _has_project_data_read_capability(capability_ids: Iterable[str]) -> bool:
    for capability_id in capability_ids:
        item = str(capability_id or "").strip()
        if item in {"project.summary.read", "project.structured_data.search", "project.context.bundle"}:
            return True
        if item.startswith(("source_library.", "workflow_graph.", "agent_artifact.", "ingest.")):
            return True
    return False


_IDENTITY_TOKENS = (
    "你是谁",
    "你是什么",
    "你是啥",
    "这个系统是什么",
    "这个 agent 是什么",
    "who are you",
    "what are you",
)

_LATENCY_TOKENS = (
    "为什么这么慢",
    "为什么慢",
    "太慢",
    "速度慢",
    "交互速度",
    "latency",
    "slow",
)

_CAPABILITY_TOKENS = (
    "你能做什么",
    "能做什么",
    "能干什么",
    "系统现在能干什么",
    "当前有什么能力",
    "有什么能力",
    "有哪些能力",
    "有哪些工具",
    "什么工具",
    "工具列表",
    "工具池",
    "capability",
    "capabilities",
    "available tools",
)

_SESSION_STATUS_TOKENS = (
    "当前状态",
    "会话状态",
    "执行状态",
    "任务状态",
    "进度",
    "刚才",
    "上一步",
    "上一轮",
    "第二项",
    "失败原因",
    "为什么失败",
)

_PROJECT_READ_TOKENS = (
    "这个项目有什么数据",
    "当前项目有什么数据",
    "项目有什么数据",
    "项目里有什么数据",
    "项目里有哪些数据",
    "现在有哪些数据可以用",
    "项目数据",
    "结构化数据",
    "数据库",
    "database",
    "structured data",
    "stored data",
    "当前项目",
    "本项目",
    "项目里",
    "项目状态",
    "项目进展",
    "当前项目进展",
)

_PROJECT_MATERIAL_TOKENS = (
    "资料",
    "材料",
    "素材",
    "事实",
    "信息",
    "证据",
    "已有资料",
    "现有资料",
    "项目资料",
    "项目材料",
    "项目库",
    "本地资料",
    "库中资料",
)

_INTERNAL_CONTEXT_TOKENS = (
    "内部",
    "内部资料",
    "内部数据",
    "内源",
    "内源资料",
    "内源数据",
    "项目内",
    "项目数据",
    "项目里的数据",
    "项目中的数据",
    "本地",
    "本地资料",
    "本地数据",
    "已有",
    "已有资料",
    "已有数据",
    "现有",
    "存量",
    "已存储",
    "已采集",
    "已经采集",
    "采集过",
    "采集好的",
    "采集到的",
    "已收集",
    "已经收集",
    "收集过",
    "收集好的",
    "已搜集",
    "已经搜集",
    "搜集过",
    "搜集好的",
    "已入库",
    "已经入库",
    "入库资料",
    "入库数据",
    "库中",
    "项目库",
    "existing",
    "stored",
    "internal",
    "local",
)

_SOURCE_LIBRARY_TOKENS = (
    "source_library",
    "source library",
    "来源库",
    "数据源",
    "item_key",
    "source item",
)

_WRITING_CONTEXT_TOKENS = (
    "写作",
    "写一段",
    "写成",
    "写篇",
    "写稿",
    "改稿",
    "文本",
    "正文",
    "文章",
    "论文",
    "文稿",
    "文档",
    "报告",
    "段落",
    "这段",
    "这段文字",
    "选区",
    "划词",
    "句子",
    "篇章",
    "草稿",
    "工作台",
    "canvas",
    "writing",
    "draft",
    "paragraph",
)

_WORKFLOW_TOKENS = ("workflow", "workflow_graph", "工作流", "graph")
_ARTIFACT_TOKENS = ("artifact", "artifacts", "工件", "产物", "输出文件", "报告草稿")
_INGEST_STATUS_TOKENS = ("ingest 状态", "ingest status", "采集状态", "source-library 状态")

_CONTROL_TOKENS = ("继续", "重试", "取消", "停止", "abort", "cancel", "retry", "continue")
_CONTROL_MUTATION_TOKENS = ("重试", "取消", "停止", "abort", "cancel", "retry")

_SOURCE_EXECUTION_TOKENS = (
    "采集",
    "收集",
    "搜集",
    "抓取",
    "补充",
    "补一些",
    "补一点",
    "扩充",
    "扩展",
    "新增资料",
    "添加资料",
    "补一轮",
    "补一批",
    "补证据",
    "补充证据",
    "ingest",
    "collect",
    "crawl",
)

_WORKFLOW_EXECUTION_TOKENS = (
    "运行 workflow",
    "执行 workflow",
    "跑 workflow",
    "运行工作流",
    "执行工作流",
    "运行 workflow graph",
    "run workflow",
    "execute workflow",
)

_REPORT_EXECUTION_TOKENS = (
    "生成报告",
    "生成一份报告",
    "产出报告",
    "写报告",
    "导出报告",
    "report.generate",
)

_GENERIC_EXECUTION_TOKENS = (
    "执行",
    "运行",
    "跑一下",
    "写入",
    "创建文件",
    "更新文件",
    "导出",
    "execute",
    "run",
)

_EXTERNAL_RESEARCH_TOKENS = (
    "外部",
    "外部资料",
    "外部数据",
    "外部来源",
    "外部搜索",
    "外部补充",
    "外部搜集",
    "外源",
    "外源资料",
    "外源数据",
    "公开资料",
    "公开数据",
    "公开来源",
    "公开网络",
    "互联网上",
    "网上",
    "联网",
    "联网搜索",
    "网络搜索",
    "网络资料",
    "全网",
    "站外",
    "站外资料",
    "站外来源",
    "新来源",
    "新增来源",
    "新资料",
    "新数据",
    "新增资料",
    "新增数据",
    "新采集",
    "新搜集",
    "最新",
    "最近",
    "市场变化",
    "融资动态",
    "新闻",
    "market",
    "price",
    "news",
    "last ",
)

_ANALYSIS_ACTION_TOKENS = ("分析", "研究", "调研", "summarize", "analyze", "research")
_READ_ONLY_SEARCH_TOKENS = ("搜索", "查找", "匹配", "search", "find", "lookup")


class FastModelFirstTurnDecisionPlanner:
    """Fast local planner that applies model-style intent decisions over rule hints.

    The classifier remains visible as routing_hints, but direct answer, read-only
    tool use, clarification, approval, and governed execution are decided here.
    """

    def decide(
        self,
        *,
        message: str,
        project_key: str | None,
        routing_hints: dict[str, Any],
        tool_pool: dict[str, Any],
    ) -> dict[str, Any]:
        text = _norm(message)
        if not text:
            return self._decision(
                action="ask_clarification",
                agent_mode="conversation",
                confidence=0.95,
                reason="empty or whitespace-only user message",
                clarifying_question="请补充你想让我回答、读取还是执行什么任务。",
            )

        if is_social_chat_goal(text):
            return self._decision(
                action="answer_direct",
                agent_mode="conversation",
                confidence=0.98,
                reason="short social chat should be answered directly",
                direct_answer=(
                    "你好。我在这里，可以直接用普通对话回答问题；需要项目事实时我会读取只读上下文，"
                    "只有明确采集、生成、执行或写入时才进入审批。"
                ),
            )

        if _contains_any(text, _IDENTITY_TOKENS):
            return self._decision(
                action="answer_direct",
                agent_mode="conversation",
                confidence=0.97,
                reason="identity/capability framing question",
                direct_answer=(
                    "我是这个项目里的交互式 agent。你可以直接问我基本事实、当前项目数据、来源库、workflow、"
                    "artifact 和会话状态；需要真正执行采集、生成或写入时，我会先展示工具轨迹和审批边界。"
                ),
            )

        if _contains_any(text, _LATENCY_TOKENS):
            return self._decision(
                action="answer_direct",
                agent_mode="conversation",
                confidence=0.92,
                reason="latency question should be explained without dispatching work",
                direct_answer=(
                    "慢的主要风险点通常是入口把普通问题误判成执行任务、等待后台批处理或审批、以及前端用非流式响应等待完整结果。"
                    "这类问题应该先由 turn decision 判断为直接回答或只读工具，再把写入/联网动作交给审批。"
                ),
            )

        if self._is_control_request(text):
            return self._decision(
                action="call_tools",
                agent_mode="control",
                confidence=0.88,
                reason="explicit session control request",
                selected_capability_ids=self._control_capabilities(text),
            )

        if _contains_any(text, _CAPABILITY_TOKENS):
            return self._decision(
                action="call_tools",
                agent_mode="conversation",
                confidence=0.95,
                reason="capability/tool question can be answered with read-only catalog tools",
                selected_capability_ids=[
                    "agent_runtime.capability.catalog",
                    "agent_runtime.tool_pool.list",
                    "agent_session.context.read",
                ],
            )

        if _contains_any(text, _SESSION_STATUS_TOKENS) and not _contains_any(text, _PROJECT_READ_TOKENS):
            return self._decision(
                action="call_tools",
                agent_mode="conversation",
                confidence=0.9,
                reason="session/status question is conversational but can read the session ledger",
                selected_capability_ids=["agent_session.context.read"],
            )

        if self._is_source_library_read(text):
            return self._decision(
                action="call_tools",
                agent_mode="read_only",
                confidence=0.91,
                reason="source-library lookup/search is read-only unless collection is explicit",
                selected_capability_ids=self._source_library_read_capabilities(text),
            )

        if self._is_project_read(text):
            return self._decision(
                action="call_tools",
                agent_mode="read_only",
                confidence=0.9,
                reason="project data/progress/status request should inspect current context, not execute",
                selected_capability_ids=[
                    "agent_session.context.read",
                    "project.context.bundle",
                    "project.summary.read",
                    "project.structured_data.search",
                    "agent_artifact.search",
                ],
            )

        if self._is_writing_material_read(text):
            return self._decision(
                action="call_tools",
                agent_mode="read_only",
                confidence=0.88,
                reason="writing material request should inspect internal project context before external collection",
                selected_capability_ids=[
                    "agent_session.context.read",
                    "project.context.bundle",
                    "project.summary.read",
                    "project.structured_data.search",
                    "agent_artifact.search",
                ],
            )

        if self._is_workflow_read(text):
            return self._decision(
                action="call_tools",
                agent_mode="read_only",
                confidence=0.86,
                reason="workflow graph inspection is read-only unless run is explicit",
                selected_capability_ids=["workflow_graph.list", "workflow_graph.inspect"],
            )

        if _contains_any(text, _INGEST_STATUS_TOKENS):
            return self._decision(
                action="call_tools",
                agent_mode="read_only",
                confidence=0.86,
                reason="ingest status is a read-only status query",
                selected_capability_ids=["ingest.status.read"],
            )

        if self._is_workflow_execution(text):
            return self._decision(
                action="request_approval",
                agent_mode="execute",
                confidence=0.94,
                reason="explicit workflow execution needs governed approval",
                selected_capability_ids=["workflow_graph.inspect", "workflow_graph.run"],
            )

        if self._is_source_execution(text):
            selected = ["source_library.item.list", "ingest.status.read", "ingest.source_library.run"]
            if _contains_any(text, _PROJECT_MATERIAL_TOKENS) and not _contains_any(text, _SOURCE_LIBRARY_TOKENS):
                selected = [
                    "agent_session.context.read",
                    "project.context.bundle",
                    "project.summary.read",
                    "project.structured_data.search",
                    "agent_artifact.search",
                    *selected,
                ]
            return self._decision(
                action="request_approval",
                agent_mode="execute",
                confidence=0.93,
                reason="explicit source-library/ingest collection needs governed approval",
                selected_capability_ids=selected,
            )

        if self._is_generic_collection_execution(text):
            return self._decision(
                action="request_approval",
                agent_mode="execute",
                confidence=0.82,
                reason="generic material collection should preview internal context before governed search/collection",
                selected_capability_ids=[
                    "agent_session.context.read",
                    "project.context.bundle",
                    "project.summary.read",
                    "project.structured_data.search",
                    "agent_artifact.search",
                    "source_library.item.list",
                    "ingest.status.read",
                    "agent_batch.nl_command.submit",
                ],
            )

        if _contains_any(text, _REPORT_EXECUTION_TOKENS):
            return self._decision(
                action="request_approval",
                agent_mode="execute",
                confidence=0.9,
                reason="report generation writes an artifact and needs governed approval",
                selected_capability_ids=["agent_artifact.search", "report.generate"],
            )

        if _contains_any(text, _ARTIFACT_TOKENS):
            selected = ["agent_artifact.search"]
            if _contains_any(text, ("read", "打开", "查看", "读取")):
                selected.append("agent_artifact.read")
            return self._decision(
                action="call_tools",
                agent_mode="read_only",
                confidence=0.84,
                reason="artifact question should inspect session artifacts",
                selected_capability_ids=selected,
            )

        if self._is_external_research_execution(text):
            return self._decision(
                action="request_approval",
                agent_mode="execute",
                confidence=0.78,
                reason="external/current market research likely requires governed project execution",
                selected_capability_ids=["agent_batch.nl_command.submit"],
            )

        if _contains_any(text, _GENERIC_EXECUTION_TOKENS):
            return self._decision(
                action="ask_clarification",
                agent_mode="conversation",
                confidence=0.66,
                reason="generic execution verb lacks a concrete governed target",
                clarifying_question="你想让我读取现有项目信息，还是执行会写入/联网的任务？如果要执行，请说明目标、范围和输出。",
            )

        return self._decision(
            action="answer_direct",
            agent_mode="conversation",
            confidence=0.78,
            reason="ordinary non-execution message should be answered freely by the conversation model",
            answer_source="model",
            requires_model_answer=True,
        )

    @staticmethod
    def _decision(
        *,
        action: str,
        agent_mode: str,
        confidence: float,
        reason: str,
        selected_capability_ids: list[str] | None = None,
        direct_answer: str = "",
        clarifying_question: str = "",
        answer_source: str = "direct",
        requires_model_answer: bool = False,
    ) -> dict[str, Any]:
        return {
            "contract_version": TURN_DECISION_CONTRACT_VERSION,
            "action": action,
            "agent_mode": agent_mode,
            "confidence": confidence,
            "reason": reason,
            "selected_capability_ids": selected_capability_ids or [],
            "direct_answer": direct_answer,
            "clarifying_question": clarifying_question,
            "answer_source": answer_source,
            "requires_model_answer": bool(requires_model_answer),
            "model_path": "fast_model_first",
        }

    @staticmethod
    def _is_control_request(text: str) -> bool:
        if not _contains_any(text, _CONTROL_TOKENS):
            return False
        if _contains_any(text, _CONTROL_MUTATION_TOKENS):
            return True
        if text in {"继续", "continue", "继续上一步", "继续当前会话"}:
            return True
        return False

    @staticmethod
    def _control_capabilities(text: str) -> list[str]:
        selected = ["agent_session.context.read"]
        if _contains_any(text, ("取消", "停止", "abort", "cancel")):
            selected.append("task.cancel")
        if _contains_any(text, ("重试", "retry")):
            selected.append("task.retry")
        if "继续" in text or "continue" in text:
            selected.append("task.continue")
        return selected

    @staticmethod
    def _is_source_library_read(text: str) -> bool:
        if not _contains_any(text, _SOURCE_LIBRARY_TOKENS):
            return False
        return not _contains_any(text, _SOURCE_EXECUTION_TOKENS)

    @staticmethod
    def _source_library_read_capabilities(text: str) -> list[str]:
        selected = ["agent_session.context.read", "project.summary.read", "project.structured_data.search", "source_library.item.list"]
        if _contains_any(text, _READ_ONLY_SEARCH_TOKENS):
            selected.append("source_library.item.search")
        if _contains_any(text, ("item_key", "详情", "明细", "inspect")):
            selected.append("source_library.item.inspect")
        return selected

    @staticmethod
    def _is_project_read(text: str) -> bool:
        material_intent = classify_material_intent(text)
        if _contains_any(text, _WORKFLOW_TOKENS):
            return False
        if _contains_any(text, _REPORT_EXECUTION_TOKENS):
            return False
        if _contains_any(text, _WRITING_CONTEXT_TOKENS) and _contains_any(text, _PROJECT_MATERIAL_TOKENS):
            return False
        if (
            _contains_any(text, _PROJECT_MATERIAL_TOKENS)
            and _contains_any(text, _SOURCE_EXECUTION_TOKENS)
            and not _contains_any(text, _INTERNAL_CONTEXT_TOKENS)
        ):
            return False
        if material_intent.category in {"internal_existing", "internal_generated"} and material_intent.material_state == "existing":
            return True
        if _contains_any(text, _PROJECT_MATERIAL_TOKENS):
            return True
        if _contains_any(text, _PROJECT_READ_TOKENS) or _contains_any(text, _SESSION_STATUS_TOKENS):
            return True
        if "总结" in text and ("当前项目" in text or "本项目" in text or "项目进展" in text):
            return True
        if "summary" in text and "project" in text:
            return True
        return False

    @staticmethod
    def _is_writing_material_read(text: str) -> bool:
        material_intent = classify_material_intent(text)
        if _contains_any(text, _REPORT_EXECUTION_TOKENS):
            return False
        if not (
            (_contains_any(text, _WRITING_CONTEXT_TOKENS) and _contains_any(text, _PROJECT_MATERIAL_TOKENS))
            or (material_intent.work_context == "writing" and material_intent.category in {"internal_existing", "internal_generated"})
        ):
            return False
        if _contains_any(text, _SOURCE_LIBRARY_TOKENS) or _contains_any(text, _EXTERNAL_RESEARCH_TOKENS):
            return False
        return True

    @staticmethod
    def _is_workflow_read(text: str) -> bool:
        return _contains_any(text, _WORKFLOW_TOKENS) and not _contains_any(text, _WORKFLOW_EXECUTION_TOKENS)

    @staticmethod
    def _is_workflow_execution(text: str) -> bool:
        return _contains_any(text, _WORKFLOW_TOKENS) and _contains_any(text, _WORKFLOW_EXECUTION_TOKENS + ("运行", "执行", "run"))

    @staticmethod
    def _is_source_execution(text: str) -> bool:
        material_intent = classify_material_intent(text)
        if text.startswith("ingest ") or text.startswith("ingest:"):
            return True
        if (
            _contains_any(text, _PROJECT_MATERIAL_TOKENS)
            and _contains_any(text, _INTERNAL_CONTEXT_TOKENS)
            and not _contains_any(text, _SOURCE_LIBRARY_TOKENS)
            and not _contains_any(text, _EXTERNAL_RESEARCH_TOKENS)
        ):
            return False
        return _contains_any(text, _SOURCE_EXECUTION_TOKENS) and _contains_any(
            text,
            _SOURCE_LIBRARY_TOKENS + ("source",),
        ) or (material_intent.category == "source_catalog" and material_intent.risk == "write_external")

    @staticmethod
    def _is_generic_collection_execution(text: str) -> bool:
        material_intent = classify_material_intent(text)
        if _contains_any(text, _SOURCE_LIBRARY_TOKENS):
            return False
        if _contains_any(text, _WRITING_CONTEXT_TOKENS) and not _contains_any(text, _EXTERNAL_RESEARCH_TOKENS):
            return False
        if _contains_any(text, _PROJECT_MATERIAL_TOKENS) and _contains_any(text, _INTERNAL_CONTEXT_TOKENS):
            return False
        if material_intent.category in {"external_discovery", "external_ingest"}:
            return True
        return _contains_any(text, _SOURCE_EXECUTION_TOKENS + ("搜集", "找资料", "collect", "crawl", "gather"))

    @staticmethod
    def _is_external_research_execution(text: str) -> bool:
        if _contains_any(text, _SOURCE_LIBRARY_TOKENS) and _contains_any(text, _READ_ONLY_SEARCH_TOKENS):
            return False
        if not _contains_any(text, _ANALYSIS_ACTION_TOKENS):
            return False
        return _contains_any(text, _EXTERNAL_RESEARCH_TOKENS)


class JsonModelTurnDecisionPlanner:
    """Model-backed turn decision planner for entry-level routing."""

    def __init__(self, *, chat_model: Any | None = None, chat_model_factory: Any | None = None) -> None:
        self.chat_model = chat_model
        self.chat_model_factory = chat_model_factory

    def decide(
        self,
        *,
        message: str,
        project_key: str | None,
        routing_hints: dict[str, Any],
        tool_pool: dict[str, Any],
    ) -> dict[str, Any]:
        model = self._get_model()
        prompt = self._build_prompt(
            message=message,
            project_key=project_key,
            routing_hints=routing_hints,
            tool_pool=tool_pool,
        )
        response = model.invoke(prompt)
        content = getattr(response, "content", None)
        if content is None and isinstance(response, dict):
            content = response.get("content")
        parsed = self._parse_json_content(str(content or ""))
        if parsed is None:
            return FastModelFirstTurnDecisionPlanner().decide(
                message=message,
                project_key=project_key,
                routing_hints=routing_hints,
                tool_pool=tool_pool,
            )
        parsed.setdefault("model_path", "json_model_turn_decision")
        return parsed

    def _get_model(self) -> Any:
        if self.chat_model is not None:
            return self.chat_model
        if self.chat_model_factory is not None:
            self.chat_model = self.chat_model_factory()
            return self.chat_model
        from app.services.llm.provider import get_local_fallback_chat
        from app.settings.config import settings

        timeout = int(getattr(settings, "agent_chat_turn_decision_timeout_seconds", 8) or 8)
        self.chat_model = get_local_fallback_chat(
            temperature=0.0,
            max_tokens=700,
            timeout_seconds=timeout,
            codex_cli_timeout_seconds=timeout,
            codex_cli_reasoning_effort="none",
        )
        return self.chat_model

    @staticmethod
    def _build_prompt(
        *,
        message: str,
        project_key: str | None,
        routing_hints: dict[str, Any],
        tool_pool: dict[str, Any],
    ) -> str:
        compact_tools = [
            {
                "capability_id": tool.get("capability_id") or tool.get("tool_name") or tool.get("name"),
                "description": tool.get("description"),
                "approval_level": tool.get("approval_level"),
                "concurrency_class": tool.get("concurrency_class"),
                "enabled": tool.get("enabled", True),
            }
            for tool in list(tool_pool.get("tools") or [])[:40]
            if isinstance(tool, dict)
        ]
        payload = {
            "instruction": (
                "Decide the next agent turn. Return only JSON with keys: "
                "action, agent_mode, selected_capability_ids, direct_answer, clarifying_question, confidence, reason. "
                "Valid actions: answer_direct, call_tools, ask_clarification, request_approval, decline_or_safe_complete. "
                "Use routing_hints only as low-priority hints. Never default unknown text to agent_batch. "
                "If the user asks what data/materials/evidence exist in this project, workspace, app, or current database, "
                "select read-only project tools such as project.context.bundle, project.summary.read, project.structured_data.search, agent_artifact.search, and agent_session.context.read. "
                "Treat internal/existing/stored/local/project materials as already-available project context. "
                "Treat external/web/online/new-source requests as collection or source-discovery context. "
                "For writing-context material requests, prefer internal project data and artifacts first unless the user explicitly asks for external/web/source collection. "
                "For general material supplementation without a writing/internal qualifier, prepare governed search/collection rather than only reading stored data. "
                "Use source_library tools when the user explicitly says source_library/source library/来源库/数据源/采集入口/item_key, asks for external/web sourcing, or asks to run collection. "
                "If the user asks what data is available now without naming a subject, assume they mean the current project/app data, "
                "not general world knowledge or source-library entries, and use the same read-only project/database tools. "
                "Use direct answer or clarification for greetings, identity, latency, capability, and low-confidence input. "
                "Use read-only tools for project/source-library/workflow/artifact/status questions. "
                "Use request_approval only for explicit collection, workflow run, report generation, writing, or external execution. "
                "For ordinary non-project conversation or fact questions, set action=answer_direct, agent_mode=conversation, "
                "answer_source=model, and put a natural answer in direct_answer when possible."
            ),
            "user_message": message,
            "project_key": project_key,
            "routing_hints": routing_hints,
            "tools": compact_tools,
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


class GuardedModelTurnDecisionPlanner:
    """Use model routing only where it adds value without slowing obvious paths.

    Guardrails and project-specific tool boundaries stay fast and deterministic.
    Plain free conversation is handled by the final-answer model path, so it does
    not need a second model call just to classify the turn.
    """

    def __init__(
        self,
        *,
        model_planner: AgentTurnDecisionPlanner | None = None,
        fast_planner: FastModelFirstTurnDecisionPlanner | None = None,
    ) -> None:
        self.model_planner = model_planner or JsonModelTurnDecisionPlanner()
        self.fast_planner = fast_planner or FastModelFirstTurnDecisionPlanner()

    def decide(
        self,
        *,
        message: str,
        project_key: str | None,
        routing_hints: dict[str, Any],
        tool_pool: dict[str, Any],
    ) -> dict[str, Any]:
        fast_decision = self.fast_planner.decide(
            message=message,
            project_key=project_key,
            routing_hints=routing_hints,
            tool_pool=tool_pool,
        )
        if self._should_use_fast_guardrail(fast_decision):
            guarded = dict(fast_decision)
            guarded["model_path"] = "guarded_fast_before_model"
            guarded["guarded_model_reason"] = "safety/control/direct-safe path does not need a routing model call"
            return guarded

        try:
            model_decision = self.model_planner.decide(
                message=message,
                project_key=project_key,
                routing_hints=routing_hints,
                tool_pool=tool_pool,
            )
        except Exception as exc:  # noqa: BLE001
            guarded = self._fallback_after_model_error(message=message, fast_decision=fast_decision)
            guarded["model_path"] = "guarded_fast_after_model_error"
            guarded["model_error"] = {"type": exc.__class__.__name__, "message": self._safe_model_error_message(exc)}
            return guarded

        action = str(model_decision.get("action") or "").strip()
        selected = [str(item or "").strip() for item in list(model_decision.get("selected_capability_ids") or []) if str(item or "").strip()]
        if action in {"call_tools", "request_approval"} and not selected:
            repaired = dict(model_decision)
            repaired["selected_capability_ids"] = list(fast_decision.get("selected_capability_ids") or [])
            repaired["agent_mode"] = repaired.get("agent_mode") or fast_decision.get("agent_mode")
            repaired["model_path"] = f"{repaired.get('model_path') or 'json_model_turn_decision'}+fast_capability_repair"
            repaired["repair_reason"] = "model chose a tool action without concrete tools; reused fast guarded tool selection"
            return repaired
        return model_decision

    @staticmethod
    def _should_use_fast_guardrail(decision: dict[str, Any]) -> bool:
        action = str(decision.get("action") or "").strip()
        agent_mode = str(decision.get("agent_mode") or "").strip()
        selected = [str(item or "").strip() for item in list(decision.get("selected_capability_ids") or []) if str(item or "").strip()]
        direct_answer = str(decision.get("direct_answer") or "").strip()
        requires_model_answer = bool(decision.get("requires_model_answer"))
        if action == "request_approval":
            return True
        if agent_mode == "control":
            return True
        if action == "answer_direct" and direct_answer:
            return True
        if action == "answer_direct" and requires_model_answer:
            return False
        return False

    @staticmethod
    def _fallback_after_model_error(*, message: str, fast_decision: dict[str, Any]) -> dict[str, Any]:
        if GuardedModelTurnDecisionPlanner._looks_like_project_context_query(message):
            return {
                "contract_version": TURN_DECISION_CONTRACT_VERSION,
                "action": "call_tools",
                "agent_mode": "read_only",
                "confidence": 0.68,
                "reason": "model routing failed; safely falling back to read-only project/database context tools",
                "selected_capability_ids": [
                    "agent_session.context.read",
                    "project.context.bundle",
                    "project.summary.read",
                    "project.structured_data.search",
                    "agent_artifact.search",
                ],
                "direct_answer": "",
                "clarifying_question": "",
                "answer_source": "direct",
                "requires_model_answer": False,
            }
        return dict(fast_decision)

    @staticmethod
    def _looks_like_project_context_query(message: str) -> bool:
        text = str(message or "").strip().lower()
        if not text:
            return False
        project_markers = ("项目", "本项目", "当前项目", "workspace", "工作区", "库里", "系统里", "应用里", "project")
        data_markers = ("数据", "资料", "材料", "证据", "database", "数据库", "有哪些", "有什么", "可以用")
        availability_markers = ("有哪些", "有什么", "可以用", "能用", "现在", "当前", "已有", "现有", "available")
        if _contains_any(text, project_markers) and _contains_any(text, data_markers):
            return True
        return _contains_any(text, ("数据", "资料", "材料", "证据", "来源", "source", "database", "数据库")) and _contains_any(
            text,
            availability_markers,
        )

    @staticmethod
    def _safe_model_error_message(exc: Exception) -> str:
        name = exc.__class__.__name__
        if name == "TimeoutExpired":
            return "model routing timed out"
        raw = str(exc or "").strip()
        if "/Applications/" in raw or "codex" in raw or "--sandbox" in raw:
            return f"{name}: model routing failed"
        return f"{name}: {raw[:160]}" if raw else name


def build_turn_decision_plan(
    *,
    message: str,
    project_key: str | None,
    planner: AgentTurnDecisionPlanner | None,
    tool_pool: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    routing_hints = build_routing_hints(message)
    active_planner = planner or FastModelFirstTurnDecisionPlanner()
    raw_decision = active_planner.decide(
        message=message,
        project_key=project_key,
        routing_hints=routing_hints,
        tool_pool=tool_pool,
    )
    decision = normalize_turn_decision(raw_decision, message=message, routing_hints=routing_hints)
    selected_capabilities = _capabilities_by_id(decision["selected_capability_ids"])
    return decision, selected_capabilities
