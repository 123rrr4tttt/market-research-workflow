"""Official access adapters (compat placeholder)."""

from __future__ import annotations

from typing import Any, Dict


def handle_official_access_api(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    """
    Placeholder adapter for official API access channels.
    Keep compatibility surface without forcing project-specific logic into trunk.
    """
    return {
        "inserted": 0,
        "skipped": 0,
        "candidates": [],
        "written": None,
        "message": "official_access.api adapter is a placeholder; provide project customization handler if needed.",
    }

