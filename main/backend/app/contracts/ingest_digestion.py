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


class LongCycleLifecycleTransition(str, Enum):
    PLAN = "plan"
    MARK_READY = "mark_ready"
    DISPATCH = "dispatch"
    SUCCEED = "succeed"
    FAIL = "fail"
    BLOCK = "block"
    SKIP = "skip"


class IngestTimeSemantics(BaseModel):
    source_time: datetime | None = None
    processed_time: datetime
    effective_time: datetime
    time_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    time_provenance: str = Field(default="processed_time_fallback", max_length=96)
    time_parse_version: str = Field(default="source-time-window-v1", max_length=96)
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
    effective_time: datetime
    time_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    time_provenance: str = Field(default="processed_time_fallback", max_length=96)
    time_parse_version: str = Field(default="source-time-window-v1", max_length=96)
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


class LongCycleTaskLifecycleEvent(BaseModel):
    transition: LongCycleLifecycleTransition
    from_status: LongCycleTaskStatus | None = None
    to_status: LongCycleTaskStatus
    event_time: datetime
    actor: str | None = Field(default=None, max_length=128)
    reason: str | None = Field(default=None, max_length=256)
    dispatch_ref: str | None = Field(default=None, max_length=256)
    output_ref: str | None = Field(default=None, max_length=512)
    error: str | None = Field(default=None, max_length=512)

    model_config = ConfigDict(extra="forbid")


class LongCyclePersistentTaskRecord(BaseModel):
    contract_version: str = Field(default="ingest.long_cycle_persistent_task.v1", max_length=96)
    task_key: str = Field(..., min_length=1, max_length=96)
    scheduler_ref: str | None = Field(default=None, max_length=256)
    persistent_ref: str | None = Field(default=None, max_length=256)
    task: LongCycleTaskObject
    status: LongCycleTaskStatus
    lifecycle_events: list[LongCycleTaskLifecycleEvent] = Field(default_factory=list)
    attempt_count: int = Field(default=0, ge=0)
    dispatch_ref: str | None = Field(default=None, max_length=256)
    output_ref: str | None = Field(default=None, max_length=512)
    error: str | None = Field(default=None, max_length=512)
    created_at: datetime
    updated_at: datetime
    remaining_external_bindings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("scheduler_ref", "persistent_ref", "dispatch_ref", "output_ref", "error")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("remaining_external_bindings")
    @classmethod
    def _normalize_external_bindings(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out


class LongCycleSchedulerDispatchIntent(BaseModel):
    contract_version: str = Field(default="ingest.long_cycle_scheduler_dispatch_intent.v1", max_length=96)
    dispatch_key: str = Field(..., min_length=1, max_length=96)
    idempotency_key: str = Field(..., min_length=1, max_length=128)
    scheduler_ref: str = Field(..., min_length=1, max_length=256)
    queue_name: str = Field(default="ingest.long_cycle.contract", max_length=128)
    worker_task_name: str = Field(default="ingest.long_cycle.digest.contract_only", max_length=128)
    task_key: str = Field(..., min_length=1, max_length=96)
    selected_window: str = Field(..., min_length=1, max_length=32)
    cadence: str = Field(..., min_length=1, max_length=64)
    run_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    live_dispatch: bool = False

    model_config = ConfigDict(extra="forbid")

    @field_validator("scheduler_ref", "queue_name", "worker_task_name", "task_key", "selected_window", "cadence")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


class LongCyclePersistenceWriteResult(BaseModel):
    contract_version: str = Field(default="ingest.long_cycle_persistence_write_result.v1", max_length=96)
    repository_ref: str = Field(..., min_length=1, max_length=256)
    logical_table: str = Field(..., min_length=1, max_length=128)
    operation: str = Field(default="upsert", max_length=32)
    record_key: str = Field(..., min_length=1, max_length=96)
    status_before: LongCycleTaskStatus | None = None
    status_after: LongCycleTaskStatus
    write_time: datetime
    payload_ref: str | None = Field(default=None, max_length=256)
    live_db_write: bool = False

    model_config = ConfigDict(extra="forbid")

    @field_validator("repository_ref", "logical_table", "operation", "record_key")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("payload_ref")
    @classmethod
    def _normalize_payload_ref(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None


class LongCycleLifecycleContractCheck(BaseModel):
    contract_version: str = Field(default="ingest.long_cycle_lifecycle_contract_check.v1", max_length=96)
    status: str = Field(..., max_length=32)
    blockers: list[str] = Field(default_factory=list)
    closed_slice: list[str] = Field(default_factory=list)
    remaining_runtime_gaps: list[str] = Field(default_factory=list)
    automation_status: LongCycleAutomationStatus
    persistent_task: LongCyclePersistentTaskRecord

    model_config = ConfigDict(extra="forbid")

    @field_validator("blockers", "closed_slice", "remaining_runtime_gaps")
    @classmethod
    def _normalize_string_list(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out


class LongCycleSchedulerE2EContractCheck(BaseModel):
    contract_version: str = Field(default="ingest.long_cycle_scheduler_e2e_contract_check.v1", max_length=96)
    status: str = Field(..., max_length=32)
    blockers: list[str] = Field(default_factory=list)
    closed_slice: list[str] = Field(default_factory=list)
    remaining_runtime_gaps: list[str] = Field(default_factory=list)
    automation_status: LongCycleAutomationStatus
    dispatch_intent: LongCycleSchedulerDispatchIntent
    persistent_task: LongCyclePersistentTaskRecord
    completed_record: LongCyclePersistentTaskRecord
    persistence_writes: list[LongCyclePersistenceWriteResult] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("blockers", "closed_slice", "remaining_runtime_gaps")
    @classmethod
    def _normalize_string_list(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out
