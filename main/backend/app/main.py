import logging
import os
import time
import json
from pathlib import Path

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .settings.config import settings
from .models.base import engine
from .models.base import Base
from .models.entities import (
    ConfigState,
    Document,
    Embedding,
    EtlJobRun,
    IngestChannel,
    LlmServiceConfig,
    MarketMetricPoint,
    MarketStat,
    PriceObservation,
    Product,
    SearchHistory,
    SourceLibraryItem,
    Source,
    SharedIngestChannel,
    SharedSourceLibraryItem,
    Topic,
)
from .services.search.es_client import get_es_client
from .services.projects import bind_project

# Create FastAPI app
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="Market Intel API", version="0.1.0")

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

@app.on_event("startup")
def _ensure_bootstrap_projects() -> None:
    """
    Bootstrap control-plane projects and migrate away from legacy "default".

    Meaning:
    - One-time migration: legacy project_key "default" -> "online_lottery" (schema rename,
      table moves, aggregator remap). This is historical migration, not subproject injection.
    - First install: if no projects exist, create "business_survey" (商业调查) as the initial project.
    - All projects are peers. "public" schema is reserved for control-plane and shared tables.
    """
    try:
        with engine.begin() as conn:
            # Control-plane always in public schema
            conn.execute(text('SET search_path TO "public"'))

            # If legacy default project exists, migrate it to online_lottery.
            legacy = conn.execute(
                text("SELECT project_key, schema_name FROM public.projects WHERE project_key = 'default' LIMIT 1")
            ).first()
            if legacy:
                # Migrate schema if needed (idempotent)
                has_old_schema = conn.execute(text("SELECT to_regclass('project_default.documents') IS NOT NULL")).scalar()
                has_new_schema = conn.execute(text("SELECT to_regclass('project_online_lottery.documents') IS NOT NULL")).scalar()
                if has_old_schema and not has_new_schema:
                    # If an empty target schema exists, drop it first
                    target_has_any = conn.execute(
                        text(
                            """
                            SELECT EXISTS(
                              SELECT 1 FROM pg_tables WHERE schemaname='project_online_lottery' LIMIT 1
                            )
                            """
                        )
                    ).scalar()
                    if not target_has_any:
                        conn.execute(text('DROP SCHEMA IF EXISTS "project_online_lottery" CASCADE'))
                    conn.execute(text('ALTER SCHEMA "project_default" RENAME TO "project_online_lottery"'))

                conn.execute(
                    text(
                        """
                        UPDATE public.projects
                        SET project_key = 'online_lottery',
                            name = COALESCE(NULLIF(name, ''), '线上彩票项目'),
                            schema_name = 'project_online_lottery'
                        WHERE project_key = 'default'
                        """
                    )
                )
                # Sync cursors
                conn.execute(
                    text("UPDATE public.project_sync_state SET project_key='online_lottery' WHERE project_key='default'")
                )
                # Aggregator tables best-effort remap
                conn.execute(text('CREATE SCHEMA IF NOT EXISTS "aggregator"'))
                for t in ["documents_agg", "market_metric_points_agg", "price_observations_agg"]:
                    exists = conn.execute(text(f"SELECT to_regclass('aggregator.{t}') IS NOT NULL")).scalar()
                    if exists:
                        conn.execute(
                            text(
                                f'UPDATE aggregator."{t}" SET project_key = \'online_lottery\' WHERE project_key = \'default\''
                            )
                        )

            count = conn.execute(text("SELECT COUNT(*) FROM public.projects")).scalar() or 0
            if int(count) == 0:
                # Bootstrap a first project if none exists yet (generic business survey).
                conn.execute(
                    text(
                        """
                        INSERT INTO public.projects(project_key, name, schema_name, enabled, is_active, created_at, updated_at)
                        VALUES (:project_key, :name, :schema_name, true, true, now(), now())
                        """
                    ),
                    {
                        "project_key": "business_survey",
                        "name": "商业调查",
                        "schema_name": "project_business_survey",
                    },
                )

            # If tenant tables were previously created in public schema, move them into
            # the first project schema (legacy migration only).
            has_public_docs = conn.execute(text("SELECT to_regclass('public.documents') IS NOT NULL")).scalar()
            has_target_docs = conn.execute(text("SELECT to_regclass('project_online_lottery.documents') IS NOT NULL")).scalar()
            if has_public_docs and not has_target_docs:
                conn.execute(text('CREATE SCHEMA IF NOT EXISTS "project_online_lottery"'))
                tenant_tables = [
                    "sources",
                    "documents",
                    "market_stats",
                    "config_states",
                    "embeddings",
                    "etl_job_runs",
                    "search_history",
                    "llm_service_configs",
                    "topics",
                    "ingest_channels",
                    "source_library_items",
                    "market_metric_points",
                    "products",
                    "price_observations",
                ]
                for t in tenant_tables:
                    conn.execute(text(f'ALTER TABLE IF EXISTS public."{t}" SET SCHEMA "project_online_lottery"'))

                # Move common id sequences if they exist (best-effort).
                for t in tenant_tables:
                    conn.execute(text(f'ALTER SEQUENCE IF EXISTS public."{t}_id_seq" SET SCHEMA "project_online_lottery"'))
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("app").warning("failed to bootstrap projects: %s", exc)


