from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
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
        self.assertIn("guardrail_rollout", payload)
        self.assertIsInstance(payload.get("reason_code_top_n"), list)
        self.assertIsInstance(payload.get("adapter_hit_rate"), list)
        self.assertIsInstance(payload.get("guardrail_rollout"), dict)

    def test_metrics_payload_helper_keeps_stable_fields(self):
        summary = new_metrics_summary()
        record_metrics_observation(
            summary,
            {
                "inserted_valid": 0,
                "reason_code": "content_empty",
                "handler_allocation": {"handler_used": "crawler_pool"},
            },
            fallback_adapter="url_routing",
        )
        payload = build_metrics_payload_from_summary(summary)

        self._assert_contract_fields(payload)
        self.assertEqual(payload.get("sample_size"), 1)
        self.assertEqual(payload.get("reason_code_top_n", [])[0].get("reason_code"), "content_empty")
        self.assertEqual(payload.get("adapter_hit_rate", [])[0].get("adapter"), "crawler_pool")

    def test_metrics_payload_counts_rate_limited_observations(self):
        summary = new_metrics_summary()
        record_metrics_observation(
            summary,
            {
                "inserted_valid": 0,
                "reason_code": "HTTP 429",
                "handler_allocation": {"handler_used": "url_routing"},
            },
            fallback_adapter="url_routing",
        )
        record_metrics_observation(
            summary,
            {
                "inserted_valid": 0,
                "reason_code": "ok",
                "rejection_breakdown": {"too_many_requests": 3, "fetch_failed": 1},
                "handler_allocation": {"handler_used": "crawler_pool"},
            },
            fallback_adapter="url_routing",
        )

        payload = build_metrics_payload_from_summary(summary, top_n=3)
        reason_top = {str(row.get("reason_code")): int(row.get("count") or 0) for row in (payload.get("reason_code_top_n") or [])}
        self.assertEqual(int(payload.get("sample_size") or 0), 2)
        self.assertEqual(reason_top.get("rate_limited"), 2)

    def test_metrics_payload_counts_guardrail_rollout_canary_visibility(self):
        summary = new_metrics_summary()
        record_metrics_observation(
            summary,
            {
                "inserted_valid": 0,
                "reason_code": "domain_blocked",
                "guardrail_rollout": {
                    "contract_version": "ingest.guardrail_rollout.v1",
                    "enable_strict_gate": True,
                    "strict_gate_source": "settings.ingest_guardrail_rollout_mode:canary",
                    "rollout_mode": "canary",
                    "project_key": "demo_proj",
                    "canary_projects": ["demo_proj"],
                    "canary_matched": True,
                    "global_default_enabled": False,
                    "live_canary_validated": False,
                    "closure_claim": False,
                },
            },
            fallback_adapter="source_library_frontdoor",
        )

        payload = build_metrics_payload_from_summary(summary)
        rollout = payload["guardrail_rollout"]
        source_counts = {row["key"]: row["count"] for row in rollout["strict_gate_source_counts"]}
        mode_counts = {row["key"]: row["count"] for row in rollout["rollout_mode_counts"]}
        self.assertEqual(rollout["sample_size"], 1)
        self.assertEqual(rollout["strict_enabled_samples"], 1)
        self.assertEqual(rollout["canary_matched_samples"], 1)
        self.assertEqual(source_counts["settings.ingest_guardrail_rollout_mode:canary"], 1)
        self.assertEqual(mode_counts["canary"], 1)
        self.assertFalse(rollout["live_canary_validated"])
        self.assertFalse(rollout["closure_claim"])

    def test_source_library_frontdoor_wrapper_delegates_to_explicit_handoff_helper(self):
        bridge = Mock(
            return_value={
                "status": "success",
                "inserted": 1,
                "inserted_valid": 1,
                "skipped": 0,
                "rejected_count": 0,
                "rejection_breakdown": {},
                "degradation_flags": [],
                "document_id": 91,
                "quality_score": 0.0,
                "records": [{"url": "https://example.com/path/1"}],
                "by_url": [],
                "errors": [],
                "frontdoor_ingress": {"contract_version": "frontdoor.ingress.v1"},
                "postprocess_frontdoor": {"data": {"admission": "accept"}},
                "single_write_workflow": "source_library_frontdoor",
                "source_library_collect_only": True,
            }
        )

        with patch.object(url_pool_module, "_run_source_library_frontdoor_ingress", bridge):
            result = url_pool_module.ingest_url_via_source_library_frontdoor(url="https://example.com/path/1")

        bridge.assert_called_once()
        self.assertEqual(result["document_id"], 91)
        self.assertEqual(result["status"], "success")


if __name__ == "__main__":
    unittest.main()
