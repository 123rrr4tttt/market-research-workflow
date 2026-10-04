from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.production_observability import health as production_health  # noqa: E402
from app.production_observability import http as production_http  # noqa: E402
from app.release_identity import RELEASE_VERSION  # noqa: E402
from app.production_observability import (  # noqa: E402
    ProjectionDriftStatus,
    ProjectionReadStatus,
    ProjectionReleaseStatus,
    ProjectionRuntimeSignal,
    ProviderRuntimeStatus,
    QueueReadStatus,
    QueueRuntimeSignal,
    RuntimeBindingStatus,
    RuntimeAuthorityReadSignal,
    RuntimeAuthorityReadStatus,
)


class Stage5RuntimeHealthSourceWiringTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = SimpleNamespace(
            production_observability_runtime_id="stage5-runtime-source-test",
            production_canary_route_enabled=False,
            production_domain_rejection_trigger_ratio=0.10,
            production_domain_rejection_recover_ratio=0.05,
            production_route_error_trigger_ratio=0.05,
            production_route_error_recover_ratio=0.01,
            production_release_error_trigger_ratio=0.05,
            production_release_error_recover_ratio=0.01,
            db_pool_max_overflow=5,
        )
        self.authority_signal = RuntimeAuthorityReadSignal(
            source=production_health.AUTHORITY_READ_SOURCE,
            read_status=RuntimeAuthorityReadStatus.OBSERVED,
            task_id="run:authority:test",
            tenant_id="tenant:authority:test",
            project_scope_digest="a" * 64,
            project_registry_revision=7,
            capability_id="capability:successor-runtime:c9",
            step_id="step:authority:test",
            claim_authority_epoch=1,
            expected_project_scope_digest="a" * 64,
            expected_project_registry_revision=7,
            expected_claim_authority_epoch=1,
        )

    def test_deep_health_sources_build_typed_runtime_snapshot(self) -> None:
        queue_signal = QueueRuntimeSignal(
            source="redis.broker.llen:celery",
            read_status=QueueReadStatus.OK,
            depth=2,
        )
        projection_signal = ProjectionRuntimeSignal(
            source="postgres.c9:semantic-source-closure+active-offset",
            read_status=ProjectionReadStatus.OK,
            drift_status=ProjectionDriftStatus.MATCH,
            active_source_digest="a" * 64,
            expected_source_digest="a" * 64,
            projection_generation=1,
            offset_revision=2,
            source_revision=3,
            offset_ref="c9:semantic-source:test:closure_manifest",
        )
        with (
            patch.object(production_health, "read_runtime_queue_signal", return_value=queue_signal),
            patch.object(
                production_health,
                "read_runtime_projection_signal",
                return_value=projection_signal,
            ),
            patch.object(
                production_health,
                "read_runtime_authority_signal",
                return_value=self.authority_signal,
            ),
            patch.dict(production_health.os.environ, {}, clear=False),
        ):
            production_health.os.environ.pop("STAGE5_SIMULATE_PROVIDER_FAILURE", None)
            item = production_health.build_runtime_health_snapshot(
                database_connection_status="ok",
                database_pool_status="ok",
                pool_status={"size": 3, "checkedout": 1},
                runtime_status={"runtime_mode": "docker"},
                engine=object(),
                settings_obj=self.settings,
                release_version=RELEASE_VERSION,
                production_runtime=False,
                service_version=RELEASE_VERSION,
            )

        self.assertEqual(item.queue, queue_signal)
        self.assertEqual(item.database.source, "sqlalchemy.engine:select_1+pool_status")
        self.assertEqual(item.database.pool_size, 3)
        self.assertEqual(item.database.pool_limit, 8)
        self.assertEqual(item.provider.status, ProviderRuntimeStatus.NOT_OBSERVED)
        self.assertFalse(item.provider.simulated)
        self.assertEqual(item.runtime_binding.authority_status, RuntimeBindingStatus.BOUND)
        self.assertEqual(item.runtime_binding.authority_read, self.authority_signal)
        self.assertEqual(
            item.runtime_binding.projection_release_status,
            ProjectionReleaseStatus.MATCH,
        )
        self.assertEqual(item.projection, projection_signal)

    def test_task_authority_fields_read_normal_mismatch_and_recover(self) -> None:
        scope = SimpleNamespace(
            project_key="tenant:authority:test",
            scope_digest="a" * 64,
            project_registry_revision=7,
        )
        normal_step = SimpleNamespace(
            project_key="tenant:authority:test",
            project_scope_digest="a" * 64,
            project_registry_revision=7,
            capability_id="capability:successor-runtime:c9",
            step_id="step:authority:test",
            claim_authority_epoch=1,
        )
        capability = SimpleNamespace(
            project_key="tenant:authority:test",
            capability_id="capability:successor-runtime:c9",
            authority_epoch=1,
        )

        normal = production_health.runtime_authority_read_signal_from_rows(
            scope=scope,
            step=normal_step,
            capability=capability,
            task_id="run:authority:test",
        )
        mismatched = production_health.runtime_authority_read_signal_from_rows(
            scope=scope,
            step=normal_step,
            capability=SimpleNamespace(**{**vars(capability), "authority_epoch": 2}),
            task_id="run:authority:test",
        )
        recovered = production_health.runtime_authority_read_signal_from_rows(
            scope=scope,
            step=normal_step,
            capability=capability,
            task_id="run:authority:test",
        )

        self.assertEqual(normal.read_status, RuntimeAuthorityReadStatus.OBSERVED)
        self.assertEqual(mismatched.read_status, RuntimeAuthorityReadStatus.MISMATCH)
        self.assertEqual(mismatched.mismatch_fields, ("epoch",))
        self.assertEqual(recovered.read_status, RuntimeAuthorityReadStatus.OBSERVED)

    def test_task_authority_without_identity_is_not_observed(self) -> None:
        signal = production_health.authority_not_observed(
            "task id and tenant id are required",
            task_id=None,
            tenant_id=None,
        )

        self.assertEqual(signal.read_status, RuntimeAuthorityReadStatus.NOT_OBSERVED)
        self.assertEqual(
            signal.not_observed_fields,
            ("task", "tenant", "project_scope", "capability", "step", "epoch"),
        )

    def test_http_observer_receives_actual_latency_and_terminal_outcome(self) -> None:
        calls: list[dict] = []

        def observer(**kwargs: object) -> None:
            calls.append(kwargs)

        production_http.observe_production_http_request(
            controller=SimpleNamespace(observe_http_request=observer),
            request_id="request-1",
            status_code=200,
            terminal_outcome="success",
            latency_seconds=0.3,
        )

        self.assertEqual(
            calls,
            [
                {
                    "observation_id": "request-1",
                    "status_code": 200,
                    "terminal_outcome": "success",
                    "latency_seconds": 0.3,
                }
            ],
        )

    def test_provider_without_explicit_evidence_is_not_reported_healthy(self) -> None:
        with patch.dict(production_health.os.environ, {}, clear=False):
            production_health.os.environ.pop("STAGE5_SIMULATE_PROVIDER_FAILURE", None)
            local = production_health.read_runtime_provider_signal(
                self.settings,
                production_runtime=False,
            )
            production_signal = production_health.read_runtime_provider_signal(
                self.settings,
                production_runtime=True,
            )

        self.assertEqual(local.status, ProviderRuntimeStatus.NOT_OBSERVED)
        self.assertEqual(production_signal.status, ProviderRuntimeStatus.UNSUPPORTED)
        self.assertFalse(local.simulated)
        self.assertFalse(production_signal.simulated)