@app.on_event("startup")
def _ensure_all_project_schemas_ready() -> None:
    """
    Backfill tenant tables for existing projects.

    Some schemas may have been created before table initialization logic existed.
    Ensure each enabled project schema has all tenant tables to prevent runtime 500s.
    """
    tenant_tables = [
        Source.__table__,
        Document.__table__,
        MarketStat.__table__,
        ConfigState.__table__,
        Embedding.__table__,
        EtlJobRun.__table__,
        SearchHistory.__table__,
        LlmServiceConfig.__table__,
        Topic.__table__,
        IngestChannel.__table__,
        SourceLibraryItem.__table__,
        MarketMetricPoint.__table__,
        Product.__table__,
        PriceObservation.__table__,
    ]
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text("SELECT project_key, schema_name FROM public.projects WHERE enabled = true")
            ).fetchall()
            for project_key, schema_name in rows:
                if not schema_name:
                    continue
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
                # Use schema-only search path so checkfirst does not falsely match public tables.
                conn.execute(text(f'SET search_path TO "{schema_name}"'))
                Base.metadata.create_all(bind=conn, tables=tenant_tables, checkfirst=True)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("app").warning("failed to ensure project schemas ready: %s", exc)


@app.on_event("startup")
def _sync_llm_prompts_from_files() -> None:
    """Sync LLM prompts from llm_prompts/*.yaml into each project's DB."""
    try:
        from scripts.sync_llm_prompts import sync_prompts

        prompts_dir = Path(__file__).resolve().parent.parent / "llm_prompts"
        if (prompts_dir / "default.yaml").exists():
            n = sync_prompts()
            logging.getLogger("app").info("LLM prompts synced: %d configs", n)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("app").warning("LLM prompts sync failed: %s", exc)


@app.on_event("startup")
def _ensure_shared_library_tables_ready() -> None:
    """Ensure source library shared tables exist in public schema."""
    shared_tables = [
        SharedIngestChannel.__table__,
        SharedSourceLibraryItem.__table__,
    ]
    try:
        with engine.begin() as conn:
            conn.execute(text('SET search_path TO "public"'))
            Base.metadata.create_all(bind=conn, tables=shared_tables, checkfirst=True)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("app").warning("failed to ensure shared source-library tables ready: %s", exc)

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


