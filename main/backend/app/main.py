import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .settings.config import settings
from .models.base import engine
from .services.search.es_client import get_es_client

# Create FastAPI app
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="Lottery Intel API", version="0.1.0")

# 在 Docker 环境中，frontend 目录通过 volume 挂载到 /app/frontend
# 优先使用挂载的本地 frontend 目录（对应 projects/彩票情报(lottery-intel)/frontend）
# 如果不存在，则使用 backend/frontend 作为后备
_LOCAL_FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend" / "templates"
_BACKEND_FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "templates"

# 在容器内，/app/frontend 对应本地的 frontend 目录
if os.getenv("DOCKER_ENV") == "true":
    # Docker 环境：使用挂载的本地目录
    TEMPLATE_DIR = Path("/app/frontend/templates")
else:
    # 本地环境：优先使用项目根目录的 frontend
    if _LOCAL_FRONTEND.exists():
        TEMPLATE_DIR = _LOCAL_FRONTEND
    else:
        TEMPLATE_DIR = _BACKEND_FRONTEND

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

REQUEST_COUNT = Counter(
    "lottery_api_requests_total",
    "API request count",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "lottery_api_request_latency_seconds",
    "API request latency",
    ["endpoint"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response: Response = await call_next(request)
    elapsed = time.perf_counter() - start
    endpoint = request.url.path
    REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
    REQUEST_LATENCY.labels(endpoint).observe(elapsed)
    logging.getLogger("app").info(
        "request", extra={"method": request.method, "path": endpoint, "status": response.status_code, "latency": elapsed}
    )
    return response


@app.get("/api/v1/health")
def health_check() -> dict:
    """Lightweight health check; deep checks added later."""
    return {
        "status": "ok",
        "provider": settings.llm_provider,
        "env": settings.env,
    }


@app.get("/api/v1/health/deep")
def deep_health_check() -> dict:
    """Deep health check: DB and Elasticsearch connectivity."""
    checks: dict[str, str] = {}
    # DB check
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001 - report raw for observability at MVP
        checks["database"] = f"error: {type(e).__name__}"

    # ES check
    try:
        es = get_es_client()
        ok = es.ping()
        checks["elasticsearch"] = "ok" if ok else "error: ping failed"
    except Exception as e:  # noqa: BLE001
        checks["elasticsearch"] = f"error: {type(e).__name__}"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, **checks}


@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/index.html", response_class=HTMLResponse)
def index_html(request: Request):
    """主页的 index.html 路由"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/settings.html", response_class=HTMLResponse)
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})


# Mount API routers (placeholders; will be populated as modules are implemented)
try:
    from .api import router as api_router  # type: ignore

    app.include_router(api_router, prefix="/api/v1")
except Exception:
    # Safe to skip during initial bootstrapping when modules are empty
    pass




@app.get("/admin.html", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


