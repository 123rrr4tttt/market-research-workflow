from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngestInputKind(str, Enum):
    URL_DRIVEN_EXTERNAL = "url_driven_external"
    RAW_IMPORT = "raw_import"
    REPORT_SHAPED = "report_shaped"
    DERIVED_LLM_REPORT = "derived_llm_report"
    DERIVED_WRITING_MARKDOWN = "derived_writing_markdown"
    UNKNOWN = "unknown"


class ContentFormat(str, Enum):
    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    STRUCTURED_JSON = "structured_json"
    OTHER = "other"


class DigestionStage(str, Enum):
    PASS_THROUGH = "pass_through"
    CHUNK_FIRST = "chunk_first"
    SUMMARIZE_FIRST = "summarize_first"
    EXTRACT_FIRST = "extract_first"


class IngestTimeSemantics(BaseModel):
    source_time: datetime | None = None
    processed_time: datetime
    task_window: str | None = None
    task_window_start: date | None = None
    task_window_end: date | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("task_window")
    @classmethod
    def _normalize_task_window(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        return normalized or None


class NormalizedIngestEnvelope(BaseModel):
    project_key: str | None = Field(default=None, max_length=64)
    input_kind: IngestInputKind = IngestInputKind.UNKNOWN
    source_locator: str | None = Field(default=None, max_length=2048)
    content_format: ContentFormat = ContentFormat.OTHER
    source_time: datetime | None = None
    processed_time: datetime
    lineage_ref: str | None = Field(default=None, max_length=256)
    requested_downstream_targets: list[str] = Field(default_factory=list)
    task_window: str | None = None
    task_window_start: date | None = None
    task_window_end: date | None = None
    ingestion_entrypoint: str | None = Field(default=None, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @field_validator("project_key")
    @classmethod
    def _normalize_project_key(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("source_locator")
    @classmethod
    def _normalize_source_locator(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("requested_downstream_targets")
    @classmethod
    def _normalize_targets(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item or "").strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out


class DigestionDecision(BaseModel):
    stage: DigestionStage
    chunking_required: bool = False
    summarize_required: bool = False
    extract_required: bool = False
    reason: str = Field(default="", max_length=256)

    model_config = ConfigDict(extra="forbid")
