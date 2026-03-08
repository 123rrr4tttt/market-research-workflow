from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Date, String, case, cast, func, select

from ...models.base import SessionLocal
from ...models.entities import Document

_EPSILON = 1e-9


def _policy_effective_date_expr():
    effective_raw = cast(Document.extracted_data["policy"]["effective_date"], String)
    effective_text = func.replace(effective_raw, '"', "")
    return case(
        (effective_text.op("~")(r"^\d{4}-\d{2}-\d{2}"), cast(func.substr(effective_text, 1, 10), Date)),
        else_=None,
    )


def _effective_date_expr():
    return func.coalesce(_policy_effective_date_expr(), Document.publish_date, func.date(Document.created_at))


def _normalize_json_text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1].strip()
    return s or None


def _prompt_group_of(doc: Document) -> str:
    extracted = doc.extracted_data or {}
    return (
        _normalize_json_text(extracted.get("prompt_group_id"))
        or _normalize_json_text(extracted.get("topic_cluster"))
        or _normalize_json_text(extracted.get("topic"))
        or _normalize_json_text((extracted.get("policy") or {}).get("policy_type"))
        or "unknown"
    )


def _source_domain_of(doc: Document) -> str:
    extracted = doc.extracted_data or {}
    source_domain = _normalize_json_text(extracted.get("source_domain"))
    if source_domain:
        return source_domain.lower()
    uri = str(doc.uri or "").strip()
    if not uri:
        return "unknown"
    host = urlparse(uri).netloc.strip().lower()
    return host or "unknown"


def _bucket_of(day: date, bucket: str) -> date:
    if bucket == "day":
        return day
    if bucket == "week":
        return day - timedelta(days=day.weekday())
    if bucket == "month":
        return date(day.year, day.month, 1)
    raise ValueError("bucket must be one of: day, week, month")


def _window_days(start: date, end: date) -> int:
    return max(1, (end - start).days + 1)


