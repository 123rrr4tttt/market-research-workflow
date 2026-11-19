from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_discovery_preserves_unclassified_material_without_a_model(self):
        self.assertEqual(store_module._classify_kind("Annual meeting", "", None), "external")
        self.assertEqual(store_module._classify_kind("Market regulation", "", None), "external")
        self.assertEqual(store_module._classify_kind("Market revenue", "", None), "market")
        self.assertEqual(store_module._classify_kind("Policy legislation", "", None), "policy")

    def test_discovery_gate_rejects_search_endpoint(self):
        ok, reason, _ = store_module._discovery_gate_check(
            url="https://www.google.com/search?q=robotics",
            content="robotics market update " * 40,
            material_type="market",
            extracted_data={},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "url_policy_low_value_endpoint")

    def test_discovery_gate_rejects_shell_content(self):
        ok, reason, _ = store_module._discovery_gate_check(
            url="https://example.com/post/1",
            content="self.__next_f = []; var bodyCacheable = true;",
            material_type="market",
            extracted_data={},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "content_shell_signature")

    def test_discovery_gate_accepts_meaningful_content(self):
        ok, reason, diagnostics = store_module._discovery_gate_check(
            url="https://example.com/news/ai-supply-chain",
            content=" ".join(["ai supply chain production demand"] * 120),
            material_type="market",
            extracted_data={"entities_relations": {"entities": [{"name": "NVIDIA"}]}},
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")
        self.assertIn("content_gate", diagnostics)


    def test_discovery_indexes_only_committed_policy_material_ids(self):
        session = MagicMock()
        session.query.return_value.filter.return_value.one_or_none.return_value = None
        writer_results = [
            {"inserted": 1, "material_id": 10},
            {"inserted": 1, "material_id": 11},
        ]

        def index(*, material_ids):
            session.commit.assert_called_once()
            self.assertEqual(material_ids, [10])

        with (
            patch.object(store_module, "SessionLocal", return_value=session),
            patch.object(store_module, "_store_tables_available", return_value=True),
            patch.object(store_module, "_get_or_create_source"),
            patch.object(store_module, "_fetch_content", return_value=("article text", None, None)),
            patch.object(store_module, "_discovery_gate_check", return_value=(True, "ok", {})),
            patch.object(store_module, "build_discovery_ingress_envelope", return_value={"collection_payload": {}}),
            patch.object(store_module, "run_postprocess_frontdoor", side_effect=[
                {"data": {"writer_result": result}} for result in writer_results
            ]),
            patch.object(store_module, "index_policy_documents", side_effect=index) as index_policies,
            patch("app.services.indexer.policy.settings.openai_api_key", ""),
        ):
            session.__enter__.return_value = session
            result = store_module.store_results([
                {"link": "https://example.com/policy", "title": "Policy legislation"},
                {"link": "https://example.com/news", "title": "Market revenue"},
            ])

        self.assertEqual(result["inserted"], 2)
        index_policies.assert_called_once_with(material_ids=[10])


if __name__ == "__main__":
    unittest.main()
