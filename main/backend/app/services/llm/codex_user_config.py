from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard

import tomllib

from ...settings.config import settings

_MAX_CONFIG_BYTES = 2 * 1024 * 1024


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _string_object_dict(value: object) -> dict[str, object] | None:
    if not _is_object_mapping(value):
        return None
    normalized: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        normalized[key] = item
    return normalized


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


@dataclass(frozen=True, slots=True)
class CodexUserModelConfig:
    model: str = ""
    model_provider: str = ""
    model_reasoning_effort: str = ""
    provider_config: dict[str, object] | None = None
    catalog_path: str = ""


def load_user_codex_model_config() -> CodexUserModelConfig:
    """Read only the model-selection subset of the user's Codex config.

    Authentication files remain copied by the isolated-home preparation path.
    MCP servers, plugins, apps, projects, and other user tooling are not
    imported here.
    """

    if bool(getattr(settings, "codex_cli_llm_ignore_user_config", False)):
        return CodexUserModelConfig()

    path = _user_codex_config_path()
    try:
        if not path.is_file() or path.stat().st_size > _MAX_CONFIG_BYTES:
            return CodexUserModelConfig()
        parsed_value: object = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeError):
        return CodexUserModelConfig()
    parsed = _string_object_dict(parsed_value)
    if parsed is None:
        return CodexUserModelConfig()

    model = _nonempty_text(parsed.get("model"))
    provider = _nonempty_text(parsed.get("model_provider"))
    reasoning = _nonempty_text(parsed.get("model_reasoning_effort"))
    provider_config: dict[str, object] | None = None
    if provider:
        providers = parsed.get("model_providers")
        provider_table = _string_object_dict(providers)
        candidate = provider_table.get(provider) if provider_table is not None else None
        provider_config = _string_object_dict(candidate)

    return CodexUserModelConfig(
        model=model,
        model_provider=provider,
        model_reasoning_effort=reasoning,
        provider_config=provider_config,
        catalog_path=_nonempty_text(parsed.get("model_catalog_json")),
    )


def resolve_codex_model(
    *,
    explicit_model: str | None = None,
    configured_model: str | None = None,
    user_config: CodexUserModelConfig | None = None,
) -> str:
    explicit = _nonempty_text(explicit_model)
    if explicit:
        return _normalize_model_alias(explicit, user_config)
    configured = _nonempty_text(configured_model)
    if configured:
        return _normalize_model_alias(configured, user_config)
    user = user_config or load_user_codex_model_config()
    return _normalize_model_alias(user.model, user) or _provider_default_model(user)


def resolve_codex_reasoning_effort(
    *,
    explicit_reasoning_effort: str | None = None,
    configured_reasoning_effort: str | None = None,
    user_config: CodexUserModelConfig | None = None,
) -> str:
    if explicit_reasoning_effort is not None:
        explicit = _nonempty_text(explicit_reasoning_effort)
        if explicit:
            return explicit
        return "none"
    configured = _nonempty_text(configured_reasoning_effort)
    if configured:
        return configured
    user = user_config or load_user_codex_model_config()
    return user.model_reasoning_effort or "none"


def _user_codex_config_path() -> Path:
    override = _nonempty_text(getattr(settings, "codex_cli_user_config_path", ""))
    if override:
        path = Path(override).expanduser()
        return path if path.is_absolute() else Path.cwd() / path

    codex_home = _nonempty_text(os.environ.get("CODEX_HOME"))
    if codex_home:
        return Path(codex_home).expanduser() / "config.toml"

    auth_path = Path(
        _nonempty_text(getattr(settings, "codex_cli_auth_path", "~/.codex/auth.json"))
    ).expanduser()
    return auth_path.parent / "config.toml"


