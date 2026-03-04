from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import AnyHttpUrl, BaseModel, Field

from ..contracts.responses import ok
from ..services.llm_report_generator import (
    build_structured_report,
    evaluate_report_gate,
    render_markdown,
)


router = APIRouter(prefix="/llm-report", tags=["llm-report"])


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


@router.post("/generate")
def generate_llm_report(payload: GenerateReportRequest) -> dict[str, Any]:
    report = build_structured_report(
        topic=payload.topic,
        sources=[item.model_dump() for item in payload.sources],
        section_titles=payload.section_titles or None,
    )
    markdown = render_markdown(report)
    gate = evaluate_report_gate(report)
    return ok({"report": report.to_dict(), "markdown": markdown, "quality_gate": gate})
