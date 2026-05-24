from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.ingest.canary_handoff_live import build_production_like_handoff_evidence
from app.services.ingest.canary_strict_promotion import (
    OPS_PROMOTION_BLOCKERS,
    OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER,
    OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION,
    PRODUCTION_24H_BLOCKERS,
    PRODUCTION_24H_METRICS_CONTRACT_VERSION,
    build_strict_promotion_readiness,
    validate_strict_promotion_readiness,
)
from scripts.check_ingest_canary_24h_metrics_artifact import build_24h_metrics_artifact


pytestmark = pytest.mark.unit


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


def _live_evidence() -> dict:
    return build_production_like_handoff_evidence(
        project_key="demo_proj",
        accepted_url="https://example.com/article",
        rejected_url="https://example.com/search?q=wave55",
        accepted_status_code=200,
        rejected_status_code=200,
        accepted_result={"status": "success", "canary_handoff": _handoff("strict_passed")},
        rejected_result={
            "status": "failed",
            "canary_handoff": _handoff("strict_blocked", reason_code="domain_blocked"),
        },
        db_readback={"accepted_doc_count": 1, "accepted_doc_ids": [101], "rejected_doc_count": 0},
    )


def _production_metrics_artifact() -> dict:
    artifact = build_24h_metrics_artifact(project_key="demo_proj")
    artifact.update(
        {
            "contract_version": PRODUCTION_24H_METRICS_CONTRACT_VERSION,
            "artifact_kind": "production_ingest_canary_24h_metrics_readback",
            "deterministic_fixture": False,
            "evidence_scope": "production",
            "generated_by": "ops_production_metrics_export",
            "source_record": {
                "record_id": "ops-prod-ingest-24h-20260524",
                "system": "production_metrics_export",
                "generated_at": "2026-05-24T00:05:00Z",
            },
        }
    )
    artifact["window"]["window_label"] = "production_24h"
    artifact["window"]["live_window_observed"] = True
    artifact["live_boundaries"].update(
        {
            "live_production_canary_claim": True,
            "metric_24h_live_readback_claim": True,
            "production_data_claim": True,
            "closure_claim": False,
            "remaining_live_gaps": [],
        }
    )
    return artifact


def _ops_promotion_evidence() -> dict:
    return {
        "contract_version": OPS_STRICT_GATE_PROMOTION_CONTRACT_VERSION,
        "evidence_scope": "operations",
        "operations_approval_recorded": True,
        "production_24h_metrics_reviewed": True,
        "rollback_plan_recorded": True,
        "promotion_decision": "promote",
        "strict_gate_global_default_enabled": True,
        "approved_by": "ops-oncall",
        "approved_at": "2026-05-24T00:15:00Z",
        "approval_ticket": "OPS-INGEST-STRICT-20260524",
        "rollback_plan_ref": "runbook://ingest-strict-gate-rollback",
    }


