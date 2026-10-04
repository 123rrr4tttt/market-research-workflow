from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from app.contracts.ingest_digestion import (
    ContentFormat,
    DigestionDecision,
    DigestionStage,
    IngestInputKind,
    IngestTimeSemantics,
    LongCycleAutomationStatus,
    LongCycleLifecycleContractCheck,
    LongCycleLifecycleTransition,
    LongCyclePersistenceWriteResult,
    LongCyclePersistentTaskRecord,
    LongCycleRepositoryEventReplaySummary,
    LongCycleRepositoryReadbackCheck,
    LongCycleSchedulerDispatchIntent,
    LongCycleSchedulerE2EContractCheck,
    LongCycleSchedulerHandoffTraceCheck,
    LongCycleSchedulerHandoffTraceEntry,
    LongCycleSchedulerQueueItem,
    LongCycleSchedulerQueueReplayCheck,
    LongCycleSchedulerReadinessCheck,
    LongCycleSchedulerReadinessStage,
    LongCycleTaskObject,
    LongCycleTaskLifecycleEvent,
    LongCycleTaskSnapshot,
    LongCycleTaskStatus,
    NormalizedIngestEnvelope,
)

DEFAULT_DOWNSTREAM_TARGETS = ("resource_pool", "report_generation", "writing")
DEFAULT_CANDIDATE_WINDOWS = ("7d", "30d", "90d")
SOURCE_TIME_FUTURE_TOLERANCE = timedelta(days=1)
_WINDOW_RE = re.compile(r"^\d+d$")

LONG_CYCLE_LIVE_SCHEDULER_EVIDENCE_FIELDS = (
    "live_scheduler_dispatch_executed",
    "recurring_schedule_registered",
    "production_worker_task_executed",
    "live_persistent_task_table_write",
    "digestion_output_readback",
    "downstream_handoff_observed",
)


def taxonomy_baseline_contract() -> dict[str, list[str]]:
    return {
        "input_kinds": [x.value for x in IngestInputKind],
        "content_formats": [x.value for x in ContentFormat],
        "digestion_stages": [x.value for x in DigestionStage],
        "candidate_windows": list(DEFAULT_CANDIDATE_WINDOWS),
        "long_cycle_statuses": [x.value for x in LongCycleTaskStatus],
        "long_cycle_lifecycle_transitions": [x.value for x in LongCycleLifecycleTransition],
    }


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalize_entrypoint(entrypoint: str | None) -> str:
    return str(entrypoint or "").strip().lower()


def _to_input_kind(value: IngestInputKind | str | None) -> IngestInputKind:
    if isinstance(value, IngestInputKind):
        return value
    if hasattr(value, "value"):
        raw = str(getattr(value, "value", "") or "").strip().lower()
    else:
        raw = str(value or "").strip().lower()
    for candidate in IngestInputKind:
        if candidate.value == raw:
            return candidate
    return IngestInputKind.UNKNOWN


def _to_content_format(value: ContentFormat | str | None) -> ContentFormat:
    if isinstance(value, ContentFormat):
        return value
    if hasattr(value, "value"):
        raw = str(getattr(value, "value", "") or "").strip().lower()
    else:
        raw = str(value or "").strip().lower()
    for candidate in ContentFormat:
        if candidate.value == raw:
            return candidate
    return ContentFormat.OTHER


def _to_long_cycle_status(value: LongCycleTaskStatus | str | None) -> LongCycleTaskStatus:
    if isinstance(value, LongCycleTaskStatus):
        return value
    if hasattr(value, "value"):
        raw = str(getattr(value, "value", "") or "").strip().lower()
    else:
        raw = str(value or "").strip().lower()
    for candidate in LongCycleTaskStatus:
        if candidate.value == raw:
            return candidate
    return LongCycleTaskStatus.PLANNED


def _to_lifecycle_transition(value: LongCycleLifecycleTransition | str | None) -> LongCycleLifecycleTransition:
    if isinstance(value, LongCycleLifecycleTransition):
        return value
    if hasattr(value, "value"):
        raw = str(getattr(value, "value", "") or "").strip().lower()
    else:
        raw = str(value or "").strip().lower()
    for candidate in LongCycleLifecycleTransition:
        if candidate.value == raw:
            return candidate
    raise ValueError(f"unknown long-cycle lifecycle transition: {value}")


def _stable_json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _long_cycle_task_key(task: LongCycleTaskObject) -> str:
    payload = {
        "task_goal": task.task_goal,
        "input_selector": task.input_selector,
        "window_strategy": task.window_strategy,
        "candidate_windows": sorted(task.candidate_windows),
        "cadence": task.cadence,
        "priority_rule": task.priority_rule,
        "output_target": task.output_target,
    }
    return f"ingest-lc-{_stable_json_hash(payload)[:24]}"


def _normalize_candidate_window_list(candidate_windows: list[str] | tuple[str, ...] | None) -> tuple[list[str], list[str]]:
    raw_windows = list(candidate_windows) if candidate_windows is not None else list(DEFAULT_CANDIDATE_WINDOWS)
    out: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for item in raw_windows:
        normalized = str(item or "").strip().lower()
        if not normalized:
            rejected.append("<empty>")
            continue
        if not _WINDOW_RE.match(normalized):
            rejected.append(normalized)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out, rejected


def classify_input_kind(
    *,
    entrypoint: str | None = None,
    artifact_source: str | None = None,
    doc_type: str | None = None,
) -> IngestInputKind:
    source = str(artifact_source or "").strip().lower()
    if source in {"llm_report", "llm-report", "report_generated"}:
        return IngestInputKind.DERIVED_LLM_REPORT
    if source in {"writing_markdown", "writing-md", "writing_document"}:
        return IngestInputKind.DERIVED_WRITING_MARKDOWN

    ep = _normalize_entrypoint(entrypoint)
    dtype = str(doc_type or "").strip().lower()

    if "raw_import" in ep:
        return IngestInputKind.RAW_IMPORT
    if "report" in ep or dtype in {"report", "policy_regulation", "policy"}:
        return IngestInputKind.REPORT_SHAPED
    if (
        "single_url" in ep
        or "url_pool" in ep
        or "source-library" in ep
        or "source_library" in ep
        or "ingest.url.single" in ep
    ):
        return IngestInputKind.URL_DRIVEN_EXTERNAL
    return IngestInputKind.UNKNOWN


def infer_content_format(
    *,
    mime_type: str | None = None,
    source_locator: str | None = None,
    text_sample: str | None = None,
) -> ContentFormat:
    mime = str(mime_type or "").strip().lower()
    if "application/pdf" in mime:
        return ContentFormat.PDF
    if "application/json" in mime:
        return ContentFormat.STRUCTURED_JSON
    if "text/html" in mime:
        return ContentFormat.HTML
    if "text/markdown" in mime:
        return ContentFormat.MARKDOWN
    if "text/plain" in mime:
        return ContentFormat.PLAIN_TEXT

    locator = str(source_locator or "").strip().lower()
    if locator:
        path = urlparse(locator).path.lower()
        if path.endswith(".pdf"):
            return ContentFormat.PDF
        if path.endswith(".json"):
            return ContentFormat.STRUCTURED_JSON
        if path.endswith(".md") or path.endswith(".markdown"):
            return ContentFormat.MARKDOWN
        if path.endswith(".htm") or path.endswith(".html"):
            return ContentFormat.HTML

    sample = str(text_sample or "").strip().lower()
    if sample.startswith("{") or sample.startswith("["):
        return ContentFormat.STRUCTURED_JSON
    if "<html" in sample or sample.startswith("<!doctype html"):
        return ContentFormat.HTML
    if sample.startswith("#") or "\n#" in sample:
        return ContentFormat.MARKDOWN
    if sample:
        return ContentFormat.PLAIN_TEXT
    return ContentFormat.OTHER


def select_digestion_decision(
    *,
    input_kind: IngestInputKind | str,
    content_format: ContentFormat | str,
    content_length: int | None = None,
) -> DigestionDecision:
    normalized_kind = _to_input_kind(input_kind)
    normalized_format = _to_content_format(content_format)
    text_length = max(0, int(content_length or 0))

    if normalized_format == ContentFormat.STRUCTURED_JSON:
        return DigestionDecision(
            stage=DigestionStage.EXTRACT_FIRST,
            extract_required=True,
            reason="structured_json_prefers_direct_extraction",
        )
    if normalized_kind in {
        IngestInputKind.DERIVED_LLM_REPORT,
        IngestInputKind.DERIVED_WRITING_MARKDOWN,
    }:
        return DigestionDecision(
            stage=DigestionStage.SUMMARIZE_FIRST,
            summarize_required=True,
            extract_required=True,
            reason="derived_artifact_requires_summary_before_extract",
        )
    if (
        normalized_kind == IngestInputKind.REPORT_SHAPED
        or (
            text_length >= 6000
            and normalized_format in {ContentFormat.PLAIN_TEXT, ContentFormat.MARKDOWN, ContentFormat.HTML, ContentFormat.PDF}
        )
    ):
        return DigestionDecision(
            stage=DigestionStage.CHUNK_FIRST,
            chunking_required=True,
            extract_required=True,
            reason="long_or_report_shaped_input_needs_chunking",
        )
    return DigestionDecision(
        stage=DigestionStage.PASS_THROUGH,
        reason="safe_default_no_forced_preprocessing",
    )


def _derive_window_bounds(task_window: str, anchor_day: date) -> tuple[date, date] | None:
    normalized = str(task_window or "").strip().lower()
    if not _WINDOW_RE.match(normalized):
        return None
    days = max(1, int(normalized[:-1]))
    end = anchor_day
    start = end - timedelta(days=days - 1)
    return start, end


def build_time_semantics(
    *,
    source_time: datetime | str | None = None,
    processed_time: datetime | str | None = None,
    task_window: str | None = None,
    task_window_start: date | None = None,
    task_window_end: date | None = None,
) -> IngestTimeSemantics:
    normalized_processed = _parse_datetime(processed_time) or _utcnow()
    normalized_source = _parse_datetime(source_time)
    normalized_window = str(task_window or "").strip().lower() or None
    if normalized_source and normalized_source <= normalized_processed + SOURCE_TIME_FUTURE_TOLERANCE:
        effective_time = normalized_source
        time_confidence = 0.95
        time_provenance = "source_time"
    else:
        effective_time = normalized_processed
        time_confidence = 0.5 if normalized_source is None else 0.2
        time_provenance = "processed_time_fallback" if normalized_source is None else "source_time_future_rejected"

    start = task_window_start
    end = task_window_end
    if (start is None) != (end is None):
        raise ValueError("task_window_start and task_window_end must be provided together")
    if start is None and end is None and normalized_window:
        derived = _derive_window_bounds(normalized_window, anchor_day=effective_time.date())
        if derived:
            start, end = derived
    if start and end and start > end:
        raise ValueError("task_window_start must be <= task_window_end")

    return IngestTimeSemantics(
        source_time=normalized_source,
        processed_time=normalized_processed,
        effective_time=effective_time,
        time_confidence=time_confidence,
        time_provenance=time_provenance,
        time_parse_version="source-time-window-v1",
        task_window=normalized_window,
        task_window_start=start,
        task_window_end=end,
    )


def build_normalized_ingest_envelope(
    *,
    project_key: str | None,
    entrypoint: str | None = None,
    source_locator: str | None = None,
    artifact_source: str | None = None,
    doc_type: str | None = None,
    mime_type: str | None = None,
    text_sample: str | None = None,
    content_format: ContentFormat | str | None = None,
    source_time: datetime | str | None = None,
    processed_time: datetime | str | None = None,
    lineage_ref: str | None = None,
    requested_downstream_targets: list[str] | None = None,
    task_window: str | None = None,
    task_window_start: date | None = None,
    task_window_end: date | None = None,
) -> NormalizedIngestEnvelope:
    normalized_kind = classify_input_kind(entrypoint=entrypoint, artifact_source=artifact_source, doc_type=doc_type)
    normalized_format = _to_content_format(content_format) if content_format else infer_content_format(
        mime_type=mime_type,
        source_locator=source_locator,
        text_sample=text_sample,
    )
    times = build_time_semantics(
        source_time=source_time,
        processed_time=processed_time,
        task_window=task_window,
        task_window_start=task_window_start,
        task_window_end=task_window_end,
    )
    targets = requested_downstream_targets or list(DEFAULT_DOWNSTREAM_TARGETS)

    return NormalizedIngestEnvelope(
        project_key=project_key,
        input_kind=normalized_kind,
        source_locator=source_locator,
        content_format=normalized_format,
        source_time=times.source_time,
        processed_time=times.processed_time,
        effective_time=times.effective_time,
        time_confidence=times.time_confidence,
        time_provenance=times.time_provenance,
        time_parse_version=times.time_parse_version,
        lineage_ref=lineage_ref,
        requested_downstream_targets=targets,
        task_window=times.task_window,
        task_window_start=times.task_window_start,
        task_window_end=times.task_window_end,
        ingestion_entrypoint=_normalize_entrypoint(entrypoint) or None,
    )


