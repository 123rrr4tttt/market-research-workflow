"""数据库管理API"""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, List, Literal, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ..composition.raw_material_import_task import (
    RAW_MATERIAL_IMPORT_TASK_DEFINITION,
    RawMaterialImportAsyncResult,
    RawMaterialImportTaskBinding,
    RawMaterialImportTaskDefinition,
)
from ..contracts import ApiEnvelope, ErrorCode, success_response, task_result_response
from ..contracts.raw_material_import import RawImportRequest
from ..project_customization import get_project_customization
from ..services import document_admin
from ..services.document_admin import AdminMaterialSnapshot, JsonObject, optional_json_object, parse_json_object
from ..services.document_views import (
    build_social_data_item,
    get_extracted_data,
)
from ..services.extraction.topic_workflow import run_topic_extraction_workflow
from ..services.ingest.adapters.http_utils import fetch_html
from ..services.ingest.postprocess_frontdoor import run_frontdoor_extraction
from ..services.ingest.url_pool import _extract_text_from_html
from ..services.projects import current_project_key
from ..services.projects.context import resolve_request_project_context
from ._error_responses import error_json_response as _error_json

if TYPE_CHECKING:
    from ..services.graph.models import Graph


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _project_key_fallback() -> str:
    from ..settings.config import settings
    try:
        from sqlalchemy import text

        from ..models.base import engine
        with engine.connect() as conn:
            conn.execute(text('SET search_path TO "public"'))
            row = conn.execute(
                text("SELECT project_key FROM public.projects WHERE is_active = true LIMIT 1")
            ).fetchone()
            if row:
                return str(row[0])
    except Exception:
        pass
    return settings.active_project_key or "default"


def _project_key_from_request(request: Request) -> str:
    """Resolve explicit request scope through the shared request-scope owner."""
    project_key, _, _ = resolve_request_project_context(
        request,
        fallback=_project_key_fallback,
        use_resolved_fallback=True,
    )
    return project_key


def _empty_graph_response():
    """Return a successful empty graph payload to keep frontend contract stable."""
    from app.services.graph.exporter import export_to_json
    from app.services.graph.models import Graph

    return success_response(export_to_json(Graph()))


def _parse_iso_date_or_error(value: Optional[str], *, field: str) -> tuple[date | None, JSONResponse | None]:
    if not value:
        return None, None
    try:
        return datetime.fromisoformat(value).date(), None
    except Exception as exc:  # noqa: BLE001
        logger.warning("解析日期失败 field=%s value=%s err=%s", field, value, exc)
        return None, _error_json(
            400,
            ErrorCode.INVALID_INPUT,
            f"{field} must be a valid ISO date (YYYY-MM-DD)",
            details={"field": field, "value": value},
        )




class MaterialListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    state: Optional[str] = None
    material_type: Optional[str] = None
    has_extracted_data: Optional[bool] = None
    search: Optional[str] = None
    sort_by: Optional[str] = Field(default="created_at", description="排序字段: created_at, publish_date, id")
    sort_order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$", description="排序方向: asc, desc")



class SourceListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    kind: Optional[str] = None
    enabled: Optional[bool] = None
    sort_by: Optional[str] = Field(default="created_at", description="排序字段: created_at, id, name, material_count")
    sort_order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$", description="排序方向: asc, desc")


class SocialDataListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    platform: Optional[str] = None
    search: Optional[str] = None
    sentiment_orientation: Optional[str] = Field(None, pattern="^(positive|negative|neutral)$", description="情感倾向: positive, negative, neutral")
    sort_by: Optional[str] = Field(default="created_at", description="排序字段: created_at, publish_date, id")
    sort_order: Optional[str] = Field(default="desc", pattern="^(asc|desc)$", description="排序方向: asc, desc")


def _material_sort_field(value: str | None) -> Literal["created_at", "publish_date", "id"]:
    if value == "publish_date":
        return "publish_date"
    if value == "id":
        return "id"
    return "created_at"


def _source_sort_field(value: str | None) -> Literal["created_at", "id", "name", "material_count"]:
    if value == "id":
        return "id"
    if value == "name":
        return "name"
    if value == "material_count":
        return "material_count"
    return "created_at"


def _sort_order(value: str | None) -> Literal["asc", "desc"]:
    return "asc" if value == "asc" else "desc"


def _sentiment_orientation(value: str | None) -> Literal["positive", "negative", "neutral"] | None:
    if value == "positive":
        return "positive"
    if value == "negative":
        return "negative"
    if value == "neutral":
        return "neutral"
    return None


class DeleteMaterialsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_ids: List[int]
    preview: bool = Field(default=False, description="仅预览影响范围，不执行删除")