@app.get("/admin.html", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/dashboard.html", response_class=HTMLResponse)
def dashboard_page(request: Request):
    """数据可视化仪表盘页面"""
    try:
        return templates.TemplateResponse("dashboard.html", {"request": request})
    except Exception as e:
        logging.getLogger("app").error(f"Failed to load dashboard.html: {e}")
        logging.getLogger("app").error(f"Template directory: {TEMPLATE_DIR}")
        logging.getLogger("app").error(f"Dashboard file exists: {(TEMPLATE_DIR / 'dashboard.html').exists()}")
        raise


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_redirect(request: Request):
    """重定向 /dashboard 到 /dashboard.html"""
    return RedirectResponse(url="/dashboard.html", status_code=301)


@app.get("/app.html", response_class=HTMLResponse)
def app_page(request: Request):
    """主应用页面（带侧边栏）"""
    return templates.TemplateResponse("app.html", {"request": request})


@app.get("/app", response_class=HTMLResponse)
def app_redirect(request: Request):
    """重定向 /app 到 /app.html"""
    return RedirectResponse(url="/app.html", status_code=301)


@app.get("/data-dashboard.html", response_class=HTMLResponse)
def data_dashboard_page(request: Request):
    """数据仪表盘页面（市场数据与舆论数据）"""
    return templates.TemplateResponse("data-dashboard.html", {"request": request})


@app.get("/backend-dashboard.html", response_class=HTMLResponse)
def backend_dashboard_page(request: Request):
    """后端数据仪表盘页面（系统监控）"""
    return templates.TemplateResponse("backend-dashboard.html", {"request": request})


@app.get("/policy-dashboard.html", response_class=HTMLResponse)
def policy_dashboard_page(request: Request):
    """政策可视化仪表盘页面"""
    return templates.TemplateResponse("policy-dashboard.html", {"request": request})


@app.get("/policy-state-detail.html", response_class=HTMLResponse)
def policy_state_detail_page(request: Request):
    """州级政策详情页面"""
    return templates.TemplateResponse("policy-state-detail.html", {"request": request})


@app.get("/policy-tracking.html", response_class=HTMLResponse)
def policy_tracking_page(request: Request):
    """政策追踪页面"""
    return templates.TemplateResponse("policy-tracking.html", {"request": request})


@app.get("/market-data-visualization.html", response_class=HTMLResponse)
def market_data_visualization_page(request: Request):
    """市场数据可视化页面"""
    try:
        return templates.TemplateResponse("market-data-visualization.html", {"request": request})
    except Exception as e:
        logging.getLogger("app").error(f"Failed to load market-data-visualization.html: {e}")
        logging.getLogger("app").error(f"Template directory: {TEMPLATE_DIR}")
        logging.getLogger("app").error(f"File exists: {(TEMPLATE_DIR / 'market-data-visualization.html').exists()}")
        raise


@app.get("/social-media-visualization.html", response_class=HTMLResponse)
def social_media_visualization_page(request: Request):
    """社交媒体数据可视化页面"""
    try:
        return templates.TemplateResponse("social-media-visualization.html", {"request": request})
    except Exception as e:
        logging.getLogger("app").error(f"Failed to load social-media-visualization.html: {e}")
        logging.getLogger("app").error(f"Template directory: {TEMPLATE_DIR}")
        logging.getLogger("app").error(f"File exists: {(TEMPLATE_DIR / 'social-media-visualization.html').exists()}")
        raise


@app.get("/policy-visualization.html", response_class=HTMLResponse)
def policy_visualization_page(request: Request):
    """政策可视化页面"""
    try:
        return templates.TemplateResponse("policy-visualization.html", {"request": request})
    except Exception as e:
        logging.getLogger("app").error(f"Failed to load policy-visualization.html: {e}")
        logging.getLogger("app").error(f"Template directory: {TEMPLATE_DIR}")
        logging.getLogger("app").error(f"File exists: {(TEMPLATE_DIR / 'policy-visualization.html').exists()}")
        raise


@app.get("/graph.html", response_class=HTMLResponse)
def graph_page(request: Request):
    """Unified graph visualization page (policy/social/market)"""
    try:
        return templates.TemplateResponse("graph.html", {"request": request})
    except Exception as e:
        logging.getLogger("app").error(f"Failed to load graph.html: {e}")
        raise


@app.get("/policy-graph.html", response_class=RedirectResponse)
def policy_graph_page(request: Request):
    """Redirect to unified graph page"""
    return RedirectResponse(url="/graph.html?type=policy", status_code=302)


@app.get("/social-media-graph.html", response_class=RedirectResponse)
def social_media_graph_page(request: Request):
    """Redirect to unified graph page"""
    return RedirectResponse(url="/graph.html?type=social", status_code=302)

@app.get("/project-management.html", response_class=HTMLResponse)
def project_management_page(request: Request):
    """项目管理页面"""
    return templates.TemplateResponse("project-management.html", {"request": request})


@app.get("/process-management.html", response_class=HTMLResponse)
def process_management_page(request: Request):
    """进程管理页面"""
    return templates.TemplateResponse("process-management.html", {"request": request})


@app.get("/source-library-management.html", response_class=HTMLResponse)
def source_library_management_page(request: Request):
    """信息源库管理页面"""
    return templates.TemplateResponse("source-library-management.html", {"request": request})


@app.get("/api/v1/maps/usa")
def get_usa_map() -> JSONResponse:
    """提供美国地图GeoJSON供前端使用。"""
    if not USA_MAP_PATH.exists():
        raise HTTPException(status_code=404, detail="USA map resource not found")
    try:
        with USA_MAP_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="USA map resource invalid") from exc


# Mount API routers (placeholders; will be populated as modules are implemented)
try:
    from .api import router as api_router  # type: ignore

    app.include_router(api_router, prefix="/api/v1")
except Exception:
    # Safe to skip during initial bootstrapping when modules are empty
    pass


