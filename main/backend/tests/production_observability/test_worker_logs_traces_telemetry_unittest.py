from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.production_observability.worker_telemetry import (  # noqa: E402
    WORKER_TELEMETRY_CONTRACT_VERSION,
    build_worker_telemetry_identity,
    publish_worker_telemetry,
    read_worker_telemetry_snapshot,
)


class _RedisFake:
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def xadd(self, stream: str, mapping: dict[str, str], **_kwargs: object) -> str:
        self.rows.append(dict(mapping))
        return str(len(self.rows))

    def xrange(
        self,
        stream: str,
        *,
        min: str = "-",
        max: str = "+",
        count: int,
    ) -> list[tuple[str, dict[str, str]]]:
        return [(str(index), row) for index, row in enumerate(self.rows[:count])]


class WorkerTelemetryTestCase(unittest.TestCase):
    def test_identity_uses_allowlist_and_nested_runtime_readback(self) -> None:
        request = SimpleNamespace(
            id="celery-task-1",
            hostname="celery@stage5-worker",
            delivery_info={"routing_key": "celery"},
        )
        task = SimpleNamespace(name="app.tasks.task_sync_aggregator", request=request)
        identity = build_worker_telemetry_identity(
            args=(),
            kwargs={
                "request_id": "request-stage5",
                "trace_id": "trace-stage5",
                "project_key": "stage5_observability_20260913",
                "candidate_id": "governance:aggregator-sync",
                "secret": "must-not-be-copied",
                "runtime_readback": {"run_id": "run-stage5"},
            },
            task=task,
        )

        self.assertEqual(identity["request_id"], "request-stage5")
        self.assertEqual(identity["run_id"], "run-stage5")
        self.assertEqual(identity["candidate_id"], "governance:aggregator-sync")
        self.assertEqual(identity["worker_name"], "celery@stage5-worker")
        self.assertNotIn("secret", identity)

    def test_publish_read_and_unknown_boundary(self) -> None:
        client = _RedisFake()
        base = {
            "request_id": "request-stage5",
            "trace_id": "trace-stage5",
            "run_id": "run-stage5",
            "project_key": "stage5_observability_20260913",
            "candidate_id": "governance:aggregator-sync",
            "task_id": "celery-task-1",
            "task_name": "app.tasks.task_sync_aggregator",
            "worker_name": "celery@stage5-worker",
            "queue": "celery",
        }
        for record_type in ("worker_event", "structured_log", "trace"):
            row = {
                **base,
                "contract_version": WORKER_TELEMETRY_CONTRACT_VERSION,
                "record_type": record_type,
                "event": "worker_started" if record_type == "structured_log" else "started",
                "status": "running",
                "observed_at": "2026-09-13T00:00:00+00:00",
            }
            self.assertTrue(publish_worker_telemetry([row], client=client))

        snapshot = read_worker_telemetry_snapshot(client)
        payload = snapshot.to_dict()
        self.assertEqual(snapshot.read_status, "ok")
        self.assertEqual(payload["status"], "observed")
        self.assertEqual(payload["structured_logs_status"], "observed")
        self.assertEqual(payload["traces_status"], "observed")
        self.assertEqual(payload["record_counts"], {"worker_event": 1, "structured_log": 1, "trace": 1})
        self.assertEqual(payload["correlatable_request_ids"], ["request-stage5"])

        empty = read_worker_telemetry_snapshot(_RedisFake()).to_dict()
        self.assertEqual(empty["read_status"], "ok")
        self.assertEqual(empty["status"], "unknown")
        self.assertEqual(empty["structured_logs_status"], "not_observed")
        self.assertEqual(empty["traces_status"], "not_observed")
        self.assertEqual(empty["correlatable_request_ids"], [])


if __name__ == "__main__":
    unittest.main()
