from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit

try:
    from app.services.agent_batch import executor_health
except Exception as exc:  # pragma: no cover - dependency/import guard
    executor_health = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class _FakeInspect:
    def __init__(self, ping_result=None, ping_error: Exception | None = None):
        self._ping_result = ping_result
        self._ping_error = ping_error

    def ping(self):
        if self._ping_error is not None:
            raise self._ping_error
        return self._ping_result


class _FakeControl:
    def __init__(self, inspect_result=None, inspect_error: Exception | None = None):
        self._inspect_result = inspect_result
        self._inspect_error = inspect_error
        self.inspect_calls: list[float] = []

    def inspect(self, *, timeout: float):
        self.inspect_calls.append(timeout)
        if self._inspect_error is not None:
            raise self._inspect_error
        return self._inspect_result


class _FakeConf:
    def __init__(self, broker_url):
        self.broker_url = broker_url


class _FakeCeleryApp:
    def __init__(self, *, broker_url: str, inspect_result=None, inspect_error: Exception | None = None):
        self.conf = _FakeConf(broker_url)
        self.control = _FakeControl(inspect_result=inspect_result, inspect_error=inspect_error)


class AgentBatchExecutorHealthUnitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"executor health unit tests require backend dependencies: {_IMPORT_ERROR}")

    def test_inspect_executor_health_success_worker_online_and_masked_url(self):
        app = _FakeCeleryApp(
            broker_url="redis://user:secret@localhost:6379/0",
            inspect_result=_FakeInspect(ping_result={"celery@w2": {"ok": "pong"}, "celery@w1": {"ok": "pong"}}),
        )

        out = executor_health.inspect_executor_health(app_instance=app, inspect_timeout=2.5)

        self.assertTrue(out["worker_online"])
        self.assertEqual(out["workers"], ["celery@w1", "celery@w2"])
        self.assertEqual(out["broker_url_masked"], "redis://user:***@localhost:6379/0")
        self.assertIn("timestamp", out)
        self.assertEqual(out["diagnostics"]["inspect_timeout_seconds"], 2.5)
        self.assertEqual(out["diagnostics"]["ping_response_type"], "dict")
        self.assertEqual(out["diagnostics"]["worker_count"], 2)
        self.assertEqual(app.control.inspect_calls, [2.5])

    def test_inspect_executor_health_no_workers_when_ping_none(self):
        app = _FakeCeleryApp(
            broker_url="redis://localhost:6379/1",
            inspect_result=_FakeInspect(ping_result=None),
        )

        out = executor_health.inspect_executor_health(app_instance=app)

        self.assertFalse(out["worker_online"])
        self.assertEqual(out["workers"], [])
        self.assertEqual(out["broker_url_masked"], "redis://localhost:6379/1")
        self.assertEqual(out["diagnostics"]["ping_response_type"], "none")
        self.assertEqual(out["diagnostics"]["worker_count"], 0)
        self.assertTrue(out["diagnostics"]["inspect_ok"])

    def test_inspect_executor_health_handles_inspect_error_without_raising(self):
        app = _FakeCeleryApp(
            broker_url="redis://u:p@127.0.0.1:6379/0",
            inspect_error=TimeoutError("inspect timed out"),
        )

        out = executor_health.inspect_executor_health(app_instance=app, inspect_timeout=0)

        self.assertFalse(out["worker_online"])
        self.assertEqual(out["workers"], [])
        self.assertEqual(out["broker_url_masked"], "redis://u:***@127.0.0.1:6379/0")
        self.assertFalse(out["diagnostics"]["inspect_ok"])
        self.assertIn("TimeoutError", out["diagnostics"]["error"])
        self.assertEqual(out["diagnostics"]["inspect_timeout_seconds"], 1.0)
        self.assertEqual(out["diagnostics"]["ping_response_type"], "none")

    def test_inspect_executor_health_handles_ping_error_without_raising(self):
        app = _FakeCeleryApp(
            broker_url="redis://user:pass@localhost:6379/0",
            inspect_result=_FakeInspect(ping_error=RuntimeError("ping failure")),
        )

        out = executor_health.inspect_executor_health(app_instance=app)

        self.assertFalse(out["worker_online"])
        self.assertEqual(out["workers"], [])
        self.assertFalse(out["diagnostics"]["inspect_ok"])
        self.assertIn("RuntimeError", out["diagnostics"]["error"])
        self.assertEqual(out["diagnostics"]["worker_count"], 0)

    def test_inspect_executor_health_uses_module_celery_app_when_missing_argument(self):
        fake_app = _FakeCeleryApp(
            broker_url="redis://user:pass@localhost:6379/0?token=abc",
            inspect_result=_FakeInspect(ping_result={"celery@one": {"ok": "pong"}}),
        )
        with patch.object(executor_health, "celery_app", fake_app):
            out = executor_health.inspect_executor_health()

        self.assertTrue(out["worker_online"])
        self.assertEqual(out["workers"], ["celery@one"])
        self.assertEqual(out["broker_url_masked"], "redis://user:***@localhost:6379/0?token=%2A%2A%2A")
