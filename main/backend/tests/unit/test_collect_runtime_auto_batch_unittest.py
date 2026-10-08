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

    def test_deployment_flags_are_not_dispatch_boundaries(self):
        calls = []

        def gateway(request: CollectRequest) -> CollectResult:
            calls.append(tuple(request.query_terms))
            first = request.query_terms[0]
            return CollectResult(
                channel=request.channel,
                status="completed",
                inserted=len(request.query_terms),
                provider_job_id=f"job-{first}",
                provider_type="fixture",
                provider_status="completed",
                attempt_count=1,
                meta={"raw": {"links": [f"https://example/{first}"]}, "terminal_readback": {
                    "kind": "terminal",
                    "readback": {"provider_job_id": f"job-{first}", "terminal_status": "completed"},
                }},
            )
        runtime.register_successor_collect_effect_gateway(gateway)
        request = self._successor_request()
        try:
            with patch.dict(
                "os.environ",
                {
                    "SUCCESSOR_RUNTIME_COLLECT": "off",
                    "INGEST_WORKFLOW_ADAPTER": "workflow",
                },
                clear=True,
            ):
                with_flags = runtime.run_collect(request)
            self.assertFalse(hasattr(runtime, "_resolve_successor_collect_mode"))
            self.assertFalse(hasattr(runtime, "_successor_switch_configured"))
            self.assertFalse(hasattr(runtime, "_resolve_workflow_mode"))
        finally:
            runtime.reset_successor_collect_effect_gateway()
        self.assertEqual(with_flags.status, "unknown")
        self.assertEqual(with_flags.meta["raw"]["reason"], "target_delivery_readback_required")
        self.assertEqual(calls, [("a1", "a2", "a3", "a4"), ("b1", "b2", "b3", "b4")])
        self.assertEqual(with_flags.inserted, 8)
        self.assertEqual(
            [item["result_status"] for item in with_flags.meta["raw"]["delivery_observations"]],
            ["succeeded", "succeeded"],
        )

    def test_all_channels_use_the_same_effect_gateway_signature(self):
        observed: list[str] = []

        def gateway(request: CollectRequest) -> CollectResult:
            observed.append(request.channel)
            return CollectResult(channel=request.channel, status="completed")
        runtime.register_successor_collect_effect_gateway(gateway)
        requests = [
            CollectRequest(channel="search.market", query_terms=["one"], project_key="project"),
            CollectRequest(channel="search.policy", query_terms=["one"], project_key="project"),
            CollectRequest(flow="source_collect", channel="source_library", item_key="item"),
            CollectRequest(channel="url_pool", urls=["https://example.test"]),
            CollectRequest(channel="crawler.scrapy", options={"project": "project", "spider": "spider"}),
        ]
        try:
            results = [runtime.run_collect(request) for request in requests]
        finally:
            runtime.reset_successor_collect_effect_gateway()
        self.assertEqual(observed, [
            "search.market", "search.policy", "source_library", "url_pool", "crawler.scrapy",
        ])
        self.assertEqual([result.status for result in results], ["completed"] * 5)

    def test_missing_gateway_is_unknown_and_registry_has_no_product_dispatch(self):
        runtime.reset_successor_collect_effect_gateway()
        try:
            batched = runtime.run_collect(self._successor_request())
            single = runtime.run_collect(CollectRequest(channel="source_library", item_key="item"))
        finally:
            runtime.reset_successor_collect_effect_gateway()
        self.assertFalse(hasattr(runtime, "_SKILL_REGISTRY"))
        self.assertEqual(batched.status, "unknown")
        self.assertEqual(batched.errors[0]["code"], "successor_effect_gateway_unavailable")
        self.assertEqual(single.status, "unknown")
        self.assertEqual(single.errors[0]["code"], "successor_effect_gateway_unavailable")

    def test_policy_batch_uses_composed_elements(self):
        calls: list[tuple[str, tuple[str, ...]]] = []

        def gateway(request: CollectRequest) -> CollectResult:
            calls.append((request.channel, tuple(request.query_terms)))
            return CollectResult(
                channel=request.channel,
                status="failed",
                provider_job_id=f"job-{request.query_terms[0]}",
                errors=[{"code": "x", "message": "bad"}],
                meta={"terminal_readback": {
                    "kind": "terminal",
                    "provider_job_id": f"job-{request.query_terms[0]}",
                    "status": "failed",
                }},
            )

        runtime.register_successor_collect_effect_gateway(gateway)
        try:
            result = runtime.run_collect(self._successor_request(channel="search.policy"))
        finally:
            runtime.reset_successor_collect_effect_gateway()

        self.assertEqual(calls, [
            ("search.policy", ("a1", "a2", "a3", "a4")),
            ("search.policy", ("b1", "b2", "b3", "b4")),
        ])
        self.assertEqual(result.status, "failed")
        self.assertNotIn("aggregate_kind", result.meta["raw"])
        self.assertEqual(result.meta["raw"]["batches_total"], 2)

    def _successor_request(self, **kwargs):
        options = kwargs.pop("options", {})
        return CollectRequest(
            channel=kwargs.pop("channel", "search.market"),
            project_key="successor-test",
            query_terms=["a1", "a2", "a3", "a4", "b1", "b2", "b3", "b4"],
            limit=80,
            options=options,
            **kwargs,
        )

    def test_successor_route_orders_sync_outcomes(self):
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
        adapter = _Adapter()
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            result = runtime.run_collect(self._successor_request())
            self.assertEqual(result.status, "unknown")
            self.assertEqual(result.meta["raw"]["reason"], "target_delivery_readback_required")
            self.assertNotIn("aggregate_kind", result.meta["raw"])
            observations = result.meta["raw"]["delivery_observations"]
            self.assertEqual(observations[0]["input_index"], 0)
            self.assertEqual(
                [item["result_status"] for item in observations],
                ["succeeded", "succeeded"],
            )
            self.assertTrue(all(
                item["receipt"]["receipt_kind"] == "DISPATCH_ACKNOWLEDGEMENT"
                and not item["receipt"]["authoritative_readback"]
                for item in observations
            ))
            self.assertEqual(
                [row["observation"]["state"] for row in result.meta["raw"]["delivery_observations"]],
                ["unknown", "unknown"],
            )
            self.assertEqual(len(calls), 2)
        finally:
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
        adapter = _Adapter()
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            class FixedDatetime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return datetime(2030, 1, 1, tzinfo=timezone.utc)

            with patch.object(runtime, "datetime", FixedDatetime):
                result = runtime.run_collect(self._successor_request())
            self.assertEqual(result.status, "unknown")
            self.assertNotIn("aggregate_kind", result.meta["raw"])
            self.assertEqual(len(result.meta["raw"]["delivery_observations"]), 2)
            observations = result.meta["raw"]["delivery_observations"]
            self.assertEqual(observations[0]["observation"]["state"], "unknown")
            self.assertEqual(observations[1]["observation"]["state"], "failed")
            self.assertEqual(result.inserted, 4)
            self.assertEqual([row["counts"]["inserted"] for row in observations], [4, 0])
            self.assertEqual(
                [row["receipt"]["provider_job_id"] for row in observations],
                ["job-b2", "job-b1"],
            )
        finally:
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
        adapter = _Adapter()
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            result = runtime.run_collect(self._successor_request())
            self.assertEqual(result.status, "failed")
            self.assertNotIn("aggregate_kind", result.meta["raw"])
        finally:
            runtime.reset_successor_collect_effect_gateway()

    def test_terminal_failed_readback_controls_final_status_when_local_return_completed(self):
        def gateway(request: CollectRequest) -> CollectResult:
            job_id = f"job-{request.query_terms[0]}"
            provider_errors = (
                [{"code": "element_rejected", "message": "provider rejected second batch"}]
                if request.query_terms[0] == "b1"
                else []
            )
            return CollectResult(
                channel=request.channel,
                status="failed" if provider_errors else "completed",
                provider_job_id=job_id,
                errors=provider_errors,
                meta={"terminal_readback": {
                    "kind": "terminal",
                    "provider_job_id": job_id,
                    "status": "failed",
                }},
            )

        runtime.register_successor_collect_effect_gateway(gateway)
        try:
            result = runtime.run_collect(self._successor_request())
        finally:
            runtime.reset_successor_collect_effect_gateway()

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            [row["result_status"] for row in result.meta["raw"]["delivery_observations"]],
            ["succeeded", "failed"],
        )
        self.assertEqual(
            [item["result"]["status"] for item in result.meta["raw"]["batch_results"]],
            ["failed", "failed"],
        )
        self.assertEqual(
            [error["code"] for error in result.errors],
            ["runner_unavailable", "element_rejected"],
        )
        self.assertEqual(
            [error["message"] for error in result.errors],
            [
                "target delivery readback is required for successor completion",
                "provider rejected second batch",
            ],
        )
        self.assertEqual(
            [item["result"]["errors"] for item in result.meta["raw"]["batch_results"]],
            [
                [{
                    "code": "runner_unavailable",
                    "message": "target delivery readback is required for successor completion",
                    "query_terms": ["a1", "a2", "a3", "a4"],
                }],
                [{
                    "code": "element_rejected",
                    "message": "provider rejected second batch",
                    "query_terms": ["b1", "b2", "b3", "b4"],
                }],
            ],
        )
        self.assertEqual(
            [row["errors"] for row in result.meta["raw"]["delivery_observations"]],
            [[], [{
                "code": "element_rejected",
                "message": "provider rejected second batch",
                "query_terms": ["b1", "b2", "b3", "b4"],
            }]],
        )

    def test_successor_fail_fast_projection_is_cancelled_and_keeps_receipts(self):
        calls: list[tuple[str, ...]] = []

        class _Adapter:
            def run(self, request):
                calls.append(tuple(request.query_terms))
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
        adapter = _Adapter()
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            result = runtime.run_collect(self._successor_request(options={"batch_fail_fast": True}))
            self.assertEqual(result.status, "unknown")
            self.assertIn("cancellation_receipt", result.meta["raw"])
            receipt = result.meta["raw"]["delivery_observations"][0]["receipt"]
            self.assertEqual(receipt["provider_job_id"], "job-a")
            self.assertFalse(receipt["authoritative_readback"])
            self.assertEqual(calls, [("a1", "a2", "a3", "a4")])
            self.assertEqual(
                [row["execution_state"] for row in result.meta["raw"]["delivery_observations"]],
                ["attempted", "not_attempted"],
            )
        finally:
            runtime.reset_successor_collect_effect_gateway()

    def test_successor_fail_fast_stops_after_first_failed_element(self):
        calls: list[tuple[str, ...]] = []

        def gateway(request: CollectRequest) -> CollectResult:
            calls.append(tuple(request.query_terms))
            return CollectResult(
                channel=request.channel,
                status="failed",
                provider_job_id="job-a1",
                errors=[{"code": "x", "message": "failed"}],
                meta={"terminal_readback": {
                    "kind": "terminal",
                    "provider_job_id": "job-a1",
                    "status": "failed",
                }},
            )

        runtime.register_successor_collect_effect_gateway(gateway)
        try:
            result = runtime.run_collect(
                self._successor_request(options={"batch_fail_fast": True})
            )
        finally:
            runtime.reset_successor_collect_effect_gateway()

        self.assertEqual(calls, [("a1", "a2", "a3", "a4")])
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(len(result.meta["raw"]["batch_results"]), 1)
        self.assertEqual(
            [row["execution_state"] for row in result.meta["raw"]["delivery_observations"]],
            ["attempted", "not_attempted"],
        )

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
        adapter = _Adapter()
        runtime.register_successor_collect_effect_gateway(adapter.run)
        try:
            result = runtime.run_collect(self._successor_request(options={"batch_parallelism": 2}))
            self.assertEqual(maximum, 1)
            self.assertEqual(result.meta["batch_parallelism"], 1)
            self.assertEqual(result.meta["batch_parallelism_requested"], 2)
            result = runtime.run_collect(self._successor_request(options={"batch_parallelism": 2, "batch_independence_policy": "explicit"}))
            self.assertEqual(maximum, 1)
            self.assertEqual(result.meta["batch_parallelism"], 1)
            self.assertEqual(result.meta["batch_parallelism_requested"], 2)
        finally:
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

    def test_successor_waiting_provider_remains_unknown_before_fold(self):
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

    def test_waiting_delivery_observation_survives_count_rejection(self):
        def gateway(request: CollectRequest) -> CollectResult:
            return CollectResult(
                channel=request.channel,
                status="accepted",
                inserted=-1,
                provider_job_id=f"job-{request.query_terms[0]}",
                provider_status="waiting",
                meta={"terminal_readback": {"kind": "waiting"}},
            )

        runtime.register_successor_collect_effect_gateway(gateway)
        try:
            result = runtime.run_collect(self._successor_request())
        finally:
            runtime.reset_successor_collect_effect_gateway()

        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.inserted, -2)
        rows = result.meta["raw"]["delivery_observations"]
        self.assertEqual([row["counts"]["inserted"] for row in rows], [-1, -1])
        self.assertEqual([row["observation"]["state"] for row in rows], ["waiting", "waiting"])
        self.assertEqual([row["execution_state"] for row in rows], ["attempted", "attempted"])
        self.assertEqual(
            [outcome["result_status"] for outcome in result.meta["raw"]["delivery_observations"]],
            ["failed", "failed"],
        )

    def test_receipt_rejection_preserves_waiting_job_and_counts(self):
        def gateway(request: CollectRequest) -> CollectResult:
            return CollectResult(
                channel=request.channel,
                status="accepted",
                inserted=3,
                provider_job_id="job-x",
                provider_status="waiting",
                attempt_count=-1,
                meta={
                    "raw": {"links": ["https://example/observed"]},
                    "terminal_readback": {"kind": "waiting"},
                },
            )

        runtime.register_successor_collect_effect_gateway(gateway)
        try:
            result = runtime.run_collect(self._successor_request())
        finally:
            runtime.reset_successor_collect_effect_gateway()

        self.assertEqual(result.status, "unknown")
        self.assertEqual(result.inserted, 6)
        rows = result.meta["raw"]["delivery_observations"]
        self.assertEqual([row["counts"]["inserted"] for row in rows], [3, 3])
        self.assertEqual([row["observation"]["state"] for row in rows], ["waiting", "waiting"])
        self.assertEqual([row["observation"]["provider_job_id"] for row in rows], ["job-x", "job-x"])
        self.assertEqual(result.meta["raw"]["links"], ["https://example/observed"])
        self.assertEqual(
            [row["links"] for row in rows],
            [["https://example/observed"], ["https://example/observed"]],
        )
        self.assertTrue(all("receipt" not in row for row in rows))

    def test_non_iterable_links_remain_an_element_execution_failure(self):
        def gateway(request: CollectRequest) -> CollectResult:
            return CollectResult(channel=request.channel, meta={"raw": {"links": 1}})

        runtime.register_successor_collect_effect_gateway(gateway)
        try:
            result = runtime.run_collect(self._successor_request())
        finally:
            runtime.reset_successor_collect_effect_gateway()

        self.assertEqual(result.status, "failed")
        self.assertEqual(len(result.errors), 2)
        self.assertEqual([error["exception_type"] for error in result.errors], ["TypeError", "TypeError"])
        self.assertEqual(
            [error["message"] for error in result.errors],
            ["'int' object is not iterable", "'int' object is not iterable"],
        )

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

if __name__ == "__main__":
    unittest.main()
