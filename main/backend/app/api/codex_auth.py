from __future__ import annotations

import os
import platform
import re
import shutil
import shlex
import subprocess
import tarfile
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ..contracts import ErrorCode, error_response
from ..contracts.responses import ok
from ..settings.config import settings
from ..services.llm.codex_app_server import codex_app_server_status
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
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_CODEX_RELEASE_BASE_URL = "https://github.com/openai/codex/releases/latest/download"
_CODEX_LOGIN_LOCK = threading.Lock()
_CODEX_LOGIN_PROCESS: subprocess.Popen[str] | None = None
_CODEX_LOGIN_STARTED_AT: float | None = None


def _error_json(status_code: int, code: ErrorCode, message: str, *, details: dict[str, Any] | None = None) -> JSONResponse:
    payload = error_response(code, message, details=details)
    payload["detail"] = {"error": payload["error"], "message": payload["error"]["message"]}
    return JSONResponse(status_code=status_code, content=payload, headers={"X-Error-Code": code.value})


@router.get("/login", response_model=None)
def codex_auth_login(
    next_url: str | None = Query(default=None, max_length=2048),
    force_oauth: bool = Query(default=False),
) -> Any:
    if has_valid_token_sink() and not force_oauth:
        return RedirectResponse(url=next_url or codex_oauth_frontend_success_url(), status_code=302)

    if not codex_oauth_enabled():
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
            "codex_cli_installed": bool(_codex_bin()),
            "authenticated": session is not None,
            "token_sink_authenticated": has_valid_token_sink(),
            "device_auth_pending": _codex_login_pending(),
            "persistent_core": codex_app_server_status(),
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
                "codex_cli_installed": bool(_codex_bin()),
                "install_attempted": False,
                "install_succeeded": True,
                "device_url": None,
                "device_code": None,
                "hint": None,
            }
        )

    codex_bin = _codex_bin()
    if not codex_bin:
        installed, install_hint = _install_codex_cli()
        codex_bin = _codex_bin()
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

    try:
        device_url, device_code = _start_codex_device_auth(codex_bin)
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

    device_url_match = _DEVICE_URL_RE.search(device_url or "")
    device_code_match = _DEVICE_CODE_RE.search(device_code or "")
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


