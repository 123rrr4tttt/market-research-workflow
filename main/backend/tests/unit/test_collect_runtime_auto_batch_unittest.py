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

    def _successor_request(self, **kwargs):
        options = kwargs.pop("options", {})
        return CollectRequest(
            channel="search.market",
            project_key="successor-test",
            query_terms=["a1", "a2", "a3", "a4", "b1", "b2", "b3", "b4"],
            limit=80,
            options=options,
            **kwargs,
        )

    def test_successor_route_calls_typed_c3_interpreter_and_orders_outcomes(self):
        calls = []

        class _Adapter:
            def run(self, request):
                calls.append(tuple(request.query_terms))
                return CollectResult(
                    channel=request.channel,
                    status="completed",
                    inserted=len(request.query_terms),
                    meta={"raw": {"links": [f"https://example/{request.query_terms[0]}"]}, "terminal_readback": {"kind": "terminal", "status": "completed"}},
                    provider_job_id=f"job-{request.query_terms[0]}",
                    provider_type="fixture",
                    provider_status="completed",
                    attempt_count=1,
                )

        runtime.reset_collect_adapters()
        adapter = _Adapter()
        runtime.register_collect_skill("search.market", adapter)
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                from app.successor_runtime.capabilities import collect_c3_interpreters as ci

                original_interpret = ci.CollectTraversalSuccessorInterpreter.interpret
                with patch("app.successor_runtime.capabilities.collect_c3_interpreters.CollectTraversalSuccessorInterpreter.interpret", autospec=True) as interpret:
                    interpret.side_effect = original_interpret
                    result = runtime.run_collect(self._successor_request())
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.meta["raw"]["aggregate_kind"], "succeeded")
            self.assertEqual(result.meta["raw"]["ordered_outcomes"]["outcomes"][0]["input_index"], 0)
            self.assertEqual(len(calls), 2)
            self.assertGreaterEqual(interpret.call_count, 2)
        finally:
            runtime.reset_collect_adapters()
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_partial_projection_is_not_completed(self):
        class _Adapter:
            def run(self, request):
                if request.query_terms[0] == "b1":
                    return CollectResult(channel=request.channel, status="failed", errors=[{"code": "x", "message": "bad"}])
                return CollectResult(channel=request.channel, status="completed", inserted=4, meta={"raw": {}, "terminal_readback": {"kind": "terminal", "status": "completed"}})

        runtime.reset_collect_adapters()
        adapter = _Adapter()
        runtime.register_collect_skill("search.market", adapter)
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                result = runtime.run_collect(self._successor_request())
            self.assertEqual(result.status, "partial")
            self.assertEqual(result.meta["raw"]["aggregate_kind"], "partial")
            self.assertEqual(len(result.meta["ordered_outcomes"].outcomes), 2)
        finally:
            runtime.reset_collect_adapters()
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_all_failed_projection_is_failed(self):
        class _Adapter:
            def run(self, request):
                return CollectResult(channel=request.channel, status="failed", errors=[{"code": "x", "message": "bad"}])

        runtime.reset_collect_adapters()
        adapter = _Adapter()
        runtime.register_collect_skill("search.market", adapter)
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                result = runtime.run_collect(self._successor_request())
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.meta["raw"]["aggregate_kind"], "failed")
        finally:
            runtime.reset_collect_adapters()
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_fail_fast_projection_is_cancelled_and_keeps_receipts(self):
        class _Adapter:
            def run(self, request):
                if request.query_terms[0] == "b1":
                    return CollectResult(channel=request.channel, status="failed", errors=[{"code": "x", "message": "bad"}])
                return CollectResult(
                    channel=request.channel,
                    status="completed",
                    inserted=4,
                    meta={"raw": {}, "terminal_readback": {"kind": "terminal", "status": "completed"}},
                    provider_job_id="job-a",
                    provider_type="fixture",
                    provider_status="queued",
                    attempt_count=1,
                )

        runtime.reset_collect_adapters()
        adapter = _Adapter()
        runtime.register_collect_skill("search.market", adapter)
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                result = runtime.run_collect(self._successor_request(options={"batch_fail_fast": True}))
            self.assertEqual(result.status, "cancelled")
            self.assertIn("cancellation_receipt", result.meta["raw"])
            self.assertEqual(result.meta["raw"]["receipts"][0]["provider_job_id"], "job-a")
        finally:
            runtime.reset_collect_adapters()
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_parallelism_requires_explicit_independence_policy(self):
        active = 0
        maximum = 0
        lock = threading.Lock()

        class _Adapter:
            def run(self, request):
                nonlocal active, maximum
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                time.sleep(0.02)
                with lock:
                    active -= 1
                return CollectResult(channel=request.channel, status="completed", inserted=4, meta={"raw": {}, "terminal_readback": {"kind": "terminal", "status": "completed"}})

        runtime.reset_collect_adapters()
        adapter = _Adapter()
        runtime.register_collect_skill("search.market", adapter)
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                result = runtime.run_collect(self._successor_request(options={"batch_parallelism": 2}))
            self.assertEqual(maximum, 1)
            self.assertEqual(result.meta["batch_parallelism"], 1)
            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                result = runtime.run_collect(self._successor_request(options={"batch_parallelism": 2, "batch_independence_policy": "explicit"}))
            self.assertGreaterEqual(maximum, 2)
            self.assertEqual(result.meta["batch_parallelism"], 2)
        finally:
            runtime.reset_collect_adapters()
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_without_effect_gateway_is_unknown_and_does_not_use_legacy_registry(self):
        calls = []

        class _LegacyAdapter:
            def run(self, request):
                calls.append(request)
                raise AssertionError("legacy adapter must not run on successor route")

        runtime.reset_collect_adapters()
        runtime.register_collect_skill("search.market", _LegacyAdapter())
        runtime.reset_successor_collect_effect_gateway()
        try:
            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                result = runtime.run_collect(self._successor_request())
                small = CollectRequest(channel="search.market", project_key="successor-test", query_terms=["one"], limit=1)
                small_result = runtime.run_collect(small)
            self.assertEqual(result.status, "unknown")
            self.assertEqual(result.meta["raw"]["outcome"], "OutcomeUnknown")
            self.assertEqual(calls, [])
            self.assertEqual(small_result.status, "unknown")
            self.assertEqual(calls, [])
        finally:
            runtime.reset_collect_adapters()


if __name__ == "__main__":
    unittest.main()
