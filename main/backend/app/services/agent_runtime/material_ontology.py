from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


MaterialCategory = str


@dataclass(frozen=True)
class MaterialIntent:
    category: MaterialCategory
    scope: str
    material_state: str
    work_context: str
    risk: str
    label: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


INTERNAL_EXISTING = "internal_existing"
INTERNAL_GENERATED = "internal_generated"
SOURCE_CATALOG = "source_catalog"
EXTERNAL_DISCOVERY = "external_discovery"
EXTERNAL_INGEST = "external_ingest"
UNKNOWN = "unknown"


_CATEGORY_LABELS = {
    INTERNAL_EXISTING: "内部已有资料",
    INTERNAL_GENERATED: "内部生成材料",
    SOURCE_CATALOG: "来源库/采集入口",
    EXTERNAL_DISCOVERY: "外部发现计划",
    EXTERNAL_INGEST: "外部采集/写入",
    UNKNOWN: "未分类材料",
}

_SOURCE_CATALOG_TOKENS = (
    "source_library",
    "source library",
    "source-library",
    "来源库",
    "数据源",
    "采集源",
    "采集入口",
    "item_key",
    "source item",
)

_EXTERNAL_TOKENS = (
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
    "新收集",
    "再找来源",
    "再找资料",
    "再找数据",
    "external",
    "web",
    "online",
    "internet",
)

_INTERNAL_TOKENS = (
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
    "既有",
    "已有资料",
    "已有数据",
    "既有资料",
    "既有数据",
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
    "项目资料",
    "项目材料",
    "existing",
    "stored",
    "internal",
    "local",
)

_MATERIAL_TOKENS = (
    "资料",
    "材料",
    "数据",
    "证据",
    "素材",
    "事实",
    "信息",
    "线索",
    "来源",
    "引用",
    "出处",
    "参考来源",
    "引用来源",
    "参考文献",
    "文档",
    "报告",
    "artifact",
    "artifacts",
    "graph",
    "documents",
    "source",
    "sources",
    "citation",
    "citations",
    "reference",
    "references",
)

_GENERATED_TOKENS = (
    "生成",
    "产物",
    "artifact",
    "artifacts",
    "草稿",
    "摘要",
    "报告",
    "trace",
    "plan",
    "generated",
)

_COLLECTION_TOKENS = (
    "补充",
    "补资料",
    "补充资料",
    "补材料",
    "补素材",
    "补一些",
    "补一点",
    "扩充",
    "扩充资料",
    "扩展资料",
    "新增资料",
    "添加资料",
    "找资料",
    "找些",
    "找一些",
    "再找",
    "再找来源",
    "继续找",
    "查找",
    "查资料",
    "查一下",
    "收集",
    "搜集",
    "搜一下",
    "采集",
    "抓取",
    "补证据",
    "检索",
    "搜索",
    "搜索来源",
    "collect",
    "crawl",
    "gather",
    "supplement",
    "ingest",
    "search",
)

_GAP_TOKENS = (
    "不足",
    "不够",
    "缺",
    "缺少",
    "缺口",
    "空白",
    "补强",
    "需要更多",
    "not enough",
    "insufficient",
    "gap",
    "missing",
)

_INGEST_TOKENS = (
    "入库",
    "导入",
    "写入",
    "保存到",
    "登记到",
    "跑来源库",
    "执行来源库",
    "采集入库",
    "run source_library",
    "source_library.run",
    "ingest",
)