def _build_material_delete_preview(materials: list[AdminMaterialSnapshot], requested_ids: list[int]) -> JsonObject:
    found_ids = {material["material_id"] for material in materials}
    missing_ids = [int(material_id) for material_id in requested_ids if int(material_id) not in found_ids]
    risk_tags = ["destructive_write", "bulk_delete"]
    if len(materials) >= 10:
        risk_tags.append("large_batch")
    if missing_ids:
        risk_tags.append("missing_ids")

    samples: list[JsonValue] = []
    for material in materials[:5]:
        samples.append(
            {
                "material_id": material["material_id"],
                "title": material["title"],
                "material_type": material["material_type"],
                "state": material["state"],
                "uri": material["uri"],
                "source_id": material["source_id"],
                "has_extracted_data": material["extracted_data"] is not None,
            }
        )

    evidence = _build_admin_preview_evidence(
        action="materials.delete",
        materials=materials,
        requested_ids=requested_ids,
        missing_ids=missing_ids,
        risk_tags=risk_tags,
        filters={"material_ids": [int(material_id) for material_id in requested_ids]},
    )

    return parse_json_object({
        "preview": True,
        "action": "materials.delete",
        "action_kind": "materials.delete",
        "would_affect_count": len(materials),
        "samples": samples,
        "risk_tags": risk_tags,
        "risk_labels": risk_tags,
        "requires_confirmation": bool(materials),
        "requested": len(requested_ids),
        "missing": missing_ids,
        **evidence,
    }, field="material_delete_preview")


class ReExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_ids: Optional[List[int]] = None
    preview: bool = Field(default=False, description="仅预览影响范围，不执行重抽取")
    force: bool = Field(default=False, description="是否强制重新提取已有数据的文档")
    fetch_missing_content: bool = Field(default=False, description="content为空时，尝试抓取正文后再提取")
    batch_size: int = Field(default=20, ge=1, le=200, description="分批提交大小（降低长事务）")
    limit: Optional[int] = Field(default=None, ge=1, le=5000, description="最多处理文档数")
    treat_empty_er_as_missing: bool = Field(default=True, description="entities_relations存在但实体/关系为空时仍视为缺失")


def _build_material_preview_samples(materials: list[AdminMaterialSnapshot]) -> list[JsonObject]:
    samples: list[JsonObject] = []
    for material in materials[:5]:
        content = material["content"]
        samples.append(
            {
                "material_id": material["material_id"],
                "title": material["title"],
                "material_type": material["material_type"],
                "state": material["state"],
                "uri": material["uri"],
                "source_id": material["source_id"],
                "has_content": bool(str(content or "").strip()),
                "has_extracted_data": material["extracted_data"] is not None,
            }
        )
    return samples


def _admin_preview_material_ref(material: AdminMaterialSnapshot, *, action: str) -> JsonObject:
    material_id = material["material_id"]
    return {
        "id": f"admin.preview.{action}.material:{material_id}",
        "kind": "material_record",
        "table": "materials",
        "material_id": material_id,
        "title": material["title"],
        "material_type": material["material_type"],
        "state": material["state"],
        "uri": material["uri"],
        "source_id": material["source_id"],
        "columns": ["material_id", "title", "material_type", "state", "uri", "source_id", "extracted_data"],
    }


def _build_admin_preview_evidence(
    *,
    action: str,
    materials: list[AdminMaterialSnapshot],
    requested_ids: list[int],
    missing_ids: list[int],
    risk_tags: list[str],
    filters: JsonObject,
) -> JsonObject:
    source_refs = [_admin_preview_material_ref(material, action=action) for material in materials[:20]]
    source_query = parse_json_object({
        "scope": "admin.preview",
        "action": action,
        "table": "materials",
        "filters": filters,
        "selection": {
            "requested_material_ids": [int(material_id) for material_id in requested_ids],
            "requested_count": len(requested_ids),
            "matched_count": len(materials),
            "missing_material_ids": [int(material_id) for material_id in missing_ids],
            "missing_count": len(missing_ids),
        },
    }, field="admin_preview.source_query")
    trace_chain: JsonValue = [
        {
            "stage": "admin.preview.request",
            "status": "received",
            "action": action,
            "requested_count": len(requested_ids),
        },
        {
            "stage": "admin.preview.selection",
            "status": "matched" if materials else "empty",
            "matched_count": len(materials),
            "missing_count": len(missing_ids),
        },
        {
            "stage": "admin.preview.confirmation",
            "status": "required" if materials else "not_required",
            "requires_confirmation": bool(materials),
            "risk_tags": list(risk_tags),
        },
    ]
    evidence_preview = parse_json_object({
        "preview": True,
        "evidence_kind": "material_selection",
        "source": "admin_preview",
        "materials_matched": len(materials),
        "materials_sampled": len(source_refs),
        "missing_material_ids": [int(material_id) for material_id in missing_ids],
        "source_ref_ids": [str(ref["id"]) for ref in source_refs],
        "fields_are_predicted": False,
        "execution_result_available": False,
    }, field="admin_preview.evidence_preview")
    return parse_json_object({
        "source_query": source_query,
        "source_refs": source_refs,
        "trace_chain": trace_chain,
        "evidence_preview": evidence_preview,
    }, field="admin_preview_evidence")