def query_prompt_time_density(
    *,
    start: date,
    end: date,
    bucket: str = "day",
    source_domains: list[str] | None = None,
    prompt_group_ids: list[str] | None = None,
    normalize: bool = True,
) -> list[dict[str, Any]]:
    if start > end:
        raise ValueError("start must be <= end")
    if bucket not in {"day", "week", "month"}:
        raise ValueError("bucket must be one of: day, week, month")

    normalized_domains = {x.strip().lower() for x in (source_domains or []) if str(x).strip()}
    normalized_groups = {x.strip() for x in (prompt_group_ids or []) if str(x).strip()}
    policy_time = _effective_date_expr()

    with SessionLocal() as session:
        docs = session.execute(
            select(Document).where(
                Document.doc_type.in_(["policy", "policy_regulation", "news", "social"]),
                policy_time >= start,
                policy_time <= end,
            )
        ).scalars().all()

        # Baseline window defaults to 90d ending at current query end.
        baseline_start = end - timedelta(days=89)
        baseline_docs = session.execute(
            select(Document).where(
                Document.doc_type.in_(["policy", "policy_regulation", "news", "social"]),
                policy_time >= baseline_start,
                policy_time <= end,
            )
        ).scalars().all()

    grouped_doc_ids: dict[tuple[str, str, date], set[int]] = defaultdict(set)
    grouped_hashes: dict[tuple[str, str, date], list[str]] = defaultdict(list)

    for doc in docs:
        day = doc.publish_date or (doc.created_at.date() if doc.created_at else None)
        extracted = doc.extracted_data or {}
        eff = (
            _normalize_json_text((extracted.get("policy") or {}).get("effective_date"))
            or (day.isoformat() if day else None)
        )
        if not eff:
            continue
        try:
            effective_day = datetime.strptime(eff[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        domain = _source_domain_of(doc)
        prompt_group = _prompt_group_of(doc)
        if normalized_domains and domain not in normalized_domains:
            continue
        if normalized_groups and prompt_group not in normalized_groups:
            continue
        bucket_time = _bucket_of(effective_day, bucket)
        key = (domain, prompt_group, bucket_time)
        grouped_doc_ids[key].add(int(doc.id))
        dedup_key = str(doc.text_hash or "").strip() or str(doc.uri or "").strip().lower()
        if dedup_key:
            grouped_hashes[key].append(dedup_key)

    baseline_group_counts: dict[str, int] = defaultdict(int)
    for doc in baseline_docs:
        prompt_group = _prompt_group_of(doc)
        if normalized_groups and prompt_group not in normalized_groups:
            continue
        baseline_group_counts[prompt_group] += 1

    window_days = _window_days(start, end)
    baseline_days = _window_days(baseline_start, end)
    out: list[dict[str, Any]] = []
    for (domain, prompt_group, bucket_time), doc_ids in sorted(grouped_doc_ids.items(), key=lambda x: x[0]):
        hashes = grouped_hashes[(domain, prompt_group, bucket_time)]
        hash_counts: dict[str, int] = defaultdict(int)
        for h in hashes:
            hash_counts[h] += 1
        duplicates = sum(max(0, c - 1) for c in hash_counts.values())
        total_docs = len(doc_ids)
        effective_new_docs = max(0, total_docs - duplicates)
        density = float(effective_new_docs) / float(window_days)
        baseline_density = float(baseline_group_counts.get(prompt_group, 0)) / float(baseline_days)
        norm_density = density / max(baseline_density, _EPSILON) if normalize else density
        dup_ratio = float(duplicates) / float(max(1, total_docs))
        out.append(
            {
                "source_domain": domain,
                "prompt_group_id": prompt_group,
                "bucket_time": bucket_time.isoformat(),
                "effective_new_docs": int(effective_new_docs),
                "density": density,
                "baseline_density": baseline_density,
                "norm_density": norm_density,
                "dup_ratio": dup_ratio,
            }
        )
    return out


def query_prompt_time_density_priority(
    *,
    end: date,
    candidate_windows: list[str],
    source_domains: list[str] | None = None,
    prompt_group_ids: list[str] | None = None,
    prefer_low_density: bool = True,
    exclude_high_dup: bool = True,
) -> list[dict[str, Any]]:
    if not candidate_windows:
        raise ValueError("candidate_windows must not be empty")

    rows: list[dict[str, Any]] = []
    for window in candidate_windows:
        raw = str(window).strip().lower()
        if not raw.endswith("d") or not raw[:-1].isdigit():
            raise ValueError("candidate_windows must use Nd format, e.g. 7d")
        window_days = max(1, int(raw[:-1]))
        start = end - timedelta(days=window_days - 1)
        density_rows = query_prompt_time_density(
            start=start,
            end=end,
            bucket="day",
            source_domains=source_domains,
            prompt_group_ids=prompt_group_ids,
            normalize=True,
        )
        for row in density_rows:
            dup_ratio = float(row["dup_ratio"])
            if exclude_high_dup and dup_ratio > 0.95:
                continue
            norm_density = float(row["norm_density"])
            freshness_penalty = min(1.0, float(window_days) / 365.0)
            score = (0.6 * norm_density) + (0.3 * dup_ratio) + (0.1 * freshness_penalty)
            if not prefer_low_density:
                score = -score
            rows.append(
                {
                    "source_domain": row["source_domain"],
                    "prompt_group_id": row["prompt_group_id"],
                    "window": raw,
                    "density": row["density"],
                    "norm_density": norm_density,
                    "dup_ratio": dup_ratio,
                    "collection_priority_score": score,
                }
            )

    rows.sort(key=lambda x: x["collection_priority_score"])
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    return rows


def select_priority_windows(
    rows: list[dict[str, Any]],
    *,
    max_windows: int = 3,
) -> list[dict[str, Any]]:
    if max_windows <= 0:
        raise ValueError("max_windows must be > 0")
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        window = str(row.get("window") or "").strip()
        if not window or window in seen:
            continue
        seen.add(window)
        selected.append(row)
        if len(selected) >= max_windows:
            break
    return selected
