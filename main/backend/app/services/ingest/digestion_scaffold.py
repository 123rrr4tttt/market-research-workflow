from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from app.contracts.ingest_digestion import (
    ContentFormat,
    DigestionDecision,
    DigestionStage,
    IngestInputKind,
    IngestTimeSemantics,
    NormalizedIngestEnvelope,
)

DEFAULT_DOWNSTREAM_TARGETS = ("resource_pool", "report_generation", "writing")
DEFAULT_CANDIDATE_WINDOWS = ("7d", "30d", "90d")
_WINDOW_RE = re.compile(r"^\d+d$")


def taxonomy_baseline_contract() -> dict[str, list[str]]:
    return {
        "input_kinds": [x.value for x in IngestInputKind],
        "content_formats": [x.value for x in ContentFormat],
        "digestion_stages": [x.value for x in DigestionStage],
        "candidate_windows": list(DEFAULT_CANDIDATE_WINDOWS),
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
    if "single_url" in ep or "url_pool" in ep or "source-library" in ep or "source_library" in ep:
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

    start = task_window_start
    end = task_window_end
    if (start is None) != (end is None):
        raise ValueError("task_window_start and task_window_end must be provided together")
    if start is None and end is None and normalized_window:
        derived = _derive_window_bounds(normalized_window, anchor_day=normalized_processed.date())
        if derived:
            start, end = derived
    if start and end and start > end:
        raise ValueError("task_window_start must be <= task_window_end")

    return IngestTimeSemantics(
        source_time=normalized_source,
        processed_time=normalized_processed,
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
