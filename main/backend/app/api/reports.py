from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

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
    if fmt == "html":
        html = generate_html_report(payload.states, payload.start, payload.end)
        return {"format": "html", "data": html}
    if fmt == "csv":
        csv_bytes = generate_csv_report(payload.states, payload.start, payload.end)
        return Response(
            content=csv_bytes,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=lottery_report.csv"},
        )
    raise ValueError("暂不支持的格式")


