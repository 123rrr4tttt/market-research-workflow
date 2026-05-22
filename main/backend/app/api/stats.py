from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..contracts import ApiEnvelope, ErrorCode, fail, ok
from ..services.stats import (
    query_prompt_time_density,
    query_prompt_time_density_cloud,
    query_prompt_time_density_priority,
    select_priority_windows,
)

router = APIRouter(prefix="/stats", tags=["stats"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_WINDOW_RE = re.compile(r"^\d+d$")


class PromptTimeDensityItem(BaseModel):
    source_domain: str
    noun_group_id: str
    prompt_group_id: str
    bucket_time: str
    effective_new_docs: int
    density: float
    baseline_density: float
    norm_density: float
    dup_ratio: float

    model_config = {"extra": "allow"}


class PromptTimeDensityData(BaseModel):
    items: list[PromptTimeDensityItem]
    total: int
    start: str
    end: str
    bucket: str


class PromptTimeDensityCloudPoint(BaseModel):
    bucket_time: str
    density: float
    smoothed_density: float
    norm_density: float
    dup_ratio: float
    effective_new_docs: int
    is_peak: bool
    uncertainty_lower: float
    uncertainty_upper: float

    model_config = {"extra": "allow"}


class PromptTimeDensityCloudData(BaseModel):
    cloud_points: list[PromptTimeDensityCloudPoint]
    cloud_summary: dict[str, Any]
    uncertainty_band: dict[str, Any]
    cold_start_proxy: dict[str, Any] | None = None
    start: str
    end: str

    model_config = {"extra": "allow"}


class PromptTimeDensityPriorityItem(BaseModel):
    source_domain: str | None = None
    noun_group_id: str | None = None
    prompt_group_id: str | None = None
    window: str | None = None
    density: float | None = None
    norm_density: float | None = None
    dup_ratio: float | None = None
    peak_pressure: float | None = None
    latent_density_score: float | None = None
    vector_overlap: float | None = None
    shift_signal: float | None = None
    offpeak_confidence: float | None = None
    collection_priority_score: float | None = None
    freshness_penalty: float | None = None
    target_overlap: float | None = None
    p_base: float | None = None
    p_new: float | None = None
    kl_to_base: float | None = None
    policy_decision_trace: dict[str, Any] | None = None
    rank: int | None = None
    request_id: str | None = None
    chosen_window: str | None = None
    is_chosen: bool | None = None

    model_config = {"extra": "allow"}


class PromptTimeDensityPriorityData(BaseModel):
    items: list[PromptTimeDensityPriorityItem]
    total: int
    end: str
    candidate_windows: list[str]


class PromptTimeDensityWindowSelectionData(PromptTimeDensityPriorityData):
    max_windows: int


PromptTimeDensityEnvelope = ApiEnvelope[PromptTimeDensityData]
PromptTimeDensityCloudEnvelope = ApiEnvelope[PromptTimeDensityCloudData]
PromptTimeDensityPriorityEnvelope = ApiEnvelope[PromptTimeDensityPriorityData]
PromptTimeDensityWindowSelectionEnvelope = ApiEnvelope[PromptTimeDensityWindowSelectionData]


def _json_error(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    payload = fail(code, message)
    payload["detail"] = {"error": payload["error"], "message": payload["error"]["message"]}
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={"X-Error-Code": code.value},
    )


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


def _coalesce_noun_group_ids(
    *,
    noun_group_ids: Optional[list[str]],
    prompt_group_ids: Optional[list[str]],
) -> Optional[list[str]]:
    return noun_group_ids if noun_group_ids is not None else prompt_group_ids


@router.get("/prompt-time-density", response_model=PromptTimeDensityEnvelope)
def get_prompt_time_density(
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    time_window: Optional[str] = Query("30d", description="时间窗 Nd，如 7d/30d/90d"),
    bucket: str = Query("day", description="桶粒度 day/week/month"),
    source_domains: Optional[list[str]] = Query(None, description="来源域过滤"),
    noun_group_ids: Optional[list[str]] = Query(None, description="语义组过滤（noun group）"),
    prompt_group_ids: Optional[list[str]] = Query(None, description="提示词组过滤"),
    normalize: bool = Query(True, description="是否输出规范化密度"),
):
    try:
        start_dt, end_dt = _resolve_range(start=start, end=end, time_window=time_window)
        if bucket not in {"day", "week", "month"}:
            return _json_error(422, ErrorCode.INVALID_INPUT, "bucket must be one of: day, week, month")
        merged_groups = _coalesce_noun_group_ids(noun_group_ids=noun_group_ids, prompt_group_ids=prompt_group_ids)
        items = query_prompt_time_density(
            start=start_dt,
            end=end_dt,
            bucket=bucket,
            source_domains=source_domains,
            noun_group_ids=merged_groups,
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
    except Exception as exc:  # noqa: BLE001
        return _json_error(500, ErrorCode.INTERNAL_ERROR, str(exc))


@router.get("/prompt-time-density/cloud", response_model=PromptTimeDensityCloudEnvelope)
def get_prompt_time_density_cloud(
    keyword: str = Query(..., description="关键词"),
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    time_window: Optional[str] = Query("30d", description="时间窗 Nd，如 7d/30d/90d"),
    bucket: str = Query("day", description="桶粒度 day/week/month"),
    source_domains: Optional[list[str]] = Query(None, description="来源域过滤"),
    noun_group_ids: Optional[list[str]] = Query(None, description="语义组过滤（noun group）"),
    prompt_group_ids: Optional[list[str]] = Query(None, description="提示词组过滤（兼容）"),
    smoothing: str = Query("ema", description="平滑方法 ema/gaussian/none"),
    peak_percentile: float = Query(0.85, description="峰值分位阈值 [0,1]"),
    uncertainty: float = Query(0.2, description="不确定度带宽 [0,1]"),
    normalize: bool = Query(True, description="是否输出规范化密度"),
):
    try:
        start_dt, end_dt = _resolve_range(start=start, end=end, time_window=time_window)
        if bucket not in {"day", "week", "month"}:
            return _json_error(422, ErrorCode.INVALID_INPUT, "bucket must be one of: day, week, month")
        merged_groups = _coalesce_noun_group_ids(noun_group_ids=noun_group_ids, prompt_group_ids=prompt_group_ids)
        data = query_prompt_time_density_cloud(
            keyword=keyword,
            start=start_dt,
            end=end_dt,
            bucket=bucket,
            source_domains=source_domains,
            noun_group_ids=merged_groups,
            prompt_group_ids=prompt_group_ids,
            smoothing=smoothing,
            peak_percentile=peak_percentile,
            uncertainty=uncertainty,
            normalize=normalize,
        )
        return ok(
            {
                **data,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
            }
        )
    except ValueError as exc:
        return _json_error(422, ErrorCode.INVALID_INPUT, str(exc))
    except Exception as exc:  # noqa: BLE001
        return _json_error(500, ErrorCode.INTERNAL_ERROR, str(exc))


@router.get("/prompt-time-density/priority", response_model=PromptTimeDensityPriorityEnvelope)
def get_prompt_time_density_priority(
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
    candidate_windows: Optional[list[str]] = Query(None, description="候选窗口 Nd 列表"),
    source_domains: Optional[list[str]] = Query(None, description="来源域过滤"),
    noun_group_ids: Optional[list[str]] = Query(None, description="语义组过滤（noun group）"),
    prompt_group_ids: Optional[list[str]] = Query(None, description="提示词组过滤"),
    prefer_low_density: bool = Query(True, description="是否低密度优先"),
    exclude_high_dup: bool = Query(True, description="是否过滤高重复窗口"),
    min_overlap: float = Query(0.35, description="最小 overlap [0,1]"),
    target_overlap: float = Query(0.55, description="目标 overlap [0,1]"),
    eta: float = Query(0.08, description="轻避峰强度 >=0"),
    delta_max: float = Query(0.12, description="单窗口分布偏移上限 [0,1]"),
    tau: float = Query(0.03, description="KL 预算 >=0"),
    avoid_peak: bool = Query(True, description="是否启用轻避峰"),
):
    try:
        end_dt = _parse_ymd(end, field="end") or datetime.utcnow().date()
        windows = candidate_windows or ["7d", "30d", "90d"]
        merged_groups = _coalesce_noun_group_ids(noun_group_ids=noun_group_ids, prompt_group_ids=prompt_group_ids)
        items = query_prompt_time_density_priority(
            end=end_dt,
            candidate_windows=windows,
            source_domains=source_domains,
            noun_group_ids=merged_groups,
            prompt_group_ids=prompt_group_ids,
            prefer_low_density=prefer_low_density,
            exclude_high_dup=exclude_high_dup,
            min_overlap=min_overlap,
            target_overlap=target_overlap,
            eta=eta,
            delta_max=delta_max,
            tau=tau,
            avoid_peak=avoid_peak,
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
    except Exception as exc:  # noqa: BLE001
        return _json_error(500, ErrorCode.INTERNAL_ERROR, str(exc))


@router.get("/prompt-time-density/select-windows", response_model=PromptTimeDensityWindowSelectionEnvelope)
def select_prompt_time_windows(
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
    candidate_windows: Optional[list[str]] = Query(None, description="候选窗口 Nd 列表"),
    source_domains: Optional[list[str]] = Query(None, description="来源域过滤"),
    noun_group_ids: Optional[list[str]] = Query(None, description="语义组过滤（noun group）"),
    prompt_group_ids: Optional[list[str]] = Query(None, description="提示词组过滤"),
    max_windows: int = Query(3, ge=1, le=10, description="最多返回窗口数"),
    prefer_low_density: bool = Query(True, description="是否低密度优先"),
    exclude_high_dup: bool = Query(True, description="是否过滤高重复窗口"),
    min_overlap: float = Query(0.35, description="最小 overlap [0,1]"),
    target_overlap: float = Query(0.55, description="目标 overlap [0,1]"),
    eta: float = Query(0.08, description="轻避峰强度 >=0"),
    delta_max: float = Query(0.12, description="单窗口分布偏移上限 [0,1]"),
    tau: float = Query(0.03, description="KL 预算 >=0"),
    avoid_peak: bool = Query(True, description="是否启用轻避峰"),
):
    try:
        end_dt = _parse_ymd(end, field="end") or datetime.utcnow().date()
        windows = candidate_windows or ["7d", "30d", "90d"]
        merged_groups = _coalesce_noun_group_ids(noun_group_ids=noun_group_ids, prompt_group_ids=prompt_group_ids)
        rows = query_prompt_time_density_priority(
            end=end_dt,
            candidate_windows=windows,
            source_domains=source_domains,
            noun_group_ids=merged_groups,
            prompt_group_ids=prompt_group_ids,
            prefer_low_density=prefer_low_density,
            exclude_high_dup=exclude_high_dup,
            min_overlap=min_overlap,
            target_overlap=target_overlap,
            eta=eta,
            delta_max=delta_max,
            tau=tau,
            avoid_peak=avoid_peak,
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
    except Exception as exc:  # noqa: BLE001
        return _json_error(500, ErrorCode.INTERNAL_ERROR, str(exc))