_WRITING_TOKENS = (
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

_INVESTIGATION_TOKENS = (
    "调查",
    "线索",
    "追查",
    "多轮",
    "trace",
    "investigation",
    "clue",
)


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def category_label(category: str | None) -> str:
    return _CATEGORY_LABELS.get(str(category or ""), _CATEGORY_LABELS[UNKNOWN])


def classify_material_intent(message: str) -> MaterialIntent:
    text = str(message or "").strip().lower()
    has_catalog = _contains_any(text, _SOURCE_CATALOG_TOKENS)
    has_external = _contains_any(text, _EXTERNAL_TOKENS)
    has_internal = _contains_any(text, _INTERNAL_TOKENS)
    has_material = _contains_any(text, _MATERIAL_TOKENS)
    wants_collection = _contains_any(text, _COLLECTION_TOKENS)
    wants_ingest = _contains_any(text, _INGEST_TOKENS)
    is_writing = _contains_any(text, _WRITING_TOKENS)
    is_investigation = _contains_any(text, _INVESTIGATION_TOKENS)

    work_context = "writing" if is_writing else "investigation" if is_investigation else "project_read" if has_material or has_catalog else "conversation"

    if has_catalog:
        return _intent(
            SOURCE_CATALOG,
            scope="external" if wants_collection else "mixed",
            material_state="catalog",
            work_context=work_context,
            risk="write_external" if wants_collection else "read_only",
            reason="explicit source catalog or data-source wording",
        )
    if is_writing and has_internal and has_material and not _contains_any(text, _GAP_TOKENS) and not wants_ingest:
        return _intent(
            INTERNAL_EXISTING,
            scope="internal",
            material_state="existing",
            work_context="writing",
            risk="read_only",
            reason="writing request explicitly points to existing project or already collected material",
        )
    if is_writing and wants_collection and has_material and _contains_any(text, _GAP_TOKENS):
        return _intent(
            EXTERNAL_DISCOVERY,
            scope="mixed",
            material_state="to_collect",
            work_context="writing",
            risk="read_only",
            reason="writing material gap can escalate from internal evidence to external discovery",
        )
    if has_external:
        return _intent(
            EXTERNAL_INGEST if wants_ingest else EXTERNAL_DISCOVERY,
            scope="external",
            material_state="to_collect" if wants_collection or wants_ingest else "catalog",
            work_context=work_context,
            risk="write_external" if wants_ingest else "read_only",
            reason="explicit external/web material scope",
        )
    if wants_collection and has_material and not (is_writing or has_internal):
        return _intent(
            EXTERNAL_DISCOVERY,
            scope="mixed",
            material_state="to_collect",
            work_context="execution",
            risk="write_shared",
            reason="general material supplementation asks for gathering; inspect internal context before external discovery",
        )
    if is_writing and wants_collection and has_material and not has_external:
        return _intent(
            INTERNAL_EXISTING,
            scope="internal",
            material_state="existing",
            work_context="writing",
            risk="read_only",
            reason="writing material supplementation starts from project-local material unless external collection is explicit",
        )
    if has_internal or has_material:
        generated = _contains_any(text, _GENERATED_TOKENS)
        category = INTERNAL_GENERATED if generated and not has_internal else INTERNAL_EXISTING
        return _intent(
            category,
            scope="internal",
            material_state="generated" if category == INTERNAL_GENERATED else "existing",
            work_context=work_context,
            risk="read_only",
            reason="project-local or already available material wording",
        )
    return _intent(UNKNOWN, scope="unknown", material_state="unknown", work_context=work_context, risk="read_only", reason="no material signal")


def capability_material_category(capability_id: str | None) -> MaterialCategory:
    item = str(capability_id or "")
    if item in {"project.summary.read", "project.structured_data.search", "project.structured_data.quality_audit", "project.context.bundle", "project.graph.search", "project.structured_graph.query"}:
        return INTERNAL_EXISTING
    if item in {"writing.document.list", "writing.document.read"}:
        return INTERNAL_EXISTING
    if item in {"agent_artifact.search", "agent_artifact.read", "agent_investigation.trace.read", "agent_long_task.stage.read", "agent_long_task.stage.update"}:
        return INTERNAL_GENERATED
    if item.startswith("source_library.item."):
        return SOURCE_CATALOG
    if item in {"source.discovery.plan", "source.web.search", "source.candidate.review"}:
        return EXTERNAL_DISCOVERY
    if item in {"ingest.source_library.run", "ingest.url_pool.submit", "agent_batch.nl_command.submit", "agent_batch.submit"}:
        return EXTERNAL_INGEST
    if item in {"ingest.url_pool.status", "source.history.read"}:
        return INTERNAL_EXISTING
    return UNKNOWN


def material_annotation_for_capability(capability_id: str | None) -> dict[str, Any]:
    category = capability_material_category(capability_id)
    return {
        "category": category,
        "label": category_label(category),
    }


def annotate_capability_result(capability_call: dict[str, Any]) -> dict[str, Any]:
    out = dict(capability_call or {})
    category = capability_material_category(str(out.get("capability_id") or out.get("tool_name") or ""))
    if category == UNKNOWN:
        return out
    annotation = {"category": category, "label": category_label(category)}
    out["material_category"] = annotation
    result = dict(out.get("result") or {})
    result.setdefault("material_category", annotation)
    out["result"] = result
    return out


def _intent(category: str, *, scope: str, material_state: str, work_context: str, risk: str, reason: str) -> MaterialIntent:
    return MaterialIntent(
        category=category,
        scope=scope,
        material_state=material_state,
        work_context=work_context,
        risk=risk,
        label=category_label(category),
        reason=reason,
    )
