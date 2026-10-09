"""Bounded PDF text extraction shared by local and fetched Material sources."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from pypdf import PdfReader
from pypdf.errors import PdfReadError

_MAX_PDF_BYTES = 20 * 1024 * 1024
_MAX_PDF_PAGES = 100
_MAX_CONTENT_CHARS = 50000

PdfExtractionReason = Literal[
    "pdf_size",
    "page_limit",
    "encrypted",
    "no_extractable",
]


@dataclass(frozen=True, slots=True)
class PdfTextExtractionRejected:
    reason: PdfExtractionReason
    message: str


@dataclass(frozen=True, slots=True)
class PdfTextExtraction:
    metadata_title: str | None
    content: str
    page_count: int
    truncated: bool


def _extract_pdf_reader_text(
    reader: PdfReader,
) -> PdfTextExtraction | PdfTextExtractionRejected:
    if reader.is_encrypted:
        return PdfTextExtractionRejected("encrypted", "PDF is encrypted")
    page_count = len(reader.pages)
    if not 1 <= page_count <= _MAX_PDF_PAGES:
        return PdfTextExtractionRejected(
            "page_limit",
            f"PDF page count must be between 1 and {_MAX_PDF_PAGES}",
        )

    parts: list[str] = []
    remaining = _MAX_CONTENT_CHARS
    truncated = False
    for page in reader.pages:
        page_text = str(page.extract_text() or "").strip()
        if not page_text:
            continue
        separator_size = 2 if parts else 0
        available = max(0, remaining - separator_size)
        if available <= 0:
            truncated = True
            continue
        kept = page_text[:available]
        parts.append(kept)
        remaining -= separator_size + len(kept)
        if len(kept) < len(page_text):
            truncated = True
    content_text = "\n\n".join(parts).strip()
    if not content_text or not any(char.isalnum() for char in content_text):
        return PdfTextExtractionRejected(
            "no_extractable",
            "PDF contains no extractable text",
        )

    metadata_title = str(getattr(reader.metadata, "title", None) or "").strip() or None
    return PdfTextExtraction(
        metadata_title=metadata_title,
        content=content_text,
        page_count=page_count,
        truncated=truncated,
    )


def extract_pdf_text_result(
    body: bytes,
) -> PdfTextExtraction | PdfTextExtractionRejected:
    """Extract bounded PDF text without inventing a title from its locator."""

    if not body or len(body) > _MAX_PDF_BYTES:
        return PdfTextExtractionRejected(
            "pdf_size",
            f"PDF response size must be between 1 and {_MAX_PDF_BYTES} bytes",
        )
    try:
        return _extract_pdf_reader_text(PdfReader(BytesIO(body), strict=True))
    except (IndexError, KeyError, OSError, PdfReadError, TypeError, ValueError) as exc:
        return PdfTextExtractionRejected(
            "no_extractable",
            f"PDF cannot be parsed: {exc}",
        )


__all__ = [
    "PdfTextExtraction",
    "PdfTextExtractionRejected",
    "extract_pdf_text_result",
]
