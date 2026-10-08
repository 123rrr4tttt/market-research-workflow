"""Historical exact-byte readback for retired workflow acceptance artifacts."""

from __future__ import annotations

import pytest

from app.successor_runtime.capabilities.workflow_slice_acceptance import (
    HISTORICAL_C1_ACCEPTANCE_SCHEMA,
    read_workflow_acceptance_artifact,
    replay_workflow_acceptance_artifact,
)


def test_historical_acceptance_readback_preserves_bytes_and_rejects_unknown_schema() -> None:
    raw = (
        b'{"schema":"mrw.functorial-successor.c1-slice-acceptance.v1",'
        b'"acceptance_digest":"historical-byte-identity"}'
    )
    historical = read_workflow_acceptance_artifact(
        schema=HISTORICAL_C1_ACCEPTANCE_SCHEMA,
        raw_bytes=raw,
    )
    assert historical.identity.era == "historical_c1"
    assert historical.raw_bytes is raw
    assert replay_workflow_acceptance_artifact(historical) == raw
    assert historical.sha256 == __import__("hashlib").sha256(raw).hexdigest()

    with pytest.raises(ValueError, match="unsupported workflow acceptance schema"):
        read_workflow_acceptance_artifact(
            schema="mrw.workflow.runtime.acceptance.v999",
            raw_bytes=b"{}",
        )
