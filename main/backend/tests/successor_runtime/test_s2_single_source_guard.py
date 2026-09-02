"""S2 C2.3 single-source-guard runtime binding tests.

The guard wrapper is installed by the C2 assembly around the provider
gateway.  These tests prove the guard port is actually evaluated before
delegate dispatch and that rejected guards never reach the provider.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.successor_runtime.assembly.base import local_assembly_scope_digest
from app.successor_runtime.assembly.c2_assembly import build_c2_assembly
from app.successor_runtime.capabilities import single_source_guard_port as guard
from app.successor_runtime.capabilities.source_library_c2_3_guard_runtime import (
    SingleSourceGuardedProviderGateway,
)
from app.successor_runtime.substrate.postgres.source_library_c2_23_canary import (
    C2_3StoreRehydratedHandler,
)

pytestmark = pytest.mark.unit

ALLOWED = "https://example.com/feed.xml"


class _Delegate:
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def provider_calls(self) -> list[str]:
        return self.calls

    def execute(self, request: Any, authorization: Any = None) -> str:
        self.calls.append(request.request_id)
        return "dispatched"


def _guard_value(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "contract_version": "resource_pool.site_entry.single_source_guard.v1",
        "strict_source": True,
        "guarantee": True,
        "allowed_urls": [ALLOWED],
        "allowed_count": 1,
        "blocked_reason": None,
        "reason_code": None,
        "status": "passed",
        "source_ref": {"site_entry_url": ALLOWED},
        "report_source_ref": "resource_pool.site_entry:project:10",
    }
    value.update(overrides)
    return value


def _request(**payload_overrides: Any) -> Any:
    payload: dict[str, Any] = {
        "site_entries": [ALLOWED],
        "single_source_guard": _guard_value(),
    }
    payload.update(payload_overrides)
    return SimpleNamespace(
        request_id="request:c2-3-guard:001",
        item_key="handler.cluster.news",
        project_scope=SimpleNamespace(project_key="demo_proj"),
        effect_payload=payload,
    )


def test_admitted_guard_runs_port_then_dispatch() -> None:
    delegate = _Delegate()
    wrapper = SingleSourceGuardedProviderGateway(delegate=delegate)

    outcome = wrapper.execute(_request())

    assert outcome == "dispatched"
    assert delegate.calls == ["request:c2-3-guard:001"]
    assert len(wrapper.guard_decisions) == 1
    assert isinstance(wrapper.guard_decisions[0], guard.GuardAdmitted)
    assert len(wrapper.execution_facts) == 1
    fact = wrapper.execution_facts[0]
    assert fact.contract_version == "source_library.execution_fact.v1"
    assert fact.reason_code == "single_source_guard_passed"
    assert wrapper.guard_decisions[0].authority.granted is False
    assert wrapper.guard_decisions[0].authority.live_provider_allowed is False


@pytest.mark.parametrize(
    ("override", "reason_code"),
    [
        ({"strict_source": False}, "single_source_guard_strict_source_required"),
        (
            {
                "guarantee": False,
                "blocked_reason": "review_rejected",
                "status": "blocked",
            },
            "single_source_guard_blocked",
        ),
        (
            {"allowed_urls": [], "allowed_count": 0},
            "single_source_guard_allowed_urls_invalid",
        ),
    ],
)
def test_rejected_guard_never_dispatches(
    override: dict[str, Any],
    reason_code: str,
) -> None:
    delegate = _Delegate()
    wrapper = SingleSourceGuardedProviderGateway(delegate=delegate)

    with pytest.raises(guard.SourceLibrarySingleSourceGuardError) as exc:
        wrapper.execute(_request(single_source_guard=_guard_value(**override)))

    assert exc.value.details.reason_code == reason_code
    assert delegate.calls == []
    assert wrapper.execution_facts == []


def test_site_entry_mismatch_rejects_before_dispatch() -> None:
    delegate = _Delegate()
    wrapper = SingleSourceGuardedProviderGateway(delegate=delegate)

    with pytest.raises(guard.SourceLibrarySingleSourceGuardError) as exc:
        wrapper.execute(
            _request(
                site_entries=["https://other.example/feed.xml"],
            )
        )

    assert exc.value.details.reason_code == "single_source_guard_site_entries_mismatch"
    assert delegate.calls == []


def test_request_without_guard_declaration_preserves_unguarded_dispatch() -> None:
    delegate = _Delegate()
    wrapper = SingleSourceGuardedProviderGateway(delegate=delegate)

    outcome = wrapper.execute(
        SimpleNamespace(
            request_id="request:c2-3-unguarded:001",
            item_key="market.default.tech",
            project_scope=SimpleNamespace(project_key="demo_proj"),
            effect_payload={"protocol_search": True, "query_term": "robotics"},
        )
    )

    assert outcome == "dispatched"
    assert delegate.calls == ["request:c2-3-unguarded:001"]
    assert wrapper.guard_decisions == []


def test_c2_assembly_installs_guarded_gateway_around_c23_dispatch() -> None:
    assembly = build_c2_assembly(
        uow_factory=lambda: object(),  # type: ignore[arg-type]
        project_scope_digest=local_assembly_scope_digest(),
    )
    c2_3_handlers = [
        handler
        for handler in assembly.handlers
        if isinstance(handler, C2_3StoreRehydratedHandler)
    ]
    assert len(c2_3_handlers) == 1
    handler = c2_3_handlers[0]
    assert handler.single_source_guard_port is not None
    assert isinstance(handler.guarded_gateway, SingleSourceGuardedProviderGateway)
    assert "SINGLE_SOURCE_GUARD_PORT_CONSUMED_BEFORE_DISPATCH" in (
        assembly.cell("C2.3").note
    )
    assert handler.guarded_gateway.guard_decisions == []
    assert handler.guarded_gateway.execution_facts == []
