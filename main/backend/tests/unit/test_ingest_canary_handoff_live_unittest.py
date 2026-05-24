from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest.canary_handoff import build_single_url_canary_handoff
    from app.services.ingest.canary_handoff_live import (
        build_production_like_handoff_evidence,
        validate_production_like_handoff_evidence,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


def _handoff(state: str, *, reason_code: str = "ok") -> dict:
    return {
        "contract_version": "ingest.single_url_canary_handoff.v1",
        "handoff_state": "partial_live_gap_open",
        "strict_gate_state": {
            "state": state,
            "strict_gate_enabled": True,
            "reason_code": reason_code,
        },
        "rollout": {"channel": "canary"},
        "metrics_snapshot": {
            "contract_version": "ingest.single_url_canary_metrics_snapshot.v1",
            "guardrail_rollout": {
                "live_canary_validated": False,
                "closure_claim": False,
            },
        },
    }


class IngestCanaryHandoffLiveUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"ingest canary handoff live tests require backend dependencies: {_IMPORT_ERROR}")

    def test_production_like_evidence_validates_api_db_and_guardrail_readbacks(self):
        evidence = build_production_like_handoff_evidence(
            project_key="wave55_canary",
            accepted_url="https://example.com/article",
            rejected_url="https://example.com/search?q=wave55",
            accepted_status_code=200,
            rejected_status_code=200,
            accepted_result={
                "status": "success",
                "canary_handoff": _handoff("strict_passed"),
            },
            rejected_result={
                "status": "failed",
                "canary_handoff": _handoff("strict_blocked", reason_code="domain_blocked"),
            },
            db_readback={
                "accepted_doc_count": 1,
                "accepted_doc_ids": [101],
                "rejected_doc_count": 0,
                "rejected_doc_ids": [],
            },
        )
        validation = validate_production_like_handoff_evidence(evidence)

        self.assertTrue(evidence["live_canary_validated"])
        self.assertFalse(evidence["closure_claim"])
        self.assertEqual(validation["status"], "passed")
        self.assertTrue(validation["passed"])

    def test_live_evidence_promotes_handoff_without_closure_claim(self):
        evidence = build_production_like_handoff_evidence(
            project_key="wave55_canary",
            accepted_url="https://example.com/article",
            rejected_url="https://example.com/search?q=wave55",
            accepted_status_code=200,
            rejected_status_code=200,
            accepted_result={
                "status": "success",
                "canary_handoff": _handoff("strict_passed"),
            },
            rejected_result={
                "status": "failed",
                "canary_handoff": _handoff("strict_blocked", reason_code="domain_blocked"),
            },
            db_readback={"accepted_doc_count": 1, "accepted_doc_ids": [101], "rejected_doc_count": 0},
        )
        postprocess = {
            "status": "ok",
            "data": {
                "admission": "accept",
                "writer_result": {"inserted": 1, "doc_id": 101},
                "quality_assessment": {
                    "quality_score": 95.0,
                    "meaningful": True,
                    "provenance_ok": True,
                    "content_ok": True,
                    "strict_gate_enabled": True,
                    "strict_gate_source": "settings.ingest_guardrail_rollout_mode:canary",
                    "guardrail_rollout_mode": "canary",
                    "guardrail_canary_matched": True,
                    "guardrail_closure_claim": False,
                },
                "quality_gates": {
                    "gate_plus": {"blocked": False},
                    "gate_config": {
                        "enable_strict_gate": True,
                        "strict_gate_source": "settings.ingest_guardrail_rollout_mode:canary",
                        "guardrail_rollout": {
                            "contract_version": "ingest.guardrail_rollout.v1",
                            "enable_strict_gate": True,
                            "strict_gate_source": "settings.ingest_guardrail_rollout_mode:canary",
                            "rollout_mode": "canary",
                            "project_key": "wave55_canary",
                            "canary_projects": ["wave55_canary"],
                            "canary_matched": True,
                            "global_default_enabled": False,
                            "live_canary_validated": False,
                            "closure_claim": False,
                        },
                    },
                },
            },
            "meta": {"trace_id": "trace-wave55", "reason_code": "ok"},
        }
        handoff = build_single_url_canary_handoff(
            ingress_envelope={
                "contract_version": "frontdoor.ingress.v1",
                "ingress_type": "source_library",
                "entrypoint": "ingest.url.single",
                "source_mode": "url_execution",
                "project_key": "wave55_canary",
                "source_ref": {"url": "https://example.com/article"},
            },
            postprocess_frontdoor=postprocess,
            writer_result={"inserted": 1, "doc_id": 101},
            live_canary_evidence=evidence,
        )

        self.assertEqual(handoff["handoff_state"], "live_canary_validated")
        self.assertTrue(handoff["live_canary_validated"])
        self.assertFalse(handoff["closure_claim"])
        self.assertTrue(handoff["remaining_live_run_gaps"])
        self.assertNotIn("live canary execution has not been run", " ".join(handoff["remaining_live_run_gaps"]))
        self.assertTrue(handoff["metrics_snapshot"]["guardrail_rollout"]["live_canary_validated"])


if __name__ == "__main__":
    unittest.main()
