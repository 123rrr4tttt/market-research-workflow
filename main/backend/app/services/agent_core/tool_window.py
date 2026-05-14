from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from app.services.agent_runtime.material_ontology import classify_material_intent

from .contracts import CoreToolSpec


@dataclass(frozen=True)
class CoreToolWindow:
    """The tool catalog slice exposed to the model for one turn.

    This is a context-budget layer, not a planner. It decides which schemas are
    cheap and relevant enough to show; the model still decides whether to call
    any visible tool.
    """

    specs: tuple[CoreToolSpec, ...]
    profile: str
    reason: str
    full_tool_count: int

    @property
    def visible_tool_count(self) -> int:
        return len(self.specs)

    @property
    def hidden_tool_count(self) -> int:
        return max(0, self.full_tool_count - len(self.specs))

    def to_plan_metadata(self) -> dict[str, Any]:
        return {
            "tool_window_profile": self.profile,
            "tool_window_reason": self.reason,
            "visible_tool_count": self.visible_tool_count,
            "hidden_tool_count": self.hidden_tool_count,
            "full_tool_count": self.full_tool_count,
        }


@dataclass(frozen=True)
class _ConditionalToolGroup:
    require_all: tuple[str, ...]
    tools: tuple[str, ...]
    require_none: tuple[str, ...] = ()
    skill_prefix_matches: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ToolWindowProfileDefinition:
    name: str
    reason: str
    tools: tuple[str, ...]
    require_all: tuple[str, ...] = ()
    require_none: tuple[str, ...] = ()
    skill_prefix_matches: tuple[str, ...] = ()
    conditional_tool_groups: tuple[_ConditionalToolGroup, ...] = ()


