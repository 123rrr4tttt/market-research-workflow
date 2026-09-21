"""Focused W03 closure witnesses for the frozen no-throw ownership set."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pytest
from functorial_kit import Failure

from app.services.crawlers import registry, scrapyd_runtime


REPO_ROOT = Path(__file__).resolve().parents[4]
SERVICES_ROOT = REPO_ROOT / "main" / "backend" / "app" / "services"

# This is the frozen W03 ownership set. It deliberately does not scan the
# repository: other packets may change their own core paths concurrently.
W03_NO_THROW_FILES: tuple[str, ...] = (
    "collect_runtime/runtime.py",
    "crawlers/bridge.py",
    "crawlers/providers/scrapy.py",
    "crawlers/registry.py",
    "crawlers/scrapyd_bootstrap.py",
    "crawlers/scrapyd_client.py",
    "crawlers/scrapyd_runtime.py",
    "http/client.py",
    "indexer/policy.py",
    "ingest/canary_metrics_readback.py",
    "ingest/commodity.py",
    "ingest/digestion_scaffold.py",
    "ingest/ecom.py",
    "ingest/frontdoor_ingress.py",
    "ingest/market.py",
    "ingest/market_web.py",
    "ingest/news.py",
    "ingest/policy.py",
    "ingest/raw_import.py",
    "ingest/reports/california.py",
    "ingest/reports/general.py",
    "ingest/social.py",
    "ingest/url_pool.py",
    "job_logger.py",
    "resource_pool/open_source_source_presets.py",
    "resource_pool/search_contract_discovery.py",
    "resource_pool/search_template_service.py",
    "resource_pool/site_entries.py",
    "resource_pool/unified_search.py",
)

_RAISE = re.compile(r"\braise\b")
_BOUNDARY_CLASSES = frozenset(
    {
        "SHELL_BOUNDARY_EXCEPTION",
        "LEGACY_COMPATIBILITY_EXCEPTION",
        "PROGRAMMER_DEFECT",
    }
)


def _raise_windows(source: str) -> Iterable[tuple[int, str]]:
    lines = source.splitlines()
    for index, line in enumerate(lines):
        if _RAISE.search(line):
            # Match the kit scanner's immediate-predecessor window exactly.
            yield index + 1, "\n".join(lines[max(0, index - 2) : index])


def test_w03_no_throw_closure_for_exact_owned_files() -> None:
    assert len(W03_NO_THROW_FILES) == 29
    assert len(set(W03_NO_THROW_FILES)) == 29

    retained: list[tuple[str, int, str]] = []
    for relative_path in W03_NO_THROW_FILES:
        source = (SERVICES_ROOT / relative_path).read_text(encoding="utf-8")
        for line_number, window in _raise_windows(source):
            assert "kit:boundary" in window, (
                f"unclassified W03 raise at {relative_path}:{line_number}"
            )
            retained.append((relative_path, line_number, window))

    assert retained
    for _, _, window in retained:
        assert any(f"class={value}" in window for value in _BOUNDARY_CLASSES)


def test_w03_crawler_registry_empty_key_is_its_own_closed_precondition() -> None:
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


def test_w03_scrapyd_port_laws_live_shape_and_fake_ordered_composition(
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


def test_w03_scrapyd_port_failure_preserved_and_compatibility_lift(
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
