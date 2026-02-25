from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


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


def _load_single_file(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    elif suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Cannot parse YAML file {path}; install pyyaml or use JSON files."
            ) from exc
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

