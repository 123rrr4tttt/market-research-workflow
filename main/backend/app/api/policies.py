"""政策API接口"""
from __future__ import annotations

from datetime import date, datetime
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, select
from sqlalchemy.exc import DatabaseError, OperationalError

from ..contracts import ApiEnvelope, ErrorCode, fail, ok, ok_page
from ..contracts.schemas.policies import (
    PolicyDetail,
    PoliciesListData,
    PolicyStateDetail,
    PolicyStats,
    PolicySummary,
)
from ..models.base import SessionLocal
from ..models.entities import Document
from ..services.document_views import (
    build_policy_detail,
    build_policy_summary,
    get_policy_data,
    get_policy_key_points,
    get_policy_relations,
)
from ..services.document_queries import (
    policy_effective_date_expr,
    policy_has_data_condition,
    policy_state_condition,
    policy_time_expr,
    policy_type_condition,
    policy_type_order_expr,
)
from ..services.graph.relation_ontology import relation_annotation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/policies", tags=["policies"])

PoliciesListEnvelope = ApiEnvelope[PoliciesListData]
PolicyStatsEnvelope = ApiEnvelope[PolicyStats]
PolicyStateDetailEnvelope = ApiEnvelope[PolicyStateDetail]
PolicyDetailEnvelope = ApiEnvelope[PolicyDetail]


def _json_error(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    payload = fail(code, message)
    payload["detail"] = {"error": payload["error"], "message": payload["error"]["message"]}
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={"X-Error-Code": code.value},
    )


def _extract_policy_data(doc: Document) -> dict[str, Any]:
    """从文档中提取政策数据"""
    return build_policy_summary(doc)


def _extract_policy_detail(doc: Document) -> dict[str, Any]:
    return build_policy_detail(doc)


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date_param(value: Optional[str], *, field: str) -> Optional[date]:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if not _DATE_RE.match(raw):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    return datetime.strptime(raw, "%Y-%m-%d").date()


@router.get("", response_model=PoliciesListEnvelope)
def list_policies(
    state: Optional[str] = Query(None, description="州代码，如 CA"),
    policy_type: Optional[str] = Query(None, description="政策类型"),
    status: Optional[str] = Query(None, description="政策状态"),
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD（兼容参数）"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD（兼容参数）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: str = Query("publish_date", description="排序字段"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="排序方向"),
):
    """返回政策概要列表"""
    try:
        start_raw = start if start is not None else start_date
        end_raw = end if end is not None else end_date
        try:
            start_dt = _parse_date_param(start_raw, field="start")
            end_dt = _parse_date_param(end_raw, field="end")
        except ValueError as exc:
            return _json_error(422, ErrorCode.INVALID_INPUT, str(exc))

        with SessionLocal() as session:
            conditions = [Document.doc_type.in_(["policy", "policy_regulation"]), policy_has_data_condition()]
            policy_time = policy_time_expr()
            policy_effective = policy_effective_date_expr()

            if state:
                conditions.append(policy_state_condition(state))

            if policy_type:
                conditions.append(policy_type_condition(policy_type))

            if status:
                conditions.append(Document.status == status)

            if start_dt:
                conditions.append(policy_time >= start_dt)

            if end_dt:
                conditions.append(policy_time <= end_dt)

            total_query = select(func.count(Document.id)).where(and_(*conditions))
            total = session.execute(total_query).scalar() or 0

            query = select(Document).where(and_(*conditions))
            logger.info("政策列表排序: sort_by=%s, sort_order=%s", sort_by, sort_order)

            if sort_by == "publish_date":
                if sort_order == "desc":
                    query = query.order_by(policy_time.desc().nullslast(), Document.id.desc())
                else:
                    query = query.order_by(policy_time.asc().nullslast(), Document.id.asc())
            elif sort_by == "effective_date":
                if sort_order == "desc":
                    query = query.order_by(
                        policy_effective.desc().nullslast(),
                        policy_time.desc().nullslast(),
                        Document.id.desc(),
                    )
                else:
                    query = query.order_by(
                        policy_effective.asc().nullslast(),
                        policy_time.asc().nullslast(),
                        Document.id.asc(),
                    )
            elif sort_by == "title":
                if sort_order == "desc":
                    query = query.order_by(Document.title.desc().nullslast(), Document.id.desc())
                else:
                    query = query.order_by(Document.title.asc().nullslast(), Document.id.asc())
            elif sort_by == "state":
                if sort_order == "desc":
                    query = query.order_by(Document.state.desc().nullslast(), Document.id.desc())
                else:
                    query = query.order_by(Document.state.asc().nullslast(), Document.id.asc())
            elif sort_by == "policy_type":
                if sort_order == "desc":
                    query = query.order_by(
                        policy_type_order_expr().desc().nullslast(),
                        Document.id.desc(),
                    )
                else:
                    query = query.order_by(
                        policy_type_order_expr().asc().nullslast(),
                        Document.id.asc(),
                    )
            elif sort_by == "status":
                if sort_order == "desc":
                    query = query.order_by(Document.status.desc().nullslast(), Document.id.desc())
                else:
                    query = query.order_by(Document.status.asc().nullslast(), Document.id.asc())
            else:
                query = query.order_by(Document.created_at.desc(), Document.id.desc())

            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            documents = session.execute(query).scalars().all()
            items = [_extract_policy_data(doc) for doc in documents]
            total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

            return ok_page(
                {"items": items},
                page=page,
                page_size=page_size,
                total=int(total),
                total_pages=total_pages,
            )
    except (OperationalError, DatabaseError):
        logger.exception("数据库连接失败")
        return _json_error(503, ErrorCode.UPSTREAM_ERROR, "数据库服务不可用，请检查数据库服务是否已启动。")
    except Exception as exc:  # noqa: BLE001
        logger.exception("获取政策列表失败")
        return _json_error(500, ErrorCode.INTERNAL_ERROR, f"获取政策列表失败: {exc}")


