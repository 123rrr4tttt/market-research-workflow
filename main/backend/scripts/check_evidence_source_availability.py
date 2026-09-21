"""Shared fail-closed contract for repository evidence inputs."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any


EVIDENCE_SOURCE_AVAILABLE = "EVIDENCE_SOURCE_AVAILABLE"
EVIDENCE_SOURCE_UNAVAILABLE = "EVIDENCE_SOURCE_UNAVAILABLE"

NON_AUTHORITATIVE_AUTHORITY_CEILING = {
    "authoritative": False,
    "closure_claim_allowed": False,
    "live_evidence": False,
    "promotion_allowed": False,
}


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def classify_required_evidence(
    root: Path,
    required: Mapping[str, Path | str],
) -> dict[str, Any]:
    """Classify required repository evidence without reading fallback sources."""

    resolved = {
        str(label): (Path(value) if Path(value).is_absolute() else root / Path(value)).resolve()
        for label, value in required.items()
    }
    missing = [
        {"label": label, "path": _display_path(path, root)}
        for label, path in sorted(resolved.items())
        if not path.is_file()
    ]
    return {
        "status": EVIDENCE_SOURCE_UNAVAILABLE if missing else EVIDENCE_SOURCE_AVAILABLE,
        "required_paths": [
            {
                "label": label,
                "path": _display_path(path, root),
                "available": path.is_file(),
            }
            for label, path in sorted(resolved.items())
        ],
        "missing_paths": missing,
        "authority_ceiling": dict(NON_AUTHORITATIVE_AUTHORITY_CEILING),
    }


def merge_evidence_sources(*sources: Mapping[str, Any]) -> dict[str, Any]:
    """Merge child availability contracts while preserving fail-closed status."""

    required_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    missing_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for source in sources:
        for row in source.get("required_paths") or []:
            if isinstance(row, Mapping):
                normalized = {
                    "label": str(row.get("label") or "evidence"),
                    "path": str(row.get("path") or ""),
                    "available": row.get("available") is True,
                }
                required_by_key[(normalized["label"], normalized["path"])] = normalized
        for row in source.get("missing_paths") or []:
            if isinstance(row, Mapping):
                normalized_missing = {
                    "label": str(row.get("label") or "evidence"),
                    "path": str(row.get("path") or ""),
                }
                missing_by_key[(normalized_missing["label"], normalized_missing["path"])] = normalized_missing

    missing = list(missing_by_key.values())
    return {
        "status": EVIDENCE_SOURCE_UNAVAILABLE if missing else EVIDENCE_SOURCE_AVAILABLE,
        "required_paths": list(required_by_key.values()),
        "missing_paths": missing,
        "authority_ceiling": dict(NON_AUTHORITATIVE_AUTHORITY_CEILING),
    }


def unavailable_error(source: Mapping[str, Any]) -> str:
    paths = [str(row.get("path") or "") for row in source.get("missing_paths") or [] if isinstance(row, Mapping)]
    return f"{EVIDENCE_SOURCE_UNAVAILABLE}: missing required evidence: {paths}"
