from __future__ import annotations

import json
from typing import TypeGuard


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_string_object(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _message_content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if _is_object_list(content):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif _is_string_object(item):
                text_value = item.get("text") or item.get("content")
                if isinstance(text_value, str):
                    parts.append(text_value)
        return "\n".join(parts)
    return str(content or "")


def extract_json_payload(content: object) -> dict[str, object] | None:
    text = _message_content_text(content).strip()
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
        parsed: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if _is_string_object(parsed) else None
