"""Focused W07 runtime orchestration result/ABI witnesses."""

from __future__ import annotations

import pytest
from functorial_kit import Failure

from app.successor_runtime.runtime.replay import (
    RuntimeReplayError,
    replay_runtime_events,
    replay_runtime_events_result,
)


def test_w07_replay_result_is_closed_and_legacy_abi_is_preserved() -> None:
    result = replay_runtime_events_result(())
    assert isinstance(result, Failure)
    assert result.family == "successor.runtime.failure"
    assert result.code == "REPLAY_EVENT_INVALID"
    assert result.context is not None
    assert result.context["public_exception"] == "RuntimeReplayError"

    with pytest.raises(RuntimeReplayError, match="at least one event"):
        replay_runtime_events(())
