from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.celery_app import celery_app

_SENSITIVE_QUERY_KEYS = {"password", "pass", "pwd", "token", "secret", "access_token"}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mask_broker_url(raw_url: Any) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""

    try:
        parsed = urlsplit(text)
        if not parsed.scheme or not parsed.netloc:
            return "***"

        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port is not None else ""
        if parsed.username is not None or parsed.password is not None:
            username = parsed.username or "user"
            userinfo = f"{username}:***"
            netloc = f"{userinfo}@{host}{port}"
        else:
            netloc = f"{host}{port}"

        if parsed.query:
            pairs = parse_qsl(parsed.query, keep_blank_values=True)
            masked_query = urlencode(
                [
                    (k, "***" if str(k or "").lower() in _SENSITIVE_QUERY_KEYS else v)
                    for k, v in pairs
                ]
            )
        else:
            masked_query = ""

        return urlunsplit((parsed.scheme, netloc, parsed.path, masked_query, parsed.fragment))
    except Exception:
        return "***"


def inspect_executor_health(*, app_instance: Any | None = None, inspect_timeout: float = 1.0) -> dict[str, Any]:
    app = app_instance or celery_app
    timeout = float(inspect_timeout) if inspect_timeout and inspect_timeout > 0 else 1.0

    diagnostics: dict[str, Any] = {
        "inspect_timeout_seconds": timeout,
    }
    workers: list[str] = []
    worker_online = False
    ping_payload: Any = None

    broker_url = ""
    try:
        broker_url = getattr(getattr(app, "conf", object()), "broker_url", "") or ""
    except Exception as exc:
        diagnostics["broker_url_error"] = f"{type(exc).__name__}: {exc}"

    try:
        inspector = app.control.inspect(timeout=timeout)
        ping_payload = inspector.ping() if inspector is not None else None
        diagnostics["inspect_ok"] = True
    except Exception as exc:
        diagnostics["inspect_ok"] = False
        diagnostics["error"] = f"{type(exc).__name__}: {exc}"

    if isinstance(ping_payload, dict):
        workers = sorted(str(k) for k in ping_payload.keys())
        worker_online = len(workers) > 0
        diagnostics["ping_response_type"] = "dict"
        diagnostics["worker_count"] = len(workers)
    elif ping_payload is None:
        diagnostics["ping_response_type"] = "none"
        diagnostics["worker_count"] = 0
    else:
        diagnostics["ping_response_type"] = type(ping_payload).__name__
        diagnostics["worker_count"] = 0

    return {
        "worker_online": worker_online,
        "workers": workers,
        "broker_url_masked": _mask_broker_url(broker_url),
        "timestamp": _utcnow_iso(),
        "diagnostics": diagnostics,
    }

