"""政策API接口"""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy import and_, cast, func, or_, select, String
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/policies", tags=["policies"])

PoliciesListEnvelope = ApiEnvelope[PoliciesListData]
PolicyStatsEnvelope = ApiEnvelope[PolicyStats]
PolicyStateDetailEnvelope = ApiEnvelope[PolicyStateDetail]
PolicyDetailEnvelope = ApiEnvelope[PolicyDetail]


def _json_error(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=fail(code, message))


def _extract_policy_data(doc: Document) -> dict[str, Any]:
    """从文档中提取政策数据"""
    extracted = doc.extracted_data or {}
    policy_data = extracted.get("policy", {})

    return {
        "id": doc.id,
        "title": doc.title,
        "state": doc.state or policy_data.get("state"),
        "status": doc.status,
        "publish_date": doc.publish_date.isoformat() if doc.publish_date else None,
        "effective_date": policy_data.get("effective_date"),
        "policy_type": policy_data.get("policy_type"),
        "key_points": policy_data.get("key_points", []),
        "summary": doc.summary,
        "uri": doc.uri,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


def _extract_policy_detail(doc: Document) -> dict[str, Any]:
    extracted = doc.extracted_data or {}
    policy_data = extracted.get("policy", {})
    entities_relations = extracted.get("entities_relations", {})
    return {
        **_extract_policy_data(doc),
        "content": doc.content,
        "source_id": doc.source_id,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "entities": entities_relations.get("entities", []),
        "relations": entities_relations.get("relations", []),
    }


@router.get("", response_model=PoliciesListEnvelope)
def list_policies(
    state: Optional[str] = Query(None, description="州代码，如 CA"),
    policy_type: Optional[str] = Query(None, description="政策类型"),
    status: Optional[str] = Query(None, description="政策状态"),
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: str = Query("publish_date", description="排序字段"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="排序方向"),
):
    """返回政策概要列表"""
    try:
        with SessionLocal() as session:
            conditions = [Document.doc_type.in_(["policy", "policy_regulation"])]

            if state:
                conditions.append(
                    or_(
                        Document.state == state.upper(),
                        cast(Document.extracted_data["policy"]["state"], String) == state.upper(),
                    )
                )

            if policy_type:
                conditions.append(cast(Document.extracted_data["policy"]["policy_type"], String) == policy_type)

            if status:
                conditions.append(Document.status == status)

            if start:
                try:
                    start_date = datetime.fromisoformat(start).date()
                    conditions.append(
                        or_(
                            Document.publish_date >= start_date,
                            cast(Document.extracted_data["policy"]["effective_date"], String) >= start,
                        )
                    )
                except Exception:
                    pass

            if end:
                try:
                    end_date = datetime.fromisoformat(end).date()
                    conditions.append(
                        or_(
                            Document.publish_date <= end_date,
                            cast(Document.extracted_data["policy"]["effective_date"], String) <= end,
                        )
                    )
                except Exception:
                    pass

            total_query = select(func.count(Document.id)).where(and_(*conditions))
            total = session.execute(total_query).scalar() or 0

            query = select(Document).where(and_(*conditions))
            logger.info("政策列表排序: sort_by=%s, sort_order=%s", sort_by, sort_order)

            if sort_by == "publish_date":
                if sort_order == "desc":
                    query = query.order_by(Document.publish_date.desc().nullslast(), Document.id.desc())
                else:
                    query = query.order_by(Document.publish_date.asc().nullslast(), Document.id.asc())
            elif sort_by == "effective_date":
                if sort_order == "desc":
                    query = query.order_by(
                        Document.publish_date.desc().nullslast(),
                        cast(Document.extracted_data["policy"]["effective_date"], String).desc().nullslast(),
                        Document.id.desc(),
                    )
                else:
                    query = query.order_by(
                        Document.publish_date.asc().nullslast(),
                        cast(Document.extracted_data["policy"]["effective_date"], String).asc().nullslast(),
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
                        cast(Document.extracted_data["policy"]["policy_type"], String).desc().nullslast(),
                        Document.id.desc(),
                    )
                else:
                    query = query.order_by(
                        cast(Document.extracted_data["policy"]["policy_type"], String).asc().nullslast(),
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
):
    """获取政策统计数据"""
    try:
        with SessionLocal() as session:
            conditions = [Document.doc_type.in_(["policy", "policy_regulation"])]

            if start:
                try:
                    start_date = datetime.fromisoformat(start).date()
                    conditions.append(
                        or_(
                            Document.publish_date >= start_date,
                            cast(Document.extracted_data["policy"]["effective_date"], String) >= start,
                        )
                    )
                except Exception:
                    pass

            if end:
                try:
                    end_date = datetime.fromisoformat(end).date()
                    conditions.append(
                        or_(
                            Document.publish_date <= end_date,
                            cast(Document.extracted_data["policy"]["effective_date"], String) <= end,
                        )
                    )
                except Exception:
                    pass

            docs_query = select(Document).where(and_(*conditions))
            docs = session.execute(docs_query).scalars().all()

            state_counts: dict[str, int] = {}
            for doc in docs:
                state_value = doc.state
                if not state_value:
                    extracted = doc.extracted_data or {}
                    state_value = extracted.get("policy", {}).get("state")
                if state_value:
                    key = state_value.upper()
                    state_counts[key] = state_counts.get(key, 0) + 1
            state_distribution = [{"state": k, "count": v} for k, v in state_counts.items()]

            type_counts: dict[str, int] = {}
            for doc in docs:
                extracted = doc.extracted_data or {}
                policy_type = extracted.get("policy", {}).get("policy_type") or "unknown"
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
                select(func.date_trunc("month", Document.publish_date).label("month"), func.count(Document.id).label("count"))
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
):
    """获取指定州的政策详情和统计"""
    try:
        with SessionLocal() as session:
            conditions = [
                Document.doc_type.in_(["policy", "policy_regulation"]),
                or_(
                    Document.state == state.upper(),
                    cast(Document.extracted_data["policy"]["state"], String) == state.upper(),
                ),
            ]

            if start:
                try:
                    start_date = datetime.fromisoformat(start).date()
                    conditions.append(
                        or_(
                            Document.publish_date >= start_date,
                            cast(Document.extracted_data["policy"]["effective_date"], String) >= start,
                        )
                    )
                except Exception:
                    pass

            if end:
                try:
                    end_date = datetime.fromisoformat(end).date()
                    conditions.append(
                        or_(
                            Document.publish_date <= end_date,
                            cast(Document.extracted_data["policy"]["effective_date"], String) <= end,
                        )
                    )
                except Exception:
                    pass

            query = select(Document).where(and_(*conditions)).order_by(Document.publish_date.desc().nullslast())
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
            all_key_points: list[str] = []
            for doc in documents:
                extracted = doc.extracted_data or {}
                policy_data = extracted.get("policy", {})
                all_key_points.extend(policy_data.get("key_points", []))

                entities_relations = extracted.get("entities_relations", {})
                for entity in entities_relations.get("entities", []):
                    entity_type = entity.get("type", "unknown")
                    entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
                for relation in entities_relations.get("relations", []):
                    predicate = relation.get("predicate", "unknown")
                    relation_counts[predicate] = relation_counts.get(predicate, 0) + 1

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