@router.get("/stats", response_model=PolicyStatsEnvelope)
def get_policy_stats(
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD（兼容参数）"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD（兼容参数）"),
):
    """获取政策统计数据"""
    try:
        start_raw = start if start is not None else start_date
        end_raw = end if end is not None else end_date
        try:
            start_dt = _parse_date_param(start_raw, field="start")
            end_dt = _parse_date_param(end_raw, field="end")
        except ValueError as exc:
            return _json_error(422, ErrorCode.INVALID_INPUT, str(exc))

        with SessionLocal() as session:
            conditions = [Document.doc_type.in_(["policy", "policy_regulation"]), policy_has_data_condition()]
            policy_time = policy_time_expr()

            if start_dt:
                conditions.append(policy_time >= start_dt)

            if end_dt:
                conditions.append(policy_time <= end_dt)

            docs_query = select(Document).where(and_(*conditions))
            docs = session.execute(docs_query).scalars().all()

            state_counts: dict[str, int] = {}
            for doc in docs:
                state_value = doc.state
                if not state_value:
                    state_value = get_policy_data(doc).get("state")
                if state_value:
                    key = state_value.upper()
                    state_counts[key] = state_counts.get(key, 0) + 1
            state_distribution = [{"state": k, "count": v} for k, v in state_counts.items()]

            type_counts: dict[str, int] = {}
            for doc in docs:
                policy_type = get_policy_data(doc).get("policy_type") or "unknown"
                type_counts[policy_type] = type_counts.get(policy_type, 0) + 1
            type_distribution = [{"policy_type": k, "count": v} for k, v in type_counts.items()]

            status_query = (
                select(Document.status, func.count(Document.id).label("count"))
                .where(and_(*conditions))
                .group_by(Document.status)
            )
            status_dist = session.execute(status_query).all()
            status_distribution = [{"status": row.status or "unknown", "count": row.count} for row in status_dist]

            trend_query = (
                select(func.date_trunc("month", policy_time).label("month"), func.count(Document.id).label("count"))
                .where(and_(*conditions))
                .group_by("month")
                .order_by("month")
            )
            trend_data = session.execute(trend_query).all()
            trend_series = [
                {"date": row.month.date().isoformat() if row.month else None, "count": row.count}
                for row in trend_data
            ]

            total_query = select(func.count(Document.id)).where(and_(*conditions))
            total = session.execute(total_query).scalar() or 0

            active_query = select(func.count(Document.id)).where(and_(*conditions, Document.status == "active"))
            active_count = session.execute(active_query).scalar() or 0
            states_count = len([s for s in state_distribution if s["state"]])

            return ok(
                {
                    "total": int(total),
                    "active_count": int(active_count),
                    "states_count": int(states_count),
                    "state_distribution": state_distribution,
                    "type_distribution": type_distribution,
                    "status_distribution": status_distribution,
                    "trend_series": trend_series,
                }
            )
    except (OperationalError, DatabaseError):
        logger.exception("数据库连接失败")
        return _json_error(503, ErrorCode.UPSTREAM_ERROR, "数据库服务不可用，请检查数据库服务是否已启动。")
    except Exception as exc:  # noqa: BLE001
        logger.exception("获取政策统计失败")
        return _json_error(500, ErrorCode.INTERNAL_ERROR, f"获取政策统计失败: {exc}")


