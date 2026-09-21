from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Iterator, NoReturn
from urllib.parse import urlparse, urlencode

import httpx
from functorial_kit import Failure

from app.settings.config import settings
from mrw_functorial_kit.core.agent_service_semantics import codex_oauth_failures

try:
    import jwt
except ImportError:  # pragma: no cover - optional runtime dependency guard.
    jwt = None  # type: ignore[assignment]

try:
    import fcntl
except ImportError:  # pragma: no cover - fcntl is unavailable on non-POSIX platforms.
    fcntl = None  # type: ignore[assignment]


@dataclass(frozen=True, init=False)
class CodexSession:
    session_id: str
    access_token: str | None
    token_type: str | None
    scope: str | None
    created_at: int
    expires_at: int
    claims: dict[str, Any]

    def __init__(
        self,
        session_id: str,
        access_token: str | None,
        token_type: str | None,
        scope: str | None,
        created_at: int,
        expires_at: int,
        claims: dict[str, Any] | None = None,
        identity_claims: dict[str, Any] | None = None,
    ) -> None:
        clean_claims = (
            claims
            if isinstance(claims, dict)
            else identity_claims
            if isinstance(identity_claims, dict)
            else {}
        )
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "access_token", access_token)
        object.__setattr__(self, "token_type", token_type)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "claims", clean_claims)

    @property
    def identity_claims(self) -> dict[str, Any]:
        return self.claims


@dataclass(frozen=True)
class TokenSinkClaimsContext:
    has_valid_token_sink: bool
    claims: dict[str, Any]
    from_token_sink: bool
    profile_name: str | None = None
    expires_at: int | None = None
    fallback_used: bool | None = None
    profile_name_hash: str | None = None

    def profile_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if self.profile_name:
            metadata["profile_name"] = self.profile_name
        if self.profile_name_hash:
            metadata["profile_name_hash"] = self.profile_name_hash
        if self.expires_at is not None:
            metadata["expires_at"] = self.expires_at
        if self.fallback_used is not None:
            metadata["fallback_used"] = self.fallback_used
        return metadata


@dataclass(frozen=True)
class TokenSinkProfileSelection:
    payload: dict[str, Any]
    profile_name: str
    expires_at: int
    fallback_used: bool

    def metadata(self) -> dict[str, Any]:
        return {
            "profile_name": _observable_token_sink_profile_name(self.profile_name),
            "profile_name_hash": _token_sink_profile_name_hash(self.profile_name),
            "expires_at": self.expires_at,
            "fallback_used": self.fallback_used,
        }


_STATE_LOCK = threading.RLock()
_TOKEN_SINK_LOCK = threading.RLock()
_PENDING_STATES: dict[str, dict[str, Any]] = {}
_ACTIVE_SESSIONS: dict[str, CodexSession] = {}


class TokenSinkPathSecurityError(PermissionError):
    pass


_OAUTH_FAILURE_WITNESS = "test:test_w02_oauth_failure_lifts"
_OAUTH_FAILURE_CONTEXT_KEYS = frozenset(
    {"operation", "public_exception", "public_message", "site", "witness"}
)


def _oauth_failure(
    code: str,
    message: str,
    *,
    operation: str,
    site: str,
    public_exception: str,
) -> Failure:
    """Build a closed OAuth failure before the retained compatibility lift."""
    return codex_oauth_failures.fail(
        code,
        message,
        {
            "operation": operation,
            "public_exception": public_exception,
            "public_message": message,
            "site": site,
            "witness": _OAUTH_FAILURE_WITNESS,
        },
    )


