"""社交平台关键词库管理"""
from __future__ import annotations

import logging
import re
from typing import Iterable, List, Dict, Set

try:  # 避免在未安装 redis 时崩溃
    import redis  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    redis = None

from ...settings.config import settings
from ...services.projects import current_project_key
from ...project_customization import get_project_customization


logger = logging.getLogger(__name__)

_REDIS_CLIENT: "redis.Redis | None" = None
_FALLBACK_STORE: Dict[str, Set[str]] = {}

# Key: social:keywords:{project_key}:{platform} for project pool, social:keywords:shared:{platform} for shared
_SHARED_KEY = "shared"


def _domain_tokens() -> set[str]:
    """Domain tokens from project customization. Empty = no filter (allow all)."""
    try:
        tokens = get_project_customization().get_domain_tokens()
        return set(tokens) if tokens else set()
    except Exception:  # noqa: BLE001
        return set()


def _pool_key(platform: str) -> str:
    """Project-specific or shared pool key."""
    key = (current_project_key() or "").strip().lower() or _SHARED_KEY
    platform_key = platform.strip().lower() or "default"
    return f"social:keywords:{key}:{platform_key}"


def _get_redis_client():
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None or redis is None:
        return _REDIS_CLIENT

    try:
        client = redis.Redis.from_url(  # type: ignore[assignment]
            settings.redis_url,
            decode_responses=True,
        )
        client.ping()
        _REDIS_CLIENT = client
    except Exception as exc:  # noqa: BLE001
        logger.warning("keyword_library: redis unavailable, fallback to in-memory store: %s", exc)
        _REDIS_CLIENT = None
    return _REDIS_CLIENT




_NON_LATIN_PATTERN = re.compile(r"[^a-z0-9\s]")
_MULTI_SPACES_PATTERN = re.compile(r"\s+")


def normalize_keyword(keyword: str) -> str:
    cleaned = keyword.strip().lower()
    cleaned = cleaned.replace("-", " ")
    cleaned = _NON_LATIN_PATTERN.sub(" ", cleaned)
    cleaned = _MULTI_SPACES_PATTERN.sub(" ", cleaned)
    return cleaned.strip()


def _is_domain_keyword(normalized: str) -> bool:
    """True if keyword passes domain filter. Empty tokens = allow all."""
    if not normalized:
        return False
    tokens = _domain_tokens()
    if not tokens:
        return True
    words = normalized.split()
    for token in tokens:
        token_clean = normalize_keyword(token)
        if token_clean in normalized:
            return True
        if token_clean in words:
            return True
    return False


def clean_keywords(keywords: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    cleaned: List[str] = []
    for keyword in keywords:
        normalized = normalize_keyword(keyword)
        if not normalized or normalized in seen:
            continue
        if not _is_domain_keyword(normalized):
            logger.debug("keyword_library: filtered out non-domain keyword '%s' -> '%s'", keyword, normalized)
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def store_keywords(platform: str, keywords: Iterable[str]) -> List[str]:
    cleaned = clean_keywords(keywords)
    if not cleaned:
        return []

    key = _pool_key(platform)
    client = _get_redis_client()
    if client is None:
        storage = _FALLBACK_STORE.setdefault(key, set())
        storage.update(cleaned)
        return list(storage)

    try:
        client.sadd(key, *cleaned)
        stored = client.smembers(key)
        return sorted(stored)
    except Exception as exc:  # noqa: BLE001
        logger.warning("keyword_library: redis write failed, switching to fallback: %s", exc)
        storage = _FALLBACK_STORE.setdefault(key, set())
        storage.update(cleaned)
        return list(storage)


def get_keywords(platform: str) -> List[str]:
    key = _pool_key(platform)
    client = _get_redis_client()
    if client is None:
        storage = _FALLBACK_STORE.get(key, set())
        return sorted(storage)

    try:
        members = client.smembers(key)
        if not members:
            return []
        return sorted(members)
    except Exception as exc:  # noqa: BLE001
        logger.warning("keyword_library: redis read failed, using fallback: %s", exc)
        storage = _FALLBACK_STORE.get(key, set())
        return sorted(storage)


def merge_keywords(platform: str, keywords: Iterable[str]) -> List[str]:
    """存储关键词并返回去重后的全部关键词列表"""
    stored = store_keywords(platform, keywords)
    return stored


