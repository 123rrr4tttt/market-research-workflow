import logging
import os
import time
import uuid
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from prometheus_client import Counter, Histogram, REGISTRY, generate_latest, CONTENT_TYPE_LATEST

from .contracts.errors import ErrorCode, map_exception_to_error, map_status_to_error_code
from .contracts.responses import ApiMetaModel, fail, ok
from .composition.production import is_production_environment, production_metrics_label
from .settings.config import get_effective_project_key_enforcement_mode, settings
from .models.base import engine, get_db_pool_status
from .release_identity import RELEASE_VERSION
from .production_observability import (
    install_production_observability,
    production_observability_config_from_settings,
)
from .production_observability import http as production_http
from .production_observability.health import build_runtime_health_snapshot
from .services.search.es_client import get_es_client
from .services.projects import bind_project
from .services.codex_oauth import (
    TokenSinkClaimsContext,
    codex_cookie_name,
    codex_oauth_enabled,
    get_session,
    get_token_sink_claims_context,
    has_valid_token_sink,
)
from .services.request_identity import (
    RequestActorContext,
    actor_id_from_secret,
    authenticated_actor_context,
    legacy_actor_id_from_request,
    set_request_actor_context,
)
from .startup_hooks import register_startup_hooks
from .web_ui_routes import register_ui_routes

############################
# Logging configuration
############################

# Stable service metadata for observability
_SERVICE_NAME = os.getenv("SERVICE_NAME", "market-intel-api")
_SERVICE_VERSION = os.getenv("SERVICE_VERSION", RELEASE_VERSION)
_DEPLOY_COLOR = os.getenv("DEPLOY_COLOR", os.getenv("COLOR", "blue"))

class _StaticContextFilter(logging.Filter):
    """Inject stable fields into all log records.

    Ensures formatting never breaks even for third‑party loggers.
    """

    def __init__(self, service: str, env_value: str, version: str, deploy_color: str) -> None:
        super().__init__()
        self._service = service
        self._env_value = env_value
        self._version = version
        self._deploy_color = deploy_color

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if not hasattr(record, "service"):
            record.service = self._service
        if not hasattr(record, "env"):
            record.env = self._env_value
        if not hasattr(record, "version"):
            record.version = self._version
        if not hasattr(record, "deploy_color"):
            record.deploy_color = self._deploy_color
        return True

# Ensure every log record has the static fields, including third-party loggers.
_BASE_RECORD_FACTORY = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs):
    record = _BASE_RECORD_FACTORY(*args, **kwargs)
    if not hasattr(record, "service"):
        record.service = _SERVICE_NAME
    if not hasattr(record, "env"):
        record.env = getattr(settings, "env", "dev")
    if not hasattr(record, "version"):
        record.version = _SERVICE_VERSION
    if not hasattr(record, "deploy_color"):
        record.deploy_color = _DEPLOY_COLOR
    return record


logging.setLogRecordFactory(_record_factory)

# Base configuration
logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s %(levelname)s %(name)s "
        "service=%(service)s env=%(env)s version=%(version)s deploy_color=%(deploy_color)s "
        "%(message)s"
    ),
)

# Add context filter on root so all child loggers inherit it
logging.getLogger().addFilter(
    _StaticContextFilter(
        service=_SERVICE_NAME,
        env_value=getattr(settings, "env", "dev"),
        version=_SERVICE_VERSION,
        deploy_color=_DEPLOY_COLOR,
    )
)

# Create FastAPI app
app = FastAPI(title="Market Intel API", version=_SERVICE_VERSION)

@app.on_event("startup")
def _validate_production_composition() -> None:
    """Install the existing production authority ports before serving requests."""
    from .composition.production import validate_production_startup
    from .composition.production_runtime import build_production_runtime_bindings

    if not is_production_environment(settings):
        return
    runtime_id = str(settings.production_observability_runtime_id or "").strip()
    if not runtime_id:
        raise RuntimeError("production observability runtime_id is required")
    observability_config = production_observability_config_from_settings(
        settings,
        release_version=RELEASE_VERSION,
    )
    runtime = build_production_runtime_bindings(engine, settings)
    validate_production_startup(
        settings, routes=app.routes, runtime_bindings=runtime
    )
    app.state.production_runtime_bindings = runtime
    install_production_observability(app, observability_config)


