"""Legacy actual postprocess writer-zero replay and frozen P1 locator tests."""

from __future__ import annotations

import pytest

from app.successor_migration.legacy_ingest_c7 import (
    LEGACY_INGEST_C7_WRITER_DISABLED,
    LegacyIngestC7Replay,
    LegacyIngestWriterDisabledError,
    capture_legacy_ingest_c7_fixture,
    frozen_p1_cell_locators,
)
from tests.successor_runtime.p4_c7_fixture import submission


def test_legacy_actual_postprocess_replay_has_writer_spy_zero() -> None:
    fixture, replay = capture_legacy_ingest_c7_fixture(submission())
    assert fixture["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert fixture["writer_enabled"] is False
    assert fixture["writer_calls"] == 0
    assert fixture["provider_calls"] == 0
    assert fixture["authority"] is False
    assert fixture["writer_result_present"] is False
    assert fixture["run_writer"] is False
    assert fixture["run_extraction"] is False
    assert fixture["fixture_digest"]
    assert replay.writer_calls == 0


def test_legacy_writer_is_hard_disabled() -> None:
    assert LEGACY_INGEST_C7_WRITER_DISABLED is True
    replay = LegacyIngestC7Replay()
    with pytest.raises(LegacyIngestWriterDisabledError):
        replay.persist({"doc_type": "unknown"})
    assert replay.writer_calls == 1


def test_replay_never_invokes_writer_and_is_repeatable() -> None:
    replay = LegacyIngestC7Replay()
    first = replay.capture(submission())
    second = replay.capture(submission())
    assert first == second
    assert replay.writer_calls == 0
    assert replay.replay_calls == 2


def test_frozen_p1_locators_are_present_for_all_c7_cells() -> None:
    locators = frozen_p1_cell_locators()
    assert set(locators) == {"C7.1", "C7.2", "C7.3", "C7.4"}
    for cell in locators.values():
        assert cell["locator_paths"]
        assert "FROZEN_LOCATORS_PRESENT" in str(cell["locator_status"])
