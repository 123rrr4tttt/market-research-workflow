"""URL pool channel adapter: collect-only fetch for source-library boundary."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import gettempdir
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests

from ...ingest.adapters.http_utils import fetch_html, make_html_parser
from ...resource_pool.article_extraction_service import extract_article_content_from_html
from ...resource_pool import list_urls


def _normalize_urls_from_params(params: Dict[str, Any]) -> List[str]:
    raw = params.get("urls")
    out: List[str] = []
    if isinstance(raw, list):
        for x in raw:
            s = str(x or "").strip()
            if s.startswith(("http://", "https://")) and s not in out:
                out.append(s)
    elif isinstance(raw, str):
        s = raw.strip()
        if s.startswith(("http://", "https://")):
            out.append(s)
    single = str(params.get("url") or "").strip()
    if single.startswith(("http://", "https://")) and single not in out:
        out.append(single)
    return out


def _extract_text_preview(html: str, *, max_chars: int = 2000) -> tuple[str | None, str]:
    parser = make_html_parser(html)
    title_node = parser.css_first("title") if hasattr(parser, "css_first") else None
    title = str(title_node.text(strip=True) if title_node is not None else "").strip() or None
    extracted = extract_article_content_from_html(html=html, title=title)
    text = str(extracted.content or "").strip()
    if not text:
        text = parser.text(" ", strip=True) if hasattr(parser, "text") else str(html or "")
        if not isinstance(text, str):
            text = str(text or "")
        text = " ".join(text.split())
    return title, text[:max_chars]


def _build_pdf_artifact_ref(url: str) -> Dict[str, Any] | None:
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
    artifact_ref: Dict[str, Any] | None,
    *,
    timeout: float,
    retries: int,
) -> Dict[str, Any] | None:
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
            return materialized
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)

    degraded = dict(artifact_ref)
    degraded["download_status"] = "failed"
    if last_error:
        degraded["download_error"] = last_error
    return degraded


def handle_url_pool(params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    merged_params = dict(params or {})
    terminal_output_only = bool(merged_params.get("source_library_terminal_output_only")) or str(
        merged_params.get("source_library_execution_layer") or ""
    ).strip().lower() == "terminal_output_only"
    urls = _normalize_urls_from_params(merged_params)
    limit = max(1, int(merged_params.get("limit") or merged_params.get("max_items") or 50))
    timeout = float(merged_params.get("probe_timeout") or 8.0)
    retries = max(0, int(merged_params.get("fetch_retries") or 1))

    if not urls:
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
            if u.startswith(("http://", "https://")) and u not in urls:
                urls.append(u)
            if len(urls) >= limit:
                break
    else:
        urls = urls[:limit]

    by_url: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    fetched = 0
    for url in urls:
        try:
            html, resp = fetch_html(url, timeout=timeout, retries=retries)
            title, preview = _extract_text_preview(html)
            artifact_ref = _materialize_pdf_artifact(
                _build_pdf_artifact_ref(url),
                timeout=timeout,
                retries=retries,
            )
            record_meta = {
                "http_status": int(getattr(resp, "status_code", 200) or 200),
                "execution_layer": "terminal_output_only" if terminal_output_only else "execute",
            }
            if artifact_ref:
                record_meta["artifact_ref"] = artifact_ref
            record = {
                "record_id": url,
                "url": url,
                "title": title,
                "content_text": preview,
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
                        "content_chars": len(preview or ""),
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
        "by_url": by_url,
        "records": records,
        "fetched": fetched,
        "requested": len(urls),
        "source_library_collect_only": True,
        "single_write_workflow": "terminal_output_only" if terminal_output_only else "url_routing",
        "execution_layer": "terminal_output_only" if terminal_output_only else "execute",
    }
