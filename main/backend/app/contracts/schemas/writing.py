from __future__ import annotations

from typing import Annotated, Any, Literal

from functorial_kit import Failure
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator
from ..materials import normalize_material_source_type
from mrw_functorial_kit.core.application_failure_semantics import writing_request_contract_failures


_WRITING_FAILURE_WITNESS = "test:test_writing_query_core_failure"
MaterialCardSource = Annotated[
    Literal["material", "resource", "graph"], BeforeValidator(normalize_material_source_type)
]


def _normalize_writing_query(value: object, *, operation: str) -> str | Failure:
    normalized = str(value or "").strip()
    if normalized:
        return normalized
    return writing_request_contract_failures.fail(
        "query_required",
        "query is required",
        {
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "failure_family": writing_request_contract_failures.name,
            "field": "query",
            "owner": "app.contracts.schemas.writing",
            "operation": operation,
            "public_exception": "ValueError",
            "public_message": "query is required",
            "site": "app.contracts.schemas.writing",
            "witness": _WRITING_FAILURE_WITNESS,
        },
    )


def _lift_writing_contract_failure(value: str | Failure) -> str:
    if isinstance(value, Failure):
        # kit:boundary owner=app.contracts.schemas.writing.pydantic_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=writing.request.contract_failure witness=test:test_writing_query_core_failure
        raise ValueError(value.message)
    return value


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
    sources: list[MaterialCardSource] = Field(default_factory=list)
    timeout_ms: int | None = Field(default=None, ge=50, le=30000)
    context: "WritingContextEnvelope | None" = None
    graph_context: dict[str, Any] | None = None

    @field_validator("query")
    @classmethod
    def _query_must_not_be_blank(cls, value: str) -> str:
        return _lift_writing_contract_failure(
            _normalize_writing_query(value, operation="KeywordCardRequest.query")
        )


class KeywordCardItem(BaseModel):
    card_id: str = Field(..., min_length=1, max_length=128)
    source_type: MaterialCardSource
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
    search_failures: list[dict[str, Any]] = Field(default_factory=list)
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
    source_type: MaterialCardSource
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
    source_type: MaterialCardSource


class SuggestRequest(WritingRequestContext):
    query: str = Field(..., min_length=1, max_length=200)
    mode: Literal["keyword", "template", "material", "command"] = "keyword"
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        return _lift_writing_contract_failure(
            _normalize_writing_query(value, operation="SuggestRequest.query")
        )


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


class WritingTemplateItemData(BaseModel):
    template_key: str = Field(..., min_length=1, max_length=128)
    label: str = Field(..., min_length=1, max_length=300)
    description: str = Field(default="", max_length=1000)
    template_content: str = ""

    model_config = ConfigDict(extra="allow")


class WritingTemplateListData(BaseModel):
    items: list[WritingTemplateItemData] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class WritingDocumentData(BaseModel):
    doc_id: int | None = None
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

    model_config = ConfigDict(extra="forbid")


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
    source_material_id: int | None = None
    source_uri: str | None = None
    source_title: str | None = None
    quote_text: str | None = None
    position_anchor: str | None = None
    card_id: str | None = None
    metadata_json: dict[str, Any] | None = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    model_config = ConfigDict(extra="forbid")


class WritingCitationUpsertItem(BaseModel):
    source_material_id: int | None = Field(default=None, ge=1)
    source_uri: str | None = Field(default=None, max_length=2048)
    source_title: str | None = Field(default=None, max_length=500)
    quote_text: str | None = Field(default=None, max_length=10000)
    position_anchor: str | None = Field(default=None, max_length=500)
    card_id: str | None = Field(default=None, max_length=128)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class WritingCitationListData(BaseModel):
    items: list[WritingCitationData] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class TypedKnowledgeWritingHandoffData(BaseModel):
    contract_version: Literal["typed_knowledge.writing_handoff.v1"] = "typed_knowledge.writing_handoff.v1"
    knowledge_item_key: str = Field(..., min_length=1, max_length=256)
    project_key: str = Field(..., min_length=1, max_length=64)
    canonical_statement: str = Field(..., min_length=1, max_length=2000)
    primary_type_node_key: str = Field(..., min_length=1, max_length=256)
    topic_cluster_keys: list[str] = Field(default_factory=list)
    booklet_keys: list[str] = Field(default_factory=list)
    review_state: str = Field(..., min_length=1, max_length=64)
    quality_grade: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=64)
    evidence_refs: list[str] = Field(default_factory=list, min_length=1)
    visibility_scope: str = Field(..., min_length=1, max_length=64)
    selection_hash: str | None = Field(default=None, max_length=128)
    selection_text: str | None = Field(default=None, max_length=5000)
    facets: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class TypedKnowledgeWritingContext(BaseModel):
    contract_version: Literal["writing.typed_knowledge_context.v1"] = "writing.typed_knowledge_context.v1"
    source: Literal["typed_knowledge"] = "typed_knowledge"
    consumer: Literal["writing.keyword_card"] = "writing.keyword_card"
    handoffs: list[TypedKnowledgeWritingHandoffData] = Field(default_factory=list, min_length=1)
    boundary: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class WritingContextEnvelope(BaseModel):
    contract_version: str = Field(default="writing.context_boundary.e3.v1", min_length=1, max_length=64)
    selection_context: dict[str, Any] = Field(default_factory=dict)
    evidence_context: dict[str, Any] = Field(default_factory=dict)
    accepted_citation_context: dict[str, Any] = Field(default_factory=dict)
    graph_context: dict[str, Any] | None = None
    typed_knowledge_context: TypedKnowledgeWritingContext | None = None

    model_config = ConfigDict(extra="forbid")
