from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ...settings.config import BACKEND_ROOT, settings
from .codex_app_server import get_persistent_codex_core
from ..codex_oauth import has_valid_token_sink


class CodexCliChatModel:
    """Small LangChain-compatible adapter for local Codex CLI auth fallback."""

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout_seconds: int | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.model = str(model or settings.codex_cli_llm_model or "gpt-5.4-mini").strip() or "gpt-5.4-mini"
        self.timeout_seconds = int(timeout_seconds or settings.codex_cli_llm_timeout_seconds or 120)
        self.reasoning_effort = str(
            reasoning_effort if reasoning_effort is not None else getattr(settings, "codex_cli_llm_reasoning_effort", "none")
        ).strip()

    def invoke(self, prompt: Any) -> SimpleNamespace:
        text = invoke_codex_cli(
            str(prompt or ""),
            model=self.model,
            timeout_seconds=self.timeout_seconds,
            reasoning_effort=self.reasoning_effort,
        )
        return SimpleNamespace(content=text)


def codex_cli_llm_available() -> bool:
    if not bool(getattr(settings, "codex_cli_llm_fallback_enabled", True)):
        return False
    command = str(getattr(settings, "codex_cli_llm_command", "codex") or "codex").strip() or "codex"
    return bool(_resolve_codex_bin(command) and has_valid_token_sink())


def invoke_codex_cli(
    prompt: str,
    *,
    model: str | None = None,
    timeout_seconds: int | None = None,
    reasoning_effort: str | None = None,
) -> str:
    if bool(getattr(settings, "codex_cli_llm_persistent_enabled", True)):
        try:
            mounted = get_persistent_codex_core(
                codex_bin_resolver=lambda: _resolve_codex_bin(str(getattr(settings, "codex_cli_llm_command", "codex") or "codex")),
                workdir_resolver=_resolve_codex_workdir,
                disabled_features_resolver=_disabled_features,
            )
            return mounted.invoke(
                prompt,
                model=model,
                timeout_seconds=timeout_seconds,
                reasoning_effort=reasoning_effort,
            ).content
        except Exception:
            if not bool(getattr(settings, "codex_cli_llm_fallback_enabled", True)):
                raise
    return _invoke_codex_cli_once(
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
    resolved_prompt = str(prompt or "").strip()
    if not resolved_prompt:
        raise ValueError("prompt is required")
    command = str(getattr(settings, "codex_cli_llm_command", "codex") or "codex").strip() or "codex"
    codex_bin = _resolve_codex_bin(command)
    if not codex_bin:
        raise RuntimeError("codex cli is not installed")
    if not has_valid_token_sink():
        raise RuntimeError("codex cli auth is not available")

    workdir = _resolve_codex_workdir()
    resolved_model = str(model or settings.codex_cli_llm_model or "gpt-5.4-mini").strip() or "gpt-5.4-mini"
    resolved_reasoning_effort = str(
        reasoning_effort if reasoning_effort is not None else getattr(settings, "codex_cli_llm_reasoning_effort", "none")
    ).strip()
    timeout = max(5, int(timeout_seconds or settings.codex_cli_llm_timeout_seconds or 120))
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
        "--model",
        resolved_model,
        "--color",
        "never",
    ]
    if bool(getattr(settings, "codex_cli_llm_ignore_user_config", True)):
        args.append("--ignore-user-config")
    for feature in _disabled_features():
        args.extend(["--disable", feature])
    if resolved_reasoning_effort:
        args.extend(["-c", f'model_reasoning_effort="{resolved_reasoning_effort}"'])
    args.append(resolved_prompt)

    completed = subprocess.run(
        args,
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = _extract_codex_answer(completed.stdout)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"codex cli failed: {detail[:500]}")
    if not output:
        raise RuntimeError("codex cli returned empty output")
    return output


def _extract_codex_answer(stdout: str) -> str:
    text = str(stdout or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    lines = text.splitlines()
    cutoff = next((idx for idx, line in enumerate(lines) if line.strip() == "tokens used"), len(lines))
    lines = lines[:cutoff]
    marker = next((idx for idx in range(len(lines) - 1, -1, -1) if lines[idx].strip() == "codex"), -1)
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
