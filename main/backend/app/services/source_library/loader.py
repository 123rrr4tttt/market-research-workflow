from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable, NoReturn, Protocol, TypeGuard, runtime_checkable

from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import source_library_loader_failures

logger = logging.getLogger(__name__)
_FAILURE_WITNESS = "test:test_source_configuration_and_report_export_failures"


@runtime_checkable
class _YamlModule(Protocol):
    safe_load: Callable[[object], object]


def _is_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _loader_failure(code: str, message: str, *, site: str, **details: object) -> Failure:
    context: dict[str, object] = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": source_library_loader_failures.name,
        "operation": "source_library.loader",
        "owner": "source_library.loader",
        "public_exception": "RuntimeError",
        "public_message": message,
        "site": site,
        "witness": _FAILURE_WITNESS,
    }
    context.update(details)
    return source_library_loader_failures.fail(code, message, context)


def _raise_loader_failure(failure: Failure, *, cause: BaseException | None = None) -> NoReturn:
    context = failure.context or {}
    required = {"boundary_class", "failure_family", "operation", "owner", "public_exception", "public_message", "site", "witness"}
    if (
        not source_library_loader_failures.matches(failure)
        or required - set(context)
        or context.get("failure_family") != source_library_loader_failures.name
        or context.get("boundary_class") != "PURE_CONTRACT_FAILURE"
        or context.get("public_exception") != "RuntimeError"
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=source_library.loader.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_source_configuration_and_report_export_failures
        raise TypeError("source-library loader failure lift context is incomplete or inconsistent")
    if cause is None:
        # kit:boundary owner=source_library.loader.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.loader.failure witness=test:test_source_configuration_and_report_export_failures
        raise RuntimeError(str(context["public_message"]))
    # kit:boundary owner=source_library.loader.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.loader.failure witness=test:test_source_configuration_and_report_export_failures
    raise RuntimeError(str(context["public_message"])) from cause


def _source_library_root() -> Path:
    """Root path for 信息源库 (contains global/ and projects/)."""
    env_root = os.environ.get("SOURCE_LIBRARY_ROOT")
    if env_root:
        return Path(env_root)
    # Docker: backend at /app, 信息源库 mounted at /app/信息源库
    if os.environ.get("DOCKER_ENV") == "true" or os.path.exists("/.dockerenv"):
        return Path("/app/信息源库")
    # Local: app/services/source_library/loader.py -> app -> backend -> main -> repo
    try:
        return Path(__file__).resolve().parents[5] / "信息源库"
    except IndexError:
        return Path(__file__).resolve().parents[4] / "信息源库"


def try_load_single_file(path: Path) -> list[dict[str, object]] | Failure:
    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            data: object = json.load(f)
    elif suffix in {".yaml", ".yml"}:
        try:
            from importlib import import_module

            candidate = import_module("yaml")
        except Exception as exc:  # noqa: BLE001
            return _loader_failure(
                "yaml_parser_unavailable",
                f"Cannot parse YAML file {path}; install pyyaml or use JSON files.",
                site="try_load_single_file.yaml_import",
                cause=exc,
            )
        if not isinstance(candidate, _YamlModule):
            return _loader_failure(
                "yaml_parser_invalid",
                f"Cannot use YAML parser for {path}; safe_load is unavailable.",
                site="try_load_single_file.yaml_protocol",
            )
        with path.open("r", encoding="utf-8") as stream:
            data = candidate.safe_load(stream)
    else:
        return []

    if data is None:
        return []
    if _is_object(data):
        raw_items = data.get("items")
        if _is_object_list(raw_items):
            return [dict(item) for item in raw_items if _is_object(item)]
        return [dict(data)]
    if _is_object_list(data):
        return [dict(item) for item in data if _is_object(item)]
    return []


def _load_single_file(path: Path) -> list[dict[str, object]]:
    outcome = try_load_single_file(path)
    if isinstance(outcome, Failure):
        cause = (outcome.context or {}).get("cause")
        _raise_loader_failure(outcome, cause=cause if isinstance(cause, BaseException) else None)
    return outcome


def _load_dir(base: Path) -> list[dict[str, object]]:
    if not base.exists() or not base.is_dir():
        return []
    items: list[dict[str, object]] = []
    patterns = ["*.json", "*.yaml", "*.yml"]
    for pattern in patterns:
        for path in sorted(base.glob(pattern)):
            loaded = _load_single_file(path)
            if loaded:
                items.extend(loaded)
    return items


def load_global_library_files() -> dict[str, list[dict[str, object]]]:
    root = _source_library_root() / "global"
    channels = _load_dir(root / "channels")
    source_items = _load_dir(root / "items")
    logger.info(
        "loaded source-library files from %s: channels=%d items=%d",
        root,
        len(channels),
        len(source_items),
    )
    return {"channels": channels, "items": source_items}


def load_project_library_files(project_key: str | None) -> dict[str, list[dict[str, object]]]:
    key = (project_key or "").strip().lower()
    if not key:
        return {"channels": [], "items": []}
    root = _source_library_root() / "projects" / key
    channels = _load_dir(root / "channels")
    source_items = _load_dir(root / "items")
    logger.info(
        "loaded project source-library files from %s: channels=%d items=%d",
        root,
        len(channels),
        len(source_items),
    )
    return {"channels": channels, "items": source_items}