@router.get("/state/{state}", response_model=PolicyStateDetailEnvelope)
def get_state_policies(
    state: str = Path(..., description="州代码，如 CA"),
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD（兼容参数）"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD（兼容参数）"),
):
    """获取指定州的政策详情和统计"""
    try:
        start_raw = start if start is not None else start_date
        end_raw = end if end is not None else end_date
        try:
            start_dt = _parse_date_param(start_raw, field="start")
            end_dt = _parse_date_param(end_raw, field="end")
        except ValueError as exc:
            return _json_error(422, ErrorCode.INVALID_INPUT, str(exc))

        with SessionLocal() as session:
            conditions = [
                Document.doc_type.in_(["policy", "policy_regulation"]),
                policy_state_condition(state),
            ]
            policy_time = policy_time_expr()

            if start_dt:
                conditions.append(policy_time >= start_dt)

            if end_dt:
                conditions.append(policy_time <= end_dt)

            query = select(Document).where(and_(*conditions)).order_by(policy_time.desc().nullslast(), Document.id.desc())
            documents = session.execute(query).scalars().all()
            policies = [_extract_policy_data(doc) for doc in documents]

            total = len(policies)
            active_count = sum(1 for p in policies if p.get("status") == "active")

            type_counts: dict[str, int] = {}
            for policy in policies:
                policy_type = policy.get("policy_type") or "unknown"
                type_counts[policy_type] = type_counts.get(policy_type, 0) + 1
            most_common_type = max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else None

            entity_counts: dict[str, int] = {}
            relation_counts: dict[str, int] = {}
            relation_class_counts: dict[str, int] = {}
            all_key_points: list[str] = []
            for doc in documents:
                all_key_points.extend(get_policy_key_points(doc))

                for entity in build_policy_detail(doc)["entities"]:
                    entity_type = entity.get("type", "unknown")
                    entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
                for relation in get_policy_relations(doc):
                    ann = relation_annotation(relation.get("predicate", "unknown"))
                    predicate = ann["predicate_norm"]
                    relation_counts[predicate] = relation_counts.get(predicate, 0) + 1
                    relation_class = ann["relation_class"]
                    relation_class_counts[relation_class] = relation_class_counts.get(relation_class, 0) + 1

            return ok(
                {
                    "state": state.upper(),
                    "policies": policies,
                    "statistics": {
                        "total": total,
                        "active_count": active_count,
                        "most_common_type": most_common_type,
                        "type_distribution": [{"type": k, "count": v} for k, v in type_counts.items()],
                        "entity_distribution": [{"type": k, "count": v} for k, v in entity_counts.items()],
                        "relation_distribution": [
                            {"predicate": k, "count": v} for k, v in relation_counts.items()
                        ],
                        "relation_class_distribution": [
                            {"relation_class": k, "count": v} for k, v in relation_class_counts.items()
                        ],
                        "key_points_count": len(all_key_points),
                    },
                }
            )
    except (OperationalError, DatabaseError):
        logger.exception("数据库连接失败")
        return _json_error(503, ErrorCode.UPSTREAM_ERROR, "数据库服务不可用，请检查数据库服务是否已启动。")
    except Exception as exc:  # noqa: BLE001
        logger.exception("获取州政策详情失败")
        return _json_error(500, ErrorCode.INTERNAL_ERROR, f"获取州政策详情失败: {exc}")


@router.get("/{policy_id}", response_model=PolicyDetailEnvelope)
def get_policy_detail(policy_id: int = Path(..., description="政策ID")):
    """获取政策详情"""
    try:
        with SessionLocal() as session:
            doc = session.execute(
                select(Document).where(
                    Document.id == policy_id,
                    Document.doc_type.in_(["policy", "policy_regulation"]),
                )
            ).scalar_one_or_none()
            if not doc:
                return _json_error(404, ErrorCode.NOT_FOUND, "政策不存在")

            return ok(_extract_policy_detail(doc))
    except HTTPException:
        raise
    except (OperationalError, DatabaseError):
        logger.exception("数据库连接失败")
        return _json_error(503, ErrorCode.UPSTREAM_ERROR, "数据库服务不可用，请检查数据库服务是否已启动。")
    except Exception as exc:  # noqa: BLE001
        logger.exception("获取政策详情失败")
        return _json_error(500, ErrorCode.INTERNAL_ERROR, f"获取政策详情失败: {exc}")