def _admin_after_action_material_ref(material: AdminMaterialSnapshot, *, action: str) -> JsonObject:
    material_id = material["material_id"]
    return {
        "id": f"admin.after_action.{action}.material:{material_id}",
        "kind": "material_record",
        "table": "materials",
        "material_id": material_id,
        "title": material["title"],
        "material_type": material["material_type"],
        "state": material["state"],
        "uri": material["uri"],
        "source_id": material["source_id"],
        "columns": ["material_id", "title", "material_type", "state", "uri", "source_id", "extracted_data"],
    }


def _admin_response_project_key() -> str:
    return current_project_key()


def _admin_response_trace_id(
    *,
    action_kind: str,
    project_key: str,
    requested_ids: list[int],
    affected_count: int,
    missing_ids: list[int],
    skipped_count: int,
    status: str,
) -> str:
    seed = {
        "action_kind": action_kind,
        "project_key": project_key,
        "requested_material_ids": [int(material_id) for material_id in requested_ids],
        "affected_count": int(affected_count),
        "missing_material_ids": [int(material_id) for material_id in missing_ids],
        "skipped_count": int(skipped_count),
        "status": status,
    }
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()[:20]
    return f"admin-response-readback-{digest}"


def _build_admin_after_action_evidence(
    *,
    action: str,
    pre_mutation_docs: list[AdminMaterialSnapshot],
    requested_ids: list[int],
    missing_ids: list[int],
    affected_count: int,
    skipped_count: int,
    status: str,
    filters: JsonObject,
    rollback_hint: str,
    execution_summary: JsonObject | None = None,
) -> JsonObject:
    """Describe a completed mutation from its pre-mutation selection snapshot.

    The compatible ``response_readback`` fields are response-level provenance only.
    They are neither a persistent audit record nor a post-commit database readback.
    """
    project_key = _admin_response_project_key()
    executed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    normalized_requested_ids = [int(material_id) for material_id in requested_ids]
    normalized_missing_ids = [int(material_id) for material_id in missing_ids]
    trace_id = _admin_response_trace_id(
        action_kind=action,
        project_key=project_key,
        requested_ids=normalized_requested_ids,
        affected_count=affected_count,
        missing_ids=normalized_missing_ids,
        skipped_count=skipped_count,
        status=status,
    )
    source_refs = [_admin_after_action_material_ref(material, action=action) for material in pre_mutation_docs[:20]]
    source_query = parse_json_object({
        "scope": "admin.after_action.response_readback",
        "action": action,
        "table": "materials",
        "filters": filters,
        "selection": {
            "requested_material_ids": normalized_requested_ids,
            "requested_count": len(normalized_requested_ids),
            "matched_count": len(pre_mutation_docs),
            "affected_count": int(affected_count),
            "missing_material_ids": normalized_missing_ids,
            "missing_count": len(normalized_missing_ids),
            "skipped_count": int(skipped_count),
            "source_snapshot_timing": "pre_mutation",
            "post_commit_readback_performed": False,
        },
    }, field="admin_after_action.source_query")
    audit_event = parse_json_object({
        "contract_version": "admin.mutation.response_audit_readback.v1",
        "audit_scope": "response_level_only",
        "persistence": "not_persisted",
        "trace_id": trace_id,
        "action_kind": action,
        "project_key": project_key,
        "requested_count": len(normalized_requested_ids),
        "affected_count": int(affected_count),
        "executed_at": executed_at,
        "status": status,
    }, field="admin_after_action.audit_event")
    execution_result = parse_json_object({
        "execution_result_available": True,
        "trace_id": trace_id,
        "action_kind": action,
        "status": status,
        "affected_count": int(affected_count),
        "requested_count": len(normalized_requested_ids),
        "matched_count": len(pre_mutation_docs),
        "missing_ids": normalized_missing_ids,
        "missing_count": len(normalized_missing_ids),
        "skipped_count": int(skipped_count),
    }, field="admin_after_action.execution_result")
    if execution_summary:
        execution_result.update(execution_summary)

    trace_chain: JsonValue = [
        {
            "stage": "admin.after_action.request",
            "status": "received",
            "action": action,
            "trace_id": trace_id,
            "requested_count": len(normalized_requested_ids),
        },
        {
            "stage": "admin.after_action.selection",
            "status": "matched" if pre_mutation_docs else "empty",
            "trace_id": trace_id,
            "matched_count": len(pre_mutation_docs),
            "missing_count": len(normalized_missing_ids),
        },
        {
            "stage": "admin.after_action.mutation",
            "status": status,
            "trace_id": trace_id,
            "affected_count": int(affected_count),
            "skipped_count": int(skipped_count),
        },
        {
            "stage": "admin.after_action.response_readback",
            "status": "available",
            "trace_id": trace_id,
            "execution_result_available": True,
        },
    ]
    response_level_audit_readback = parse_json_object({
        "contract_version": "admin.mutation.response_audit_readback.v1",
        "scope": "response_level_only",
        "persistence": "not_persisted",
        "audit_event": audit_event,
        "source_ref_ids": [str(ref["id"]) for ref in source_refs],
    }, field="admin_after_action.audit_readback")
    return parse_json_object({
        "action_kind": action,
        "audit_event": audit_event,
        "audit_trail": [audit_event],
        "response_level_audit_readback": response_level_audit_readback,
        "execution_result": execution_result,
        "source_query": source_query,
        "source_refs": source_refs,
        "trace_chain": trace_chain,
        "rollback_hint": rollback_hint,
        "rollback_recommendation": rollback_hint,
    }, field="admin_after_action_evidence")


