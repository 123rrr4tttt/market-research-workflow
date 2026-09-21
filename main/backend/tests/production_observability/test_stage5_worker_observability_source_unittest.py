from __future__ import annotations

import logging
from pathlib import Path
import sys
import unittest

from prometheus_client import REGISTRY, generate_latest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.celery_app import celery_app  # noqa: E402
from app.production_observability.worker import (  # noqa: E402
    WORKER_TASKS_METRIC_NAME,
    WORKER_TASK_LATENCY_METRIC_NAME,
    worker_trace_snapshot,
)
from app.services.observability_tasks import task_stage5_worker_observability_probe  # noqa: E402


class Stage5WorkerObservabilitySourceTestCase(unittest.TestCase):
    def test_eager_celery_chain_exports_metrics_log_and_trace(self) -> None:
        task_id = "stage5-worker-task-test"
        trace_id = "stage5-worker-trace-test"
        kwargs = {
            "request_id": "stage5-worker-request-test",
            "run_id": "stage5-worker-run-test",
            "trace_id": trace_id,
            "project_key": "tenant:stage5-worker-test",
            "candidate_review_key": "review:stage5-worker-candidate",
            "candidate_id": "candidate:stage5-worker-candidate",
            "queue": "stage5.worker.probe",
            "line_key": "stage5_worker_probe",
        }
        records: list[str] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(self.format(record))

        handler = CaptureHandler()
        logger = logging.getLogger("app.production_observability.worker")
        old_logger_level = logger.level
        old_config = {
            key: celery_app.conf[key]
            for key in ("task_always_eager", "task_eager_propagates", "result_backend")
        }
        celery_app.conf.update(
            task_always_eager=True,
            task_eager_propagates=True,
            result_backend="cache+memory://",
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            eager_result = task_stage5_worker_observability_probe.apply(
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
        self.assertEqual(
            result["candidate_identity"]["candidate_review_key"],
            kwargs["candidate_review_key"],
        )
        self.assertEqual(sum(result["effect_boundary"].values()), 0)

        traces = worker_trace_snapshot(trace_id)
        self.assertEqual([item["event"] for item in traces], ["worker_task_started", "worker_task_finished"])
        self.assertTrue(all(item["candidate_identity_redacted"] is True for item in traces))
        self.assertGreaterEqual(len(records), 2)
        self.assertTrue(any("worker_task_started" in item for item in records))
        self.assertTrue(any("worker_task_finished" in item for item in records))
        self.assertTrue(any('"record_type":"structured_log"' in item for item in records))
        self.assertTrue(any('"record_type":"trace"' in item for item in records))
        self.assertTrue(all(trace_id in item for item in records))

        task_labels = {
            "task_name": task_stage5_worker_observability_probe.name,
            "worker_name": traces[0]["worker_name"],
            "queue": kwargs["queue"],
            "project_key": kwargs["project_key"],
            "line_key": "stage5_worker_probe",
        }
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


if __name__ == "__main__":
    unittest.main()
