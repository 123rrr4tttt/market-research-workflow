from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

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


class LongCycleTaskStatus(str, Enum):
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


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


class LongCycleTaskSnapshot(BaseModel):
    status: LongCycleTaskStatus = LongCycleTaskStatus.PLANNED
    selected_window: str | None = Field(default=None, max_length=32)
    output_ref: str | None = Field(default=None, max_length=512)
    updated_at: datetime
    reason: str | None = Field(default=None, max_length=256)

    model_config = ConfigDict(extra="forbid")

    @field_validator("selected_window")
    @classmethod
    def _normalize_selected_window(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        return normalized or None


class LongCycleTaskObject(BaseModel):
    task_goal: str = Field(default="", max_length=256)
    input_selector: dict[str, Any] = Field(default_factory=dict)
    window_strategy: str = Field(default="prompt_time_density_priority", max_length=128)
    candidate_windows: list[str] = Field(default_factory=list)
    cadence: str = Field(default="manual", max_length=64)
    priority_rule: str | None = Field(default="prefer_low_density_gap_fill", max_length=128)
    output_target: str = Field(default="digestion_status_snapshot", max_length=128)
    success_status: LongCycleTaskStatus = LongCycleTaskStatus.SUCCEEDED
    failure_status: LongCycleTaskStatus = LongCycleTaskStatus.FAILED
    last_run_snapshot: LongCycleTaskSnapshot | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("task_goal", "window_strategy", "cadence", "output_target")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("candidate_windows")
    @classmethod
    def _normalize_candidate_windows(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item or "").strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out


class LongCycleAutomationStatus(BaseModel):
    contract_version: str = Field(default="ingest.long_cycle_automation_status.v1", max_length=96)
    status: LongCycleTaskStatus
    blockers: list[str] = Field(default_factory=list)
    selected_window: str | None = Field(default=None, max_length=32)
    task: LongCycleTaskObject
    normalized_input: NormalizedIngestEnvelope
    digestion_decision: DigestionDecision

    model_config = ConfigDict(extra="forbid")

    @field_validator("blockers")
    @classmethod
    def _normalize_blockers(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out
