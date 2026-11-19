"""Crawler registration and Scrapyd transport failure contracts."""

from __future__ import annotations

import pytest
from functorial_kit import Failure

from app.services.crawlers import registry, scrapyd_runtime


def test_crawler_registry_empty_key_is_its_own_closed_precondition() -> None:
    failure = registry._registry_precondition_failure(
        "crawler provider key is required",
        operation="register_provider",
        site="app.services.crawlers.registry.register_provider",
    )
    assert failure.family == "crawler.registry.contract_failure"
    assert failure.code == "provider_key_required"

    with pytest.raises(ValueError, match="^crawler provider key is required$"):
        registry.register_provider("  ", object())


class _DeterministicScrapydTransport:
    def __init__(self, health_results: list[bool | Failure]) -> None:
        self._health_results = iter(health_results)
        self.events: list[str] = []

    def health(self, base_url: str, timeout: float = 2.0) -> bool | Failure:
        self.events.append(f"health:{base_url}:{timeout}")
        return next(self._health_results)

    def start_compose(self) -> Failure | None:
        self.events.append("compose")
        return None

    def start_local_daemon(self) -> Failure | None:
        self.events.append("local")
        return None


def test_scrapyd_port_laws_live_shape_and_fake_ordered_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAWLER_LAZY_START_SCRAPYD", "1")
    fake = _DeterministicScrapydTransport([False, False, True])

    result = scrapyd_runtime.try_ensure_scrapyd_ready(
        base_url="http://fake-scrapyd:6800/",
        transport=fake,
    )

    assert isinstance(result, scrapyd_runtime.ResolvedScrapydBaseUrl)
    assert result.base_url == "http://fake-scrapyd:6800"
    assert [event.split(":", 1)[0] for event in fake.events] == [
        "health",
        "health",
        "compose",
        "health",
    ]


def test_scrapyd_port_failure_preserved_and_compatibility_lift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CRAWLER_LAZY_START_SCRAPYD", "0")
    fake = _DeterministicScrapydTransport([False, False])

    failure = scrapyd_runtime.try_ensure_scrapyd_ready(
        base_url="http://fake-scrapyd:6800",
        transport=fake,
    )
    assert isinstance(failure, Failure)
    assert failure.family == "crawler.runtime.failure"
    assert failure.code == "scrapyd_unavailable"
    assert failure.context and failure.context["observed_failure"] is None

    with pytest.raises(ValueError, match="^Scrapyd is unavailable and lazy-start is disabled$"):
        scrapyd_runtime.ensure_scrapyd_ready(
            base_url="http://fake-scrapyd:6800",
            transport=_DeterministicScrapydTransport([False, False]),
        )
