from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import get_args

import pytest

from app.successor_runtime.capabilities import ingest_c7_movements as c7


ROOT = Path(__file__).resolve().parents[1]


def _registry_members(name: str) -> tuple[str, ...]:
    registry = json.loads((ROOT / "registries/vocabularies.json").read_text())[
        "entries"
    ]
    return next(tuple(entry["members"]) for entry in registry if entry["name"] == name)


def _registry_codes(name: str) -> tuple[str, ...]:
    registry = json.loads((ROOT / "registries/failures.json").read_text())["entries"]
    return next(tuple(entry["codes"]) for entry in registry if entry["name"] == name)


def test_runtime_literal_aliases_match_registry_closure() -> None:
    assert get_args(c7.C7Alternative) == _registry_members(
        "c7.digestion.alternatives"
    )
    assert c7.C7_ALTERNATIVES == get_args(c7.C7Alternative)
    assert get_args(c7.C7InputKind) == _registry_members("c7.ingest.input_kind")
    assert c7.C7_INPUT_KINDS == get_args(c7.C7InputKind)
    assert get_args(c7.C7ContentFormat) == _registry_members(
        "c7.ingest.content_format"
    )
    assert c7.C7_CONTENT_FORMATS == get_args(c7.C7ContentFormat)


def test_runtime_failure_partition_covers_registry_exactly() -> None:
    terminal = _registry_codes("c7.movement.terminal_failure")
    deferred = get_args(c7.C7DeferredFailureCode)
    rejected = get_args(c7.C7RejectedFailureCode)

    assert len(terminal) == len(set(terminal)) == 41
    assert c7.C7_TERMINAL_FAILURE_CODES == terminal
    assert c7.C7_DEFERRED_FAILURE_CODES == deferred
    assert c7.C7_REJECTED_FAILURE_CODES == rejected
    assert not set(deferred) & set(rejected)
    assert set(deferred) | set(rejected) == set(terminal)
    assert set(deferred) == {
        "authority_epoch_revoked",
        "unsafe_pass_through_deferred",
    }


def test_unknown_failure_code_fails_closed_in_constructor() -> None:
    with pytest.raises(
        ValueError, match=r"unsupported C7 rejected failure code: not_registered"
    ):
        c7.C7Rejected(
            failure_code="not_registered",
            reason="unregistered rejection",
            snapshot_ref="snapshot:c7:test",
        )
    with pytest.raises(
        ValueError, match=r"unsupported C7 deferred failure code: not_registered"
    ):
        c7.C7Deferred(
            failure_code="not_registered",
            reason="unregistered deferral",
            snapshot_ref="snapshot:c7:test",
        )


@pytest.mark.parametrize(
    ("dataclass", "code"),
    [
        (c7.C7Rejected, "authority_epoch_revoked"),
        (c7.C7Rejected, "unsafe_pass_through_deferred"),
        (c7.C7Deferred, "malformed_structured_json"),
    ],
)
def test_failure_dispositions_do_not_cross(dataclass: type[object], code: str) -> None:
    with pytest.raises(ValueError, match=r"unsupported C7 .* failure code"):
        dataclass(
            failure_code=code,
            reason="wrong disposition",
            snapshot_ref="snapshot:c7:test",
        )


def test_existing_reject_and_defer_paths_accept_registered_codes() -> None:
    rejected = c7.C7Rejected(
        failure_code="malformed_structured_json",
        reason="registered malformed JSON rejection",
        snapshot_ref="snapshot:c7:reject",
    )
    deferred = c7.C7Deferred(
        failure_code="unsafe_pass_through_deferred",
        reason="registered unsafe pass-through deferral",
        snapshot_ref="snapshot:c7:defer",
    )

    assert rejected.failure_code == "malformed_structured_json"
    assert deferred.failure_code == "unsafe_pass_through_deferred"
    assert rejected.rejected_digest
    assert deferred.deferred_digest


def test_reverse_return_failure_and_reason_remain_open_text() -> None:
    reverse = c7.C7ReverseReturn(
        snapshot_ref="snapshot:c7:reverse",
        snapshot_identity_digest="a" * 64,
        reason="operator supplied explanation",
        failure="not_a_registered_failure_code",
        failure_digest="b" * 64,
    )

    assert reverse.failure == "not_a_registered_failure_code"
    assert reverse.reason == "operator supplied explanation"
    assert "failure" in dataclasses.asdict(reverse)
