from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError, DatabaseError
import logging

from ..services.ingest.policy import ingest_policy_documents
from ..services.ingest.market import ingest_market_data
from ..services.ingest.reports.california import collect_california_sales_reports
from ..services.ingest.news import (
    collect_calottery_news,
    collect_calottery_retailer_updates,
    collect_reddit_discussions,
)
from ..services.ingest.reports.general import (
    collect_weekly_market_reports,
    collect_monthly_financial_reports,
)
from ..services.tasks import (
    task_ingest_policy,
    task_ingest_market,
    task_collect_calottery_news,
    task_collect_calottery_retailer,
    task_collect_reddit,
    task_collect_weekly_reports,
    task_collect_monthly_reports,
)
from ..services.job_logger import list_jobs

logger = logging.getLogger(__name__)
from fastapi.responses import JSONResponse


class PolicyIngestRequest(BaseModel):
    state: str = Field(..., description="州，例如 CA")
    source_hint: str | None = Field(default=None, description="可选源标识")
    async_mode: bool = Field(default=False, description="是否走 Celery 异步任务")


router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/policy")
def ingest_policy(payload: PolicyIngestRequest):
    if payload.async_mode:
        task = task_ingest_policy.delay(payload.state)
        return {"task_id": task.id, "state": payload.state, "async": True}
    try:
        return ingest_policy_documents(payload.state, payload.source_hint)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


class MarketIngestRequest(BaseModel):
    state: str = Field(..., description="州，例如 CA")
    source_hint: str | None = Field(default=None, description="可选源标识")
    async_mode: bool = Field(default=False, description="是否走 Celery 异步任务")
    game: str | None = Field(default=None, description="玩法（如 SuperLotto Plus/Powerball/Mega Millions）")
    limit: int | None = Field(default=None, description="抓取条数上限（按适配器顺序）")


class CaliforniaReportRequest(BaseModel):
    limit: int = Field(default=3, ge=1, le=20, description="要保存的 PDF 报告数量上限")


class NewsRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50, description="抓取的条数")
    async_mode: bool = Field(default=False, description="是否异步执行")


class RedditRequest(BaseModel):
    subreddit: str = Field(default="Lottery", description="子论坛名称")
    limit: int = Field(default=20, ge=1, le=100, description="抓取贴文数")
    async_mode: bool = Field(default=False, description="是否异步执行")


@router.post("/market")
def ingest_market(payload: MarketIngestRequest):
    if payload.async_mode:
        task = task_ingest_market.delay(payload.state, payload.source_hint, payload.game, payload.limit)
        return {
            "task_id": task.id,
            "state": payload.state,
            "game": payload.game,
            "async": True,
        }
    try:
        return ingest_market_data(payload.state, payload.source_hint, payload.game, payload.limit)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/history")
def ingest_history(limit: int = 20):
    try:
        return list_jobs(limit=limit)
    except (OperationalError, DatabaseError) as e:
        logger.exception("数据库连接失败")
        raise HTTPException(
            status_code=503,
            detail="数据库服务不可用，请检查数据库服务是否已启动。"
        )
    except Exception as e:
        logger.exception("获取历史记录失败")
        error_msg = str(e)
        if "Connection" in error_msg or "db" in error_msg.lower() or "database" in error_msg.lower() or "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail="数据库服务不可用，请检查数据库服务是否已启动。"
            )
        raise HTTPException(status_code=500, detail=f"获取历史记录失败: {error_msg}")


@router.post("/reports/california")
def ingest_california_reports(payload: CaliforniaReportRequest):
    try:
        return collect_california_sales_reports(limit=payload.limit)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/news/calottery")
def ingest_calottery_news(payload: NewsRequest):
    if payload.async_mode:
        task = task_collect_calottery_news.delay(payload.limit)
        return {"task_id": task.id, "async": True, "limit": payload.limit}
    try:
        return collect_calottery_news(limit=payload.limit)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/news/calottery/retailer")
def ingest_calottery_retailer(payload: NewsRequest):
    if payload.async_mode:
        task = task_collect_calottery_retailer.delay(payload.limit)
        return {"task_id": task.id, "async": True, "limit": payload.limit}
    try:
        return collect_calottery_retailer_updates(limit=payload.limit)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/social/reddit")
def ingest_reddit(payload: RedditRequest):
    if payload.async_mode:
        task = task_collect_reddit.delay(payload.subreddit, payload.limit)
        return {
            "task_id": task.id,
            "async": True,
            "subreddit": payload.subreddit,
            "limit": payload.limit,
        }
    try:
        return collect_reddit_discussions(subreddit=payload.subreddit, limit=payload.limit)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/reports/weekly")
def ingest_weekly_reports(payload: NewsRequest):
    if payload.async_mode:
        task = task_collect_weekly_reports.delay(payload.limit)
        return {"task_id": task.id, "async": True, "limit": payload.limit}
    try:
        return collect_weekly_market_reports(limit=payload.limit)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/reports/monthly")
def ingest_monthly_reports(payload: NewsRequest):
    if payload.async_mode:
        task = task_collect_monthly_reports.delay(payload.limit)
        return {"task_id": task.id, "async": True, "limit": payload.limit}
    try:
        return collect_monthly_financial_reports(limit=payload.limit)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


