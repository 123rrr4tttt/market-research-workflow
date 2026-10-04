from __future__ import annotations

import pytest

from functorial_kit import Failure
from app.services.crawlers.base import CrawlerDispatchRequest, CrawlerDispatchResult
from app.services.crawlers.durable_effect_bridge import (
    DurableCrawlerEffectBridge,
    InMemoryCrawlerAttemptStore,
    RequestDigestMismatch,
)
from app.successor_runtime.capabilities.source_contracts import CancelReceipt


class _Provider:
    provider_type = "scrapy"

    def __init__(self) -> None:
        self.dispatch_calls = 0
        self.poll_calls = 0
        self.cancel_calls = 0

    def dispatch(self, request):  # noqa: ANN001
        self.dispatch_calls += 1
        return CrawlerDispatchResult(
            provider_type="scrapy",
            provider_status="queued",
            provider_job_id="job-1",
            raw={"fixture": True},
        )

    def poll(self, **kwargs):  # noqa: ANN003
        self.poll_calls += 1
        return {"provider_status": "completed", "external_job_id": kwargs["external_job_id"]}

    def cancel(self, **kwargs):  # noqa: ANN003
        self.cancel_calls += 1
        return {"cancel_status": "CANCEL_ACCEPTED"}


class _LabelOnlyProvider:
    provider_type = "scrapy"

    def __init__(self) -> None:
        self.cancel_calls = 0

    def dispatch(self, request):  # noqa: ANN001
        return CrawlerDispatchResult(provider_type="scrapy", provider_status="completed", provider_job_id="job-label")

    def cancel(self, **kwargs):  # noqa: ANN003
        self.cancel_calls += 1
        return {"cancel_status": "CANCEL_ACCEPTED"}


class _PollFailureProvider(_Provider):
    def poll(self, **kwargs):  # noqa: ANN003
        self.poll_calls += 1
        raise RuntimeError("poll unavailable")


def _request() -> CrawlerDispatchRequest:
    return CrawlerDispatchRequest(
        provider="scrapy",
        project="demo",
        spider="news",
        arguments={"q": "ai"},
        idempotency_key="crawler-idem-1",
        attempt_id="crawler-attempt-1",
    )


def test_durable_bridge_replays_across_instances_and_persists_terminal_readback() -> None:
    provider = _Provider()
    store = InMemoryCrawlerAttemptStore()
    first = DurableCrawlerEffectBridge(provider=provider, store=store).dispatch(_request())
    second = DurableCrawlerEffectBridge(provider=provider, store=store).dispatch(_request())

    assert first.provider_job_id == "job-1"
    assert first.terminal_readback.to_plain()["kind"] == "terminal"
    assert second.terminal_readback.to_plain()["kind"] == "terminal"
    assert provider.dispatch_calls == 1


def test_durable_bridge_fails_closed_on_request_digest_drift() -> None:
    provider = _Provider()
    store = InMemoryCrawlerAttemptStore()
    bridge = DurableCrawlerEffectBridge(provider=provider, store=store)
    original = _request()
    assert bridge.dispatch(original).provider_job_id == "job-1"
    changed = CrawlerDispatchRequest(
        provider="scrapy",
        project="demo",
        spider="news",
        arguments={"q": "different"},
        idempotency_key=original.idempotency_key,
        attempt_id=original.attempt_id,
    )
    result = bridge.dispatch(changed)
    assert getattr(result, "context", {}).get("reason_code") == "request_digest_mismatch"
    assert provider.dispatch_calls == 1

    changed_attempt = CrawlerDispatchRequest(
        provider="scrapy",
        project="demo",
        spider="news",
        arguments={"q": "ai"},
        idempotency_key=original.idempotency_key,
        attempt_id="crawler-attempt-2",
    )
    assert isinstance(store.reserve(changed_attempt), Failure)
    attempt_result = bridge.dispatch(changed_attempt)
    assert getattr(attempt_result, "context", {}).get("reason_code") == "request_digest_mismatch"
    assert provider.dispatch_calls == 1

    with pytest.raises(ValueError, match="^durable crawler bridge requires an injected attempt store$"):
        DurableCrawlerEffectBridge(provider=provider, store=None)

    class _LegacyMismatchStore:
        def reserve(self, request):  # noqa: ANN001, ARG002
            raise RequestDigestMismatch("idempotency key is bound to a different attempt id")

    legacy_result = DurableCrawlerEffectBridge(provider=provider, store=_LegacyMismatchStore()).dispatch(_request())
    assert getattr(legacy_result, "context", {}).get("reason_code") == "request_digest_mismatch"


def test_durable_bridge_returns_typed_cancel_receipt() -> None:
    provider = _Provider()
    store = InMemoryCrawlerAttemptStore()
    bridge = DurableCrawlerEffectBridge(provider=provider, store=store)
    bridge.dispatch(_request())
    receipt = bridge.cancel(_request())

    assert isinstance(receipt, CancelReceipt)
    assert receipt.cancel_status == "ALREADY_TERMINAL"
    assert provider.cancel_calls == 0


def test_provider_completed_label_without_typed_readback_is_not_terminal() -> None:
    provider = _LabelOnlyProvider()
    store = InMemoryCrawlerAttemptStore()
    bridge = DurableCrawlerEffectBridge(provider=provider, store=store)
    bridge.dispatch(_request())
    receipt = bridge.cancel(_request())

    assert isinstance(receipt, CancelReceipt)
    assert receipt.cancel_status == "CANCEL_ACCEPTED"
    assert provider.cancel_calls == 1


def test_poll_exception_is_persisted_as_typed_unavailable_readback() -> None:
    provider = _PollFailureProvider()
    store = InMemoryCrawlerAttemptStore()
    bridge = DurableCrawlerEffectBridge(provider=provider, store=store)
    result = bridge.dispatch(_request())

    assert result.terminal_readback.to_plain()["kind"] == "unavailable"
    persisted = store.reserve(_request())
    assert persisted.terminal_readback.to_plain()["kind"] == "unavailable"
