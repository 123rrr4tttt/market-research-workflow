from __future__ import annotations

import sys
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.collect_runtime import runtime
    from app.services.collect_runtime.contracts import CollectRequest, CollectResult

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
        self.assertEqual(max_active, 1)
        self.assertEqual(result.inserted, 8)
        self.assertEqual(result.meta["batch_parallelism"], 1)
        self.assertEqual(result.meta["batch_parallelism_requested"], 2)
        self.assertFalse(result.meta["batch_fail_fast"])
        self.assertEqual(result.meta["raw"]["batch_parallelism"], 1)
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

    def test_workflow_compat_parser_preserves_rollout_values_and_default(self):
        cases = [
            ({}, "legacy"),
            ({"INGEST_WORKFLOW_ADAPTER": "off"}, "legacy"),
            ({"INGEST_WORKFLOW_ADAPTER": "legacy"}, "legacy"),
            ({"INGEST_WORKFLOW_ADAPTER": "on"}, "workflow"),
            ({"INGEST_WORKFLOW_ADAPTER": "workflow"}, "workflow"),
            ({"INGEST_WORKFLOW_ADAPTER": "canary"}, "workflow"),
            ({"INGEST_WORKFLOW_ADAPTER": "unknown"}, "legacy"),
        ]
        for environment, expected in cases:
            with self.subTest(environment=environment):
                with patch.dict("os.environ", environment, clear=True):
                    self.assertEqual(runtime._resolve_workflow_mode(), expected)

    def test_workflow_compat_input_uses_original_dispatcher_and_batch_projection(self):
        request = CollectRequest(
            channel="search.market",
            query_terms=["a1", "a2", "a3", "a4", "b1", "b2", "b3", "b4"],
            limit=80,
            source_context={"summary": "市场信息采集"},
        )

        def _fake_dispatch(sub_request: CollectRequest) -> CollectResult:
            return CollectResult(
                channel=sub_request.channel,
                inserted=len(sub_request.query_terms),
                meta={"raw": {"query_terms": list(sub_request.query_terms)}},
            )

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("app.services.collect_runtime.runtime._run_collect_no_batch", side_effect=_fake_dispatch) as dispatch,
        ):
            default_result = runtime.run_collect(request)
            default_calls = [list(call.args[0].query_terms) for call in dispatch.call_args_list]

        with (
            patch.dict("os.environ", {"INGEST_WORKFLOW_ADAPTER": "workflow"}, clear=True),
            patch("app.services.collect_runtime.runtime._run_collect_no_batch", side_effect=_fake_dispatch) as dispatch,
        ):
            workflow_result = runtime.run_collect(request)
            workflow_calls = [list(call.args[0].query_terms) for call in dispatch.call_args_list]

        expected_calls = [["a1", "a2", "a3", "a4"], ["b1", "b2", "b3", "b4"]]
        self.assertEqual(default_calls, expected_calls)
        self.assertEqual(workflow_calls, expected_calls)
        for result in (default_result, workflow_result):
            self.assertEqual(result.inserted, 8)
            self.assertEqual(result.meta["query_term_batches"], expected_calls)
            self.assertEqual(
                [batch["query_terms"] for batch in result.meta["raw"]["batch_results"]],
                expected_calls,
            )
            self.assertEqual(result.meta["batch_parallelism"], 1)

    def test_explicit_off_overrides_workflow_compat_and_uses_legacy_effect(self):
        calls = []

        class _Adapter:
            def run(self, request):
                calls.append(tuple(request.query_terms))
                return CollectResult(channel=request.channel, inserted=1)

        runtime.reset_collect_adapters()
        runtime.reset_successor_collect_effect_gateway()
        runtime.register_collect_skill("search.market", _Adapter())
        try:
            environment = {
                "SUCCESSOR_RUNTIME_COLLECT": "off",
                "INGEST_WORKFLOW_ADAPTER": "workflow",
            }
            with patch.dict("os.environ", environment, clear=True):
                result = runtime.run_collect(CollectRequest(channel="search.market", query_terms=["one"]))
            self.assertEqual(result.status, "completed")
            self.assertEqual(calls, [("one",)])
        finally:
            runtime.reset_collect_adapters()

    def test_product_shadow_mode_is_rejected_before_legacy_effect(self):
        calls = []

        class _Adapter:
            def run(self, request):
                calls.append(request)
                raise AssertionError("shadow mode must not execute the legacy adapter")

        runtime.reset_collect_adapters()
        runtime.reset_successor_collect_effect_gateway()
        runtime.register_collect_skill("search.market", _Adapter())
        try:
            environment = {
                "SUCCESSOR_RUNTIME_COLLECT": "shadow",
                "INGEST_WORKFLOW_ADAPTER": "workflow",
            }
            with (
                patch.dict("os.environ", environment, clear=True),
                self.assertRaisesRegex(ValueError, "^Collect shadow mode is not implemented for product collection requests$"),
            ):
                runtime.run_collect(self._successor_request())
            self.assertEqual(calls, [])
            failure = runtime._collect_contract_failure(
                "product_mode_unsupported", "unsupported", site="run_collect.product_mode"
            )
            self.assertEqual(failure.family, "collect.runtime.failure")
            self.assertEqual(failure.code, "product_mode_unsupported")
        finally:
            runtime.reset_collect_adapters()

    def test_unknown_channel_failure_stays_at_original_dispatcher(self):
        runtime.reset_collect_adapters()
        runtime.reset_successor_collect_effect_gateway()
        request = CollectRequest(channel="not.registered", query_terms=["one"])
        for workflow_mode in (None, "workflow"):
            environment = {} if workflow_mode is None else {"INGEST_WORKFLOW_ADAPTER": workflow_mode}
            with self.subTest(workflow_mode=workflow_mode):
                with (
                    patch.dict("os.environ", environment, clear=True),
                    self.assertRaisesRegex(ValueError, "^unsupported collect channel: not.registered$"),
                ):
                    runtime.run_collect(request)

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
                    meta={"raw": {"links": [f"https://example/{request.query_terms[0]}"]}, "terminal_readback": {"kind": "terminal", "readback": {"provider_job_id": f"job-{request.query_terms[0]}", "terminal_status": "completed"}}},
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
                from app.successor_runtime.capabilities import acquisition_batch_interpreters as ci

                original_interpret = ci.CollectTraversalSuccessorInterpreter.interpret
                with patch("app.successor_runtime.capabilities.acquisition_batch_interpreters.CollectTraversalSuccessorInterpreter.interpret", autospec=True) as interpret:
                    interpret.side_effect = original_interpret
                    result = runtime.run_collect(self._successor_request())
            self.assertEqual(result.status, "unknown")
            self.assertEqual(result.meta["raw"]["reason"], "target_delivery_readback_required")
            self.assertNotIn("aggregate_kind", result.meta["raw"])
            self.assertEqual(result.meta["raw"]["typed_batch_results"][0]["input_index"], 0)
            self.assertEqual(
                [item["status"] for item in result.meta["raw"]["typed_batch_results"]],
                ["failed", "failed"],
            )
            self.assertTrue(all(
                item["receipt"]["receipt_kind"] == "DISPATCH_ACKNOWLEDGEMENT"
                and not item["receipt"]["authoritative_readback"]
                for item in result.meta["raw"]["typed_batch_results"]
            ))
            self.assertEqual(
                [row["observation"]["state"] for row in result.meta["raw"]["delivery_observations"]],
                ["unknown", "unknown"],
            )
            self.assertEqual(len(calls), 2)
            self.assertGreaterEqual(interpret.call_count, 2)
        finally:
            runtime.reset_collect_adapters()
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_partial_projection_is_not_completed(self):
        class _Adapter:
            def run(self, request):
                if request.query_terms[0] == "b1":
                    return CollectResult(
                        channel=request.channel,
                        status="failed",
                        provider_job_id="job-b1",
                        errors=[{"code": "x", "message": "bad"}],
                        meta={"terminal_readback": {
                            "kind": "terminal", "provider_job_id": "job-b1", "status": "failed",
                        }},
                    )
                return CollectResult(
                    channel=request.channel,
                    status="completed",
                    provider_job_id="job-b2",
                    inserted=4,
                    meta={"raw": {}, "terminal_readback": {
                        "kind": "terminal", "provider_job_id": "job-b2", "status": "completed",
                    }},
                )

        runtime.reset_collect_adapters()
        adapter = _Adapter()
        runtime.register_collect_skill("search.market", adapter)
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            class FixedDatetime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return datetime(2030, 1, 1, tzinfo=timezone.utc)

            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                with patch.object(runtime, "datetime", FixedDatetime):
                    result = runtime.run_collect(self._successor_request())
            self.assertEqual(result.status, "unknown")
            self.assertNotIn("aggregate_kind", result.meta["raw"])
            self.assertEqual(len(result.meta["raw"]["typed_batch_results"]), 2)
            self.assertEqual(result.meta["raw"]["delivery_observations"][0]["observation"]["state"], "unknown")
            self.assertEqual(result.meta["raw"]["delivery_observations"][1]["observation"]["state"], "failed")
        finally:
            runtime.reset_collect_adapters()
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_all_failed_projection_is_failed(self):
        class _Adapter:
            def run(self, request):
                return CollectResult(
                    channel=request.channel,
                    status="failed",
                    provider_job_id="job-failed",
                    errors=[{"code": "x", "message": "bad"}],
                    meta={"terminal_readback": {
                        "kind": "terminal", "provider_job_id": "job-failed", "status": "failed",
                    }},
                )

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
                    return CollectResult(channel=request.channel, status="failed", errors=[{"code": "x", "message": "bad"}], meta={"terminal_readback": {"kind": "terminal", "status": "failed"}})
                return CollectResult(
                    channel=request.channel,
                    status="completed",
                    inserted=4,
                    meta={"raw": {}, "terminal_readback": {"kind": "terminal", "readback": {"provider_job_id": "job-a", "terminal_status": "completed"}}},
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
            self.assertEqual(result.status, "unknown")
            self.assertIn("cancellation_receipt", result.meta["raw"])
            self.assertEqual(result.meta["raw"]["typed_batch_results"][0]["receipt"]["provider_job_id"], "job-a")
            self.assertFalse(result.meta["raw"]["typed_batch_results"][0]["receipt"]["authoritative_readback"])
        finally:
            runtime.reset_collect_adapters()
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_parallelism_remains_serial_without_capacity_and_write_scopes(self):
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
            self.assertEqual(result.meta["batch_parallelism_requested"], 2)
            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                result = runtime.run_collect(self._successor_request(options={"batch_parallelism": 2, "batch_independence_policy": "explicit"}))
            self.assertEqual(maximum, 1)
            self.assertEqual(result.meta["batch_parallelism"], 1)
            self.assertEqual(result.meta["batch_parallelism_requested"], 2)
        finally:
            runtime.reset_collect_adapters()
            runtime.reset_successor_collect_effect_gateway()

    def test_collect_delivery_uses_source_library_terminal_readback_and_job_identity(self):
        result = CollectResult(
            channel="source_library",
            status="completed",
            meta={"terminal_output": {"meta": {
                "provider_job_id": "job-1",
                "terminal_readback": {"kind": "terminal", "readback": {
                    "provider_job_id": "job-1", "terminal_status": "completed",
                }},
            }}},
        )
        self.assertEqual(runtime._collect_delivery_observation(result).provider_state, "delivered")
        self.assertEqual(runtime._collect_delivery_observation(result).state, "unknown")
        result.meta["terminal_output"]["meta"]["terminal_readback"]["readback"]["provider_job_id"] = "job-2"
        self.assertEqual(runtime._collect_delivery_observation(result).state, "unknown")

    def test_successor_waiting_provider_remains_unknown_before_c3_fold(self):
        class _Gateway:
            def run(self, request):
                return CollectResult(
                    channel=request.channel,
                    status="accepted",
                    provider_job_id=f"job-{request.query_terms[0]}",
                    provider_status="waiting",
                    meta={"terminal_readback": {"kind": "waiting", "attempt_ref": request.query_terms[0]}},
                )

        runtime.register_successor_collect_effect_gateway(_Gateway().run)
        try:
            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                result = runtime.run_collect(self._successor_request())
            self.assertEqual(result.status, "unknown")
            self.assertEqual(result.meta["raw"]["outcome"], "OutcomeUnknown")
            self.assertEqual(len(result.meta["raw"]["delivery_observations"]), 2)
            self.assertEqual(
                [row["observation"]["state"] for row in result.meta["raw"]["delivery_observations"]],
                ["waiting", "waiting"],
            )
        finally:
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_cancelled_provider_is_not_folded_as_failed(self):
        class _Gateway:
            def run(self, request):
                return CollectResult(
                    channel=request.channel,
                    status="cancelled",
                    provider_job_id=f"job-{request.query_terms[0]}",
                    provider_status="cancelled",
                    meta={"terminal_readback": {"kind": "terminal", "readback": {
                        "provider_job_id": f"job-{request.query_terms[0]}", "terminal_status": "cancelled",
                    }}},
                )

        runtime.register_successor_collect_effect_gateway(_Gateway().run)
        try:
            with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                result = runtime.run_collect(self._successor_request())
            self.assertEqual(result.status, "cancelled")
            self.assertEqual(result.meta["raw"]["outcome"], "Cancelled")
            self.assertEqual(
                [row["observation"]["state"] for row in result.meta["raw"]["delivery_observations"]],
                ["cancelled", "cancelled"],
            )
        finally:
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_mixed_terminal_and_waiting_or_cancelled_retains_effect_facts(self):
        for second_state in ("waiting", "cancelled"):
            with self.subTest(second_state=second_state):
                class _Gateway:
                    def run(self, request):
                        first = request.query_terms[0]
                        state = "completed" if first == "a1" else second_state
                        readback = (
                            {"kind": "waiting", "attempt_ref": first}
                            if state == "waiting" else
                            {"kind": "terminal", "readback": {
                                "provider_job_id": f"job-{first}", "terminal_status": state,
                            }}
                        )
                        return CollectResult(
                            channel=request.channel,
                            status="accepted" if state == "waiting" else state,
                            inserted=3 if first == "a1" else 1,
                            meta={"raw": {"links": [f"https://example/{first}"]}, "terminal_readback": readback},
                            provider_job_id=f"job-{first}",
                            provider_status=state,
                        )

                runtime.register_successor_collect_effect_gateway(_Gateway().run)
                try:
                    with patch.dict("os.environ", {"SUCCESSOR_RUNTIME_COLLECT": "on"}, clear=False):
                        result = runtime.run_collect(self._successor_request())
                    self.assertEqual(result.status, "unknown")
                    self.assertEqual(result.inserted, 4)
                    self.assertEqual(result.meta["raw"]["links"], ["https://example/a1", "https://example/b1"])
                    self.assertEqual(
                        [row["observation"]["provider_state"] for row in result.meta["raw"]["delivery_observations"]],
                        ["delivered", second_state],
                    )
                    self.assertEqual(
                        [row["observation"]["state"] for row in result.meta["raw"]["delivery_observations"]],
                        ["unknown", second_state],
                    )
                finally:
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
            for mode in ("on", "canary"):
                with self.subTest(mode=mode), patch.dict(
                    "os.environ", {"SUCCESSOR_RUNTIME_COLLECT": mode}, clear=True
                ):
                    result = runtime.run_collect(self._successor_request())
                    small = CollectRequest(channel="search.market", project_key="successor-test", query_terms=["one"], limit=1)
                    small_result = runtime.run_collect(small)
                self.assertEqual(result.status, "unknown")
                self.assertEqual(result.meta["raw"]["outcome"], "OutcomeUnknown")
                self.assertEqual(small_result.status, "unknown")
                self.assertEqual(calls, [])
        finally:
            runtime.reset_collect_adapters()


if __name__ == "__main__":
    unittest.main()
