from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from ..contracts import ErrorCode, error_response
from ..contracts.responses import ok
from ..services.report import generate_html_report, generate_csv_report


class ReportRequest(BaseModel):
    states: list[str] = Field(default_factory=lambda: ["CA"])
    start: str | None = Field(default=None, description="开始日期 YYYY-MM-DD")
    end: str | None = Field(default=None, description="结束日期 YYYY-MM-DD")
    format: str = Field(default="html", description="html 或 csv")


router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("")
def create_report(payload: ReportRequest):
    fmt = payload.format.lower()
    try:
        if fmt == "html":
            html = generate_html_report(payload.states, payload.start, payload.end)
            return ok({"format": "html", "data": html})
        if fmt == "csv":
            csv_bytes = generate_csv_report(payload.states, payload.start, payload.end)
            return Response(
                content=csv_bytes,
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=lottery_report.csv"},
            )
        raise HTTPException(
            status_code=400,
            detail=error_response(
                ErrorCode.INVALID_INPUT,
                "暂不支持的格式",
            ),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=error_response(
                ErrorCode.INVALID_INPUT,
                str(exc),
            ),
        ) from exc
