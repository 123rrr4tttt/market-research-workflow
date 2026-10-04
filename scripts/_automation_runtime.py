"""Shared runtime helpers for root automation scripts."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from mrw_functorial_kit.business_line_vocabulary import (  # noqa: E402
    BUSINESS_LINE_KEYS as CANONICAL_LINE_KEYS,
    WORKER_REQUIRED_BUSINESS_LINE_KEYS as WORKER_REQUIRED_LINE_KEYS,
)


def repo_root() -> Path:
    return _ROOT


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