def _build_bulk_extracted_data_preview(
    materials: list[AdminMaterialSnapshot],
    *,
    payload: "BulkUpdateExtractedDataRequest",
    missing: list[int],
) -> JsonObject:
    risk_tags = ["bulk_write", "extracted_data_update"]
    if payload.mode == "replace":
        risk_tags.append("replace_write")
    if payload.mode == "merge":
        risk_tags.append("merge_write")
    if payload.extracted_data is None:
        risk_tags.append("clears_extracted_data")
    if len(materials) >= 10:
        risk_tags.append("large_batch")
    if missing:
        risk_tags.append("missing_ids")

    evidence = _build_admin_preview_evidence(
        action="materials.bulk_extracted_data",
        materials=materials,
        requested_ids=payload.material_ids,
        missing_ids=missing,
        risk_tags=risk_tags,
        filters=parse_json_object({
            "material_ids": [int(material_id) for material_id in payload.material_ids],
            "mode": payload.mode,
            "clears_extracted_data": payload.extracted_data is None,
        }, field="bulk_extracted_data_preview.filters"),
    )

    return parse_json_object({
        "preview": True,
        "action": "materials.bulk_extracted_data",
        "action_kind": "materials.bulk_extracted_data",
        "would_affect_count": len(materials),
        "samples": _build_material_preview_samples(materials),
        "risk_tags": risk_tags,
        "risk_labels": risk_tags,
        "requires_confirmation": bool(materials),
        "requested": len(payload.material_ids),
        "missing": missing,
        "mode": payload.mode,
        "clears_extracted_data": payload.extracted_data is None,
        **evidence,
    }, field="bulk_extracted_data_preview")


def _build_reextract_preview(materials: list[AdminMaterialSnapshot], payload: ReExtractRequest) -> JsonObject:
    risk_tags = ["bulk_reextract", "extraction_rerun"]
    if payload.force:
        risk_tags.append("force_overwrite")
    if payload.fetch_missing_content:
        risk_tags.append("may_fetch_missing_content")
    if not payload.material_ids:
        risk_tags.append("implicit_material_selection")
    if len(materials) >= 10:
        risk_tags.append("large_batch")

    missing_ids: list[int] = []
    if payload.material_ids:
        found_ids = {material["material_id"] for material in materials}
        missing_ids = [int(material_id) for material_id in payload.material_ids if int(material_id) not in found_ids]
        if missing_ids:
            risk_tags.append("missing_ids")

    evidence = _build_admin_preview_evidence(
        action="materials.re_extract",
        materials=materials,
        requested_ids=payload.material_ids or [],
        missing_ids=missing_ids,
        risk_tags=risk_tags,
        filters=parse_json_object({
            "material_ids": payload.material_ids,
            "force": bool(payload.force),
            "fetch_missing_content": bool(payload.fetch_missing_content),
            "limit": payload.limit,
            "treat_empty_er_as_missing": bool(payload.treat_empty_er_as_missing),
        }, field="reextract_preview.filters"),
    )

    return parse_json_object({
        "preview": True,
        "action": "materials.re_extract",
        "action_kind": "materials.re_extract",
        "would_affect_count": len(materials),
        "samples": _build_material_preview_samples(materials),
        "risk_tags": risk_tags,
        "risk_labels": risk_tags,
        "requires_confirmation": bool(materials),
        "requested": len(payload.material_ids or []),
        "missing": missing_ids,
        "selection": {
            "material_ids": payload.material_ids,
            "force": bool(payload.force),
            "fetch_missing_content": bool(payload.fetch_missing_content),
            "limit": payload.limit,
            "treat_empty_er_as_missing": bool(payload.treat_empty_er_as_missing),
        },
        **evidence,
    }, field="reextract_preview")


class TopicExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topics: List[Literal["company", "product", "operation"]] = Field(default_factory=lambda: ["company", "product", "operation"], min_length=1)
    material_ids: Optional[List[int]] = None
    material_types: Optional[List[str]] = None
    force: bool = Field(default=False)
    fetch_missing_content: bool = Field(default=False)
    batch_size: int = Field(default=10, ge=1, le=100)
    limit: Optional[int] = Field(default=200, ge=1, le=5000)
    candidate_mode: Literal["rules_then_llm"] = "rules_then_llm"


