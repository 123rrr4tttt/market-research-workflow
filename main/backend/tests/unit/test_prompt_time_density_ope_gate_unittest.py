from __future__ import annotations

from datetime import datetime, timezone
import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from scripts.generate_prompt_time_density_gonogo import build_gonogo_report
from scripts.run_prompt_time_density_ope import evaluate_ope


def _rows(*, created_at: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for request_id in ("req-1", "req-2", "req-3"):
        for window, p_base, p_new, chosen in (
            ("7d", 0.40, 0.55, True),
            ("30d", 0.35, 0.30, False),
            ("90d", 0.25, 0.15, False),
        ):
            out.append(
                {
                    "request_id": request_id,
                    "source_domain": "neutral.example",
                    "noun_group_id": "robotics",
                    "window": window,
                    "chosen_window": "7d",
                    "is_chosen": chosen,
                    "p_base": p_base,
                    "p_new": p_new,
                    "vector_overlap": 0.62,
                    "offpeak_confidence": 0.7,
                    "observed_reward": 0.75 if chosen else None,
                    "features_json": {"dup_ratio": 0.0, "peak_pressure": 0.2},
                    "created_at": created_at,
                }
            )
    return out


class PromptTimeDensityOpeGateUnitTest(unittest.TestCase):
    def test_ope_report_includes_freshness_and_weight_diagnostics(self) -> None:
        report = evaluate_ope(
            _rows(created_at="2026-05-22T10:00:00+00:00"),
            n_bootstrap=50,
            now=datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
            stale_after_hours=24.0,
        )
        self.assertEqual(report["summary"]["contexts_used"], 3)
        self.assertEqual(report["freshness"]["status"], "fresh")
        self.assertAlmostEqual(report["freshness"]["latest_age_hours"], 2.0)
        self.assertGreater(report["diagnostics"]["effective_sample_size_ratio"], 0.0)
        self.assertLessEqual(report["diagnostics"]["weight_cv"], 2.5)

    def test_gonogo_requires_fresh_ope_when_flagged(self) -> None:
        fresh = evaluate_ope(
            _rows(created_at="2026-05-22T10:00:00+00:00"),
            n_bootstrap=50,
            now=datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
            stale_after_hours=24.0,
        )
        stale = evaluate_ope(
            _rows(created_at="2026-05-18T10:00:00+00:00"),
            n_bootstrap=50,
            now=datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
            stale_after_hours=24.0,
        )
        base_kwargs = {
            "realcase": {"failed": 0},
            "perf": {"api_p95_seconds": 0.3, "api_error_rate": 0.0},
            "require_ope": True,
            "ope_min_contexts": 2,
            "ope_max_latest_age_hours": 24.0,
            "ope_min_ess_ratio": 0.2,
            "ope_max_weight_cv": 2.5,
        }
        self.assertEqual(build_gonogo_report(ope=fresh, **base_kwargs)["decision"], "GO")
        stale_gate = build_gonogo_report(ope=stale, **base_kwargs)
        self.assertEqual(stale_gate["decision"], "NO-GO")
        self.assertFalse(stale_gate["gates"]["ope_freshness"])

    def test_gonogo_requires_ope_file_when_flagged(self) -> None:
        gate = build_gonogo_report(
            realcase={"failed": 0},
            perf={"api_p95_seconds": 0.3, "api_error_rate": 0.0},
            require_ope=True,
        )
        self.assertEqual(gate["decision"], "NO-GO")
        self.assertFalse(gate["gates"]["ope_present"])


if __name__ == "__main__":
    unittest.main()
