import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .settings.config import settings
from .models.base import engine
from .services.search.es_client import get_es_client
from .services.projects import bind_project
from .startup_hooks import register_startup_hooks
from .web_ui_routes import register_ui_routes

# Create FastAPI app
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="Market Intel API", version="0.1.0-rc.1")

# Cache active project for fallback routing
_ACTIVE_PROJECT_CACHE_KEY: str | None = None
_ACTIVE_PROJECT_CACHE_TS: float = 0.0

def _get_active_project_key_fallback() -> str | None:
    global _ACTIVE_PROJECT_CACHE_KEY, _ACTIVE_PROJECT_CACHE_TS
    now = time.time()
    if _ACTIVE_PROJECT_CACHE_KEY and (now - _ACTIVE_PROJECT_CACHE_TS) < 5:
        return _ACTIVE_PROJECT_CACHE_KEY
    try:
        with engine.connect() as conn:
            conn.execute(text('SET search_path TO "public"'))
            key = conn.execute(
                text("SELECT project_key FROM public.projects WHERE is_active = true LIMIT 1")
            ).scalar()
            if key:
                _ACTIVE_PROJECT_CACHE_KEY = str(key)
                _ACTIVE_PROJECT_CACHE_TS = now
                return _ACTIVE_PROJECT_CACHE_KEY
    except Exception:
        return None
    return None

# 在 Docker 环境中，frontend 目录通过 volume 挂载到 /app/frontend
# 优先使用挂载的本地 frontend 目录（对应当前独立项目的 frontend）
# 如果不存在，则使用 backend/frontend 作为后备
_LOCAL_FRONTEND_ROOT = Path(__file__).resolve().parent.parent.parent / "frontend"
_BACKEND_FRONTEND_ROOT = Path(__file__).resolve().parent.parent / "frontend"
_LOCAL_FRONTEND = _LOCAL_FRONTEND_ROOT / "templates"
_BACKEND_FRONTEND = _BACKEND_FRONTEND_ROOT / "templates"

# 在容器内，/app/frontend 对应本地的 frontend 目录
# 统一使用与config.py相同的判断逻辑：检查DOCKER_ENV环境变量或/.dockerenv文件
if os.getenv("DOCKER_ENV") == "true" or os.path.exists("/.dockerenv"):
    # Docker 环境：使用挂载的本地目录
    FRONTEND_ROOT = Path("/app/frontend")
else:
    # 本地环境：优先使用项目根目录的 frontend
    if _LOCAL_FRONTEND.exists():
        FRONTEND_ROOT = _LOCAL_FRONTEND_ROOT
    else:
        FRONTEND_ROOT = _BACKEND_FRONTEND_ROOT

TEMPLATE_DIR = FRONTEND_ROOT / "templates"
STATIC_DIR = FRONTEND_ROOT / "static"
USA_MAP_PATH = STATIC_DIR / "js" / "USA.json"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Static files (css/js/images) for frontend templates
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
register_startup_hooks(app)

REQUEST_COUNT = Counter(
    "market_api_requests_total",
    "API request count",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "market_api_request_latency_seconds",
    "API request latency",
    ["endpoint"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    project_key = request.headers.get("X-Project-Key") or request.query_params.get("project_key")
    if not project_key:
        project_key = _get_active_project_key_fallback() or settings.active_project_key
    start = time.perf_counter()
    with bind_project(project_key):
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
register_ui_routes(app, templates=templates, template_dir=TEMPLATE_DIR, usa_map_path=USA_MAP_PATH)


# Mount API routers (placeholders; will be populated as modules are implemented)
try:
    from .api import router as api_router  # type: ignore

    app.include_router(api_router, prefix="/api/v1")
except Exception:
    # Safe to skip during initial bootstrapping when modules are empty
    pass
