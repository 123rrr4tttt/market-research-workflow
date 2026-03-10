from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest.meaningful_gate import GateDecision
    from app.services.ingest import single_url as single_url_module
    from app.services.ingest import url_pool as url_pool_module
    from app.services.ingest.metrics_payload import (
        build_metrics_payload_from_summary,
        new_metrics_summary,
        record_metrics_observation,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class IngestMetricsPayloadUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest metrics payload tests require backend dependencies: {_IMPORT_ERROR}")

    def _assert_contract_fields(self, payload: dict) -> None:
        self.assertIn("url_only_document_rate", payload)
        self.assertIn("empty_body_rate", payload)
        self.assertIn("reason_code_top_n", payload)
        self.assertIn("adapter_hit_rate", payload)
        self.assertIsInstance(payload.get("reason_code_top_n"), list)
        self.assertIsInstance(payload.get("adapter_hit_rate"), list)

    def _assert_source_template_health_fields(self, payload: dict) -> None:
        self.assertIn("template_success_rate", payload)
        self.assertIn("template_body_insert_rate", payload)
        self.assertIn("template_empty_body_rate", payload)
        self.assertIn("template_rejection_top_n", payload)
        self.assertIsInstance(payload.get("template_rejection_top_n"), list)

    def test_metrics_payload_helper_keeps_stable_fields(self):
        summary = new_metrics_summary()
        record_metrics_observation(
            summary,
            {
                "inserted_valid": 0,
                "reason_code": "content_empty",
                "handler_allocation": {"handler_used": "crawler_pool"},
            },
            fallback_adapter="single_url",
        )
        payload = build_metrics_payload_from_summary(summary)

        self._assert_contract_fields(payload)
        self.assertEqual(payload.get("sample_size"), 1)
        self.assertEqual(payload.get("reason_code_top_n", [])[0].get("reason_code"), "content_empty")
        self.assertEqual(payload.get("adapter_hit_rate", [])[0].get("adapter"), "crawler_pool")

    def test_single_url_result_contains_metrics_payload_in_meta_and_debug(self):
        fake_job_id = 923
        blocked_gate = GateDecision(
            accepted=False,
            blocked=True,
            reason="url_policy_low_value_endpoint",
            quality_score=0.0,
            diagnostics={"matched_path_keyword": "/search"},
        )

        with patch.object(single_url_module, "start_job", return_value=fake_job_id), patch.object(
            single_url_module, "complete_job"
        ), patch.object(single_url_module, "url_policy_check", return_value=blocked_gate):
            result = single_url_module.ingest_single_url(
                url="https://example.com/search?q=metrics",
                query_terms=["metrics"],
                strict_mode=False,
            )

        metrics_payload = ((result.get("meta") or {}).get("metrics_payload") or {})
        self._assert_contract_fields(metrics_payload)
        self.assertEqual(metrics_payload, ((result.get("debug") or {}).get("metrics_payload") or {}))

    def test_url_pool_result_contains_metrics_payload_in_meta_and_debug(self):
        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = Mock(
            return_value={
                "status": "degraded_success",
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "reason_code": "fetch_failed",
                "rejected_count": 1,
                "rejection_breakdown": {"fetch_failed": 1},
                "degradation_flags": ["fetch_failed"],
                "handler_allocation": {"handler_used": "single_url"},
            }
        )

        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}), patch.object(
            url_pool_module, "_annotate_url_pool_context"
        ):
            result = url_pool_module.collect_urls_from_list(
                ["https://a.example.com/path/1"],
                query_terms=["metrics"],
            )

        metrics_payload = ((result.get("meta") or {}).get("metrics_payload") or {})
        self._assert_contract_fields(metrics_payload)
        self.assertEqual(metrics_payload, ((result.get("debug") or {}).get("metrics_payload") or {}))
        self.assertGreaterEqual(int(metrics_payload.get("sample_size") or 0), 1)

    def test_url_pool_result_contains_source_template_health_defaults(self):
        fake_module = types.ModuleType("app.services.ingest.single_url")
        fake_module.ingest_single_url = Mock(
            return_value={
                "status": "degraded_success",
                "inserted": 0,
                "inserted_valid": 0,
                "skipped": 1,
                "reason_code": "fetch_failed",
                "rejected_count": 1,
                "rejection_breakdown": {"fetch_failed": 1},
                "degradation_flags": ["fetch_failed"],
                "handler_allocation": {"handler_used": "single_url"},
            }
        )

        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}), patch.object(
            url_pool_module, "_annotate_url_pool_context"
        ):
            result = url_pool_module.collect_urls_from_list(
                ["https://a.example.com/path/1"],
                query_terms=["metrics"],
            )

        health = ((result.get("meta") or {}).get("source_template_health") or {})
        self._assert_source_template_health_fields(health)
        self.assertEqual(health, ((result.get("debug") or {}).get("source_template_health") or {}))
        self.assertEqual(int(health.get("sample_size") or 0), 0)
        self.assertEqual(float(health.get("template_success_rate") or 0.0), 0.0)
        self.assertEqual(float(health.get("template_body_insert_rate") or 0.0), 0.0)
        self.assertEqual(float(health.get("template_empty_body_rate") or 0.0), 0.0)
        self.assertEqual(list(health.get("template_rejection_top_n") or []), [])

    def test_url_pool_result_contains_source_template_health_rejections(self):
        fake_module = types.ModuleType("app.services.ingest.single_url")

        def _fake_ingest(*, url: str, **kwargs):
            if "/search" in url:
                return {
                    "status": "degraded_success",
                    "inserted": 0,
                    "inserted_valid": 0,
                    "skipped": 1,
                    "reason_code": "search_template_results_insufficient",
                    "rejected_count": 1,
                    "rejection_breakdown": {"search_template_results_insufficient": 1},
                    "degradation_flags": ["search_template_no_results"],
                    "handler_allocation": {"handler_used": "single_url"},
                    "capability_profile": {"entry_type": "search_template"},
                }
            return {
                "status": "success",
                "inserted": 1,
                "inserted_valid": 1,
                "skipped": 0,
                "reason_code": "ok",
                "rejected_count": 0,
                "rejection_breakdown": {},
                "degradation_flags": [],
                "handler_allocation": {"handler_used": "single_url"},
            }

        fake_module.ingest_single_url = Mock(side_effect=_fake_ingest)

        with patch.dict(sys.modules, {"app.services.ingest.single_url": fake_module}), patch.object(
            url_pool_module, "_annotate_url_pool_context"
        ):
            result = url_pool_module.collect_urls_from_list(
                ["https://a.example.com/search?q=metrics"],
                query_terms=["metrics"],
            )

        health = ((result.get("meta") or {}).get("source_template_health") or {})
        self._assert_source_template_health_fields(health)
        self.assertEqual(health, ((result.get("debug") or {}).get("source_template_health") or {}))
        self.assertEqual(int(health.get("sample_size") or 0), 1)
        self.assertEqual(float(health.get("template_success_rate") or 0.0), 1.0)
        self.assertEqual(float(health.get("template_body_insert_rate") or 0.0), 0.0)
        self.assertEqual(float(health.get("template_empty_body_rate") or 0.0), 1.0)
        top = list(health.get("template_rejection_top_n") or [])
        self.assertGreaterEqual(len(top), 1)
        self.assertEqual(top[0].get("reason_code"), "search_template_results_insufficient")
        self.assertEqual(int(top[0].get("count") or 0), 1)


if __name__ == "__main__":
    unittest.main()
