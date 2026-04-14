from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..contracts import success_response
from ..services.keyword_memory import (
    keyword_memory_stats,
    list_keyword_history,
    list_keyword_priors,
    list_vectorization_candidates,
    upsert_keyword_prior,
)

router = APIRouter(prefix="/keywords", tags=["keywords"])


class KeywordPriorUpsertPayload(BaseModel):
    keyword: str = Field(..., min_length=1)
    prior_score: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = Field(default="manual")
    enabled: bool = Field(default=True)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None)
    extra: dict[str, Any] | None = Field(default=None)


@router.get("/stats")
def get_keyword_memory_stats():
    return success_response(keyword_memory_stats())


@router.get("/history")
def get_keyword_history(
    limit: int = Query(default=200, ge=1, le=1000),
    q: str | None = Query(default=None),
):
    rows = list_keyword_history(limit=limit, q=q)
    out = [
        {
            "id": int(r.id),
            "keyword": r.keyword,
            "normalized_keyword": r.normalized_keyword,
            "search_count": int(r.search_count or 0),
            "hit_count": int(r.hit_count or 0),
            "inserted_count": int(r.inserted_count or 0),
            "rejected_count": int(r.rejected_count or 0),
            "last_status": r.last_status,
            "last_source": r.last_source,
            "last_source_domain": r.last_source_domain,
            "last_filter_decision": r.last_filter_decision,
            "first_seen_at": r.first_seen_at.isoformat() if r.first_seen_at else None,
            "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
            "extra": r.extra or {},
        }
        for r in rows
    ]
    return success_response({"items": out, "total": len(out)})


@router.get("/priors")
def get_keyword_priors(
    limit: int = Query(default=200, ge=1, le=1000),
    enabled_only: bool = Query(default=False),
):
    rows = list_keyword_priors(limit=limit, enabled_only=enabled_only)
    out = [
        {
            "id": int(r.id),
            "keyword": r.keyword,
            "normalized_keyword": r.normalized_keyword,
            "prior_score": float(r.prior_score or 0),
            "confidence": float(r.confidence or 0),
            "source": r.source,
            "enabled": bool(r.enabled),
            "tags": list(r.tags or []),
            "notes": r.notes,
            "extra": r.extra or {},
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]
    return success_response({"items": out, "total": len(out)})


@router.post("/priors/upsert")
def post_keyword_prior_upsert(payload: KeywordPriorUpsertPayload):
    row = upsert_keyword_prior(
        keyword=payload.keyword,
        prior_score=payload.prior_score,
        confidence=payload.confidence,
        source=payload.source,
        enabled=payload.enabled,
        tags=payload.tags,
        notes=payload.notes,
        extra=payload.extra,
    )
    return success_response(
        {
            "id": int(row.id),
            "keyword": row.keyword,
            "prior_score": float(row.prior_score or 0),
            "confidence": float(row.confidence or 0),
            "source": row.source,
            "enabled": bool(row.enabled),
            "tags": list(row.tags or []),
            "notes": row.notes,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    )


@router.get("/vectorization/candidates")
def get_vectorization_candidates(limit: int = Query(default=200, ge=1, le=1000)):
    return success_response({"items": list_vectorization_candidates(limit=limit), "total": limit})
