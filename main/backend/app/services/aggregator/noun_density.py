from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.entities import Document

NOUN_DENSITY_VERSION = "nd_v1"

_BUCKET_TO_DELTA: dict[str, timedelta] = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
}


@dataclass
class _DocProjection:
    id: int
    source_domain: str
    source_time: datetime | None
    effective_time: datetime | None
    created_at: datetime | None
    text_hash: str | None
    uri: str | None
    doc_type: str | None
    title: str | None
    extracted_data: dict[str, Any] | None


def _normalize_source_domain(value: str | None) -> str:
    out = str(value or "").strip().lower()
    return out or "unknown"


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid datetime: {value}") from exc
    return _as_utc(dt)


def _bucket_start(dt: datetime, bucket: str) -> datetime:
    dtu = _as_utc(dt) or dt
    if bucket == "day":
        return dtu.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "week":
        day_start = dtu.replace(hour=0, minute=0, second=0, microsecond=0)
        return day_start - timedelta(days=day_start.weekday())
    if bucket == "month":
        return dtu.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"unsupported bucket: {bucket}")


def _resolve_window(
    *,
    time_window: str | None,
    start_time: str | None,
    end_time: str | None,
    now: datetime | None = None,
) -> tuple[datetime, datetime, str]:
    now_utc = _as_utc(now) or datetime.now(timezone.utc)
    start_dt = _parse_dt(start_time)
    end_dt = _parse_dt(end_time)

    if start_dt and end_dt:
        if start_dt >= end_dt:
            raise ValueError("start_time must be earlier than end_time")
        return start_dt, end_dt, "custom"

    tw = str(time_window or "30d").strip().lower()
    preset_days = {
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "180d": 180,
    }
    if tw not in preset_days:
        raise ValueError("unsupported time_window, use one of 7d/30d/90d/180d or start_time+end_time")

    end = now_utc
    start = end - timedelta(days=preset_days[tw])
    return start, end, tw


def _effective_dt(doc: _DocProjection) -> datetime | None:
    return _as_utc(doc.effective_time) or _as_utc(doc.source_time) or _as_utc(doc.created_at)


def extract_noun_groups(doc: _DocProjection) -> list[str]:
    extracted = doc.extracted_data if isinstance(doc.extracted_data, dict) else {}
    groups: list[str] = []

    group_ids = extracted.get("noun_vector_group_ids")
    if isinstance(group_ids, list):
        for g in group_ids:
            token = str(g or "").strip().lower()
            if token:
                groups.append(token)

    if not groups:
        fallback_fields = {
            "company_structured": "company",
            "product_structured": "product",
            "operation_structured": "operation",
        }
        for field, label in fallback_fields.items():
            payload = extracted.get(field)
            if not isinstance(payload, dict):
                continue
            has_signal = bool(
                payload.get("entities")
                or payload.get("relations")
                or payload.get("facts")
                or payload.get("topics")
            )
            if has_signal:
                groups.append(label)

    # Keep insertion order while deduping.
    seen: set[str] = set()
    out: list[str] = []
    for g in groups:
        if g in seen:
            continue
        seen.add(g)
        out.append(g)
    return out


def _query_docs(session: Session, source_domains: Iterable[str] | None) -> list[_DocProjection]:
    stmt = select(Document)
    normalized = {_normalize_source_domain(x) for x in (source_domains or []) if str(x or "").strip()}
    if normalized:
        stmt = stmt.where(Document.source_domain.in_(sorted(normalized)))

    rows = session.execute(stmt).scalars().all()
    out: list[_DocProjection] = []
    for row in rows:
        out.append(
            _DocProjection(
                id=int(row.id),
                source_domain=_normalize_source_domain(row.source_domain),
                source_time=row.source_time,
                effective_time=row.effective_time,
                created_at=row.created_at,
                text_hash=row.text_hash,
                uri=row.uri,
                doc_type=row.doc_type,
                title=row.title,
                extracted_data=row.extracted_data if isinstance(row.extracted_data, dict) else {},
            )
        )
    return out


