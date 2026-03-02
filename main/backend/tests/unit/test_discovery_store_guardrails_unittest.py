from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.discovery import store as store_module

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class DiscoveryStoreGuardrailsUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"discovery store guardrails unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_discovery_gate_rejects_search_endpoint(self):
        ok, reason, _ = store_module._discovery_gate_check(
            url="https://www.google.com/search?q=robotics",
            content="robotics market update " * 40,
            doc_type="market",
            extracted_data={},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "url_policy_low_value_endpoint")

    def test_discovery_gate_rejects_shell_content(self):
        ok, reason, _ = store_module._discovery_gate_check(
            url="https://example.com/post/1",
            content="self.__next_f = []; var bodyCacheable = true;",
            doc_type="market",
            extracted_data={},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "content_shell_signature")

    def test_discovery_gate_accepts_meaningful_content(self):
        ok, reason, diagnostics = store_module._discovery_gate_check(
            url="https://example.com/news/ai-supply-chain",
            content=" ".join(["ai supply chain production demand"] * 120),
            doc_type="market",
            extracted_data={"entities_relations": {"entities": [{"name": "NVIDIA"}]}},
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertIn("content_gate", diagnostics)


if __name__ == "__main__":
    unittest.main()