class IngestCanaryStrictPromotionReadinessUnitTestCase(unittest.TestCase):
    def test_repo_local_preflight_passes_but_production_and_ops_remain_external(self) -> None:
        report = build_strict_promotion_readiness(
            project_key="demo_proj",
            live_canary_evidence=_live_evidence(),
            metrics_artifact=build_24h_metrics_artifact(project_key="demo_proj"),
        )
        payload = report.to_dict()
        remaining = {item["id"] for item in payload["remaining_external_blockers"]}

        self.assertEqual(validate_strict_promotion_readiness(payload), [])
        self.assertEqual(report.status, "external_blocked")
        self.assertTrue(report.repo_local_preflight_passed)
        self.assertTrue(report.repo_local_live_canary_validated)
        self.assertTrue(report.repo_local_metric_24h_shape_validated)
        self.assertFalse(report.production_24h_metrics_satisfied)
        self.assertFalse(report.strict_gate_promotion_satisfied)
        self.assertFalse(report.closure_claim)
        self.assertTrue(set(PRODUCTION_24H_BLOCKERS).issubset(remaining))
        self.assertTrue(set(OPS_PROMOTION_BLOCKERS).issubset(remaining))
        self.assertEqual(
            report.promotion_recommendation,
            "do_not_promote_without_production_24h_metrics_and_operations_decision",
        )

    def test_production_metrics_artifact_clears_only_production_blockers(self) -> None:
        report = build_strict_promotion_readiness(
            project_key="demo_proj",
            live_canary_evidence=_live_evidence(),
            metrics_artifact=_production_metrics_artifact(),
        )
        payload = report.to_dict()
        remaining = {item["id"] for item in payload["remaining_external_blockers"]}

        self.assertEqual(validate_strict_promotion_readiness(payload), [])
        self.assertEqual(report.status, "external_blocked")
        self.assertTrue(report.repo_local_preflight_passed)
        self.assertTrue(report.production_24h_metrics_satisfied)
        self.assertFalse(report.strict_gate_promotion_satisfied)
        self.assertFalse(report.closure_claim)
        self.assertFalse(set(PRODUCTION_24H_BLOCKERS).intersection(remaining))
        self.assertTrue(set(OPS_PROMOTION_BLOCKERS).issubset(remaining))

    def test_valid_production_and_ops_artifacts_can_close_when_claimed(self) -> None:
        report = build_strict_promotion_readiness(
            project_key="demo_proj",
            live_canary_evidence=_live_evidence(),
            metrics_artifact=_production_metrics_artifact(),
            ops_promotion_evidence=_ops_promotion_evidence(),
            closure_claim=True,
        )
        payload = report.to_dict()

        self.assertEqual(validate_strict_promotion_readiness(payload), [])
        self.assertEqual(report.status, "closed")
        self.assertTrue(report.closure_claim)
        self.assertTrue(report.production_24h_metrics_satisfied)
        self.assertTrue(report.strict_gate_promotion_satisfied)
        self.assertEqual(payload["remaining_external_blockers"], [])
        self.assertEqual(report.promotion_recommendation, "promotion_evidence_satisfied")

    def test_invalid_ops_artifact_does_not_clear_ops_boundary(self) -> None:
        ops_evidence = _ops_promotion_evidence()
        ops_evidence.pop("approval_ticket")
        report = build_strict_promotion_readiness(
            project_key="demo_proj",
            live_canary_evidence=_live_evidence(),
            metrics_artifact=_production_metrics_artifact(),
            ops_promotion_evidence=ops_evidence,
            closure_claim=True,
        )
        payload = report.to_dict()
        remaining = {item["id"] for item in payload["remaining_external_blockers"]}

        self.assertEqual(validate_strict_promotion_readiness(payload), [])
        self.assertEqual(report.status, "external_blocked")
        self.assertFalse(report.closure_claim)
        self.assertFalse(report.strict_gate_promotion_satisfied)
        self.assertIn(OPS_PROMOTION_EVIDENCE_INVALID_BLOCKER, remaining)

    def test_missing_live_evidence_keeps_repo_local_blocked(self) -> None:
        report = build_strict_promotion_readiness(
            project_key="demo_proj",
            live_canary_evidence=None,
            metrics_artifact=build_24h_metrics_artifact(project_key="demo_proj"),
        )
        remaining = {item["id"] for item in report.to_dict()["remaining_external_blockers"]}

        self.assertEqual(report.status, "repo_local_blocked")
        self.assertFalse(report.repo_local_preflight_passed)
        self.assertIn("repo_local_live_canary_evidence_missing", remaining)
        self.assertFalse(report.closure_claim)

    def test_validator_rejects_non_closed_closure_claim(self) -> None:
        report = build_strict_promotion_readiness(
            project_key="demo_proj",
            live_canary_evidence=_live_evidence(),
            metrics_artifact=build_24h_metrics_artifact(project_key="demo_proj"),
        ).to_dict()
        report["closure_claim"] = True

        errors = validate_strict_promotion_readiness(report)

        self.assertTrue(any("closure_claim" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