def _get_topic_dictionaries(project_key: str) -> JsonObject:
    """主干只内置谓词/修饰词；项目可通过 field_mapping.topic_dictionaries 提供名词/成分词典。"""
    customization = get_project_customization(project_key)
    fm = parse_json_object(customization.get_field_mapping() or {}, field="project_customization.field_mapping")
    td = optional_json_object(fm.get("topic_dictionaries"), field="field_mapping.topic_dictionaries") or {}
    return {
        "predicates": td.get("predicates") if isinstance(td.get("predicates"), list) else [
            "合作", "并购", "收购", "供应", "分销", "依赖", "运营", "销售", "上架", "投放", "促销", "定价",
            "发布", "推出", "适配", "接入", "升级", "降本", "增长", "转化", "gmv"
        ],
        "modifiers": td.get("modifiers") if isinstance(td.get("modifiers"), list) else [
            "公司", "企业", "品牌", "平台", "店铺", "商家", "型号", "产品", "品类", "渠道", "策略", "指标",
            "model", "product", "brand", "platform", "store", "sku", "category", "component", "pricing"
        ],
        "company_nouns": td.get("company_nouns") if isinstance(td.get("company_nouns"), list) else [],
        "product_nouns": td.get("product_nouns") if isinstance(td.get("product_nouns"), list) else [],
        "operation_nouns": td.get("operation_nouns") if isinstance(td.get("operation_nouns"), list) else [],
        "components": td.get("components") if isinstance(td.get("components"), list) else [
            "电机", "减速器", "传感器", "控制器", "末端执行器", "芯片", "battery", "motor", "sensor", "controller", "actuator"
        ],
    }


def _augment_market_graph_with_topic_structured(
    graph: Graph,
    materials: Iterable[object],
    topic_scope: Literal["company", "product", "operation", ""] | None = None,
) -> None:
    def _read_extracted_data(material: object) -> object:
        return get_extracted_data(material)

    document_admin.augment_market_graph_with_topic_structured(
        graph,
        materials,
        extracted_data_reader=_read_extracted_data,
        topic_scope=topic_scope,
    )


@router.get("/stats", response_model=ApiEnvelope[document_admin.AdminStatsResult])
def get_stats(request: Request):
    """获取数据库统计信息"""
    project_key = _project_key_from_request(request)
    return success_response(document_admin.get_admin_stats(project_key))


def _dispatch_raw_material_import_async(
    binding: RawMaterialImportTaskBinding,
    request: RawImportRequest,
    project_key: str,
) -> RawMaterialImportAsyncResult:
    return binding.delay(request, project_key)


def _run_raw_material_import_sync(
    definition: RawMaterialImportTaskDefinition,
    request: RawImportRequest,
    project_key: str,
) -> dict[str, object]:
    return definition.run_request(request, project_key)


@router.post("/materials/raw-import", response_model=ApiEnvelope[JsonObject])
def raw_import_materials(request: Request, payload: RawImportRequest):
    """Raw data direct ingest: skip fetch stage and reuse project-consistent ingest flow."""
    project_key = _project_key_from_request(request)
    if payload.async_mode:
        from ..services.tasks import raw_material_import_task_binding

        task = _dispatch_raw_material_import_async(
            raw_material_import_task_binding,
            payload,
            project_key,
        )
        task_result = parse_json_object(
            task_result_response(
                task_id=task.id,
                async_mode=True,
                params={"source_name": payload.source_name, "items_total": len(payload.items)},
            ),
            field="raw_import_task_result",
        )
        return success_response(task_result)
    result = _run_raw_material_import_sync(
        RAW_MATERIAL_IMPORT_TASK_DEFINITION,
        payload,
        project_key,
    )
    return success_response(parse_json_object(result, field="raw_import_result"))


@router.post("/materials/list", response_model=ApiEnvelope[document_admin.AdminMaterialPage])
def list_materials(request: Request, payload: MaterialListRequest):
    """列出文档"""
    project_key = _project_key_from_request(request)
    query_spec = document_admin.AdminMaterialListQuery(
        page=payload.page,
        page_size=payload.page_size,
        state=payload.state,
        material_type=payload.material_type,
        has_extracted_data=payload.has_extracted_data,
        search=payload.search,
        sort_by=_material_sort_field(payload.sort_by),
        sort_order=_sort_order(payload.sort_order),
    )
    return success_response(document_admin.list_admin_materials(project_key, query_spec))


class UpdateExtractedDataRequest(BaseModel):
    mode: Literal["replace", "merge"] = Field(default="replace", description="replace: 全量替换；merge: 递归合并(对象)")
    extracted_data: JsonValue = Field(default=None, description="要写入的 JSON 值；null 表示清空 extracted_data")


class BulkUpdateExtractedDataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_ids: List[int] = Field(..., description="要更新的材料ID列表")
    preview: bool = Field(default=False, description="仅预览影响范围，不执行写入")
    mode: Literal["replace", "merge"] = Field(default="replace", description="replace: 全量替换；merge: 递归合并(对象)")
    extracted_data: JsonValue = Field(default=None, description="要写入的 JSON 值；null 表示清空 extracted_data")


