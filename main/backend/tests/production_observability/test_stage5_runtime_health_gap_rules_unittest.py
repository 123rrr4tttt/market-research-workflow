from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pytest
from prometheus_client import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.production_observability import (  # noqa: E402
    AlertState,
    DatabaseRuntimeSignal,
    MetricFamily,
    ProductionObservabilityController,
    ProjectionDriftStatus,
    ProjectionReadStatus,
    ProjectionReleaseStatus,
    ProjectionRuntimeSignal,
    ProviderRuntimeSignal,
    ProviderRuntimeStatus,
    QueueReadStatus,
    QueueRuntimeSignal,
    RuntimeBindingSignal,
    RuntimeBindingStatus,
    RuntimeAuthorityReadSignal,
    RuntimeAuthorityReadStatus,
    RuntimeHealthSnapshot,
    production_observability_config_from_settings,
)
from app.production_observability.metrics import RUNTIME_HEALTH_METRIC_NAME


GAP_RULE_IDS = (
    "local-runtime-queue.v2",
    "local-runtime-db-connection.v2",
    "local-runtime-provider-failure.v2",
    "local-runtime-authority-mismatch.v2",
    "local-runtime-projection-drift.v2",
    "local-runtime-request-latency.v2",
)
OBSERVED_AT = "2026-09-13T00:00:00+00:00"
MATCHING_DIGEST = "a" * 64
DRIFTED_DIGEST = "b" * 64


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        production_observability_runtime_id="stage5-runtime-health-test",
        production_canary_route_enabled=False,
        production_domain_rejection_trigger_ratio=0.10,
        production_domain_rejection_recover_ratio=0.05,
        production_route_error_trigger_ratio=0.05,
        production_route_error_recover_ratio=0.01,
        production_release_error_trigger_ratio=0.05,
        production_release_error_recover_ratio=0.01,
    )


def controller() -> ProductionObservabilityController:
    return ProductionObservabilityController(
        production_observability_config_from_settings(
            settings(),
            release_version="stage5-local",
        )
    )


def authority_signal(
    read_status: RuntimeAuthorityReadStatus,
) -> RuntimeAuthorityReadSignal:
    not_observed = read_status is RuntimeAuthorityReadStatus.NOT_OBSERVED
    return RuntimeAuthorityReadSignal(
        source="postgres.project_scope_registry+runtime_step_authorizations+runtime_capability_authority",
        read_status=read_status,
        task_id=None if not_observed else "run:authority:test",
        tenant_id=None if not_observed else "tenant:authority:test",
        project_scope_digest=None if not_observed else MATCHING_DIGEST,
        project_registry_revision=None if not_observed else 7,
        capability_id=None if not_observed else "capability:successor-runtime:c9",
        step_id=None if not_observed else "step:authority:test",
        claim_authority_epoch=None if not_observed else 1,
        expected_project_scope_digest=None if not_observed else MATCHING_DIGEST,
        expected_project_registry_revision=None if not_observed else 7,
        expected_claim_authority_epoch=None if not_observed else 1,
        mismatch_fields=("epoch",)
        if read_status is RuntimeAuthorityReadStatus.MISMATCH
        else (),
        not_observed_fields=("task", "tenant", "project_scope", "capability", "step", "epoch")
        if not_observed
        else (),
        read_error="task authority row is absent or ambiguous"
        if not_observed
        else None,
    )


