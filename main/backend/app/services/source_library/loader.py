from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import source_library_loader_failures

logger = logging.getLogger(__name__)
_FAILURE_WITNESS = "test:test_w01_source_export_failures"


def _loader_failure(code: str, message: str, *, site: str, **details: Any) -> Failure:
    context: dict[str, Any] = {
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
        # kit:boundary owner=source_library.loader.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_source_export_failures
        raise TypeError("source-library loader failure lift context is incomplete or inconsistent")
    if cause is None:
        # kit:boundary owner=source_library.loader.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.loader.failure witness=test:test_w01_source_export_failures
        raise RuntimeError(str(context["public_message"]))
    # kit:boundary owner=source_library.loader.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.loader.failure witness=test:test_w01_source_export_failures
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


def try_load_single_file(path: Path) -> list[dict] | Failure:
    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return _loader_failure(
                "yaml_parser_unavailable",
                f"Cannot parse YAML file {path}; install pyyaml or use JSON files.",
                site="try_load_single_file.yaml_import",
                cause=exc,
            )
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)  # type: ignore[attr-defined]
    else:
        return []

    if data is None:
        return []
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            return [x for x in data["items"] if isinstance(x, dict)]
        return [data]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _load_single_file(path: Path) -> list[dict]:
    outcome = try_load_single_file(path)
    if isinstance(outcome, Failure):
        cause = (outcome.context or {}).get("cause")
        _raise_loader_failure(outcome, cause=cause if isinstance(cause, BaseException) else None)
    return outcome


def _load_dir(base: Path) -> list[dict]:
    if not base.exists() or not base.is_dir():
        return []
    items: list[dict] = []
    patterns = ["*.json", "*.yaml", "*.yml"]
    for pattern in patterns:
        for path in sorted(base.glob(pattern)):
            loaded = _load_single_file(path)
            if loaded:
                items.extend(loaded)
    return items


def load_global_library_files() -> Dict[str, List[Dict[str, Any]]]:
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


def load_project_library_files(project_key: str | None) -> Dict[str, List[Dict[str, Any]]]:
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