def _start_codex_device_auth(codex_bin: str) -> tuple[str | None, str | None]:
    global _CODEX_LOGIN_PROCESS, _CODEX_LOGIN_STARTED_AT
    _stop_codex_login_process()
    process = subprocess.Popen(
        [codex_bin, "login", "--device-auth"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output = ""
    deadline = time.monotonic() + 8
    try:
        while time.monotonic() < deadline:
            line = process.stdout.readline() if process.stdout else ""
            if not line:
                if process.poll() is not None:
                    break
                time.sleep(0.05)
                continue
            output += line
            clean_output = _ANSI_RE.sub("", output)
            device_url_match = _DEVICE_URL_RE.search(clean_output)
            device_code_match = _DEVICE_CODE_RE.search(clean_output)
            if device_url_match and device_code_match:
                with _CODEX_LOGIN_LOCK:
                    _CODEX_LOGIN_PROCESS = process
                    _CODEX_LOGIN_STARTED_AT = time.monotonic()
                return device_url_match.group(0), device_code_match.group(0)
        clean_output = _ANSI_RE.sub("", output)
        device_url_match = _DEVICE_URL_RE.search(clean_output)
        device_code_match = _DEVICE_CODE_RE.search(clean_output)
        return (
            device_url_match.group(0) if device_url_match else None,
            device_code_match.group(0) if device_code_match else None,
        )
    finally:
        if process.poll() is None:
            with _CODEX_LOGIN_LOCK:
                keep_waiting = _CODEX_LOGIN_PROCESS is process
            if not keep_waiting:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()


def _codex_login_pending() -> bool:
    with _CODEX_LOGIN_LOCK:
        process = _CODEX_LOGIN_PROCESS
        started_at = _CODEX_LOGIN_STARTED_AT
    if process is None or process.poll() is not None:
        return False
    if started_at and time.monotonic() - started_at > 15 * 60:
        _stop_codex_login_process()
        return False
    return True


def _stop_codex_login_process() -> None:
    global _CODEX_LOGIN_PROCESS, _CODEX_LOGIN_STARTED_AT
    with _CODEX_LOGIN_LOCK:
        process = _CODEX_LOGIN_PROCESS
        _CODEX_LOGIN_PROCESS = None
        _CODEX_LOGIN_STARTED_AT = None
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()


def _install_codex_cli() -> tuple[bool, str]:
    install_command = str(settings.codex_cli_install_command or "").strip()
    if not install_command:
        return False, "codex cli is missing and CODEX_CLI_INSTALL_COMMAND is empty"

    if install_command.lower() == "auto":
        return _install_codex_cli_from_release()

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

    if completed.returncode != 0 and argv[:3] == ["npm", "i", "-g"] and "--force" not in argv:
        retry_argv = ["npm", "i", "-g", "--force", *argv[3:]]
        retry_command = " ".join(shlex.quote(part) for part in retry_argv)
        try:
            completed = subprocess.run(retry_argv, capture_output=True, text=True, timeout=300)
            install_command = retry_command
        except subprocess.TimeoutExpired:
            return False, f"codex install timed out: `{retry_command}`"
        except Exception as exc:  # noqa: BLE001
            return False, f"failed to run install command `{retry_command}`: {exc}"

    if completed.returncode != 0 and _should_retry_after_npm_partial_install(argv, completed):
        cleanup_hint = _cleanup_codex_npm_partial_install()
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return False, f"codex install timed out after cleanup: `{install_command}` ({cleanup_hint})"
        except Exception as exc:  # noqa: BLE001
            return False, f"failed to rerun install command `{install_command}` after cleanup: {exc} ({cleanup_hint})"

    if completed.returncode != 0:
        message = ((completed.stderr or "") + "\n" + (completed.stdout or "")).strip()
        compact = message[:240] if message else "unknown error"
        return False, f"codex install failed: `{install_command}` ({compact})"

    _ensure_codex_cli_shim()
    if _codex_bin():
        return True, "codex cli installed"
    return False, "install command completed but `codex` is not in PATH, restart backend with updated PATH"


def _codex_bin() -> str | None:
    _ensure_codex_cli_shim()
    return shutil.which("codex")


def _install_codex_cli_from_release() -> tuple[bool, str]:
    if os.environ.get("DOCKER_ENV") != "true":
        return False, "CODEX_CLI_INSTALL_COMMAND=auto is only supported in Docker; set an explicit install command"

    arch = platform.machine().lower()
    if arch in {"x86_64", "amd64"}:
        target = "x86_64-unknown-linux-musl"
    elif arch in {"aarch64", "arm64"}:
        target = "aarch64-unknown-linux-musl"
    else:
        return False, f"unsupported Docker architecture for Codex CLI auto install: {arch}"

    asset = f"codex-{target}.tar.gz"
    url = f"{_CODEX_RELEASE_BASE_URL}/{asset}"
    install_dir = Path.home() / ".codex" / "bin"
    binary_path = install_dir / "codex"

    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / asset
            urlretrieve(url, archive_path)
            with tarfile.open(archive_path, "r:gz") as archive:
                member = next(
                    (
                        item
                        for item in archive.getmembers()
                        if item.isfile() and Path(item.name).name in {"codex", f"codex-{target}"}
                    ),
                    None,
                )
                if member is None:
                    return False, f"Codex release archive missing codex binary: {url}"
                member.name = "codex"
                archive.extract(member, path=tmp)
            extracted = Path(tmp) / "codex"
            shutil.copy2(extracted, binary_path)
        binary_path.chmod(0o755)
        _ensure_codex_cli_shim()
    except Exception as exc:  # noqa: BLE001
        return False, f"failed to install Codex CLI from release `{url}`: {exc}"

    if _codex_bin():
        return True, f"codex cli installed from {url}"
    return False, f"codex binary installed to {binary_path} but is not in PATH"


def _subprocess_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _should_retry_after_npm_partial_install(argv: list[str], completed: subprocess.CompletedProcess[str]) -> bool:
    if os.environ.get("DOCKER_ENV") != "true":
        return False
    if not argv or argv[0] != "npm" or "@openai/codex" not in argv:
        return False
    message = ((completed.stderr or "") + "\n" + (completed.stdout or "")).lower()
    return "enotempty" in message or "/@openai/codex" in message


def _cleanup_codex_npm_partial_install() -> str:
    try:
        npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=15)
    except Exception as exc:  # noqa: BLE001
        return f"unable to locate npm global root: {exc}"

    if npm_root.returncode != 0:
        return "unable to locate npm global root"

    openai_root = Path(npm_root.stdout.strip()) / "@openai"
    removed: list[str] = []
    for path in [openai_root / "codex", *openai_root.glob(".codex-*")]:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            removed.append(str(path))
    return f"removed partial codex npm install: {', '.join(removed) if removed else 'none'}"


def _ensure_codex_cli_shim() -> None:
    if os.environ.get("DOCKER_ENV") != "true" or shutil.which("codex"):
        return

    cached_binary = Path.home() / ".codex" / "bin" / "codex"
    if cached_binary.exists():
        try:
            cached_binary.chmod(0o755)
            shim = Path("/usr/local/bin/codex")
            if shim.exists() or shim.is_symlink():
                shim.unlink()
            shim.symlink_to(cached_binary)
        except OSError:
            return
        return

    try:
        npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, timeout=15)
    except Exception:  # noqa: BLE001
        return

    if npm_root.returncode != 0:
        return

    codex_js = Path(npm_root.stdout.strip()) / "@openai" / "codex" / "bin" / "codex.js"
    shim = Path("/usr/local/bin/codex")
    if not codex_js.exists():
        return

    try:
        codex_js.chmod(0o755)
        if shim.exists() or shim.is_symlink():
            shim.unlink()
        shim.symlink_to(codex_js)
    except OSError:
        return


def _build_error_redirect(code: str, *, detail: str | None = None) -> str:
    base = codex_oauth_frontend_error_url()
    params = {"auth_error": code}
    if detail:
        params["detail"] = detail[:240]
    joiner = "&" if "?" in base else "?"
    return f"{base}{joiner}{urlencode(params)}"
