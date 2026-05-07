from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.source_library.external_project_registry import (  # noqa: E402
    EXTERNAL_PROJECT_PROVIDER_REGISTRY_VERSION,
    list_external_project_provider_bindings,
    resolve_external_project_provider_binding,
)


class ExternalProjectRegistryUnitTestCase(unittest.TestCase):
    def test_list_provider_bindings_exposes_supported_execution_modes(self) -> None:
        bindings = list_external_project_provider_bindings()

        by_mode = {entry["execution_mode"]: entry for entry in bindings}
        self.assertEqual(set(by_mode), {"rss_feed", "sitemap", "http_api"})
        self.assertEqual(by_mode["rss_feed"]["registry_version"], EXTERNAL_PROJECT_PROVIDER_REGISTRY_VERSION)
        self.assertEqual(by_mode["http_api"]["provider_family"], "api_provider")

    def test_resolve_provider_binding_derives_runtime_traits_from_manifest(self) -> None:
        binding = resolve_external_project_provider_binding(
            {
                "execution_mode": "http_api",
                "capabilities": {"article_body": False, "pdf_artifact": True},
                "accepted_inputs": {"query_terms": True, "domains": True, "date_range": False},
                "normalization": {"record_kind": "article_metadata", "frontdoor_strategy": "records_only_defer"},
            }
        )

        self.assertEqual(binding["provider_key"], "external_project.http_api")
        self.assertEqual(binding["capability_family"], "record_materialization")
        self.assertTrue(binding["supports_pdf_artifact"])
        self.assertTrue(binding["accepts_domains"])
        self.assertEqual(binding["record_kind"], "article_metadata")

    def test_resolve_provider_binding_rejects_unsupported_execution_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported external project execution_mode"):
            resolve_external_project_provider_binding({"execution_mode": "python_library"})


if __name__ == "__main__":
    unittest.main()
