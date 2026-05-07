"""Curated source presets extracted from local open-source reference projects.

These presets are intentionally small and opinionated:
- prefer business / industry media with current RSS / sitemap endpoints
- keep provenance so we can trace back why a source exists
- materialize into existing site_entry records instead of introducing new tables
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OpenSourcePresetEntry:
    name: str
    site_url: str
    entry_type: str
    domain: str
    template: str | None = None
    tags: tuple[str, ...] = ()
    note: str | None = None
    source_project: str | None = None
    source_path: str | None = None
    source_kind: str | None = None


@dataclass(frozen=True)
class OpenSourcePresetPack:
    key: str
    title: str
    description: str
    entries: tuple[OpenSourcePresetEntry, ...]


BUSINESS_MEDIA_FOUNDATION = OpenSourcePresetPack(
    key="business_media_foundation",
    title="Business Media Foundation",
    description=(
        "Business/industry media seeds distilled from local open-source inventories "
        "(fundus publisher sources, RSSHub routes, Common Crawl news seeds)."
    ),
    entries=(
        OpenSourcePresetEntry(
            name="Reuters News Sitemap",
            site_url="https://www.reuters.com/arc/outboundfeeds/news-sitemap-index/?outputType=xml",
            entry_type="sitemap",
            domain="www.reuters.com",
            tags=("curated", "business_news", "wire", "sitemap", "newsmap"),
            note="Fundus US publisher sources define Reuters news sitemap as a primary source.",
            source_project="fundus",
            source_path="src/fundus/publishers/us/__init__.py",
            source_kind="newsmap",
        ),
        OpenSourcePresetEntry(
            name="CNBC News Sitemap",
            site_url="https://www.cnbc.com/sitemap_news.xml",
            entry_type="sitemap",
            domain="www.cnbc.com",
            tags=("curated", "business_news", "markets_media", "sitemap", "newsmap"),
            note="Fundus US publisher sources define CNBC news sitemap as a primary source.",
            source_project="fundus",
            source_path="src/fundus/publishers/us/__init__.py",
            source_kind="newsmap",
        ),
        OpenSourcePresetEntry(
            name="CNBC All Sitemap",
            site_url="https://www.cnbc.com/sitemapAll.xml",
            entry_type="sitemap",
            domain="www.cnbc.com",
            tags=("curated", "business_news", "markets_media", "sitemap"),
            note="Fundus US publisher sources include the broader CNBC sitemap.",
            source_project="fundus",
            source_path="src/fundus/publishers/us/__init__.py",
            source_kind="sitemap",
        ),
        OpenSourcePresetEntry(
            name="Business Insider News Sitemap",
            site_url="https://www.businessinsider.com/sitemap/google-news.xml",
            entry_type="sitemap",
            domain="www.businessinsider.com",
            tags=("curated", "business_news", "tech_media", "sitemap", "newsmap"),
            note="Fundus US publisher sources define BI google-news sitemap as a source.",
            source_project="fundus",
            source_path="src/fundus/publishers/us/__init__.py",
            source_kind="newsmap",
        ),
        OpenSourcePresetEntry(
            name="TechCrunch News Sitemap",
            site_url="https://techcrunch.com/news-sitemap.xml",
            entry_type="sitemap",
            domain="techcrunch.com",
            tags=("curated", "business_news", "tech_media", "sitemap", "newsmap"),
            note="Fundus US publisher sources include TechCrunch news sitemap.",
            source_project="fundus",
            source_path="src/fundus/publishers/us/__init__.py",
            source_kind="newsmap",
        ),
        OpenSourcePresetEntry(
            name="Wired RSS",
            site_url="https://www.wired.com/feed/rss",
            entry_type="rss",
            domain="www.wired.com",
            tags=("curated", "business_news", "tech_media", "rss"),
            note="Fundus US publisher sources include Wired RSS feed.",
            source_project="fundus",
            source_path="src/fundus/publishers/us/__init__.py",
            source_kind="rss",
        ),
        OpenSourcePresetEntry(
            name="AP News Content News Sitemap",
            site_url="https://apnews.com/news-sitemap-content.xml",
            entry_type="sitemap",
            domain="apnews.com",
            tags=("curated", "business_news", "wire", "sitemap", "newsmap"),
            note="Fundus US publisher sources include AP content news sitemap.",
            source_project="fundus",
            source_path="src/fundus/publishers/us/__init__.py",
            source_kind="newsmap",
        ),
        OpenSourcePresetEntry(
            name="The Guardian World RSS",
            site_url="https://www.theguardian.com/world/rss",
            entry_type="rss",
            domain="www.theguardian.com",
            tags=("curated", "business_news", "global_news", "rss"),
            note="Common Crawl news seeds include Guardian world RSS.",
            source_project="news-crawl",
            source_path="seeds/feeds.txt",
            source_kind="rss",
        ),
        OpenSourcePresetEntry(
            name="The Guardian News Sitemap",
            site_url="https://www.theguardian.com/sitemaps/news.xml",
            entry_type="sitemap",
            domain="www.theguardian.com",
            tags=("curated", "business_news", "global_news", "sitemap", "newsmap"),
            note="Common Crawl news seeds include Guardian news sitemap.",
            source_project="news-crawl",
            source_path="seeds/feeds.txt",
            source_kind="newsmap",
        ),
        OpenSourcePresetEntry(
            name="BBC News Sitemap",
            site_url="https://www.bbc.com/sitemaps/https-index-com-news.xml",
            entry_type="sitemap",
            domain="www.bbc.com",
            tags=("curated", "business_news", "global_news", "sitemap", "newsmap"),
            note="Common Crawl news seeds include BBC news sitemap.",
            source_project="news-crawl",
            source_path="seeds/feeds.txt",
            source_kind="newsmap",
        ),
    ),
)


TECH_BUSINESS_SEARCH_MEDIA = OpenSourcePresetPack(
    key="tech_business_search_media",
    title="Tech Business Search Media",
    description="Search-template business/tech media sources validated in the current stack.",
    entries=(
        OpenSourcePresetEntry(
            name="VentureBeat Search",
            site_url="https://venturebeat.com/?s={{q}}",
            entry_type="search_template",
            domain="venturebeat.com",
            template="https://venturebeat.com/?s={{q}}",
            tags=("curated", "business_news", "ai_media", "search_template"),
            note="Validated manually in current search_template pipeline.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="search_template",
        ),
        OpenSourcePresetEntry(
            name="PYMNTS Search",
            site_url="https://www.pymnts.com/?s={{q}}",
            entry_type="search_template",
            domain="www.pymnts.com",
            template="https://www.pymnts.com/?s={{q}}",
            tags=("curated", "business_news", "fintech_media", "search_template"),
            note="Validated manually in current search_template pipeline.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="search_template",
        ),
        OpenSourcePresetEntry(
            name="Commercial Observer Search",
            site_url="https://commercialobserver.com/?s={{q}}",
            entry_type="search_template",
            domain="commercialobserver.com",
            template="https://commercialobserver.com/?s={{q}}",
            tags=("curated", "business_news", "capital_markets_media", "search_template"),
            note="Validated manually in current search_template pipeline.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="search_template",
        ),
        OpenSourcePresetEntry(
            name="Investopedia Search",
            site_url="https://www.investopedia.com/search?q={{q}}",
            entry_type="search_template",
            domain="www.investopedia.com",
            template="https://www.investopedia.com/search?q={{q}}",
            tags=("curated", "business_news", "markets_media", "search_template"),
            note="Validated manually in current search_template pipeline.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="search_template",
        ),
    ),
)


KEYWORD_RESEARCH_FOUNDATION = OpenSourcePresetPack(
    key="keyword_research_foundation",
    title="Keyword Research Foundation",
    description=(
        "High-recall sources for user keyword research. Mixes query-capable search templates "
        "with RSS feeds so a plain keyword set can produce candidate URLs quickly."
    ),
    entries=(
        OpenSourcePresetEntry(
            name="TechCrunch Search",
            site_url="https://techcrunch.com/?s={{q}}",
            entry_type="search_template",
            domain="techcrunch.com",
            template="https://techcrunch.com/?s={{q}}",
            tags=("curated", "keyword_research", "tech_media", "startup", "search_template"),
            note="Query-capable media source for startup and technology market research.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="search_template",
        ),
        OpenSourcePresetEntry(
            name="VentureBeat Search",
            site_url="https://venturebeat.com/?s={{q}}",
            entry_type="search_template",
            domain="venturebeat.com",
            template="https://venturebeat.com/?s={{q}}",
            tags=("curated", "keyword_research", "ai_media", "search_template"),
            note="Query-capable media source for AI and enterprise technology research.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="search_template",
        ),
        OpenSourcePresetEntry(
            name="The Verge Search",
            site_url="https://www.theverge.com/search?q={{q}}",
            entry_type="search_template",
            domain="www.theverge.com",
            template="https://www.theverge.com/search?q={{q}}",
            tags=("curated", "keyword_research", "consumer_tech", "search_template"),
            note="Query-capable media source for consumer technology and product signals.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="search_template",
        ),
        OpenSourcePresetEntry(
            name="Ars Technica Search",
            site_url="https://arstechnica.com/search/?query={{q}}",
            entry_type="search_template",
            domain="arstechnica.com",
            template="https://arstechnica.com/search/?query={{q}}",
            tags=("curated", "keyword_research", "technology", "search_template"),
            note="Query-capable media source for technical and policy-oriented technology coverage.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="search_template",
        ),
        OpenSourcePresetEntry(
            name="PYMNTS Search",
            site_url="https://www.pymnts.com/?s={{q}}",
            entry_type="search_template",
            domain="www.pymnts.com",
            template="https://www.pymnts.com/?s={{q}}",
            tags=("curated", "keyword_research", "fintech_media", "payments", "search_template"),
            note="Query-capable media source for payments, fintech, and commerce research.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="search_template",
        ),
        OpenSourcePresetEntry(
            name="Investopedia Search",
            site_url="https://www.investopedia.com/search?q={{q}}",
            entry_type="search_template",
            domain="www.investopedia.com",
            template="https://www.investopedia.com/search?q={{q}}",
            tags=("curated", "keyword_research", "markets_media", "finance", "search_template"),
            note="Query-capable source for financial definitions, market explainers, and investing topics.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="search_template",
        ),
        OpenSourcePresetEntry(
            name="Wired RSS",
            site_url="https://www.wired.com/feed/rss",
            entry_type="rss",
            domain="www.wired.com",
            tags=("curated", "keyword_research", "tech_media", "rss"),
            note="RSS source for recent technology stories, filtered by keyword terms.",
            source_project="fundus",
            source_path="src/fundus/publishers/us/__init__.py",
            source_kind="rss",
        ),
        OpenSourcePresetEntry(
            name="MIT Technology Review RSS",
            site_url="https://www.technologyreview.com/feed/",
            entry_type="rss",
            domain="www.technologyreview.com",
            tags=("curated", "keyword_research", "technology", "rss"),
            note="RSS source for technology trend and research coverage, filtered by keyword terms.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="rss",
        ),
        OpenSourcePresetEntry(
            name="The Verge RSS",
            site_url="https://www.theverge.com/rss/index.xml",
            entry_type="rss",
            domain="www.theverge.com",
            tags=("curated", "keyword_research", "consumer_tech", "rss"),
            note="RSS source for recent consumer technology stories, filtered by keyword terms.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="rss",
        ),
        OpenSourcePresetEntry(
            name="TechCrunch RSS",
            site_url="https://techcrunch.com/feed/",
            entry_type="rss",
            domain="techcrunch.com",
            tags=("curated", "keyword_research", "startup", "rss"),
            note="RSS source for recent startup and technology stories, filtered by keyword terms.",
            source_project="manual+open-source-guided",
            source_path="local_validation",
            source_kind="rss",
        ),
    ),
)


OPEN_SOURCE_PRESET_PACKS: dict[str, OpenSourcePresetPack] = {
    BUSINESS_MEDIA_FOUNDATION.key: BUSINESS_MEDIA_FOUNDATION,
    TECH_BUSINESS_SEARCH_MEDIA.key: TECH_BUSINESS_SEARCH_MEDIA,
    KEYWORD_RESEARCH_FOUNDATION.key: KEYWORD_RESEARCH_FOUNDATION,
}


def list_open_source_preset_packs() -> list[dict[str, Any]]:
    return [
        {
            "key": pack.key,
            "title": pack.title,
            "description": pack.description,
            "entry_count": len(pack.entries),
        }
        for pack in OPEN_SOURCE_PRESET_PACKS.values()
    ]


def get_open_source_preset_pack(pack_key: str) -> OpenSourcePresetPack:
    key = str(pack_key or "").strip()
    if key not in OPEN_SOURCE_PRESET_PACKS:
        raise ValueError(f"unknown open-source preset pack: {pack_key}")
    return OPEN_SOURCE_PRESET_PACKS[key]


def list_validated_search_template_site_urls() -> list[str]:
    pack = get_open_source_preset_pack(TECH_BUSINESS_SEARCH_MEDIA.key)
    return [str(entry.site_url or "").strip() for entry in pack.entries if str(entry.site_url or "").strip()]