def _raise_oauth_failure(
    failure: Failure,
    exception_type: type[Exception],
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """Preserve the established exception ABI at the OAuth service boundary."""
    context = failure.context or {}
    if (
        failure.family != codex_oauth_failures.name
        or _OAUTH_FAILURE_CONTEXT_KEYS - set(context)
        or context.get("public_exception") != exception_type.__name__
    ):
        # kit:boundary owner=codex_oauth.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w02_oauth_failure_lifts
        raise TypeError("OAuth failure lift context is incomplete")
    if cause is None:
        # kit:boundary owner=codex_oauth.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=codex.oauth.failure witness=test:test_w02_oauth_failure_lifts
        raise exception_type(str(context["public_message"]))
    # kit:boundary owner=codex_oauth.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=codex.oauth.failure witness=test:test_w02_oauth_failure_lifts
    raise exception_type(str(context["public_message"])) from cause


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


def build_authorize_url(*, next_url: str | None = None, redirect_uri: str | None = None) -> Annotated[
    str,
    "kit:prepared-command effect_boundary=codex_oauth_authorize_redirect "
    "witness=test:test_w02_agent_authority_metadata"
]:
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
        _raise_oauth_failure(
            _oauth_failure(
                "state_required",
                "state is required",
                operation="exchange_code_to_session",
                site="state",
                public_exception="ValueError",
            ),
            ValueError,
        )

    with _STATE_LOCK:
        pending = _PENDING_STATES.pop(state_key, None)
    if not isinstance(pending, dict):
        _raise_oauth_failure(
            _oauth_failure(
                "invalid_or_expired_state",
                "invalid_or_expired_state",
                operation="exchange_code_to_session",
                site="state_lookup",
                public_exception="ValueError",
            ),
            ValueError,
        )

    if int(pending.get("expires_at") or 0) < int(time.time()):
        _raise_oauth_failure(
            _oauth_failure(
                "state_expired",
                "state_expired",
                operation="exchange_code_to_session",
                site="state_expiry",
                public_exception="ValueError",
            ),
            ValueError,
        )

    code_verifier = str(pending.get("code_verifier") or "")
    if not code_verifier:
        _raise_oauth_failure(
            _oauth_failure(
                "state_missing_verifier",
                "state_missing_verifier",
                operation="exchange_code_to_session",
                site="code_verifier",
                public_exception="ValueError",
            ),
            ValueError,
        )

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
        _raise_oauth_failure(
            _oauth_failure(
                "token_exchange_failed",
                reason,
                operation="exchange_code_to_session",
                site="token_endpoint",
                public_exception="ValueError",
            ),
            ValueError,
        )

    data = response.json() if response.content else {}
    access_token = str(data.get("access_token") or "").strip() or None
    token_type = str(data.get("token_type") or "").strip() or None
    scope = str(data.get("scope") or "").strip() or cfg["scope"]
    id_token = str(data.get("id_token") or "").strip() or None
    claims = validate_id_token_claims(id_token, cfg=cfg)
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
        claims=claims,
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
                "id_token": id_token,
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
        if _select_valid_token_sink_profile() is not None:
            return True
    return _has_valid_codex_cli_auth()


def get_token_sink_claims_context() -> TokenSinkClaimsContext:
    """Return locally decoded claims for the OAuth token sink only.

    This intentionally ignores Codex CLI auth fallback so fallback auth can
    prove presence without manufacturing an OIDC identity.
    """
    if not bool(getattr(settings, "codex_oauth_token_sink_enabled", True)):
        return TokenSinkClaimsContext(False, {}, False)
    selection = _select_valid_token_sink_profile()
    if selection is None:
        return TokenSinkClaimsContext(False, {}, False)
    id_token = str(selection.payload.get("id_token") or "").strip() or None
    claims = validate_id_token_claims(id_token)
    metadata = selection.metadata()
    return TokenSinkClaimsContext(
        True,
        claims,
        True,
        profile_name=metadata.get("profile_name") if isinstance(metadata.get("profile_name"), str) else None,
        expires_at=metadata.get("expires_at") if isinstance(metadata.get("expires_at"), int) else None,
        fallback_used=metadata.get("fallback_used") if isinstance(metadata.get("fallback_used"), bool) else None,
        profile_name_hash=(
            metadata.get("profile_name_hash") if isinstance(metadata.get("profile_name_hash"), str) else None
        ),
    )


def revoke_session(session_id: str | None) -> dict[str, Any]:
    sid = str(session_id or "").strip()
    session_revoked = False
    session: CodexSession | None = None
    if sid:
        with _STATE_LOCK:
            session = _ACTIVE_SESSIONS.pop(sid, None)
            session_revoked = session is not None
    provider_revoke_result = revoke_provider_token(session=session)
    token_sink_result = revoke_token_sink()
    return {
        "session_present": bool(sid),
        "session_revoked": session_revoked,
        "token_sink_attempted": bool(token_sink_result.get("attempted")),
        "token_sink_revoked": bool(token_sink_result.get("revoked")),
        "token_sink_reason": str(token_sink_result.get("reason") or "unknown"),
        "provider_revoke": provider_revoke_result,
    }


def persist_token_sink(payload: dict[str, Any]) -> None:
    sink_path = _resolve_token_sink_path()
    profile = _token_sink_profile()
    now = int(time.time())

    existing: dict[str, Any] = {}
    with _TOKEN_SINK_LOCK:
        _assert_safe_token_sink_path(sink_path, for_write=True)
        with _token_sink_file_lock(exclusive=True):
            existing_payload = _read_token_sink_file(lock=False)
            if isinstance(existing_payload, dict):
                existing = existing_payload

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
            _write_token_sink_file(sink_path, final_payload)


def read_token_sink() -> dict[str, Any] | None:
    payload = _read_token_sink_file()
    if not isinstance(payload, dict):
        return None

    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), dict) else {}
    active_profile = _active_token_sink_profile(payload)
    profile_payload = profiles.get(active_profile)
    if not isinstance(profile_payload, dict):
        return None
    return profile_payload


