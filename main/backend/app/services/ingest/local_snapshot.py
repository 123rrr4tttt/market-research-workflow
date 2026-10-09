"""Read one explicitly authorized local material snapshot without external effects."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from functorial_kit import Failure

from mrw_functorial_kit.core.provider_port_failures import ingest_operation_failures

from ..resource_pool.article_extraction_service import extract_article_content_from_html
from ..source_library.pdf_extraction import (
    PdfTextExtractionRejected,
    extract_pdf_text_result,
)
from .material_input import MaterialPreparationError, RawSnapshot, prepare_material

ExtractionStatus = Literal["extracted", "partial", "reference_only"]


@dataclass(frozen=True, slots=True)
class LocalSnapshotResult:
    locator: str
    raw_sha256: str | None
    mime_type: str | None
    source_title: str | None
    content: str | None
    extraction_status: ExtractionStatus
    reason: str | None
    extractor: str | None


_MIME_BY_SUFFIX = {
    ".htm": "text/html",
    ".html": "text/html",
    ".markdown": "text/markdown",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".text": "text/plain",
    ".txt": "text/plain",
}


class _HtmlTitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_title = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() == "title":
            self._inside_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._inside_title = False

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self._parts.append(data)

    @property
    def title(self) -> str | None:
        normalized = " ".join("".join(self._parts).split())
        return normalized or None


def _reference_only(
    locator: str,
    reason: str,
    *,
    raw_sha256: str | None = None,
    mime_type: str | None = None,
    extractor: str | None = None,
) -> LocalSnapshotResult:
    return LocalSnapshotResult(
        locator=locator,
        raw_sha256=raw_sha256,
        mime_type=mime_type,
        source_title=None,
        content=None,
        extraction_status="reference_only",
        reason=reason,
        extractor=extractor,
    )


def _failure(
    *,
    project_key: str,
    locator: str,
    reason: str,
    message: str,
) -> Failure:
    return ingest_operation_failures.fail(
        "raw_import_failed",
        message,
        {
            "operation": "ingest.local_snapshot.prepare",
            "project_key": project_key,
            "locator": locator,
            "reason_code": reason,
        },
    )


def _resolve_authorized_file(
    *,
    project_key: str,
    source_root: Path,
    locator: str,
) -> Path | LocalSnapshotResult | Failure:
    locator_path = Path(locator)
    if not locator or locator_path.is_absolute():
        return _reference_only(locator, "outside_root")

    try:
        resolved_root = source_root.resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, RuntimeError):
        return _reference_only(locator, "not_opened")
    except OSError as exc:
        return _failure(
            project_key=project_key,
            locator=locator,
            reason="unexpected_io",
            message=f"local snapshot source root cannot be resolved: {exc}",
        )
    if not resolved_root.is_dir():
        return _reference_only(locator, "not_opened")

    try:
        resolved_path = (resolved_root / locator_path).resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError, RuntimeError):
        return _reference_only(locator, "not_opened")
    except OSError as exc:
        return _failure(
            project_key=project_key,
            locator=locator,
            reason="unexpected_io",
            message=f"local snapshot path cannot be resolved: {exc}",
        )
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        return _reference_only(locator, "outside_root")
    return resolved_path


def _read_regular_file_once(
    *,
    project_key: str,
    locator: str,
    path: Path,
) -> bytes | LocalSnapshotResult | Failure:
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                return _reference_only(locator, "not_opened")
            raw_bytes = stream.read()
            after = os.fstat(stream.fileno())
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return _reference_only(locator, "not_opened")
    except OSError as exc:
        return _failure(
            project_key=project_key,
            locator=locator,
            reason="unexpected_io",
            message=f"local snapshot could not be read: {exc}",
        )

    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(raw_bytes) != after.st_size:
        return _failure(
            project_key=project_key,
            locator=locator,
            reason="digest_changed",
            message="local snapshot bytes changed while being read",
        )
    return raw_bytes


def _prepare_text(
    *,
    project_key: str,
    locator: str,
    raw_bytes: bytes,
    raw_sha256: str,
    mime_type: str,
) -> LocalSnapshotResult | Failure:
    snapshot = RawSnapshot(
        project_key=project_key,
        source_locator=locator,
        raw_bytes=raw_bytes,
        raw_content_digest=raw_sha256,
        mime_type=mime_type,
    )
    try:
        prepared = prepare_material(snapshot)
    except MaterialPreparationError as exc:
        if isinstance(exc.__cause__, UnicodeDecodeError):
            reason = "invalid_encoding"
        elif "empty" in str(exc).lower():
            reason = "empty"
        else:
            return _failure(
                project_key=project_key,
                locator=locator,
                reason="material_preparation",
                message=str(exc),
            )
        return _reference_only(
            locator,
            reason,
            raw_sha256=raw_sha256,
            mime_type=mime_type,
            extractor="material_input.prepare_material",
        )
    if prepared.raw_content_digest != raw_sha256:
        return _failure(
            project_key=project_key,
            locator=locator,
            reason="digest_changed",
            message="prepared local snapshot digest differs from the opened bytes",
        )
    return LocalSnapshotResult(
        locator=locator,
        raw_sha256=raw_sha256,
        mime_type=mime_type,
        source_title=None,
        content=prepared.text,
        extraction_status="extracted",
        reason=None,
        extractor="material_input.prepare_material",
    )


def _prepare_html(
    *,
    locator: str,
    raw_bytes: bytes,
    raw_sha256: str,
    mime_type: str,
) -> LocalSnapshotResult:
    try:
        html = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return _reference_only(
            locator,
            "invalid_encoding",
            raw_sha256=raw_sha256,
            mime_type=mime_type,
            extractor="resource_pool.article_extraction_service",
        )

    title_parser = _HtmlTitleParser()
    title_parser.feed(html)
    source_title = title_parser.title
    extraction = extract_article_content_from_html(
        html=html,
        title=source_title,
    )
    content = str(extraction.content or "").strip()
    if not content:
        return LocalSnapshotResult(
            locator=locator,
            raw_sha256=raw_sha256,
            mime_type=mime_type,
            source_title=source_title,
            content=None,
            extraction_status="reference_only",
            reason="empty",
            extractor=extraction.extractor,
        )
    return LocalSnapshotResult(
        locator=locator,
        raw_sha256=raw_sha256,
        mime_type=mime_type,
        source_title=source_title,
        content=content,
        extraction_status="extracted",
        reason=None,
        extractor=extraction.extractor,
    )


def _prepare_pdf(
    *,
    locator: str,
    raw_bytes: bytes,
    raw_sha256: str,
    mime_type: str,
) -> LocalSnapshotResult:
    extraction = extract_pdf_text_result(raw_bytes)
    if isinstance(extraction, PdfTextExtractionRejected):
        return _reference_only(
            locator,
            extraction.reason,
            raw_sha256=raw_sha256,
            mime_type=mime_type,
            extractor="pypdf",
        )
    return LocalSnapshotResult(
        locator=locator,
        raw_sha256=raw_sha256,
        mime_type=mime_type,
        source_title=extraction.metadata_title,
        content=extraction.content,
        extraction_status="partial" if extraction.truncated else "extracted",
        reason="content_truncated" if extraction.truncated else None,
        extractor="pypdf",
    )


def prepare_local_snapshot(
    *,
    project_key: str,
    source_root: Path,
    locator: str,
) -> LocalSnapshotResult | Failure:
    """Prepare one relative local locator without fetching, OCR, or persistence."""

    normalized_project_key = str(project_key or "").strip()
    normalized_locator = str(locator or "").strip()
    if not normalized_project_key:
        return _failure(
            project_key=normalized_project_key,
            locator=normalized_locator,
            reason="cross_project",
            message="local snapshot project_key is required",
        )

    resolved = _resolve_authorized_file(
        project_key=normalized_project_key,
        source_root=Path(source_root),
        locator=normalized_locator,
    )
    if isinstance(resolved, (Failure, LocalSnapshotResult)):
        return resolved

    raw = _read_regular_file_once(
        project_key=normalized_project_key,
        locator=normalized_locator,
        path=resolved,
    )
    if isinstance(raw, (Failure, LocalSnapshotResult)):
        return raw

    raw_sha256 = sha256(raw).hexdigest()
    mime_type = _MIME_BY_SUFFIX.get(resolved.suffix.lower())
    if mime_type is None:
        return _reference_only(
            normalized_locator,
            "unsupported_mime",
            raw_sha256=raw_sha256,
            mime_type="application/octet-stream",
        )
    if mime_type in {"text/plain", "text/markdown"}:
        return _prepare_text(
            project_key=normalized_project_key,
            locator=normalized_locator,
            raw_bytes=raw,
            raw_sha256=raw_sha256,
            mime_type=mime_type,
        )
    if mime_type == "text/html":
        return _prepare_html(
            locator=normalized_locator,
            raw_bytes=raw,
            raw_sha256=raw_sha256,
            mime_type=mime_type,
        )
    return _prepare_pdf(
        locator=normalized_locator,
        raw_bytes=raw,
        raw_sha256=raw_sha256,
        mime_type=mime_type,
    )


__all__ = ["LocalSnapshotResult", "prepare_local_snapshot"]
