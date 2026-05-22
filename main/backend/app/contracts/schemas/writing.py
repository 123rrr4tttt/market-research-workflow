from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WritingRequestContext(BaseModel):
    project_key: str | None = Field(default=None, max_length=64)
    trace_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    actor_id: str | None = Field(default=None, max_length=128)
    agent_role: Literal["user_facing_assistant", "orchestration_runtime", "business_capability_wrapper"] | None = Field(
        default=None,
        max_length=64,
    )

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
    context: "WritingContextEnvelope | None" = None
    graph_context: dict[str, Any] | None = None

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
    context_boundary: dict[str, Any] = Field(default_factory=dict)
    dependency_gate: dict[str, Any] = Field(default_factory=dict)
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
    target_scope: Literal["selection", "document"] | None = None
    async_mode: bool = Field(default=False, alias="async")
    gate_mode: str | None = Field(default=None, max_length=32)

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def _infer_target_scope(self) -> "LlmActionRequest":
        if self.target_scope is not None:
            return self
        self.target_scope = "selection" if str(self.selection_text or "").strip() else "document"
        return self


class LlmActionResponse(BaseModel):
    content: str = ""
    sources: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = ""
    warnings: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    job_id: int | None = None
    status: str = "completed"
    capability_truth: dict[str, Any] = Field(default_factory=dict)
    observability: dict[str, Any] = Field(default_factory=dict)
    action_boundary: dict[str, Any] = Field(default_factory=dict)
    dependency_gate: dict[str, Any] = Field(default_factory=dict)


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


class WritingDocumentData(BaseModel):
    id: int | None = None
    project_key: str | None = None
    title: str = ""
    body_md: str = ""
    status: str | None = "draft"
    version: int | None = None
    etag: str | None = None
    updated_by_user_id: str | None = None
    updated_at: str | None = None
    created_at: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class WritingDocumentListData(BaseModel):
    items: list[WritingDocumentData] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class WritingDocumentDeleteData(BaseModel):
    deleted: bool = False
    document: WritingDocumentData | dict[str, Any] = Field(default_factory=WritingDocumentData)

    model_config = ConfigDict(extra="allow")


class WritingDocumentDraftData(BaseModel):
    id: int | None = None
    doc_id: int | None = None
    project_key: str | None = None
    draft_body_md: str = ""
    selection_snapshot: dict[str, Any] | list[Any] | None = Field(default_factory=dict)
    base_version: int | None = None
    autosave_token: str | None = None
    request_id: str | None = None
    updated_at: str | None = None
    created_at: str | None = None

    model_config = ConfigDict(extra="allow")


class WritingCitationData(BaseModel):
    id: int | None = None
    doc_id: int | None = None
    project_key: str | None = None
    source_doc_id: int | None = None
    source_uri: str | None = None
    source_title: str | None = None
    quote_text: str | None = None
    position_anchor: str | None = None
    card_id: str | None = None
    metadata_json: dict[str, Any] | None = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    model_config = ConfigDict(extra="allow")


class WritingCitationListData(BaseModel):
    items: list[WritingCitationData] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


PrimaryWritingLoopStage = Literal[
    "document_ready",
    "editing",
    "saved",
    "context_loaded",
    "citation_applied",
    "action_executed",
    "write_back_ready",
]


class WritingBaselineCapability(BaseModel):
    capability_id: str = Field(..., min_length=1, max_length=64)
    designed: bool
    implemented: bool
    still_open: bool
    owner_modules: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=500)

    model_config = ConfigDict(extra="forbid")


class WritingBaselineDeltaMatrix(BaseModel):
    contract_version: str = Field(default="writing.wave_a.e1.v1", min_length=1, max_length=64)
    capabilities: list[WritingBaselineCapability] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    repo_reality: str = Field(default="", max_length=500)

    model_config = ConfigDict(extra="forbid")


class WritingPrimaryLoopCheckpoint(BaseModel):
    project_key: str | None = Field(default=None, max_length=64)
    document_id: int | None = Field(default=None, ge=1)
    has_markdown_body: bool = False
    saved_version: int | None = Field(default=None, ge=1)
    has_context_cards: bool = False
    has_accepted_citation: bool = False
    llm_action_invoked: bool = False
    has_write_back_candidate: bool = False
    graph_context_attached: bool = False
    graph_handoff_contract_version: str | None = Field(default=None, max_length=64)
    llm_consumer: str | None = Field(default="writing.llm_action", max_length=128)
    frontend_surface: str | None = Field(default="writing.workbench", max_length=128)

    model_config = ConfigDict(extra="forbid")


class WritingPrimaryLoopState(BaseModel):
    contract_version: str = Field(default="writing.wave_a.e2.v1", min_length=1, max_length=64)
    stages: list[PrimaryWritingLoopStage] = Field(default_factory=list)
    next_required_stage: PrimaryWritingLoopStage | None = None
    always_on_layers: list[str] = Field(default_factory=list)
    optional_layers: list[str] = Field(default_factory=list)
    no_graph_happy_path_complete: bool = False
    selection_level_entry_supported: bool = True
    document_level_entry_supported: bool = True
    ordering_violations: list[str] = Field(default_factory=list)
    cross_theme_dependency_gate: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class WritingContextEnvelope(BaseModel):
    contract_version: str = Field(default="writing.context_boundary.e3.v1", min_length=1, max_length=64)
    selection_context: dict[str, Any] = Field(default_factory=dict)
    evidence_context: dict[str, Any] = Field(default_factory=dict)
    accepted_citation_context: dict[str, Any] = Field(default_factory=dict)
    graph_context: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")
