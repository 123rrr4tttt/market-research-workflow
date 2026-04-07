from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.collect_runtime.contracts import CollectRequest, CollectResult
    from app.services.collect_runtime import runtime

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class CollectRuntimeAutoBatchUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"collect_runtime auto-batch unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_auto_batch_uses_parallelism_from_options_and_emits_diagnostics(self):
        request = CollectRequest(
            channel="search.market",
            query_terms=["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"],
            limit=80,
            source_context={"summary": "市场信息采集", "batch_parallelism": 1},
            options={"batch_parallelism": 2},
        )
        active = 0
        max_active = 0
        lock = threading.Lock()

        def _fake_run(sub_request: CollectRequest) -> CollectResult:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return CollectResult(
                channel=sub_request.channel,
                inserted=len(sub_request.query_terms),
                meta={"raw": {"links": [f"https://example.com/{sub_request.query_terms[0]}"]}},
            )

        with patch("app.services.collect_runtime.runtime._run_collect_no_batch", side_effect=_fake_run):
            result = runtime._maybe_run_auto_batched(request)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreaterEqual(max_active, 2)
        self.assertEqual(result.inserted, 8)
        self.assertEqual(result.meta["batch_parallelism"], 2)
        self.assertEqual(result.meta["batch_parallelism_requested"], 2)
        self.assertFalse(result.meta["batch_fail_fast"])
        self.assertEqual(result.meta["raw"]["batch_parallelism"], 2)
        self.assertEqual(result.meta["raw"]["batches_total"], 2)
        self.assertEqual(result.meta["query_term_batches"], [["t1", "t2", "t3", "t4"], ["t5", "t6", "t7", "t8"]])

    def test_auto_batch_isolates_failures_by_default(self):
        request = CollectRequest(
            channel="search.market",
            query_terms=["a1", "a2", "a3", "a4", "b1", "b2", "b3", "b4", "c1"],
            limit=90,
            source_context={"summary": "市场信息采集"},
        )

        def _fake_run(sub_request: CollectRequest) -> CollectResult:
            if sub_request.query_terms[0] == "b1":
                raise RuntimeError("batch exploded")
            return CollectResult(
                channel=sub_request.channel,
                inserted=len(sub_request.query_terms),
                meta={"raw": {"links": [f"https://example.com/{sub_request.query_terms[0]}"]}},
            )

        with patch("app.services.collect_runtime.runtime._run_collect_no_batch", side_effect=_fake_run):
            result = runtime._maybe_run_auto_batched(request)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.inserted, 5)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0]["code"], "auto_batch_execution_failed")
        self.assertEqual(result.meta["batches_total"], 3)
        self.assertEqual(result.meta["batches_failed"], 1)
        self.assertEqual(result.meta["batches_succeeded"], 2)
        self.assertEqual(result.meta["raw"]["batches_failed"], 1)
        self.assertEqual(result.meta["raw"]["batches_succeeded"], 2)


if __name__ == "__main__":
    unittest.main()
