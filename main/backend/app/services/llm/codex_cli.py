from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import codex_invocation_failures
from ...settings.config import BACKEND_ROOT, settings
from ..codex_oauth import has_valid_token_sink
from .codex_app_server import get_persistent_codex_core
from .codex_user_config import (
    load_user_codex_model_config,
    resolve_codex_model,
    resolve_codex_reasoning_effort,
)


def _codex_failure(
    code: str,
    message: str,
    *,
    operation: str,
    site: str,
    public_message: str | None = None,
    **context: Any,
) -> Failure:
    details: dict[str, Any] = {
        "owner": "codex.invocation",
        "operation": operation,
        "site": site,
        "public_exception": "RuntimeError",
        "public_message": message if public_message is None else public_message,
        "witness": "test:test_w01_effect_failures",
    }
    details.update(context)
    return codex_invocation_failures.fail(code, message, details)


def _raise_codex_failure(failure: Failure) -> NoReturn:
    if not codex_invocation_failures.matches(failure):
        # kit:boundary owner=codex.invocation.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_codex_cli_failure_lift_rejects_invalid_registered_context
        raise TypeError("codex invocation failure lift requires a registered failure")
    context = failure.context or {}
    required = {"owner", "operation", "site", "public_exception", "public_message"}
    if required - set(context):
        # kit:boundary owner=codex.invocation.failure_lift class=PROGRAMMER_DEFECT failure_family=codex.invocation.failure witness=test:test_codex_cli_failure_lift_rejects_invalid_registered_context
        raise TypeError("codex invocation failure lift context is incomplete")
    exception_name = context.get("public_exception")
    if exception_name == "ValueError":
        # kit:boundary owner=codex.invocation.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_codex_cli_effect_failure_is_closed_and_public_prompt_abi_is_preserved
        raise ValueError(str(context["public_message"]))
    if exception_name != "RuntimeError":
        # kit:boundary owner=codex.invocation.failure_lift class=PROGRAMMER_DEFECT failure_family=codex.invocation.failure witness=test:test_codex_cli_failure_lift_rejects_invalid_registered_context
        raise TypeError("codex invocation failure lift only supports the retained ABI")
    # kit:boundary owner=codex.invocation.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=codex.invocation.failure witness=test:test_codex_cli_effect_retains_subprocess_status_without_message_parsing
    raise RuntimeError(str(context["public_message"]))


class CodexCliChatModel:
    """Small LangChain-compatible adapter for local Codex CLI auth fallback."""

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout_seconds: int | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.model = resolve_codex_model(
            explicit_model=model,
            configured_model=getattr(settings, "codex_cli_llm_model", ""),
        )
        self.timeout_seconds = int(
            timeout_seconds or settings.codex_cli_llm_timeout_seconds or 120
        )
        self.reasoning_effort = resolve_codex_reasoning_effort(
            explicit_reasoning_effort=reasoning_effort,
            configured_reasoning_effort=getattr(
                settings, "codex_cli_llm_reasoning_effort", ""
            ),
        )

    def invoke(self, prompt: Any) -> SimpleNamespace:
        text = invoke_codex_cli(
            str(prompt or ""),
            model=self.model or None,
            timeout_seconds=self.timeout_seconds,
            reasoning_effort=self.reasoning_effort,
        )
        return SimpleNamespace(content=text)


def codex_cli_llm_available() -> bool:
    if not bool(getattr(settings, "codex_cli_llm_fallback_enabled", True)):
        return False
    command = (
        str(getattr(settings, "codex_cli_llm_command", "codex") or "codex").strip()
        or "codex"
    )
    return bool(_resolve_codex_bin(command) and has_valid_token_sink())


def invoke_codex_cli(
    prompt: str,
    *,
    model: str | None = None,
    timeout_seconds: int | None = None,
    reasoning_effort: str | None = None,
) -> str:
    outcome = invoke_codex_cli_effect(
        prompt,
        model=model,
        timeout_seconds=timeout_seconds,
        reasoning_effort=reasoning_effort,
    )
    if isinstance(outcome, Failure):
        _raise_codex_failure(outcome)
    return outcome


def invoke_codex_cli_effect(
    prompt: str,
    *,
    model: str | None = None,
    timeout_seconds: int | None = None,
    reasoning_effort: str | None = None,
) -> str | Failure:
    if bool(getattr(settings, "codex_cli_llm_persistent_enabled", True)):
        try:
            mounted = get_persistent_codex_core(
                codex_bin_resolver=lambda: _resolve_codex_bin(
                    str(getattr(settings, "codex_cli_llm_command", "codex") or "codex")
                ),
                workdir_resolver=_resolve_codex_workdir,
                disabled_features_resolver=_disabled_features,
            )
            return mounted.invoke(
                prompt,
                model=model,
                timeout_seconds=timeout_seconds,
                reasoning_effort=reasoning_effort,
            ).content
        except RuntimeError as exc:
            if not bool(getattr(settings, "codex_cli_llm_fallback_enabled", True)):
                return _codex_failure(
                    "rpc_error",
                    "codex persistent app-server invocation failed",
                    operation="codex_cli.persistent_invoke",
                    site="invoke_codex_cli",
                    public_message=str(exc) or "codex persistent app-server invocation failed",
                    cause=exc,
                )
    return _invoke_codex_cli_once_effect(
        prompt,
        model=model,
        timeout_seconds=timeout_seconds,
        reasoning_effort=reasoning_effort,
    )


