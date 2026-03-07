from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WritingRequestContext(BaseModel):
    project_key: str | None = Field(default=None, max_length=64)
    trace_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @field_validator("project_key")
    @classmethod
    def _project_key_must_not_be_blank(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None


class KeywordCardRequest(WritingRequestContext):
    query: str = Field(..., min_length=1, max_length=200)
    selection_hash: str | None = Field(default=None, max_length=64)
    limit: int = Field(default=10, ge=1, le=50)
    sources: list[Literal["document", "resource", "graph"]] = Field(default_factory=list)
    timeout_ms: int | None = Field(default=None, ge=50, le=30000)

    @field_validator("query")
    @classmethod
    def _query_must_not_be_blank(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("query is required")
        return normalized


class KeywordCardItem(BaseModel):
    card_id: str = Field(..., min_length=1, max_length=128)
    source_type: Literal["document", "resource", "graph"]
    title: str = Field(..., min_length=1, max_length=300)
    snippet: str = Field(default="", max_length=2000)
    url: str | None = Field(default=None, max_length=2048)
    score: float = Field(default=0.0, ge=0.0)
    publisher: str | None = Field(default=None, max_length=255)
    published_at: str | None = Field(default=None, max_length=64)
    retrieved_at: str | None = Field(default=None, max_length=64)
    evidence: str | None = Field(default=None, max_length=2000)
    relevance_tags: list[str] = Field(default_factory=list)
    credibility: float | None = Field(default=None, ge=0.0, le=1.0)
    quick_actions: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class KeywordCardListResponse(BaseModel):
    cards: list[KeywordCardItem] = Field(default_factory=list)
    selection_hash: str = Field(..., min_length=1, max_length=64)
    suggested_queries: list[str] = Field(default_factory=list)
    search_backends_used: list[str] = Field(default_factory=list)
    source_count: dict[str, int] = Field(default_factory=dict)
    dedupe_count: int = Field(default=0, ge=0)
    score_snapshot: dict[str, Any] = Field(default_factory=dict)
    cache_hit: bool = False
    cache_ttl_ms: int | None = Field(default=None, ge=0)


class KeywordCardPreviewRequest(WritingRequestContext):
    card_id: str = Field(..., min_length=1, max_length=128)
    query: str | None = Field(default=None, max_length=200)


class KeywordCardPreviewResponse(BaseModel):
    card_id: str
    title: str
    url: str | None = None
    publisher: str | None = None
    snippet: str = ""
    score: float = 0.0
    source_type: Literal["document", "resource", "graph"]
    quick_actions: list[str] = Field(default_factory=list)


class KeywordCardDetailRequest(WritingRequestContext):
    card_id: str = Field(..., min_length=1, max_length=128)
    include_provenance: bool = True
    max_provenance_items: int = Field(default=20, ge=1, le=100)


class KeywordCardDetailResponse(BaseModel):
    card_id: str
    title: str
    url: str | None = None
    score: float = 0.0
    evidence: str | None = None
    publisher: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None
    normalized_query: str | None = None
    dedupe_trace: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    selection_matches: dict[str, Any] = Field(default_factory=dict)
    source_type: Literal["document", "resource", "graph"]


class SuggestRequest(WritingRequestContext):
    query: str = Field(..., min_length=1, max_length=200)
    mode: Literal["keyword", "template", "material", "command"] = "keyword"
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("query is required")
        return normalized


class SuggestItem(BaseModel):
    kind: Literal["keyword", "template", "material", "command"]
    id: str = Field(..., min_length=1, max_length=128)
    label: str = Field(..., min_length=1, max_length=300)
    snippet: str | None = Field(default=None, max_length=500)
    score: float | None = Field(default=None, ge=0.0)
    extra: dict[str, Any] = Field(default_factory=dict)


class SuggestResponse(BaseModel):
    items: list[SuggestItem] = Field(default_factory=list)
    suggest_type: str = Field(..., min_length=1, max_length=64)
    query: str = Field(..., min_length=1, max_length=200)
    source: list[str] = Field(default_factory=list)
    query_rewrite: str = Field(default="", max_length=200)
    selection_hash: str | None = Field(default=None, max_length=64)


class TemplateValidateRequest(WritingRequestContext):
    template_key: str | None = Field(default=None, max_length=128)
    template_content: str | None = None
    template_id: str | None = Field(default=None, max_length=128)
    sample_payload: dict[str, Any] = Field(default_factory=dict)
    strict: bool = False


class TemplateValidateResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    normalized_template: dict[str, Any] = Field(default_factory=dict)
    rules: dict[str, Any] = Field(default_factory=dict)
    observability: dict[str, Any] = Field(default_factory=dict)


class LlmActionRequest(WritingRequestContext):
    action_id: Literal["outline_generate", "section_expand", "selection_rewrite", "evidence_summary"]
    template_key: str | None = Field(default=None, max_length=128)
    template_version: str | None = Field(default=None, max_length=64)
    document_id: str | None = Field(default=None, max_length=128)
    input_markdown: str = Field(default="", max_length=50000)
    selection_text: str | None = Field(default=None, max_length=5000)
    async_mode: bool = Field(default=False, alias="async")
    gate_mode: str | None = Field(default=None, max_length=32)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class LlmActionResponse(BaseModel):
    content: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = ""
    warnings: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    job_id: int | None = None
    status: str = "completed"
    observability: dict[str, Any] = Field(default_factory=dict)


class LlmActionHistoryItem(BaseModel):
    job_id: int
    job_type: str
    status: str
    project_key: str | None = None
    action_id: str | None = None
    template_key: str | None = None
    template_version: str | None = None
    request_meta: dict[str, Any] = Field(default_factory=dict)
    actor_id: str | None = None
    trace_id: str | None = None
    created_at: str | None = None
    duration_ms: int | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)
