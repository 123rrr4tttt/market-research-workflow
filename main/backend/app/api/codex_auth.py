from __future__ import annotations

import re
import shutil
import shlex
import subprocess
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ..contracts import ErrorCode, error_response
from ..contracts.responses import ok
from ..settings.config import settings
from ..services.codex_oauth import (
    build_authorize_url,
    codex_cookie_name,
    codex_cookie_secure,
    codex_oauth_enabled,
    codex_oauth_frontend_success_url,
    codex_oauth_frontend_error_url,
    exchange_code_to_session,
    get_session,
    has_valid_token_sink,
    revoke_session,
)


router = APIRouter(prefix="/codex-auth", tags=["codex-auth"])
_DEVICE_URL_RE = re.compile(r"https://auth\.openai\.com/codex/device\S*")
_DEVICE_CODE_RE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{5}\b")


def _error_json(status_code: int, code: ErrorCode, message: str, *, details: dict[str, Any] | None = None) -> JSONResponse:
    payload = error_response(code, message, details=details)
    payload["detail"] = {"error": payload["error"], "message": payload["error"]["message"]}
    return JSONResponse(status_code=status_code, content=payload, headers={"X-Error-Code": code.value})


@router.get("/login", response_model=None)
def codex_auth_login(next_url: str | None = Query(default=None, max_length=2048)) -> Any:
    if not codex_oauth_enabled():
        if has_valid_token_sink():
            return RedirectResponse(url=next_url or codex_oauth_frontend_success_url(), status_code=302)
        return _error_json(
            400,
            ErrorCode.INVALID_INPUT,
            "codex cli login is required on host machine",
            details={
                "category": "codex_cli_auth",
                "reason_code": "codex_cli_login_required",
                "hint": "run `codex login` on the backend host",
            },
        )
    try:
        authorize_url = build_authorize_url(next_url=next_url)
        return RedirectResponse(url=authorize_url, status_code=302)
    except ValueError as exc:
        return _error_json(
            400,
            ErrorCode.INVALID_INPUT,
            "codex oauth login is not configured",
            details={"category": "codex_oauth_config", "reason_code": str(exc)},
        )


@router.get("/callback", response_model=None)
async def codex_auth_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> Any:
    if not codex_oauth_enabled():
        return RedirectResponse(url=codex_oauth_frontend_error_url(), status_code=302)

    if error:
        err_url = _build_error_redirect("oauth_error", detail=error)
        return RedirectResponse(url=err_url, status_code=302)

    if not code or not state:
        err_url = _build_error_redirect("missing_code_or_state")
        return RedirectResponse(url=err_url, status_code=302)

    try:
        session, next_url = await exchange_code_to_session(code=code, state=state)
    except Exception as exc:  # noqa: BLE001
        err_url = _build_error_redirect("token_exchange_failed", detail=str(exc))
        return RedirectResponse(url=err_url, status_code=302)

    response = RedirectResponse(url=next_url or codex_oauth_frontend_success_url(), status_code=302)
    response.set_cookie(
        key=codex_cookie_name(),
        value=session.session_id,
        httponly=True,
        secure=codex_cookie_secure(),
        samesite="lax",
        max_age=max(1, int(session.expires_at - session.created_at)),
        path="/",
    )
    return response


@router.get("/status")
def codex_auth_status(request: Request) -> dict[str, Any]:
    sid = request.cookies.get(codex_cookie_name())
    session = get_session(sid)
    return ok(
        {
            "codex_oauth_enabled": codex_oauth_enabled(),
            "authenticated": session is not None,
            "token_sink_authenticated": has_valid_token_sink(),
            "session": (
                {
                    "expires_at": session.expires_at,
                    "scope": session.scope,
                    "token_type": session.token_type,
                }
                if session is not None
                else None
            ),
        }
    )


@router.post("/logout")
def codex_auth_logout(request: Request, response: Response) -> dict[str, Any]:
    sid = request.cookies.get(codex_cookie_name())
    revoke_session(sid)
    response.delete_cookie(key=codex_cookie_name(), path="/")
    return ok({"logged_out": True})


@router.post("/cli/bootstrap")
def codex_cli_bootstrap() -> dict[str, Any]:
    if has_valid_token_sink():
        return ok(
            {
                "authenticated": True,
                "codex_cli_installed": bool(shutil.which("codex")),
                "install_attempted": False,
                "install_succeeded": True,
                "device_url": None,
                "device_code": None,
                "hint": None,
            }
        )

    codex_bin = shutil.which("codex")
    if not codex_bin:
        installed, install_hint = _install_codex_cli()
        codex_bin = shutil.which("codex")
        if not installed or not codex_bin:
            return ok(
                {
                    "authenticated": False,
                    "codex_cli_installed": False,
                    "install_attempted": True,
                    "install_succeeded": bool(installed and codex_bin),
                    "device_url": None,
                    "device_code": None,
                    "hint": install_hint,
                }
            )

    command = [codex_bin, "login", "--device-auth"]
    output = ""
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=8)
        output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        output = (str(exc.stdout or "") + "\n" + str(exc.stderr or "")).strip()
    except Exception as exc:  # noqa: BLE001
        return ok(
            {
                "authenticated": False,
                "codex_cli_installed": True,
                "device_url": None,
                "device_code": None,
                "hint": f"failed to start `codex login --device-auth`: {exc}",
            }
        )

    device_url_match = _DEVICE_URL_RE.search(output)
    device_code_match = _DEVICE_CODE_RE.search(output)
    device_url = device_url_match.group(0) if device_url_match else None
    device_code = device_code_match.group(0) if device_code_match else None

    hint = None
    if not device_url or not device_code:
        hint = "unable to parse device code, run `codex login --device-auth` on backend host manually"

    return ok(
        {
            "authenticated": False,
            "codex_cli_installed": True,
            "install_attempted": False,
            "install_succeeded": True,
            "device_url": device_url,
            "device_code": device_code,
            "hint": hint,
        }
    )


def _install_codex_cli() -> tuple[bool, str]:
    install_command = str(settings.codex_cli_install_command or "").strip()
    if not install_command:
        return False, "codex cli is missing and CODEX_CLI_INSTALL_COMMAND is empty"

    try:
        argv = shlex.split(install_command)
    except ValueError as exc:
        return False, f"invalid CODEX_CLI_INSTALL_COMMAND: {exc}"

    if not argv:
        return False, "invalid CODEX_CLI_INSTALL_COMMAND: empty command"

    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return False, f"codex install timed out: `{install_command}`"
    except Exception as exc:  # noqa: BLE001
        return False, f"failed to run install command `{install_command}`: {exc}"

    if completed.returncode != 0:
        message = ((completed.stderr or "") + "\n" + (completed.stdout or "")).strip()
        compact = message[:240] if message else "unknown error"
        return False, f"codex install failed: `{install_command}` ({compact})"

    if shutil.which("codex"):
        return True, "codex cli installed"
    return False, "install command completed but `codex` is not in PATH, restart backend with updated PATH"


def _build_error_redirect(code: str, *, detail: str | None = None) -> str:
    base = codex_oauth_frontend_error_url()
    params = {"auth_error": code}
    if detail:
        params["detail"] = detail[:240]
    joiner = "&" if "?" in base else "?"
    return f"{base}{joiner}{urlencode(params)}"