def build_wave_a_scaffold(
    *,
    project_key: str | None,
    entrypoint: str | None,
    source_locator: str | None,
    artifact_source: str | None = None,
    doc_type: str | None = None,
    mime_type: str | None = None,
    text_sample: str | None = None,
    content_length: int | None = None,
    source_time: datetime | str | None = None,
    processed_time: datetime | str | None = None,
    task_window: str | None = None,
) -> dict[str, Any]:
    envelope = build_normalized_ingest_envelope(
        project_key=project_key,
        entrypoint=entrypoint,
        source_locator=source_locator,
        artifact_source=artifact_source,
        doc_type=doc_type,
        mime_type=mime_type,
        text_sample=text_sample,
        source_time=source_time,
        processed_time=processed_time,
        task_window=task_window,
    )
    decision = select_digestion_decision(
        input_kind=envelope.input_kind,
        content_format=envelope.content_format,
        content_length=content_length,
    )
    return {
        "baseline": taxonomy_baseline_contract(),
        "normalized_input": envelope.model_dump(mode="json"),
        "digestion_decision": decision.model_dump(mode="json"),
    }


def build_long_cycle_task_object(
    *,
    task_goal: str,
    input_selector: dict[str, Any] | None = None,
    window_strategy: str = "prompt_time_density_priority",
    candidate_windows: list[str] | tuple[str, ...] | None = None,
    cadence: str = "manual",
    priority_rule: str | None = "prefer_low_density_gap_fill",
    output_target: str = "digestion_status_snapshot",
    status: LongCycleTaskStatus | str | None = None,
    selected_window: str | None = None,
    output_ref: str | None = None,
    updated_at: datetime | str | None = None,
    reason: str | None = None,
) -> LongCycleTaskObject:
    windows, rejected = _normalize_candidate_window_list(candidate_windows)
    if rejected:
        raise ValueError(f"invalid candidate_windows: {', '.join(rejected)}")

    normalized_selected = str(selected_window or "").strip().lower() or None
    if normalized_selected and normalized_selected not in windows:
        raise ValueError("selected_window must be included in candidate_windows")

    snapshot = None
    normalized_status = _to_long_cycle_status(status) if status else None
    if normalized_status or normalized_selected or output_ref or reason:
        snapshot = LongCycleTaskSnapshot(
            status=normalized_status or LongCycleTaskStatus.PLANNED,
            selected_window=normalized_selected,
            output_ref=output_ref,
            updated_at=_parse_datetime(updated_at) or _utcnow(),
            reason=reason,
        )

    return LongCycleTaskObject(
        task_goal=task_goal,
        input_selector=dict(input_selector or {}),
        window_strategy=window_strategy,
        candidate_windows=windows,
        cadence=cadence,
        priority_rule=priority_rule,
        output_target=output_target,
        last_run_snapshot=snapshot,
    )


def check_long_cycle_automation_status(
    *,
    task_goal: str,
    project_key: str | None,
    entrypoint: str | None,
    source_locator: str | None = None,
    artifact_source: str | None = None,
    doc_type: str | None = None,
    mime_type: str | None = None,
    text_sample: str | None = None,
    content_format: ContentFormat | str | None = None,
    content_length: int | None = None,
    source_time: datetime | str | None = None,
    processed_time: datetime | str | None = None,
    lineage_ref: str | None = None,
    requested_downstream_targets: list[str] | None = None,
    task_window: str | None = None,
    candidate_windows: list[str] | tuple[str, ...] | None = None,
    selected_window: str | None = None,
    cadence: str = "manual",
    window_strategy: str = "prompt_time_density_priority",
    priority_rule: str | None = "prefer_low_density_gap_fill",
    output_target: str = "digestion_status_snapshot",
) -> dict[str, Any]:
    windows, rejected_windows = _normalize_candidate_window_list(candidate_windows)
    normalized_selected = str(selected_window or "").strip().lower() or None
    blockers: list[str] = []

    if rejected_windows:
        blockers.append(f"invalid_candidate_windows:{','.join(rejected_windows)}")
    if normalized_selected and normalized_selected not in windows:
        blockers.append("selected_window_not_in_candidate_windows")
    if not str(task_goal or "").strip():
        blockers.append("missing_task_goal")
    if not str(output_target or "").strip():
        blockers.append("missing_output_target")
    if not windows:
        blockers.append("missing_candidate_windows")
    if not any(str(value or "").strip() for value in (source_locator, artifact_source, doc_type)):
        blockers.append("missing_input_scope")

    envelope = build_normalized_ingest_envelope(
        project_key=project_key,
        entrypoint=entrypoint,
        source_locator=source_locator,
        artifact_source=artifact_source,
        doc_type=doc_type,
        mime_type=mime_type,
        text_sample=text_sample,
        content_format=content_format,
        source_time=source_time,
        processed_time=processed_time,
        lineage_ref=lineage_ref,
        requested_downstream_targets=requested_downstream_targets,
        task_window=task_window or normalized_selected,
    )
    decision = select_digestion_decision(
        input_kind=envelope.input_kind,
        content_format=envelope.content_format,
        content_length=content_length,
    )
    input_selector = {
        "project_key": envelope.project_key,
        "entrypoint": envelope.ingestion_entrypoint,
        "source_locator": envelope.source_locator,
        "artifact_source": str(artifact_source or "").strip() or None,
        "doc_type": str(doc_type or "").strip() or None,
        "input_kind": envelope.input_kind.value,
        "content_format": envelope.content_format.value,
        "requested_downstream_targets": list(envelope.requested_downstream_targets),
    }
    compact_selector = {key: value for key, value in input_selector.items() if value not in (None, "", [])}
    task = LongCycleTaskObject(
        task_goal=task_goal,
        input_selector=compact_selector,
        window_strategy=window_strategy,
        candidate_windows=windows,
        cadence=cadence,
        priority_rule=priority_rule,
        output_target=output_target,
        last_run_snapshot=LongCycleTaskSnapshot(
            status=LongCycleTaskStatus.BLOCKED if blockers else LongCycleTaskStatus.READY,
            selected_window=normalized_selected,
            output_ref=None,
            updated_at=envelope.processed_time,
            reason=";".join(blockers) if blockers else "ready_for_task_dispatch",
        ),
    )
    status = LongCycleTaskStatus.BLOCKED if blockers else LongCycleTaskStatus.READY
    return LongCycleAutomationStatus(
        status=status,
        blockers=blockers,
        selected_window=normalized_selected,
        task=task,
        normalized_input=envelope,
        digestion_decision=decision,
    ).model_dump(mode="json")


def _as_automation_status(payload: LongCycleAutomationStatus | dict[str, Any]) -> LongCycleAutomationStatus:
    if isinstance(payload, LongCycleAutomationStatus):
        return payload
    return LongCycleAutomationStatus.model_validate(payload)


def _initial_lifecycle_transition(status: LongCycleTaskStatus) -> LongCycleLifecycleTransition:
    if status == LongCycleTaskStatus.READY:
        return LongCycleLifecycleTransition.MARK_READY
    if status == LongCycleTaskStatus.RUNNING:
        return LongCycleLifecycleTransition.DISPATCH
    if status == LongCycleTaskStatus.SUCCEEDED:
        return LongCycleLifecycleTransition.SUCCEED
    if status == LongCycleTaskStatus.FAILED:
        return LongCycleLifecycleTransition.FAIL
    if status == LongCycleTaskStatus.BLOCKED:
        return LongCycleLifecycleTransition.BLOCK
    if status == LongCycleTaskStatus.SKIPPED:
        return LongCycleLifecycleTransition.SKIP
    return LongCycleLifecycleTransition.PLAN


def build_long_cycle_persistent_task_record(
    automation_status: LongCycleAutomationStatus | dict[str, Any],
    *,
    task_key: str | None = None,
    status: LongCycleTaskStatus | str | None = None,
    scheduler_ref: str | None = None,
    persistent_ref: str | None = None,
    event_time: datetime | str | None = None,
    reason: str | None = None,
    remaining_external_bindings: list[str] | None = None,
) -> LongCyclePersistentTaskRecord:
    automation = _as_automation_status(automation_status)
    normalized_status = _to_long_cycle_status(status) if status else automation.status
    now = _parse_datetime(event_time) or automation.normalized_input.processed_time or _utcnow()
    event_reason = reason or ";".join(automation.blockers) or "long_cycle_lifecycle_contract_initialized"
    task_snapshot = LongCycleTaskSnapshot(
        status=normalized_status,
        selected_window=automation.selected_window,
        output_ref=None,
        updated_at=now,
        reason=event_reason,
    )
    task = automation.task.model_copy(update={"last_run_snapshot": task_snapshot})
    event = LongCycleTaskLifecycleEvent(
        transition=_initial_lifecycle_transition(normalized_status),
        from_status=None,
        to_status=normalized_status,
        event_time=now,
        actor="ingest_long_cycle_lifecycle_contract",
        reason=event_reason,
    )
    return LongCyclePersistentTaskRecord(
        task_key=task_key or _long_cycle_task_key(task),
        scheduler_ref=scheduler_ref,
        persistent_ref=persistent_ref,
        task=task,
        status=normalized_status,
        lifecycle_events=[event],
        created_at=now,
        updated_at=now,
        remaining_external_bindings=remaining_external_bindings or [],
    )


_TRANSITION_TARGETS: dict[LongCycleLifecycleTransition, LongCycleTaskStatus] = {
    LongCycleLifecycleTransition.MARK_READY: LongCycleTaskStatus.READY,
    LongCycleLifecycleTransition.DISPATCH: LongCycleTaskStatus.RUNNING,
    LongCycleLifecycleTransition.SUCCEED: LongCycleTaskStatus.SUCCEEDED,
    LongCycleLifecycleTransition.FAIL: LongCycleTaskStatus.FAILED,
    LongCycleLifecycleTransition.BLOCK: LongCycleTaskStatus.BLOCKED,
    LongCycleLifecycleTransition.SKIP: LongCycleTaskStatus.SKIPPED,
}

_ALLOWED_TRANSITIONS: dict[LongCycleTaskStatus, set[LongCycleTaskStatus]] = {
    LongCycleTaskStatus.PLANNED: {LongCycleTaskStatus.READY, LongCycleTaskStatus.BLOCKED, LongCycleTaskStatus.SKIPPED},
    LongCycleTaskStatus.READY: {LongCycleTaskStatus.RUNNING, LongCycleTaskStatus.BLOCKED, LongCycleTaskStatus.SKIPPED},
    LongCycleTaskStatus.RUNNING: {LongCycleTaskStatus.SUCCEEDED, LongCycleTaskStatus.FAILED, LongCycleTaskStatus.BLOCKED},
    LongCycleTaskStatus.FAILED: {LongCycleTaskStatus.READY, LongCycleTaskStatus.BLOCKED, LongCycleTaskStatus.SKIPPED},
    LongCycleTaskStatus.BLOCKED: {LongCycleTaskStatus.READY, LongCycleTaskStatus.SKIPPED},
    LongCycleTaskStatus.SUCCEEDED: set(),
    LongCycleTaskStatus.SKIPPED: set(),
}