def snapshot(
    *,
    observed_at: str = OBSERVED_AT,
    queue_depth: int = 0,
    queue_read_status: QueueReadStatus = QueueReadStatus.OK,
    database_connection_status: str = "ok",
    database_pool_status: str = "ok",
    provider_status: ProviderRuntimeStatus = ProviderRuntimeStatus.SIMULATED_HEALTHY,
    authority_status: RuntimeBindingStatus = RuntimeBindingStatus.BOUND,
    authority_read_status: RuntimeAuthorityReadStatus = RuntimeAuthorityReadStatus.OBSERVED,
    projection_release_status: ProjectionReleaseStatus = ProjectionReleaseStatus.MATCH,
    projection_drift: bool = False,
    projection_not_observed: bool = False,
) -> RuntimeHealthSnapshot:
    if projection_not_observed:
        projection = ProjectionRuntimeSignal(
            source="postgres.c9:semantic-source-closure+active-offset",
            read_status=ProjectionReadStatus.NOT_OBSERVED,
            drift_status=ProjectionDriftStatus.UNKNOWN,
            active_source_digest="",
            expected_source_digest="",
            projection_generation=0,
            offset_revision=0,
            source_revision=0,
            offset_ref="",
            status_detail="active C9 semantic-source offset missing",
        )
    else:
        projection = ProjectionRuntimeSignal(
            source="postgres.c9:semantic-source-closure+active-offset",
            read_status=ProjectionReadStatus.OK,
            drift_status=(
                ProjectionDriftStatus.MISMATCH if projection_drift else ProjectionDriftStatus.MATCH
            ),
            active_source_digest=DRIFTED_DIGEST if projection_drift else MATCHING_DIGEST,
            expected_source_digest=MATCHING_DIGEST,
            projection_generation=1,
            offset_revision=2,
            source_revision=3,
            offset_ref="c9:semantic-source:test:closure_manifest",
        )
    return RuntimeHealthSnapshot(
        observed_at=observed_at,
        queue=QueueRuntimeSignal(
            source="redis.broker.llen:celery",
            read_status=queue_read_status,
            depth=queue_depth,
        ),
        database=DatabaseRuntimeSignal(
            source="sqlalchemy.engine:select_1+pool_status",
            connection_status=database_connection_status,
            pool_status=database_pool_status,
            pool_size=10,
            checked_out=1,
            pool_limit=15,
        ),
        provider=ProviderRuntimeSignal(
            source="stage5-local-env-provider-failure",
            status=provider_status,
            simulated=True,
        ),
        runtime_binding=RuntimeBindingSignal(
            source="postgres.project_scope_registry+runtime_step_authorizations+runtime_capability_authority",
            authority_status=authority_status,
            projection_release_status=projection_release_status,
            authority_read=authority_signal(authority_read_status),
        ),
        projection=projection,
    )


