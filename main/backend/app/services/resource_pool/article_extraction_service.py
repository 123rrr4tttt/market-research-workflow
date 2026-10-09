"""General-purpose article extraction helpers for detail pages."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Protocol, runtime_checkable

from ..ingest.content_extraction import extract_main_text_from_html


@runtime_checkable
class _TrafilaturaModule(Protocol):
    def extract(
        self,
        html: str,
        *,
        url: str | None,
        include_comments: bool,
        include_tables: bool,
        output_format: str,
        favor_precision: bool,
    ) -> object: ...


def _load_trafilatura() -> _TrafilaturaModule | None:
    try:  # pragma: no cover - optional dependency
        module = import_module("trafilatura")
        return module if isinstance(module, _TrafilaturaModule) else None
    except Exception:  # pragma: no cover - optional dependency
        return None


trafilatura: _TrafilaturaModule | None = _load_trafilatura()


def _extract_with_trafilatura(raw_html: str, url: str | None) -> str:
    if trafilatura is None:
        return ""
    value = trafilatura.extract(
        raw_html,
        url=url,
        include_comments=False,
        include_tables=False,
        output_format="txt",
        favor_precision=True,
    )
    return value.strip() if isinstance(value, str) else ""


@dataclass(frozen=True)
class ArticleExtractionResult:
    title: str | None
    content: str
    extractor: str
    confidence: str
    meta: dict[str, object]


def extract_article_content_from_html(
    *,
    html: str,
    url: str | None = None,
    title: str | None = None,
) -> ArticleExtractionResult:
    raw_html = str(html or "").strip()
    if not raw_html:
        return ArticleExtractionResult(title=title, content="", extractor="none", confidence="low", meta={})

    try:
        extracted = _extract_with_trafilatura(raw_html, url)
        if extracted:
            return ArticleExtractionResult(
                title=title,
                content=extracted,
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
