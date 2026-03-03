import logging
import os
import time
import uuid
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .contracts.errors import ErrorCode, map_exception_to_error, map_status_to_error_code
from .contracts.responses import ApiMetaModel, fail, ok
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
_REQUEST_LOGGER = logging.getLogger("app.request")
_ERROR_LOGGER = logging.getLogger("app.error")
_API_PREFIX = "/api/v1/"
_API_CONTRACT_EXEMPT_PATHS = {"/api/v1/health", "/api/v1/health/deep"}


def _is_contract_api_path(path: str) -> bool:
    return path.startswith(_API_PREFIX) and path not in _API_CONTRACT_EXEMPT_PATHS


def _build_error_payload(
    request: Request,
    code: ErrorCode,
    message: str,
    *,
    details: dict | None = None,
) -> dict:
    project_key = (
        (request.headers.get("X-Project-Key") or "").strip()
        or (request.query_params.get("project_key") or "").strip()
        or None
    )
    request_id = (request.headers.get("X-Request-Id") or "").strip() or None
    meta = ApiMetaModel(trace_id=request_id, project_key=project_key)
    return fail(code, message, details=details, meta=meta)


def _with_legacy_detail_alias(payload: dict) -> dict:
    """Transitional compatibility for callers still reading body.detail.error."""
    if "detail" in payload:
        return payload
    error_obj = payload.get("error")
    if not isinstance(error_obj, dict):
        return payload
    cloned = dict(payload)
    cloned["detail"] = {"error": error_obj, "message": error_obj.get("message")}
    return cloned


def _extract_http_exception_content(request: Request, exc: HTTPException) -> tuple[dict, ErrorCode]:
    detail = exc.detail
    if isinstance(detail, dict):
        if {"status", "data", "error", "meta"}.issubset(detail.keys()):
            error_obj = detail.get("error")
            if isinstance(error_obj, dict):
                code_text = str(error_obj.get("code") or "")
                for candidate in ErrorCode:
                    if candidate.value == code_text:
                        return _with_legacy_detail_alias(detail), candidate
            code = map_status_to_error_code(exc.status_code)
            return _with_legacy_detail_alias(detail), code
        message = str(detail.get("message") or detail.get("detail") or "Request failed")
        code = map_status_to_error_code(exc.status_code)
        payload = _build_error_payload(request, code, message, details=detail)
        return _with_legacy_detail_alias(payload), code
    code = map_status_to_error_code(exc.status_code)
    message = str(detail) if detail else "Request failed"
    payload = _build_error_payload(request, code, message)
    return _with_legacy_detail_alias(payload), code


def _is_already_envelope(payload: object) -> bool:
    return (
        isinstance(payload, dict)
        and {"status", "data", "error", "meta"}.issubset(payload.keys())
    )


def _maybe_wrap_success_json_response(
    request: Request,
    response: Response,
    *,
    request_id: str,
    project_key: str,
) -> Response:
    if not _is_contract_api_path(request.url.path):
        return response
    if response.status_code < 200 or response.status_code >= 300:
        return response

    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        return response

    body = getattr(response, "body", None)
    if not body:
        return response

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return response

    if _is_already_envelope(payload):
        return response

    meta = ApiMetaModel(trace_id=request_id, project_key=project_key)
    wrapped = ok(payload, meta=meta)
    wrapped_response = JSONResponse(status_code=response.status_code, content=wrapped)
    for k, v in response.headers.items():
        lk = k.lower()
        if lk in {"content-length", "content-type"}:
            continue
        wrapped_response.headers[k] = v
    return wrapped_response

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


def _resolve_request_project_context(request: Request) -> tuple[str, str, bool]:
    """Resolve project key source for observability and fallback warning."""
    header_key = (request.headers.get("X-Project-Key") or "").strip()
    if header_key:
        return header_key, "header", False
    query_key = (request.query_params.get("project_key") or "").strip()
    if query_key:
        return query_key, "query", False
    fallback = _get_active_project_key_fallback() or settings.active_project_key
    return fallback, "fallback", True

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
    project_key, project_key_source, project_key_is_fallback = _resolve_request_project_context(request)
    request_id = (request.headers.get("X-Request-Id") or "").strip() or str(uuid.uuid4())
    start = time.perf_counter()
    with bind_project(project_key):
        response: Response = await call_next(request)
    response = _maybe_wrap_success_json_response(
        request,
        response,
        request_id=request_id,
        project_key=project_key,
    )
    elapsed = time.perf_counter() - start
    endpoint = request.url.path
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Project-Key-Resolved"] = project_key
    response.headers["X-Project-Key-Source"] = project_key_source
    if project_key_is_fallback:
        response.headers["X-Project-Key-Warning"] = "fallback_used"
    REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
    REQUEST_LATENCY.labels(endpoint).observe(elapsed)
    if project_key_is_fallback:
        _REQUEST_LOGGER.warning(
            "project_key_fallback_used path=%s resolved_project_key=%s request_id=%s",
            endpoint,
            project_key,
            request_id,
        )
    error_code = (response.headers.get("X-Error-Code") or "").strip() or "-"
    _REQUEST_LOGGER.info(
        "request path=%s method=%s status=%s latency=%.4f request_id=%s project_key=%s project_key_source=%s error_code=%s",
        endpoint,
        request.method,
        response.status_code,
        elapsed,
        request_id,
        project_key,
        project_key_source,
        error_code,
    )
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if not _is_contract_api_path(request.url.path):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    payload, code = _extract_http_exception_content(request, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers={"X-Error-Code": code.value},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    _ERROR_LOGGER.exception("unhandled_exception path=%s", request.url.path)
    if not _is_contract_api_path(request.url.path):
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
    code, message, details = map_exception_to_error(exc)
    payload = _with_legacy_detail_alias(_build_error_payload(request, code, message, details=details))
    return JSONResponse(
        status_code=500,
        content=payload,
        headers={"X-Error-Code": code.value},
    )


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


# Mount API routers.
from .api import router as api_router  # type: ignore

app.include_router(api_router, prefix="/api/v1")
