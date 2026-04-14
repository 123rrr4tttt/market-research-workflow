from __future__ import annotations

import sys
import unittest
import importlib.util
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.unit

_MODULE_PATH = ROOT / "app" / "api" / "resource_pool.py"
_API_PACKAGE = types.ModuleType("app.api")
_API_PACKAGE.__path__ = [str(ROOT / "app" / "api")]
sys.modules.setdefault("app.api", _API_PACKAGE)
_SPEC = importlib.util.spec_from_file_location("app.api.resource_pool", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["app.api.resource_pool"] = _MODULE
_SPEC.loader.exec_module(_MODULE)

DiscoverSearchContractPayload = _MODULE.DiscoverSearchContractPayload
discover_search_contract_api = _MODULE.discover_search_contract_api
ImportOpenSourcePresetPayload = _MODULE.ImportOpenSourcePresetPayload
import_open_source_presets_api = _MODULE.import_open_source_presets_api


class ResourcePoolApiUnitTestCase(unittest.TestCase):
    def test_discover_search_contract_api_returns_enveloped_payload(self) -> None:
        payload = DiscoverSearchContractPayload(
            project_key="demo_proj",
            scope="project",
            site_url="https://example.com",
            query_terms=["robotics"],
            persist=True,
        )
        fake_result = SimpleNamespace(
            site_url="https://example.com",
            domain="example.com",
            entry_type="search_template",
            templates_tried=["https://example.com/search?q={{q}}"],
            suffixes_tried=["", "pricing"],
            best_template="https://example.com/search?q={{q}}",
            best_suffix="pricing",
            best_score=11.0,
            probe_rows=[],
            persisted_entry={"site_url": "https://example.com"},
        )

        with patch.object(_MODULE, "discover_search_contract", return_value=fake_result):
            response = discover_search_contract_api(payload)

        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn('"best_template":"https://example.com/search?q={{q}}"', body)
        self.assertIn('"best_suffix":"pricing"', body)

    def test_import_open_source_presets_api_returns_enveloped_payload(self) -> None:
        payload = ImportOpenSourcePresetPayload(
            project_key="demo_proj",
            scope="project",
            pack_key="business_media_foundation",
            enabled=True,
            extra_tags=["seeded"],
        )
        fake_result = SimpleNamespace(
            pack_key="business_media_foundation",
            title="Business Media Foundation",
            scope="project",
            project_key="demo_proj",
            inserted_or_updated=[{"site_url": "https://www.reuters.com/arc/outboundfeeds/news-sitemap-index/?outputType=xml"}],
        )

        with patch.object(_MODULE, "import_open_source_preset_pack", return_value=fake_result):
            response = import_open_source_presets_api(payload)

        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn('"pack_key":"business_media_foundation"', body)
        self.assertIn('"count":1', body)


if __name__ == "__main__":
    unittest.main()
