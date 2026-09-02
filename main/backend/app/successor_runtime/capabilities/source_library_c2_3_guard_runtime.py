"""C2.3 runtime wrapper that consumes the single-source-guard port.

The wrapper is the dispatch-boundary binding for ALL-SM-012: whenever an
effect payload declares a donor-shaped single-source guard, the successor
guard port is evaluated before the delegate provider gateway is invoked.
Rejected guards raise the typed guard error and never touch the delegate;
admitted guards record their execution fact before dispatch.
"""

from __future__ import annotations

from typing import Any

from app.successor_runtime.capabilities import single_source_guard_port as guard


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
        override = _guard_override_from_request(request)
        if override is None:
            return self.delegate.execute(request, authorization)
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
        self.guard_decisions.append(decision)
        if isinstance(decision, guard.GuardAdmitted):
            if decision.execution_fact is not None:
                self.execution_facts.append(decision.execution_fact)
            return self.delegate.execute(request, authorization)
        details = decision.details or guard.GuardRejectionDetails(
            reason_code=decision.reason_code,
            field="override_params.single_source_guard",
            expected={},
            actual={},
        )
        raise guard.SourceLibrarySingleSourceGuardError(
            f"single_source_guard is blocked: {decision.reason_code}",
            details=details,
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
