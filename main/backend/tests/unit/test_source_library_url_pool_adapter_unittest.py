from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.adapters.url_pool import handle_url_pool
from app.services.source_library.adapters.url_pool import _extract_text_preview
from app.services.source_library.adapters.url_pool import _materialize_pdf_artifact


class SourceLibraryUrlPoolAdapterUnitTestCase(unittest.TestCase):
    def test_extract_text_preview_uses_selectolax_css_first_for_title(self) -> None:
        title, preview = _extract_text_preview(
            "<html><head><title>Arxiv Paper</title></head><body><article><p>Body text here.</p></article></body></html>"
        )

        self.assertEqual(title, "Arxiv Paper")
        self.assertTrue(preview)

    def test_terminal_output_only_mode_fetches_clean_records_without_write_side_effects(self) -> None:
        with patch(
            "app.services.source_library.adapters.url_pool.fetch_html",
            return_value=("<html><title>Example A</title><body>Hello World</body></html>", SimpleNamespace(status_code=200)),
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

    def test_arxiv_abs_record_includes_pdf_artifact_ref(self) -> None:
        with patch(
            "app.services.source_library.adapters.url_pool.fetch_html",
            return_value=("<html><title>Arxiv Paper</title><body>Abstract</body></html>", SimpleNamespace(status_code=200)),
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
