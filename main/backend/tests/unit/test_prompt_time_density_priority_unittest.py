from __future__ import annotations

from datetime import date
import sys
import unittest
from pathlib import Path
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
            "effective_new_docs": 3,
            "density": 3.0 / float(window_days),
            "baseline_density": 0.1,
            "norm_density": 0.2,
            "dup_ratio": 0.0,
        }
    ]


class PromptTimeDensityPriorityUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"prompt time density tests require backend dependencies: {_IMPORT_ERROR}")

    def _query(self, *, target_overlap: float) -> dict[str, dict[str, object]]:
        with patch.object(
            prompt_time_density,
            "query_prompt_time_density",
            side_effect=_fake_density_rows,
        ), patch.object(
            prompt_time_density,
            "_persist_policy_decision_logs",
        ):
            rows = prompt_time_density.query_prompt_time_density_priority(
                end=date(2026, 3, 31),
                candidate_windows=["7d", "30d", "90d"],
                min_overlap=0.35,
                target_overlap=target_overlap,
                eta=1.0,
                delta_max=1.0,
                tau=10.0,
                avoid_peak=True,
            )
        return {str(row["window"]): row for row in rows}

    def test_target_overlap_gap_enters_shift_signal_and_probability(self):
        low_target = self._query(target_overlap=0.55)
        high_target = self._query(target_overlap=0.95)

        self.assertEqual(low_target["7d"]["target_overlap_gap"], 0.0)
        self.assertEqual(low_target["30d"]["target_overlap_gap"], 0.0)
        self.assertEqual(low_target["90d"]["target_overlap_gap"], 0.0)
        self.assertEqual(high_target["7d"]["target_overlap_gap"], 0.0)
        self.assertGreater(
            float(high_target["90d"]["target_overlap_gap"]),
            float(high_target["30d"]["target_overlap_gap"]),
        )

        self.assertGreater(float(high_target["90d"]["shift_signal"]), float(low_target["90d"]["shift_signal"]))
        self.assertGreater(float(high_target["7d"]["p_new"]), float(low_target["7d"]["p_new"]))
        self.assertLess(float(high_target["90d"]["p_new"]), float(low_target["90d"]["p_new"]))

        trace = dict(high_target["90d"]["policy_decision_trace"])
        breakdown = dict(trace["shift_signal_breakdown"])
        self.assertEqual(breakdown["target_overlap"], 0.95)
        self.assertEqual(breakdown["target_overlap_gap"], high_target["90d"]["target_overlap_gap"])


if __name__ == "__main__":
    unittest.main()
