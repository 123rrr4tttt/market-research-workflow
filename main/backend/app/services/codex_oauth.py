from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from app.settings.config import settings


@dataclass(frozen=True)
class CodexSession:
    session_id: str
    access_token: str | None
    token_type: str | None
    scope: str | None
    created_at: int
    expires_at: int


_STATE_LOCK = threading.RLock()
_PENDING_STATES: dict[str, dict[str, Any]] = {}
_ACTIVE_SESSIONS: dict[str, CodexSession] = {}


def codex_oauth_enabled() -> bool:
    return bool(getattr(settings, "codex_oauth_enabled", False))


def codex_cookie_name() -> str:
    name = str(getattr(settings, "codex_oauth_cookie_name", "codex_session") or "").strip()
    return name or "codex_session"


def codex_cookie_secure() -> bool:
    return bool(getattr(settings, "codex_oauth_cookie_secure", False))


def codex_oauth_frontend_success_url() -> str:
    value = str(getattr(settings, "codex_oauth_frontend_success_url", "/") or "").strip()
    return value or "/"


def codex_oauth_frontend_error_url() -> str:
    value = str(getattr(settings, "codex_oauth_frontend_error_url", "/") or "").strip()
    return value or "/"


def build_authorize_url(*, next_url: str | None = None, redirect_uri: str | None = None) -> str:
    cfg = _read_oauth_config()
    _cleanup_expired_state_and_sessions()

    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = _pkce_s256(verifier)
    authorize_redirect_uri = str(redirect_uri or "").strip() or str(cfg["redirect_uri"])

    with _STATE_LOCK:
        _PENDING_STATES[state] = {
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + int(cfg["state_ttl_seconds"]),
            "code_verifier": verifier,
            "redirect_uri": authorize_redirect_uri,
            "next_url": _normalize_next_url(next_url),
        }

    query = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": authorize_redirect_uri,
        "scope": cfg["scope"],
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if cfg["provider"] == "openai":
        query["id_token_add_organizations"] = "true"
        query["codex_cli_simplified_flow"] = "true"
        if cfg["originator"]:
            query["originator"] = cfg["originator"]
    return f"{cfg['authorize_url']}?{urlencode(query)}"


async def exchange_code_to_session(*, code: str, state: str) -> tuple[CodexSession, str]:
    cfg = _read_oauth_config()
    _cleanup_expired_state_and_sessions()

    state_key = str(state or "").strip()
    if not state_key:
        raise ValueError("state is required")

    with _STATE_LOCK:
        pending = _PENDING_STATES.pop(state_key, None)
    if not isinstance(pending, dict):
        raise ValueError("invalid_or_expired_state")

    if int(pending.get("expires_at") or 0) < int(time.time()):
        raise ValueError("state_expired")

    code_verifier = str(pending.get("code_verifier") or "")
    if not code_verifier:
        raise ValueError("state_missing_verifier")

    token_payload = {
        "grant_type": "authorization_code",
        "code": str(code or "").strip(),
        "redirect_uri": str(pending.get("redirect_uri") or "").strip() or cfg["redirect_uri"],
        "client_id": cfg["client_id"],
        "code_verifier": code_verifier,
    }
    if cfg["client_secret"]:
        token_payload["client_secret"] = cfg["client_secret"]

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            cfg["token_url"],
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code >= 400:
        reason = f"token_exchange_failed:{response.status_code}"
        try:
            payload = response.json() if response.content else {}
            if isinstance(payload, dict):
                error_code = str(payload.get("error") or "").strip()
                error_desc = str(payload.get("error_description") or payload.get("message") or "").strip()
                if error_code and error_desc:
                    reason = f"{reason}:{error_code}:{error_desc[:240]}"
                elif error_code:
                    reason = f"{reason}:{error_code}"
        except Exception:
            pass
        raise ValueError(reason)

    data = response.json() if response.content else {}
    access_token = str(data.get("access_token") or "").strip() or None
    token_type = str(data.get("token_type") or "").strip() or None
    scope = str(data.get("scope") or "").strip() or cfg["scope"]
    expires_in = _safe_int(data.get("expires_in"), default=3600)
    now = int(time.time())

    sid = secrets.token_urlsafe(32)
    session = CodexSession(
        session_id=sid,
        access_token=access_token,
        token_type=token_type,
        scope=scope,
        created_at=now,
        expires_at=now + max(300, min(expires_in, 86400 * 7)),
    )
    with _STATE_LOCK:
        _ACTIVE_SESSIONS[sid] = session

    if bool(getattr(settings, "codex_oauth_token_sink_enabled", True)):
        persist_token_sink(
            {
                "provider": cfg["provider"],
                "access_token": access_token,
                "refresh_token": str(data.get("refresh_token") or "").strip() or None,
                "token_type": token_type,
                "scope": scope,
                "expires_at": session.expires_at,
                "created_at": session.created_at,
                "id_token": str(data.get("id_token") or "").strip() or None,
            }
        )

    next_url = str(pending.get("next_url") or "").strip() or codex_oauth_frontend_success_url()
    return session, next_url


