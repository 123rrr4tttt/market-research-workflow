"""Fixture-level parity tests for the live Serper C2.3 adapter."""

from __future__ import annotations

import re
from typing import Any

import pytest

from app.successor_runtime.capabilities import source_library_c2_3 as c23
from app.successor_runtime.capabilities import (
    source_library_c2_3_test_interpreters as c23_fixtures,
)
from app.successor_runtime.capabilities import source_library_c2_shared as shared
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_library_c2_3_live_provider import (
    LIVE_PROVIDER,
    SerperLiveCredentialResolverPort,
    SerperLiveEffectPort,
    SerperLiveProviderEffectGateway,
    SerperLiveReadbackPort,
    SerperOutcomeUnknownError,
    build_serper_live_gateway,
    serper_authority_digest,
)

from .test_p3_c2_3_contracts import _effect_request

pytestmark = pytest.mark.unit

_FAKE_KEY = "fake-serper-key-1234567890"
_AUTHORIZATION = {
    "authority_digest": serper_authority_digest(),
    "grant_scope": "project",
    "provider": LIVE_PROVIDER,
}


def _live_request() -> c23.ProviderEffectRequest:
    plain = _effect_request().to_plain()
    payload = {
        "provider_harvest_mode": "terminal_output_only",
        "query_terms": ["robotics"],
        "limit": 5,
    }
    plain["provider"] = LIVE_PROVIDER
    plain["request_id"] = "c2-2:provider_harvest:harvest-0"
    plain["idempotency_key"] = "idem:serper:live-parity:1"
    plain["effect_payload"] = payload
    plain["effect_payload_digest"] = content_digest({"payload": payload})
    plain["credential_refs"] = [
        {
            "schema_version": shared.CREDENTIAL_REF_SCHEMA,
            "ref": "credential:/project/serper/live",
            "provider": LIVE_PROVIDER,
            "grant_scope": "project",
            "required": True,
        }
    ]
    plain["request_digest"] = ""
    return c23.provider_effect_request_from_plain(plain)


def _gateway(
    transport: Any,
    *,
    key_provider: Any = None,
) -> SerperLiveProviderEffectGateway:
    key = key_provider if key_provider is not None else lambda: _FAKE_KEY
    return SerperLiveProviderEffectGateway(
        credentials=SerperLiveCredentialResolverPort(api_key_provider=key),
        effect=SerperLiveEffectPort(
            api_key_provider=key,
            transport=transport,
            observed_at_provider="2026-09-02T00:00:00.000Z",
        ),
        readback=SerperLiveReadbackPort(),
    )


def _assert_no_secret(value: Any) -> None:
    text = value if isinstance(value, str) else str(value)
    assert _FAKE_KEY not in text
    for line in text.splitlines():
        assert re.fullmatch(r"[A-Za-z0-9+/]{40,}={0,2}", line.strip()) is None


