"""Canonical HTTP request contract for raw Material imports."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RawImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    url: str | None = None
    uri: str | None = None
    uris: list[str] | None = None
    text: str | None = Field(
        default=None,
        description="粘贴文本/文件文本内容；可留空并用 url/uri 自动抓取",
    )
    summary: str | None = None
    material_type: str | None = None
    publish_date: str | None = None
    state: str | None = None


class RawImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RawImportItem] = Field(default_factory=list, min_length=1, max_length=200)
    source_name: str = Field(default="raw_import", min_length=1, max_length=255)
    source_kind: str = Field(default="manual")
    infer_from_links: bool = Field(default=True, description="从文本中识别首个 URL 作为 uri")
    enable_extraction: bool = Field(default=True, description="是否直接进入结构化提取流程")
    default_material_type: Literal[
        "market_info",
        "policy",
        "social_sentiment",
        "news",
        "raw_note",
    ] = "raw_note"
    extraction_mode: Literal[
        "auto",
        "market",
        "policy",
        "social",
        "comprehensive",
    ] = "auto"
    overwrite_on_uri: bool = Field(
        default=False,
        description="相同 URI 是否覆盖已存在文档内容",
    )
    chunk_size: int = Field(default=2800, ge=500, le=8000, description="大文本分片长度（字符）")
    chunk_overlap: int = Field(default=200, ge=0, le=1000, description="分片重叠长度（字符）")
    max_chunks: int = Field(default=8, ge=1, le=50, description="单条文本最多分片数")
    fetch_url_when_text_empty: bool = Field(
        default=True,
        description="text 为空时是否尝试抓取 url/uri 正文",
    )
    fetch_url_also_when_text_present: bool = Field(
        default=True,
        description="text 不为空时是否仍抓取 url/uri 正文并合并",
    )
    url_fetch_timeout: float = Field(
        default=8.0,
        ge=1.0,
        le=30.0,
        description="URL 抓取超时时间（秒）",
    )
    url_to_market: bool = Field(
        default=True,
        description="URL 抓取成功且未显式指定 material_type 时，按 market_info 入库",
    )
    async_mode: bool = Field(default=False, description="是否走 Celery 异步任务")


__all__ = ["RawImportItem", "RawImportRequest"]
