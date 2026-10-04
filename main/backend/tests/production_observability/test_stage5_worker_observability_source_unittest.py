from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from prometheus_client import REGISTRY, generate_latest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.celery_app import celery_app  # noqa: E402
from app.production_observability import worker_telemetry  # noqa: E402
from app.production_observability.worker import (  # noqa: E402
    WORKER_TASK_LATENCY_METRIC_NAME,
    WORKER_TASKS_METRIC_NAME,
    worker_trace_snapshot,
)
from app.services.observability_tasks import (  # noqa: E402
    WORKER_OBSERVATION_FALLBACK_WORKER_NAME,
    WORKER_OBSERVATION_LINE_KEY,
    WORKER_OBSERVATION_TASK_NAME,
    task_worker_observation_probe,
)


class WorkerObservationSourceTestCase(unittest.TestCase):
    def test_eager_celery_chain_exports_metrics_log_and_trace(self) -> None:
        task_id = "worker-observation-task-test"
        trace_id = "worker-observation-trace-test"
        kwargs = {
            "request_id": "worker-observation-request-test",
            "run_id": "worker-observation-run-test",
            "trace_id": trace_id,
            "project_key": "tenant:worker-observation-test",
            "candidate_review_key": "review:worker-observation-candidate",
            "candidate_id": "candidate:worker-observation-candidate",
            "queue": "worker.observation",
            "line_key": WORKER_OBSERVATION_LINE_KEY,
        }
        records: list[str] = []
        redis_records: list[tuple[str, dict[str, str]]] = []

        class FakeRedisTransport:
            def xadd(self, stream: str, fields: dict[str, str], **_kwargs: object) -> str:
                redis_records.append((stream, dict(fields)))
                return f"{len(redis_records):016x}"

        class CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(self.format(record))

        handler = CaptureHandler()
        logger = logging.getLogger("app.production_observability.worker")
        old_logger_level = logger.level
        old_config = {
            key: celery_app.conf[key] for key in ("task_always_eager", "task_eager_propagates", "result_backend")
        }
        celery_app.conf.update(
            task_always_eager=True,
            task_eager_propagates=True,
            result_backend="cache+memory://",
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        with patch.object(worker_telemetry, "_redis_client", return_value=FakeRedisTransport()):
            try:
                eager_result = task_worker_observation_probe.apply(
                    kwargs=kwargs,
                    task_id=task_id,
                )
                result = eager_result.get()
            finally:
                logger.removeHandler(handler)
                logger.setLevel(old_logger_level)
                celery_app.conf.update(old_config)

        self.assertTrue(eager_result.successful())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["runtime_readback"]["task_id"], task_id)
        self.assertEqual(result["runtime_readback"]["trace_id"], trace_id)
        self.assertEqual(result["runtime_readback"]["line_key"], WORKER_OBSERVATION_LINE_KEY)
        self.assertEqual(
            result["candidate_identity"]["candidate_review_key"],
            kwargs["candidate_review_key"],
        )
        self.assertEqual(sum(result["effect_boundary"].values()), 0)

        traces = worker_trace_snapshot(trace_id)
        self.assertEqual([item["event"] for item in traces], ["worker_task_started", "worker_task_finished"])
        self.assertEqual(result["runtime_readback"]["worker_name"], traces[0]["worker_name"])
        self.assertTrue(all(item["candidate_identity_redacted"] is True for item in traces))
        self.assertGreaterEqual(len(records), 2)
        self.assertTrue(any("worker_task_started" in item for item in records))
        self.assertTrue(any("worker_task_finished" in item for item in records))
        self.assertTrue(any('"record_type":"structured_log"' in item for item in records))
        self.assertTrue(any('"record_type":"trace"' in item for item in records))
        self.assertTrue(all(trace_id in item for item in records))
        self.assertEqual(len(redis_records), 6)
        self.assertTrue(all(stream == worker_telemetry.WORKER_TELEMETRY_STREAM for stream, _ in redis_records))
        self.assertEqual(
            {fields["record_type"] for _, fields in redis_records},
            {"worker_event", "structured_log", "trace"},
        )

        task_labels = {
            "task_name": task_worker_observation_probe.name,
            "worker_name": traces[0]["worker_name"],
            "queue": kwargs["queue"],
            "project_key": kwargs["project_key"],
            "line_key": WORKER_OBSERVATION_LINE_KEY,
        }
        self.assertEqual(task_worker_observation_probe.name, WORKER_OBSERVATION_TASK_NAME)
        count = REGISTRY.get_sample_value(WORKER_TASKS_METRIC_NAME, {**task_labels, "status": "succeeded"})
        histogram_count = REGISTRY.get_sample_value(
            f"{WORKER_TASK_LATENCY_METRIC_NAME}_count",
            task_labels,
        )
        self.assertIsNotNone(count)
        self.assertGreaterEqual(float(count or 0), 1.0)
        self.assertIsNotNone(histogram_count)
        self.assertGreaterEqual(float(histogram_count or 0), 1.0)
        metrics_text = generate_latest().decode("utf-8")
        self.assertIn(f"# HELP {WORKER_TASKS_METRIC_NAME}", metrics_text)
        self.assertIn(f"# TYPE {WORKER_TASK_LATENCY_METRIC_NAME} histogram", metrics_text)

    def test_task_registration_and_runtime_defaults_use_worker_observation_identity(self) -> None:
        self.assertEqual(celery_app.tasks[WORKER_OBSERVATION_TASK_NAME].name, WORKER_OBSERVATION_TASK_NAME)
        self.assertEqual(task_worker_observation_probe.name, WORKER_OBSERVATION_TASK_NAME)
        self.assertNotIn("task_stage5_worker_observability_probe", celery_app.tasks)

        task_worker_observation_probe.push_request(
            id=None,
            hostname=None,
            delivery_info={},
        )
        try:
            result = task_worker_observation_probe.run(
                request_id="worker-observation-default-request",
                run_id="worker-observation-default-run",
                trace_id="worker-observation-default-trace",
                project_key="tenant:worker-observation-default",
                candidate_review_key="review:worker-observation-default",
                candidate_id="candidate:worker-observation-default",
                queue="worker.observation",
            )
        finally:
            task_worker_observation_probe.pop_request()

        self.assertEqual(result["runtime_readback"]["line_key"], WORKER_OBSERVATION_LINE_KEY)
        self.assertEqual(
            result["runtime_readback"]["worker_name"],
            WORKER_OBSERVATION_FALLBACK_WORKER_NAME,
        )
        self.assertEqual(sum(result["effect_boundary"].values()), 0)


if __name__ == "__main__":
    unittest.main()