_SOURCE_LIBRARY_TOKENS = frozenset(
    {
        "来源库",
        "数据源",
        "采集源",
        "采集入口",
        "source library",
        "source-library",
        "source_library",
        "source item",
        "item_key",
    }
)
_EXTERNAL_SOURCE_TOKENS = frozenset(
    {
        "外部",
        "外部资料",
        "外部数据",
        "外部来源",
        "外部搜索",
        "外源",
        "外源资料",
        "外源数据",
        "互联网上",
        "网上",
        "网络资料",
        "全网",
        "公开资料",
        "公开数据",
        "公开来源",
        "站外",
        "站外资料",
        "新来源",
        "新增来源",
        "新资料",
        "新数据",
        "新增资料",
        "新增数据",
        "新的资料",
        "新的数据",
        "新的来源",
        "更多资料",
        "更多数据",
        "更多来源",
        "额外资料",
        "额外数据",
        "额外来源",
        "参考来源",
        "引用来源",
        "参考文献",
        "新采集",
        "新搜集",
        "再找来源",
        "再找资料",
        "再找数据",
        "external",
        "web",
        "online",
        "internet",
    }
)
_INTERNAL_MATERIAL_TOKENS = frozenset(
    {
        "内部",
        "项目内",
        "内源",
        "项目里的数据",
        "项目中的数据",
        "本地",
        "已有",
        "既有",
        "现有",
        "存量",
        "已存储",
        "已经存储",
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
        "已归档",
        "已经归档",
        "归档资料",
        "归档数据",
        "项目库中",
        "库中",
        "项目库",
        "existing",
        "stored",
        "internal",
        "local",
    }
)
_PROJECT_DATA_TOKENS = frozenset(
    {
        "数据",
        "数据库",
        "结构化",
        "记录",
        "资料",
        "材料",
        "已有资料",
        "现有资料",
        "项目资料",
        "项目材料",
        "项目库",
        "documents",
        "graph_nodes",
        "resource_pool",
        "records",
        "stored data",
        "project data",
        "图谱",
        "知识图谱",
        "实体",
        "关系",
        "线索",
        "来源",
        "引用",
        "出处",
        "参考来源",
        "引用来源",
        "参考文献",
        "source",
        "sources",
        "citation",
        "citations",
        "reference",
        "references",
        "clue",
        "entity",
        "relation",
    }
)
_DATA_QUALITY_TOKENS = frozenset({"清理", "脏", "噪声", "质量", "脚本", "css", "导航", "noise", "noisy", "clean", "quality"})
_EXECUTION_TOKENS = frozenset({"执行", "运行", "启动", "生成", "补", "采集", "跑", "run", "execute", "start", "collect", "generate", "supplement"})
_COLLECTION_ACTION_TOKENS = frozenset(
    {
        "补",
        "补充",
        "补一些",
        "补一点",
        "扩充",
        "扩展",
        "新增资料",
        "添加资料",
        "收集",
        "搜集",
        "采集",
        "搜索",
        "检索",
        "查找",
        "再找",
        "再找来源",
        "继续找",
        "找资料",
        "找些",
        "找一些",
        "找材料",
        "找数据",
        "找证据",
        "找来源",
        "找参考",
        "搜索来源",
        "collect",
        "gather",
        "search",
        "find",
        "lookup",
        "crawl",
        "ingest",
    }
)
_MATERIAL_COLLECTION_TOKENS = frozenset(
    {
        "补充资料",
        "补资料",
        "补充材料",
        "补材料",
        "补素材",
        "查资料",
        "收集资料",
        "搜集资料",
        "采集资料",
        "找资料",
        "检索资料",
        "补充数据",
        "搜集数据",
        "采集数据",
        "补证据",
        "补充证据",
        "补充来源",
        "collect material",
        "collect data",
        "supplement material",
        "supplement data",
        "gather material",
        "gather data",
    }
)
_DISCOVERY_PLAN_TOKENS = frozenset(
    {
        "发现",
        "候选",
        "可信",
        "信任",
        "外部搜索",
        "source discovery",
        "discovery",
        "candidate",
        "trust",
        "url",
        "external research",
    }
)
_LONG_TASK_TOKENS = frozenset(
    {
        "长任务",
        "长程",
        "持续",
        "分拆",
        "拆分",
        "分解",
        "多轮",
        "调查",
        "追查",
        "线索",
        "续跑",
        "继续推进",
        "long task",
        "long-running",
        "multi-round",
        "investigation",
        "trace",
        "clue",
        "resume",
        "break down",
    }
)
_WRITING_TOKENS = frozenset(
    {
        "写作",
        "写一段",
        "写成",
        "写篇",
        "写稿",
        "稿件",
        "新建稿件",
        "改稿",
        "文本",
        "正文",
        "文章",
        "论文",
        "文稿",
        "文档",
        "工作台",
        "资料卡",
        "引用卡",
        "引用框",
        "引用篮",
        "引用",
        "段落",
        "这段",
        "这段文字",
        "选区",
        "划词",
        "句子",
        "篇章",
        "插入",
        "贴进去",
        "写入",
        "改写",
        "续写",
        "报告",
        "writing",
        "workbench",
        "paragraph",
        "canvas",
        "cavanse",
        "draft",
        "citation",
        "citations",
        "reference card",
    }
)
_CAPABILITY_TOKENS = frozenset({"mcp", "工具", "能力", "tool", "capability", "能做什么", "可以做什么"})
_WORKFLOW_TOKENS = frozenset({"workflow", "workflow_graph", "工作流", "图", "graph"})
_TASK_CONTROL_TOKENS = frozenset({"取消", "重试", "继续", "cancel", "retry", "continue"})
_TASK_TARGET_TOKENS = frozenset({"任务", "task", "审批", "approval"})
_PROJECT_CONTEXT_TOKENS = frozenset({"项目", "会话", "状态", "source library", "source-library", "source_library", "来源库", "ingest"})


