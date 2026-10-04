"""Sibling legacy adapter for C2.3 provider effects (fixture replay only).

The legacy provider cluster is not called: ``runner.run_channel`` and every
adapter stay untouched.  The adapter replays frozen donor fixture receipts and
handoffs from an in-code registry, and it explicitly records that zero live
provider, credential, network, filesystem or database calls occurred.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_library_c2_3 import (
    AcceptedProviderEffect,
    CapturedSourceRecordRef,
    CompletedProviderEffect,
    FailedProviderEffect,
    OutcomeUnknownProviderEffect,
    ProviderAttemptRef,
    ProviderEffectOutcome,
    ProviderEffectRequest,
    ProviderReceipt,
)

__all__ = [
    "LegacyC2_3FixtureTrace",
    "LegacySourceLibraryC2_3Adapter",
    "legacy_fixture_outcome",
]


LEGACY_C2_3_INTERPRETER_ID = "legacy.source_library.c2_3.provider_effect.v1"
DONOR_FIXTURE_OBSERVED_AT = "2030-09-01T08:00:00Z"


@dataclass(frozen=True, slots=True)
class LegacyC2_3FixtureTrace:
    trace_id: str
    fixture_id: str
    outcome: dict[str, Any]
    provider_calls: tuple[str, ...]
    handoff: dict[str, Any]
    trace_digest: str = ""

    def __post_init__(self) -> None:
        if self.trace_digest == "":
            object.__setattr__(
                self,
                "trace_digest",
                content_digest(
                    {
                        "schema": "mrw.successor.source-library.c2-3.legacy-trace.v1",
                        "trace_id": self.trace_id,
                        "fixture_id": self.fixture_id,
                        "outcome": self.outcome,
                        "provider_calls": list(self.provider_calls),
                        "handoff": self.handoff,
                    }
                ),
            )


def legacy_fixture_outcome(
    request: ProviderEffectRequest,
    *,
    fixture_id: str,
) -> ProviderEffectOutcome:
    """Deterministic donor fixture outcome; never calls the live runner."""

    attempt = ProviderAttemptRef(
        attempt_id=f"legacy-attempt:{fixture_id}:{request.request_id}",
        request_digest=request.request_digest,
        provider=request.provider,
        epoch=1,
    )
    receipt = ProviderReceipt(
        receipt_id=f"legacy-receipt:{fixture_id}:{request.request_id}",
        provider=request.provider,
        provider_job_id=f"legacy-job:{fixture_id}",
        provider_status="COMPLETED",
        attempt_ref=attempt.as_ref_string(),
        observed_at=DONOR_FIXTURE_OBSERVED_AT,
    )
    if fixture_id == "provider_harvest_accepted":
        return AcceptedProviderEffect(receipt=receipt)
    if fixture_id == "transport_failure":
        return FailedProviderEffect(
            code="TRANSPORT",
            message="donor fixture transport failure",
            retryable=True,
        )
    if fixture_id == "outcome_unknown":
        return OutcomeUnknownProviderEffect(
            attempt_ref=attempt.as_ref_string(),
            reason="donor fixture crashed after dispatch before receipt",
        )
    record = CapturedSourceRecordRef(
        record_id=f"record:{fixture_id}:1",
        content_ref=f"content:{fixture_id}:1",
        content_digest=content_digest({"fixture": fixture_id}),
        source_ref=f"source:{request.channel_key}",
    )
    return CompletedProviderEffect(
        receipt=receipt,
        record_refs=(record,),
        staged_artifact_refs=(),
    )


class LegacySourceLibraryC2_3Adapter:
    """Read-only donor fixture/receipt replay for C2.3 parity evidence."""

    interpreter_id = LEGACY_C2_3_INTERPRETER_ID

    def __init__(self) -> None:
        self.provider_calls: list[str] = []
        self.traces: list[LegacyC2_3FixtureTrace] = []

    def replay(
        self,
        request: ProviderEffectRequest,
        *,
        fixture_id: str,
        trace_id: str | None = None,
    ) -> LegacyC2_3FixtureTrace:
        outcome = legacy_fixture_outcome(request, fixture_id=fixture_id)
        receipt = getattr(outcome, "receipt", None)
        handoff = {
            "contract_version": "source_library.provider_handoff.v1",
            "handoff_kind": "fixture_receipt",
            "channel_key": request.channel_key,
            "provider": request.provider,
            "provider_type": "fixture",
            "downstream_handoff": "ingest",
            "execution_layer": "terminal_output_only"
            if request.terminal_output_only
            else "collect",
            "prefer_crawler_first": False,
            "force_url_routing_flow": False,
            "provider_job_id": (
                receipt.provider_job_id if receipt is not None else None
            ),
            "provider_status": (
                receipt.provider_status if receipt is not None else "FIXTURE"
            ),
            "receipt_digest": (
                receipt.receipt_digest if receipt is not None else content_digest({})
            ),
        }
        trace = LegacyC2_3FixtureTrace(
            trace_id=trace_id or f"legacy.c2_3.{fixture_id}",
            fixture_id=fixture_id,
            outcome=outcome.to_plain(),
            provider_calls=tuple(self.provider_calls),
            handoff=handoff,
        )
        self.traces.append(trace)
        return trace
