"""General-purpose article extraction helpers for detail pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..ingest.content_extraction import extract_main_text_from_html

try:  # pragma: no cover - optional dependency
    import trafilatura  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    trafilatura = None


@dataclass(frozen=True)
class ArticleExtractionResult:
    title: str | None
    content: str
    extractor: str
    confidence: str
    meta: dict[str, Any]


def extract_article_content_from_html(
    *,
    html: str,
    url: str | None = None,
    title: str | None = None,
) -> ArticleExtractionResult:
    raw_html = str(html or "").strip()
    if not raw_html:
        return ArticleExtractionResult(title=title, content="", extractor="none", confidence="low", meta={})

    if trafilatura is not None:
        try:
            extracted = trafilatura.extract(
                raw_html,
                url=url,
                include_comments=False,
                include_tables=False,
                output_format="txt",
                favor_precision=True,
            )
            if str(extracted or "").strip():
                return ArticleExtractionResult(
                    title=title,
                    content=str(extracted).strip(),
                    extractor="trafilatura",
                    confidence="high",
                    meta={"url": url},
                )
        except Exception:
            pass

    fallback = extract_main_text_from_html(raw_html)
    return ArticleExtractionResult(
        title=title,
        content=str(fallback or "").strip(),
        extractor="heuristic.main_content.v1",
        confidence="medium" if str(fallback or "").strip() else "low",
        meta={"url": url},
    )
