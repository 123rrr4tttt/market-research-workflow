"""平台适配器模块"""
from __future__ import annotations

from typing import Dict, Type, Protocol, Optional
from ..models import NormalizedSocialPost
from ....models.entities import Document


class PlatformAdapter(Protocol):
    """平台适配器协议"""
    def to_normalized(self, doc: Document) -> Optional[NormalizedSocialPost]:
        """将平台特定的文档转换为规范化格式"""
        ...


# 适配器注册表
_adapters: Dict[str, Type[PlatformAdapter]] = {}


def register_adapter(platform: str, adapter_class: Type[PlatformAdapter]):
    """注册平台适配器"""
    _adapters[platform] = adapter_class


def get_adapter(platform: str) -> Optional[Type[PlatformAdapter]]:
    """获取平台适配器"""
    return _adapters.get(platform)


def normalize_document(doc: Document) -> Optional[NormalizedSocialPost]:
    """将文档转换为规范化格式（自动选择适配器）"""
    if not doc.extracted_data:
        return None

    platform = doc.extracted_data.get("platform", "").lower()
    adapter_class = get_adapter(platform) if platform else None

    if adapter_class:
        adapter = adapter_class()
        return adapter.to_normalized(doc)

    # Fallback: generic adapter for docs with sentiment but no platform-specific adapter
    # (e.g. social_sentiment from news, market_web, or platform=google_news)
    from .generic import GenericSocialAdapter
    return GenericSocialAdapter().to_normalized(doc)


# 注册平台适配器
from .reddit import RedditAdapter
from .generic import GenericSocialAdapter

register_adapter("reddit", RedditAdapter)
register_adapter("generic", GenericSocialAdapter)

