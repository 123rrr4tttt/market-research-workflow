from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GraphAliasCandidate:
    alias_text: str
    alias_norm: str
    alias_type: str


class GraphNodeAliasResolver:
    """Resolve alias candidates from a projected graph node payload."""

    _alias_keys = ("label", "name", "text", "canonical_name", "title")

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = unicodedata.normalize("NFKC", str(value or ""))
        text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
        text = re.sub(r"\s+", " ", text).strip().lower()
        return text

    def resolve(self, node_payload: dict[str, Any]) -> list[GraphAliasCandidate]:
        out: list[GraphAliasCandidate] = []
        seen: set[tuple[str, str]] = set()

        for key in self._alias_keys:
            raw = str(node_payload.get(key) or "").strip()
            if not raw:
                continue
            norm = self._normalize_text(raw)
            if not norm:
                continue
            alias_type = "display" if key in ("label", "name") else "raw"
            sig = (norm, alias_type)
            if sig in seen:
                continue
            seen.add(sig)
            out.append(GraphAliasCandidate(alias_text=raw, alias_norm=norm, alias_type=alias_type))

        canonical_id = str(node_payload.get("id") or "").strip()
        if canonical_id:
            norm = self._normalize_text(canonical_id)
            if norm and (norm, "id") not in seen:
                out.append(GraphAliasCandidate(alias_text=canonical_id, alias_norm=norm, alias_type="id"))

        return out