# Cache active project for fallback routing
_ACTIVE_PROJECT_CACHE_KEY: str | None = None
_ACTIVE_PROJECT_CACHE_TS: float = 0.0
_REQUEST_LOGGER = logging.getLogger("app.request")
_ERROR_LOGGER = logging.getLogger("app.error")
_API_PREFIX = "/api/v1/"
_API_CONTRACT_EXEMPT_PATHS = {"/api/v1/health", "/api/v1/health/deep"}
_ZERO_TRACE_ID = "0" * 32
_ZERO_PARENT_ID = "0" * 16


def _is_contract_api_path(path: str) -> bool:
    return path.startswith(_API_PREFIX) and path not in _API_CONTRACT_EXEMPT_PATHS


def _is_lower_hex(value: str, length: int) -> bool:
    return len(value) == length and all(char in "0123456789abcdef" for char in value)


def _trace_id_from_traceparent(value: str | None) -> str | None:
    if not value:
        return None
    parts = value.strip().split("-")
    if len(parts) != 4:
        return None
    version, trace_id, parent_id, flags = (part.lower() for part in parts)
    if not _is_lower_hex(version, 2):
        return None
    if not _is_lower_hex(trace_id, 32) or trace_id == _ZERO_TRACE_ID:
        return None
    if not _is_lower_hex(parent_id, 16) or parent_id == _ZERO_PARENT_ID:
        return None
    if not _is_lower_hex(flags, 2):
        return None
    return trace_id


def _resolve_request_trace_id(request: Request, request_id: str | None = None) -> str | None:
    header_trace_id = (request.headers.get("X-Trace-Id") or "").strip()
    if header_trace_id:
        return header_trace_id
    traceparent_trace_id = _trace_id_from_traceparent(request.headers.get("traceparent"))
    if traceparent_trace_id:
        return traceparent_trace_id
    if request_id:
        return request_id
    return None


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
    trace_id = getattr(request.state, "trace_id", None) or _resolve_request_trace_id(request, request_id)
    meta = ApiMetaModel(trace_id=trace_id, project_key=project_key)
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


def _enrich_existing_envelope_meta(
    payload: dict,
    *,
    trace_id: str,
    project_key: str,
) -> dict:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return payload

    updated_meta = dict(meta)
    if updated_meta.get("trace_id") is None and trace_id:
        updated_meta["trace_id"] = trace_id
    if updated_meta.get("project_key") is None and project_key:
        updated_meta["project_key"] = project_key
    return {**payload, "meta": updated_meta}


def _response_chunk_bytes(chunk) -> bytes:
    if isinstance(chunk, str):
        return chunk.encode("utf-8")
    return bytes(chunk)


def _preserve_response_metadata(source: Response, target: Response) -> None:
    target.raw_headers = [
        (key, value)
        for key, value in source.raw_headers
        if key.lower() != b"content-length"
    ] + [(b"content-length", str(len(target.body)).encode("latin-1"))]
    target.background = source.background


async def _materialize_success_json_response(
    request: Request,
    response: Response,
) -> Response:
    if not _is_contract_api_path(request.url.path):
        return response
    if response.status_code < 200 or response.status_code >= 300:
        return response

    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        return response
    if getattr(response, "body", None) is not None:
        return response

    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        return response

    chunks = []
    async for chunk in body_iterator:
        chunks.append(_response_chunk_bytes(chunk))
    materialized = Response(
        content=b"".join(chunks),
        status_code=response.status_code,
    )
    _preserve_response_metadata(response, materialized)
    return materialized


