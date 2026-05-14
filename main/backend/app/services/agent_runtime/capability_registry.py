from __future__ import annotations

from typing import Any

from .material_ontology import classify_material_intent


_CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "capability_id": "agent_runtime.capability.catalog",
        "name": "Agent capability catalogue",
        "description": "Answer tool/capability questions without dispatching project work.",
        "domain": "agent_runtime",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.capability_registry"}],
        "required_input": ["message"],
        "risks": [],
    },
    {
        "capability_id": "agent_runtime.tool_pool.list",
        "name": "Agent tool pool",
        "description": "Assemble the current project-aware tool pool, grouped by core, deferred, disabled, and approval-required tools.",
        "domain": "agent_runtime",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.tool_pool.AgentToolPoolAssembler"}],
        "required_input": ["project_key"],
        "risks": [],
    },
    {
        "capability_id": "agent_runtime.tool.search",
        "name": "Agent tool search",
        "description": "Search and lazily discover available agent tools by domain, risk, name, description, or required input.",
        "domain": "agent_runtime",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.tool_pool.search"}],
        "required_input": ["query"],
        "risks": [],
    },
    {
        "capability_id": "agent_session.context.read",
        "name": "Session context reader",
        "description": "Inspect the current session ledger, recent messages, tasks, events, artifacts, and approvals.",
        "domain": "agent_sessions",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_sessions.get_session_bundle"}],
        "required_input": ["session_id"],
        "risks": [],
    },
    {
        "capability_id": "agent_batch.nl_command.submit",
        "name": "Natural-language project execution",
        "description": "Turn a user request into governed agent_batch tasks that can call search, source_library, ingest, and workflow handoff paths.",
        "domain": "agent_batch",
        "call_pattern": "async",
        "approval_level": "medium",
        "concurrency_class": "write_shared",
        "entrypoints": [{"type": "internal_service", "id": "agent_batch.run_agent_batch_nl_command_loop"}],
        "required_input": ["command", "project_key"],
        "risks": ["external_collection", "cost", "data_mutation"],
    },
    {
        "capability_id": "source_library.item.list",
        "name": "Source library discovery",
        "description": "Inspect available project and shared source-library data-source items from the database before execution.",
        "domain": "source_library",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "http_api", "method": "GET", "path": "/api/v1/source_library/items"}],
        "required_input": ["project_key"],
        "risks": [],
    },
    {
        "capability_id": "source_library.item.search",
        "name": "Source library search",
        "description": "Search available source-library items without executing collection.",
        "domain": "source_library",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.read_only_tools.source_library_search"}],
        "required_input": ["project_key", "query"],
        "risks": [],
    },
    {
        "capability_id": "source_library.item.inspect",
        "name": "Source library item inspector",
        "description": "Read one source-library item definition without running it.",
        "domain": "source_library",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.read_only_tools.source_library_inspect"}],
        "required_input": ["project_key", "item_key"],
        "risks": [],
    },
    {
        "capability_id": "project.summary.read",
        "name": "Project summary reader",
        "description": "Read the local project database and summarize project-scoped data, source-library coverage, and session counters.",
        "domain": "project",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.read_only_tools.project_summary"}],
        "required_input": ["project_key", "session_id"],
        "risks": [],
    },
    {
        "capability_id": "project.structured_data.search",
        "name": "Project structured-data search",
        "description": (
            "Search or inventory already-stored structured project data across documents, extracted JSON, graph nodes, "
            "market metrics, products, prices, resource-pool entries, keyword memory, search history, and sources."
        ),
        "domain": "project",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.read_only_tools.project_structured_data_search"}],
        "required_input": ["project_key"],
        "risks": [],
    },
    {
        "capability_id": "project.context.bundle",
        "name": "Project material context bundle",
        "description": (
            "Build a compact read-only material inventory across internal structured data, generated artifacts, "
            "writing documents, and source-library catalog entries with explicit material ontology labels."
        ),
        "domain": "project",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.read_only_tools.project_context_bundle"}],
        "required_input": ["project_key", "session_id"],
        "risks": [],
    },
    {
        "capability_id": "agent_artifact.search",
        "name": "Agent artifact search",
        "description": "Search session artifacts without mutating project state.",
        "domain": "agent_sessions",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.read_only_tools.artifact_search"}],
        "required_input": ["session_id"],
        "risks": [],
    },
    {
        "capability_id": "agent_artifact.read",
        "name": "Agent artifact reader",
        "description": "Read a session artifact payload for conversational follow-up.",
        "domain": "agent_sessions",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.read_only_tools.artifact_read"}],
        "required_input": ["session_id"],
        "risks": [],
    },
    {
        "capability_id": "workflow_graph.list",
        "name": "Workflow graph discovery",
        "description": "List compiled workflow graphs and workflow graph templates without executing a run.",
        "domain": "workflow_graph",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.read_only_tools.workflow_graph_list"}],
        "required_input": [],
        "risks": [],
    },
    {
        "capability_id": "workflow_graph.inspect",
        "name": "Workflow graph inspector",
        "description": "Inspect compiled workflow graph nodes, order, checksum, and input shape before execution.",
        "domain": "workflow_graph",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.read_only_tools.workflow_graph_inspect"}],
        "required_input": ["graph_id"],
        "risks": [],
    },
    {
        "capability_id": "ingest.status.read",
        "name": "Ingest status reader",
        "description": "Read recent ingest and source-library job status without starting collection.",
        "domain": "ingest",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.read_only_tools.ingest_status_read"}],
        "required_input": ["session_id"],
        "risks": [],
    },
    {
        "capability_id": "ingest.source_library.run",
        "name": "Source-library collection",
        "description": "Execute selected source-library items through ingest/source-library runtime.",
        "domain": "ingest",
        "call_pattern": "both",
        "approval_level": "high",
        "concurrency_class": "write_external",
        "entrypoints": [{"type": "http_api", "method": "POST", "path": "/api/v1/ingest/source-library/run"}],
        "required_input": ["items", "project_key"],
        "risks": ["external_network", "filesystem_write", "data_mutation"],
    },
    {
        "capability_id": "ingest.url_pool.submit",
        "name": "URL-pool ingest submit",
        "description": "Submit an approved external URL candidate through the URL-pool/source-library ingestion frontdoor.",
        "domain": "ingest",
        "call_pattern": "async",
        "approval_level": "none",
        "concurrency_class": "write_external",
        "entrypoints": [{"type": "agent_core_tool", "id": "ingest.url_pool.submit"}],
        "required_input": ["url", "project_key"],
        "risks": ["external_network", "filesystem_write", "data_mutation"],
    },
    {
        "capability_id": "ingest.url_pool.status",
        "name": "URL-pool ingest status",
        "description": "Read URL-pool submission status and check stored project documents/sources for verified evidence.",
        "domain": "ingest",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "agent_core_tool", "id": "ingest.url_pool.status"}],
        "required_input": ["project_key"],
        "risks": [],
    },
    {
        "capability_id": "source.history.read",
        "name": "Source candidate history",
        "description": "Read source candidate reviews and URL-pool submissions from the current session and optional recent same-project sessions.",
        "domain": "source_library",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "agent_core_tool", "id": "source.history.read"}],
        "required_input": ["project_key"],
        "risks": [],
    },
    {
        "capability_id": "workflow_graph.run",
        "name": "Workflow graph execution",
        "description": "Run a compiled workflow graph and project node progress into agent sessions.",
        "domain": "workflow_graph",
        "call_pattern": "async",
        "approval_level": "high",
        "concurrency_class": "write_shared",
        "entrypoints": [{"type": "skill", "skill_id": "workflow_graph.run"}],
        "required_input": ["graph_id", "inputs"],
        "risks": ["workflow_side_effects", "cost"],
    },
    {
        "capability_id": "report.generate",
        "name": "Report draft generation",
        "description": "Generate a report draft from existing session/project evidence and write the markdown output to a declared artifact path.",
        "domain": "report",
        "call_pattern": "async",
        "approval_level": "high",
        "concurrency_class": "write_shared",
        "entrypoints": [{"type": "internal_service", "id": "llm_report_generator.build_structured_report"}],
        "required_input": ["topic", "output_path"],
        "risks": ["filesystem_write", "derived_content", "cost"],
    },
    {
        "capability_id": "task.cancel",
        "name": "Task/session cancellation",
        "description": "Cancel the current agent session when the user explicitly asks to stop or abort.",
        "domain": "agent_sessions",
        "call_pattern": "sync",
        "approval_level": "explicit_user_request",
        "concurrency_class": "write_shared",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.control_tools.task_cancel"}],
        "required_input": ["session_id"],
        "risks": ["session_state_mutation"],
    },
    {
        "capability_id": "task.retry",
        "name": "Task retry",
        "description": "Retry a failed, canceled, or expired task in the current agent session.",
        "domain": "agent_sessions",
        "call_pattern": "sync",
        "approval_level": "explicit_user_request",
        "concurrency_class": "write_shared",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.control_tools.task_retry"}],
        "required_input": ["session_id"],
        "risks": ["session_state_mutation"],
    },
    {
        "capability_id": "task.continue",
        "name": "Task continue",
        "description": "Continue a waiting or partially completed session through a coordinator pass.",
        "domain": "agent_sessions",
        "call_pattern": "sync",
        "approval_level": "explicit_user_request",
        "concurrency_class": "write_shared",
        "entrypoints": [{"type": "internal_service", "id": "agent_runtime.control_tools.task_continue"}],
        "required_input": ["session_id"],
        "risks": ["session_state_mutation"],
    },
    {
        "capability_id": "agent_session.stream",
        "name": "Interactive event stream",
        "description": "Read session-scoped task, message, artifact, and approval progress through SSE.",
        "domain": "agent_sessions",
        "call_pattern": "sync",
        "approval_level": "none",
        "concurrency_class": "read_only",
        "entrypoints": [{"type": "http_api", "method": "GET", "path": "/api/v1/agent-sessions/{session_id}/stream"}],
        "required_input": ["session_id"],
        "risks": [],
    },
)

