"""Lexical search suggestions for social platforms and subreddit discovery."""
from __future__ import annotations

import re

_BILINGUAL_LANG_MODES = {"bi", "bilingual", "zh-en", "zh_en", "both", "multi", "multilingual"}


def _is_bilingual_mode(language: str) -> bool:
    return (language or "").strip().lower() in _BILINGUAL_LANG_MODES


def dedup_keywords(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        kw = str(raw or "").strip()
        if not kw or kw in seen:
            continue
        seen.add(kw)
        out.append(kw)
    return out


def generate_keywords(topic: str, language: str = "zh") -> list[str]:
    """Expand a topic into bounded lexical search terms without model inference."""
    topic = topic.strip()
    if not topic:
        return []
    if _is_bilingual_mode(language):
        return dedup_keywords(generate_keywords(topic, "zh") + generate_keywords(topic, "en"))
    suffixes = (
        ("regulation", "market", "sales report", "supply chain")
        if language.strip().lower().startswith("en")
        else ("政策", "市场", "销售 报告", "产业链")
    )
    return [topic, *(f"{topic} {suffix}" for suffix in suffixes)]


def generate_topic_keywords(
    topic: str,
    *,
    topic_focus: str,
    language: str = "zh",
    base_keywords: list[str] | None = None,
) -> dict[str, list[str]]:
    """Expand collection terms with a bounded list of focus-specific hints."""
    focus = topic_focus.strip().lower()
    zh_suffixes = {
        "company": ["公司", "企业", "品牌", "合作", "供应链", "渠道"],
        "product": ["产品", "型号", "品类", "参数", "发布", "应用场景"],
        "operation": ["经营", "商业模式", "运营模式", "电商", "平台", "渠道策略"],
    }
    en_suffixes = {
        "company": ["company", "brand", "partnership", "supply chain", "channel"],
        "product": ["product", "model", "category", "specs", "launch", "use case"],
        "operation": ["operation", "business model", "ecommerce", "platform", "channel strategy"],
    }
    zh = zh_suffixes.get(focus, [])
    en = en_suffixes.get(focus, [])
    if _is_bilingual_mode(language):
        # Interleave languages so the query cap cannot drop either language.
        suffixes = [suffix for pair in zip(zh[:4], en[:4]) for suffix in pair]
        hints = [*zh, *en]
    else:
        hints = zh if language.strip().lower().startswith("zh") else en
        suffixes = hints[:4]
    base = dedup_keywords(base_keywords or []) or dedup_keywords([topic])
    terms = dedup_keywords([f"{kw} {suffix}" for kw in base[:4] for suffix in suffixes])
    return {"search_keywords": terms[:12], "topic_hints": hints}


def generate_social_keywords(
    topic: str,
    language: str = "zh",
    platform: str | None = None,
    base_keywords: list[str] | None = None,
) -> dict[str, list[str]]:
    """Suggest terms only; the collection operation owns keyword-library writes."""
    platform = (platform or "").strip().lower()
    seed = dedup_keywords([topic, *(base_keywords or [])])
    terms = seed[:4]
    if seed:
        primary = seed[0]
        bilingual = _is_bilingual_mode(language)
        english = language.strip().lower().startswith("en")
        if bilingual or not english:
            terms += [f"{primary} {suffix}" for suffix in ("讨论", "社区", "体验")]
        if bilingual or english:
            terms += [f"{primary} {suffix}" for suffix in ("discussion", "community", "experience")]
        if platform == "reddit":
            terms.append(f"{primary} reddit")
    return {
        "search_keywords": dedup_keywords(terms),
        "subreddit_keywords": generate_subreddit_keywords(topic, base_keywords=base_keywords),
    }


def generate_subreddit_keywords(topic: str, *, base_keywords: list[str] | None = None) -> list[str]:
    """Normalize provided search terms for Reddit discovery, without translating them."""

    def normalize(value: str) -> str:
        return re.sub(r"[^\w]", "", re.sub(r"[\s-]+", "_", value.strip().lower()))

    primary = normalize(topic)
    terms = [primary, *(normalize(value) for value in (base_keywords or []))]
    if primary.endswith("s"):
        terms.append(primary[:-1])
    elif primary:
        terms.append(primary + "s")
    return dedup_keywords(terms)[:10]