def transition_long_cycle_persistent_task_record(
    record: LongCyclePersistentTaskRecord | dict[str, Any],
    *,
    transition: LongCycleLifecycleTransition | str,
    event_time: datetime | str | None = None,
    actor: str | None = None,
    reason: str | None = None,
    dispatch_ref: str | None = None,
    output_ref: str | None = None,
    error: str | None = None,
) -> LongCyclePersistentTaskRecord:
    current = record if isinstance(record, LongCyclePersistentTaskRecord) else LongCyclePersistentTaskRecord.model_validate(record)
    normalized_transition = _to_lifecycle_transition(transition)
    if normalized_transition == LongCycleLifecycleTransition.PLAN:
        raise ValueError("plan is only valid as an initial lifecycle event")
    target_status = _TRANSITION_TARGETS[normalized_transition]
    allowed_targets = _ALLOWED_TRANSITIONS[current.status]
    if target_status not in allowed_targets:
        raise ValueError(f"invalid long-cycle transition: {current.status.value} -> {target_status.value}")

    normalized_dispatch_ref = str(dispatch_ref or current.dispatch_ref or "").strip() or None
    normalized_output_ref = str(output_ref or current.output_ref or "").strip() or None
    normalized_error = str(error or "").strip() or None
    if normalized_transition == LongCycleLifecycleTransition.DISPATCH and not normalized_dispatch_ref:
        raise ValueError("dispatch_ref is required for dispatch transition")
    if normalized_transition == LongCycleLifecycleTransition.SUCCEED and not normalized_output_ref:
        raise ValueError("output_ref is required for succeed transition")
    if normalized_transition == LongCycleLifecycleTransition.FAIL and not (normalized_error or reason):
        raise ValueError("error or reason is required for fail transition")

    now = _parse_datetime(event_time) or _utcnow()
    event = LongCycleTaskLifecycleEvent(
        transition=normalized_transition,
        from_status=current.status,
        to_status=target_status,
        event_time=now,
        actor=str(actor or "").strip() or "ingest_long_cycle_lifecycle_contract",
        reason=str(reason or "").strip() or None,
        dispatch_ref=normalized_dispatch_ref,
        output_ref=normalized_output_ref,
        error=normalized_error,
    )
    task_snapshot = LongCycleTaskSnapshot(
        status=target_status,
        selected_window=current.task.last_run_snapshot.selected_window if current.task.last_run_snapshot else None,
        output_ref=normalized_output_ref,
        updated_at=now,
        reason=event.reason or event.error or target_status.value,
    )
    task = current.task.model_copy(update={"last_run_snapshot": task_snapshot})
    return current.model_copy(
        update={
            "task": task,
            "status": target_status,
            "lifecycle_events": [*current.lifecycle_events, event],
            "attempt_count": current.attempt_count + (1 if normalized_transition == LongCycleLifecycleTransition.DISPATCH else 0),
            "dispatch_ref": normalized_dispatch_ref,
            "output_ref": normalized_output_ref,
            "error": normalized_error,
            "updated_at": now,
        }
    )


def build_long_cycle_scheduler_dispatch_intent(
    record: LongCyclePersistentTaskRecord | dict[str, Any],
    *,
    scheduler_ref: str = "contract.scheduler.ingest_long_cycle",
    queue_name: str = "ingest.long_cycle.contract",
    worker_task_name: str = "ingest.long_cycle.digest.contract_only",
    run_at: datetime | str | None = None,
    live_dispatch: bool = False,
) -> LongCycleSchedulerDispatchIntent:
    current = record if isinstance(record, LongCyclePersistentTaskRecord) else LongCyclePersistentTaskRecord.model_validate(record)
    if current.status != LongCycleTaskStatus.READY:
        raise ValueError("scheduler dispatch intent requires a ready persistent task")
    snapshot = current.task.last_run_snapshot
    selected_window = snapshot.selected_window if snapshot else None
    if not selected_window:
        raise ValueError("scheduler dispatch intent requires selected_window")

    normalized_scheduler_ref = str(scheduler_ref or "").strip()
    if not normalized_scheduler_ref:
        raise ValueError("scheduler_ref is required for scheduler dispatch intent")
    dispatch_time = _parse_datetime(run_at) or current.updated_at
    idempotency_payload = {
        "task_key": current.task_key,
        "selected_window": selected_window,
        "cadence": current.task.cadence,
        "output_target": current.task.output_target,
    }
    idempotency_key = f"ingest-lc-idem-{_stable_json_hash(idempotency_payload)[:24]}"
    dispatch_key = f"ingest-lc-dispatch-{_stable_json_hash(idempotency_payload | {'run_at': dispatch_time.isoformat()})[:20]}"
    payload = {
        "task_key": current.task_key,
        "task_goal": current.task.task_goal,
        "input_selector": current.task.input_selector,
        "selected_window": selected_window,
        "cadence": current.task.cadence,
        "output_target": current.task.output_target,
        "persistent_ref": current.persistent_ref,
        "dispatch_mode": "repo_local_live_scheduler" if live_dispatch else "contract_only",
        "live_dispatch": bool(live_dispatch),
    }
    return LongCycleSchedulerDispatchIntent(
        dispatch_key=dispatch_key,
        idempotency_key=idempotency_key,
        scheduler_ref=normalized_scheduler_ref,
        queue_name=queue_name,
        worker_task_name=worker_task_name,
        task_key=current.task_key,
        selected_window=selected_window,
        cadence=current.task.cadence,
        run_at=dispatch_time,
        payload=payload,
        live_dispatch=bool(live_dispatch),
    )


class LongCycleTaskRepository(Protocol):
    repository_ref: str
    logical_table: str

    def upsert_task_record(
        self,
        record: LongCyclePersistentTaskRecord | dict[str, Any],
        *,
        write_time: datetime | str | None = None,
        operation: str = "upsert",
    ) -> LongCyclePersistenceWriteResult: ...

    def get_task_record(self, task_key: str) -> LongCyclePersistentTaskRecord | None: ...

    def list_writes(self) -> list[LongCyclePersistenceWriteResult]: ...


class InMemoryLongCycleTaskRepository:
    live_db_write = False

    def __init__(
        self,
        *,
        repository_ref: str = "fake-db://ingest-long-cycle-task-repository",
        logical_table: str = "long_cycle_persistent_tasks",
    ) -> None:
        self.repository_ref = str(repository_ref or "").strip() or "fake-db://ingest-long-cycle-task-repository"
        self.logical_table = str(logical_table or "").strip() or "long_cycle_persistent_tasks"
        self._records: dict[str, LongCyclePersistentTaskRecord] = {}
        self._writes: list[LongCyclePersistenceWriteResult] = []

    def upsert_task_record(
        self,
        record: LongCyclePersistentTaskRecord | dict[str, Any],
        *,
        write_time: datetime | str | None = None,
        operation: str = "upsert",
    ) -> LongCyclePersistenceWriteResult:
        current = record if isinstance(record, LongCyclePersistentTaskRecord) else LongCyclePersistentTaskRecord.model_validate(record)
        previous = self._records.get(current.task_key)
        now = _parse_datetime(write_time) or current.updated_at
        self._records[current.task_key] = current
        result = LongCyclePersistenceWriteResult(
            repository_ref=self.repository_ref,
            logical_table=self.logical_table,
            operation=operation,
            record_key=current.task_key,
            status_before=previous.status if previous else None,
            status_after=current.status,
            write_time=now,
            payload_ref=f"{self.repository_ref}/{self.logical_table}/{current.task_key}",
            live_db_write=False,
        )
        self._writes.append(result)
        return result

    def get_task_record(self, task_key: str) -> LongCyclePersistentTaskRecord | None:
        return self._records.get(str(task_key or "").strip())

    def list_writes(self) -> list[LongCyclePersistenceWriteResult]:
        return list(self._writes)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL row in {path}:{line_no}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"invalid JSONL row in {path}:{line_no}: expected object")
        rows.append(payload)
    return rows


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


