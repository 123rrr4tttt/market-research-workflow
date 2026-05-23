from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import pytest

pytestmark = pytest.mark.unit


def _load_checker_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "check_time_density_current_state.py"
    spec = importlib.util.spec_from_file_location("check_time_density_current_state", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load time-density current-state checker: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TimeDensityCurrentStateCheckerTest(unittest.TestCase):
    def test_checker_reports_current_state_with_known_gaps(self) -> None:
        module = _load_checker_module()
        state = module.build_current_state()

        self.assertEqual(state["contract_version"], "time-density-current-state-doc-provenance.v1")
        self.assertEqual(state["status"], "passed_with_known_gaps")
        self.assertEqual(state["failures"], [])
        self.assertTrue(state["checks"]["runtime_contracts_current"])
        self.assertTrue(state["checks"]["evidence_markers_current"])
        self.assertTrue(state["checks"]["stale_taxonomy_markers_present"])
        self.assertEqual(state["evidence"]["time_statistics"]["status"], "current")
        self.assertEqual(state["evidence"]["source_time_window"]["status"], "current")
        self.assertEqual(state["evidence"]["time_semantics_density"]["status"], "current")
        self.assertIn("ARCHIVE_EXTERNAL_BLOCKED", state["evidence"]["time_statistics"]["path"])
        self.assertIn(
            "production_freshness_not_claimed_by_local_contract",
            state["remaining_gaps"],
        )

    def test_checker_falls_back_to_current_dev_evidence_when_archive_is_absent(self) -> None:
        module = _load_checker_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for topic in module.EVIDENCE_TOPICS:
                source = module.REPO_ROOT / topic.paths[0]
                target = root / topic.paths[1]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

            state = module.build_current_state(repo_root=root)

        self.assertEqual(state["status"], "passed_with_known_gaps")
        self.assertEqual(state["failures"], [])
        self.assertTrue(all("CURRENT_DEV" in item["path"] for item in state["evidence"].values()))

    def test_marker_classifier_accepts_current_checker_backed_evidence(self) -> None:
        module = _load_checker_module()
        marker_state = module.classify_evidence_markers(
            """
            ## Local Stale/Drift Status
            - `doc_stale`: reduced by checker-backed evidence.
            - `doc_drift`: reduced by runtime provenance.
            - `external_gap`: still open for live data.
            ## Repeatable Validation
            - checker: `status=passed_with_known_gaps`, `failures=[]`
            - script: `main/backend/scripts/check_time_density_current_state.py`
            """,
            current_markers=(
                "check_time_density_current_state.py",
                "status=passed_with_known_gaps",
                "failures=[]",
            ),
        )

        self.assertEqual(marker_state["status"], "current")
        self.assertTrue(marker_state["current_markers_present"])
        self.assertTrue(marker_state["stale_taxonomy_markers_present"])
        self.assertEqual(marker_state["missing_current_markers"], [])

    def test_marker_classifier_flags_stale_evidence_without_current_validation(self) -> None:
        module = _load_checker_module()
        marker_state = module.classify_evidence_markers(
            """
            ## Local Stale/Drift Status
            - `doc_stale`: noted, but no repeatable checker result is recorded.
            - `doc_drift`: still possible.
            - `external_gap`: still open.
            """,
            current_markers=(
                "check_time_density_current_state.py",
                "status=passed_with_known_gaps",
                "failures=[]",
            ),
        )

        self.assertEqual(marker_state["status"], "stale")
        self.assertFalse(marker_state["current_markers_present"])
        self.assertTrue(marker_state["stale_taxonomy_markers_present"])
        self.assertIn("check_time_density_current_state.py", marker_state["missing_current_markers"])
        self.assertIn("status=passed_with_known_gaps", marker_state["missing_current_markers"])


if __name__ == "__main__":
    unittest.main()