def _organic_fake_transport(status: int = 200, organic: list[Any] | None = None):
    calls: list[dict[str, Any]] = []

    def transport(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> tuple[int, dict[str, Any]]:
        calls.append(
            {
                "url": url,
                "payload": payload,
                "headers": headers,
                "timeout_seconds": timeout_seconds,
            }
        )
        return status, {"organic": organic or []}

    return transport, calls


def test_serper_authority_digest_is_frozen() -> None:
    expected = content_digest(
        {
            "schema": "mrw.successor.source-library.c2-3.live-authority.v1",
            "canonical_owner": "source_library.c2_3.v1",
            "provider": LIVE_PROVIDER,
            "grant_scope": "project",
            "redaction": "credential-ref-only",
        }
    )
    assert serper_authority_digest() == expected


def test_live_gateway_completed_outcome_is_typed_and_redacted() -> None:
    request = _live_request()
    rows = [
        {
            "title": f"Robotics report {index}",
            "link": f"https://example.com/robotics/{index}",
            "snippet": "Synthetic Serper parity row",
        }
        for index in range(7)
    ]
    transport, calls = _organic_fake_transport(organic=rows)
    gateway = _gateway(transport)
    outcome = gateway.execute(request, _AUTHORIZATION)
    assert isinstance(outcome, c23.CompletedProviderEffect)
    assert outcome.receipt.provider == LIVE_PROVIDER
    assert outcome.receipt.provider_status == "COMPLETED"
    assert outcome.receipt.attempt_ref.startswith("provider-attempt:attempt:serper:")
    assert len(outcome.record_refs) == 5
    for ref in outcome.record_refs:
        assert re.fullmatch(r"[0-9a-f]{64}", ref.content_digest) is not None
        assert ref.source_ref.startswith("https://")
    assert gateway.provider_calls == [request.request_id]
    assert gateway.effect.real_provider_calls == 1
    assert len(calls) == 1
    assert calls[0]["url"] == "https://google.serper.dev/search"
    assert calls[0]["payload"]["q"] == "robotics"
    assert calls[0]["headers"]["X-API-KEY"] == _FAKE_KEY
    assert calls[0]["headers"]["Content-Type"] == "application/json"
    assert calls[0]["headers"]["Accept"] == "application/json"
    _assert_no_secret(outcome.to_plain())


def test_http_429_is_typed_rate_limit() -> None:
    request = _live_request()
    transport, _ = _organic_fake_transport(status=429)
    gateway = _gateway(transport)
    outcome = gateway.execute(request, _AUTHORIZATION)
    assert isinstance(outcome, c23.FailedProviderEffect)
    assert outcome.code == "RATE_LIMIT"
    assert outcome.retryable is True
    assert gateway.provider_calls == [request.request_id]
    assert gateway.effect.real_provider_calls == 1


def test_outcome_unknown_keeps_attempt_and_readback_unavailable() -> None:
    request = _live_request()

    def unknown_transport(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> tuple[int, dict[str, Any]]:
        raise SerperOutcomeUnknownError("simulated unknown outcome")

    gateway = _gateway(unknown_transport)
    outcome = gateway.execute(request, _AUTHORIZATION)
    assert isinstance(outcome, c23.OutcomeUnknownProviderEffect)
    assert _FAKE_KEY not in outcome.reason
    attempt_ref = shared.ProviderAttemptRef(
        attempt_id=f"attempt:serper:{request.request_id}",
        request_digest=request.request_digest,
        provider=LIVE_PROVIDER,
    )
    readback = gateway.readback_attempt(attempt_ref, request)
    assert isinstance(readback, shared.ReadbackUnavailable)
    reconciled = c23_fixtures.reconcile_provider_effect(request, attempt_ref, readback)
    assert isinstance(reconciled, shared.OutcomeUnknownProviderEffect)
    assert gateway.provider_calls == [request.request_id]
    assert gateway.effect.real_provider_calls == 1


def test_missing_key_rejects_without_transport() -> None:
    request = _live_request()
    gateway = _gateway(None, key_provider=lambda: None)
    outcome = gateway.execute(request, _AUTHORIZATION)
    assert isinstance(outcome, c23.RejectedProviderEffect)
    assert outcome.code == "MISSING_CREDENTIAL"
    assert gateway.provider_calls == []
    assert gateway.effect.real_provider_calls == 0


def test_authority_digest_mismatch_is_unauthorized() -> None:
    request = _live_request()
    resolver = SerperLiveCredentialResolverPort(api_key_provider=lambda: _FAKE_KEY)
    ref = request.credential_refs[0]
    rejected = resolver.resolve(
        ref,
        {"authority_digest": "0" * 64},
    )
    assert isinstance(rejected, shared.RedactedCredentialRejection)
    assert rejected.code == "UNAUTHORIZED"
    assert rejected.credential_decision_receipt is not None
    assert rejected.credential_decision_receipt.decision == "UNAUTHORIZED"


def test_build_returns_none_without_key_and_gateway_with_key() -> None:
    assert build_serper_live_gateway(api_key_provider=lambda: None) is None
    gateway = build_serper_live_gateway(
        api_key_provider=lambda: _FAKE_KEY,
        transport=lambda *args: (200, {"organic": []}),
    )
    assert isinstance(gateway, SerperLiveProviderEffectGateway)


def test_cancel_and_non_start_are_honest_terminal() -> None:
    request = _live_request()
    attempt_ref = shared.ProviderAttemptRef(
        attempt_id=f"attempt:serper:{request.request_id}",
        request_digest=request.request_digest,
        provider=LIVE_PROVIDER,
    )
    readback = SerperLiveReadbackPort()
    unavailable = readback.readback(attempt_ref, request)
    assert isinstance(unavailable, shared.ReadbackUnavailable)
    assert unavailable.reason == (
        "Serper search API has no authoritative job readback; synchronous terminal only"
    )
    non_start = readback.prove_not_started(attempt_ref, request)
    assert isinstance(non_start, shared.NonStartUnprovable)
    assert non_start.reason == "Serper API exposes no non-start oracle"

    transport, _ = _organic_fake_transport()
    effect = SerperLiveEffectPort(
        api_key_provider=lambda: _FAKE_KEY,
        transport=transport,
    )
    cancel = effect.cancel(attempt_ref, request)
    assert cancel.cancel_status == "ALREADY_TERMINAL"
    assert effect.cancel_calls == [request.request_id]