def revoke_token_sink_profile(*, profile_name: str | None = None) -> dict[str, Any]:
    sink_path = _resolve_token_sink_path()
    requested_profile = str(profile_name or "").strip()
    target_profile = requested_profile
    now = int(time.time())

    with _TOKEN_SINK_LOCK:
        try:
            _assert_safe_token_sink_path(sink_path, for_write=True)
        except TokenSinkPathSecurityError:
            return _token_sink_profile_revoke_result(
                revoked=False,
                reason="path_unsafe",
                profile_name=target_profile,
                revoked_at=now,
            )

        with _token_sink_file_lock(exclusive=True):
            payload = _read_token_sink_file(lock=False)
            if not isinstance(payload, dict):
                return _token_sink_profile_revoke_result(
                    revoked=False,
                    reason="token_sink_missing",
                    profile_name=target_profile,
                )

            if not target_profile:
                target_profile = _active_token_sink_profile(payload)
            profiles = payload.get("profiles") if isinstance(payload.get("profiles"), dict) else {}
            profile_payload = profiles.get(target_profile)
            if not isinstance(profile_payload, dict):
                return _token_sink_profile_revoke_result(
                    revoked=False,
                    reason="profile_missing",
                    profile_name=target_profile,
                )

            updated_profile = dict(profile_payload)
            updated_profile["revoked"] = True
            updated_profile["revoked_at"] = now
            for key in ("access_token", "refresh_token", "id_token"):
                updated_profile.pop(key, None)
            profiles[target_profile] = updated_profile
            payload["profiles"] = profiles
            payload["updated_at"] = now
            try:
                _write_token_sink_file(sink_path, payload)
            except Exception:
                return _token_sink_profile_revoke_result(
                    revoked=False,
                    reason="write_failed",
                    profile_name=target_profile,
                    revoked_at=now,
                )

    return _token_sink_profile_revoke_result(
        revoked=True,
        reason="revoked",
        profile_name=target_profile,
        revoked_at=now,
    )


def _select_valid_token_sink_profile() -> TokenSinkProfileSelection | None:
    payload = _read_token_sink_file()
    if not isinstance(payload, dict):
        return None

    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), dict) else {}
    active_profile = _active_token_sink_profile(payload)
    active_payload = profiles.get(active_profile)
    now = int(time.time())
    if _is_valid_token_sink_profile(active_payload, now=now):
        return TokenSinkProfileSelection(
            payload=active_payload,
            profile_name=active_profile,
            expires_at=_safe_int(active_payload.get("expires_at"), default=0),
            fallback_used=False,
        )

    allowed_fallback_profiles = _token_sink_fallback_profiles()
    if allowed_fallback_profiles:
        profile_items = [
            (profile_name, profiles.get(profile_name))
            for profile_name in allowed_fallback_profiles
        ]
    else:
        profile_items = sorted(
            (
                (str(profile_name or "").strip(), profile_payload)
                for profile_name, profile_payload in profiles.items()
            ),
            key=lambda item: item[0],
        )

    for profile_name, profile_payload in profile_items:
        if not profile_name or profile_name == active_profile:
            continue
        if _is_valid_token_sink_profile(profile_payload, now=now):
            return TokenSinkProfileSelection(
                payload=profile_payload,
                profile_name=profile_name,
                expires_at=_safe_int(profile_payload.get("expires_at"), default=0),
                fallback_used=True,
            )
    return None


