"""Focused W02 failure-family witnesses for OAuth and skill-runtime lifts."""

from __future__ import annotations

from pathlib import Path

import pytest
from functorial_kit import Failure

from mrw_functorial_kit.core.agent_service_semantics import (
    agent_skill_runtime_failures,
    codex_oauth_failures,
)


def test_w02_oauth_failure_producer_and_legacy_lift_preserve_value_error_abi() -> None:
    from app.services.codex_oauth import _oauth_failure, _raise_oauth_failure

    failure = _oauth_failure(
        "state_required",
        "state is required",
        operation="exchange_code_to_session",
        site="state",
        public_exception="ValueError",
    )

    assert isinstance(failure, Failure)
    assert codex_oauth_failures.matches(failure)
    assert failure.context is not None
    assert failure.context["witness"] == "test:test_w02_oauth_failure_lifts"
    with pytest.raises(ValueError, match="^state is required$"):
        _raise_oauth_failure(failure, ValueError)


def test_w02_oauth_token_sink_path_rejection_uses_the_closed_family() -> None:
    from app.services.codex_oauth import (
        TokenSinkPathSecurityError,
        _assert_safe_token_sink_path,
    )

    with pytest.raises(
        TokenSinkPathSecurityError,
        match="^token_sink_path_must_be_absolute$",
    ):
        _assert_safe_token_sink_path(Path("relative-token-sink.json"), for_write=False)


def test_w02_skill_failure_producer_and_legacy_lift_preserve_permission_abi() -> None:
    from app.services.skill_runtime import _raise_skill_failure, _skill_failure

    failure = _skill_failure(
        "approval_context_required",
        "skill invoke denied: example (approval_context_required)",
        operation="enforce_runtime_policies",
        site="approval_context",
        public_exception="PermissionError",
    )

    assert isinstance(failure, Failure)
    assert agent_skill_runtime_failures.matches(failure)
    assert failure.context is not None
    assert failure.context["witness"] == "test:test_w02_skill_runtime_failure_lifts"
    with pytest.raises(
        PermissionError,
        match=r"^skill invoke denied: example \(approval_context_required\)$",
    ):
        _raise_skill_failure(failure, PermissionError)


def test_w02_skill_runtime_invalid_actor_role_is_closed_before_abi_lift() -> None:
    from app.services.skill_runtime import _normalize_actor_roles

    with pytest.raises(ValueError, match="^unsupported actor_role: invalid$"):
        _normalize_actor_roles(("invalid",))