def get_session(session_id: str | None) -> CodexSession | None:
    sid = str(session_id or "").strip()
    if not sid:
        return None
    _cleanup_expired_state_and_sessions()
    with _STATE_LOCK:
        return _ACTIVE_SESSIONS.get(sid)


def has_valid_token_sink() -> bool:
    if bool(getattr(settings, "codex_oauth_token_sink_enabled", True)):
        payload = read_token_sink()
        if isinstance(payload, dict):
            token = str(payload.get("access_token") or "").strip()
            expires_at = _safe_int(payload.get("expires_at"), default=0)
            if token and expires_at > int(time.time()) + 30:
                return True
    return _has_valid_codex_cli_auth()


def revoke_session(session_id: str | None) -> None:
    sid = str(session_id or "").strip()
    if sid:
        with _STATE_LOCK:
            _ACTIVE_SESSIONS.pop(sid, None)
    revoke_token_sink()


def persist_token_sink(payload: dict[str, Any]) -> None:
    sink_path = _resolve_token_sink_path()
    profile = _token_sink_profile()
    now = int(time.time())

    existing: dict[str, Any] = {}
    if sink_path.exists():
        try:
            existing = json.loads(sink_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}

    profiles = existing.get("profiles") if isinstance(existing.get("profiles"), dict) else {}
    profile_payload = {
        "provider": str(payload.get("provider") or _oauth_provider()).strip() or "openai",
        "access_token": str(payload.get("access_token") or "").strip() or None,
        "refresh_token": str(payload.get("refresh_token") or "").strip() or None,
        "token_type": str(payload.get("token_type") or "").strip() or None,
        "scope": str(payload.get("scope") or "").strip() or None,
        "expires_at": _safe_int(payload.get("expires_at"), default=now + 3600),
        "created_at": _safe_int(payload.get("created_at"), default=now),
        "id_token": str(payload.get("id_token") or "").strip() or None,
    }
    profiles[profile] = profile_payload

    final_payload = {
        "schema_version": "codex_oauth_sink.v1",
        "active_profile": profile,
        "profiles": profiles,
        "updated_at": now,
    }
    sink_path.parent.mkdir(parents=True, exist_ok=True)
    sink_path.write_text(json.dumps(final_payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_token_sink() -> dict[str, Any] | None:
    sink_path = _resolve_token_sink_path()
    if not sink_path.exists():
        return None
    try:
        payload = json.loads(sink_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
    except Exception:
        return None

    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), dict) else {}
    active_profile = str(payload.get("active_profile") or _token_sink_profile()).strip() or _token_sink_profile()
    profile_payload = profiles.get(active_profile)
    if not isinstance(profile_payload, dict):
        return None
    return profile_payload


def revoke_token_sink() -> None:
    sink_path = _resolve_token_sink_path()
    if not sink_path.exists():
        return
    try:
        sink_path.unlink()
    except Exception:
        pass


def _read_oauth_config() -> dict[str, Any]:
    if not codex_oauth_enabled():
        raise ValueError("codex_oauth_disabled")

    provider = _oauth_provider()
    authorize_url = str(getattr(settings, "codex_oauth_authorize_url", "") or "").strip()
    token_url = str(getattr(settings, "codex_oauth_token_url", "") or "").strip()
    client_id = str(getattr(settings, "codex_oauth_client_id", "") or "").strip()
    client_secret = str(getattr(settings, "codex_oauth_client_secret", "") or "").strip() or None
    redirect_uri = str(getattr(settings, "codex_oauth_redirect_uri", "") or "").strip()
    scope = str(getattr(settings, "codex_oauth_scope", "openid profile email offline_access") or "").strip()
    state_ttl_seconds = _safe_int(getattr(settings, "codex_oauth_state_ttl_seconds", 600), default=600)
    originator = str(getattr(settings, "codex_oauth_originator", "codex_cli_rs") or "").strip()

    if provider == "openai":
        if not authorize_url:
            authorize_url = "https://auth.openai.com/oauth/authorize"
        if not token_url:
            token_url = "https://auth.openai.com/oauth/token"

    if not authorize_url:
        raise ValueError("codex_oauth_authorize_url_missing")
    if not token_url:
        raise ValueError("codex_oauth_token_url_missing")
    if not client_id:
        raise ValueError("codex_oauth_client_id_missing")
    if not redirect_uri:
        raise ValueError("codex_oauth_redirect_uri_missing")

    return {
        "provider": provider,
        "authorize_url": authorize_url,
        "token_url": token_url,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state_ttl_seconds": max(120, min(state_ttl_seconds, 3600)),
        "originator": originator or "codex_cli_rs",
    }


def _oauth_provider() -> str:
    value = str(getattr(settings, "codex_oauth_provider", "openai") or "").strip().lower()
    return value or "openai"


def _resolve_token_sink_path() -> Path:
    raw = str(getattr(settings, "codex_oauth_token_sink_path", "~/.codex/auth_openai.json") or "").strip()
    return Path(raw).expanduser().resolve()


def _resolve_codex_cli_auth_path() -> Path:
    raw = str(getattr(settings, "codex_cli_auth_path", "~/.codex/auth.json") or "").strip()
    return Path(raw).expanduser().resolve()


def _token_sink_profile() -> str:
    value = str(getattr(settings, "codex_oauth_token_sink_profile", "default") or "").strip()
    return value or "default"


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _normalize_next_url(next_url: str | None) -> str:
    url = str(next_url or "").strip()
    if not url:
        return codex_oauth_frontend_success_url()
    if url.startswith("/"):
        return url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return codex_oauth_frontend_success_url()


def _cleanup_expired_state_and_sessions() -> None:
    now = int(time.time())
    with _STATE_LOCK:
        for key in list(_PENDING_STATES.keys()):
            if int(_PENDING_STATES[key].get("expires_at") or 0) <= now:
                _PENDING_STATES.pop(key, None)
        for key in list(_ACTIVE_SESSIONS.keys()):
            if int(_ACTIVE_SESSIONS[key].expires_at) <= now:
                _ACTIVE_SESSIONS.pop(key, None)


def _has_valid_codex_cli_auth() -> bool:
    path = _resolve_codex_cli_auth_path()
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return False
    access_token = str(tokens.get("access_token") or "").strip()
    if not access_token:
        return False
    exp = _jwt_exp(access_token)
    if exp is None:
        # fallback: token exists but unparsable; treat as present to match CLI behavior
        return True
    return exp > int(time.time()) + 30


def _jwt_exp(token: str) -> int | None:
    parts = str(token or "").split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload + padding)
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    try:
        return int(obj.get("exp"))
    except Exception:
        return None