def _is_valid_token_sink_profile(payload: Any, *, now: int) -> bool:
    if not isinstance(payload, dict):
        return False
    if _is_revoked_token_sink_profile(payload):
        return False
    token = str(payload.get("access_token") or "").strip()
    expires_at = _safe_int(payload.get("expires_at"), default=0)
    return bool(token and expires_at > now + 30)


def _is_revoked_token_sink_profile(payload: dict[str, Any]) -> bool:
    if payload.get("revoked") is True:
        return True

    revoked_at = payload.get("revoked_at")
    if revoked_at is None or revoked_at is False:
        return False
    if isinstance(revoked_at, (int, float)):
        return revoked_at > 0
    if isinstance(revoked_at, str):
        value = revoked_at.strip()
        if not value or value.lower() in {"0", "false", "none", "null"}:
            return False
        try:
            return float(value) > 0
        except ValueError:
            return True
    return bool(revoked_at)


def _active_token_sink_profile(payload: dict[str, Any]) -> str:
    active_profile = str(payload.get("active_profile") or _token_sink_profile()).strip()
    return active_profile or _token_sink_profile()


def _observable_token_sink_profile_name(profile_name: str) -> str:
    clean_name = str(profile_name or "").strip()[:128]
    if not clean_name:
        return "unknown"
    return "redacted"


def _token_sink_profile_name_hash(profile_name: str) -> str:
    digest = hashlib.sha256(str(profile_name or "").encode("utf-8")).hexdigest()[:16]
    return f"profile:{digest}"


def _token_sink_profile_revoke_result(
    *,
    revoked: bool,
    reason: str,
    profile_name: str,
    revoked_at: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "revoked": revoked,
        "reason": reason,
        "profile_name": _observable_token_sink_profile_name(profile_name),
        "profile_name_hash": _token_sink_profile_name_hash(profile_name),
    }
    if revoked_at is not None:
        result["revoked_at"] = revoked_at
    return result


