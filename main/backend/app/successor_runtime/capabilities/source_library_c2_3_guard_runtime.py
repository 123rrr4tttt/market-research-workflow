"""C2.3 runtime wrapper that consumes the single-source-guard port.

The wrapper is the dispatch-boundary binding for ALL-SM-012: whenever an
effect payload declares a donor-shaped single-source guard, the successor
guard port is evaluated before the delegate provider gateway is invoked.
Rejected guards surface the typed guard error and never touch the delegate;
admitted guards record their execution fact before dispatch.
"""

from __future__ import annotations

from typing import Any

from functorial_kit import Failure

from app.successor_runtime.capabilities import single_source_guard_port as guard
from app.successor_runtime.capabilities import source_library_c2_shared as shared


def _guard_override_from_request(request: Any) -> dict[str, Any] | None:
    """Extract the donor-shaped guard override from one effect payload."""

    payload = dict(getattr(request, "effect_payload", {}) or {})
    if "override_params" in payload and isinstance(payload["override_params"], dict):
        return dict(payload["override_params"])
    raw_guard = payload.get("single_source_guard")
    if raw_guard is None:
        return None
    site_entries = (
        payload.get("site_entries")
        or payload.get("urls")
        or payload.get("site_entry_urls")
        or ()
    )
    if not site_entries:
        single_url = payload.get("url") or payload.get("site_entry")
        site_entries = (single_url,) if single_url else ()
    return {
        "site_entries": list(site_entries),
        "single_source_guard": raw_guard,
    }


class SingleSourceGuardedProviderGateway:
    """Dispatch boundary that runs the guard port before provider execution."""

    def __init__(
        self,
        delegate: Any,
        guard_port: guard.SingleSourceGuardPort | None = None,
    ) -> None:
        if delegate is None:
            # kit:boundary owner=source_library_c2_3_guard_runtime.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
            raise ValueError("guarded provider gateway requires a delegate")
        self.delegate = delegate
        self.guard_port = guard_port or guard.DefaultSingleSourceGuardPort()
        self.guard_decisions: list[guard.GuardDecision] = []
        self.execution_facts: list[guard.SingleSourceExecutionFact] = []

    @property
    def provider_calls(self) -> list[str]:
        return getattr(self.delegate, "provider_calls", [])

    def execute(
        self,
        request: Any,
        authorization: Any = None,
    ) -> Any:
        result = self.try_execute(request, authorization)
        if isinstance(result, Failure):
            if result.family != guard.source_library_single_source_guard_failures.name:
                return result
            context = result.context or {}
            raw_details = context.get("details")
            if isinstance(raw_details, dict):
                details = guard.GuardRejectionDetails(
                    reason_code=str(raw_details.get("reason_code", result.code)),
                    field=str(raw_details.get("field", "override_params.single_source_guard")),
                    expected=dict(raw_details.get("expected") or {}),
                    actual=dict(raw_details.get("actual") or {}),
                )
            else:
                details = guard.GuardRejectionDetails(
                    reason_code=str(context.get("reason_code", result.code)),
                    field="override_params.single_source_guard",
                    expected={},
                    actual={},
                )
            # kit:boundary owner=source_library_c2_3_guard_runtime.execute class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.single_source_guard.failure witness=test:test_w06_c2_total_core_failure_lifts
            raise guard.SourceLibrarySingleSourceGuardError(
                f"single_source_guard is blocked: {result.code}",
                details=details,
            )
        return result

    def try_execute(
        self,
        request: Any,
        authorization: Any = None,
    ) -> Any | Failure:
        """Total guard dispatch; rejected declarations become typed Failure."""

        try:
            override = _guard_override_from_request(request)
        except (TypeError, ValueError, AttributeError) as exc:
            return shared.c2_guard_failure(
                "single_source_guard_invalid_shape",
                str(exc),
                site="SingleSourceGuardedProviderGateway.try_execute",
            )
        if override is None:
            return self.delegate.execute(request, authorization)
        try:
            decision = self.guard_port.evaluate(
                {
                    "override_params": override,
                    "item_key": getattr(request, "item_key", ""),
                    "project_key": str(
                        getattr(
                            getattr(request, "project_scope", None),
                            "project_key",
                            "",
                        )
                        or ""
                    ),
                }
            )
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            return shared.c2_guard_failure(
                "single_source_guard_invalid_shape",
                str(exc),
                site="SingleSourceGuardedProviderGateway.try_execute",
            )
        self.guard_decisions.append(decision)
        if isinstance(decision, guard.GuardAdmitted):
            if decision.execution_fact is not None:
                self.execution_facts.append(decision.execution_fact)
            return self.delegate.execute(request, authorization)
        if not isinstance(decision, guard.GuardRejected):
            return shared.c2_guard_failure(
                "single_source_guard_invalid_shape",
                "single-source guard port returned an unknown decision",
                site="SingleSourceGuardedProviderGateway.try_execute",
            )
        details = decision.details or guard.GuardRejectionDetails(
            reason_code=decision.reason_code,
            field="override_params.single_source_guard",
            expected={},
            actual={},
        )
        return shared.c2_guard_failure(
            decision.reason_code,
            f"single_source_guard is blocked: {decision.reason_code}",
            site="SingleSourceGuardedProviderGateway.try_execute",
            reason_code=decision.reason_code,
            details=details.to_plain(),
        )

    def readback_attempt(self, attempt: Any, request: Any) -> Any:
        return self.delegate.readback_attempt(attempt, request)

    def cancel(self, attempt: Any, request: Any) -> Any:
        return self.delegate.cancel(attempt, request)

    def prove_not_started(self, attempt: Any, request: Any) -> Any:
        return self.delegate.prove_not_started(attempt, request)


__all__ = [
    "SingleSourceGuardedProviderGateway",
    "_guard_override_from_request",
]