def _nonempty_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_model_alias(
    candidate: str,
    user_config: CodexUserModelConfig | None,
) -> str:
    """Map a provider/upstream model name to its router model id.

    Codex MultiRouter model entries distinguish the externally selected model
    id from the upstream provider model.  A caller may legitimately know only
    the upstream name (for example, ``glm-5.3``); resolve that exact name to
    the unique router id (for example, ``glm-5.3-zhipu-glm-en``).
    """

    requested = _nonempty_text(candidate)
    if not requested:
        return ""
    user = user_config or load_user_codex_model_config()
    entries = user.provider_config.get("models") if user.provider_config else None
    if not _is_object_list(entries):
        return requested

    matches: list[tuple[int, str]] = []
    for entry_value in entries:
        entry = _string_object_dict(entry_value)
        if entry is None:
            continue
        model_id = _first_nonempty_text(entry, ("model", "slug", "id"))
        if not model_id:
            continue
        requested_key = requested.lower()
        exact_identity = requested_key in {
            model_id.lower(),
            _nonempty_text(entry.get("slug")).lower(),
            _nonempty_text(entry.get("id")).lower(),
        }
        exact_display = requested_key in {
            _nonempty_text(entry.get("display_name")).lower(),
            _nonempty_text(entry.get("displayName")).lower(),
        }
        upstream_alias = requested_key in {
            _nonempty_text(entry.get("upstreamModel")).lower(),
            _nonempty_text(entry.get("upstream_model")).lower(),
        }
        if not (exact_identity or exact_display or upstream_alias):
            continue
        rank = 0 if exact_identity else 1 if exact_display else 2
        matches.append((rank, model_id))

    if matches:
        return min(matches)[1]
    return requested


def _first_nonempty_text(entry: dict[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _nonempty_text(entry.get(key))
        if value:
            return value
    return ""


def _provider_default_model(user_config: CodexUserModelConfig) -> str:
    entries = (
        user_config.provider_config.get("models")
        if user_config.provider_config
        else None
    )
    if not _is_object_list(entries):
        return ""
    defaults: list[str] = []
    for entry_value in entries:
        entry = _string_object_dict(entry_value)
        if entry is None:
            continue
        is_default = entry.get("isDefault", entry.get("is_default", False))
        model_id = _first_nonempty_text(entry, ("model", "slug", "id"))
        if bool(is_default) and model_id:
            defaults.append(model_id)
    return defaults[0] if len(defaults) == 1 else ""


__all__ = [
    "CodexUserModelConfig",
    "list_codex_models",
    "load_user_codex_model_config",
    "resolve_codex_model",
    "resolve_codex_reasoning_effort",
]


def list_codex_models() -> dict[str, object]:
    """List the model choices exposed by the user's current Codex router."""

    user_config = load_user_codex_model_config()
    entries = user_config.provider_config.get("models") if user_config.provider_config else None
    if not _is_object_list(entries):
        entries = []

    items: list[dict[str, object]] = []
    for entry_value in entries:
        entry = _string_object_dict(entry_value)
        if entry is None:
            continue
        if bool(entry.get("hidden", False)):
            continue
        model_id = _first_nonempty_text(entry, ("model", "slug", "id"))
        if not model_id:
            continue
        efforts: list[str] = []
        raw_efforts: object = (
            entry.get("supported_reasoning_efforts")
            or entry.get("supportedReasoningEfforts")
            or entry.get("supported_reasoning_levels")
            or entry.get("supportedReasoningLevels")
            or []
        )
        for raw in raw_efforts if _is_object_list(raw_efforts) else []:
            if isinstance(raw, str):
                efforts.append(raw)
            else:
                effort_entry = _string_object_dict(raw)
                if effort_entry is None:
                    continue
                effort = _nonempty_text(
                    effort_entry.get("effort")
                    or effort_entry.get("reasoning_effort")
                    or effort_entry.get("reasoningEffort")
                )
                if effort:
                    efforts.append(effort)
        items.append(
            {
                "model": model_id,
                "display_name": _first_nonempty_text(entry, ("displayName", "display_name", "description"))
                or model_id,
                "is_default": bool(entry.get("isDefault", entry.get("is_default", False))),
                "supported_reasoning_efforts": list(dict.fromkeys(efforts)),
            }
        )

    return {
        "schema": "mrw.codex-models.v1",
        "provider": user_config.model_provider or None,
        "current_model": resolve_codex_model(user_config=user_config) or None,
        "current_reasoning_effort": resolve_codex_reasoning_effort(user_config=user_config) or None,
        "items": items,
    }