def _read_token_sink_file(*, lock: bool = True) -> dict[str, Any] | None:
    if lock:
        sink_path = _resolve_token_sink_path()
        if not _is_safe_token_sink_path(sink_path, for_write=False):
            return None
        with _TOKEN_SINK_LOCK, _token_sink_file_lock(exclusive=False):
            return _read_token_sink_file(lock=False)

    sink_path = _resolve_token_sink_path()
    if not _is_safe_token_sink_path(sink_path, for_write=False):
        return None
    if not sink_path.exists():
        return None
    try:
        payload = json.loads(sink_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
    except Exception:
        return None
    return payload


@contextmanager
def _token_sink_file_lock(*, exclusive: bool) -> Iterator[None]:
    if fcntl is None:
        yield
        return

    sink_path = _resolve_token_sink_path()
    lock_path = sink_path.with_name(f".{sink_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            lock_path.chmod(0o600)
        except Exception:
            pass
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_token_sink_file(sink_path: Path, payload: dict[str, Any]) -> None:
    _assert_safe_token_sink_path(sink_path, for_write=True)
    sink_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = sink_path.with_name(f".{sink_path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.chmod(0o600)
        temp_path.replace(sink_path)
        _fsync_parent_directory(sink_path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass


def _fsync_parent_directory(path: Path) -> None:
    dir_fd: int | None = None
    try:
        dir_fd = os.open(path.parent, os.O_RDONLY)
        os.fsync(dir_fd)
    except Exception:
        pass
    finally:
        if dir_fd is not None:
            try:
                os.close(dir_fd)
            except Exception:
                pass


def _is_safe_token_sink_path(path: Path, *, for_write: bool) -> bool:
    try:
        _assert_safe_token_sink_path(path, for_write=for_write)
        return True
    except TokenSinkPathSecurityError:
        return False


def _raise_token_sink_path_failure(
    code: str,
    message: str,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    _raise_oauth_failure(
        _oauth_failure(
            code,
            message,
            operation="token_sink_path_validation",
            site="token_sink_path",
            public_exception="TokenSinkPathSecurityError",
        ),
        TokenSinkPathSecurityError,
        cause=cause,
    )


def _assert_safe_token_sink_path(path: Path, *, for_write: bool) -> None:
    path = Path(path).expanduser()
    if "\x00" in str(path) or "\n" in str(path) or "\r" in str(path):
        _raise_token_sink_path_failure(
            "token_sink_path_contains_control_character",
            "token_sink_path_contains_control_character",
        )
    if not path.is_absolute():
        _raise_token_sink_path_failure(
            "token_sink_path_must_be_absolute",
            "token_sink_path_must_be_absolute",
        )

    parent = path.parent
    if parent.exists():
        if parent.is_symlink():
            _raise_token_sink_path_failure(
                "token_sink_parent_must_not_be_symlink",
                "token_sink_parent_must_not_be_symlink",
            )
        if not parent.is_dir():
            _raise_token_sink_path_failure(
                "token_sink_parent_must_be_directory",
                "token_sink_parent_must_be_directory",
            )
        _assert_current_user_owned(parent, reason="token_sink_parent_owner_mismatch")
        mode = parent.stat().st_mode
        if mode & 0o022:
            _raise_token_sink_path_failure(
                "token_sink_parent_must_not_be_group_or_world_writable",
                "token_sink_parent_must_not_be_group_or_world_writable",
            )
    elif not for_write:
        _raise_token_sink_path_failure(
            "token_sink_parent_missing",
            "token_sink_parent_missing",
        )

    if path.exists() or path.is_symlink():
        if path.is_symlink():
            _raise_token_sink_path_failure(
                "token_sink_path_must_not_be_symlink",
                "token_sink_path_must_not_be_symlink",
            )
        if not path.is_file():
            _raise_token_sink_path_failure(
                "token_sink_path_must_be_file",
                "token_sink_path_must_be_file",
            )
        _assert_current_user_owned(path, reason="token_sink_owner_mismatch")


def _assert_current_user_owned(path: Path, *, reason: str) -> None:
    try:
        stat_result = path.stat()
    except OSError as exc:
        _raise_token_sink_path_failure(
            "token_sink_owner_mismatch",
            reason,
            cause=exc,
        )
    if hasattr(os, "getuid") and stat_result.st_uid != os.getuid():
        _raise_token_sink_path_failure("token_sink_owner_mismatch", reason)


def revoke_token_sink() -> dict[str, Any]:
    sink_path = _resolve_token_sink_path()
    with _TOKEN_SINK_LOCK:
        try:
            _assert_safe_token_sink_path(sink_path, for_write=True)
        except TokenSinkPathSecurityError:
            return _token_sink_revoke_result(revoked=False, reason="path_unsafe")
        try:
            with _token_sink_file_lock(exclusive=True):
                if not sink_path.exists():
                    return _token_sink_revoke_result(revoked=False, reason="missing")
                try:
                    sink_path.unlink()
                    _fsync_parent_directory(sink_path)
                except Exception:
                    return _token_sink_revoke_result(revoked=False, reason="write_failed")
        except TokenSinkPathSecurityError:
            return _token_sink_revoke_result(revoked=False, reason="path_unsafe")
        except Exception:
            return _token_sink_revoke_result(revoked=False, reason="write_failed")
    return _token_sink_revoke_result(revoked=True, reason="revoked")


def _token_sink_revoke_result(*, revoked: bool, reason: str) -> dict[str, Any]:
    return {
        "attempted": True,
        "revoked": revoked,
        "reason": reason,
    }


def revoke_provider_token(*, session: CodexSession | None = None) -> dict[str, Any]:
    revoke_url = _provider_revoke_url()
    if not revoke_url:
        return _provider_revoke_result(
            attempted=False,
            revoked=False,
            reason="not_configured",
        )

    token = str(getattr(session, "access_token", None) or "").strip()
    if not token:
        token = _active_token_sink_access_token()
    if not token:
        return _provider_revoke_result(
            attempted=False,
            revoked=False,
            reason="token_missing",
        )

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                revoke_url,
                data={"token": token, "token_type_hint": "access_token"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except Exception:
        return _provider_revoke_result(
            attempted=True,
            revoked=False,
            reason="request_failed",
        )

    status_code = int(getattr(response, "status_code", 0) or 0)
    if 200 <= status_code < 300:
        return _provider_revoke_result(
            attempted=True,
            revoked=True,
            reason="revoked",
            status_code=status_code,
        )
    return _provider_revoke_result(
        attempted=True,
        revoked=False,
        reason="http_failed",
        status_code=status_code,
    )


def _provider_revoke_result(
    *,
    attempted: bool,
    revoked: bool,
    reason: str,
    status_code: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": attempted,
        "revoked": revoked,
        "reason": reason,
    }
    if status_code is not None:
        result["status_code"] = status_code
    return result


def _active_token_sink_access_token() -> str | None:
    if not bool(getattr(settings, "codex_oauth_token_sink_enabled", True)):
        return None
    selection = _select_valid_token_sink_profile()
    if selection is None:
        return None
    token = str(selection.payload.get("access_token") or "").strip()
    return token or None


def decode_id_token_claims(id_token: str | None) -> dict[str, Any]:
    """Decode an OIDC id_token payload without trusting it."""
    token = str(id_token or "").strip()
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload + padding)
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}

    return _sanitize_id_token_claims(obj)


def _decode_id_token_header(id_token: str | None) -> dict[str, Any]:
    token = str(id_token or "").strip()
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    header = parts[0]
    padding = "=" * (-len(header) % 4)
    try:
        raw = base64.urlsafe_b64decode(header + padding)
        obj = json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    return _sanitize_id_token_claims(obj)


def _sanitize_id_token_claims(obj: dict[str, Any]) -> dict[str, Any]:
    claims: dict[str, Any] = {}
    for key, value in obj.items():
        clean_key = str(key or "").strip()
        if not clean_key:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            claims[clean_key] = value
        elif isinstance(value, list):
            claims[clean_key] = [
                item
                for item in value[:20]
                if isinstance(item, (str, int, float, bool)) or item is None
            ]
        elif isinstance(value, dict):
            claims[clean_key] = {
                str(child_key): child_value
                for child_key, child_value in list(value.items())[:20]
                if isinstance(child_value, (str, int, float, bool)) or child_value is None
            }
    return claims


def validate_id_token_claims(
    id_token: str | None,
    *,
    cfg: dict[str, Any] | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    expected = cfg if isinstance(cfg, dict) else _id_token_validation_config()
    claims = _verify_id_token_signature(id_token, expected=expected)
    if not claims:
        return {}
    if not _id_token_audience_matches(claims.get("aud"), str(expected.get("client_id") or "").strip()):
        return {}
    if not _id_token_issuer_matches(claims.get("iss"), str(expected.get("expected_issuer") or "").strip()):
        return {}
    if not _id_token_exp_valid(claims.get("exp"), now=int(now if now is not None else time.time())):
        return {}
    expected_source = str(expected.get("expected_id_token_source") or "").strip()
    if expected_source and _id_token_source_claim(claims) != expected_source:
        return {}
    return claims


def _verify_id_token_signature(id_token: str | None, *, expected: dict[str, Any]) -> dict[str, Any]:
    """Return claims only after local signature verification succeeds.

    This deliberately avoids live JWKS network fetches. Production callers must
    provide inline JWK/JWKS material, while tests may use a shared HMAC key.
    """
    if jwt is None:
        return {}
    token = str(id_token or "").strip()
    parts = token.split(".")
    if len(parts) != 3 or not parts[2]:
        return {}
    header = _decode_id_token_header(token)
    alg = str(header.get("alg") or "").strip().upper()
    if not alg or alg == "NONE":
        return {}

    for key in _id_token_verification_keys(expected=expected, header=header, alg=alg):
        try:
            decoded = jwt.decode(
                token,
                key=key,
                algorithms=[alg],
                options={
                    "verify_aud": False,
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_iss": False,
                    "verify_nbf": False,
                },
            )
        except Exception:
            continue
        if isinstance(decoded, dict):
            return _sanitize_id_token_claims(decoded)
    return {}


def _id_token_verification_keys(
    *,
    expected: dict[str, Any],
    header: dict[str, Any],
    alg: str,
) -> list[Any]:
    keys: list[Any] = []
    shared_key = str(
        expected.get("id_token_shared_key")
        or getattr(settings, "codex_oauth_id_token_shared_key", "")
        or ""
    ).strip()
    if shared_key and alg in {"HS256", "HS384", "HS512"}:
        keys.append(shared_key)

    for jwk in _configured_id_token_jwks(expected):
        key = _jwk_verification_key(jwk, header=header, alg=alg)
        if key is not None:
            keys.append(key)
    return keys


def _configured_id_token_jwks(expected: dict[str, Any]) -> list[dict[str, Any]]:
    configured: list[dict[str, Any]] = []
    for value in (
        expected.get("id_token_jwk"),
        getattr(settings, "codex_oauth_id_token_jwk", ""),
    ):
        obj = _json_config_object(value)
        if isinstance(obj, dict):
            configured.append(obj)

    for value in (
        expected.get("id_token_jwks"),
        getattr(settings, "codex_oauth_id_token_jwks", ""),
    ):
        obj = _json_config_object(value)
        if isinstance(obj, dict):
            raw_keys = obj.get("keys")
        elif isinstance(obj, list):
            raw_keys = obj
        else:
            raw_keys = []
        if isinstance(raw_keys, list):
            configured.extend(item for item in raw_keys if isinstance(item, dict))
    return configured


def _json_config_object(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _jwk_verification_key(jwk: dict[str, Any], *, header: dict[str, Any], alg: str) -> Any | None:
    header_kid = str(header.get("kid") or "").strip()
    jwk_kid = str(jwk.get("kid") or "").strip()
    if header_kid and jwk_kid and header_kid != jwk_kid:
        return None
    jwk_alg = str(jwk.get("alg") or "").strip().upper()
    if jwk_alg and jwk_alg != alg:
        return None
    try:
        pyjwk = jwt.PyJWK.from_dict(jwk)
        return pyjwk.key
    except Exception:
        return None


def _id_token_validation_config() -> dict[str, Any]:
    provider = _oauth_provider()
    authorize_url = str(getattr(settings, "codex_oauth_authorize_url", "") or "").strip()
    if provider == "openai" and not authorize_url:
        authorize_url = "https://auth.openai.com/oauth/authorize"
    originator = str(getattr(settings, "codex_oauth_originator", "codex_cli_rs") or "").strip()
    return {
        "client_id": str(getattr(settings, "codex_oauth_client_id", "") or "").strip(),
        "expected_issuer": _expected_id_token_issuer(provider=provider, authorize_url=authorize_url),
        "expected_id_token_source": _expected_id_token_source(originator=originator),
        "id_token_jwk": str(getattr(settings, "codex_oauth_id_token_jwk", "") or "").strip(),
        "id_token_jwks": str(getattr(settings, "codex_oauth_id_token_jwks", "") or "").strip(),
        "id_token_shared_key": str(getattr(settings, "codex_oauth_id_token_shared_key", "") or "").strip(),
    }


def _id_token_audience_matches(audience: Any, expected_audience: str) -> bool:
    if not expected_audience:
        return False
    if isinstance(audience, str):
        return audience == expected_audience
    if isinstance(audience, list):
        return any(isinstance(item, str) and item == expected_audience for item in audience)
    return False


def _id_token_issuer_matches(issuer: Any, expected_issuer: str) -> bool:
    if not expected_issuer or not isinstance(issuer, str):
        return False
    return issuer.rstrip("/") == expected_issuer.rstrip("/")


def _id_token_exp_valid(expires_at: Any, *, now: int) -> bool:
    try:
        parsed = int(expires_at)
    except Exception:
        return False
    return parsed > now


def _id_token_source_claim(claims: dict[str, Any]) -> str:
    for key in (
        "source",
        "token_source",
        "originator",
        "https://api.openai.com/auth/source",
        "https://auth.openai.com/source",
    ):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _expected_id_token_issuer(*, provider: str, authorize_url: str) -> str:
    configured = str(getattr(settings, "codex_oauth_expected_issuer", "") or "").strip()
    if configured:
        return configured.rstrip("/")
    if provider == "openai":
        return "https://auth.openai.com"
    parsed = urlparse(authorize_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return ""


def _expected_id_token_source(*, originator: str) -> str:
    configured = str(getattr(settings, "codex_oauth_expected_id_token_source", "") or "").strip()
    return configured or originator


def _read_oauth_config() -> dict[str, Any]:
    if not codex_oauth_enabled():
        _raise_oauth_failure(
            _oauth_failure(
                "codex_oauth_disabled",
                "codex_oauth_disabled",
                operation="read_oauth_config",
                site="enabled",
                public_exception="ValueError",
            ),
            ValueError,
        )

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
        _raise_oauth_failure(
            _oauth_failure(
                "codex_oauth_authorize_url_missing",
                "codex_oauth_authorize_url_missing",
                operation="read_oauth_config",
                site="authorize_url",
                public_exception="ValueError",
            ),
            ValueError,
        )
    if not token_url:
        _raise_oauth_failure(
            _oauth_failure(
                "codex_oauth_token_url_missing",
                "codex_oauth_token_url_missing",
                operation="read_oauth_config",
                site="token_url",
                public_exception="ValueError",
            ),
            ValueError,
        )
    if not client_id:
        _raise_oauth_failure(
            _oauth_failure(
                "codex_oauth_client_id_missing",
                "codex_oauth_client_id_missing",
                operation="read_oauth_config",
                site="client_id",
                public_exception="ValueError",
            ),
            ValueError,
        )
    if not redirect_uri:
        _raise_oauth_failure(
            _oauth_failure(
                "codex_oauth_redirect_uri_missing",
                "codex_oauth_redirect_uri_missing",
                operation="read_oauth_config",
                site="redirect_uri",
                public_exception="ValueError",
            ),
            ValueError,
        )

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
        "expected_issuer": _expected_id_token_issuer(provider=provider, authorize_url=authorize_url),
        "expected_id_token_source": _expected_id_token_source(originator=originator or "codex_cli_rs"),
        "id_token_jwk": str(getattr(settings, "codex_oauth_id_token_jwk", "") or "").strip(),
        "id_token_jwks": str(getattr(settings, "codex_oauth_id_token_jwks", "") or "").strip(),
        "id_token_shared_key": str(getattr(settings, "codex_oauth_id_token_shared_key", "") or "").strip(),
    }


def _oauth_provider() -> str:
    value = str(getattr(settings, "codex_oauth_provider", "openai") or "").strip().lower()
    return value or "openai"


def _provider_revoke_url() -> str:
    return str(getattr(settings, "codex_oauth_provider_revoke_url", "") or "").strip()


def _resolve_token_sink_path() -> Path:
    raw = str(getattr(settings, "codex_oauth_token_sink_path", "~/.codex/auth_openai.json") or "").strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _resolve_codex_cli_auth_path() -> Path:
    raw = str(getattr(settings, "codex_cli_auth_path", "~/.codex/auth.json") or "").strip()
    return Path(raw).expanduser().resolve()


def _token_sink_profile() -> str:
    value = str(getattr(settings, "codex_oauth_token_sink_profile", "default") or "").strip()
    return value or "default"


def _token_sink_fallback_profiles() -> list[str]:
    raw = str(getattr(settings, "codex_oauth_token_sink_fallback_profiles", "") or "")
    profiles: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        profile_name = item.strip()
        if not profile_name or profile_name in seen:
            continue
        profiles.append(profile_name)
        seen.add(profile_name)
    return profiles


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