@router.post("/materials/bulk/extracted-data", response_model=ApiEnvelope[JsonObject])
def bulk_update_material_extracted_data(payload: BulkUpdateExtractedDataRequest):
    """批量写入/合并文档 extracted_data。"""
    if not payload.material_ids:
        return _error_json(400, ErrorCode.INVALID_INPUT, "material_ids 不能为空")

    command = document_admin.AdminExtractedDataCommand(
        mode=payload.mode,
        extracted_data=payload.extracted_data,
    )
    if payload.preview:
        readback_docs = document_admin.preview_admin_materials(payload.material_ids)
        found_ids = {material["material_id"] for material in readback_docs}
        missing = [material_id for material_id in payload.material_ids if material_id not in found_ids]
        return success_response(_build_bulk_extracted_data_preview(readback_docs, payload=payload, missing=missing))

    result = document_admin.bulk_update_admin_material_extracted_data(payload.material_ids, command)
    updated = result["updated"]
    skipped = result["skipped"]
    errors = result["errors"]
    missing = result["missing"]
    pre_mutation_docs = result["readback"]

    status = "completed"
    if skipped or errors or missing:
        status = "completed_with_skips"
    evidence = _build_admin_after_action_evidence(
        action="materials.bulk_extracted_data",
        pre_mutation_docs=pre_mutation_docs,
        requested_ids=payload.material_ids,
        missing_ids=missing,
        affected_count=updated,
        skipped_count=skipped,
        status=status,
        filters=parse_json_object({
            "material_ids": [int(material_id) for material_id in payload.material_ids],
            "mode": payload.mode,
            "clears_extracted_data": payload.extracted_data is None,
        }, field="bulk_extracted_data.filters"),
        rollback_hint=(
            "Response-level readback only: no automatic rollback is available for bulk extracted_data writes. "
            "Restore previous extracted_data values from a backup/export or rerun the write with known prior JSON."
        ),
        execution_summary=parse_json_object({
            "updated_count": updated,
            "errors": errors,
            "mode": payload.mode,
            "clears_extracted_data": payload.extracted_data is None,
        }, field="bulk_extracted_data.execution_summary"),
    )
    return success_response(
        {
            "requested": len(payload.material_ids),
            "updated": updated,
            "skipped": skipped,
            "missing": missing,
            "errors": errors,
            **evidence,
        }
    )

@router.post("/materials/delete", response_model=ApiEnvelope[JsonObject])
def delete_materials(payload: DeleteMaterialsRequest):
    """删除文档"""
    if payload.preview:
        readback_materials = document_admin.preview_admin_materials(payload.material_ids)
        return success_response(_build_material_delete_preview(readback_materials, payload.material_ids))

    result = document_admin.delete_admin_materials(payload.material_ids)
    deleted = result["deleted"]
    missing = result["missing"]
    pre_mutation_docs = result["readback"]

    status = "completed"
    if not deleted:
        status = "no_op"
    elif missing:
        status = "completed_with_missing"
    evidence = _build_admin_after_action_evidence(
        action="materials.delete",
        pre_mutation_docs=pre_mutation_docs,
        requested_ids=payload.material_ids,
        missing_ids=missing,
        affected_count=deleted,
        skipped_count=0,
        status=status,
        filters={"material_ids": [int(material_id) for material_id in payload.material_ids]},
        rollback_hint=(
            "Response-level readback only: delete is not automatically reversible. "
            "Restore deleted materials from database backup or source re-ingest using the returned source_refs."
        ),
        execution_summary={"deleted_count": deleted},
    )
    return success_response({"deleted": deleted, "missing": missing, **evidence})


@router.post("/materials/re-extract", response_model=ApiEnvelope[JsonObject])
def re_extract_materials(payload: ReExtractRequest):
    """重新提取文档的结构化数据"""
    command = document_admin.AdminReextractCommand(
        material_ids=payload.material_ids,
        force=payload.force,
        fetch_missing_content=payload.fetch_missing_content,
        batch_size=payload.batch_size,
        limit=payload.limit,
        treat_empty_er_as_missing=payload.treat_empty_er_as_missing,
    )
    if payload.preview:
        return success_response(_build_reextract_preview(document_admin.preview_admin_reextract(command), payload))

    def _run_extraction(
        *,
        title: str | None,
        content: str | None,
        extraction_plan: JsonObject | None = None,
    ) -> object:
        plan: dict[str, object] | None = None
        if extraction_plan is not None:
            plan = {key: value for key, value in extraction_plan.items()}
        return run_frontdoor_extraction(title=title, content=content, extraction_plan=plan)

    result = document_admin.reextract_admin_materials(
        command,
        extraction_runner=_run_extraction,
        fetch_html=fetch_html,
        extract_text_from_html=_extract_text_from_html,
    )
    success_count = result["success"]
    error_count = result["error"]
    skipped_count = result["skipped"]
    missing_ids = result["missing"]
    pre_mutation_docs = result["readback"]
    selected_ids = [material["material_id"] for material in pre_mutation_docs]
    requested_ids = payload.material_ids or selected_ids
    status = "completed"
    if error_count:
        status = "completed_with_errors"
    elif skipped_count or missing_ids:
        status = "completed_with_skips"
    evidence = _build_admin_after_action_evidence(
        action="materials.re_extract",
        pre_mutation_docs=pre_mutation_docs,
        requested_ids=requested_ids,
        missing_ids=missing_ids,
        affected_count=success_count,
        skipped_count=skipped_count,
        status=status,
        filters=parse_json_object({
            "material_ids": payload.material_ids,
            "force": payload.force,
            "fetch_missing_content": payload.fetch_missing_content,
            "limit": payload.limit,
            "treat_empty_er_as_missing": payload.treat_empty_er_as_missing,
        }, field="reextract.filters"),
        rollback_hint=(
            "Response-level readback only: re-extract merges structured fields and is not automatically reversible. "
            "Restore prior extracted_data from backup/export, or rerun extraction with corrected inputs."
        ),
        execution_summary=parse_json_object({
            "success_count": success_count,
            "error_count": error_count,
            "total": result["total"],
            "fetch_missing_content": result["fetch_missing_content"],
            "batch_size": result["batch_size"],
            "treat_empty_er_as_missing": result["treat_empty_er_as_missing"],
        }, field="reextract.execution_summary"),
    )
    return success_response(
        {
            "total": result["total"],
            "success": success_count,
            "error": error_count,
            "skipped": skipped_count,
            "fetch_missing_content": result["fetch_missing_content"],
            "batch_size": result["batch_size"],
            "treat_empty_er_as_missing": result["treat_empty_er_as_missing"],
            **evidence,
        }
    )