def _invoke_codex_cli_once(
    prompt: str,
    *,
    model: str | None = None,
    timeout_seconds: int | None = None,
    reasoning_effort: str | None = None,
) -> str:
    outcome = _invoke_codex_cli_once_effect(
        prompt,
        model=model,
        timeout_seconds=timeout_seconds,
        reasoning_effort=reasoning_effort,
    )
    if isinstance(outcome, Failure):
        _raise_codex_failure(outcome)
    return outcome


def _invoke_codex_cli_once_effect(
    prompt: str,
    *,
    model: str | None = None,
    timeout_seconds: int | None = None,
    reasoning_effort: str | None = None,
) -> str | Failure:
    resolved_prompt = str(prompt or "").strip()
    if not resolved_prompt:
        return _codex_failure(
            "prompt_required",
            "prompt is required",
            operation="codex_cli.prompt_validate",
            site="_invoke_codex_cli_once",
            public_exception="ValueError",
        )
    command = (
        str(getattr(settings, "codex_cli_llm_command", "codex") or "codex").strip()
        or "codex"
    )
    codex_bin = _resolve_codex_bin(command)
    if not codex_bin:
        return _codex_failure(
            "cli_not_installed",
            "codex cli is not installed",
            operation="codex_cli.resolve_binary",
            site="_invoke_codex_cli_once",
        )
    if not has_valid_token_sink():
        return _codex_failure(
            "cli_auth_unavailable",
            "codex cli auth is not available",
            operation="codex_cli.auth_check",
            site="_invoke_codex_cli_once",
        )

    workdir = _resolve_codex_workdir()
    user_config = load_user_codex_model_config()
    resolved_model = resolve_codex_model(
        explicit_model=model,
        configured_model=getattr(settings, "codex_cli_llm_model", ""),
        user_config=user_config,
    )
    resolved_reasoning_effort = resolve_codex_reasoning_effort(
        explicit_reasoning_effort=reasoning_effort,
        configured_reasoning_effort=getattr(
            settings, "codex_cli_llm_reasoning_effort", ""
        ),
        user_config=user_config,
    )
    timeout = max(
        5, int(timeout_seconds or settings.codex_cli_llm_timeout_seconds or 120)
    )
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")

    args = [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--cd",
        workdir,
        "--color",
        "never",
    ]
    if resolved_model:
        args.extend(["--model", resolved_model])
    if bool(getattr(settings, "codex_cli_llm_ignore_user_config", True)):
        args.append("--ignore-user-config")
    for feature in _disabled_features():
        args.extend(["--disable", feature])
    if resolved_reasoning_effort:
        args.extend(["-c", f'model_reasoning_effort="{resolved_reasoning_effort}"'])
    args.append(resolved_prompt)

    try:
        completed = subprocess.run(
            args,
            cwd=workdir,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return _codex_failure(
            "endpoint_timeout",
            "codex cli invocation timed out",
            operation="codex_cli.subprocess",
            site="_invoke_codex_cli_once",
            timeout_seconds=timeout,
            cause=exc,
        )
    except OSError as exc:
        return _codex_failure(
            "cli_command_failed",
            "codex cli command could not be started",
            operation="codex_cli.subprocess",
            site="_invoke_codex_cli_once",
            public_message=str(exc) or "codex cli command could not be started",
            cause=exc,
        )
    output = _extract_codex_answer(completed.stdout)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return _codex_failure(
            "cli_command_failed",
            "codex cli command failed",
            operation="codex_cli.subprocess",
            site="_invoke_codex_cli_once",
            public_message=f"codex cli failed: {detail[:500]}",
            returncode=completed.returncode,
            stderr=detail[:500],
        )
    if not output:
        return _codex_failure(
            "empty_output",
            "codex cli returned empty output",
            operation="codex_cli.output_decode",
            site="_invoke_codex_cli_once",
        )
    return output


def _extract_codex_answer(stdout: str) -> str:
    text = str(stdout or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    lines = text.splitlines()
    cutoff = next(
        (idx for idx, line in enumerate(lines) if line.strip() == "tokens used"),
        len(lines),
    )
    lines = lines[:cutoff]
    marker = next(
        (idx for idx in range(len(lines) - 1, -1, -1) if lines[idx].strip() == "codex"),
        -1,
    )
    if marker >= 0:
        lines = lines[marker + 1 :]
    content_lines = [line for line in lines if line.strip()]
    if not content_lines:
        return ""
    if len(content_lines) % 2 == 0:
        mid = len(content_lines) // 2
        if content_lines[:mid] == content_lines[mid:]:
            content_lines = content_lines[:mid]
    return "\n".join(content_lines).strip()


def _disabled_features() -> list[str]:
    raw = str(getattr(settings, "codex_cli_llm_disabled_features", "") or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _resolve_codex_workdir() -> str:
    raw = str(getattr(settings, "codex_cli_llm_workdir", "") or "").strip()
    path = Path(raw).expanduser() if raw else Path(tempfile.gettempdir())
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        return str(BACKEND_ROOT)
    return str(path)


def _resolve_codex_bin(command: str) -> str | None:
    resolved_command = str(command or "").strip() or "codex"
    if "/" in resolved_command:
        path = Path(resolved_command).expanduser()
        return str(path) if path.exists() else None
    found = shutil.which(resolved_command)
    if found:
        return found
    for candidate in (
        Path("/Applications/Codex.app/Contents/Resources/codex"),
        Path.home() / ".local/bin/codex",
        Path("/opt/homebrew/bin/codex"),
        Path("/usr/local/bin/codex"),
    ):
        if candidate.exists():
            return str(candidate)
    return None
