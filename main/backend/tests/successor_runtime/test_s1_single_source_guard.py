"""S1 single-source guard successor port parity and fail-closed tests.

Fixtures mirror the donor byte-closure shapes consumed by
``resource_pool.site_entry.single_source_guard.v1`` and the merged override
validated by ``services/source_library/single_source_guard.py``.  The tests
never import or execute donor code; they assert named parity observations on
the successor typed port: unique-source admission with execution-fact
emission, duplicate/conflicting/unknown source rejection, pre-dispatch
blocking and authority defaulting to false.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.successor_runtime.capabilities import single_source_guard_port as guard

ALLOWED = "https://example.com/feed.xml"
OTHER = "https://evil.example/feed.xml"


def _raw_guard(**overrides: Any) -> dict[str, Any]:
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


def _override(site_entries: list[str], **guard_overrides: Any) -> dict[str, Any]:
    return {
        "site_entries": site_entries,
        "single_source_guard": _raw_guard(**guard_overrides),
    }


def _typed_guard(**overrides: Any) -> guard.SingleSourceGuardDeclaration:
    return guard.SingleSourceGuardDeclaration.from_dict(_raw_guard(**overrides))


def _claims(**overrides: Any) -> guard.SourceDispatchClaims:
    raw: dict[str, Any] = {
        "site_entries": [ALLOWED],
        "urls": (),
        "site_entry_urls": (),
        "official_access_site_entries": (),
    }
    raw.update(overrides)
    return guard.SourceDispatchClaims.from_plain(raw)


def _admitted(decision: guard.GuardDecision) -> guard.GuardAdmitted:
    assert isinstance(decision, guard.GuardAdmitted)
    return decision


def test_unique_site_entry_is_admitted_and_emits_execution_fact() -> None:
    decision = guard.evaluate_guard_declaration(
        _typed_guard(),
        _claims(),
    )
    admitted = _admitted(decision)
    assert admitted.guard is not None
    assert admitted.guard.allowed_urls == (ALLOWED,)
    assert admitted.guard.allowed_count == 1
    assert admitted.guard.strict_source is True
    assert admitted.guard.guarantee is True
    assert admitted.guard.blocked_reason is None
    assert admitted.dispatch_allowed is True
    fact = admitted.execution_fact
    assert fact is not None
    assert fact.contract_version == "source_library.execution_fact.v1"
    assert fact.reason_code == "single_source_guard_passed"
    assert fact.guard_status == "passed"
    assert fact.guard_reason_code is None
    assert fact.source_refs[0]["site_entry_url"] == ALLOWED
    assert (
        fact.source_refs[0]["report_source_ref"]
        == "resource_pool.site_entry:project:10"
    )
    assert len(fact.digest()) == 64


def test_raw_facade_preserves_donor_guard_and_item_keys() -> None:
    override = _override([ALLOWED])
    decision = guard.guard_override_decision(
        override,
        item_key="demo.item",
        project_key="demo_proj",
    )
    admitted = _admitted(decision)
    assert admitted.guard is not None
    assert admitted.guard.to_plain()["status"] == "passed"
    assert admitted.guard.to_plain()["reason_code"] is None
    fact = admitted.execution_fact
    assert fact is not None
    assert fact.item_key == "demo.item"
    assert fact.project_key == "demo_proj"
    assert fact.single_source_guard is not None
    assert fact.single_source_guard.allowed_urls == (ALLOWED,)


def test_duplicate_site_entry_is_rejected_as_conflict() -> None:
    decision = guard.evaluate_guard_declaration(
        _typed_guard(),
        _claims(site_entries=[ALLOWED, ALLOWED]),
    )
    assert isinstance(decision, guard.GuardRejected)
    assert decision.reason_code == "single_source_guard_site_entries_mismatch"
    assert decision.dispatch_allowed is False
    assert not hasattr(decision, "execution_fact")


def test_conflicting_urls_sibling_is_rejected_fail_closed() -> None:
    override = {
        "site_entries": [ALLOWED],
        "urls": [OTHER],
        "single_source_guard": _raw_guard(),
    }
    decision = guard.guard_override_decision(override)
    assert isinstance(decision, guard.GuardRejected)
    assert decision.reason_code == "single_source_guard_site_entries_mismatch"
    assert decision.details is not None
    assert decision.details.actual["claims"] == [ALLOWED, OTHER]


def test_unknown_and_undeclared_guard_are_fail_closed() -> None:
    absent = guard.guard_override_decision({})
    assert isinstance(absent, guard.GuardRejected)
    assert absent.reason_code == "single_source_guard_missing"
    assert absent.dispatch_allowed is False

    invalid = guard.guard_override_decision(
        {"site_entries": [ALLOWED], "single_source_guard": "not-an-object"}
    )
    assert isinstance(invalid, guard.GuardRejected)
    assert invalid.reason_code == "single_source_guard_invalid_shape"


def test_blocked_guard_rejects_before_any_dispatch() -> None:
    provider_calls: list[str] = []

    def dispatch_boundary(request_id: str) -> None:
        provider_calls.append(request_id)

    decision = guard.guard_override_decision(
        _override(
            [ALLOWED],
            guarantee=False,
            blocked_reason="review_rejected",
            status="blocked",
        )
    )
    assert isinstance(decision, guard.GuardRejected)
    assert decision.reason_code == "single_source_guard_blocked"
    if decision.dispatch_allowed:
        dispatch_boundary("must-not-run")  # pragma: no cover
    assert provider_calls == []


def test_donor_decision_code_parity_matrix() -> None:
    cases: list[tuple[dict[str, Any], str]] = [
        (
            _override([ALLOWED], strict_source=False),
            "single_source_guard_strict_source_required",
        ),
        (
            _override([ALLOWED], guarantee=False, blocked_reason="review_disabled"),
            "single_source_guard_blocked",
        ),
        (
            _override([ALLOWED], allowed_urls=[], allowed_count=0),
            "single_source_guard_allowed_urls_invalid",
        ),
        (
            _override([ALLOWED], allowed_urls=[ALLOWED, OTHER], allowed_count=2),
            "single_source_guard_allowed_urls_invalid",
        ),
        (
            _override([OTHER]),
            "single_source_guard_site_entries_mismatch",
        ),
    ]
    for override, expected_code in cases:
        decision = guard.guard_override_decision(override)
        assert isinstance(decision, guard.GuardRejected)
        assert decision.reason_code == expected_code
        assert decision.dispatch_allowed is False
        assert decision.authority.granted is False


def test_authority_defaults_false_on_admitted_and_rejected() -> None:
    rejected = guard.guard_override_decision(
        _override([OTHER]),
    )
    admitted = guard.evaluate_guard_declaration(
        _typed_guard(),
        _claims(),
    )
    assert isinstance(rejected, guard.GuardRejected)
    assert isinstance(admitted, guard.GuardAdmitted)
    for decision in (rejected, admitted):
        assert decision.authority.granted is False
        assert decision.authority.live_provider_allowed is False
        assert decision.authority.reason == guard.GUARD_AUTHORITY_FALSE_REASON
    with pytest.raises(ValueError):
        guard.GuardAuthoritySnapshot(granted=True)


def test_acceptance_trace_maps_decision_to_fact_and_zero_dispatch() -> None:
    events: list[dict[str, Any]] = []
    override = _override([ALLOWED])
    decision = guard.guard_override_decision(
        override,
        item_key="demo.item",
        project_key="demo_proj",
    )
    admitted = _admitted(decision)
    assert admitted.execution_fact is not None
    assert admitted.execution_fact.digest()
    events.append(
        {"event": "guard_admitted", "digest": admitted.execution_fact.digest()}
    )

    blocked = guard.guard_override_decision(
        _override([OTHER]),
        item_key="demo.item",
        project_key="demo_proj",
    )
    assert isinstance(blocked, guard.GuardRejected)
    events.append({"event": "guard_blocked", "reason_code": blocked.reason_code})
    assert [event["event"] for event in events] == [
        "guard_admitted",
        "guard_blocked",
    ]
    assert len(events[0]["digest"]) == 64


def test_default_port_is_runtime_checkable_and_deterministic() -> None:
    port = guard.DefaultSingleSourceGuardPort()
    assert isinstance(port, guard.SingleSourceGuardPort)
    request = {
        "override_params": _override([ALLOWED]),
        "item_key": "demo.item",
        "project_key": "demo_proj",
    }
    first = guard.guard_override_decision(
        request["override_params"],
        item_key="demo.item",
        project_key="demo_proj",
    )
    second = port.evaluate(request)
    assert isinstance(first, guard.GuardAdmitted)
    assert isinstance(second, guard.GuardAdmitted)
    assert second.to_plain() == first.to_plain()
    assert second.authority.granted is False


def test_missing_optional_declaration_fields_still_yield_donor_codes() -> None:
    raw_guard = _raw_guard()
    raw_guard.pop("allowed_count", None)
    decision = guard.guard_override_decision(
        {"site_entries": [ALLOWED], "single_source_guard": raw_guard}
    )
    assert isinstance(decision, guard.GuardRejected)
    assert decision.reason_code == "single_source_guard_allowed_urls_invalid"

    non_boolean = guard.guard_override_decision(
        {
            "site_entries": [ALLOWED],
            "single_source_guard": _raw_guard(strict_source="yes"),
        }
    )
    assert isinstance(non_boolean, guard.GuardRejected)
    assert non_boolean.reason_code == "single_source_guard_strict_source_required"