@router.post("/materials/topic-extract", response_model=ApiEnvelope[document_admin.AdminTopicExtractResult])
def topic_extract_materials(request: Request, payload: TopicExtractRequest):
    """专题析取（规则筛 + LLM确认），回填 company/product/operation 专题结构化字段。"""
    project_key = _project_key_from_request(request)
    command = document_admin.AdminTopicExtractCommand(
        project_key=project_key,
        topics=payload.topics,
        material_ids=payload.material_ids,
        material_types=payload.material_types,
        force=payload.force,
        fetch_missing_content=payload.fetch_missing_content,
        batch_size=payload.batch_size,
        limit=payload.limit,
        candidate_mode=payload.candidate_mode,
    )
    return success_response(
        document_admin.topic_extract_admin_materials(
            command,
            dictionaries=_get_topic_dictionaries(project_key),
            workflow_runner=run_topic_extraction_workflow,
            fetch_html=fetch_html,
            extract_text_from_html=_extract_text_from_html,
        )
    )


@router.get("/materials/{material_id}", response_model=ApiEnvelope[AdminMaterialSnapshot])
def get_material(material_id: int):
    """获取文档详情"""
    result = document_admin.get_admin_material(material_id)
    if result is None:
        return _error_json(404, ErrorCode.NOT_FOUND, "文档不存在")
    return success_response(result)


@router.post("/materials/{material_id}/extracted-data", response_model=ApiEnvelope[document_admin.AdminExtractedDataResult])
def update_material_extracted_data(material_id: int, payload: UpdateExtractedDataRequest):
    """手动写入/合并文档 extracted_data（在库结构化结果）。"""
    command = document_admin.AdminExtractedDataCommand(
        mode=payload.mode,
        extracted_data=payload.extracted_data,
    )
    try:
        result = document_admin.update_admin_material_extracted_data(material_id, command)
    except document_admin.AdminMaterialNotFoundError:
        return _error_json(404, ErrorCode.NOT_FOUND, "文档不存在")
    except document_admin.AdminMaterialInputError as exc:
        return _error_json(400, ErrorCode.INVALID_INPUT, str(exc))
    return success_response(result)


@router.post("/sources/list", response_model=ApiEnvelope[document_admin.AdminSourcePage])
def list_sources(payload: SourceListRequest):
    """列出数据源"""
    query_spec = document_admin.AdminSourceListQuery(
        page=payload.page,
        page_size=payload.page_size,
        kind=payload.kind,
        enabled=payload.enabled,
        sort_by=_source_sort_field(payload.sort_by),
        sort_order=_sort_order(payload.sort_order),
    )
    return success_response(document_admin.list_admin_sources(query_spec))


@router.post("/social-data/list", response_model=ApiEnvelope[document_admin.AdminSocialDataPage])
def list_social_data(payload: SocialDataListRequest):
    """列出社交平台数据"""
    query_spec = document_admin.AdminSocialDataListQuery(
        page=payload.page,
        page_size=payload.page_size,
        platform=payload.platform,
        search=payload.search,
        sentiment_orientation=_sentiment_orientation(payload.sentiment_orientation),
        sort_by=_material_sort_field(payload.sort_by),
        sort_order=_sort_order(payload.sort_order),
    )
    return success_response(
        document_admin.list_admin_social_data(
            query_spec,
            projector=lambda document: build_social_data_item(document),
        )
    )


