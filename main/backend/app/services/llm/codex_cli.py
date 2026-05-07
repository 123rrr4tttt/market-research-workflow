from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ...settings.config import BACKEND_ROOT, settings
from ..codex_oauth import has_valid_token_sink


class CodexCliChatModel:
    """Small LangChain-compatible adapter for local Codex CLI auth fallback."""

    def __init__(self, *, model: str | None = None, timeout_seconds: int | None = None) -> None:
        self.model = str(model or settings.codex_cli_llm_model or "gpt-5.4-mini").strip() or "gpt-5.4-mini"
        self.timeout_seconds = int(timeout_seconds or settings.codex_cli_llm_timeout_seconds or 120)

    def invoke(self, prompt: Any) -> SimpleNamespace:
        text = invoke_codex_cli(str(prompt or ""), model=self.model, timeout_seconds=self.timeout_seconds)
        return SimpleNamespace(content=text)


def codex_cli_llm_available() -> bool:
    if not bool(getattr(settings, "codex_cli_llm_fallback_enabled", True)):
        return False
    command = str(getattr(settings, "codex_cli_llm_command", "codex") or "codex").strip() or "codex"
    return bool(shutil.which(command) and has_valid_token_sink())


def invoke_codex_cli(prompt: str, *, model: str | None = None, timeout_seconds: int | None = None) -> str:
    resolved_prompt = str(prompt or "").strip()
    if not resolved_prompt:
        raise ValueError("prompt is required")
    command = str(getattr(settings, "codex_cli_llm_command", "codex") or "codex").strip() or "codex"
    codex_bin = shutil.which(command)
    if not codex_bin:
        raise RuntimeError("codex cli is not installed")
    if not has_valid_token_sink():
        raise RuntimeError("codex cli auth is not available")

    workdir = str(BACKEND_ROOT)
    resolved_model = str(model or settings.codex_cli_llm_model or "gpt-5.4-mini").strip() or "gpt-5.4-mini"
    timeout = max(5, int(timeout_seconds or settings.codex_cli_llm_timeout_seconds or 120))
    env = dict(os.environ)
    env.setdefault("NO_COLOR", "1")

    completed = subprocess.run(
        [
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
            resolved_prompt,
        ],
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