def build_source_time_window_stats(
    session: Session,
    *,
    time_window: str | None,
    start_time: str | None,
    end_time: str | None,
    bucket: Literal["day", "week", "month"],
    source_domains: list[str] | None = None,
) -> dict[str, Any]:
    start_dt, end_dt, resolved_window = _resolve_window(
        time_window=time_window,
        start_time=start_time,
        end_time=end_time,
    )
    if bucket not in _BUCKET_TO_DELTA:
        raise ValueError("bucket must be one of day/week/month")

    acc: dict[tuple[str, datetime], dict[str, Any]] = {}
    for doc in _query_docs(session, source_domains):
        eff = _effective_dt(doc)
        if eff is None or eff < start_dt or eff >= end_dt:
            continue
        bucket_time = _bucket_start(eff, bucket)
        key = (doc.source_domain, bucket_time)
        bucket_acc = acc.setdefault(
            key,
            {
                "source_domain": doc.source_domain,
                "bucket_time": bucket_time.isoformat(),
                "total_docs": 0,
                "with_source_time_docs": 0,
                "fallback_ingested_docs": 0,
            },
        )
        bucket_acc["total_docs"] += 1
        if doc.source_time is not None:
            bucket_acc["with_source_time_docs"] += 1
        if doc.source_time is None and doc.effective_time is not None:
            bucket_acc["fallback_ingested_docs"] += 1

    rows: list[dict[str, Any]] = []
    for row in sorted(acc.values(), key=lambda x: (x["source_domain"], x["bucket_time"])):
        total = int(row["total_docs"] or 0)
        with_source = int(row["with_source_time_docs"] or 0)
        row["source_time_coverage"] = round(with_source / total, 6) if total else 0.0
        rows.append(row)

    return {
        "version": NOUN_DENSITY_VERSION,
        "time_window": resolved_window,
        "bucket": bucket,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "items": rows,
    }


def build_source_noun_density(
    session: Session,
    *,
    time_window: str | None,
    start_time: str | None,
    end_time: str | None,
    bucket: Literal["day", "week", "month"],
    source_domains: list[str] | None = None,
    noun_group_ids: list[str] | None = None,
    normalize: bool = True,
) -> dict[str, Any]:
    start_dt, end_dt, resolved_window = _resolve_window(
        time_window=time_window,
        start_time=start_time,
        end_time=end_time,
    )
    if bucket not in _BUCKET_TO_DELTA:
        raise ValueError("bucket must be one of day/week/month")

    noun_filter = {str(x or "").strip().lower() for x in (noun_group_ids or []) if str(x or "").strip()}
    window_days = max(1, int(_BUCKET_TO_DELTA[bucket].days))

    acc: dict[tuple[str, str, datetime], dict[str, Any]] = {}
    for doc in _query_docs(session, source_domains):
        eff = _effective_dt(doc)
        if eff is None or eff < start_dt or eff >= end_dt:
            continue

        groups = extract_noun_groups(doc)
        if noun_filter:
            groups = [g for g in groups if g in noun_filter]
        if not groups:
            continue

        dedupe_key = doc.text_hash or doc.uri or str(doc.id)
        bucket_time = _bucket_start(eff, bucket)
        for group in groups:
            key = (doc.source_domain, group, bucket_time)
            bucket_acc = acc.setdefault(
                key,
                {
                    "source_domain": doc.source_domain,
                    "noun_group_id": group,
                    "bucket_time": bucket_time.isoformat(),
                    "effective_new_docs": 0,
                    "_unique": set(),
                },
            )
            bucket_acc["effective_new_docs"] += 1
            bucket_acc["_unique"].add(dedupe_key)

    rows: list[dict[str, Any]] = []
    density_by_group: dict[tuple[str, str], list[float]] = defaultdict(list)

    for row in sorted(acc.values(), key=lambda x: (x["source_domain"], x["noun_group_id"], x["bucket_time"])):
        docs = int(row["effective_new_docs"])
        unique_count = len(row["_unique"])
        density = docs / float(window_days)
        dup_ratio = 1.0 - (float(unique_count) / float(docs)) if docs > 0 else 0.0
        row["density"] = round(density, 6)
        row["dup_ratio"] = round(max(0.0, min(1.0, dup_ratio)), 6)
        density_by_group[(row["source_domain"], row["noun_group_id"])].append(density)
        rows.append(row)

    baselines: dict[tuple[str, str], float] = {}
    for key, values in density_by_group.items():
        baselines[key] = (sum(values) / len(values)) if values else 1.0

    for row in rows:
        key = (row["source_domain"], row["noun_group_id"])
        baseline = baselines.get(key) or 1.0
        norm_density = (row["density"] / baseline) if baseline > 0 else row["density"]
        row["norm_density"] = round(norm_density if normalize else row["density"], 6)
        row["baseline_density"] = round(baseline, 6)
        row["collection_priority_score"] = round((row["norm_density"] * 0.8) + (row["dup_ratio"] * 0.2), 6)

    grouped_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_rows[(row["source_domain"], row["noun_group_id"])].append(row)

    for group_rows in grouped_rows.values():
        group_rows.sort(key=lambda x: (x["collection_priority_score"], x["bucket_time"]))
        for idx, row in enumerate(group_rows, start=1):
            row["recommended_window_rank"] = idx
            row.pop("_unique", None)

    return {
        "version": NOUN_DENSITY_VERSION,
        "time_window": resolved_window,
        "bucket": bucket,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "items": rows,
    }


