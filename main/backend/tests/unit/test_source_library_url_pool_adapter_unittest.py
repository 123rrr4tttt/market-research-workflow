from __future__ import annotations

import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.adapters.url_pool import (  # noqa: E402
    _extract_text_preview,
    _materialize_pdf_artifact,
    handle_url_pool,
)


def _text_pdf_bytes(text: str) -> bytes:
    """Build a small PDF with a ToUnicode map, including CJK text, without test dependencies."""
    cid_hex = "".join(f"{index:04X}" for index, _ in enumerate(text, 1))
    mappings = "\n".join(
        f"<{index:04X}> <{char.encode('utf-16-be').hex().upper()}>"
        for index, char in enumerate(text, 1)
    )
    cmap = (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        f"{len(text)} beginbfchar\n{mappings}\nendbfchar\n"
        "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend"
    ).encode("ascii")
    content = f"BT /F1 12 Tf 10 100 Td <{cid_hex}> Tj ET".encode("ascii")

    def stream(data: bytes) -> bytes:
        return f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /Test /Encoding /Identity-H "
        b"/DescendantFonts [6 0 R] /ToUnicode 7 0 R >>",
        stream(content),
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Test /CIDSystemInfo "
        b"<< /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> >>",
        stream(cmap),
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode())
    return bytes(pdf)


class SourceLibraryUrlPoolAdapterUnitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # Keep URL validation deterministic when the test host resolves public
        # domains through a private proxy address.
        resolver = patch(
            "app.services.source_library.external_project.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.215.14", 0))],
        )
        resolver.start()
        self.addCleanup(resolver.stop)

    def test_pdf_response_extracts_text_from_same_response_for_mime_and_signature(self) -> None:
        for headers in (
            {"Content-Type": "application/pdf; charset=binary"},
            {"Content-Type": "application/octet-stream"},
        ):
            with self.subTest(headers=headers):
                pdf = _text_pdf_bytes("中文研究 English research")
                with patch(
                    "app.services.source_library.adapters.url_pool.fetch_html",
                    return_value=("%PDF-1.4 garbled", SimpleNamespace(status_code=200, headers=headers, content=pdf)),
                ) as fetch_html, patch(
                    "app.services.source_library.adapters.url_pool._materialize_pdf_artifact"
                ) as materialize:
                    result = handle_url_pool({"url": "https://example.com/research.pdf"}, project_key="demo_proj")

                fetch_html.assert_called_once()
                materialize.assert_not_called()
                self.assertEqual(result["fetched"], 1)
                record = result["records"][0]
                self.assertIn("中文研究", record["content_text"])
                self.assertIn("English research", record["content_text"])
                self.assertNotIn("%PDF", record["content_text"])
                self.assertTrue(record["title"])
                self.assertEqual(record["record_meta"]["content_format"], "pdf")
                self.assertEqual(record["record_meta"]["text_extraction_status"], "succeeded")
                self.assertEqual(record["record_meta"]["content_mime_type"], "application/pdf")
                self.assertEqual(record["record_meta"]["body_sha256"], sha256(pdf).hexdigest())
                self.assertEqual(record["record_meta"]["pdf_page_count"], 1)

    def test_invalid_pdf_has_failure_metadata_and_no_record(self) -> None:
        pdf = b"%PDF-1.4 invalid PDF bytes"
        with patch(
            "app.services.source_library.adapters.url_pool.fetch_html",
            return_value=(
                "%PDF-1.4 invalid PDF bytes",
                SimpleNamespace(status_code=200, headers={"Content-Type": "application/pdf"}, content=pdf),
            ),
        ):
            result = handle_url_pool({"url": "https://example.com/broken.pdf"}, project_key="demo_proj")

        self.assertEqual(result["fetched"], 0)
        self.assertEqual(result["records"], [])
        self.assertIn("PDF text extraction failed", result["by_url"][0]["error"])
        self.assertEqual(result["by_url"][0]["record_meta"]["text_extraction_status"], "failed")

    def test_oversized_pdf_is_rejected_before_parse(self) -> None:
        pdf = b"%PDF-1.4" + b"x" * (20 * 1024 * 1024)
        with patch(
            "app.services.source_library.adapters.url_pool.fetch_html",
            return_value=("", SimpleNamespace(status_code=200, headers={}, content=pdf)),
        ):
            result = handle_url_pool({"url": "https://example.com/large.pdf"}, project_key="demo_proj")
        self.assertEqual(result["records"], [])
        self.assertIn("size", result["by_url"][0]["error"])

    def test_extract_text_preview_uses_selectolax_css_first_for_title(self) -> None:
        title, preview = _extract_text_preview(
            "<html><head><title>Arxiv Paper</title></head><body><article><p>Body text here.</p></article></body></html>"
        )

        self.assertEqual(title, "Arxiv Paper")
        self.assertTrue(preview)

    def test_extract_text_preview_keeps_article_body_beyond_legacy_preview_limit(self) -> None:
        article_text = " ".join([f"sentence {i} with enough body text." for i in range(600)])
        title, content = _extract_text_preview(
            f"<html><head><title>Long Article</title></head><body><article>{article_text}</article></body></html>"
        )

        self.assertEqual(title, "Long Article")
        self.assertGreater(len(content), 2000)
        self.assertIn("sentence 599", content)

    def test_html_response_decodes_utf8_and_omits_script_body(self) -> None:
        article = "東江水新協議按實際取水量扣減水價。"
        html = (
            "<html><head><title>東江水供水</title></head><body>"
            "<script>var js = document.createElement('script');</script>"
            f"<article><p>{article}</p></article></body></html>"
        )
        body = html.encode("utf-8")
        response = SimpleNamespace(
            status_code=200, headers={"Content-Type": "text/html"}, content=body,
            encoding="ISO-8859-1", apparent_encoding="utf-8",
        )
        with patch(
            "app.services.source_library.adapters.url_pool.fetch_html",
            return_value=(body.decode("latin-1"), response),
        ):
            result = handle_url_pool({"url": "https://example.com/article"}, project_key="demo_proj")

        record = result["records"][0]
        self.assertEqual(record["title"], "東江水供水")
        self.assertIn(article, record["content_text"])
        self.assertNotIn("document.createElement", record["content_text"])

    def test_terminal_output_only_mode_fetches_clean_records_without_write_side_effects(self) -> None:
        with patch(
            "app.services.source_library.adapters.url_pool.fetch_html",
            return_value=(
                "<html><title>Example A</title><body>Hello World</body></html>",
                SimpleNamespace(status_code=200),
            ),
        ) as fetch_html, patch(
            "app.services.source_library.adapters.url_pool._extract_text_preview",
            return_value=("Example A", "Hello World"),
        ):
            result = handle_url_pool(
                {
                    "urls": ["https://example.com/a"],
                    "source_library_execution_layer": "terminal_output_only",
                    "source_library_terminal_output_only": True,
                },
                project_key="demo_proj",
            )

        fetch_html.assert_called_once()
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["single_write_workflow"], "terminal_output_only")
        self.assertEqual(result["execution_layer"], "terminal_output_only")
        self.assertEqual(result["requested"], 1)
        self.assertEqual(result["fetched"], 1)
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["records"][0]["title"], "Example A")
        self.assertEqual(result["by_url"][0]["result"]["execution_layer"], "terminal_output_only")

    def test_rejects_local_urls_before_fetch(self) -> None:
        with patch(
            "app.services.source_library.adapters.url_pool.fetch_html",
            return_value=(
                "<html><title>Example A</title><body>Hello World</body></html>",
                SimpleNamespace(status_code=200),
            ),
        ) as fetch_html, patch(
            "app.services.source_library.adapters.url_pool._extract_text_preview",
            return_value=("Example A", "Hello World"),
        ):
            result = handle_url_pool(
                {
                    "urls": ["http://127.0.0.1/admin", "https://example.com/a"],
                    "source_library_execution_layer": "terminal_output_only",
                    "source_library_terminal_output_only": True,
                },
                project_key="demo_proj",
            )

        fetch_html.assert_called_once_with("https://example.com/a", timeout=8.0, retries=1)
        self.assertEqual(result["requested"], 1)
        self.assertEqual(result["fetched"], 1)
        self.assertEqual(len(result["rejected_urls"]), 1)
        self.assertIn("cannot target localhost", result["rejected_urls"][0])

    def test_does_not_fallback_to_pool_when_explicit_urls_are_all_rejected(self) -> None:
        with patch("app.services.source_library.adapters.url_pool.fetch_html") as fetch_html, patch(
            "app.services.source_library.adapters.url_pool.list_urls",
            return_value=([{"url": "https://example.com/from-pool"}], 1),
        ) as list_urls:
            result = handle_url_pool(
                {
                    "urls": ["http://localhost/admin"],
                    "source_library_execution_layer": "terminal_output_only",
                    "source_library_terminal_output_only": True,
                },
                project_key="demo_proj",
            )

        fetch_html.assert_not_called()
        list_urls.assert_not_called()
        self.assertEqual(result["requested"], 0)
        self.assertEqual(result["fetched"], 0)
        self.assertEqual(len(result["rejected_urls"]), 1)

    def test_arxiv_abs_record_includes_pdf_artifact_ref(self) -> None:
        with patch(
            "app.services.source_library.adapters.url_pool.fetch_html",
            return_value=(
                "<html><title>Arxiv Paper</title><body>Abstract</body></html>",
                SimpleNamespace(status_code=200),
            ),
        ), patch(
            "app.services.source_library.adapters.url_pool._extract_text_preview",
            return_value=("Arxiv Paper", "Abstract"),
        ), patch(
            "app.services.source_library.adapters.url_pool._materialize_pdf_artifact",
            return_value={
                "artifact_source": "pdf",
                "artifact_role": "primary_source_pdf",
                "source_locator": "https://arxiv.org/pdf/1808.00177v5.pdf",
                "mime_type": "application/pdf",
                "download_status": "downloaded",
                "storage_kind": "local_file",
                "local_path": "/tmp/source-library-artifacts/arxiv.pdf",
                "sha256": "abc123",
                "byte_size": 42,
            },
        ):
            result = handle_url_pool(
                {
                    "urls": ["https://arxiv.org/abs/1808.00177v5"],
                    "source_library_execution_layer": "terminal_output_only",
                    "source_library_terminal_output_only": True,
                },
                project_key="demo_proj",
            )

        artifact_ref = result["records"][0]["record_meta"].get("artifact_ref")
        self.assertEqual(artifact_ref["artifact_source"], "pdf")
        self.assertEqual(artifact_ref["mime_type"], "application/pdf")
        self.assertEqual(artifact_ref["source_locator"], "https://arxiv.org/pdf/1808.00177v5.pdf")
        self.assertEqual(artifact_ref["download_status"], "downloaded")
        self.assertEqual(artifact_ref["storage_kind"], "local_file")
        self.assertEqual(artifact_ref["local_path"], "/tmp/source-library-artifacts/arxiv.pdf")
        self.assertEqual(result["by_url"][0]["result"]["artifact_ref"]["source_locator"], "https://arxiv.org/pdf/1808.00177v5.pdf")

    def test_materialize_pdf_artifact_downloads_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "app.services.source_library.adapters.url_pool.gettempdir",
            return_value=tmpdir,
        ), patch(
            "app.services.source_library.adapters.url_pool.requests.get",
            return_value=SimpleNamespace(
                content=b"%PDF-1.4 fake pdf bytes",
                raise_for_status=lambda: None,
            ),
        ):
            artifact = _materialize_pdf_artifact(
                {
                    "artifact_source": "pdf",
                    "artifact_role": "primary_source_pdf",
                    "source_locator": "https://arxiv.org/pdf/1808.00177v5.pdf",
                    "mime_type": "application/pdf",
                    "download_status": "pending",
                },
                timeout=8.0,
                retries=1,
            )

            self.assertEqual(artifact["download_status"], "downloaded")
            self.assertEqual(artifact["storage_kind"], "local_file")
            self.assertTrue(Path(artifact["local_path"]).exists())
            self.assertEqual(Path(artifact["local_path"]).read_bytes(), b"%PDF-1.4 fake pdf bytes")
            self.assertEqual(artifact["byte_size"], len(b"%PDF-1.4 fake pdf bytes"))


if __name__ == "__main__":
    unittest.main()
