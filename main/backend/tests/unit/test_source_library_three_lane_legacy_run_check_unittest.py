from __future__ import annotations

import unittest
from collections.abc import Callable
from typing import Any

_check_contract: Callable[[], dict[str, Any]] | None = None
_import_error: Exception | None = None
try:
    from scripts.check_source_library_three_lane_legacy_run_contract import (
        check_contract as _loaded_check_contract,
    )

    _check_contract = _loaded_check_contract
except Exception as exc:  # noqa: BLE001
    _import_error = exc


class SourceLibraryThreeLaneLegacyRunCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        if _import_error is not None or _check_contract is None:
            raise unittest.SkipTest(
                f"source-library three-lane checker imports failed: {_import_error}"
            )

    def test_legacy_run_endpoint_returns_explicit_410_contract(self) -> None:
        from app.main import app
        from app.production_observability import (
            AlertRule,
            MetricFamily,
            PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION,
            ProductionObservabilityConfig,
            ProductionObservabilityController,
        )

        def _controller() -> ProductionObservabilityController:
            domain = "source_library"
            route = "legacy-run-contract"
            release_version = "test"
            config = ProductionObservabilityConfig(
                contract_version=PRODUCTION_OBSERVABILITY_RUNTIME_CONTRACT_VERSION,
                runtime_id="legacy-run-contract-test",
                domain=domain,
                route=route,
                release_version=release_version,
                canary_route_enabled=True,
                alert_rules=(
                    AlertRule(
                        rule_id="legacy-run-route-error",
                        metric_family=MetricFamily.ROUTE_ERROR_RATE,
                        domain=domain,
                        route=route,
                        release_version=release_version,
                        trigger_threshold=1.0,
                        recover_threshold=0.0,
                    ),
                ),
            )
            return ProductionObservabilityController(config)

        check_contract = _check_contract
        self.assertIsNotNone(check_contract)
        assert check_contract is not None

        previous_controller = getattr(app.state, "production_observability_r7", None)
        try:
            rollback_controller = _controller()
            rollback_controller.request_stop(
                request_id="legacy-run-contract-prior-stop",
                requested_by="same-process-witness",
                reason="simulate prior suite rollback latch",
            )
            app.state.production_observability_r7 = rollback_controller
            rejected_report = check_contract()
            self.assertEqual(rejected_report["legacy_response"]["status_code"], 403)
            self.assertEqual(
                rejected_report["legacy_response"]["details"]["reason_code"],
                "observability_rollback_latched",
            )

            app.state.production_observability_r7 = _controller()
            report = check_contract()
        finally:
            app.state.production_observability_r7 = previous_controller

        self.assertEqual(report["status"], "pass", report["failures"])
        response = report["legacy_response"]
        self.assertEqual(response["status_code"], 410)
        self.assertEqual(response["x_error_code"], "INVALID_INPUT")
        self.assertEqual(response["error_code"], "INVALID_INPUT")
        self.assertEqual(response["deprecated"], "source_library.legacy_item_run.v1")
        self.assertEqual(response["details"]["replacement_endpoint"], "/api/v1/ingest/source-library/run")
        self.assertEqual(response["details"]["legacy_status"], "410_gone")
        self.assertFalse(response["details"]["runs_source_library_item"])


if __name__ == "__main__":
    unittest.main()