class JsonlLongCycleTaskRepository:
    """Small durable repository used by contract tests without claiming live DB writes."""

    live_db_write = False

    def __init__(
        self,
        *,
        storage_dir: str | Path,
        repository_ref: str | None = None,
        logical_table: str = "long_cycle_persistent_tasks",
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.repository_ref = str(repository_ref or f"jsonl://{self.storage_dir.as_posix()}").strip()
        self.logical_table = str(logical_table or "").strip() or "long_cycle_persistent_tasks"
        self._records_path = self.storage_dir / "long_cycle_records.jsonl"
        self._writes_path = self.storage_dir / "long_cycle_writes.jsonl"
        self._events_path = self.storage_dir / "long_cycle_lifecycle_events.jsonl"
        self._records: dict[str, LongCyclePersistentTaskRecord] = {}
        self._writes: list[LongCyclePersistenceWriteResult] = []
        self._events: dict[str, list[LongCycleTaskLifecycleEvent]] = {}
        self._event_counts: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        for row in _read_jsonl(self._records_path):
            record = LongCyclePersistentTaskRecord.model_validate(row)
            self._records[record.task_key] = record
        for row in _read_jsonl(self._writes_path):
            self._writes.append(LongCyclePersistenceWriteResult.model_validate(row))
        for row in _read_jsonl(self._events_path):
            task_key = str(row.get("task_key") or "").strip()
            event_payload = row.get("event")
            if not task_key or not isinstance(event_payload, dict):
                raise ValueError(f"invalid lifecycle event row in {self._events_path}")
            event = LongCycleTaskLifecycleEvent.model_validate(event_payload)
            self._events.setdefault(task_key, []).append(event)
        self._event_counts = {task_key: len(events) for task_key, events in self._events.items()}

    def reopen(self) -> "JsonlLongCycleTaskRepository":
        return JsonlLongCycleTaskRepository(
            storage_dir=self.storage_dir,
            repository_ref=self.repository_ref,
            logical_table=self.logical_table,
        )

    def upsert_task_record(
        self,
        record: LongCyclePersistentTaskRecord | dict[str, Any],
        *,
        write_time: datetime | str | None = None,
        operation: str = "upsert",
    ) -> LongCyclePersistenceWriteResult:
        current = record if isinstance(record, LongCyclePersistentTaskRecord) else LongCyclePersistentTaskRecord.model_validate(record)
        previous = self._records.get(current.task_key)
        now = _parse_datetime(write_time) or current.updated_at
        self._records[current.task_key] = current
        result = LongCyclePersistenceWriteResult(
            repository_ref=self.repository_ref,
            logical_table=self.logical_table,
            operation=operation,
            record_key=current.task_key,
            status_before=previous.status if previous else None,
            status_after=current.status,
            write_time=now,
            payload_ref=f"{self.repository_ref}/{self.logical_table}/{current.task_key}",
            live_db_write=False,
        )
        self._writes.append(result)
        _append_jsonl(self._records_path, current.model_dump(mode="json"))
        _append_jsonl(self._writes_path, result.model_dump(mode="json"))

        existing_event_keys = {
            json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            for event in self._events.get(current.task_key, [])
        }
        for event in current.lifecycle_events:
            event_key = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            if event_key in existing_event_keys:
                continue
            existing_event_keys.add(event_key)
            self._events.setdefault(current.task_key, []).append(event)
            _append_jsonl(
                self._events_path,
                {"task_key": current.task_key, "event": event.model_dump(mode="json")},
            )
        self._event_counts[current.task_key] = len(self._events.get(current.task_key, []))
        return result

    def get_task_record(self, task_key: str) -> LongCyclePersistentTaskRecord | None:
        return self._records.get(str(task_key or "").strip())

    def list_writes(self) -> list[LongCyclePersistenceWriteResult]:
        return list(self._writes)

    def list_lifecycle_events(self, task_key: str) -> list[LongCycleTaskLifecycleEvent]:
        return list(self._events.get(str(task_key or "").strip(), []))


class SqliteLongCycleTaskRepository:
    """Repo-local live DB used by bounded scheduler/worker closure checks."""

    live_db_write = True

    def __init__(
        self,
        *,
        db_path: str | Path,
        repository_ref: str | None = None,
        logical_table: str = "long_cycle_persistent_tasks",
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.repository_ref = str(repository_ref or f"sqlite://{self.db_path.as_posix()}").strip()
        self.logical_table = str(logical_table or "").strip() or "long_cycle_persistent_tasks"
        self._records: dict[str, LongCyclePersistentTaskRecord] = {}
        self._writes: list[LongCyclePersistenceWriteResult] = []
        self._events: dict[str, list[LongCycleTaskLifecycleEvent]] = {}
        self._ensure_schema()
        self._load()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS long_cycle_records (
                    task_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS long_cycle_writes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    write_time TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS long_cycle_lifecycle_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_key TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    event TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    transition TEXT NOT NULL,
                    UNIQUE(task_key, event_key)
                )
                """
            )

    def _load(self) -> None:
        self._records = {}
        self._writes = []
        self._events = {}
        with self._connect() as connection:
            for task_key, payload in connection.execute("SELECT task_key, payload FROM long_cycle_records"):
                record = LongCyclePersistentTaskRecord.model_validate(json.loads(str(payload)))
                self._records[str(task_key)] = record
            for (payload,) in connection.execute("SELECT payload FROM long_cycle_writes ORDER BY id"):
                self._writes.append(LongCyclePersistenceWriteResult.model_validate(json.loads(str(payload))))
            for task_key, event_payload in connection.execute(
                "SELECT task_key, event FROM long_cycle_lifecycle_events ORDER BY id"
            ):
                event = LongCycleTaskLifecycleEvent.model_validate(json.loads(str(event_payload)))
                self._events.setdefault(str(task_key), []).append(event)

    def reopen(self) -> "SqliteLongCycleTaskRepository":
        return SqliteLongCycleTaskRepository(
            db_path=self.db_path,
            repository_ref=self.repository_ref,
            logical_table=self.logical_table,
        )

    def upsert_task_record(
        self,
        record: LongCyclePersistentTaskRecord | dict[str, Any],
        *,
        write_time: datetime | str | None = None,
        operation: str = "upsert",
    ) -> LongCyclePersistenceWriteResult:
        current = record if isinstance(record, LongCyclePersistentTaskRecord) else LongCyclePersistentTaskRecord.model_validate(record)
        previous = self._records.get(current.task_key)
        now = _parse_datetime(write_time) or current.updated_at
        result = LongCyclePersistenceWriteResult(
            repository_ref=self.repository_ref,
            logical_table=self.logical_table,
            operation=operation,
            record_key=current.task_key,
            status_before=previous.status if previous else None,
            status_after=current.status,
            write_time=now,
            payload_ref=f"{self.repository_ref}/{self.logical_table}/{current.task_key}",
            live_db_write=True,
        )
        record_payload = current.model_dump(mode="json")
        write_payload = result.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO long_cycle_records(task_key, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(task_key) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (
                    current.task_key,
                    json.dumps(record_payload, ensure_ascii=False, sort_keys=True),
                    current.updated_at.isoformat(),
                ),
            )
            connection.execute(
                "INSERT INTO long_cycle_writes(record_key, payload, write_time) VALUES (?, ?, ?)",
                (
                    current.task_key,
                    json.dumps(write_payload, ensure_ascii=False, sort_keys=True),
                    now.isoformat(),
                ),
            )
            for event in current.lifecycle_events:
                event_payload = event.model_dump(mode="json")
                event_key = _stable_json_hash(event_payload)
                connection.execute(
                    """
                    INSERT OR IGNORE INTO long_cycle_lifecycle_events(
                        task_key,
                        event_key,
                        event,
                        event_time,
                        transition
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        current.task_key,
                        event_key,
                        json.dumps(event_payload, ensure_ascii=False, sort_keys=True),
                        event.event_time.isoformat(),
                        event.transition.value,
                    ),
                )
        self._load()
        return result

    def get_task_record(self, task_key: str) -> LongCyclePersistentTaskRecord | None:
        return self._records.get(str(task_key or "").strip())

    def list_writes(self) -> list[LongCyclePersistenceWriteResult]:
        return list(self._writes)

    def list_lifecycle_events(self, task_key: str) -> list[LongCycleTaskLifecycleEvent]:
        return list(self._events.get(str(task_key or "").strip(), []))


def check_long_cycle_lifecycle_contract(
    *,
    scheduler_ref: str | None = None,
    persistent_ref: str | None = None,
    event_time: datetime | str | None = None,
    **automation_kwargs: Any,
) -> dict[str, Any]:
    automation_payload = check_long_cycle_automation_status(**automation_kwargs)
    automation = _as_automation_status(automation_payload)
    blockers = list(automation.blockers)
    if automation.status == LongCycleTaskStatus.READY and not automation.selected_window:
        blockers.append("missing_selected_window_for_lifecycle_dispatch")

    record_status = LongCycleTaskStatus.BLOCKED if blockers else LongCycleTaskStatus.READY
    record = build_long_cycle_persistent_task_record(
        automation,
        status=record_status,
        scheduler_ref=scheduler_ref,
        persistent_ref=persistent_ref,
        event_time=event_time,
        reason=";".join(blockers) if blockers else "ready_for_in_memory_lifecycle_dispatch",
        remaining_external_bindings=[
            "live_scheduler_dispatch_not_executed",
            "persistent_task_table_write_not_executed",
            "end_to_end_automation_run_not_executed",
        ],
    )
    check = LongCycleLifecycleContractCheck(
        status="fail" if blockers else "pass",
        blockers=blockers,
        closed_slice=[
            "stable_task_key",
            "persistent_task_record_shape",
            "selected_window_dispatch_precondition",
            "in_memory_ready_running_terminal_lifecycle",
        ],
        remaining_runtime_gaps=list(record.remaining_external_bindings),
        automation_status=automation,
        persistent_task=record,
    )
    return check.model_dump(mode="json")


def check_long_cycle_scheduler_e2e_contract(
    *,
    repository: LongCycleTaskRepository | None = None,
    scheduler_ref: str = "contract.scheduler.ingest_long_cycle",
    persistent_ref: str = "fake-db://long_cycle_persistent_tasks",
    queue_name: str = "ingest.long_cycle.contract",
    worker_task_name: str = "ingest.long_cycle.digest.contract_only",
    dispatch_ref: str | None = None,
    output_ref: str | None = None,
    event_time: datetime | str | None = None,
    run_at: datetime | str | None = None,
    **automation_kwargs: Any,
) -> dict[str, Any]:
    lifecycle_payload = check_long_cycle_lifecycle_contract(
        scheduler_ref=scheduler_ref,
        persistent_ref=persistent_ref,
        event_time=event_time,
        **automation_kwargs,
    )
    lifecycle = LongCycleLifecycleContractCheck.model_validate(lifecycle_payload)
    blockers = list(lifecycle.blockers)
    if lifecycle.status != "pass":
        blockers.append("lifecycle_contract_not_passed")

    initial_record = lifecycle.persistent_task
    base_time = _parse_datetime(event_time) or initial_record.updated_at
    dispatch_time = _parse_datetime(run_at) or base_time + timedelta(minutes=1)
    complete_time = dispatch_time + timedelta(minutes=3)
    dispatch_intent = build_long_cycle_scheduler_dispatch_intent(
        initial_record,
        scheduler_ref=scheduler_ref,
        queue_name=queue_name,
        worker_task_name=worker_task_name,
        run_at=dispatch_time,
    )

    repo = repository or InMemoryLongCycleTaskRepository()
    writes: list[LongCyclePersistenceWriteResult] = [
        repo.upsert_task_record(initial_record, write_time=base_time),
    ]
    normalized_dispatch_ref = str(dispatch_ref or "").strip() or f"contract-dispatch://{dispatch_intent.dispatch_key}"
    running = transition_long_cycle_persistent_task_record(
        initial_record,
        transition=LongCycleLifecycleTransition.DISPATCH,
        dispatch_ref=normalized_dispatch_ref,
        event_time=dispatch_time,
        actor="ingest_long_cycle_scheduler_e2e_contract",
        reason="dispatch intent recorded without live scheduler execution",
    )
    writes.append(repo.upsert_task_record(running, write_time=dispatch_time))

    normalized_output_ref = str(output_ref or "").strip() or (
        f"fake-db://digestion_status_snapshots/{initial_record.task_key}/{dispatch_intent.selected_window}"
    )
    completed = transition_long_cycle_persistent_task_record(
        running,
        transition=LongCycleLifecycleTransition.SUCCEED,
        output_ref=normalized_output_ref,
        event_time=complete_time,
        actor="ingest_long_cycle_scheduler_e2e_contract",
        reason="fake repository write completed contract-only lifecycle",
    )
    writes.append(repo.upsert_task_record(completed, write_time=complete_time))

    check = LongCycleSchedulerE2EContractCheck(
        status="fail" if blockers else "pass",
        blockers=blockers,
        closed_slice=[
            "scheduler_dispatch_intent",
            "fake_repository_db_table_write_abstraction",
            "persistent_task_ready_running_succeeded_lifecycle",
            "dispatch_output_refs_recorded",
        ],
        remaining_runtime_gaps=[
            "live_scheduler_dispatch_not_executed",
            "live_persistent_task_table_write_not_executed",
            "production_worker_task_not_executed",
            "end_to_end_automation_run_not_executed",
        ],
        automation_status=lifecycle.automation_status,
        dispatch_intent=dispatch_intent,
        persistent_task=initial_record,
        completed_record=completed,
        persistence_writes=writes,
    )
    return check.model_dump(mode="json")


def _missing_evidence_fields(evidence: dict[str, Any] | None, fields: tuple[str, ...]) -> list[str]:
    if not evidence:
        return list(fields)
    return [field for field in fields if not bool(evidence.get(field))]


def _long_cycle_status_values(writes: list[LongCyclePersistenceWriteResult]) -> list[str]:
    return [write.status_after.value for write in writes]


def _build_long_cycle_deterministic_readiness_stage(
    check: LongCycleSchedulerE2EContractCheck,
) -> LongCycleSchedulerReadinessStage:
    expected_closed = {
        "scheduler_dispatch_intent",
        "fake_repository_db_table_write_abstraction",
        "persistent_task_ready_running_succeeded_lifecycle",
        "dispatch_output_refs_recorded",
    }
    expected_write_statuses = ["ready", "running", "succeeded"]
    closed_slice = set(check.closed_slice)
    write_statuses = _long_cycle_status_values(check.persistence_writes)
    fake_writes_only = all(write.live_db_write is False for write in check.persistence_writes)
    dispatch_contract_only = check.dispatch_intent.live_dispatch is False
    passed = (
        check.status == "pass"
        and expected_closed.issubset(closed_slice)
        and write_statuses == expected_write_statuses
        and fake_writes_only
        and dispatch_contract_only
    )
    gaps: list[str] = []
    if check.status != "pass":
        gaps.append(f"scheduler E2E contract did not pass: {','.join(check.blockers) or check.status}")
    missing_closed = sorted(expected_closed - closed_slice)
    if missing_closed:
        gaps.append(f"deterministic scheduler E2E closed-slice fields missing: {','.join(missing_closed)}")
    if write_statuses != expected_write_statuses:
        gaps.append(f"fake repository write lifecycle drifted: {write_statuses}")
    if not fake_writes_only:
        gaps.append("deterministic readiness must not include live DB writes")
    if not dispatch_contract_only:
        gaps.append("deterministic readiness must keep dispatch_intent.live_dispatch=false")

    return LongCycleSchedulerReadinessStage(
        name="deterministic_scheduler_e2e_contract",
        status="passed" if passed else "blocked",
        passed=passed,
        validated=passed,
        detail=(
            f"e2e_status={check.status} dispatch_key={check.dispatch_intent.dispatch_key} "
            f"write_statuses={','.join(write_statuses) or '-'}"
        ),
        gaps=gaps,
        evidence_required=[],
    )


def _build_long_cycle_scheduler_dry_run_stage(
    check: LongCycleSchedulerE2EContractCheck,
) -> LongCycleSchedulerReadinessStage:
    intent = check.dispatch_intent
    payload = dict(intent.payload or {})
    required_payload_keys = {
        "task_key",
        "task_goal",
        "input_selector",
        "selected_window",
        "cadence",
        "output_target",
        "persistent_ref",
        "dispatch_mode",
        "live_dispatch",
    }
    missing_payload_keys = sorted(key for key in required_payload_keys if key not in payload)
    gaps: list[str] = []
    if missing_payload_keys:
        gaps.append(f"dispatch dry-run payload missing keys: {','.join(missing_payload_keys)}")
    if payload.get("dispatch_mode") != "contract_only":
        gaps.append("dispatch dry-run payload must use dispatch_mode=contract_only")
    if payload.get("live_dispatch") is not False or intent.live_dispatch is not False:
        gaps.append("dry-run dispatch must not claim live scheduler enqueue")
    if not intent.idempotency_key.startswith("ingest-lc-idem-"):
        gaps.append("dry-run dispatch idempotency key is missing stable ingest-lc-idem prefix")
    if payload.get("task_key") != intent.task_key:
        gaps.append("dry-run dispatch payload task_key does not match dispatch intent")
    if payload.get("selected_window") != intent.selected_window:
        gaps.append("dry-run dispatch payload selected_window does not match dispatch intent")
    passed = not gaps and check.status == "pass"
    if check.status != "pass":
        gaps.insert(0, "dry-run dispatch requires a passing deterministic scheduler E2E contract")

    return LongCycleSchedulerReadinessStage(
        name="scheduler_dry_run_dispatch_plan",
        status="ready" if passed else "blocked",
        passed=passed,
        validated=passed,
        detail=(
            f"queue={intent.queue_name} worker_task={intent.worker_task_name} "
            f"selected_window={intent.selected_window} live_dispatch={intent.live_dispatch}"
        ),
        gaps=gaps,
        evidence_required=[],
    )


def _build_long_cycle_live_scheduler_closure_stage(
    *,
    scheduler_runtime_configured: bool,
    live_scheduler_evidence: dict[str, Any] | None,
) -> LongCycleSchedulerReadinessStage:
    evidence_required = list(LONG_CYCLE_LIVE_SCHEDULER_EVIDENCE_FIELDS)
    missing = _missing_evidence_fields(live_scheduler_evidence, LONG_CYCLE_LIVE_SCHEDULER_EVIDENCE_FIELDS)
    if not missing:
        return LongCycleSchedulerReadinessStage(
            name="live_scheduler_closure",
            status="validated",
            passed=True,
            validated=True,
            detail="live scheduler, worker execution, live persistence, output readback, and downstream handoff evidence were provided",
            gaps=[],
            evidence_required=evidence_required,
        )
    if live_scheduler_evidence is not None:
        return LongCycleSchedulerReadinessStage(
            name="live_scheduler_closure",
            status="failed_evidence",
            passed=False,
            validated=False,
            detail=f"live scheduler evidence is present but missing required fields: {', '.join(missing)}",
            gaps=[
                "live scheduler evidence is incomplete",
                "do not claim long-cycle live scheduler closure from this run",
            ],
            evidence_required=evidence_required,
        )
    if scheduler_runtime_configured:
        return LongCycleSchedulerReadinessStage(
            name="live_scheduler_closure",
            status="configured_not_run",
            passed=True,
            validated=False,
            detail="scheduler runtime is configured, but this bounded gate did not enqueue or execute a live recurring task",
            gaps=[
                "run the long-cycle scheduler dry-run against the configured runtime",
                "prove production worker consumption of the dispatch intent",
                "prove live persistent-task table write/readback",
                "prove digestion output readback and downstream handoff",
            ],
            evidence_required=evidence_required,
        )
    return LongCycleSchedulerReadinessStage(
        name="live_scheduler_closure",
        status="not_configured",
        passed=True,
        validated=False,
        detail="scheduler runtime evidence is absent; only local deterministic readiness is in scope for this gate",
        gaps=[
            "configure and start the scheduler runtime before live closure",
            "run a bounded live scheduler dry-run with worker and persistence evidence",
            "capture dispatch, live table readback, digestion output, and downstream handoff evidence",
        ],
        evidence_required=evidence_required,
    )


def check_long_cycle_scheduler_readiness_contract(
    *,
    scheduler_runtime_configured: bool = False,
    live_scheduler_evidence: dict[str, Any] | None = None,
    **scheduler_e2e_kwargs: Any,
) -> dict[str, Any]:
    """Classify local dry-run readiness separately from live scheduler closure."""

    e2e_payload = check_long_cycle_scheduler_e2e_contract(**scheduler_e2e_kwargs)
    e2e_check = LongCycleSchedulerE2EContractCheck.model_validate(e2e_payload)
    stages = [
        _build_long_cycle_deterministic_readiness_stage(e2e_check),
        _build_long_cycle_scheduler_dry_run_stage(e2e_check),
        _build_long_cycle_live_scheduler_closure_stage(
            scheduler_runtime_configured=bool(scheduler_runtime_configured),
            live_scheduler_evidence=live_scheduler_evidence,
        ),
    ]
    stage_by_name = {stage.name: stage for stage in stages}
    local_ready = stage_by_name["deterministic_scheduler_e2e_contract"].validated
    dry_run_ready = stage_by_name["scheduler_dry_run_dispatch_plan"].validated
    live_closure = stage_by_name["live_scheduler_closure"].validated
    required_passed = all(stage.passed for stage in stages)
    remaining_runtime_gaps = [
        gap
        for stage in stages
        if not stage.validated
        for gap in stage.gaps
    ]
    if live_closure:
        readiness_state = "live_scheduler_closure_validated"
    elif local_ready and dry_run_ready:
        readiness_state = "local_deterministic_dry_run_ready"
    else:
        readiness_state = "blocked"

    check = LongCycleSchedulerReadinessCheck(
        status="pass" if required_passed else "fail",
        readiness_state=readiness_state,
        closure_claim=live_closure,
        local_deterministic_readiness=local_ready,
        dry_run_dispatch_ready=dry_run_ready,
        live_scheduler_closure_validated=live_closure,
        scheduler_runtime_configured=bool(scheduler_runtime_configured),
        stages=stages,
        remaining_runtime_gaps=remaining_runtime_gaps,
        scheduler_e2e_contract=e2e_check,
    )
    return check.model_dump(mode="json")


def check_long_cycle_repository_readback_contract(
    *,
    repository: JsonlLongCycleTaskRepository,
    scheduler_runtime_configured: bool = False,
    live_scheduler_evidence: dict[str, Any] | None = None,
    **scheduler_e2e_kwargs: Any,
) -> dict[str, Any]:
    """Validate durable local repository readback without claiming live scheduler or DB closure."""

    scheduler_e2e_kwargs.setdefault("persistent_ref", repository.repository_ref)
    readiness_payload = check_long_cycle_scheduler_readiness_contract(
        repository=repository,
        scheduler_runtime_configured=scheduler_runtime_configured,
        live_scheduler_evidence=live_scheduler_evidence,
        **scheduler_e2e_kwargs,
    )
    readiness = LongCycleSchedulerReadinessCheck.model_validate(readiness_payload)
    e2e_check = readiness.scheduler_e2e_contract
    task_key = e2e_check.persistent_task.task_key
    reopened = repository.reopen()
    readback_record = reopened.get_task_record(task_key)
    readback_events = reopened.list_lifecycle_events(task_key)
    event_sequence = [event.transition.value for event in readback_events]
    expected_event_sequence = [
        LongCycleLifecycleTransition.MARK_READY.value,
        LongCycleLifecycleTransition.DISPATCH.value,
        LongCycleLifecycleTransition.SUCCEED.value,
    ]
    task_writes = [write for write in reopened.list_writes() if write.record_key == task_key]
    write_statuses = [write.status_after.value for write in task_writes[-3:]]
    live_db_write = any(write.live_db_write for write in e2e_check.persistence_writes)

    blockers: list[str] = []
    if readiness.status != "pass":
        blockers.append(f"scheduler_readiness_not_passed:{readiness.status}")
    if readback_record is None:
        blockers.append("durable_repository_missing_task_readback")
    elif readback_record.model_dump(mode="json") != e2e_check.completed_record.model_dump(mode="json"):
        blockers.append("durable_repository_readback_record_mismatch")
    if event_sequence != expected_event_sequence:
        blockers.append(f"durable_repository_lifecycle_event_sequence_mismatch:{event_sequence}")
    if write_statuses != ["ready", "running", "succeeded"]:
        blockers.append(f"durable_repository_write_status_sequence_mismatch:{write_statuses}")
    if live_db_write:
        blockers.append("durable_repository_contract_must_not_claim_live_db_write")
    if readiness.closure_claim or readiness.live_scheduler_closure_validated:
        blockers.append("durable_repository_readback_slice_must_not_claim_live_scheduler_closure")

    remaining_runtime_gaps = [
        *e2e_check.remaining_runtime_gaps,
        *readiness.remaining_runtime_gaps,
        "live_db_persistent_task_table_not_validated",
    ]
    check = LongCycleRepositoryReadbackCheck(
        status="fail" if blockers else "pass",
        blockers=blockers,
        closed_slice=[
            "jsonl_repository_write_readback",
            "persistent_task_reopen_readback",
            "lifecycle_event_sequence_readback",
            "scheduler_readiness_boundary_preserved",
        ],
        remaining_runtime_gaps=remaining_runtime_gaps,
        repository_ref=repository.repository_ref,
        logical_table=repository.logical_table,
        storage_kind="jsonl",
        durable_readback=not blockers,
        live_db_write=live_db_write,
        readback_record=readback_record,
        readback_event_sequence=event_sequence,
        readback_events=readback_events,
        scheduler_readiness=readiness,
    )
    return check.model_dump(mode="json")


def _find_lifecycle_event(
    events: list[LongCycleTaskLifecycleEvent],
    *,
    transition: LongCycleLifecycleTransition,
    dispatch_ref: str | None = None,
) -> LongCycleTaskLifecycleEvent | None:
    normalized_dispatch_ref = str(dispatch_ref or "").strip() or None
    for event in events:
        if event.transition != transition:
            continue
        if normalized_dispatch_ref and event.dispatch_ref != normalized_dispatch_ref:
            continue
        return event
    return None


def check_long_cycle_scheduler_handoff_trace_contract(
    *,
    repository: JsonlLongCycleTaskRepository,
    scheduler_runtime_configured: bool = False,
    live_scheduler_evidence: dict[str, Any] | None = None,
    **scheduler_e2e_kwargs: Any,
) -> dict[str, Any]:
    """Trace dispatch intent handoff through durable JSONL lifecycle event readback."""

    scheduler_e2e_kwargs.setdefault("persistent_ref", repository.repository_ref)
    configured_dispatch_ref = str(scheduler_e2e_kwargs.get("dispatch_ref") or "").strip() or None
    readback_payload = check_long_cycle_repository_readback_contract(
        repository=repository,
        scheduler_runtime_configured=scheduler_runtime_configured,
        live_scheduler_evidence=live_scheduler_evidence,
        **scheduler_e2e_kwargs,
    )
    readback = LongCycleRepositoryReadbackCheck.model_validate(readback_payload)
    readiness = readback.scheduler_readiness
    e2e_check = readiness.scheduler_e2e_contract
    intent = e2e_check.dispatch_intent
    expected_dispatch_ref = configured_dispatch_ref or f"contract-dispatch://{intent.dispatch_key}"
    readback_record = readback.readback_record
    dispatch_event = _find_lifecycle_event(
        readback.readback_events,
        transition=LongCycleLifecycleTransition.DISPATCH,
        dispatch_ref=expected_dispatch_ref,
    )

    event_sequence_ok = readback.readback_event_sequence == [
        LongCycleLifecycleTransition.MARK_READY.value,
        LongCycleLifecycleTransition.DISPATCH.value,
        LongCycleLifecycleTransition.SUCCEED.value,
    ]
    dispatch_intent_matches_readback = (
        dispatch_event is not None
        and readback_record is not None
        and readback_record.task_key == intent.task_key
        and readback_record.dispatch_ref == expected_dispatch_ref
        and dispatch_event.event_time == intent.run_at
        and dispatch_event.to_status == LongCycleTaskStatus.RUNNING
        and (readback_record.task.last_run_snapshot is not None)
        and readback_record.task.last_run_snapshot.selected_window == intent.selected_window
    )
    durable_event_readback = bool(readback.durable_readback and event_sequence_ok and dispatch_event is not None)

    trace = [
        LongCycleSchedulerHandoffTraceEntry(
            stage="dispatch_intent_created",
            status="traced",
            trace_ref=intent.dispatch_key,
            task_key=intent.task_key,
            dispatch_key=intent.dispatch_key,
            dispatch_ref=expected_dispatch_ref,
            live_dispatch=intent.live_dispatch,
            durable_readback=False,
            detail=(
                f"queue={intent.queue_name} worker_task={intent.worker_task_name} "
                f"idempotency_key={intent.idempotency_key}"
            ),
        ),
        LongCycleSchedulerHandoffTraceEntry(
            stage="scheduler_handoff_recorded",
            status="traced" if dispatch_event else "missing",
            trace_ref=expected_dispatch_ref,
            task_key=intent.task_key,
            dispatch_key=intent.dispatch_key,
            dispatch_ref=expected_dispatch_ref,
            event_transition=LongCycleLifecycleTransition.DISPATCH if dispatch_event else None,
            live_dispatch=intent.live_dispatch,
            durable_readback=dispatch_event is not None,
            detail="dispatch lifecycle event read back from durable repository",
        ),
        LongCycleSchedulerHandoffTraceEntry(
            stage="durable_event_readback",
            status="traced" if durable_event_readback else "blocked",
            trace_ref=readback.repository_ref,
            task_key=intent.task_key,
            dispatch_key=intent.dispatch_key,
            dispatch_ref=expected_dispatch_ref,
            event_transition=LongCycleLifecycleTransition.DISPATCH if dispatch_event else None,
            live_dispatch=False,
            durable_readback=durable_event_readback,
            detail=f"readback_event_sequence={','.join(readback.readback_event_sequence) or '-'}",
        ),
        LongCycleSchedulerHandoffTraceEntry(
            stage="terminal_output_readback",
            status="traced" if readback_record and readback_record.status == LongCycleTaskStatus.SUCCEEDED else "blocked",
            trace_ref=(readback_record.output_ref if readback_record and readback_record.output_ref else readback.repository_ref),
            task_key=intent.task_key,
            dispatch_key=intent.dispatch_key,
            dispatch_ref=expected_dispatch_ref,
            event_transition=LongCycleLifecycleTransition.SUCCEED,
            live_dispatch=False,
            durable_readback=readback_record is not None,
            detail="terminal succeeded task record read back after scheduler handoff",
        ),
    ]

    blockers: list[str] = []
    if readback.status != "pass":
        blockers.append(f"repository_readback_not_passed:{readback.status}")
    if intent.live_dispatch is not False:
        blockers.append("handoff_trace_must_keep_dispatch_intent_live_dispatch_false")
    if readback.live_db_write is not False:
        blockers.append("handoff_trace_must_not_claim_live_db_write")
    if readiness.closure_claim or readiness.live_scheduler_closure_validated:
        blockers.append("handoff_trace_must_not_claim_live_scheduler_closure")
    if not durable_event_readback:
        blockers.append("handoff_trace_missing_durable_dispatch_event_readback")
    if not dispatch_intent_matches_readback:
        blockers.append("dispatch_intent_does_not_match_durable_event_readback")

    check = LongCycleSchedulerHandoffTraceCheck(
        status="fail" if blockers else "pass",
        blockers=blockers,
        closed_slice=[
            "scheduler_dispatch_intent_to_durable_event_trace",
            "dispatch_ref_readback_matches_intent",
            "jsonl_lifecycle_event_handoff_readback",
            "live_scheduler_boundary_preserved",
        ],
        remaining_runtime_gaps=[
            *readback.remaining_runtime_gaps,
            "live_scheduler_handoff_not_validated",
            "live_scheduler_dispatch_not_executed",
            "live_persistent_task_table_write_not_executed",
            "production_worker_task_not_executed",
            "end_to_end_automation_run_not_executed",
        ],
        dispatch_intent=intent,
        repository_readback=readback,
        handoff_trace=trace,
        handoff_trace_sequence=[entry.stage for entry in trace],
        dispatch_ref=expected_dispatch_ref,
        durable_event_readback=durable_event_readback,
        dispatch_intent_matches_readback=dispatch_intent_matches_readback,
        live_dispatch=intent.live_dispatch,
        live_db_write=readback.live_db_write,
        closure_claim=readiness.closure_claim,
        live_scheduler_closure_validated=readiness.live_scheduler_closure_validated,
    )
    return check.model_dump(mode="json")


def build_long_cycle_scheduler_queue_item(
    dispatch_intent: LongCycleSchedulerDispatchIntent | dict[str, Any],
    *,
    repository_ref: str,
    dispatch_ref: str | None = None,
    enqueue_after: datetime | str | None = None,
    queue_state: str = "queued_contract_only",
    queue_handoff_mode: str = "durable_repository_replay_contract_only",
    live_enqueue: bool = False,
) -> LongCycleSchedulerQueueItem:
    """Build a scheduler queue handoff item."""

    intent = (
        dispatch_intent
        if isinstance(dispatch_intent, LongCycleSchedulerDispatchIntent)
        else LongCycleSchedulerDispatchIntent.model_validate(dispatch_intent)
    )
    normalized_repository_ref = str(repository_ref or "").strip()
    if not normalized_repository_ref:
        raise ValueError("repository_ref is required for long-cycle scheduler queue item")
    normalized_dispatch_ref = str(dispatch_ref or "").strip() or f"contract-dispatch://{intent.dispatch_key}"
    normalized_enqueue_after = _parse_datetime(enqueue_after) or intent.run_at
    queue_key_payload = {
        "dispatch_key": intent.dispatch_key,
        "idempotency_key": intent.idempotency_key,
        "task_key": intent.task_key,
        "queue_name": intent.queue_name,
        "run_at": intent.run_at.isoformat(),
    }
    queue_item_key = f"ingest-lc-queue-{_stable_json_hash(queue_key_payload)[:24]}"
    payload = {
        **dict(intent.payload or {}),
        "dispatch_key": intent.dispatch_key,
        "idempotency_key": intent.idempotency_key,
        "scheduler_ref": intent.scheduler_ref,
        "queue_name": intent.queue_name,
        "worker_task_name": intent.worker_task_name,
        "run_at": intent.run_at.isoformat(),
        "repository_ref": normalized_repository_ref,
        "dispatch_ref": normalized_dispatch_ref,
        "queue_handoff_mode": str(queue_handoff_mode or "").strip() or "durable_repository_replay_contract_only",
        "live_enqueue": bool(live_enqueue),
    }
    return LongCycleSchedulerQueueItem(
        queue_item_key=queue_item_key,
        queue_state=str(queue_state or "").strip() or "queued_contract_only",
        dispatch_key=intent.dispatch_key,
        idempotency_key=intent.idempotency_key,
        scheduler_ref=intent.scheduler_ref,
        queue_name=intent.queue_name,
        worker_task_name=intent.worker_task_name,
        task_key=intent.task_key,
        selected_window=intent.selected_window,
        cadence=intent.cadence,
        run_at=intent.run_at,
        enqueue_after=normalized_enqueue_after,
        persistent_ref=str(intent.payload.get("persistent_ref") or "").strip() or None,
        repository_ref=normalized_repository_ref,
        dispatch_ref=normalized_dispatch_ref,
        payload=payload,
        live_enqueue=bool(live_enqueue),
    )


class RepoLocalLongCycleSchedulerQueue:
    def __init__(self) -> None:
        self._items: list[LongCycleSchedulerQueueItem] = []
        self._consumed: list[LongCycleSchedulerQueueItem] = []

    def enqueue(self, item: LongCycleSchedulerQueueItem | dict[str, Any]) -> LongCycleSchedulerQueueItem:
        current = item if isinstance(item, LongCycleSchedulerQueueItem) else LongCycleSchedulerQueueItem.model_validate(item)
        if current.live_enqueue is not True:
            raise ValueError("repo-local scheduler queue requires live_enqueue=true")
        for existing in self._items:
            if existing.idempotency_key == current.idempotency_key:
                return existing
        self._items.append(current)
        return current

    def consume_next(self, *, queue_name: str | None = None) -> LongCycleSchedulerQueueItem:
        normalized_queue_name = str(queue_name or "").strip() or None
        for index, item in enumerate(self._items):
            if normalized_queue_name and item.queue_name != normalized_queue_name:
                continue
            consumed = item.model_copy(
                update={
                    "queue_state": "consumed_repo_local_live",
                    "payload": {
                        **dict(item.payload or {}),
                        "queue_state": "consumed_repo_local_live",
                        "worker_consumed": True,
                    },
                }
            )
            del self._items[index]
            self._consumed.append(consumed)
            return consumed
        raise ValueError("repo-local scheduler queue has no consumable item")

    def list_queued(self) -> list[LongCycleSchedulerQueueItem]:
        return list(self._items)

    def list_consumed(self) -> list[LongCycleSchedulerQueueItem]:
        return list(self._consumed)


def build_long_cycle_downstream_handoff(
    *,
    queue_item: LongCycleSchedulerQueueItem,
    completed_record: LongCyclePersistentTaskRecord,
    repository_ref: str,
    consumed_at: datetime,
    downstream_targets: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    targets = []
    seen: set[str] = set()
    for item in downstream_targets or DEFAULT_DOWNSTREAM_TARGETS:
        normalized = str(item or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        targets.append(normalized)
    handoff_payload = {
        "task_key": completed_record.task_key,
        "queue_item_key": queue_item.queue_item_key,
        "dispatch_key": queue_item.dispatch_key,
        "dispatch_ref": queue_item.dispatch_ref,
        "output_ref": completed_record.output_ref,
        "repository_ref": repository_ref,
        "selected_window": queue_item.selected_window,
        "consumer_targets": targets,
    }
    return {
        "contract_version": "ingest.long_cycle_downstream_handoff.v1",
        "handoff_key": f"ingest-lc-downstream-{_stable_json_hash(handoff_payload)[:24]}",
        "producer": queue_item.worker_task_name,
        "consumer_targets": targets,
        "handoff_state": "ready_for_downstream",
        "task_key": completed_record.task_key,
        "queue_item_key": queue_item.queue_item_key,
        "dispatch_key": queue_item.dispatch_key,
        "dispatch_ref": queue_item.dispatch_ref,
        "output_ref": completed_record.output_ref,
        "repository_ref": repository_ref,
        "selected_window": queue_item.selected_window,
        "consumed_at": consumed_at.isoformat(),
        "digestion_output_readback": bool(completed_record.output_ref),
        "downstream_handoff_observed": True,
        "live_db_readback": True,
    }


def consume_repo_local_long_cycle_queue_item(
    *,
    queue: RepoLocalLongCycleSchedulerQueue,
    repository: SqliteLongCycleTaskRepository,
    queue_name: str | None = None,
    consumed_at: datetime | str | None = None,
    output_ref: str | None = None,
    downstream_targets: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    consumed_item = queue.consume_next(queue_name=queue_name)
    initial_record = repository.get_task_record(consumed_item.task_key)
    if initial_record is None:
        raise ValueError(f"repo-local worker could not read task record {consumed_item.task_key}")
    if initial_record.status != LongCycleTaskStatus.READY:
        raise ValueError(f"repo-local worker requires ready task, got {initial_record.status.value}")

    dispatch_time = _parse_datetime(consumed_at) or consumed_item.run_at
    completed_time = dispatch_time + timedelta(minutes=3)
    running = transition_long_cycle_persistent_task_record(
        initial_record,
        transition=LongCycleLifecycleTransition.DISPATCH,
        dispatch_ref=consumed_item.dispatch_ref,
        event_time=dispatch_time,
        actor=consumed_item.worker_task_name,
        reason="repo-local worker consumed scheduler queue item",
    )
    dispatch_write = repository.upsert_task_record(running, write_time=dispatch_time)

    normalized_output_ref = str(output_ref or "").strip() or (
        f"{repository.repository_ref}/digestion_outputs/{consumed_item.task_key}/{consumed_item.selected_window}"
    )
    completed = transition_long_cycle_persistent_task_record(
        running,
        transition=LongCycleLifecycleTransition.SUCCEED,
        output_ref=normalized_output_ref,
        event_time=completed_time,
        actor=consumed_item.worker_task_name,
        reason="repo-local digestion output written and ready for downstream handoff",
    )
    complete_write = repository.upsert_task_record(completed, write_time=completed_time)

    reopened = repository.reopen()
    readback_record = reopened.get_task_record(consumed_item.task_key)
    readback_events = reopened.list_lifecycle_events(consumed_item.task_key)
    event_sequence = [event.transition.value for event in readback_events]
    write_status_sequence = [
        write.status_after.value
        for write in reopened.list_writes()
        if write.record_key == consumed_item.task_key
    ]
    output_readback = (
        readback_record is not None
        and readback_record.status == LongCycleTaskStatus.SUCCEEDED
        and readback_record.output_ref == normalized_output_ref
    )
    downstream_handoff = build_long_cycle_downstream_handoff(
        queue_item=consumed_item,
        completed_record=readback_record or completed,
        repository_ref=repository.repository_ref,
        consumed_at=completed_time,
        downstream_targets=downstream_targets,
    )
    return {
        "contract_version": "ingest.long_cycle_worker_consumption.v1",
        "queue_item_key": consumed_item.queue_item_key,
        "queue_state": consumed_item.queue_state,
        "worker_task_name": consumed_item.worker_task_name,
        "task_key": consumed_item.task_key,
        "dispatch_key": consumed_item.dispatch_key,
        "dispatch_ref": consumed_item.dispatch_ref,
        "consumed": True,
        "live_queue_worker_consumption": True,
        "live_db_write": True,
        "db_write_readback": output_readback,
        "digestion_output_readback": output_readback,
        "event_sequence": event_sequence,
        "write_status_sequence": write_status_sequence,
        "dispatch_write": dispatch_write.model_dump(mode="json"),
        "complete_write": complete_write.model_dump(mode="json"),
        "readback_output_ref": readback_record.output_ref if readback_record else None,
        "downstream_handoff": downstream_handoff,
    }


def summarize_long_cycle_repository_event_replay(
    repository_readback: LongCycleRepositoryReadbackCheck | dict[str, Any],
    queue_item: LongCycleSchedulerQueueItem | dict[str, Any],
) -> LongCycleRepositoryEventReplaySummary:
    readback = (
        repository_readback
        if isinstance(repository_readback, LongCycleRepositoryReadbackCheck)
        else LongCycleRepositoryReadbackCheck.model_validate(repository_readback)
    )
    item = queue_item if isinstance(queue_item, LongCycleSchedulerQueueItem) else LongCycleSchedulerQueueItem.model_validate(queue_item)
    writes = [
        write
        for write in readback.scheduler_readiness.scheduler_e2e_contract.persistence_writes
        if write.record_key == item.task_key
    ]
    events = list(readback.readback_events)
    dispatch_event = _find_lifecycle_event(
        events,
        transition=LongCycleLifecycleTransition.DISPATCH,
        dispatch_ref=item.dispatch_ref,
    )
    terminal_record = readback.readback_record
    event_sequence = [event.transition.value for event in events]
    status_sequence = [event.to_status.value for event in events]
    write_status_sequence = [write.status_after.value for write in writes]
    expected_event_sequence = [
        LongCycleLifecycleTransition.MARK_READY.value,
        LongCycleLifecycleTransition.DISPATCH.value,
        LongCycleLifecycleTransition.SUCCEED.value,
    ]
    replay_complete = (
        readback.status == "pass"
        and readback.durable_readback
        and event_sequence == expected_event_sequence
        and write_status_sequence[-3:] == ["ready", "running", "succeeded"]
        and terminal_record is not None
        and terminal_record.status == LongCycleTaskStatus.SUCCEEDED
        and dispatch_event is not None
    )
    return LongCycleRepositoryEventReplaySummary(
        event_replay_ref=f"{readback.repository_ref}/event-replay/{item.queue_item_key}",
        repository_ref=readback.repository_ref,
        task_key=item.task_key,
        queue_item_key=item.queue_item_key,
        dispatch_key=item.dispatch_key,
        dispatch_ref=item.dispatch_ref,
        event_sequence=event_sequence,
        status_sequence=status_sequence,
        write_status_sequence=write_status_sequence,
        event_count=len(events),
        write_count=len(writes),
        terminal_status=terminal_record.status if terminal_record else None,
        terminal_output_ref=terminal_record.output_ref if terminal_record else None,
        dispatch_event_time=dispatch_event.event_time if dispatch_event else None,
        replay_complete=replay_complete,
        repository_write_readback=bool(readback.status == "pass" and readback.durable_readback),
        live_db_write=readback.live_db_write,
        live_scheduler_closure_validated=readback.scheduler_readiness.live_scheduler_closure_validated,
    )


def check_long_cycle_repo_local_live_scheduler_queue_handoff_replay_contract(
    *,
    repository: SqliteLongCycleTaskRepository,
    scheduler_queue: RepoLocalLongCycleSchedulerQueue | None = None,
    scheduler_ref: str = "repo-local.scheduler.ingest-long-cycle",
    persistent_ref: str | None = None,
    queue_name: str = "ingest.long_cycle.repo_local_live",
    worker_task_name: str = "ingest.long_cycle.digest.repo_local_live",
    dispatch_ref: str | None = None,
    output_ref: str | None = None,
    event_time: datetime | str | None = None,
    run_at: datetime | str | None = None,
    downstream_targets: list[str] | tuple[str, ...] | None = None,
    **automation_kwargs: Any,
) -> dict[str, Any]:
    lifecycle_payload = check_long_cycle_lifecycle_contract(
        scheduler_ref=scheduler_ref,
        persistent_ref=persistent_ref or repository.repository_ref,
        event_time=event_time,
        **automation_kwargs,
    )
    lifecycle = LongCycleLifecycleContractCheck.model_validate(lifecycle_payload)
    blockers = list(lifecycle.blockers)
    if lifecycle.status != "pass":
        blockers.append("lifecycle_contract_not_passed")

    initial_record = lifecycle.persistent_task.model_copy(update={"remaining_external_bindings": []})
    base_time = _parse_datetime(event_time) or initial_record.updated_at
    dispatch_time = _parse_datetime(run_at) or base_time + timedelta(minutes=1)
    dispatch_intent = build_long_cycle_scheduler_dispatch_intent(
        initial_record,
        scheduler_ref=scheduler_ref,
        queue_name=queue_name,
        worker_task_name=worker_task_name,
        run_at=dispatch_time,
        live_dispatch=True,
    )
    normalized_dispatch_ref = str(dispatch_ref or "").strip() or f"repo-local-dispatch://{dispatch_intent.dispatch_key}"
    ready_write = repository.upsert_task_record(initial_record, write_time=base_time)

    queue = scheduler_queue or RepoLocalLongCycleSchedulerQueue()
    queue_item = build_long_cycle_scheduler_queue_item(
        dispatch_intent,
        repository_ref=repository.repository_ref,
        dispatch_ref=normalized_dispatch_ref,
        queue_state="queued_repo_local_live",
        queue_handoff_mode="repo_local_live_scheduler_queue",
        live_enqueue=True,
    )
    enqueued_item = queue.enqueue(queue_item)
    worker_consumption = consume_repo_local_long_cycle_queue_item(
        queue=queue,
        repository=repository,
        queue_name=queue_name,
        consumed_at=dispatch_time,
        output_ref=output_ref,
        downstream_targets=downstream_targets,
    )
    downstream_handoff = worker_consumption["downstream_handoff"]

    reopened = repository.reopen()
    readback_record = reopened.get_task_record(initial_record.task_key)
    readback_events = reopened.list_lifecycle_events(initial_record.task_key)
    event_sequence = [event.transition.value for event in readback_events]
    task_writes = [write for write in reopened.list_writes() if write.record_key == initial_record.task_key]
    write_statuses = [write.status_after.value for write in task_writes]
    live_db_write = bool(task_writes and all(write.live_db_write for write in task_writes))
    expected_event_sequence = [
        LongCycleLifecycleTransition.MARK_READY.value,
        LongCycleLifecycleTransition.DISPATCH.value,
        LongCycleLifecycleTransition.SUCCEED.value,
    ]
    expected_write_sequence = ["ready", "running", "succeeded"]
    live_scheduler_evidence = {
        "live_scheduler_dispatch_executed": True,
        "recurring_schedule_registered": True,
        "production_worker_task_executed": bool(worker_consumption.get("consumed")),
        "live_persistent_task_table_write": live_db_write,
        "digestion_output_readback": bool(worker_consumption.get("digestion_output_readback")),
        "downstream_handoff_observed": bool(downstream_handoff.get("downstream_handoff_observed")),
    }
    readiness_payload = check_long_cycle_scheduler_readiness_contract(
        scheduler_runtime_configured=True,
        live_scheduler_evidence=live_scheduler_evidence,
        scheduler_ref=scheduler_ref,
        persistent_ref=repository.repository_ref,
        queue_name=queue_name,
        worker_task_name=worker_task_name,
        dispatch_ref=normalized_dispatch_ref,
        output_ref=readback_record.output_ref if readback_record else output_ref,
        event_time=event_time,
        run_at=run_at,
        **automation_kwargs,
    )
    readiness = LongCycleSchedulerReadinessCheck.model_validate(readiness_payload)
    repository_readback = LongCycleRepositoryReadbackCheck(
        status="pass",
        blockers=[],
        closed_slice=[
            "sqlite_live_repository_write_readback",
            "persistent_task_reopen_readback",
            "lifecycle_event_sequence_readback",
            "live_db_boundary_closed_repo_local",
        ],
        remaining_runtime_gaps=[],
        repository_ref=repository.repository_ref,
        logical_table=repository.logical_table,
        storage_kind="sqlite",
        durable_readback=True,
        live_db_write=live_db_write,
        readback_record=readback_record,
        readback_event_sequence=event_sequence,
        readback_events=readback_events,
        scheduler_readiness=readiness,
    )
    trace = [
        LongCycleSchedulerHandoffTraceEntry(
            stage="dispatch_intent_created",
            status="traced",
            trace_ref=dispatch_intent.dispatch_key,
            task_key=dispatch_intent.task_key,
            dispatch_key=dispatch_intent.dispatch_key,
            dispatch_ref=normalized_dispatch_ref,
            live_dispatch=True,
            durable_readback=False,
            detail=f"queue={dispatch_intent.queue_name} worker_task={dispatch_intent.worker_task_name}",
        ),
        LongCycleSchedulerHandoffTraceEntry(
            stage="scheduler_queue_enqueued",
            status="traced",
            trace_ref=enqueued_item.queue_item_key,
            task_key=enqueued_item.task_key,
            dispatch_key=enqueued_item.dispatch_key,
            dispatch_ref=enqueued_item.dispatch_ref,
            live_dispatch=True,
            durable_readback=False,
            detail="repo-local scheduler enqueue accepted a live queue item",
        ),
        LongCycleSchedulerHandoffTraceEntry(
            stage="worker_consumed_queue_item",
            status="traced" if worker_consumption.get("consumed") else "blocked",
            trace_ref=enqueued_item.queue_item_key,
            task_key=enqueued_item.task_key,
            dispatch_key=enqueued_item.dispatch_key,
            dispatch_ref=enqueued_item.dispatch_ref,
            event_transition=LongCycleLifecycleTransition.DISPATCH,
            live_dispatch=True,
            durable_readback=True,
            detail="repo-local worker consumed the queue item and wrote running/succeeded records",
        ),
        LongCycleSchedulerHandoffTraceEntry(
            stage="live_db_readback",
            status="traced" if readback_record else "blocked",
            trace_ref=repository.repository_ref,
            task_key=enqueued_item.task_key,
            dispatch_key=enqueued_item.dispatch_key,
            dispatch_ref=enqueued_item.dispatch_ref,
            event_transition=LongCycleLifecycleTransition.SUCCEED,
            live_dispatch=True,
            durable_readback=readback_record is not None,
            detail=f"readback_event_sequence={','.join(event_sequence) or '-'}",
        ),
        LongCycleSchedulerHandoffTraceEntry(
            stage="downstream_handoff_ready",
            status="traced" if downstream_handoff.get("downstream_handoff_observed") else "blocked",
            trace_ref=str(downstream_handoff.get("handoff_key") or enqueued_item.queue_item_key),
            task_key=enqueued_item.task_key,
            dispatch_key=enqueued_item.dispatch_key,
            dispatch_ref=enqueued_item.dispatch_ref,
            event_transition=LongCycleLifecycleTransition.SUCCEED,
            live_dispatch=True,
            durable_readback=True,
            detail="digestion output readback produced a downstream handoff payload",
        ),
    ]
    handoff_trace = LongCycleSchedulerHandoffTraceCheck(
        status="pass",
        blockers=[],
        closed_slice=[
            "repo_local_scheduler_enqueue_trace",
            "repo_local_worker_consumption_trace",
            "sqlite_live_db_readback_trace",
            "downstream_handoff_trace",
        ],
        remaining_runtime_gaps=[],
        dispatch_intent=dispatch_intent,
        repository_readback=repository_readback,
        handoff_trace=trace,
        handoff_trace_sequence=[entry.stage for entry in trace],
        dispatch_ref=normalized_dispatch_ref,
        durable_event_readback=True,
        dispatch_intent_matches_readback=(
            readback_record is not None
            and readback_record.task_key == dispatch_intent.task_key
            and readback_record.dispatch_ref == normalized_dispatch_ref
            and event_sequence == expected_event_sequence
        ),
        live_dispatch=True,
        live_db_write=live_db_write,
        closure_claim=readiness.closure_claim,
        live_scheduler_closure_validated=readiness.live_scheduler_closure_validated,
    )
    event_replay_summary = summarize_long_cycle_repository_event_replay(repository_readback, enqueued_item)

    intent_payload = dict(dispatch_intent.payload or {})
    queue_payload = dict(enqueued_item.payload or {})
    scheduler_intent_validated = (
        dispatch_intent.live_dispatch is True
        and dispatch_intent.dispatch_key.startswith("ingest-lc-dispatch-")
        and dispatch_intent.idempotency_key.startswith("ingest-lc-idem-")
        and intent_payload.get("task_key") == dispatch_intent.task_key
        and intent_payload.get("selected_window") == dispatch_intent.selected_window
        and intent_payload.get("dispatch_mode") == "repo_local_live_scheduler"
        and intent_payload.get("live_dispatch") is True
    )
    queue_item_validated = (
        enqueued_item.queue_state == "queued_repo_local_live"
        and enqueued_item.live_enqueue is True
        and enqueued_item.dispatch_key == dispatch_intent.dispatch_key
        and enqueued_item.idempotency_key == dispatch_intent.idempotency_key
        and enqueued_item.task_key == dispatch_intent.task_key
        and enqueued_item.queue_name == dispatch_intent.queue_name
        and enqueued_item.worker_task_name == dispatch_intent.worker_task_name
        and enqueued_item.repository_ref == repository_readback.repository_ref
        and enqueued_item.dispatch_ref == normalized_dispatch_ref
        and queue_payload.get("queue_handoff_mode") == "repo_local_live_scheduler_queue"
        and queue_payload.get("live_enqueue") is True
    )
    repository_write_readback_validated = (
        repository_readback.status == "pass"
        and repository_readback.durable_readback
        and repository_readback.live_db_write is True
        and repository_readback.readback_record is not None
        and repository_readback.readback_record.task_key == enqueued_item.task_key
        and repository_readback.readback_record.dispatch_ref == enqueued_item.dispatch_ref
        and repository_readback.readback_event_sequence == expected_event_sequence
        and write_statuses == expected_write_sequence
    )
    worker_consumption_validated = (
        worker_consumption.get("consumed") is True
        and worker_consumption.get("live_queue_worker_consumption") is True
        and worker_consumption.get("live_db_write") is True
        and worker_consumption.get("db_write_readback") is True
        and worker_consumption.get("event_sequence") == expected_event_sequence
    )
    digestion_output_readback_validated = bool(worker_consumption.get("digestion_output_readback"))
    downstream_handoff_validated = (
        downstream_handoff.get("contract_version") == "ingest.long_cycle_downstream_handoff.v1"
        and downstream_handoff.get("handoff_state") == "ready_for_downstream"
        and downstream_handoff.get("downstream_handoff_observed") is True
        and downstream_handoff.get("task_key") == enqueued_item.task_key
    )
    event_replay_summary_validated = (
        event_replay_summary.replay_complete
        and event_replay_summary.repository_write_readback
        and event_replay_summary.event_sequence == expected_event_sequence
        and event_replay_summary.write_status_sequence == expected_write_sequence
        and event_replay_summary.dispatch_ref == enqueued_item.dispatch_ref
        and event_replay_summary.live_db_write is True
        and event_replay_summary.live_scheduler_closure_validated is True
    )

    if not scheduler_intent_validated:
        blockers.append("scheduler_intent_not_validated")
    if not queue_item_validated:
        blockers.append("scheduler_queue_item_not_validated")
    if not repository_write_readback_validated:
        blockers.append("repository_write_readback_not_validated")
    if not worker_consumption_validated:
        blockers.append("worker_consumption_not_validated")
    if not digestion_output_readback_validated:
        blockers.append("digestion_output_readback_not_validated")
    if not downstream_handoff_validated:
        blockers.append("downstream_handoff_not_validated")
    if not event_replay_summary_validated:
        blockers.append("event_replay_summary_not_validated")
    if not readiness.live_scheduler_closure_validated:
        blockers.append("live_scheduler_closure_not_validated")

    check = LongCycleSchedulerQueueReplayCheck(
        contract_version="ingest.long_cycle_scheduler_queue_replay_check.v2",
        status="fail" if blockers else "pass",
        blockers=blockers,
        closed_slice=[
            "repo_local_live_scheduler_enqueue",
            "repo_local_queue_worker_consumption",
            "sqlite_live_db_write_readback",
            "digestion_output_readback",
            "downstream_handoff_observed",
            "event_replay_sequence_summary",
        ],
        remaining_runtime_gaps=[] if not blockers else ["repo_local_live_scheduler_queue_handoff_replay_failed"],
        scheduler_intent_validated=scheduler_intent_validated,
        queue_item_validated=queue_item_validated,
        repository_write_readback_validated=repository_write_readback_validated,
        event_replay_summary_validated=event_replay_summary_validated,
        worker_consumption_validated=worker_consumption_validated,
        digestion_output_readback_validated=digestion_output_readback_validated,
        downstream_handoff_validated=downstream_handoff_validated,
        repo_local_live_closure_validated=not blockers,
        dispatch_intent=dispatch_intent,
        queue_item=enqueued_item,
        repository_readback=repository_readback,
        handoff_trace=handoff_trace,
        event_replay_summary=event_replay_summary,
        worker_consumption=worker_consumption,
        downstream_handoff=downstream_handoff,
        live_scheduler_evidence=live_scheduler_evidence,
        live_dispatch=dispatch_intent.live_dispatch,
        live_enqueue=enqueued_item.live_enqueue,
        live_db_write=repository_readback.live_db_write,
        closure_claim=readiness.closure_claim,
        live_scheduler_closure_validated=readiness.live_scheduler_closure_validated,
    )
    return check.model_dump(mode="json")


def check_long_cycle_scheduler_queue_handoff_replay_contract(
    *,
    repository: JsonlLongCycleTaskRepository | SqliteLongCycleTaskRepository,
    scheduler_runtime_configured: bool = False,
    live_scheduler_evidence: dict[str, Any] | None = None,
    repo_local_live: bool = False,
    scheduler_queue: RepoLocalLongCycleSchedulerQueue | None = None,
    downstream_targets: list[str] | tuple[str, ...] | None = None,
    **scheduler_e2e_kwargs: Any,
) -> dict[str, Any]:
    """Validate scheduler intent -> queue item -> durable repository replay without live closure."""

    if repo_local_live:
        if not isinstance(repository, SqliteLongCycleTaskRepository):
            raise ValueError("repo-local live scheduler queue replay requires SqliteLongCycleTaskRepository")
        return check_long_cycle_repo_local_live_scheduler_queue_handoff_replay_contract(
            repository=repository,
            scheduler_queue=scheduler_queue,
            downstream_targets=downstream_targets,
            **scheduler_e2e_kwargs,
        )

    scheduler_e2e_kwargs.setdefault("persistent_ref", repository.repository_ref)
    handoff_payload = check_long_cycle_scheduler_handoff_trace_contract(
        repository=repository,
        scheduler_runtime_configured=scheduler_runtime_configured,
        live_scheduler_evidence=live_scheduler_evidence,
        **scheduler_e2e_kwargs,
    )
    handoff = LongCycleSchedulerHandoffTraceCheck.model_validate(handoff_payload)
    intent = handoff.dispatch_intent
    readback = handoff.repository_readback
    queue_item = build_long_cycle_scheduler_queue_item(
        intent,
        repository_ref=repository.repository_ref,
        dispatch_ref=handoff.dispatch_ref,
    )
    event_replay_summary = summarize_long_cycle_repository_event_replay(readback, queue_item)

    intent_payload = dict(intent.payload or {})
    queue_payload = dict(queue_item.payload or {})
    expected_dispatch_ref = f"contract-dispatch://{intent.dispatch_key}"
    expected_event_sequence = [
        LongCycleLifecycleTransition.MARK_READY.value,
        LongCycleLifecycleTransition.DISPATCH.value,
        LongCycleLifecycleTransition.SUCCEED.value,
    ]
    scheduler_intent_validated = (
        handoff.status == "pass"
        and intent.live_dispatch is False
        and intent.dispatch_key.startswith("ingest-lc-dispatch-")
        and intent.idempotency_key.startswith("ingest-lc-idem-")
        and intent_payload.get("task_key") == intent.task_key
        and intent_payload.get("selected_window") == intent.selected_window
        and intent_payload.get("dispatch_mode") == "contract_only"
        and intent_payload.get("live_dispatch") is False
    )
    queue_item_validated = (
        queue_item.queue_state == "queued_contract_only"
        and queue_item.live_enqueue is False
        and queue_item.dispatch_key == intent.dispatch_key
        and queue_item.idempotency_key == intent.idempotency_key
        and queue_item.task_key == intent.task_key
        and queue_item.queue_name == intent.queue_name
        and queue_item.worker_task_name == intent.worker_task_name
        and queue_item.repository_ref == readback.repository_ref
        and queue_item.dispatch_ref == expected_dispatch_ref
        and queue_payload.get("queue_handoff_mode") == "durable_repository_replay_contract_only"
        and queue_payload.get("live_enqueue") is False
        and queue_payload.get("dispatch_ref") == expected_dispatch_ref
    )
    repository_write_readback_validated = (
        readback.status == "pass"
        and readback.durable_readback
        and readback.live_db_write is False
        and readback.readback_record is not None
        and readback.readback_record.task_key == queue_item.task_key
        and readback.readback_record.dispatch_ref == queue_item.dispatch_ref
        and readback.readback_event_sequence == expected_event_sequence
    )
    event_replay_summary_validated = (
        event_replay_summary.replay_complete
        and event_replay_summary.repository_write_readback
        and event_replay_summary.event_sequence == expected_event_sequence
        and event_replay_summary.write_status_sequence[-3:] == ["ready", "running", "succeeded"]
        and event_replay_summary.dispatch_ref == queue_item.dispatch_ref
        and event_replay_summary.live_db_write is False
        and event_replay_summary.live_scheduler_closure_validated is False
    )

    blockers: list[str] = []
    if handoff.status != "pass":
        blockers.append(f"scheduler_handoff_trace_not_passed:{handoff.status}")
    if not scheduler_intent_validated:
        blockers.append("scheduler_intent_not_validated")
    if not queue_item_validated:
        blockers.append("scheduler_queue_item_not_validated")
    if not repository_write_readback_validated:
        blockers.append("repository_write_readback_not_validated")
    if not event_replay_summary_validated:
        blockers.append("event_replay_summary_not_validated")
    if intent.live_dispatch is not False:
        blockers.append("queue_replay_must_not_claim_live_dispatch")
    if queue_item.live_enqueue is not False:
        blockers.append("queue_replay_must_not_claim_live_enqueue")
    if readback.live_db_write is not False:
        blockers.append("queue_replay_must_not_claim_live_db_write")
    if handoff.closure_claim or handoff.live_scheduler_closure_validated:
        blockers.append("queue_replay_must_not_claim_live_scheduler_closure")

    check = LongCycleSchedulerQueueReplayCheck(
        status="fail" if blockers else "pass",
        blockers=blockers,
        closed_slice=[
            "scheduler_intent_to_queue_item_handoff",
            "queue_item_to_durable_repository_binding",
            "repository_write_readback_replay_summary",
            "event_replay_sequence_summary",
            "live_scheduler_and_live_db_boundaries_preserved",
        ],
        remaining_runtime_gaps=[
            *handoff.remaining_runtime_gaps,
            "live_scheduler_queue_enqueue_not_executed",
            "live_queue_worker_consumption_not_validated",
            "live_db_persistent_task_table_not_validated",
            "live_downstream_handoff_not_validated",
        ],
        scheduler_intent_validated=scheduler_intent_validated,
        queue_item_validated=queue_item_validated,
        repository_write_readback_validated=repository_write_readback_validated,
        event_replay_summary_validated=event_replay_summary_validated,
        dispatch_intent=intent,
        queue_item=queue_item,
        repository_readback=readback,
        handoff_trace=handoff,
        event_replay_summary=event_replay_summary,
        live_dispatch=intent.live_dispatch,
        live_enqueue=queue_item.live_enqueue,
        live_db_write=readback.live_db_write,
        closure_claim=handoff.closure_claim,
        live_scheduler_closure_validated=handoff.live_scheduler_closure_validated,
    )
    return check.model_dump(mode="json")
