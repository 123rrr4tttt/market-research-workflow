from __future__ import annotations

import json
import re
from typing import Any

from ..llm.provider import get_chat_model

_DEFAULT_MODEL = "gpt-4o-mini"
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_ZH_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_EN_CHAR_RE = re.compile(r"[A-Za-z]")


def _extract_text_content(resp: Any) -> str:
    content = getattr(resp, "content", resp)
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    chunks.append(item["text"])
                else:
                    chunks.append(str(item))
            else:
                chunks.append(str(item))
        return "\n".join(chunks)
    return str(content or "")


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _is_zh_alias(value: str) -> bool:
    return bool(_ZH_CHAR_RE.search(value or ""))


def _is_en_alias(value: str) -> bool:
    text = str(value or "")
    return bool(_EN_CHAR_RE.search(text)) and not _is_zh_alias(text)


def _normalize_alias_list(
    values: Any,
    *,
    max_aliases: int,
    reserved: set[str] | None = None,
) -> list[str]:
    if not isinstance(values, list):
        return []

    out: list[str] = []
    seen: set[str] = set()
    reserved_norm = {x.casefold() for x in (reserved or set()) if x}
    for item in values:
        if not isinstance(item, str):
            continue
        alias = " ".join(item.strip().split())
        if not alias:
            continue
        norm = alias.casefold()
        if norm in seen or norm in reserved_norm:
            continue
        seen.add(norm)
        out.append(alias)
        if len(out) >= max_aliases:
            break
    return out


def _split_mixed_aliases(values: Any, *, max_aliases: int, reserved: set[str]) -> tuple[list[str], list[str]]:
    zh_pool: list[str] = []
    en_pool: list[str] = []
    if isinstance(values, list):
        for item in values:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if not text:
                continue
            if _is_zh_alias(text):
                zh_pool.append(text)
            elif _is_en_alias(text):
                en_pool.append(text)

    zh = _normalize_alias_list(zh_pool, max_aliases=max_aliases, reserved=reserved)
    en = _normalize_alias_list(en_pool, max_aliases=max_aliases, reserved=reserved)
    return zh, en


def _build_prompt(*, node_type: str, display_name: str, canonical_id: str, max_aliases: int) -> str:
    return (
        "You generate bilingual graph node aliases for entity resolution.\\n"
        "Return JSON only. Do not add markdown.\\n"
        "Schema:\\n"
        "{\\n"
        '  "aliases": {\\n'
        '    "zh": ["..."],\\n'
        '    "en": ["..."]\\n'
        "  }\\n"
        "}\\n"
        "Rules:\\n"
        f"- Up to {max_aliases} aliases per language.\\n"
        "- Keep aliases concise and realistic; avoid explanations.\\n"
        "- Do not repeat display_name or canonical_id verbatim.\\n"
        "- If uncertain, return empty arrays.\\n"
        "Input:\\n"
        f"node_type={node_type}\\n"
        f"display_name={display_name}\\n"
        f"canonical_id={canonical_id}"
    )


def generate_bilingual_aliases(
    *,
    node_type: str,
    display_name: str,
    canonical_id: str,
    model: str | None = None,
    max_aliases: int = 8,
) -> dict[str, list[str]]:
    """Generate bilingual aliases with LLM. Any failure falls back to empty lists."""
    fallback = {"zh": [], "en": []}

    nt = str(node_type or "").strip()
    dn = str(display_name or "").strip()
    cid = str(canonical_id or "").strip()
    if not (dn or cid):
        return fallback

    limit = max(1, int(max_aliases))
    reserved = {dn, cid}
    prompt = _build_prompt(node_type=nt, display_name=dn, canonical_id=cid, max_aliases=limit)

    try:
        llm = get_chat_model(model=(str(model).strip() if model else _DEFAULT_MODEL), temperature=0)
        raw_text = _extract_text_content(llm.invoke(prompt))
        payload = _extract_json(raw_text)
        if not isinstance(payload, dict):
            return fallback
    except Exception:
        return fallback

    aliases = payload.get("aliases") if isinstance(payload.get("aliases"), dict) else {}
    zh_values = aliases.get("zh")
    en_values = aliases.get("en")

    # Backward-compatible keys for looser outputs.
    if zh_values is None:
        zh_values = payload.get("zh_aliases") or payload.get("aliases_zh")
    if en_values is None:
        en_values = payload.get("en_aliases") or payload.get("aliases_en")

    zh = _normalize_alias_list(zh_values, max_aliases=limit, reserved=reserved)
    en = _normalize_alias_list(en_values, max_aliases=limit, reserved=reserved)

    if not zh and not en:
        mixed = payload.get("aliases")
        if isinstance(mixed, list):
            zh, en = _split_mixed_aliases(mixed, max_aliases=limit, reserved=reserved)

    return {"zh": zh, "en": en}


def build_bilingual_alias_payload(
    *,
    node_type: str,
    display_name: str,
    canonical_id: str,
    model: str | None = None,
    max_aliases: int = 8,
) -> dict[str, Any]:
    """Convenience helper returning node info plus generated bilingual aliases."""
    return {
        "node_type": str(node_type or "").strip(),
        "display_name": str(display_name or "").strip(),
        "canonical_id": str(canonical_id or "").strip(),
        "aliases": generate_bilingual_aliases(
            node_type=node_type,
            display_name=display_name,
            canonical_id=canonical_id,
            model=model,
            max_aliases=max_aliases,
        ),
    }
