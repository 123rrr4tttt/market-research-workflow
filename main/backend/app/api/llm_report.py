from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from ..contracts.responses import ok
from ..services.job_logger import complete_job, fail_job, start_job
from ..services.llm_report_generator import (
    build_structured_report,
    evaluate_report_gate,
    export_quality_gate_metrics,
    render_markdown,
)
from ..services.llm_report_source_enrichment import resolve_report_sources
from ..settings.config import settings


router = APIRouter(prefix="/llm-report", tags=["llm-report"])
_LLM_REPORT_JOB_TYPE = "llm_report_gen"
_VALID_GATE_MODES = {"off", "warn", "strict"}


class SourceInput(BaseModel):
    id: str | None = Field(default=None, max_length=64)
    title: str = Field(..., min_length=1, max_length=300)
    url: AnyHttpUrl
    publisher: str | None = Field(default=None, max_length=120)
    published_at: str | None = Field(default=None, max_length=64)
    retrieved_at: str | None = Field(default=None, max_length=64)
    evidence: str | None = Field(default=None, max_length=2000)


class GenerateReportRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    section_titles: list[str] = Field(default_factory=list, max_length=12)
    sources: list[SourceInput] = Field(default_factory=list, max_length=100)

    @field_validator("topic")
    @classmethod
    def _topic_must_not_be_blank(cls, value: str) -> str:
        if not str(value or "").strip():
            raise ValueError("topic cannot be blank")
        return value

    @field_validator("section_titles")
    @classmethod
    def _section_titles_must_be_valid(cls, value: list[str]) -> list[str]:
        for idx, item in enumerate(value, start=1):
            title = str(item or "").strip()
            if not title:
                raise ValueError(f"section_titles[{idx}] cannot be blank")
            if len(title) > 120:
                raise ValueError(f"section_titles[{idx}] exceeds max length 120")
        return value


def _resolve_gate_mode(raw_mode: str | None) -> tuple[str, str, bool]:
    normalized_raw_mode = str(raw_mode or "").strip().lower()
    if not normalized_raw_mode:
        return "strict", "strict", False
    if normalized_raw_mode in _VALID_GATE_MODES:
        return normalized_raw_mode, normalized_raw_mode, False
    return "strict", normalized_raw_mode, True


def _resolve_auto_source_target_count(raw_value: int | None) -> int:
    try:
        value = int(raw_value or 0)
    except Exception:  # noqa: BLE001
        value = 0
    if value <= 0:
        return 6
    return min(value, 20)


@router.post("/generate")
def generate_llm_report(payload: GenerateReportRequest, request: Request) -> dict[str, Any]:
    if not settings.llm_report_enabled:
        raise HTTPException(status_code=503, detail="llm report is temporarily disabled by config")

    trace_id = None
    if request is not None:
        trace_id = (request.headers.get("X-Request-Id") or "").strip() or None

    gate_mode, gate_mode_raw, gate_mode_fallback = _resolve_gate_mode(settings.llm_report_gate_mode)
    requested_sources = [item.model_dump() for item in payload.sources]
    source_count_requested = len(requested_sources)
    job_id: int | None = None
    job_finalized = False
    try:
        auto_source_enabled = bool(getattr(settings, "llm_report_auto_source_enabled", True))
        auto_source_target_count = _resolve_auto_source_target_count(
            getattr(settings, "llm_report_auto_source_target_count", 6)
        )
        if requested_sources or not auto_source_enabled:
            resolved_sources = requested_sources
        else:
            resolved_sources = resolve_report_sources(
                payload.topic,
                requested_sources,
                target_count=auto_source_target_count,
            )
        source_count_resolved = len(resolved_sources)
        job_id = start_job(
            _LLM_REPORT_JOB_TYPE,
            {
                "topic": payload.topic,
                "source_count_requested": source_count_requested,
                "source_count_resolved": source_count_resolved,
                "auto_source_enabled": auto_source_enabled,
                "auto_source_target_count": auto_source_target_count,
                "gate_mode": gate_mode,
                "gate_mode_raw": gate_mode_raw,
                "gate_mode_fallback": gate_mode_fallback,
                "trace_id": trace_id,
            },
        )
        report = build_structured_report(
            topic=payload.topic,
            sources=resolved_sources,
            section_titles=payload.section_titles or None,
        )
        markdown = render_markdown(report)
        gate = evaluate_report_gate(report)
        quality_gate_metrics = export_quality_gate_metrics(gate)

        gate_result = {
            **quality_gate_metrics,
            "trace_id": trace_id,
            "gate_mode": gate_mode,
            "gate_mode_raw": gate_mode_raw,
            "gate_mode_fallback": gate_mode_fallback,
            "hard_failures": gate["hard_failures"],
            "soft_failures": gate["soft_failures"],
            "missing_items": gate["missing_items"],
            "rules": gate["rules"],
            "observability": gate["observability"],
        }
        if gate_mode == "strict" and gate["decision"] == "fail":
            complete_job(
                job_id,
                status="failed",
                result={
                    **gate_result,
                    "error_code": "QUALITY_GATE_BLOCKED",
                    "gate_blocked": True,
                },
            )
            job_finalized = True
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "quality gate blocked report generation in strict mode",
                    "quality_gate": gate,
                    "quality_gate_metrics": quality_gate_metrics,
                    "observability": {
                        "job_id": job_id,
                        "trace_id": trace_id,
                        "gate_mode": gate_mode,
                    },
                },
            )

        complete_job(job_id, result=gate_result)
        job_finalized = True
        return ok(
            {
                "report": report.to_dict(),
                "markdown": markdown,
                "quality_gate": gate,
                "quality_gate_metrics": quality_gate_metrics,
                "observability": {
                    "job_id": job_id,
                    "trace_id": trace_id,
                    "gate_mode": gate_mode,
                    "gate_mode_raw": gate_mode_raw,
                    "gate_mode_fallback": gate_mode_fallback,
                },
            }
        )
    except HTTPException as exc:
        if not job_finalized and job_id is not None:
            fail_job(job_id, str(getattr(exc, "detail", exc)))
        raise
    except Exception as exc:  # noqa: BLE001
        if not job_finalized and job_id is not None:
            fail_job(job_id, str(exc))
        raise HTTPException(
            status_code=500,
            detail={
                "message": "failed to generate llm report",
                "error_code": "LLM_REPORT_INTERNAL_ERROR",
                "trace_id": trace_id,
                "job_id": job_id,
            },
        ) from exc
