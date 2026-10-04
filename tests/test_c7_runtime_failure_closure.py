from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import get_args

import pytest

from app.successor_runtime.capabilities import material_ingest_movements as c7


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
    assert get_args(c7.MaterialDigestionAlternative) == _registry_members(
        "material.digestion.alternatives"
    )
    assert c7.MATERIAL_INGEST_ALTERNATIVES == get_args(c7.MaterialDigestionAlternative)
    assert get_args(c7.MaterialIngestInputKind) == _registry_members("material.ingest.input_kind")
    assert c7.MATERIAL_INGEST_INPUT_KINDS == get_args(c7.MaterialIngestInputKind)
    assert get_args(c7.MaterialIngestContentFormat) == _registry_members(
        "material.ingest.content_format"
    )
    assert c7.MATERIAL_INGEST_CONTENT_FORMATS == get_args(c7.MaterialIngestContentFormat)


def test_runtime_failure_partition_covers_registry_exactly() -> None:
    terminal = tuple(
        code
        for code in _registry_codes("material.ingest.failure")
        if code == code.lower()
    )
    deferred = get_args(c7.MaterialDeferredFailureCode)
    rejected = get_args(c7.MaterialRejectedFailureCode)

    assert len(terminal) == len(set(terminal)) == 41
    assert c7.MATERIAL_INGEST_TERMINAL_FAILURE_CODES == terminal
    assert c7.MATERIAL_DEFERRED_FAILURE_CODES == deferred
    assert c7.MATERIAL_REJECTED_FAILURE_CODES == rejected
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
        c7.MaterialRejected(
            failure_code="not_registered",
            reason="unregistered rejection",
            snapshot_ref="snapshot:c7:test",
        )
    with pytest.raises(
        ValueError, match=r"unsupported C7 deferred failure code: not_registered"
    ):
        c7.MaterialDeferred(
            failure_code="not_registered",
            reason="unregistered deferral",
            snapshot_ref="snapshot:c7:test",
        )


@pytest.mark.parametrize(
    ("dataclass", "code"),
    [
        (c7.MaterialRejected, "authority_epoch_revoked"),
        (c7.MaterialRejected, "unsafe_pass_through_deferred"),
        (c7.MaterialDeferred, "malformed_structured_json"),
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
    rejected = c7.MaterialRejected(
        failure_code="malformed_structured_json",
        reason="registered malformed JSON rejection",
        snapshot_ref="snapshot:c7:reject",
    )
    deferred = c7.MaterialDeferred(
        failure_code="unsafe_pass_through_deferred",
        reason="registered unsafe pass-through deferral",
        snapshot_ref="snapshot:c7:defer",
    )

    assert rejected.failure_code == "malformed_structured_json"
    assert deferred.failure_code == "unsafe_pass_through_deferred"
    assert rejected.rejected_digest
    assert deferred.deferred_digest


def test_reverse_return_failure_and_reason_remain_open_text() -> None:
    reverse = c7.MaterialReverseReturn(
        snapshot_ref="snapshot:c7:reverse",
        snapshot_identity_digest="a" * 64,
        reason="operator supplied explanation",
        failure="not_a_registered_failure_code",
        failure_digest="b" * 64,
    )

    assert reverse.failure == "not_a_registered_failure_code"
    assert reverse.reason == "operator supplied explanation"
    assert "failure" in dataclasses.asdict(reverse)
