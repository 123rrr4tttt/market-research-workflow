"""URL pool channel adapter: collect-only fetch for source-library boundary."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir
from typing import Any
from urllib.parse import urlparse

import requests
from pypdf import PdfReader

from ...ingest.adapters.http_utils import fetch_html, make_html_parser
from ...resource_pool import list_urls
from ...resource_pool.article_extraction_service import extract_article_content_from_html
from ..external_project import validate_external_http_url


_MAX_PDF_BYTES = 20 * 1024 * 1024
_MAX_PDF_PAGES = 100
_MAX_CONTENT_CHARS = 50000


def _response_mime_type(response: Any) -> str:
    headers = getattr(response, "headers", None) or {}
    return str(headers.get("Content-Type") or headers.get("content-type") or "").split(";", 1)[0].strip().lower()


def _html_response_text(html: str, response: Any) -> str:
    body = getattr(response, "content", None)
    declared = str(getattr(response, "encoding", None) or "").lower()
    if not isinstance(body, bytes) or declared not in {"iso-8859-1", "latin-1", ""}:
        return html
    detected = str(getattr(response, "apparent_encoding", None) or "").strip()
    if detected and detected.lower() not in {"iso-8859-1", "latin-1"}:
        try:
            return body.decode(detected)
        except (LookupError, UnicodeDecodeError):
            pass
    return html


def _extract_pdf_text(body: bytes, url: str) -> tuple[str, str, int]:
    if not body or len(body) > _MAX_PDF_BYTES:
        raise ValueError(f"PDF response size must be between 1 and {_MAX_PDF_BYTES} bytes")  # noqa: TRY003
    reader = PdfReader(BytesIO(body), strict=True)
    if reader.is_encrypted:
        raise ValueError("PDF is encrypted")  # noqa: TRY003
    page_count = len(reader.pages)
    if not 1 <= page_count <= _MAX_PDF_PAGES:
        raise ValueError(f"PDF page count must be between 1 and {_MAX_PDF_PAGES}")  # noqa: TRY003

    parts: list[str] = []
    remaining = _MAX_CONTENT_CHARS
    for page in reader.pages:
        if remaining <= 0:
            break
        page_text = str(page.extract_text() or "").strip()
        if page_text:
            parts.append(page_text[:remaining])
            remaining -= len(parts[-1])
    content_text = "\n\n".join(parts).strip()
    if not content_text or not any(char.isalnum() for char in content_text):
        raise ValueError("PDF contains no extractable text")  # noqa: TRY003

    metadata_title = str(getattr(reader.metadata, "title", None) or "").strip()
    first_line = next((line.strip() for line in content_text.splitlines() if line.strip()), "")
    url_title = Path(urlparse(url).path).stem.replace("_", " ").replace("-", " ").strip()
    title = (metadata_title or first_line or url_title or url)[:300]
    return title, content_text, page_count


def _normalize_urls_from_params(params: dict[str, Any]) -> tuple[list[str], list[str], bool]:
    raw = params.get("urls")
    out: list[str] = []
    rejected: list[str] = []
    explicit_input = False

    def add(raw_value: Any) -> None:
        nonlocal explicit_input
        s = str(raw_value or "").strip()
        if not s:
            return
        explicit_input = True
        if not s.startswith(("http://", "https://")):
            rejected.append(f"{s}: url_pool.url must use http or https")
            return
        try:
            normalized = validate_external_http_url(s, field_name="url_pool.url")
        except ValueError as exc:
            rejected.append(f"{s}: {exc}")
            return
        if normalized not in out:
            out.append(normalized)

    if isinstance(raw, list):
        for x in raw:
            add(x)
    elif isinstance(raw, str):
        add(raw)
    if "url" in params:
        add(params.get("url"))
    return out, rejected, explicit_input


def _extract_text_preview(html: str, *, max_chars: int = 50000) -> tuple[str | None, str]:
    parser = make_html_parser(html)
    title_node = parser.css_first("title") if hasattr(parser, "css_first") else None
    title = str(title_node.text(strip=True) if title_node is not None else "").strip() or None
    for selector in ("script", "style", "noscript"):
        for node in parser.css(selector):
            node.decompose()
    extracted = extract_article_content_from_html(html=parser.html, title=title)
    text = str(extracted.content or "").strip()
    if not text:
        text = parser.text(" ", strip=True) if hasattr(parser, "text") else str(html or "")
        if not isinstance(text, str):
            text = str(text or "")
        text = " ".join(text.split())
    return title, text[:max_chars]


def _build_pdf_artifact_ref(url: str) -> dict[str, Any] | None:
    parsed = urlparse(str(url or "").strip())
    host = str(parsed.netloc or "").strip().lower()
    if host not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        return None

    path = str(parsed.path or "").strip()
    paper_id = ""
    if path.startswith("/abs/"):
        paper_id = path[len("/abs/") :].strip("/")
    elif path.startswith("/pdf/"):
        paper_id = path[len("/pdf/") :].strip("/")
    if not paper_id:
        return None

    pdf_path = f"/pdf/{paper_id}" if paper_id.endswith(".pdf") else f"/pdf/{paper_id}.pdf"
    return {
        "artifact_source": "pdf",
        "artifact_role": "primary_source_pdf",
        "source_locator": f"https://arxiv.org{pdf_path}",
        "mime_type": "application/pdf",
        "discovery_mode": "derived_from_arxiv_locator",
        "download_status": "pending",
    }


def _materialize_pdf_artifact(
    artifact_ref: dict[str, Any] | None,
    *,
    timeout: float,
    retries: int,
) -> dict[str, Any] | None:
    if not isinstance(artifact_ref, dict):
        return artifact_ref
    pdf_url = str(artifact_ref.get("source_locator") or "").strip()
    if not pdf_url:
        return artifact_ref

    artifact_dir = Path(gettempdir()) / "source-library-artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    last_error = None
    for _attempt in range(max(retries, 1) + 1):
        try:
            response = requests.get(pdf_url, timeout=timeout)
            response.raise_for_status()
            pdf_bytes = response.content
            digest = sha256(pdf_bytes).hexdigest()
            local_path = artifact_dir / f"{digest}.pdf"
            if not local_path.exists():
                local_path.write_bytes(pdf_bytes)
            materialized = dict(artifact_ref)
            materialized.update(
                {
                    "download_status": "downloaded",
                    "storage_kind": "local_file",
                    "local_path": str(local_path),
                    "sha256": digest,
                    "byte_size": len(pdf_bytes),
                }
            )
            return materialized  # noqa: TRY300
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)

    degraded = dict(artifact_ref)
    degraded["download_status"] = "failed"
    if last_error:
        degraded["download_error"] = last_error
    return degraded


def handle_url_pool(params: dict[str, Any], project_key: str | None) -> dict[str, Any]:
    merged_params = dict(params or {})
    terminal_output_only = bool(merged_params.get("source_library_terminal_output_only")) or str(
        merged_params.get("source_library_execution_layer") or ""
    ).strip().lower() == "terminal_output_only"
    urls, rejected_url_errors, explicit_url_input = _normalize_urls_from_params(merged_params)
    limit = max(1, int(merged_params.get("limit") or merged_params.get("max_items") or 50))
    timeout = float(merged_params.get("probe_timeout") or 8.0)
    retries = max(0, int(merged_params.get("fetch_retries") or 1))

    if not urls and not explicit_url_input:
        pool_rows, _total = list_urls(
            scope=str(merged_params.get("scope") or "effective"),
            project_key=str(project_key or ""),
            source=merged_params.get("source_filter") or merged_params.get("source") or None,
            domain=merged_params.get("domain") or None,
            page=1,
            page_size=limit,
        )
        for row in pool_rows:
            u = str((row or {}).get("url") or "").strip()
            if not u:
                continue
            try:
                normalized = validate_external_http_url(u, field_name="url_pool.url")
            except ValueError as exc:
                rejected_url_errors.append(f"{u}: {exc}")
                continue
            if normalized not in urls:
                urls.append(normalized)
            if len(urls) >= limit:
                break
    else:
        urls = urls[:limit]

    by_url: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    errors: list[str] = list(rejected_url_errors)
    fetched = 0
    for url in urls:
        try:
            html, resp = fetch_html(url, timeout=timeout, retries=retries)
            body = getattr(resp, "content", None)
            mime_type = _response_mime_type(resp)
            is_pdf = mime_type == "application/pdf" or isinstance(body, bytes) and body.startswith(b"%PDF-")
            record_meta = {
                "http_status": int(getattr(resp, "status_code", 200) or 200),
                "execution_layer": "terminal_output_only" if terminal_output_only else "execute",
            }
            if is_pdf:
                pdf_body = body if isinstance(body, bytes) else b""
                record_meta.update(
                    {
                        "content_format": "pdf",
                        "content_mime_type": "application/pdf",
                        "body_sha256": sha256(pdf_body).hexdigest(),
                    }
                )
                try:
                    title, content_text, page_count = _extract_pdf_text(pdf_body, url)
                except Exception as exc:  # noqa: BLE001
                    msg = f"PDF text extraction failed: {exc}"
                    record_meta["text_extraction_status"] = "failed"
                    errors.append(f"{url}: {msg}")
                    by_url.append({"url": url, "error": msg, "result": None, "record_meta": record_meta})
                    continue
                record_meta["text_extraction_status"] = "succeeded"
                record_meta["pdf_page_count"] = page_count
                artifact_ref = None
            else:
                title, content_text = _extract_text_preview(_html_response_text(html, resp))
                artifact_ref = _materialize_pdf_artifact(
                    _build_pdf_artifact_ref(url),
                    timeout=timeout,
                    retries=retries,
                )
            preview = content_text[:2000]
            if artifact_ref:
                record_meta["artifact_ref"] = artifact_ref
            record = {
                "record_id": url,
                "url": url,
                "title": title,
                "content_text": content_text,
                "summary": None,
                "published_at": None,
                "author": None,
                "language": None,
                "source_label": "url_pool",
                "record_meta": record_meta,
                "raw_ref": {"source": "url_pool", "url": url},
            }
            by_url.append(
                {
                    "url": url,
                    "error": None,
                    "result": {
                        "status": "fetched",
                        "http_status": int(getattr(resp, "status_code", 200) or 200),
                        "title": title,
                        "content_text": preview,
                        "content_preview": preview,
                        "content_chars": len(content_text or ""),
                        "record_id": url,
                        "source_label": "url_pool",
                        "execution_layer": "terminal_output_only" if terminal_output_only else "execute",
                        "record_meta": record_meta,
                        "artifact_ref": artifact_ref,
                    },
                }
            )
            records.append(record)
            fetched += 1
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            errors.append(f"{url}: {msg}")
            by_url.append({"url": url, "error": msg, "result": None})

    return {
        "status": "completed" if not terminal_output_only else "accepted",
        "inserted": 0,
        "updated": 0,
        "skipped": max(len(urls) - fetched, 0),
        "errors": errors,
        "rejected_urls": list(rejected_url_errors),
        "by_url": by_url,
        "records": records,
        "fetched": fetched,
        "requested": len(urls),
        "source_library_collect_only": True,
        "single_write_workflow": "terminal_output_only" if terminal_output_only else "url_routing",
        "execution_layer": "terminal_output_only" if terminal_output_only else "execute",
    }
