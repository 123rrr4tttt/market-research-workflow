from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

try:
    from app.services.ingest.adapters.http_utils import request_html
    from app.services.ingest.retry_policy import (
        RETRY_CLASS_PERMANENT,
        RETRY_CLASS_TRANSIENT,
        RateGate,
        RateGateDecision,
        RequestScope,
        build_retry_observability,
        classify_retry_reason,
        combine_request_outcomes,
        decide_request_retry,
        parse_retry_after_seconds,
    )

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class IngestRetryPolicyUnitTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            message = f"ingest retry policy unit tests require backend dependencies: {_IMPORT_ERROR}"
            raise unittest.SkipTest(message)

    def test_classify_retry_reason_transient_and_permanent(self):
        fetch_reason, fetch_class = classify_retry_reason("fetch_failed")
        invalid_reason, invalid_class = classify_retry_reason("invalid_url")

        self.assertEqual(fetch_reason, "fetch_failed")
        self.assertEqual(fetch_class, RETRY_CLASS_TRANSIENT)
        self.assertEqual(invalid_reason, "invalid_url")
        self.assertEqual(invalid_class, RETRY_CLASS_PERMANENT)

    def test_build_retry_observability_aggregates_counts_by_reason_and_class(self):
        payload = {
            "reason_code": "fetch_failed",
            "rejection_breakdown": {
                "fetch_failed": 1,
                "invalid_url": 3,
            },
            "crawler_dispatch": {
                "attempt_count": 3,
            },
            "retry_events": [
                {"reason": "rate_limited", "count": 2},
            ],
        }

        out = build_retry_observability(payload)

        reason_counts = out.get("retry_count_by_reason") or {}
        class_counts = out.get("retry_count_by_class") or {}

        self.assertEqual(reason_counts.get("fetch_failed"), 1)
        self.assertEqual(reason_counts.get("crawler_dispatch_retry"), 2)
        self.assertEqual(reason_counts.get("rate_limited"), 2)
        self.assertNotIn("invalid_url", reason_counts)
        self.assertEqual(class_counts.get(RETRY_CLASS_TRANSIENT), 5)
        self.assertEqual(class_counts.get(RETRY_CLASS_PERMANENT), 0)
        self.assertTrue(bool(out.get("retryable")))

    def test_request_retry_decision_uses_existing_error_code_and_retry_after(self):
        scope = RequestScope(provider="search", account="acct-1", worker="worker-a")
        rate = decide_request_retry(
            reason_code="429",
            status_code=429,
            headers={"Retry-After": "7"},
            scope=scope,
            attempt=2,
        )

        self.assertTrue(rate.retryable)
        self.assertEqual(rate.retry_class, RETRY_CLASS_TRANSIENT)
        self.assertEqual(rate.error_code.value, "RATE_LIMITED")
        self.assertEqual(rate.delay_seconds, 7.0)
        self.assertEqual(rate.failure.family, "public_request")
        self.assertEqual(rate.failure.code, "RATE_LIMITED")
        self.assertEqual(
            rate.failure.context.get("reason_code"),
            "rate_limited",
        )
        self.assertEqual(rate.failure.context.get("provider"), "search")
        self.assertEqual(rate.failure.context.get("account"), "acct-1")
        self.assertEqual(rate.failure.context.get("worker"), "worker-a")
        self.assertEqual(rate.failure.context.get("retry_after_seconds"), 7.0)

        permanent = decide_request_retry(
            reason_code="http_status",
            status_code=404,
            scope=scope,
        )
        self.assertFalse(permanent.retryable)
        self.assertEqual(permanent.retry_class, RETRY_CLASS_PERMANENT)
        self.assertEqual(permanent.delay_seconds, 0.0)

    def test_request_outcome_distinguishes_partial_and_full_failure(self):
        scope = RequestScope(provider="search")
        failure = decide_request_retry(
            reason_code="rate_limited",
            status_code=429,
            scope=scope,
        ).failure

        partial = combine_request_outcomes(["one"], [failure])
        failed = combine_request_outcomes([], [failure])
        ok = combine_request_outcomes(["one"], [])

        self.assertEqual(partial.status, "partial")
        self.assertEqual(partial.values, ("one",))
        self.assertEqual(partial.failures, (failure,))
        self.assertEqual(failed.status, "failed")
        self.assertEqual(ok.status, "ok")

    def test_request_retry_decision_rejects_unassociated_values(self):
        decision = decide_request_retry(reason_code="rate_limited", scope=RequestScope(provider="search"))
        for changes in (
            {"retry_class": RETRY_CLASS_PERMANENT},
            {"delay_seconds": float("nan")},
            {"reason_code": "fetch_failed"},
            {"scope": RequestScope(provider="other")},
            {"retry_after_seconds": 3.0},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(decision, **changes)

    def test_rate_gate_decision_rejects_inconsistent_acquisition(self):
        scope = RequestScope(provider="search")
        for acquired, waited, retry_after in (
            (True, 0.0, 1.0),
            (False, 0.0, None),
            (False, 1.0, 2.0),
            (True, float("inf"), None),
            (False, 0.0, -1.0),
        ):
            with self.subTest(acquired=acquired, waited=waited, retry_after=retry_after), self.assertRaises(ValueError):
                RateGateDecision(acquired, scope, waited, retry_after)

    def test_request_scope_rejects_blank_provider(self):
        with self.assertRaisesRegex(ValueError, "provider is required"):
            RequestScope(provider="   ")

    def test_request_scope_rejects_non_string_identity_fields(self):
        scope = RequestScope(provider="search")
        for name in ("provider", "account", "worker"):
            with self.subTest(field=name), self.assertRaises(ValueError):
                replace(scope, **{name: 1})

    def test_combine_request_outcomes_rejects_empty_outcome(self):
        with self.assertRaisesRegex(ValueError, "at least one value or failure"):
            combine_request_outcomes([], [])

    def test_rate_gate_rejects_invalid_numeric_intervals(self):
        with self.assertRaisesRegex(ValueError, "rate_limit_interval_seconds"):
            RateGate(
                rate_limit_interval_seconds=0.0,
                backoff_base_seconds=1.0,
                backoff_max_seconds=2.0,
            )
        with self.assertRaisesRegex(ValueError, "backoff_base_seconds"):
            RateGate(
                rate_limit_interval_seconds=1.0,
                backoff_base_seconds=0.0,
                backoff_max_seconds=2.0,
            )
        with self.assertRaisesRegex(ValueError, "backoff_max_seconds"):
            RateGate(
                rate_limit_interval_seconds=1.0,
                backoff_base_seconds=2.0,
                backoff_max_seconds=1.0,
            )

    def test_rate_gate_rejects_non_finite_intervals(self):
        for field in ("rate_limit_interval_seconds", "backoff_base_seconds", "backoff_max_seconds"):
            for value in (float("nan"), float("inf"), -float("inf")):
                parameters = {
                    "rate_limit_interval_seconds": 1.0,
                    "backoff_base_seconds": 1.0,
                    "backoff_max_seconds": 2.0,
                }
                parameters[field] = value
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, field):
                    RateGate(**parameters)

    def test_retry_after_rejects_non_finite_seconds(self):
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value):
                self.assertIsNone(parse_retry_after_seconds(value))

    def test_retry_observability_ignores_malformed_counts(self):
        observed = build_retry_observability({
            "retry_events": [{"reason": "rate_limited", "count": float("inf")}],
            "crawler_dispatch": {"attempt_count": "invalid"},
        })
        self.assertEqual(observed["retry_count_by_reason"], {})
        self.assertFalse(observed["retryable"])

    def test_rate_gate_has_process_guarantee_and_separates_declared_workers(self):
        now = [10.0]
        sleeps: list[float] = []

        def clock() -> float:
            return now[0]

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        gate = RateGate(
            rate_limit_interval_seconds=0.5,
            backoff_base_seconds=2.0,
            backoff_max_seconds=8.0,
            clock=clock,
            sleeper=sleep,
        )
        shared_scope = RequestScope(provider="search", account="acct", worker="a")
        first = gate.acquire(shared_scope)
        second = gate.acquire(shared_scope)
        separate_worker = gate.acquire(
            RequestScope(provider="search", account="acct", worker="b"),
        )

        self.assertTrue(first.acquired)
        self.assertTrue(second.acquired)
        self.assertTrue(separate_worker.acquired)
        self.assertEqual(first.waited_seconds, 0.0)
        self.assertEqual(second.waited_seconds, 0.5)
        self.assertEqual(separate_worker.waited_seconds, 0.0)
        self.assertEqual(sleeps, [0.5])
        self.assertEqual(gate.guarantee, "process")

        gate.record_throttle(shared_scope, retry_after_seconds=7.0)
        denied = gate.acquire(shared_scope)
        self.assertFalse(denied.acquired)
        self.assertEqual(denied.retry_after_seconds, 7.0)
        self.assertEqual(denied.guarantee, "process")

    def test_request_html_preserves_429_retry_after_and_failure_association(self):
        class FakeResponse:
            status_code = 429
            text = "slow down"
            headers = {"Retry-After": "7"}

            def raise_for_status(self) -> None:
                return None

        class FakeSession:
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.headers: dict[str, str] = {}
                self.cookies: dict[str, str] = {}
                self.get_kwargs: dict[object, object] = {}

            def get(self, url: str, **kwargs: object) -> FakeResponse:
                self.calls.append(url)
                self.get_kwargs = dict(kwargs)
                return FakeResponse()

            def close(self) -> None:
                return None

        session = FakeSession()
        sleeps: list[float] = []
        outcome = request_html(
            "https://example.test/search",
            scope=RequestScope(provider="search", account="acct", worker="a"),
            retries=2,
            backoff_seconds=1.0,
            cookies={"session": "public"},
            sleeper=sleeps.append,
            client_factory=lambda: session,
        )

        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(len(session.calls), 2)
        self.assertTrue(session.headers["User-Agent"].startswith("Mozilla/5.0"))
        self.assertEqual(session.cookies, {"session": "public"})
        self.assertTrue(session.get_kwargs["allow_redirects"])
        self.assertEqual(sleeps, [7.0])
        self.assertEqual(len(outcome.failures), 2)
        self.assertEqual(len(outcome.decisions), 2)
        self.assertEqual(outcome.decisions[-1].retry_after_seconds, 7.0)
        self.assertEqual(outcome.failures[-1].code, "RATE_LIMITED")

    def test_request_html_transport_exhaustion_returns_failure_without_terminal_sleep(self):
        class FakeSession:
            def __init__(self) -> None:
                self.calls = 0
                self.headers: dict[str, str] = {}
                self.cookies: dict[str, str] = {}

            def get(self, url: str, **kwargs: object) -> None:
                self.calls += 1
                raise requests.ConnectionError

            def close(self) -> None:
                return None

        session = FakeSession()
        sleeps: list[float] = []
        outcome = request_html(
            "https://example.test/search",
            scope=RequestScope(provider="search", account="acct", worker="a"),
            retries=2,
            backoff_seconds=1.0,
            sleeper=sleeps.append,
            client_factory=lambda: session,
        )

        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(session.calls, 2)
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(len(outcome.failures), 2)
        self.assertEqual(outcome.failures[-1].code, "UPSTREAM_ERROR")
        self.assertIsInstance(outcome.last_exception, requests.ConnectionError)


if __name__ == "__main__":
    unittest.main()
