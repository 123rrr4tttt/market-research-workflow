from __future__ import annotations

from datetime import date, datetime, timezone
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.stats import prompt_time_density

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


def _fake_density_rows(*, start: date, end: date, **_: object) -> list[dict[str, object]]:
    window_days = (end - start).days + 1
    return [
        {
            "source_domain": "neutral.example",
            "noun_group_id": "robotics",
            "prompt_group_id": "robotics",
            "bucket_time": end.isoformat(),
            "effective_new_docs": 2,
            "density": 2.0 / float(window_days),
            "baseline_density": 0.1,
            "norm_density": 0.2,
            "dup_ratio": 0.0,
            "effective_time_provenance": {
                "total_docs": 2,
                "source_counts": {"source_time": 2},
                "gap_counts": {"effective_time_missing": 2},
                "parse_versions": ["policy-time-expr-v1"],
                "fallback_chain": [
                    "extracted_data.effective_time",
                    "extracted_data.source_time",
                    "extracted_data.policy.effective_date",
                    "publish_date",
                    "created_at",
                ],
            },
        }
    ]


def _load_contract_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "check_time_density_decision_log_contract.py"
    spec = importlib.util.spec_from_file_location("check_time_density_decision_log_contract", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load time-density decision-log checker: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PromptTimeDensityDecisionLogContractUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"prompt time density tests require backend dependencies: {_IMPORT_ERROR}")

    def test_effective_time_provenance_prefers_source_time_and_marks_missing_effective_time(self) -> None:
        doc = SimpleNamespace(
            extracted_data={"source_time": "2026-03-02T12:00:00Z"},
            publish_date=date(2026, 3, 1),
            created_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
        )

        provenance = prompt_time_density.resolve_document_effective_time_provenance(doc)

        self.assertEqual(provenance["effective_day"], "2026-03-02")
        self.assertEqual(provenance["source"], "source_time")
        self.assertEqual(provenance["source_field"], "extracted_data.source_time")
        self.assertIn("effective_time_missing", provenance["gap_markers"])
        self.assertNotIn("semantic_time_fallback_used", provenance["gap_markers"])

    def test_priority_rows_carry_decision_log_freshness_contract(self) -> None:
        captured: dict[str, object] = {}

        def capture_persist(
            *,
            request_id: str,
            rows: list[dict[str, object]],
            chosen_window: str,
            project_key: str | None = None,
        ) -> None:
            captured["request_id"] = request_id
            captured["chosen_window"] = chosen_window
            captured["project_key"] = project_key
            captured["rows"] = rows

        with patch.object(
            prompt_time_density,
            "query_prompt_time_density",
            side_effect=_fake_density_rows,
        ), patch.object(
            prompt_time_density,
            "_persist_policy_decision_logs",
            side_effect=capture_persist,
        ):
            rows = prompt_time_density.query_prompt_time_density_priority(
                end=date(2026, 3, 31),
                candidate_windows=["7d", "30d", "90d"],
                min_overlap=0.35,
                target_overlap=0.95,
                eta=1.0,
                delta_max=1.0,
                tau=10.0,
                avoid_peak=True,
                project_key="demo_proj",
            )

        self.assertEqual(captured["project_key"], "demo_proj")
        self.assertTrue(rows)
        row = rows[0]
        trace = dict(row["policy_decision_trace"])
        features = prompt_time_density.build_time_density_decision_log_features(row, trace)

        self.assertEqual(
            trace["contract_version"],
            prompt_time_density.TIME_DENSITY_DECISION_LOG_CONTRACT_VERSION,
        )
        self.assertEqual(trace["effective_time_provenance"]["source_counts"]["source_time"], 2)
        self.assertEqual(trace["effective_time_source_distribution"]["source_time_count"], 2)
        self.assertEqual(trace["effective_time_source_distribution"]["source_time_coverage"], 1.0)
        self.assertEqual(trace["ope_freshness_inputs"]["freshness_timestamp_field"], "created_at")
        self.assertEqual(trace["ope_freshness_inputs"]["feedback_table"], "public.prompt_time_window_feedback")
        self.assertEqual(trace["priority_decision_trace"]["behavior_policy"], "highest_p_base_window_for_ope_replay")
        self.assertIn("p_new_desc", trace["priority_decision_trace"]["sort_order"])
        self.assertIn("prompt_time_window_feedback_pending", trace["live_data_gap_markers"])
        self.assertIn("production_freshness_probe_not_run", trace["live_data_gap_markers"])
        self.assertIn("effective_time_gap:effective_time_missing", trace["live_data_gap_markers"])

        self.assertEqual(features["contract_version"], trace["contract_version"])
        self.assertTrue(features["effective_time_provenance"])
        self.assertEqual(features["effective_time_source_distribution"]["source_time_count"], 2)
        self.assertEqual(features["source_time_coverage"], 1.0)
        self.assertTrue(features["ope_freshness_inputs"])
        self.assertTrue(features["priority_decision_trace"])
        self.assertTrue(features["live_data_gap_markers"])

    def test_checker_reports_bounded_contract_and_known_gaps(self) -> None:
        module = _load_contract_module()
        contract = module.build_contract()

        self.assertEqual(
            contract["contract_version"],
            prompt_time_density.TIME_DENSITY_DECISION_LOG_CONTRACT_VERSION,
        )
        self.assertEqual(contract["status"], "passed_with_known_gaps")
        self.assertEqual(contract["failures"], [])
        self.assertTrue(
            contract["checks"]["decision_log_contract"]["effective_time_source_distribution_recorded"]
        )
        self.assertTrue(
            contract["checks"]["persisted_payload_shape"]["features_json_carries_source_distribution"]
        )
        self.assertIn(
            "production_freshness_not_claimed_by_local_contract",
            contract["remaining_gaps"],
        )


if __name__ == "__main__":
    unittest.main()
