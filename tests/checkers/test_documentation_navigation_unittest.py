"""Current navigation and retained evidence must remain independently checked."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_checker(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


status = load_checker("docs_current_status", "scripts/check_current_dev_status_evidence.py")
navigation = load_checker("docs_navigation", "scripts/checkers/check_docs_root_navigation_drift.py")


class RetainedEvidenceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.index = self.root / status.DEFAULT_INDEX
        self.index.parent.mkdir(parents=True)
        self.index.write_text("- `partial`: 0\n- `not_closed`: 0\n- `no_closure_claim`: 0\n")
        self.history = self.index.parent / "completed"
        (self.history / "empty-artifact").mkdir(parents=True)

    def declare_history(self):
        (self.root / status.TOPIC_ALLOWLIST).write_text(json.dumps({
            "evidence_roots": [{"path": str(self.history.relative_to(self.root))}]
        }))

    def test_declared_evidence_is_not_an_active_topic(self):
        self.declare_history()
        self.assertTrue(status.check(self.root, status.DEFAULT_INDEX).ok)

    def test_undeclared_topics_and_empty_artifacts_still_fail(self):
        result = status.check(self.root, status.DEFAULT_INDEX)
        self.assertEqual(result.inactive_dirs, (self.history,))
        self.assertEqual(result.empty_dirs, (self.history / "empty-artifact",))
        self.assertFalse(result.ok)

    def test_missing_declared_evidence_fails(self):
        self.declare_history()
        (self.history / "empty-artifact").rmdir()
        self.history.rmdir()
        result = status.check(self.root, status.DEFAULT_INDEX)
        self.assertFalse(result.ok)
        self.assertTrue(any("missing" in p.message for p in result.problems))

    def test_invalid_classification_fails(self):
        (self.root / status.TOPIC_ALLOWLIST).write_text('{"evidence_roots": false}')
        self.assertTrue(any("invalid topic classification" in p.message
                            for p in status.check(self.root, status.DEFAULT_INDEX).problems))


class HistoricalNavigationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.surface = navigation.Surface("current", Path("docs/development/README.md"))
        self.entry = self.root / self.surface.path
        self.entry.parent.mkdir(parents=True)
        self.entry.write_text("[history](../history/documentation-migration.md)\n")
        self.history = self.root / navigation.EVIDENCE_INDEX
        self.history.parent.mkdir()
        self.anchor = Path("docs/history/original.md")
        (self.root / self.anchor).write_text("original evidence\n")

    def test_one_shared_index_preserves_anchor_reachability(self):
        self.history.write_text("[original](original.md)\n")
        problems = []
        missing = navigation.missing_references(self.root, [self.anchor], (self.surface,), problems)
        self.assertEqual((missing, problems), ([], []))

    def test_missing_anchor_reference_is_not_hidden_by_index_link(self):
        self.history.write_text("# History\n")
        self.assertEqual(len(navigation.missing_references(
            self.root, [self.anchor], (self.surface,), [])), 1)

    def test_missing_index_and_broken_targets_fail(self):
        problems = []
        navigation.missing_references(self.root, [self.anchor], (self.surface,), problems)
        self.assertTrue(problems)
        self.history.write_text("[original](absent.md)\n")
        problems = []
        navigation.missing_references(self.root, [self.anchor], (self.surface,), problems)
        self.assertTrue(any("absent.md" in p.message for p in problems))

    def test_direct_historical_links_remain_supported(self):
        self.entry.write_text("[original](../history/original.md)\n")
        self.assertEqual(navigation.missing_references(
            self.root, [self.anchor], (self.surface,), []), [])


if __name__ == "__main__":
    unittest.main()