_TOOL_WINDOW_PROFILES = (
    _ToolWindowProfileDefinition(
        name="source-library-execute-explicit",
        reason="source-library item key is explicit; expose the governed execution tool directly",
        require_all=("source_key", "asks_source", "asks_execute"),
        tools=("ingest.source_library.run",),
    ),
    _ToolWindowProfileDefinition(
        name="source-library-execute",
        reason="source-library execution request; expose selection reads and governed execution",
        require_all=("asks_source", "asks_execute"),
        tools=(
            "source_library.item.list",
            "source_library.item.search",
            "source_library.item.inspect",
            "ingest.source_library.run",
        ),
    ),
    _ToolWindowProfileDefinition(
        name="source-library-read",
        reason="user explicitly asks about source-library entries rather than stored project materials",
        require_all=("asks_source",),
        require_none=("asks_execute", "asks_discovery_plan"),
        tools=(
            "source_library.item.list",
            "source_library.item.search",
            "source_library.item.inspect",
            "ingest.status.read",
        ),
    ),
    _ToolWindowProfileDefinition(
        name="source-discovery-plan",
        reason="external source discovery planning request; expose no-fetch trust planning and source-library reads",
        require_all=("asks_discovery_plan",),
        require_none=("asks_writing",),
        tools=(
            "source.discovery.plan",
            "source.web.search",
            "source.candidate.review",
            "ingest.url_pool.submit",
            "ingest.url_pool.status",
            "source.history.read",
            "source_library.item.search",
            "source_library.item.list",
            "project.structured_graph.query",
            "project.structured_data.search",
            "project.structured_data.item.read",
            "project.structured_data.items.read",
            "project.context.resource.read",
        ),
    ),
    _ToolWindowProfileDefinition(
        name="material-collection",
        reason="general material supplementation should prepare governed collection, not only read stored project materials",
        require_all=("asks_material_collection",),
        require_none=("asks_writing", "asks_internal_material"),
        tools=(
            "project.context.bundle",
            "project.summary.read",
            "project.structured_data.search",
            "project.structured_data.item.read",
            "project.structured_data.items.read",
            "project.context.resource.read",
            "agent_artifact.search",
            "source.discovery.plan",
            "source.web.search",
            "source.candidate.review",
            "ingest.url_pool.submit",
            "ingest.url_pool.status",
            "source.history.read",
            "source_library.item.search",
            "source_library.item.list",
            "ingest.source_library.run",
            "ingest.status.read",
            "agent_batch.submit",
        ),
    ),
    _ToolWindowProfileDefinition(
        name="long-task-investigation",
        reason="long-running investigation or writing request; expose planning, resume, data, graph, and source-discovery tools",
        require_all=("asks_long_task",),
        tools=(
            "agent_task.plan.append",
            "agent_long_task.stage.update",
            "agent_long_task.stage.read",
            "agent_session.resume_bundle",
            "project.context.bundle",
            "project.summary.read",
            "project.structured_graph.query",
            "project.graph.search",
            "project.structured_data.search",
            "project.structured_data.item.read",
            "project.structured_data.items.read",
            "project.context.resource.read",
            "source.discovery.plan",
            "source.web.search",
            "source.candidate.review",
            "ingest.url_pool.submit",
            "ingest.url_pool.status",
            "source.history.read",
            "agent_investigation.leads.append",
            "agent_investigation.trace.read",
            "writing.document.list",
            "writing.document.read",
            "writing.document.section.read",
            "writing.document.create",
            "writing.document.insert_paragraph",
            "writing.document.citations.upsert",
            "ingest.source_library.run",
            "source_library.item.search",
            "source_library.item.list",
            "agent_artifact.search",
            "ingest.status.read",
            "agent_batch.submit",
            "skill.search",
            "skill.load",
            "mcp.service.catalog",
            "mcp.tools.list",
        ),
    ),
    _ToolWindowProfileDefinition(
        name="capability-catalog",
        reason="user asks about available tools or capabilities",
        require_all=("asks_capability",),
        tools=(
            "agent_runtime.capability.catalog",
            "agent_runtime.tool.search",
            "agent_runtime.tool_pool.list",
            "mcp.service.catalog",
            "mcp.tools.list",
            "skill.search",
            "skill.load",
            "project.summary.read",
        ),
    ),
    _ToolWindowProfileDefinition(
        name="workflow",
        reason="user asks about workflow graph state or execution",
        require_all=("asks_workflow",),
        require_none=("asks_project_data",),
        tools=("workflow_graph.list", "workflow_graph.inspect", "project.graph.search"),
        conditional_tool_groups=(
            _ConditionalToolGroup(
                require_all=("asks_execute",),
                tools=("workflow_graph.run", "skill.search", "skill.load"),
                skill_prefix_matches=("workflow_graph",),
            ),
        ),
    ),
    _ToolWindowProfileDefinition(
        name="writing-workbench",
        reason="user asks for writing/report workbench support",
        require_all=("asks_writing",),
        tools=(
            "agent_task.plan.append",
            "agent_long_task.stage.update",
            "agent_long_task.stage.read",
            "agent_session.resume_bundle",
            "project.context.bundle",
            "writing.document.list",
            "writing.document.read",
            "writing.document.section.read",
            "writing.document.create",
            "writing.document.insert_paragraph",
            "writing.document.citations.upsert",
            "project.structured_graph.query",
            "project.graph.search",
            "project.structured_data.search",
            "project.structured_data.item.read",
            "project.structured_data.items.read",
            "project.context.resource.read",
            "source.discovery.plan",
            "source.web.search",
            "source.candidate.review",
            "ingest.url_pool.submit",
            "ingest.url_pool.status",
            "source.history.read",
            "ingest.source_library.run",
            "agent_investigation.trace.read",
            "source_library.item.search",
            "agent_artifact.search",
            "agent_artifact.read",
            "report.generate",
            "skill.search",
        ),
        skill_prefix_matches=("workflow_graph.curated",),
    ),
    _ToolWindowProfileDefinition(
        name="data-quality-audit",
        reason="user asks for stored data quality, noise, or cleaning audit",
        require_all=("asks_data_quality",),
        tools=(
            "project.structured_data.quality_audit",
            "project.summary.read",
        ),
    ),
    _ToolWindowProfileDefinition(
        name="project-context",
        reason="user asks for current project/session/source-library data",
        require_all=("asks_project_data",),
        tools=(
            "project.context.bundle",
            "project.summary.read",
            "project.structured_graph.query",
            "project.structured_data.search",
            "project.structured_data.item.read",
            "project.structured_data.items.read",
            "project.context.resource.read",
            "project.structured_data.quality_audit",
            "agent_artifact.search",
            "writing.document.list",
        ),
    ),
    _ToolWindowProfileDefinition(
        name="task-control",
        reason="user asks to control an existing task or approval",
        require_all=("asks_task_control",),
        tools=("task.cancel", "task.retry", "task.continue", "agent_session.context.read", "agent_session.resume_bundle", "ingest.status.read"),
    ),
    _ToolWindowProfileDefinition(
        name="project-context",
        reason="user asks for current project/session/source-library data",
        require_all=("asks_project_context",),
        tools=(
            "project.context.bundle",
            "project.summary.read",
            "project.structured_graph.query",
            "project.graph.search",
            "project.structured_data.search",
            "project.structured_data.item.read",
            "project.structured_data.items.read",
            "project.context.resource.read",
            "project.structured_data.quality_audit",
            "agent_session.context.read",
            "agent_artifact.search",
            "writing.document.list",
            "ingest.status.read",
        ),
    ),
)


