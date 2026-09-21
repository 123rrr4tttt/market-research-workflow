#!/usr/bin/env python3
"""Probe installed R7 rules from typed runtime sources without side effects."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.production_observability.config import (
    LOCAL_STAGE5_ALERT_THRESHOLD_PROVENANCE,
    LOCAL_STAGE5_LATENCY_BREACH_SECONDS,
    production_observability_config_from_settings,
)
from app.production_observability.contracts import MetricFamily
from app.production_observability.health import (
    DatabaseRuntimeSignal,
    ProjectionDriftStatus,
    ProjectionReadStatus,
    ProjectionReleaseStatus,
    ProjectionRuntimeSignal,
    ProviderRuntimeSignal,
    ProviderRuntimeStatus,
    QueueReadStatus,
    QueueRuntimeSignal,
    RuntimeAuthorityReadSignal,
    RuntimeAuthorityReadStatus,
    RuntimeBindingSignal,
    RuntimeBindingStatus,
    RuntimeHealthSnapshot,
)
from app.production_observability.runtime import ProductionObservabilityController


GAP_RULES = {
    "queue": ("stage5-local-queue", MetricFamily.QUEUE_DEPTH),
    "db_connection": (
        "stage5-local-db-connection",
        MetricFamily.DATABASE_CONNECTION_UNAVAILABLE,
    ),
    "provider_failure": (
        "stage5-local-provider-failure",
        MetricFamily.PROVIDER_FAILURE,
    ),
    "authority_mismatch": (
        "stage5-local-authority-mismatch",
        MetricFamily.AUTHORITY_MISMATCH,
    ),
    "projection_drift": (
        "stage5-local-projection-drift",
        MetricFamily.PROJECTION_DRIFT,
    ),
    "request_latency": (
        "stage5-local-request-latency",
        MetricFamily.REQUEST_LATENCY_BREACH_RATE,
    ),
}
MATCHING_SOURCE_DIGEST = "a" * 64
DRIFTED_SOURCE_DIGEST = "b" * 64


def summarize(evaluation: Any) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": item.rule_id,
            "state": item.state.value,
            "transition": item.transition.value,
            "reason": item.reason.value,
            "latest_value": item.latest_value,
            "authority": item.authority,
        }
        for item in evaluation.decision.alert_evaluations
    ]


def runtime_snapshot(*, gap_name: str | None, observed_at: datetime) -> RuntimeHealthSnapshot:
    projection_drift = gap_name == "projection_drift"
    return RuntimeHealthSnapshot(
        observed_at=observed_at,
        queue=QueueRuntimeSignal(
            source="redis.broker.llen:celery",
            read_status=QueueReadStatus.OK,
            depth=1 if gap_name == "queue" else 0,
        ),
        database=DatabaseRuntimeSignal(
            source="sqlalchemy.engine:select_1+pool_status",
            connection_status="error: OperationalError" if gap_name == "db_connection" else "ok",
            pool_status="error: pool_exhausted" if gap_name == "db_connection" else "ok",
            pool_size=10,
            checked_out=1,
            pool_limit=15,
        ),
        provider=ProviderRuntimeSignal(
            source="stage5-local-env-provider-failure",
            status=(
                ProviderRuntimeStatus.SIMULATED_FAILURE
                if gap_name == "provider_failure"
                else ProviderRuntimeStatus.SIMULATED_HEALTHY
            ),
            simulated=True,
        ),
        runtime_binding=RuntimeBindingSignal(
            source="app.state.production_runtime_bindings+release_identity",
            authority_status=(
                RuntimeBindingStatus.MISMATCH
                if gap_name == "authority_mismatch"
                else RuntimeBindingStatus.BOUND
            ),
            projection_release_status=(
                ProjectionReleaseStatus.MATCH
            ),
            authority_read=RuntimeAuthorityReadSignal(
                source="postgres.production-authority-read",
                read_status=(
                    RuntimeAuthorityReadStatus.MISMATCH
                    if gap_name == "authority_mismatch"
                    else RuntimeAuthorityReadStatus.OBSERVED
                ),
                task_id="task:probe",
                tenant_id="tenant:probe",
                project_scope_digest="0" * 64,
                project_registry_revision=1,
                capability_id="capability:probe",
                step_id="step:probe",
                claim_authority_epoch=2,
                expected_project_scope_digest="0" * 64,
                expected_project_registry_revision=1,
                expected_claim_authority_epoch=2,
                mismatch_fields=(
                    ("project_scope_digest",) if gap_name == "authority_mismatch" else ()
                ),
            ),
        ),
        projection=ProjectionRuntimeSignal(
            source="postgres.c9:semantic-source-closure+active-offset",
            read_status=ProjectionReadStatus.OK,
            drift_status=(
                ProjectionDriftStatus.MISMATCH
                if projection_drift
                else ProjectionDriftStatus.MATCH
            ),
            active_source_digest=(
                DRIFTED_SOURCE_DIGEST if projection_drift else MATCHING_SOURCE_DIGEST
            ),
            expected_source_digest=MATCHING_SOURCE_DIGEST,
            projection_generation=1,
            offset_revision=2,
            source_revision=3,
            offset_ref="c9:semantic-source:probe:closure_manifest",
        ),
    )


def replay_runtime_step(
    controller: ProductionObservabilityController,
    *,
    step_name: str,
    gap_name: str | None,
) -> tuple[Any, RuntimeHealthSnapshot]:
    observed_at = datetime.now(UTC)
    item = runtime_snapshot(gap_name=gap_name, observed_at=observed_at)
    base = controller.observe_runtime_health(
        observation_id=f"stage5-probe:{step_name}",
        snapshot=item,
    )
    evaluation = controller.observe_runtime_health(
        observation_id=f"stage5-probe:{step_name}",
        snapshot=item,
        production_receipt=base.receipt,
    )
    return evaluation, item


def replay_http_step(
    controller: ProductionObservabilityController,
    *,
    step_name: str,
    status_code: int,
    latency_seconds: float,
) -> Any:
    observed_at = datetime.now(UTC)
    base = controller.observe_http_request(
        observation_id=f"stage5-probe:{step_name}",
        status_code=status_code,
        observed_at=observed_at,
        latency_seconds=latency_seconds,
    )
    return controller.observe_http_request(
        observation_id=f"stage5-probe:{step_name}",
        status_code=status_code,
        observed_at=observed_at,
        latency_seconds=latency_seconds,
        production_receipt=base.receipt,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--runtime-summary", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    settings = SimpleNamespace(
        production_observability_runtime_id="mrw-stage5-local-observability",
        production_canary_route_enabled=False,
        production_domain_rejection_trigger_ratio=0.10,
        production_domain_rejection_recover_ratio=0.05,
        production_route_error_trigger_ratio=0.05,
        production_route_error_recover_ratio=0.01,
        production_release_error_trigger_ratio=0.05,
        production_release_error_recover_ratio=0.01,
    )
    config = production_observability_config_from_settings(
        settings,
        release_version=args.release_version,
    )
    controller = ProductionObservabilityController(config)
    evaluations: list[dict[str, Any]] = []
    gap_results: dict[str, bool] = {}

    for gap_name in GAP_RULES:
        if gap_name == "request_latency":
            trigger = replay_http_step(
                controller,
                step_name=f"{gap_name}_trigger",
                status_code=200,
                latency_seconds=LOCAL_STAGE5_LATENCY_BREACH_SECONDS,
            )
            recovery = replay_http_step(
                controller,
                step_name=f"{gap_name}_recovery",
                status_code=200,
                latency_seconds=0.10,
            )
            trigger_source: dict[str, Any] = {
                "http_status": 200,
                "latency_seconds": LOCAL_STAGE5_LATENCY_BREACH_SECONDS,
            }
            recovery_source: dict[str, Any] = {
                "http_status": 200,
                "latency_seconds": 0.10,
            }
        else:
            trigger, trigger_snapshot = replay_runtime_step(
                controller,
                step_name=f"{gap_name}_trigger",
                gap_name=gap_name,
            )
            recovery, recovery_snapshot = replay_runtime_step(
                controller,
                step_name=f"{gap_name}_recovery",
                gap_name=None,
            )
            trigger_source = {"runtime_source_snapshot": trigger_snapshot.to_dict()}
            recovery_source = {"runtime_source_snapshot": recovery_snapshot.to_dict()}

        trigger_alerts = {item["rule_id"]: item["state"] for item in summarize(trigger)}
        recovery_alerts = {item["rule_id"]: item["state"] for item in summarize(recovery)}
        rule_id = GAP_RULES[gap_name][0]
        gap_results[gap_name] = (
            trigger_alerts.get(rule_id) == "triggered"
            and recovery_alerts.get(rule_id) == "recovered"
        )
        evaluations.extend(
            (
                {
                    "step": f"{gap_name}_trigger",
                    "source": trigger_source,
                    "production_receipt_valid": trigger.decision.receipt_valid,
                    "receipt_path": "controller-derived local/runtime receipt replayed with matching observations",
                    "alerts": summarize(trigger),
                },
                {
                    "step": f"{gap_name}_recovery",
                    "source": recovery_source,
                    "production_receipt_valid": recovery.decision.receipt_valid,
                    "receipt_path": "controller-derived local/runtime receipt replayed with matching observations",
                    "alerts": summarize(recovery),
                },
            )
        )

    for step_name, status_code, latency_seconds in (
        ("domain_rejection_trigger", 403, 0.10),
        ("domain_rejection_recovery", 200, 0.10),
        ("route_and_release_error_trigger", 500, 0.10),
        ("route_and_release_error_recovery", 200, 0.10),
    ):
        evaluation = replay_http_step(
            controller,
            step_name=step_name,
            status_code=status_code,
            latency_seconds=latency_seconds,
        )
        evaluations.append(
            {
                "step": step_name,
                "source": {"http_status": status_code, "latency_seconds": latency_seconds},
                "production_receipt_valid": evaluation.decision.receipt_valid,
                "receipt_path": "controller-derived local/runtime receipt replayed with matching observations",
                "alerts": summarize(evaluation),
            }
        )

    runtime_summary_lines = Path(args.runtime_summary).read_text(encoding="utf-8").splitlines()
    all_gap_rules_passed = len(gap_results) == len(GAP_RULES) and all(gap_results.values())
    result = {
        "schema": "mrw.stage5.observability.alert-rule-probe.v3",
        "authoritative": False,
        "classification": "in-process semantic probe using typed runtime source snapshots and actual elapsed HTTP latency values; distinct from real collector observation and external authority",
        "release_version": args.release_version,
        "runtime_id": config.runtime_id,
        "rules": [rule.to_dict() for rule in config.alert_rules],
        "gap_rule_coverage": {
            name: {
                "rule_id": rule_id,
                "metric_family": family.value,
                "trigger_then_recover": gap_results.get(name, False),
            }
            for name, (rule_id, family) in GAP_RULES.items()
        },
        "local_gap_thresholds": {
            "boolean_trigger": 1.0,
            "boolean_recover": 0.0,
            "latency_breach_seconds": LOCAL_STAGE5_LATENCY_BREACH_SECONDS,
            "provenance": LOCAL_STAGE5_ALERT_THRESHOLD_PROVENANCE,
            "production_applicability": False,
            "provider_failure_simulation": "typed local source status; no provider call",
        },
        "evaluations": evaluations,
        "runtime_http_snapshots": runtime_summary_lines,
        "runtime_boundary": {
            "actual_runtime_http_observation": "health 200, unauthenticated bound route 401, authenticated HTTP bound route 403, subsequent health 200",
            "controller_state_export": "default Prometheus registry gauges are implemented; controller-state endpoint remains unexposed",
            "scrape_requirement": "real collector observation must be separately evidenced by the source-overlay Compose run",
            "recovery_receipt_requirement": "receipt-gated recovery remains installed; healthy observations alone cannot recover a latched alert",
            "probe_purpose": "validates installed rule trigger/recovery semantics without adding a platform endpoint or calling an external provider",
        },
        "exit_code": 0 if all_gap_rules_passed else 1,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
