"""Bounded real-call parity probes for the C2.3/C6.2 live adapters.

These tests perform one real provider call per adapter and are skipped unless
``MRW_LIVE_PROVIDER_PARITY=1`` and the matching credential is present.  The
default full suite never performs a provider or network call.
"""

from __future__ import annotations

import json
import os
from time import perf_counter

import pytest

from app.successor_runtime.capabilities import agent_core_c6_2 as c6_2
from app.successor_runtime.capabilities import (
    agent_core_c6_2_live_model_port as c6_2_live,
)
from app.successor_runtime.capabilities import source_library_c2_3 as c23
from app.successor_runtime.capabilities import (
    source_library_c2_3_live_provider as c23_live,
)

from .test_p3_c2_3_live_parity import _AUTHORIZATION, _live_request
from .test_p3_c6_2_live_parity import _request as _c6_request

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


def test_real_openai_c6_2_parity_probe(capsys: pytest.CaptureFixture[str]) -> None:
    if not _REAL_MARKER:
        pytest.skip("real provider calls require MRW_LIVE_PROVIDER_PARITY=1")
    api_key = _require_credential(c6_2_live.ENV_VAR_NAME)
    port = c6_2_live.build_openai_live_provider_port()
    assert port is not None
    request = _c6_request()
    started = perf_counter()
    result = c6_2.interpret_model_step(
        request,
        port,
        attempt_id="attempt:c6-2:live:real:001",
    )
    latency_ms = round((perf_counter() - started) * 1000, 3)

    assert result.step is not None
    assert result.step.step_type == "final_answer"
    assert result.receipt.outcome_code == "ProviderStepSucceeded"
    assert result.receipt.provider_calls == 1
    assert port.provider_calls == 1
    assert api_key not in json.dumps(result.receipt.to_plain())
    summary = {
        "provider": "openai",
        "model": port.model,
        "endpoint": port.base_url.rstrip("/") + c6_2_live.CHAT_COMPLETIONS_PATH,
        "outcome_code": result.receipt.outcome_code,
        "readback_status": result.receipt.readback_status,
        "provider_calls": port.provider_calls,
        "receipt_digest": result.receipt.receipt_digest,
        "result_digest": result.result_digest,
        "latency_ms": latency_ms,
    }
    print("LIVE_PARITY_C6_2=" + json.dumps(summary, sort_keys=True))