def build_collection_window_priority(
    session: Session,
    *,
    source_domains: list[str] | None,
    noun_group_ids: list[str] | None,
    candidate_windows: list[str] | None,
    prefer_low_density: bool,
    exclude_high_dup: bool,
) -> dict[str, Any]:
    windows = [str(x or "").strip().lower() for x in (candidate_windows or ["7d", "30d", "90d"]) if str(x or "").strip()]
    if not windows:
        raise ValueError("candidate_windows cannot be empty")

    rows: list[dict[str, Any]] = []
    for window in windows:
        result = build_source_noun_density(
            session,
            time_window=window,
            start_time=None,
            end_time=None,
            bucket="day",
            source_domains=source_domains,
            noun_group_ids=noun_group_ids,
            normalize=True,
        )
        by_combo: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"density": 0.0, "norm": 0.0, "dup": 0.0, "n": 0.0})
        for item in result.get("items", []):
            key = (str(item.get("source_domain") or "unknown"), str(item.get("noun_group_id") or ""))
            if not key[1]:
                continue
            by_combo[key]["density"] += float(item.get("density") or 0.0)
            by_combo[key]["norm"] += float(item.get("norm_density") or 0.0)
            by_combo[key]["dup"] += float(item.get("dup_ratio") or 0.0)
            by_combo[key]["n"] += 1.0

        for (domain, noun_group), agg in by_combo.items():
            n = max(1.0, agg["n"])
            density = agg["density"] / n
            norm_density = agg["norm"] / n
            dup_ratio = agg["dup"] / n
            score = norm_density if prefer_low_density else -norm_density
            if exclude_high_dup:
                score += dup_ratio * 0.25
            rows.append(
                {
                    "source_domain": domain,
                    "noun_group_id": noun_group,
                    "window": window,
                    "density": round(density, 6),
                    "norm_density": round(norm_density, 6),
                    "dup_ratio": round(dup_ratio, 6),
                    "collection_priority_score": round(score, 6),
                }
            )

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["source_domain"], row["noun_group_id"])].append(row)

    out: list[dict[str, Any]] = []
    for rows_group in grouped.values():
        rows_group.sort(key=lambda x: (x["collection_priority_score"], x["window"]))
        for idx, row in enumerate(rows_group, start=1):
            row["rank"] = idx
            out.append(row)

    out.sort(key=lambda x: (x["source_domain"], x["noun_group_id"], x["rank"]))
    return {
        "version": NOUN_DENSITY_VERSION,
        "prefer_low_density": bool(prefer_low_density),
        "exclude_high_dup": bool(exclude_high_dup),
        "items": out,
    }


def build_drilldown_documents(
    session: Session,
    *,
    source_domain: str | None,
    noun_group_id: str | None,
    time_window: str | None,
    start_time: str | None,
    end_time: str | None,
    bucket: Literal["day", "week", "month"],
    bucket_time: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    if page < 1 or page_size < 1:
        raise ValueError("page and page_size must be positive")

    if bucket not in _BUCKET_TO_DELTA:
        raise ValueError("bucket must be one of day/week/month")

    source_domains = [source_domain] if source_domain else None
    docs = _query_docs(session, source_domains)

    if bucket_time:
        pivot = _parse_dt(bucket_time)
        if pivot is None:
            raise ValueError("bucket_time is invalid")
        start_dt = _bucket_start(pivot, bucket)
        end_dt = start_dt + _BUCKET_TO_DELTA[bucket]
        resolved_window = "bucket"
    else:
        start_dt, end_dt, resolved_window = _resolve_window(
            time_window=time_window,
            start_time=start_time,
            end_time=end_time,
        )

    noun_filter = str(noun_group_id or "").strip().lower()

    filtered: list[_DocProjection] = []
    for doc in docs:
        eff = _effective_dt(doc)
        if eff is None or eff < start_dt or eff >= end_dt:
            continue
        if noun_filter:
            groups = extract_noun_groups(doc)
            if noun_filter not in groups:
                continue
        filtered.append(doc)

    total = len(filtered)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    sliced = filtered[start_idx:end_idx]

    items = [
        {
            "id": d.id,
            "title": d.title,
            "doc_type": d.doc_type,
            "source_domain": d.source_domain,
            "source_time": d.source_time.isoformat() if d.source_time else None,
            "effective_time": d.effective_time.isoformat() if d.effective_time else None,
            "uri": d.uri,
            "noun_groups": extract_noun_groups(d),
        }
        for d in sliced
    ]

    return {
        "version": NOUN_DENSITY_VERSION,
        "time_window": resolved_window,
        "bucket": bucket,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "source_domain": _normalize_source_domain(source_domain) if source_domain else None,
        "noun_group_id": noun_filter or None,
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