_CAPABILITY_QUERY_TOKENS = (
    "你能做什么",
    "有哪些工具",
    "什么工具",
    "工具列表",
    "能力列表",
    "工具目录",
    "工具池",
    "capability",
    "capabilities",
    "available tools",
    "tool pool",
    "tool search",
    "help",
)

_TOOL_SEARCH_QUERY_TOKENS = (
    "搜索工具",
    "查找工具",
    "匹配工具",
    "工具搜索",
    "tool_search",
    "tool search",
    "search tools",
    "find tools",
)

_SESSION_STATUS_TOKENS = (
    "当前状态",
    "执行状态",
    "任务状态",
    "进度",
    "session",
    "会话状态",
    "events",
    "artifacts",
    "刚才",
    "上一步",
    "上一轮",
    "第二项",
    "失败原因",
    "为什么失败",
)

_SOURCE_LIBRARY_QUERY_TOKENS = (
    "source_library",
    "source library",
    "来源库",
    "数据源",
    "采集源",
    "采集入口",
    "source item",
    "item_key",
    "items",
)

_EXTERNAL_SOURCE_QUERY_TOKENS = (
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
    "网络数据",
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
    "新收集",
    "external",
    "web",
    "online",
    "internet",
)

_INTERNAL_CONTEXT_QUERY_TOKENS = (
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

_PROJECT_MATERIAL_QUERY_TOKENS = (
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

_STRUCTURED_DATA_QUERY_TOKENS = (
    "数据",
    "结构化数据",
    "stored data",
    "structured data",
    "database",
    "数据库",
)

_PROJECT_CONTEXT_QUERY_TOKENS = (
    "当前项目",
    "本项目",
    "项目里",
    "项目数据",
    "项目状态",
    "project",
    "project data",
    "project status",
)

_ARTIFACT_QUERY_TOKENS = (
    "artifact",
    "artifacts",
    "工件",
    "产物",
    "输出文件",
    "报告文件",
)

_WORKFLOW_GRAPH_QUERY_TOKENS = (
    "workflow_graph",
    "workflow graph",
    "workflow",
    "工作流",
    "graph",
)

_INGEST_STATUS_QUERY_TOKENS = (
    "ingest",
    "采集状态",
    "采集历史",
    "最近采集",
    "source_library run",
    "source-library run",
)

_REPORT_ACTION_TOKENS = (
    "报告",
    "报告草稿",
    "生成报告",
    "写报告",
    "report",
    "draft report",
    "generate report",
)

_TASK_CANCEL_TOKENS = (
    "取消",
    "停止",
    "中断",
    "cancel",
    "stop",
    "abort",
)

_TASK_RETRY_TOKENS = (
    "重试",
    "再试",
    "retry",
)

_TASK_CONTINUE_TOKENS = (
    "继续",
    "恢复",
    "continue",
    "resume",
)

_SOCIAL_CHAT_TOKENS = (
    "你好",
    "您好",
    "嗨",
    "哈喽",
    "早上好",
    "上午好",
    "中午好",
    "下午好",
    "晚上好",
    "hello",
    "hi",
    "hey",
)

_READ_ONLY_QUERY_TOKENS = (
    "有哪些",
    "列出",
    "查看",
    "看看",
    "查询",
    "说明",
    "解释",
    "是什么",
    "多少",
    "现有",
    "已有",
    "当前",
    "状态",
    "历史",
    "list",
    "show",
    "read",
    "inspect",
    "what",
    "why",
    "为什么",
    "which",
    "how many",
    "status",
)

_PROJECT_ACTION_TOKENS = (
    "采集",
    "收集",
    "抓取",
    "补一轮",
    "补一批",
    "补证据",
    "检索",
    "搜索",
    "分析",
    "总结",
    "生成",
    "执行",
    "运行",
    "调用",
    "跑",
    "修复",
    "补充",
    "补齐",
    "整理",
    "创建",
    "更新",
    "导出",
    "collect",
    "crawl",
    "ingest",
    "search",
    "analyze",
    "summarize",
    "execute",
    "run",
    "fix",
    "create",
    "update",
)

_COLLECTION_ACTION_TOKENS = (
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
    "补资料",
    "补材料",
    "找资料",
    "查资料",
    "检索",
    "搜索",
    "查找",
    "再找",
    "补一轮",
    "补一批",
    "补证据",
    "collect",
    "crawl",
    "ingest",
    "search",
)

_WRITING_CONTEXT_QUERY_TOKENS = (
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


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def is_conversation_only_goal(goal: str) -> bool:
    text = str(goal or "").strip().lower()
    if not text:
        return False
    if is_social_chat_goal(text):
        return True
    asks_capabilities = _contains_any(text, _CAPABILITY_QUERY_TOKENS)
    asks_tool_search = _contains_any(text, _TOOL_SEARCH_QUERY_TOKENS)
    asks_status = _contains_any(text, _SESSION_STATUS_TOKENS)
    requests_project_work = _contains_any(text, _PROJECT_ACTION_TOKENS) and not asks_tool_search
    return bool((asks_capabilities or asks_tool_search or asks_status) and not requests_project_work)


def is_social_chat_goal(goal: str) -> bool:
    text = str(goal or "").strip().lower()
    if not text:
        return False
    requests_project_work = _contains_any(text, _PROJECT_ACTION_TOKENS)
    references_project_surface = (
        _contains_any(text, _SOURCE_LIBRARY_QUERY_TOKENS)
        or _contains_any(text, _PROJECT_MATERIAL_QUERY_TOKENS)
        or _contains_any(text, _STRUCTURED_DATA_QUERY_TOKENS)
        or _contains_any(text, _PROJECT_CONTEXT_QUERY_TOKENS)
        or _contains_any(text, _ARTIFACT_QUERY_TOKENS)
        or _contains_any(text, _WORKFLOW_GRAPH_QUERY_TOKENS)
        or _contains_any(text, _INGEST_STATUS_QUERY_TOKENS)
    )
    if requests_project_work or references_project_surface:
        return False
    return any(text == token or text.startswith(f"{token}，") or text.startswith(f"{token},") for token in _SOCIAL_CHAT_TOKENS)


def is_task_control_goal(goal: str) -> bool:
    text = str(goal or "").strip().lower()
    if not text:
        return False
    if _contains_any(text, _TASK_CANCEL_TOKENS) or _contains_any(text, _TASK_RETRY_TOKENS):
        return True
    if _contains_any(text, _TASK_CONTINUE_TOKENS):
        requests_project_work = _contains_any(text, _PROJECT_ACTION_TOKENS)
        references_execution_surface = (
            _contains_any(text, _SOURCE_LIBRARY_QUERY_TOKENS)
            or _contains_any(text, _WORKFLOW_GRAPH_QUERY_TOKENS)
            or _contains_any(text, _INGEST_STATUS_QUERY_TOKENS)
        )
        return not requests_project_work and not references_execution_surface
    return False


def classify_goal(goal: str) -> str:
    text = str(goal or "").strip().lower()
    if not text:
        return "execute"
    if is_task_control_goal(text):
        return "control"
    if is_conversation_only_goal(text):
        return "conversation"
    asks_read_only_context = (
        _contains_any(text, _SOURCE_LIBRARY_QUERY_TOKENS)
        or _contains_any(text, _INTERNAL_CONTEXT_QUERY_TOKENS)
        or _contains_any(text, _PROJECT_MATERIAL_QUERY_TOKENS)
        or _contains_any(text, _STRUCTURED_DATA_QUERY_TOKENS)
        or _contains_any(text, _PROJECT_CONTEXT_QUERY_TOKENS)
        or _contains_any(text, _ARTIFACT_QUERY_TOKENS)
        or _contains_any(text, _SESSION_STATUS_TOKENS)
        or _contains_any(text, _WORKFLOW_GRAPH_QUERY_TOKENS)
        or _contains_any(text, _INGEST_STATUS_QUERY_TOKENS)
    )
    requests_project_work = _contains_any(text, _PROJECT_ACTION_TOKENS)
    material_intent = classify_material_intent(text)
    asks_external_source = _contains_any(text, _EXTERNAL_SOURCE_QUERY_TOKENS) or material_intent.category in {"external_discovery", "external_ingest"}
    asks_writing_context = _contains_any(text, _WRITING_CONTEXT_QUERY_TOKENS) or material_intent.work_context == "writing"
    asks_material = _contains_any(text, _PROJECT_MATERIAL_QUERY_TOKENS)
    asks_internal_context = _contains_any(text, _INTERNAL_CONTEXT_QUERY_TOKENS) or material_intent.category in {"internal_existing", "internal_generated"}
    requests_collection = _contains_any(text, _COLLECTION_ACTION_TOKENS)
    if asks_writing_context and asks_material and requests_collection and not asks_external_source and not _contains_any(text, _SOURCE_LIBRARY_QUERY_TOKENS):
        return "read_only"
    if asks_material and requests_collection and not asks_internal_context and not asks_writing_context:
        return "execute"
    if asks_read_only_context and not requests_project_work:
        return "read_only"
    if _contains_any(text, _READ_ONLY_QUERY_TOKENS) and not requests_project_work:
        return "conversation"
    return "execute"


def is_read_only_goal(goal: str) -> bool:
    return classify_goal(goal) in {"conversation", "read_only"}


def is_read_only_capability_id(capability_id: str) -> bool:
    for capability in _CAPABILITIES:
        if capability["capability_id"] == capability_id:
            return (
                capability.get("call_pattern") == "sync"
                and capability.get("approval_level") == "none"
                and capability.get("concurrency_class") == "read_only"
            )
    return False


def list_interactive_agent_capabilities() -> list[dict[str, Any]]:
    return [dict(item) for item in _CAPABILITIES]


def select_capabilities_for_goal(goal: str) -> list[dict[str, Any]]:
    text = str(goal or "").strip().lower()
    selected: list[dict[str, Any]] = []

    def add(capability_id: str, *, reason: str) -> None:
        for capability in _CAPABILITIES:
            if capability["capability_id"] == capability_id:
                enriched = dict(capability)
                enriched["selection_reason"] = reason
                selected.append(enriched)
                return

    goal_class = classify_goal(text)
    if goal_class == "conversation":
        if is_social_chat_goal(text):
            add("agent_session.stream", reason="interactive progress and final-answer delivery")
        else:
            add("agent_runtime.capability.catalog", reason="user is asking about available agent tools or session status")
            add("agent_runtime.tool_pool.list", reason="tool-pool details explain core, deferred, and approval-required tools")
            if _contains_any(text, _TOOL_SEARCH_QUERY_TOKENS):
                add("agent_runtime.tool.search", reason="user asks to search the tool pool")
            add("agent_session.context.read", reason="read session ledger before answering without dispatching work")
        add("agent_session.stream", reason="interactive progress and final-answer delivery")
    elif goal_class == "control":
        add("agent_session.context.read", reason="read current session before applying a control action")
        if _contains_any(text, _TASK_CANCEL_TOKENS):
            add("task.cancel", reason="user explicitly asked to cancel or stop the current session")
        if _contains_any(text, _TASK_RETRY_TOKENS):
            add("task.retry", reason="user explicitly asked to retry a failed task")
        if _contains_any(text, _TASK_CONTINUE_TOKENS):
            add("task.continue", reason="user explicitly asked to continue the current session")
        add("agent_session.stream", reason="interactive progress and final-answer delivery")
    elif goal_class == "read_only":
        add("agent_session.context.read", reason="read current agent session before answering without dispatching work")
        if _contains_any(text, _CAPABILITY_QUERY_TOKENS):
            add("agent_runtime.tool_pool.list", reason="request asks for available tools or capability boundaries")
        if _contains_any(text, _TOOL_SEARCH_QUERY_TOKENS):
            add("agent_runtime.tool.search", reason="request asks to search the available tool pool")
        if _contains_any(text, _PROJECT_CONTEXT_QUERY_TOKENS):
            add("project.context.bundle", reason="request asks for unified current project material context")
            add("project.summary.read", reason="request asks for current project facts")
            add("project.structured_data.search", reason="request asks for already-stored project data records")
        if _contains_any(text, _PROJECT_MATERIAL_QUERY_TOKENS):
            add("project.context.bundle", reason="request asks for existing project materials across internal surfaces")
            add("project.summary.read", reason="request asks for existing project materials")
            add("project.structured_data.search", reason="request asks for already-stored project material records")
            add("agent_artifact.search", reason="request may refer to existing session/project artifacts")
        if _contains_any(text, _WRITING_CONTEXT_QUERY_TOKENS) and _contains_any(text, _PROJECT_MATERIAL_QUERY_TOKENS):
            add("project.context.bundle", reason="writing material request should receive unified internal context first")
            add("project.summary.read", reason="writing context should inspect internal project materials first")
            add("project.structured_data.search", reason="writing context can use already-stored project data")
            add("agent_artifact.search", reason="writing context may use existing drafts and artifacts")
        if _contains_any(text, _STRUCTURED_DATA_QUERY_TOKENS):
            add("project.summary.read", reason="request asks for current project data context")
            add("project.structured_data.search", reason="request asks for already-stored structured data records")
        if _contains_any(text, _SOURCE_LIBRARY_QUERY_TOKENS):
            add("source_library.item.list", reason="request asks for available source-library items")
            if _contains_any(text, ("搜索", "查找", "search", "filter", "匹配")):
                add("source_library.item.search", reason="request asks to search source-library items")
            if "item_key" in text or "inspect" in text or "详情" in text or "明细" in text:
                add("source_library.item.inspect", reason="request asks to inspect a source-library item")
        if _contains_any(text, _ARTIFACT_QUERY_TOKENS):
            add("agent_artifact.search", reason="request asks for session artifacts")
            if "read" in text or "打开" in text or "查看" in text:
                add("agent_artifact.read", reason="request asks to read an artifact")
        if _contains_any(text, _WORKFLOW_GRAPH_QUERY_TOKENS):
            add("workflow_graph.list", reason="request asks for workflow graph facts")
            if any(token in text for token in ("inspect", "详情", "明细", "节点", "输入", "graph_id")):
                add("workflow_graph.inspect", reason="request asks to inspect a workflow graph")
        if _contains_any(text, _INGEST_STATUS_QUERY_TOKENS):
            add("ingest.status.read", reason="request asks for ingest/source-library run status")
        add("agent_session.stream", reason="interactive progress and final-answer delivery")
    else:
        add("agent_batch.nl_command.submit", reason="primary autonomous execution path for natural-language project tasks")
        add("agent_session.stream", reason="interactive progress and final-answer delivery")
        if _contains_any(text, _SESSION_STATUS_TOKENS):
            add("agent_session.context.read", reason="request references current session state")

    material_intent = classify_material_intent(text)
    asks_source_library = _contains_any(text, _SOURCE_LIBRARY_QUERY_TOKENS) or material_intent.category == "source_catalog"
    asks_external_source = _contains_any(text, _EXTERNAL_SOURCE_QUERY_TOKENS) or material_intent.category in {"external_discovery", "external_ingest"}
    asks_writing_context = _contains_any(text, _WRITING_CONTEXT_QUERY_TOKENS) or material_intent.work_context == "writing"
    asks_material = _contains_any(text, _PROJECT_MATERIAL_QUERY_TOKENS)
    asks_internal_context = _contains_any(text, _INTERNAL_CONTEXT_QUERY_TOKENS) or material_intent.category in {"internal_existing", "internal_generated"}
    requests_collection = _contains_any(text, _COLLECTION_ACTION_TOKENS)
    should_prepare_collection = asks_source_library or asks_external_source or (
        requests_collection and (not asks_material or (not asks_internal_context and not asks_writing_context))
    )
    if goal_class == "execute" and should_prepare_collection:
        if asks_material and not asks_source_library:
            add("project.context.bundle", reason="material collection should first build a unified internal/external context bundle")
            add("project.summary.read", reason="material collection should inspect internal project context before expanding")
            add("project.structured_data.search", reason="material collection can reuse already-stored project records first")
            add("agent_artifact.search", reason="material collection can reuse existing agent artifacts first")
        add("source_library.item.list", reason="request references collection or source-library selection")
        add("ingest.status.read", reason="read recent ingest/source-library status before governed execution")
        if asks_source_library:
            add("ingest.source_library.run", reason="request explicitly references governed source-library execution")
        if asks_external_source:
            add("ingest.url_pool.submit", reason="external URL candidates can be submitted through the URL-pool ingest boundary after review")
    if goal_class == "execute" and any(token in text for token in ("workflow", "workflow_graph", "工作流", "图", "graph")):
        add("workflow_graph.inspect", reason="inspect workflow graph input and node shape before execution")
        add("workflow_graph.run", reason="request references workflow or graph execution")
    if goal_class == "execute" and _contains_any(text, _REPORT_ACTION_TOKENS):
        add("agent_artifact.search", reason="report generation should inspect existing artifacts before drafting")
        add("report.generate", reason="request asks to generate a report draft")

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for capability in selected:
        capability_id = str(capability.get("capability_id") or "")
        if capability_id in seen:
            continue
        seen.add(capability_id)
        out.append(capability)
    return out