def _maybe_wrap_success_json_response(
    request: Request,
    response: Response,
    *,
    request_id: str,
    trace_id: str,
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
        enriched_payload = _enrich_existing_envelope_meta(
            payload,
            trace_id=trace_id,
            project_key=project_key,
        )
        if enriched_payload is payload:
            return response
        enriched_response = JSONResponse(
            status_code=response.status_code,
            content=enriched_payload,
        )
        _preserve_response_metadata(response, enriched_response)
        return enriched_response

    meta = ApiMetaModel(trace_id=trace_id, project_key=project_key)
    wrapped = ok(payload, meta=meta)
    wrapped_response = JSONResponse(status_code=response.status_code, content=wrapped)
    _preserve_response_metadata(response, wrapped_response)
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


_ENDPOINT_OWNED_PROJECT_CONTEXT_PATHS = frozenset(
    {
        "/api/v1/agent-chat/turn",
        "/api/v1/agent-chat/turn/stream",
        "/api/v1/agent-batch/nl-command",
        "/api/v1/agent-batch/nl-command/direct",
    }
)


def _uses_endpoint_owned_project_context(path: str) -> bool:
    if path in _ENDPOINT_OWNED_PROJECT_CONTEXT_PATHS:
        return True
    return (
        path.startswith("/api/v1/agent-chat/approvals/")
        and path.endswith("/continue")
    )


def _resolve_request_project_context(request: Request) -> tuple[str, str, bool]:
    """Resolve project key source for observability and fallback warning."""
    header_key = (request.headers.get("X-Project-Key") or "").strip()
    if header_key:
        return header_key, "header", False
    query_key = (request.query_params.get("project_key") or "").strip()
    if query_key:
        return query_key, "query", False
    if _uses_endpoint_owned_project_context(request.url.path):
        return "", "endpoint_payload", False
    fallback = _get_active_project_key_fallback() or settings.active_project_key
    return fallback, "fallback", True


def _parse_codex_auth_tokens() -> set[str]:
    raw = str(getattr(settings, "codex_auth_tokens", "") or "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _is_codex_protected_path(path: str) -> bool:
    if not bool(getattr(settings, "codex_auth_enabled", False)):
        return False
    raw_prefixes = str(getattr(settings, "codex_auth_protected_prefixes", "") or "")
    prefixes = [item.strip() for item in raw_prefixes.split(",") if item.strip()]
    if not prefixes:
        return False
    return any(path.startswith(prefix) for prefix in prefixes)


def _extract_codex_token(request: Request) -> str | None:
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    custom_header = (request.headers.get("X-Codex-Auth") or "").strip()
    return custom_header or None


def _has_valid_codex_oauth_session(request: Request) -> bool:
    sid = (request.cookies.get(codex_cookie_name()) or "").strip()
    if not sid:
        return has_valid_token_sink()
    return get_session(sid) is not None or has_valid_token_sink()


def _actor_from_verified_claims(
    claims: dict | None,
    *,
    request: Request,
    actor_source: str,
    actor_auth_mode: str,
    actor_metadata: dict[str, object] | None = None,
) -> RequestActorContext | None:
    clean_claims = claims if isinstance(claims, dict) else {}
    subject = str(clean_claims.get("sub") or "").strip()
    email = str(clean_claims.get("email") or "").strip()
    email_verified = clean_claims.get("email_verified") is True
    if subject:
        actor_id = subject
    elif email and email_verified:
        actor_id = actor_id_from_secret("codex_oauth_email", email)
    else:
        return None
    return authenticated_actor_context(
        actor_id=actor_id,
        source=actor_source,
        auth_mode=actor_auth_mode,
        legacy_actor_id=legacy_actor_id_from_request(request),
        actor_metadata=actor_metadata,
    )


def _token_sink_actor_metadata(claims_context: TokenSinkClaimsContext) -> dict[str, object]:
    metadata = claims_context.profile_metadata()
    allowed_fields = ("profile_name", "profile_name_hash", "expires_at", "fallback_used")
    return {field: metadata[field] for field in allowed_fields if field in metadata}


def _resolve_codex_oauth_actor_context(request: Request) -> RequestActorContext | None:
    sid = (request.cookies.get(codex_cookie_name()) or "").strip()
    if sid:
        session = get_session(sid)
        if session is not None:
            claims_actor = _actor_from_verified_claims(
                session.claims,
                request=request,
                actor_source="authenticated_oauth_session_claims",
                actor_auth_mode="codex_oauth_session_oidc_claims",
            )
            if claims_actor is not None:
                return claims_actor
            return authenticated_actor_context(
                actor_id=actor_id_from_secret("codex_oauth_session", session.session_id),
                source="authenticated_oauth_session",
                auth_mode="codex_oauth_session",
                legacy_actor_id=legacy_actor_id_from_request(request),
            )

    claims_context = get_token_sink_claims_context()
    if claims_context.has_valid_token_sink and claims_context.from_token_sink:
        claims_actor = _actor_from_verified_claims(
            claims_context.claims,
            request=request,
            actor_source="authenticated_oauth_token_sink_claims",
            actor_auth_mode="codex_oauth_token_sink_oidc_claims",
            actor_metadata=_token_sink_actor_metadata(claims_context),
        )
        if claims_actor is not None:
            return claims_actor

        return authenticated_actor_context(
            actor_id="codex_oauth_token_sink",
            source="authenticated_oauth_token_sink",
            auth_mode="codex_oauth_token_sink",
            legacy_actor_id=legacy_actor_id_from_request(request),
            actor_metadata=_token_sink_actor_metadata(claims_context),
        )

    if not has_valid_token_sink():
        return None

    return authenticated_actor_context(
        actor_id="codex_oauth_token_sink",
        source="authenticated_oauth_token_sink",
        auth_mode="codex_oauth_token_sink",
        legacy_actor_id=legacy_actor_id_from_request(request),
    )


def _static_codex_token_actor(request: Request, token: str) -> RequestActorContext:
    return authenticated_actor_context(
        actor_id=actor_id_from_secret("actor:codex-token", token),
        source="authenticated_codex_token",
        auth_mode="codex_static_token",
        legacy_actor_id=legacy_actor_id_from_request(request),
    )


def _build_codex_auth_error(request: Request, *, reason: str) -> JSONResponse:
    payload = _build_error_payload(
        request,
        ErrorCode.INVALID_INPUT,
        "codex auth required",
        details={"category": "codex_auth", "reason_code": reason},
    )
    return JSONResponse(
        status_code=401,
        content=_with_legacy_detail_alias(payload),
        headers={"X-Error-Code": ErrorCode.INVALID_INPUT.value},
    )

# Frontend archive cleanup: backend runtime no longer depends on the legacy
# template frontend directory. Only shared backend-owned assets remain here.
APP_ROOT = Path(__file__).resolve().parent
USA_MAP_PATH = APP_ROOT / "assets" / "maps" / "USA.json"
register_startup_hooks(app)

def _get_or_create_counter(name: str, documentation: str, labelnames: list[str]) -> Counter:
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Counter(name, documentation, labelnames)


def _get_or_create_histogram(name: str, documentation: str, labelnames: list[str]) -> Histogram:
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Histogram(name, documentation, labelnames)


REQUEST_COUNT = _get_or_create_counter(
    "market_api_requests_total",
    "API request count",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = _get_or_create_histogram(
    "market_api_request_latency_seconds",
    "API request latency",
    ["endpoint"],
)

_LEGACY_ROUTE_REWRITES: dict[str, str] = {
    "/api/v1/ingest/social/sentiment": "/api/v1/ingest/data-api",
}


@app.middleware("http")
async def legacy_route_rewrite_middleware(request: Request, call_next):
    legacy_path = request.scope.get("path") or ""
    target_path = _LEGACY_ROUTE_REWRITES.get(str(legacy_path))
    rewritten = False
    if target_path:
        request.scope["path"] = target_path
        request.scope["raw_path"] = target_path.encode("utf-8")
        rewritten = True
    response: Response = await call_next(request)
    if rewritten:
        response.headers["X-Legacy-Route-Rewrite"] = f"{legacy_path}->{target_path}"
    return response


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    controller = getattr(app.state, "production_observability_r7", None)
    production_runtime = is_production_environment()
    observe_http = production_runtime or controller is not None
    authenticated_actor: RequestActorContext | None = None
    auth_error_response: Response | None = None
    if _is_codex_protected_path(request.url.path):
        valid_tokens = _parse_codex_auth_tokens()
        token = _extract_codex_token(request)
        if token and token in valid_tokens:
            authenticated_actor = _static_codex_token_actor(request, token)
        else:
            authenticated_actor = _resolve_codex_oauth_actor_context(request)
            if authenticated_actor is None:
                if token:
                    auth_error_response = _build_codex_auth_error(
                        request, reason="invalid_token"
                    )
                elif valid_tokens:
                    auth_error_response = _build_codex_auth_error(
                        request, reason="missing_token"
                    )
                elif codex_oauth_enabled():
                    auth_error_response = _build_codex_auth_error(
                        request, reason="missing_oauth_session"
                    )
                else:
                    auth_error_response = _build_codex_auth_error(
                        request, reason="codex_auth_tokens_not_configured"
                    )

    if authenticated_actor is not None:
        set_request_actor_context(request, authenticated_actor)

    if auth_error_response is None:
        project_key, project_key_source, project_key_is_fallback = _resolve_request_project_context(request)
    else:
        project_key, project_key_source, project_key_is_fallback = "", "auth_rejected", False
    effective_project_key_mode = get_effective_project_key_enforcement_mode()
    request_id = (request.headers.get("X-Request-Id") or "").strip() or str(uuid.uuid4())
    trace_id = _resolve_request_trace_id(request, request_id) or request_id
    start = time.perf_counter()
    request.state.request_id = request_id
    request.state.trace_id = trace_id
    request.state.project_key_resolved = project_key
    request.state.project_key_source = project_key_source
    request.state.project_key_is_fallback = project_key_is_fallback
    if auth_error_response is not None:
        response: Response = auth_error_response
    elif project_key:
        with bind_project(project_key):
            response = await call_next(request)
    else:
        response = await call_next(request)
    response = await _materialize_success_json_response(request, response)
    response = _maybe_wrap_success_json_response(
        request,
        response,
        request_id=request_id,
        trace_id=trace_id,
        project_key=project_key,
    )
    elapsed = time.perf_counter() - start
    endpoint = request.url.path
    if request.scope.get("route") is None:
        request.scope["route"] = next(
            (
                route
                for route in app.routes
                if getattr(route, "path", None) == request.url.path
                and request.method in getattr(route, "methods", ())
            ),
            None,
        )
    metric_labels = production_metrics_label(request)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Trace-Id"] = trace_id
    response.headers["X-Project-Key-Resolved"] = project_key
    response.headers["X-Project-Key-Source"] = project_key_source
    response.headers["X-Project-Key-Enforcement-Mode"] = effective_project_key_mode
    response.headers["X-Project-Key-Fallback-Allowed"] = "false" if effective_project_key_mode == "require" else "true"
    if project_key_is_fallback:
        response.headers["X-Project-Key-Warning"] = "fallback_used"
    if project_key_is_fallback:
        _REQUEST_LOGGER.warning(
            "event=project_key_fallback http_target=%s project_key=%s request_id=%s enforcement_mode=%s fallback_allowed=%s",
            endpoint,
            project_key,
            request_id,
            effective_project_key_mode,
            "false" if effective_project_key_mode == "require" else "true",
        )
    error_code = (response.headers.get("X-Error-Code") or "").strip() or "-"
    duration_ms = int(round(elapsed * 1000))
    http_target = endpoint  # path only to avoid leaking query secrets
    # Standardized request log keys
    _REQUEST_LOGGER.info(
        "request request_id=%s project_key=%s http_method=%s http_target=%s http_status=%s duration_ms=%d error_code=%s",
        request_id,
        project_key,
        request.method,
        http_target,
        response.status_code,
        duration_ms,
        error_code,
    )
    if observe_http and production_http.is_sse_response(response):
        production_http.wrap_stream_response(
            request,
            response,
            finalize=lambda terminal_outcome: production_http.finalize_request_metrics(
                request=request,
                response=response,
                request_id=request_id,
                endpoint=endpoint,
                metric_labels=metric_labels,
                elapsed=time.perf_counter() - start,
                production_runtime=observe_http,
                controller=controller,
                terminal_outcome=terminal_outcome,
            ),
        )
    else:
        production_http.finalize_request_metrics(
            request=request,
            response=response,
            request_id=request_id,
            endpoint=endpoint,
            metric_labels=metric_labels,
            elapsed=elapsed,
            production_runtime=observe_http,
            controller=controller,
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


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    if not _is_contract_api_path(request.url.path):
        return JSONResponse(status_code=422, content={"detail": exc.errors()})
    payload = _with_legacy_detail_alias(
        _build_error_payload(
            request,
            ErrorCode.INVALID_INPUT,
            "Request validation failed",
            details={"errors": exc.errors()},
        )
    )
    return JSONResponse(
        status_code=422,
        content=payload,
        headers={"X-Error-Code": ErrorCode.INVALID_INPUT.value},
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
def deep_health_check(request: Request) -> dict:
    """Deep health check: DB + pool + Elasticsearch connectivity and simple latency probes."""
    checks: dict[str, str] = {}
    details: dict[str, object] = {}
    pool_status: dict[str, object] = {}

    # DB check
    db_start = time.perf_counter()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
        details["database_latency_ms"] = round((time.perf_counter() - db_start) * 1000, 2)
    except Exception as e:  # noqa: BLE001 - report raw for observability at MVP
        checks["database"] = f"error: {type(e).__name__}"

    # DB pool status
    try:
        pool_status = get_db_pool_status()
        details["database_pool"] = pool_status
        checks["database_pool"] = "ok"
        size = int(pool_status.get("size", 0))
        checkedout = int(pool_status.get("checkedout", 0))
        max_overflow = max(0, int(settings.db_pool_max_overflow))
        pool_limit = size + max_overflow
        gate_enabled = bool(settings.deep_health_pool_gate_enabled)
        exhaustion_ratio = float(settings.deep_health_pool_exhaustion_ratio)
        exhaustion_ratio = min(max(exhaustion_ratio, 0.1), 1.0)
        exhaustion_threshold = max(1, int(pool_limit * exhaustion_ratio)) if pool_limit > 0 else 0
        if gate_enabled and pool_limit > 0 and checkedout >= exhaustion_threshold:
            checks["database_pool"] = "error: pool_exhausted"
            details["database_pool_gate"] = {
                "pool_limit": pool_limit,
                "checkedout": checkedout,
                "max_overflow": max_overflow,
                "exhaustion_ratio": exhaustion_ratio,
                "exhaustion_threshold": exhaustion_threshold,
            }
    except Exception as e:  # noqa: BLE001
        checks["database_pool"] = f"error: {type(e).__name__}"

    # ES check
    es_start = time.perf_counter()
    try:
        es = get_es_client()
        ok = es.ping()
        checks["elasticsearch"] = "ok" if ok else "error: ping failed"
        details["elasticsearch_latency_ms"] = round((time.perf_counter() - es_start) * 1000, 2)
    except Exception as e:  # noqa: BLE001
        checks["elasticsearch"] = f"error: {type(e).__name__}"

    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    controller = getattr(app.state, "production_observability_r7", None)
    if controller is not None:
        observation_id = (
            getattr(request.state, "request_id", None)
            or f"deep-health:{uuid.uuid4()}"
        )
        try:
            snapshot = build_runtime_health_snapshot(
                database_connection_status=str(checks.get("database", "error: unavailable")),
                database_pool_status=str(checks.get("database_pool", "error: unavailable")),
                pool_status=pool_status,
                runtime_status={"runtime_mode": settings.env},
                engine=engine,
                settings_obj=settings,
                release_version=RELEASE_VERSION,
                production_runtime=is_production_environment(),
                service_version=_SERVICE_VERSION,
            )
            controller.observe_runtime_health(
                observation_id=observation_id,
                snapshot=snapshot,
            )
        except Exception as exc:  # noqa: BLE001 - health observation cannot replace health output
            _ERROR_LOGGER.warning(
                "runtime health observation failed request_id=%s error_type=%s",
                observation_id,
                type(exc).__name__,
                exc_info=exc,
            )
            try:
                controller.latch_runtime_failure(
                    request_id=f"{observation_id}:runtime-health-observation",
                    reason=f"runtime health observation failed: {type(exc).__name__}",
                )
            except Exception as latch_exc:  # noqa: BLE001 - latching cannot replace health output
                _ERROR_LOGGER.error(
                    "runtime health observation latch failed request_id=%s error_type=%s",
                    observation_id,
                    type(latch_exc).__name__,
                    exc_info=latch_exc,
                )
    return {"status": status, **checks, "details": details}


@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
register_ui_routes(app, usa_map_path=USA_MAP_PATH)


# Mount API routers.
from .api import router as api_router  # type: ignore

app.include_router(api_router, prefix="/api/v1")

# Successor production registry mount: initialize app.state only at startup so
# no database connection or server registry resolver is created at import time.
if str(getattr(settings, "successor_mount_mode", "local_only")).strip().lower() == (
    "production_registry"
):
    from app.successor_runtime.assembly.app_assembly import (
        AuthActorUnresolvedError,
        authenticated_oauth_session_actor_ref,
        authenticated_token_actor_ref,
        initialize_successor_registry_mount,
    )

    def _successor_production_actor_provider(request: Request) -> str:
        token = _extract_codex_token(request)
        if token:
            return authenticated_token_actor_ref(token)
        if _has_valid_codex_oauth_session(request):
            sid = (request.cookies.get(codex_cookie_name()) or "").strip()
            if sid:
                return authenticated_oauth_session_actor_ref(sid)
            return "actor:codex-oauth:token-sink"
        raise AuthActorUnresolvedError(
            "no authenticated actor identity found on successor request"
        )

    @app.on_event("startup")
    def _initialize_successor_registry_mount() -> None:
        initialize_successor_registry_mount(
            app, actor_provider=_successor_production_actor_provider
        )