def select_core_tool_window(
    *,
    message: str,
    tool_specs: list[CoreToolSpec],
    forced_tool_names: set[str] | None = None,
) -> CoreToolWindow:
    specs = list(tool_specs or [])
    by_name = {spec.name: spec for spec in specs}
    forced = {str(item or "").strip() for item in set(forced_tool_names or set()) if str(item or "").strip()}
    text = str(message or "")
    lowered = text.lower()
    signals = _extract_tool_window_signals(text, lowered)
    definition = _match_tool_window_profile(signals)
    if definition is None:
        profile = "conversation"
        reason = "ordinary conversation does not need the project tool catalog"
        selected: list[str] = []
    else:
        profile = definition.name
        reason = definition.reason
        selected = list(definition.tools)
        for needle in definition.skill_prefix_matches:
            selected.extend(_skill_names_matching(by_name, needle))
        for group in definition.conditional_tool_groups:
            if _signals_match(signals, require_all=group.require_all, require_none=group.require_none):
                selected.extend(group.tools)
                for needle in group.skill_prefix_matches:
                    selected.extend(_skill_names_matching(by_name, needle))

    selected.extend(sorted(forced))
    visible = _dedupe_specs(by_name, selected)
    return CoreToolWindow(specs=tuple(visible), profile=profile, reason=reason, full_tool_count=len(specs))


