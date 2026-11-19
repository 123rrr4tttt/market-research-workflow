from __future__ import annotations

import pytest

from app.services.resource_pool.auto_classify import _recommendation_from_llm_row
from app.services.resource_pool.site_entry_discovery import _best_effort_base_urls
from app.services.resource_pool.site_search_policy import resolve_site_search_policy
from app.services.resource_pool.url_utils import domain_from_url, normalize_domain
from app.services.source_library import url_router


@pytest.mark.parametrize(
    ("url", "domain"),
    [
        ("https://wow.example/search", "wow.example"),
        ("https://www.Wow.example/search", "wow.example"),
        ("https://www.wow.example:8443/search", "wow.example:8443"),
        ("/search", None),
        ("https://[", None),
    ],
)
def test_domain_normalization_only_removes_literal_www_prefix(url: str, domain: str | None) -> None:
    assert domain_from_url(url) == domain


@pytest.mark.parametrize("domain", ["wow.example", "www.wow.example"])
def test_source_library_matches_rules_for_domains_starting_with_w(
    monkeypatch: pytest.MonkeyPatch, domain: str,
) -> None:
    monkeypatch.setattr(
        url_router,
        "get_config",
        lambda *_: {"payload": {"rules": [
            {"pattern": "o.example", "channel_key": "incorrect", "path_prefix": "/other/"},
            {"pattern": "wow.", "channel_key": "configured"},
        ]}},
    )
    assert url_router.resolve_channel_for_url(f"https://{domain}/report", "project") == "configured"


def test_site_search_policy_still_matches_www_alias() -> None:
    known_url = "https://theverge.com"
    assert resolve_site_search_policy(known_url).category == "deprioritized"
    assert resolve_site_search_policy("https://www.theverge.com") == resolve_site_search_policy(known_url)


@pytest.mark.parametrize(
    ("site_url", "template", "accepted"),
    [
        ("https://wow.example", "https://www.wow.example/?q={{q}}", True),
        ("https://wow.example", "https://ow.example/?q={{q}}", False),
        ("https://wow.example:8443", "https://wow.example/?q={{q}}", False),
        ("https://wow.example:8443", "https://www.wow.example:8443/?q={{q}}", True),
        ("/invalid-site", "https://wow.example/?q={{q}}", False),
        ("https://wow.example", "/search?q={{q}}", False),
    ],
)
def test_site_classifier_compares_both_domains_consistently(
    site_url: str, template: str, accepted: bool,
) -> None:
    result = _recommendation_from_llm_row(
        {
            "entry_type": "search_template",
            "channel_key": "generic_web.search_template",
            "template": template,
        },
        site_url=site_url,
    )
    assert (result is not None) is accepted
    if result is not None:
        assert result.template == template


@pytest.mark.parametrize("domain", ["wow.example", "web.example", "www.wow.example"])
def test_domain_normalization_does_not_strip_initial_w_or_e(domain: str) -> None:
    expected = domain.removeprefix("www.")
    assert normalize_domain(domain) == expected
    assert _best_effort_base_urls(domain) == [f"https://{expected}/", f"http://{expected}/"]
