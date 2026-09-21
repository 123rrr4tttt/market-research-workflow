#!/usr/bin/env python3
"""Exercise runtime-health observation with live DB/Redis sources and a local receipt gate."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime

import redis
from sqlalchemy import text

import app.main as main_module
from app.production_observability import ProductionObservabilityController
from app.production_observability.config import production_observability_config_from_settings


def _summary(evaluation):
    return {
        "queue_rule": next(
            item.state.value
            for item in evaluation.decision.alert_evaluations
            if item.rule_id == "stage5-local-queue"
        ),
        "queue_transition": next(
            item.transition.value
            for item in evaluation.decision.alert_evaluations
            if item.rule_id == "stage5-local-queue"
        ),
        "receipt_valid": evaluation.decision.receipt_valid,
        "action": evaluation.decision.action.value,
        "stop_reason": evaluation.decision.stop_reason.value if evaluation.decision.stop_reason else None,
    }


def main() -> int:
    queue_name = "celery"
    redis_client = redis.Redis.from_url(main_module.settings.redis_url)
    token = f"stage5-live-probe-{uuid.uuid4()}"
    redis_client.lpush(queue_name, token)
    try:
        settings = main_module.settings
        config = production_observability_config_from_settings(
            settings,
            release_version=main_module.RELEASE_VERSION,
        )
        controller = ProductionObservabilityController(config)
        main_module.app.state.production_observability_r7 = controller
        main_module.app.state.production_runtime_bindings = (
            main_module.build_production_runtime_bindings(main_module.engine, settings)
        )

        with main_module.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        pool_status = main_module.get_db_pool_status()
        runtime_status = {"runtime_mode": "docker"}

        os.environ["STAGE5_SIMULATE_PROVIDER_FAILURE"] = "1"
        bad = main_module._build_runtime_health_snapshot(
            database_connection_status="ok",
            database_pool_status="ok",
            pool_status=pool_status,
            runtime_status=runtime_status,
        )
        trigger_base = controller.observe_runtime_health(
            observation_id="stage5-live-runtime-health",
            snapshot=bad,
        )
        trigger = controller.observe_runtime_health(
            observation_id="stage5-live-runtime-health",
            snapshot=bad,
            production_receipt=trigger_base.receipt,
        )

        redis_client.lpop(queue_name)
        os.environ.pop("STAGE5_SIMULATE_PROVIDER_FAILURE", None)
        good = main_module._build_runtime_health_snapshot(
            database_connection_status="ok",
            database_pool_status="ok",
            pool_status=main_module.get_db_pool_status(),
            runtime_status=runtime_status,
        )
        recovery_base = controller.observe_runtime_health(
            observation_id="stage5-live-runtime-health-recovery",
            snapshot=good,
        )
        recovered = controller.observe_runtime_health(
            observation_id="stage5-live-runtime-health-recovery",
            snapshot=good,
            production_receipt=recovery_base.receipt,
        )
        result = {
            "schema": "mrw.stage5.observability.live-runtime-health-receipt.v1",
            "authoritative": False,
            "external_provider_calls": 0,
            "source": {
                "queue": bad.queue.to_dict(),
                "database": bad.database.to_dict(),
                "runtime_binding": bad.runtime_binding.to_dict(),
                "provider_failure_simulated": bad.provider.to_dict(),
                "recovery_queue": good.queue.to_dict(),
                "recovery_provider": good.provider.to_dict(),
            },
            "chain": {
                "trigger": _summary(trigger),
                "trigger_receipt_digest": trigger_base.receipt.digest,
                "recovery": _summary(recovered),
                "recovery_receipt_digest": recovery_base.receipt.digest,
            },
            "boundary": "controller-derived local/runtime receipt; no production authority or external provider call",
            "observed_at": datetime.now(UTC).isoformat(),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        redis_client.lrem(queue_name, 0, token)
        os.environ.pop("STAGE5_SIMULATE_PROVIDER_FAILURE", None)


if __name__ == "__main__":
    raise SystemExit(main())