def _extract_tool_window_signals(text: str, lowered: str) -> dict[str, bool]:
    material_intent = classify_material_intent(text)
    source_key = bool(extract_source_library_item_key(text))
    asks_source = _has_any(lowered, _SOURCE_LIBRARY_TOKENS) or material_intent.category == "source_catalog"
    asks_external_source = _has_any(lowered, _EXTERNAL_SOURCE_TOKENS)
    asks_internal_material = _has_any(lowered, _INTERNAL_MATERIAL_TOKENS) or material_intent.category in {"internal_existing", "internal_generated"}
    asks_data_quality = _has_any(lowered, _DATA_QUALITY_TOKENS)
    asks_project_data = _has_any(lowered, _PROJECT_DATA_TOKENS) or asks_data_quality
    asks_collect_action = _has_any(lowered, _COLLECTION_ACTION_TOKENS)
    asks_execute = _has_any(lowered, _EXECUTION_TOKENS) or asks_collect_action
    asks_material_collection = _has_any(lowered, _MATERIAL_COLLECTION_TOKENS) or (
        asks_project_data and asks_execute and not asks_internal_material
    ) or (
        material_intent.category in {"external_discovery", "external_ingest"}
        and material_intent.material_state == "to_collect"
    )
    asks_discovery_plan = _has_any(lowered, _DISCOVERY_PLAN_TOKENS) or asks_external_source
    asks_long_task = _has_any(lowered, _LONG_TASK_TOKENS)
    asks_writing = _has_any(lowered, _WRITING_TOKENS)
    asks_capability = _has_any(lowered, _CAPABILITY_TOKENS)
    asks_workflow = _has_any(lowered, _WORKFLOW_TOKENS)
    asks_task_control = _has_any(lowered, _TASK_CONTROL_TOKENS) and _has_any(lowered, _TASK_TARGET_TOKENS)
    asks_project_context = _has_any(lowered, _PROJECT_CONTEXT_TOKENS)
    return {
        "source_key": source_key,
        "asks_source": asks_source,
        "asks_external_source": asks_external_source,
        "asks_internal_material": asks_internal_material,
        "asks_project_data": asks_project_data,
        "asks_data_quality": asks_data_quality,
        "asks_execute": asks_execute,
        "asks_material_collection": asks_material_collection,
        "asks_discovery_plan": asks_discovery_plan,
        "asks_long_task": asks_long_task,
        "asks_writing": asks_writing,
        "asks_capability": asks_capability,
        "asks_workflow": asks_workflow,
        "asks_task_control": asks_task_control,
        "asks_project_context": asks_project_context,
    }


def _match_tool_window_profile(signals: dict[str, bool]) -> _ToolWindowProfileDefinition | None:
    for definition in _TOOL_WINDOW_PROFILES:
        if _signals_match(signals, require_all=definition.require_all, require_none=definition.require_none):
            return definition
    return None


def _signals_match(signals: dict[str, bool], *, require_all: tuple[str, ...] = (), require_none: tuple[str, ...] = ()) -> bool:
    values = signals or {}
    return all(values.get(key) for key in require_all) and not any(values.get(key) for key in require_none)


def extract_source_library_item_key(message: str) -> str | None:
    matches = re.findall(r"\b[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+\b", str(message or ""), flags=re.IGNORECASE)
    for item in matches:
        lowered = item.lower()
        if lowered in {"source.library", "source-library"}:
            continue
        return item
    return None


def _has_any(text: str, tokens: set[str]) -> bool:
    return any(token in text for token in tokens)


def _skill_names_matching(by_name: dict[str, CoreToolSpec], needle: str) -> list[str]:
    value = str(needle or "").strip()
    if not value:
        return []
    return [name for name in by_name if name.startswith("skill.") and value in name]


def _dedupe_specs(by_name: dict[str, CoreToolSpec], names: list[str]) -> list[CoreToolSpec]:
    out: list[CoreToolSpec] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        spec = by_name.get(name)
        if spec is not None:
            out.append(spec)
    return out
