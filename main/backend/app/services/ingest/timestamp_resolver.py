from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any

_TIME_PARSE_VERSION = "st_v1"
_MIN_VALID_YEAR = 1990
_MAX_FUTURE_DRIFT = timedelta(hours=24)
_DATETIME_KEYWORDS = (
    "source_time",
    "publish",
    "published",
    "pub_date",
    "pubdate",
    "effective_date",
    "datepublished",
    "datemodified",
    "updated_at",
    "lastmod",
    "timestamp",
    "time",
)
_ISO_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}(?::\d{2})?)(?:\.\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _to_utc(value)

    raw = str(value).strip()
    if not raw:
        return None

    if raw.isdigit():
        try:
            iv = int(raw)
            if len(raw) == 13:
                return datetime.fromtimestamp(iv / 1000, tz=timezone.utc)
            if len(raw) == 10:
                return datetime.fromtimestamp(iv, tz=timezone.utc)
        except Exception:
            pass

    normalized = raw.replace("Z", "+00:00")
    try:
        return _to_utc(datetime.fromisoformat(normalized))
    except Exception:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return _to_utc(datetime.strptime(raw, fmt))
        except Exception:
            continue

    try:
        return _to_utc(parsedate_to_datetime(raw))
    except Exception:
        return None


def _is_valid_candidate(candidate: datetime, *, ingested_at: datetime) -> bool:
    if candidate.year < _MIN_VALID_YEAR:
        return False
    if candidate > ingested_at + _MAX_FUTURE_DRIFT:
        return False
    return True


def _candidate_score(provenance: str, candidate: datetime, *, ingested_at: datetime) -> float:
    base = 0.60
    lowered = provenance.lower()
    if "source_time" in lowered:
        base = 0.95
    elif "json" in lowered or "meta" in lowered:
        base = 0.90
    elif "publish" in lowered or "effective_date" in lowered:
        base = 0.85
    elif "header" in lowered:
        base = 0.78
    elif "body_regex" in lowered:
        base = 0.70

    age_days = abs((ingested_at - candidate).total_seconds()) / 86400
    if age_days > 3650:
        base -= 0.10
    if age_days > 7300:
        base -= 0.10
    return max(0.05, min(0.99, base))


def _walk_metadata_candidates(obj: Any, *, path: str = "metadata", depth: int = 0) -> list[tuple[datetime, str]]:
    if depth > 4:
        return []
    out: list[tuple[datetime, str]] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            key_str = str(key or "").strip()
            next_path = f"{path}.{key_str}" if key_str else path
            lowered = key_str.lower()
            if any(marker in lowered for marker in _DATETIME_KEYWORDS):
                parsed = _parse_datetime(value)
                if parsed is not None:
                    out.append((parsed, next_path))
            out.extend(_walk_metadata_candidates(value, path=next_path, depth=depth + 1))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj[:20]):
            out.extend(_walk_metadata_candidates(value, path=f"{path}[{idx}]", depth=depth + 1))
    else:
        parsed = _parse_datetime(obj)
        if parsed is not None and path.endswith(tuple(_DATETIME_KEYWORDS)):
            out.append((parsed, path))

    return out


def _extract_body_candidate(content_excerpt: str) -> tuple[datetime, str] | None:
    text = str(content_excerpt or "")
    if not text:
        return None
    match = _ISO_DATE_RE.search(text[:3000])
    if not match:
        return None
    parsed = _parse_datetime(match.group(0))
    if parsed is None:
        return None
    return parsed, "body_regex_date"


def resolve_document_temporal_fields(
    *,
    source_domain: str | None,
    metadata: dict[str, Any] | None,
    content_excerpt: str,
    ingested_at: datetime | None = None,
) -> dict[str, Any]:
    ingest_dt = _to_utc(ingested_at or datetime.now(timezone.utc))
    candidates: list[tuple[datetime, str]] = []
    candidates.extend(_walk_metadata_candidates(metadata or {}))
    body_candidate = _extract_body_candidate(content_excerpt)
    if body_candidate is not None:
        candidates.append(body_candidate)

    scored: list[tuple[float, datetime, str]] = []
    for dt, provenance in candidates:
        if not _is_valid_candidate(dt, ingested_at=ingest_dt):
            continue
        scored.append((_candidate_score(provenance, dt, ingested_at=ingest_dt), dt, provenance))

    if scored:
        scored.sort(key=lambda item: (-item[0], item[1]))
        confidence, source_time, provenance = scored[0]
        return {
            "source_domain": str(source_domain or "").strip().lower() or None,
            "source_time": source_time,
            "effective_time": source_time,
            "time_confidence": round(float(confidence), 3),
            "time_provenance": provenance,
            "time_parse_version": _TIME_PARSE_VERSION,
            "ingested_at": ingest_dt,
        }

    return {
        "source_domain": str(source_domain or "").strip().lower() or None,
        "source_time": None,
        "effective_time": ingest_dt,
        "time_confidence": 0.0,
        "time_provenance": "fallback_ingested_at",
        "time_parse_version": _TIME_PARSE_VERSION,
        "ingested_at": ingest_dt,
    }
