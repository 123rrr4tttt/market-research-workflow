from __future__ import annotations

from unittest.mock import patch

from app.services.collect_runtime.adapters.crawler_scrapy import CrawlerScrapyAdapter
from app.services.collect_runtime.contracts import CollectRequest
from app.services.crawlers.base import CrawlerDispatchResult
from app.services.crawlers.durable_effect_bridge import InMemoryCrawlerAttemptStore
from app.services.crawlers.providers.scrapy import ScrapyCrawlerProvider


class _Provider:
    provider_type = "scrapy"

    def __init__(self, statuses: list[str]) -> None:
        self.statuses = iter(statuses)
        self.dispatch_calls = 0
        self.poll_calls = 0

    def dispatch(self, request):  # noqa: ANN001
        self.dispatch_calls += 1
        return CrawlerDispatchResult(
            provider_type="scrapy",
            provider_status="queued",
            provider_job_id="job:remediation",
            attempt_count=1,
        )

    def poll(self, **_kwargs):  # noqa: ANN003
        self.poll_calls += 1
        return {
            "provider_status": next(self.statuses),
            "external_job_id": "job:remediation",
        }


def _request(key: str, *, durable_store=None) -> CollectRequest:
    options = {"spider": "news", "idempotency_key": key}
    if durable_store is not None:
        options["durable_store"] = durable_store
    return CollectRequest(
        project_key="demo",
        options=options,
    )


def test_handoff_states_never_map_to_completed() -> None:
    for provider_status in ("queued", "accepted", "scheduled", "running"):
        provider = _Provider([provider_status])
        with patch("app.services.crawlers.get_provider", return_value=provider):
            result = CrawlerScrapyAdapter().run(_request(f"idem:{provider_status}"))
        assert result.status == "accepted"
        assert result.meta["crawler"]["terminal_readback"]["kind"] == "waiting"


def test_terminal_completion_requires_typed_readback() -> None:
    provider = _Provider(["completed"])
    with patch("app.services.crawlers.get_provider", return_value=provider):
        result = CrawlerScrapyAdapter().run(_request("idem:terminal"))
    assert result.status == "completed"
    readback = result.meta["crawler"]["terminal_readback"]
    assert readback["kind"] == "terminal"
    assert readback["readback"]["terminal_status"] == "COMPLETED"


def test_repeated_attempt_reuses_dispatch_and_reconciles_via_readback() -> None:
    provider = _Provider(["running", "completed"])
    store = InMemoryCrawlerAttemptStore()
    with patch("app.services.crawlers.get_provider", return_value=provider):
        first = CrawlerScrapyAdapter().run(
            _request("idem:reconcile", durable_store=store)
        )
        second = CrawlerScrapyAdapter().run(
            _request("idem:reconcile", durable_store=store)
        )
    assert first.status == "accepted"
    assert second.status == "completed"
    assert provider.dispatch_calls == 1
    assert provider.poll_calls == 2


def test_dispatch_completed_label_without_readback_is_only_acknowledgement() -> None:
    class NoPollProvider:
        provider_type = "scrapy"

        def dispatch(self, request):  # noqa: ANN001
            return CrawlerDispatchResult(
                provider_type="scrapy",
                provider_status="completed",
                provider_job_id="job:no-readback",
                attempt_count=1,
            )

    with patch("app.services.crawlers.get_provider", return_value=NoPollProvider()):
        result = CrawlerScrapyAdapter().run(_request("idem:no-readback"))
    assert result.status == "accepted"
    assert result.meta["crawler"]["terminal_readback"] is None


def test_without_durable_store_metadata_does_not_claim_idempotent_replay() -> None:
    provider = _Provider(["running"])
    with patch("app.services.crawlers.get_provider", return_value=provider):
        result = CrawlerScrapyAdapter().run(_request("idem:not-configured"))
    reconciliation = result.meta["crawler"]["reconciliation"]
    assert reconciliation["durability"] == "not_configured"
    assert reconciliation["derived_as"] == "none"


def test_scrapyd_poll_distinguishes_finished_failure_and_cancellation() -> None:
    provider = object.__new__(ScrapyCrawlerProvider)

    class _Client:
        def list_jobs(self, *, project):  # noqa: ANN001
            return {
                "running": [{"id": "run-1"}],
                "pending": [{"id": "pending-1"}],
                "finished": [
                    {"id": "done-1", "close_reason": "finished"},
                    {"id": "fail-1", "status": "error", "close_reason": "exception"},
                    {"id": "cancel-1", "close_reason": "cancelled"},
                ],
            }

    provider.client = _Client()
    assert provider.poll(external_job_id="done-1", project="demo")["provider_status"] == "completed"
    assert provider.poll(external_job_id="fail-1", project="demo")["provider_status"] == "failed"
    assert provider.poll(external_job_id="cancel-1", project="demo")["provider_status"] == "cancelled"
    assert provider.poll(external_job_id="pending-1", project="demo")["provider_status"] == "queued"
    assert provider.poll(external_job_id="missing-1", project="demo")["provider_status"] == "unavailable"
