from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
from dataclasses import dataclass
from typing import Any

from ..llm.provider import get_chat_model

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class DirtyReviewDecision:
    delete: bool
    confidence: float
    category: str
    reason: str
    raw: dict[str, Any]


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


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes", "y"}:
            return True
        if v in {"false", "0", "no", "n"}:
            return False
    return default


def _as_confidence(value: Any) -> float:
    try:
        v = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, v))


class LlmDirtyReviewService:
    """LLM-assisted review for dirty document cleanup candidates."""

    def __init__(self, *, model: str | None = None, temperature: float = 0.0):
        model_name = str(model or "").strip() or "gpt-4o-mini"
        self._model = get_chat_model(model=model_name, temperature=temperature)

    def _build_prompt(
        self,
        *,
        doc_id: int,
        uri: str,
        title: str,
        doc_type: str,
        rule_reason: str,
        content_preview: str,
    ) -> str:
        return f"""
You are a strict data-quality reviewer for ingestion cleanup.
Decide whether this record should be deleted as dirty data.

Rules:
- delete=true only when record is clearly an intermediate/shell/garbled/status-wrapper page.
- keep valid article/content pages even if they contain some navigation or scripts.
- prefer conservative decisions for uncertain cases.

Output must be JSON only with keys:
delete (bool), confidence (0..1), category (string), reason (string).

Record:
id={doc_id}
doc_type={doc_type}
uri={uri}
title={title}
rule_reason={rule_reason}
content_preview={content_preview}
""".strip()

    def review_candidate(
        self,
        *,
        doc_id: int,
        uri: str,
        title: str,
        doc_type: str,
        rule_reason: str,
        content_preview: str,
    ) -> DirtyReviewDecision:
        prompt = self._build_prompt(
            doc_id=doc_id,
            uri=uri,
            title=title,
            doc_type=doc_type,
            rule_reason=rule_reason,
            content_preview=content_preview,
        )

        try:
            resp = self._model.invoke(prompt)
            text = str(getattr(resp, "content", resp))
        except Exception as exc:  # noqa: BLE001
            return DirtyReviewDecision(
                delete=False,
                confidence=0.0,
                category="llm_error",
                reason=f"llm_invoke_failed: {exc}",
                raw={},
            )

        parsed = _extract_json(text)
        if not isinstance(parsed, dict):
            return DirtyReviewDecision(
                delete=False,
                confidence=0.0,
                category="llm_parse_error",
                reason="llm_response_not_json",
                raw={"text": text[:600]},
            )

        return DirtyReviewDecision(
            delete=_as_bool(parsed.get("delete"), False),
            confidence=_as_confidence(parsed.get("confidence")),
            category=str(parsed.get("category") or "unspecified").strip()[:80],
            reason=str(parsed.get("reason") or "").strip()[:500],
            raw=parsed,
        )

    def review_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        max_workers: int = 8,
    ) -> dict[int, DirtyReviewDecision]:
        """Batch review candidates concurrently. Returns doc_id -> decision."""
        if not candidates:
            return {}
        workers = max(1, int(max_workers))
        if workers == 1:
            out: dict[int, DirtyReviewDecision] = {}
            for row in candidates:
                doc_id = int(row.get("doc_id") or 0)
                out[doc_id] = self.review_candidate(
                    doc_id=doc_id,
                    uri=str(row.get("uri") or ""),
                    title=str(row.get("title") or ""),
                    doc_type=str(row.get("doc_type") or ""),
                    rule_reason=str(row.get("rule_reason") or ""),
                    content_preview=str(row.get("content_preview") or ""),
                )
            return out

        out: dict[int, DirtyReviewDecision] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {}
            for row in candidates:
                doc_id = int(row.get("doc_id") or 0)
                future = executor.submit(
                    self.review_candidate,
                    doc_id=doc_id,
                    uri=str(row.get("uri") or ""),
                    title=str(row.get("title") or ""),
                    doc_type=str(row.get("doc_type") or ""),
                    rule_reason=str(row.get("rule_reason") or ""),
                    content_preview=str(row.get("content_preview") or ""),
                )
                future_map[future] = doc_id

            for future in as_completed(future_map):
                doc_id = int(future_map[future])
                try:
                    out[doc_id] = future.result()
                except Exception as exc:  # noqa: BLE001
                    out[doc_id] = DirtyReviewDecision(
                        delete=False,
                        confidence=0.0,
                        category="llm_error",
                        reason=f"llm_batch_failed: {exc}",
                        raw={},
                    )
        return out