class Stage5RuntimeHealthGapRuleTestCase(unittest.TestCase):
    def test_settings_adds_local_gap_and_latency_rules(self) -> None:
        config = production_observability_config_from_settings(
            settings(),
            release_version="stage5-local",
        )
        gap_rules = [rule for rule in config.alert_rules if rule.rule_id in GAP_RULE_IDS]

        self.assertEqual(len(config.alert_rules), 9)
        self.assertEqual(
            {rule.metric_family for rule in gap_rules},
            {
                MetricFamily.QUEUE_DEPTH,
                MetricFamily.DATABASE_CONNECTION_UNAVAILABLE,
                MetricFamily.PROVIDER_FAILURE,
                MetricFamily.AUTHORITY_MISMATCH,
                MetricFamily.PROJECTION_DRIFT,
                MetricFamily.REQUEST_LATENCY_BREACH_RATE,
            },
        )
        self.assertTrue(all(rule.trigger_threshold == 1.0 for rule in gap_rules))
        self.assertTrue(all(rule.recover_threshold == 0.0 for rule in gap_rules))

    def test_typed_runtime_sources_trigger_and_fail_closed_without_receipt(self) -> None:
        item = controller()

        triggered = item.observe_runtime_health(
            observation_id="stage5-health-bad",
            snapshot=snapshot(
                queue_depth=1,
                database_connection_status="error: OperationalError",
                database_pool_status="error: pool_exhausted",
                provider_status=ProviderRuntimeStatus.SIMULATED_FAILURE,
                authority_status=RuntimeBindingStatus.MISMATCH,
                authority_read_status=RuntimeAuthorityReadStatus.MISMATCH,
                projection_release_status=ProjectionReleaseStatus.MATCH,
                projection_drift=True,
            ),
        )
        unreceipted_recovery = item.observe_runtime_health(
            observation_id="stage5-health-good",
            snapshot=snapshot(observed_at="2026-09-13T00:01:00+00:00"),
        )

        trigger_states = {
            evaluation.rule_id: evaluation.state
            for evaluation in triggered.decision.alert_evaluations
        }
        recover_states = {
            evaluation.rule_id: evaluation.state
            for evaluation in unreceipted_recovery.decision.alert_evaluations
        }
        runtime_gap_rules = GAP_RULE_IDS[:-2]
        self.assertTrue(
            all(trigger_states[rule_id] is AlertState.TRIGGERED for rule_id in runtime_gap_rules)
        )
        self.assertTrue(
            all(recover_states[rule_id] is AlertState.TRIGGERED for rule_id in runtime_gap_rules)
        )

    def test_typed_runtime_sources_recover_with_controller_derived_receipt(self) -> None:
        item = controller()
        bad = snapshot(
            queue_depth=1,
            database_connection_status="error: OperationalError",
            database_pool_status="error: pool_exhausted",
            provider_status=ProviderRuntimeStatus.SIMULATED_FAILURE,
            authority_status=RuntimeBindingStatus.MISMATCH,
            authority_read_status=RuntimeAuthorityReadStatus.MISMATCH,
            projection_release_status=ProjectionReleaseStatus.MATCH,
            projection_drift=True,
        )
        good = snapshot(observed_at="2026-09-13T00:01:00+00:00")

        trigger_base = item.observe_runtime_health(
            observation_id="receipted-runtime-health",
            snapshot=bad,
        )
        triggered = item.observe_runtime_health(
            observation_id="receipted-runtime-health",
            snapshot=bad,
            production_receipt=trigger_base.receipt,
        )
        recovery_base = item.observe_runtime_health(
            observation_id="receipted-runtime-health-good",
            snapshot=good,
        )
        recovered = item.observe_runtime_health(
            observation_id="receipted-runtime-health-good",
            snapshot=good,
            production_receipt=recovery_base.receipt,
        )

        trigger_states = {
            evaluation.rule_id: evaluation.state
            for evaluation in triggered.decision.alert_evaluations
        }
        recover_states = {
            evaluation.rule_id: evaluation.state
            for evaluation in recovered.decision.alert_evaluations
        }
        runtime_gap_rules = GAP_RULE_IDS[:-2]
        self.assertTrue(
            all(trigger_states[rule_id] is AlertState.TRIGGERED for rule_id in runtime_gap_rules)
        )
        self.assertTrue(
            all(recover_states[rule_id] is AlertState.RECOVERED for rule_id in runtime_gap_rules)
        )
        self.assertTrue(triggered.decision.receipt_valid)
        self.assertTrue(recovered.decision.receipt_valid)

    def test_release_label_mismatch_alone_does_not_trigger_c9_projection_drift(self) -> None:
        item = controller()
        evaluation = item.observe_runtime_health(
            observation_id="release-label-without-c9-observation",
            snapshot=snapshot(
                projection_release_status=ProjectionReleaseStatus.MISMATCH,
                projection_not_observed=True,
            ),
        )

        alert = next(
            item
            for item in evaluation.decision.alert_evaluations
            if item.rule_id == "local-runtime-projection-drift.v2"
        )
        self.assertIsNone(alert.latest_value)
        self.assertEqual(alert.state, AlertState.UNKNOWN)

    def test_authority_normal_mismatch_recovery_with_derived_receipt(self) -> None:
        item = controller()
        normal = item.observe_runtime_health(
            observation_id="authority-normal",
            snapshot=snapshot(),
        )
        mismatch_base = item.observe_runtime_health(
            observation_id="authority-mismatch",
            snapshot=snapshot(
                observed_at="2026-09-13T00:01:00+00:00",
                authority_status=RuntimeBindingStatus.MISMATCH,
                authority_read_status=RuntimeAuthorityReadStatus.MISMATCH,
            ),
        )
        mismatch = item.observe_runtime_health(
            observation_id="authority-mismatch",
            snapshot=snapshot(
                observed_at="2026-09-13T00:01:00+00:00",
                authority_status=RuntimeBindingStatus.MISMATCH,
                authority_read_status=RuntimeAuthorityReadStatus.MISMATCH,
            ),
            production_receipt=mismatch_base.receipt,
        )
        recovery_base = item.observe_runtime_health(
            observation_id="authority-recovery",
            snapshot=snapshot(observed_at="2026-09-13T00:02:00+00:00"),
        )
        recovery = item.observe_runtime_health(
            observation_id="authority-recovery",
            snapshot=snapshot(observed_at="2026-09-13T00:02:00+00:00"),
            production_receipt=recovery_base.receipt,
        )

        def authority_state(evaluation: object) -> tuple[AlertState, float | None]:
            alert = next(
                item
                for item in evaluation.decision.alert_evaluations  # type: ignore[attr-defined]
                if item.rule_id == "local-runtime-authority-mismatch.v2"
            )
            return alert.state, alert.latest_value

        self.assertEqual(authority_state(normal), (AlertState.RECOVERED, 0.0))
        self.assertEqual(authority_state(mismatch), (AlertState.TRIGGERED, 1.0))
        self.assertEqual(authority_state(recovery), (AlertState.RECOVERED, 0.0))
        self.assertTrue(mismatch.decision.receipt_valid)
        self.assertTrue(recovery.decision.receipt_valid)

    def test_authority_not_observed_omits_metric_and_stays_unknown(self) -> None:
        item = controller()
        mismatch_base = item.observe_runtime_health(
            observation_id="authority-unknown",
            snapshot=snapshot(
                authority_status=RuntimeBindingStatus.MISMATCH,
                authority_read_status=RuntimeAuthorityReadStatus.MISMATCH,
            ),
        )
        mismatch = item.observe_runtime_health(
            observation_id="authority-unknown",
            snapshot=snapshot(
                authority_status=RuntimeBindingStatus.MISMATCH,
                authority_read_status=RuntimeAuthorityReadStatus.MISMATCH,
            ),
            production_receipt=mismatch_base.receipt,
        )
        unknown = item.observe_runtime_health(
            observation_id="authority-unknown-recheck",
            snapshot=snapshot(
                observed_at="2026-09-13T00:01:00+00:00",
                authority_status=RuntimeBindingStatus.UNKNOWN,
                authority_read_status=RuntimeAuthorityReadStatus.NOT_OBSERVED,
            ),
        )

        mismatch_alert = next(
            item
            for item in mismatch.decision.alert_evaluations
            if item.rule_id == "local-runtime-authority-mismatch.v2"
        )
        unknown_alert = next(
            item
            for item in unknown.decision.alert_evaluations
            if item.rule_id == "local-runtime-authority-mismatch.v2"
        )
        self.assertEqual(mismatch_alert.state, AlertState.TRIGGERED)
        self.assertEqual(unknown_alert.state, AlertState.UNKNOWN)
        self.assertIsNone(unknown_alert.latest_value)
        self.assertEqual(unknown_alert.observed_count, 0)

    def test_actual_http_latency_triggers_and_recoveries_with_derived_receipt(self) -> None:
        item = controller()
        slow_base = item.observe_http_request(
            observation_id="latency-slow",
            status_code=200,
            latency_seconds=0.30,
            observed_at=OBSERVED_AT,
        )
        slow = item.observe_http_request(
            observation_id="latency-slow",
            status_code=200,
            latency_seconds=0.30,
            observed_at=OBSERVED_AT,
            production_receipt=slow_base.receipt,
        )
        fast_base = item.observe_http_request(
            observation_id="latency-fast",
            status_code=200,
            latency_seconds=0.10,
            observed_at="2026-09-13T00:01:00+00:00",
        )
        fast = item.observe_http_request(
            observation_id="latency-fast",
            status_code=200,
            latency_seconds=0.10,
            observed_at="2026-09-13T00:01:00+00:00",
            production_receipt=fast_base.receipt,
        )

        slow_states = {
            evaluation.rule_id: evaluation.state for evaluation in slow.decision.alert_evaluations
        }
        fast_states = {
            evaluation.rule_id: evaluation.state for evaluation in fast.decision.alert_evaluations
        }
        self.assertEqual(slow_states["local-runtime-request-latency.v2"], AlertState.TRIGGERED)
        self.assertEqual(fast_states["local-runtime-request-latency.v2"], AlertState.RECOVERED)
        self.assertTrue(slow.decision.receipt_valid)
        self.assertTrue(fast.decision.receipt_valid)

    def test_c9_projection_closure_drift_recoveries_with_derived_receipt(self) -> None:
        item = controller()
        drift_base = item.observe_runtime_health(
            observation_id="c9-projection-drift",
            snapshot=snapshot(projection_drift=True),
        )
        drift = item.observe_runtime_health(
            observation_id="c9-projection-drift",
            snapshot=snapshot(projection_drift=True),
            production_receipt=drift_base.receipt,
        )
        match_base = item.observe_runtime_health(
            observation_id="c9-projection-match",
            snapshot=snapshot(observed_at="2026-09-13T00:01:00+00:00"),
        )
        match = item.observe_runtime_health(
            observation_id="c9-projection-match",
            snapshot=snapshot(observed_at="2026-09-13T00:01:00+00:00"),
            production_receipt=match_base.receipt,
        )

        drift_alert = next(
            item
            for item in drift.decision.alert_evaluations
            if item.rule_id == "local-runtime-projection-drift.v2"
        )
        match_alert = next(
            item
            for item in match.decision.alert_evaluations
            if item.rule_id == "local-runtime-projection-drift.v2"
        )
        self.assertEqual(drift_alert.latest_value, 1.0)
        self.assertEqual(drift_alert.state, AlertState.TRIGGERED)
        self.assertEqual(match_alert.latest_value, 0.0)
        self.assertEqual(match_alert.state, AlertState.RECOVERED)

    def test_projection_unavailable_stays_unknown_and_does_not_recover_drift(self) -> None:
        item = controller()
        drift_base = item.observe_runtime_health(
            observation_id="c9-projection-unknown",
            snapshot=snapshot(projection_drift=True),
        )
        drift = item.observe_runtime_health(
            observation_id="c9-projection-unknown",
            snapshot=snapshot(projection_drift=True),
            production_receipt=drift_base.receipt,
        )
        unavailable = item.observe_runtime_health(
            observation_id="c9-projection-unknown-recheck",
            snapshot=snapshot(
                observed_at="2026-09-13T00:01:00+00:00",
                projection_not_observed=True,
            ),
        )

        drift_alert = next(
            item
            for item in drift.decision.alert_evaluations
            if item.rule_id == "local-runtime-projection-drift.v2"
        )
        unavailable_alert = next(
            item
            for item in unavailable.decision.alert_evaluations
            if item.rule_id == "local-runtime-projection-drift.v2"
        )
        self.assertEqual(drift_alert.latest_value, 1.0)
        self.assertEqual(drift_alert.state, AlertState.TRIGGERED)
        self.assertIsNone(unavailable_alert.latest_value)
        self.assertEqual(unavailable_alert.state, AlertState.UNKNOWN)

    def test_runtime_health_observations_are_exported_on_default_metrics_registry(self) -> None:
        config = production_observability_config_from_settings(
            settings(),
            release_version="stage5-local",
        )
        item = ProductionObservabilityController(config)
        item.observe_runtime_health(
            observation_id="metrics-export",
            snapshot=snapshot(queue_depth=1),
        )

        labels = {
            "domain": config.domain,
            "route": config.route,
            "release_version": config.release_version,
            "metric_family": MetricFamily.QUEUE_DEPTH.value,
            "rule_id": "local-runtime-queue.v2",
        }
        sample = REGISTRY.get_sample_value(RUNTIME_HEALTH_METRIC_NAME, labels)
        self.assertIsNotNone(sample)
        self.assertEqual(sample, 1.0)

    def test_runtime_health_input_is_closed(self) -> None:
        item = controller()

        with self.assertRaises(TypeError):
            item.observe_runtime_health(
                observation_id="not-a-snapshot",
                snapshot={"queue_depth": 1},
            )
        with self.assertRaises(ValueError):
            snapshot(queue_depth=-1)
        with self.assertRaises(ValueError):
            ProjectionRuntimeSignal(
                source="postgres.c9",
                read_status=ProjectionReadStatus.OK,
                drift_status=ProjectionDriftStatus.MATCH,
                active_source_digest="not-a-digest",
                expected_source_digest="not-a-digest",
                projection_generation=0,
                offset_revision=0,
                source_revision=0,
                offset_ref="offset",
            )
        with self.assertRaises(ValueError):
            ProviderRuntimeSignal(
                source="real-provider",
                status=ProviderRuntimeStatus.SIMULATED_HEALTHY,
                simulated=False,
            )
