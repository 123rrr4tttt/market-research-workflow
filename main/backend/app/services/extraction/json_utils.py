from __future__ import annotations

import json
from typing import Any, Optional


def extract_json_payload(content: str) -> Optional[dict[str, Any]]:
    text = (content or "").strip()
    if not text:
        return None
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            text = text[start:end].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
