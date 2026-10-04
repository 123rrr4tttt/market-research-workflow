"""Bounded real-call parity probe for the C2.3 live adapter.

These tests perform one real provider call per adapter and are skipped unless
``MRW_LIVE_PROVIDER_PARITY=1`` and the matching credential is present.  The
default full suite never performs a provider or network call.
"""

from __future__ import annotations

import json
import os
from time import perf_counter

import pytest

from app.successor_runtime.capabilities import source_provider_acquisition as c23
from app.successor_runtime.capabilities import (
    source_provider_worker as c23_live,
)

from .test_p3_c2_3_live_parity import _AUTHORIZATION, _live_request

_REAL_MARKER = os.getenv("MRW_LIVE_PROVIDER_PARITY") == "1"


def _require_credential(name: str) -> str:
    value = os.getenv(name, "")
    if not value.strip():
        pytest.skip(f"{name} is not configured; no real call performed")
    return value


def test_real_serper_c2_3_parity_probe(capsys: pytest.CaptureFixture[str]) -> None:
    if not _REAL_MARKER:
        pytest.skip("real provider calls require MRW_LIVE_PROVIDER_PARITY=1")
    api_key = _require_credential(c23_live.ENV_VAR_NAME)
    gateway = c23_live.build_serper_live_gateway()
    assert gateway is not None
    request = _live_request()
    started = perf_counter()
    outcome = gateway.execute(request, _AUTHORIZATION)
    latency_ms = round((perf_counter() - started) * 1000, 3)

    assert isinstance(outcome, c23.CompletedProviderEffect)
    assert gateway.provider_calls == [request.request_id]
    assert gateway.effect.real_provider_calls == 1
    plain = outcome.to_plain()
    assert api_key not in json.dumps(plain)
    summary = {
        "provider": "serper",
        "endpoint": c23_live.SERPER_ENDPOINT,
        "outcome_kind": outcome.kind,
        "provider_status": outcome.receipt.provider_status,
        "record_ref_count": len(outcome.record_refs),
        "receipt_digest": outcome.receipt.receipt_digest,
        "outcome_digest": outcome.outcome_digest,
        "provider_calls": len(gateway.provider_calls),
        "real_provider_calls": gateway.effect.real_provider_calls,
        "latency_ms": latency_ms,
    }
    print("LIVE_PARITY_C2_3=" + json.dumps(summary, sort_keys=True))
