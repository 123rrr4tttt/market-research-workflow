from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from ..models.base import SessionLocal
from ..models.entities import KeywordHistory, KeywordPrior


def normalize_keyword(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def record_keyword_history(
    *,
    keywords: list[str] | None,
    source: str,
    source_domain: str | None = None,
    status: str | None = None,
    inserted: int = 0,
    inserted_valid: int = 0,
    rejected_count: int = 0,
    filter_decision: str | None = None,
    extra: dict[str, Any] | None = None,
) -> int:
    terms = [normalize_keyword(x) for x in (keywords or []) if normalize_keyword(x)]
    if not terms:
        return 0
    touched = 0
    now = _now_utc()
    with SessionLocal() as session:
        for term in dict.fromkeys(terms):
            row = session.execute(select(KeywordHistory).where(KeywordHistory.keyword == term)).scalar_one_or_none()
            if row is None:
                row = KeywordHistory(
                    keyword=term,
                    normalized_keyword=term,
                    search_count=0,
                    hit_count=0,
                    inserted_count=0,
                    rejected_count=0,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                session.add(row)
            row.search_count = int(row.search_count or 0) + 1
            if int(inserted_valid or 0) > 0:
                row.hit_count = int(row.hit_count or 0) + 1
            row.inserted_count = int(row.inserted_count or 0) + max(0, int(inserted or 0))
            row.rejected_count = int(row.rejected_count or 0) + max(0, int(rejected_count or 0))
            row.last_status = str(status or row.last_status or "").strip() or None
            row.last_source = str(source or row.last_source or "").strip() or None
            row.last_source_domain = str(source_domain or row.last_source_domain or "").strip() or None
            row.last_filter_decision = str(filter_decision or row.last_filter_decision or "").strip() or None
            row.last_seen_at = now
            row.extra = dict(extra or row.extra or {})
            touched += 1
        session.commit()
    return touched


def upsert_keyword_prior(
    *,
    keyword: str,
    prior_score: float = 0.5,
    confidence: float = 0.5,
    source: str = "manual",
    enabled: bool = True,
    tags: list[str] | None = None,
    notes: str | None = None,
    extra: dict[str, Any] | None = None,
) -> KeywordPrior:
    term = normalize_keyword(keyword)
    if not term:
        raise ValueError("keyword is required")
    with SessionLocal() as session:
        row = session.execute(select(KeywordPrior).where(KeywordPrior.keyword == term)).scalar_one_or_none()
        if row is None:
            row = KeywordPrior(keyword=term, normalized_keyword=term)
            session.add(row)
        row.prior_score = Decimal(str(max(0.0, min(1.0, float(prior_score)))))
        row.confidence = Decimal(str(max(0.0, min(1.0, float(confidence)))))
        row.source = str(source or "manual").strip() or "manual"
        row.enabled = bool(enabled)
        row.tags = [str(x).strip() for x in (tags or []) if str(x).strip()] or None
        row.notes = str(notes).strip() if notes else None
        row.extra = dict(extra or {})
        session.commit()
        session.refresh(row)
        return row


def list_keyword_history(*, limit: int = 200, q: str | None = None) -> list[KeywordHistory]:
    with SessionLocal() as session:
        stmt = select(KeywordHistory)
        if q:
            term = f"%{normalize_keyword(q)}%"
            stmt = stmt.where(KeywordHistory.keyword.ilike(term))
        stmt = stmt.order_by(KeywordHistory.last_seen_at.desc()).limit(max(1, min(1000, int(limit))))
        return list(session.execute(stmt).scalars())


def list_keyword_priors(*, limit: int = 200, enabled_only: bool = False) -> list[KeywordPrior]:
    with SessionLocal() as session:
        stmt = select(KeywordPrior)
        if enabled_only:
            stmt = stmt.where(KeywordPrior.enabled.is_(True))
        stmt = stmt.order_by(KeywordPrior.updated_at.desc()).limit(max(1, min(1000, int(limit))))
        return list(session.execute(stmt).scalars())


def list_vectorization_candidates(*, limit: int = 200) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        history_rows = list(
            session.execute(
                select(KeywordHistory).order_by(KeywordHistory.last_seen_at.desc()).limit(max(1, min(2000, int(limit) * 4)))
            ).scalars()
        )
        prior_rows = list(session.execute(select(KeywordPrior).where(KeywordPrior.enabled.is_(True))).scalars())

    prior_map: dict[str, KeywordPrior] = {str(x.keyword): x for x in prior_rows}
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in history_rows:
        key = str(row.keyword or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        prior = prior_map.get(key)
        prior_score = float(prior.prior_score) if prior is not None and prior.prior_score is not None else 0.5
        confidence = float(prior.confidence) if prior is not None and prior.confidence is not None else 0.5
        history_signal = min(1.0, (float(row.search_count or 0) / 20.0))
        score = round(0.6 * prior_score + 0.3 * confidence + 0.1 * history_signal, 4)
        merged.append(
            {
                "keyword": key,
                "prior_score": prior_score,
                "confidence": confidence,
                "history_search_count": int(row.search_count or 0),
                "history_hit_count": int(row.hit_count or 0),
                "history_inserted_count": int(row.inserted_count or 0),
                "history_rejected_count": int(row.rejected_count or 0),
                "vector_priority_score": score,
                "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "source_domain": row.last_source_domain,
                "tags": list(prior.tags or []) if prior is not None else [],
            }
        )

    for row in prior_rows:
        key = str(row.keyword or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        prior_score = float(row.prior_score) if row.prior_score is not None else 0.5
        confidence = float(row.confidence) if row.confidence is not None else 0.5
        score = round(0.7 * prior_score + 0.3 * confidence, 4)
        merged.append(
            {
                "keyword": key,
                "prior_score": prior_score,
                "confidence": confidence,
                "history_search_count": 0,
                "history_hit_count": 0,
                "history_inserted_count": 0,
                "history_rejected_count": 0,
                "vector_priority_score": score,
                "last_seen_at": None,
                "source_domain": None,
                "tags": list(row.tags or []),
            }
        )
    merged.sort(key=lambda x: (x["vector_priority_score"], x["history_search_count"]), reverse=True)
    return merged[: max(1, min(1000, int(limit)))]


def keyword_memory_stats() -> dict[str, int]:
    with SessionLocal() as session:
        history_total = int(session.execute(select(func.count()).select_from(KeywordHistory)).scalar() or 0)
        prior_total = int(session.execute(select(func.count()).select_from(KeywordPrior)).scalar() or 0)
        prior_enabled = int(
            session.execute(select(func.count()).select_from(KeywordPrior).where(KeywordPrior.enabled.is_(True))).scalar() or 0
        )
    return {
        "history_total": history_total,
        "prior_total": prior_total,
        "prior_enabled": prior_enabled,
    }
