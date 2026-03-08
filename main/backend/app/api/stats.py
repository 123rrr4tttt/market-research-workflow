from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..contracts import ErrorCode, fail, ok
from ..services.stats import query_prompt_time_density, query_prompt_time_density_priority, select_priority_windows

router = APIRouter(prefix="/stats", tags=["stats"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_WINDOW_RE = re.compile(r"^\d+d$")


def _json_error(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=fail(code, message))


def _parse_ymd(value: Optional[str], *, field: str) -> Optional[date]:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if not _DATE_RE.match(raw):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def _resolve_range(*, start: Optional[str], end: Optional[str], time_window: Optional[str]) -> tuple[date, date]:
    start_dt = _parse_ymd(start, field="start")
    end_dt = _parse_ymd(end, field="end")
    if start_dt and end_dt:
        if start_dt > end_dt:
            raise ValueError("start must be <= end")
        return start_dt, end_dt
    if start_dt or end_dt:
        raise ValueError("start and end must be provided together")

    window = (time_window or "30d").strip().lower()
    if not _TIME_WINDOW_RE.match(window):
        raise ValueError("time_window must use Nd format, e.g. 7d/30d/90d")
    days = max(1, int(window[:-1]))
    end_day = datetime.utcnow().date()
    start_day = end_day - timedelta(days=days - 1)
    return start_day, end_day


@router.get("/prompt-time-density")
def get_prompt_time_density(
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    time_window: Optional[str] = Query("30d", description="时间窗 Nd，如 7d/30d/90d"),
    bucket: str = Query("day", description="桶粒度 day/week/month"),
    source_domains: Optional[list[str]] = Query(None, description="来源域过滤"),
    prompt_group_ids: Optional[list[str]] = Query(None, description="提示词组过滤"),
    normalize: bool = Query(True, description="是否输出规范化密度"),
):
    try:
        start_dt, end_dt = _resolve_range(start=start, end=end, time_window=time_window)
        if bucket not in {"day", "week", "month"}:
            return _json_error(422, ErrorCode.INVALID_INPUT, "bucket must be one of: day, week, month")
        items = query_prompt_time_density(
            start=start_dt,
            end=end_dt,
            bucket=bucket,
            source_domains=source_domains,
            prompt_group_ids=prompt_group_ids,
            normalize=normalize,
        )
        return ok(
            {
                "items": items,
                "total": len(items),
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "bucket": bucket,
            }
        )
    except ValueError as exc:
        return _json_error(422, ErrorCode.INVALID_INPUT, str(exc))


@router.get("/prompt-time-density/priority")
def get_prompt_time_density_priority(
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
    candidate_windows: Optional[list[str]] = Query(None, description="候选窗口 Nd 列表"),
    source_domains: Optional[list[str]] = Query(None, description="来源域过滤"),
    prompt_group_ids: Optional[list[str]] = Query(None, description="提示词组过滤"),
    prefer_low_density: bool = Query(True, description="是否低密度优先"),
    exclude_high_dup: bool = Query(True, description="是否过滤高重复窗口"),
):
    try:
        end_dt = _parse_ymd(end, field="end") or datetime.utcnow().date()
        windows = candidate_windows or ["7d", "30d", "90d"]
        items = query_prompt_time_density_priority(
            end=end_dt,
            candidate_windows=windows,
            source_domains=source_domains,
            prompt_group_ids=prompt_group_ids,
            prefer_low_density=prefer_low_density,
            exclude_high_dup=exclude_high_dup,
        )
        return ok(
            {
                "items": items,
                "total": len(items),
                "end": end_dt.isoformat(),
                "candidate_windows": windows,
            }
        )
    except ValueError as exc:
        return _json_error(422, ErrorCode.INVALID_INPUT, str(exc))


@router.get("/prompt-time-density/select-windows")
def select_prompt_time_windows(
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
    candidate_windows: Optional[list[str]] = Query(None, description="候选窗口 Nd 列表"),
    source_domains: Optional[list[str]] = Query(None, description="来源域过滤"),
    prompt_group_ids: Optional[list[str]] = Query(None, description="提示词组过滤"),
    max_windows: int = Query(3, ge=1, le=10, description="最多返回窗口数"),
    prefer_low_density: bool = Query(True, description="是否低密度优先"),
    exclude_high_dup: bool = Query(True, description="是否过滤高重复窗口"),
):
    try:
        end_dt = _parse_ymd(end, field="end") or datetime.utcnow().date()
        windows = candidate_windows or ["7d", "30d", "90d"]
        rows = query_prompt_time_density_priority(
            end=end_dt,
            candidate_windows=windows,
            source_domains=source_domains,
            prompt_group_ids=prompt_group_ids,
            prefer_low_density=prefer_low_density,
            exclude_high_dup=exclude_high_dup,
        )
        selected = select_priority_windows(rows, max_windows=max_windows)
        return ok(
            {
                "items": selected,
                "total": len(selected),
                "end": end_dt.isoformat(),
                "candidate_windows": windows,
                "max_windows": max_windows,
            }
        )
    except ValueError as exc:
        return _json_error(422, ErrorCode.INVALID_INPUT, str(exc))
