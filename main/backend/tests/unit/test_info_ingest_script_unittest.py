from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit


def _load_script_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "信息采集测试.py"
    spec = importlib.util.spec_from_file_location("info_ingest_test_script", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load script module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InfoIngestScriptUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = _load_script_module()

    def test_compute_rejected_count_prefers_direct_value(self):
        fn = self.script._compute_rejected_count
        self.assertEqual(fn({"rejected_count": 3, "rejection_breakdown": {"a": 10}}), 3)

    def test_compute_rejected_count_fallbacks_to_breakdown_sum(self):
        fn = self.script._compute_rejected_count
        self.assertEqual(fn({"rejection_breakdown": {"a": 2, "b": 5}}), 7)
        self.assertEqual(fn({"rejection_breakdown": {"a": "x", "b": 5}}), 5)

    def test_validate_row_shape_requires_minimum_fields(self):
        fn = self.script._validate_row_shape
        row = {
            "status": "success",
            "inserted_valid": 1,
            "rejected_count": 0,
            "rejection_breakdown": {},
            "doc_id": 12,
            "content_len": 2000,
        }
        self.assertEqual(fn(row), [])
        bad = dict(row)
        bad.pop("doc_id")
        missing = fn(bad)
        self.assertIn("doc_id", missing)


if __name__ == "__main__":
    unittest.main()