@router.get("/export-graph", response_model=ApiEnvelope[document_admin.AdminGraphResult])
def export_graph(material_ids: str = Query(..., description="文档ID列表，逗号分隔")):
    """导出指定文档的内容图谱"""
    try:
        parsed_ids = [int(value.strip()) for value in material_ids.split(",") if value.strip()]
    except ValueError:
        return _error_json(
            400,
            ErrorCode.INVALID_INPUT,
            "material_ids must be a comma-separated list of integers",
            details={"field": "material_ids", "value": material_ids},
        )
    if not parsed_ids:
        return _error_json(400, ErrorCode.INVALID_INPUT, "请提供至少一个文档ID")
    try:
        return success_response(document_admin.export_admin_graph(parsed_ids))
    except document_admin.AdminGraphNotFoundError as exc:
        return _error_json(404, ErrorCode.NOT_FOUND, str(exc))
    except document_admin.AdminGraphInputError as exc:
        return _error_json(400, ErrorCode.INVALID_INPUT, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.error("导出图谱失败: %s", exc, exc_info=True)
        return _error_json(500, ErrorCode.INTERNAL_ERROR, f"导出失败: {exc}")


@router.get("/content-graph", response_model=ApiEnvelope[document_admin.AdminGraphResult])
def get_content_graph(
    request: Request,
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    platform: Optional[str] = Query(None, description="平台名称，如 reddit, twitter"),
    topic: Optional[str] = Query(None, description="主题过滤"),
    limit: int = Query(default=100, ge=1, le=2000, description="限制文档数量"),
):
    """根据条件获取内容图谱数据"""
    project_key = _project_key_from_request(request)
    start, start_error = _parse_iso_date_or_error(start_date, field="start_date")
    if start_error:
        return start_error
    end, end_error = _parse_iso_date_or_error(end_date, field="end_date")
    if end_error:
        return end_error

    try:
        return success_response(
            document_admin.get_admin_content_graph(
                project_key,
                start_date=start,
                end_date=end,
                platform=platform,
                topic=topic,
                limit=limit,
            )
        )
    except document_admin.AdminGraphBuildError as exc:
        logger.error("构建内容图谱失败: %s", exc, exc_info=True)
        return _error_json(
            500,
            ErrorCode.INTERNAL_ERROR,
            str(exc),
            details={"exception_type": exc.source_exception_type},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("获取内容图谱失败: %s", exc, exc_info=True)
        return _empty_graph_response()


@router.get("/market-graph", response_model=ApiEnvelope[document_admin.AdminGraphResult])
def get_market_graph(
    request: Request,
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    state: Optional[str] = Query(None, description="州代码过滤，如 CA"),
    game: Optional[str] = Query(None, description="游戏类型过滤"),
    view: Optional[str] = Query(None, description="视图模式，如 market_deep_entities"),
    topic_scope: Optional[Literal["company", "product", "operation"]] = Query(None, description="专题范围过滤"),
    limit: int = Query(default=100, ge=1, le=2000, description="限制数据数量"),
):
    """根据条件获取市场数据图谱。"""
    project_key = _project_key_from_request(request)
    deep_view = str(view or "").strip().lower() == "market_deep_entities" or bool(topic_scope)
    start, start_error = _parse_iso_date_or_error(start_date, field="start_date")
    if start_error:
        return start_error
    end, end_error = _parse_iso_date_or_error(end_date, field="end_date")
    if end_error:
        return end_error

    try:
        return success_response(
            document_admin.get_admin_market_graph(
                project_key,
                start_date=start,
                end_date=end,
                state=state,
                game=game,
                deep_view=deep_view,
                topic_scope=topic_scope,
                limit=limit,
                market_graph_augmenter=_augment_market_graph_with_topic_structured,
            )
        )
    except document_admin.AdminGraphBuildError as exc:
        logger.error("构建市场图谱失败: %s", exc, exc_info=True)
        return _error_json(
            500,
            ErrorCode.INTERNAL_ERROR,
            str(exc),
            details={"exception_type": exc.source_exception_type},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("获取市场数据图谱失败: %s", exc, exc_info=True)
        return _empty_graph_response()


@router.get("/policy-graph", response_model=ApiEnvelope[document_admin.AdminGraphResult])
def get_policy_graph(
    request: Request,
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    state: Optional[str] = Query(None, description="州代码过滤，如 CA"),
    policy_type: Optional[str] = Query(None, description="政策类型过滤，如 regulation"),
    limit: int = Query(default=100, ge=1, le=2000, description="限制政策数量"),
):
    """根据条件获取政策数据图谱。"""
    project_key = _project_key_from_request(request)
    start, start_error = _parse_iso_date_or_error(start_date, field="start_date")
    if start_error:
        return start_error
    end, end_error = _parse_iso_date_or_error(end_date, field="end_date")
    if end_error:
        return end_error

    try:
        return success_response(
            document_admin.get_admin_policy_graph(
                project_key,
                start_date=start,
                end_date=end,
                state=state,
                policy_type=policy_type,
                limit=limit,
            )
        )
    except document_admin.AdminGraphBuildError as exc:
        logger.error("构建政策图谱失败: %s", exc, exc_info=True)
        return _error_json(
            500,
            ErrorCode.INTERNAL_ERROR,
            str(exc),
            details={"exception_type": exc.source_exception_type},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("获取政策图谱失败: %s", exc, exc_info=True)
        return _empty_graph_response()


@router.get("/search-history", response_model=ApiEnvelope[document_admin.AdminSearchHistoryPage])
def get_search_history(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
):
    """获取搜索历史"""
    project_key = _project_key_from_request(request)
    return success_response(
        document_admin.list_admin_search_history(project_key, page=page, page_size=page_size)
    )
