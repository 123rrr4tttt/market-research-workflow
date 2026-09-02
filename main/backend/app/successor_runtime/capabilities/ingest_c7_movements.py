"""Pure C7 raw-content digestion movements and deterministic interpreters.

This module implements the corrected C7.1 semantic prefix:

    RawSnapshot -> NormalizedIngestEnvelope -> DigestionDecision
        -> exactly one branch -> StructuredMaterialCandidate
        -> VerifiedMaterialCandidate (verification only)

The implementation is deterministic, provider-zero and write-zero.  It does
not import legacy services or runtime VerificationBinding, perform
network/database/provider work, create a canonical document, or claim
promotion/authority transfer.
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol, TypeAlias

from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
    sha256_hex,
)

__all__ = [
    "C7_ALTERNATIVES",
    "C7_CHUNK_MAX_BYTES",
    "C7_CHUNK_MAX_COUNT",
    "C7_DECISION_PROFILE_REF",
    "C7_DEFAULT_DOWNSTREAM_TARGETS",
    "C7_LONG_CONTENT_FORMATS",
    "C7_LONG_REPORT_MIN_LENGTH",
    "C7_MAX_STRUCTURED_PAYLOAD_BYTES",
    "C7_NEW_ATTEMPT_POLICY",
    "C7_NORMALIZATION_ONLY_LOSS",
    "C7_NORMALIZATION_PROFILE_REF",
    "C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF",
    "C7_PURE_SCHEMA",
    "C7_STAGING_ONLY_AUTHORITY",
    "C7_VERIFICATION_PROFILE_REF",
    "C7Deferred",
    "C7MovementTrace",
    "C7PortResult",
    "C7Rejected",
    "C7ReverseReturn",
    "C7VerifyResult",
    "ChunkPort",
    "DeterministicChunkPort",
    "DeterministicExtractPort",
    "DeterministicPassThroughPort",
    "DeterministicSummarizePort",
    "DigestionDecision",
    "ExtractPort",
    "NormalizedIngestEnvelope",
    "PassThroughPort",
    "RawSnapshot",
    "StagingAuthority",
    "StructuredMaterialCandidate",
    "SummarizePort",
    "VerifiedMaterialCandidate",
    "capture_raw_snapshot_exact",
    "execute_c7_movement",
    "normalize_ingest_envelope",
    "return_for_cleanup",
    "select_exactly_one_digestion_alternative",
    "verify_structured_candidate",
]


C7_PURE_SCHEMA = "mrw.successor.ingest-c7.pure-movements.v1"
C7_ALTERNATIVES: tuple[str, ...] = (
    "EXTRACT",
    "CHUNK",
    "SUMMARIZE",
    "PASS_THROUGH",
)
C7_INPUT_KINDS: tuple[str, ...] = (
    "url_driven_external",
    "raw_import",
    "report_shaped",
    "derived_llm_report",
    "derived_writing_markdown",
    "unknown",
)
C7_CONTENT_FORMATS: tuple[str, ...] = (
    "plain_text",
    "markdown",
    "html",
    "pdf",
    "structured_json",
    "other",
)
C7_LONG_CONTENT_FORMATS: tuple[str, ...] = (
    "plain_text",
    "markdown",
    "html",
    "pdf",
)
C7_LONG_REPORT_MIN_LENGTH = 6000
C7_DEFAULT_DOWNSTREAM_TARGETS: tuple[str, ...] = (
    "resource_pool",
    "report_generation",
    "writing",
)
C7_DECISION_PROFILE_REF = "mrw.successor.ingest-c7.digestion-decision.v1"
C7_VERIFICATION_PROFILE_REF = "mrw.successor.ingest-c7.verification.v1"
C7_NORMALIZATION_PROFILE_REF = "mrw.successor.ingest-c7.normalization.v1"
C7_NORMALIZATION_ONLY_LOSS = "normalization_only"
C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF = (
    "mrw.successor.ingest-c7.provider-enrichment-declared-loss.v1"
)
C7_STAGING_ONLY_AUTHORITY = "staging_only_no_document_write"
C7_NEW_ATTEMPT_POLICY = "forbidden_without_exact_nonstart_proof_and_current_authority"
C7_CHUNK_MAX_BYTES = 4096
C7_CHUNK_MAX_COUNT = 32
C7_MAX_STRUCTURED_PAYLOAD_BYTES = 1_000_000
C7_MAX_PASS_THROUGH_BYTES = 1_000_000
C7_DEFAULT_SUMMARY_LENGTH = 512
C7_SOURCE_TIME_FUTURE_TOLERANCE_DAYS = 1

_DERIVED_INPUT_KINDS = frozenset({"derived_llm_report", "derived_writing_markdown"})
_BRANCH_INTERNAL_EXTRACT = ("extract_required",)


class StagingAuthority(str, Enum):
    """Closed staging-only authority enum; caller text is never accepted."""

    STAGING_ONLY_NO_DOCUMENT_WRITE = C7_STAGING_ONLY_AUTHORITY


def _strip(value: str, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def _optional_strip(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _normalize_optional_refs(
    values: tuple[str, ...] | list[str] | None,
    name: str,
) -> tuple[str, ...]:
    """Strip and drop empties while preserving caller order and duplicates."""

    out: list[str] = []
    for item in values or ():
        normalized = str(item or "").strip()
        if normalized:
            out.append(normalized)
    return tuple(out)


def _normalize_required_refs(
    values: tuple[str, ...] | list[str] | None,
    name: str,
) -> tuple[str, ...]:
    out = _normalize_optional_refs(values, name)
    if not out:
        raise ValueError(f"{name} must contain at least one ref")
    return out


def _normalize_iso_timestamp(
    value: str | None,
    name: str,
    *,
    required: bool = False,
) -> str | None:
    if value is None or not str(value).strip():
        if required:
            raise ValueError(f"{name} is required")
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{name} is not an ISO timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat()


def _collapse_whitespace(value: str) -> str:
    return " ".join(str(value or "").split())


def _digest_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _object_digest(instance: Any, exclude: str) -> str:
    return content_digest(
        {
            key: _digest_value(value)
            for key, value in dataclasses.asdict(instance).items()
            if key != exclude
        }
    )


def _assert_pure_effect_flags(
    *,
    provider_calls: int,
    canonical_write: bool,
    external_delivery: bool,
    cutover: bool,
    authority_transfer: bool,
) -> None:
    if int(provider_calls or 0) != 0:
        raise ValueError("pure C7 movement may not count provider calls")
    if canonical_write is not False:
        raise ValueError("pure C7 movement may not claim canonical write")
    if external_delivery is not False:
        raise ValueError("pure C7 movement may not claim external delivery")
    if cutover is not False:
        raise ValueError("pure C7 movement may not claim cutover")
    if authority_transfer is not False:
        raise ValueError("pure C7 movement may not claim authority transfer")


def _require_hex64(value: str, name: str) -> None:
    require_hex64(str(value or ""), name)


@dataclass(frozen=True, slots=True)
class RawSnapshot:
    """Exact immutable input bytes bound to a full non-prefix C7 identity."""

    project_key: str
    source_locator: str
    raw_bytes: bytes
    raw_content_digest: str = ""
    revision: int = 1
    incarnation: str = "c7-raw-v1"
    mime_type: str = "application/octet-stream"
    provenance_refs: tuple[str, ...] = ()
    snapshot_identity_digest: str = ""
    snapshot_ref: str = ""

    def __post_init__(self) -> None:
        project_key = _strip(self.project_key, "RawSnapshot.project_key")
        source_locator = _strip(self.source_locator, "RawSnapshot.source_locator")
        if not isinstance(self.raw_bytes, bytes):
            raise TypeError("RawSnapshot.raw_bytes must be bytes")
        revision = int(self.revision)
        if revision < 1:
            raise ValueError("RawSnapshot.revision must be >= 1")
        incarnation = _strip(self.incarnation, "RawSnapshot.incarnation")
        mime_type = _strip(
            self.mime_type or "application/octet-stream",
            "RawSnapshot.mime_type",
        )
        provenance_refs = _normalize_optional_refs(
            self.provenance_refs, "RawSnapshot.provenance_refs"
        )
        computed = sha256_hex(self.raw_bytes)
        raw_content_digest = self.raw_content_digest or computed
        raw_content_digest = _strip(
            raw_content_digest, "RawSnapshot.raw_content_digest"
        )
        require_hex64(raw_content_digest, "RawSnapshot.raw_content_digest")
        if raw_content_digest != computed:
            raise ValueError("RawSnapshot.raw_content_digest does not match raw bytes")
        identity = content_digest(
            {
                "project_key": project_key,
                "source_locator": source_locator,
                "raw_content_digest": raw_content_digest,
                "revision": revision,
                "incarnation": incarnation,
                "mime_type": mime_type,
                "provenance_refs": provenance_refs,
            }
        )
        if self.snapshot_identity_digest and self.snapshot_identity_digest != identity:
            raise ValueError(
                "RawSnapshot.snapshot_identity_digest does not match identity fields"
            )
        snapshot_ref = f"raw:c7:sha256:{identity}"
        if self.snapshot_ref and self.snapshot_ref != snapshot_ref:
            raise ValueError("RawSnapshot.snapshot_ref does not match full identity")
        object.__setattr__(self, "project_key", project_key)
        object.__setattr__(self, "source_locator", source_locator)
        object.__setattr__(self, "revision", revision)
        object.__setattr__(self, "incarnation", incarnation)
        object.__setattr__(self, "mime_type", mime_type)
        object.__setattr__(self, "provenance_refs", provenance_refs)
        object.__setattr__(self, "raw_content_digest", raw_content_digest)
        object.__setattr__(self, "snapshot_identity_digest", identity)
        object.__setattr__(self, "snapshot_ref", snapshot_ref)

    @property
    def content_digest(self) -> str:
        """Legacy alias for the full raw content digest."""

        return self.raw_content_digest


def capture_raw_snapshot_exact(
    *,
    project_key: str,
    source_locator: str,
    raw_bytes: bytes,
    supplied_digest: str | None = None,
    revision: int = 1,
    incarnation: str,
    mime_type: str = "application/octet-stream",
    provenance_refs: tuple[str, ...] | None = None,
    supplied_identity_digest: str | None = None,
    supplied_snapshot_ref: str | None = None,
) -> RawSnapshot:
    """Capture exact raw bytes; any supplied digest/ref must equal the bytes."""

    return RawSnapshot(
        project_key=project_key,
        source_locator=source_locator,
        raw_bytes=raw_bytes,
        raw_content_digest=supplied_digest or "",
        revision=revision,
        incarnation=incarnation,
        mime_type=mime_type,
        provenance_refs=provenance_refs or (),
        snapshot_identity_digest=supplied_identity_digest or "",
        snapshot_ref=supplied_snapshot_ref or "",
    )


@dataclass(frozen=True, slots=True)
class NormalizedIngestEnvelope:
    """Normalized envelope bound to one exact full snapshot identity."""

    snapshot_ref: str
    snapshot_identity_digest: str
    raw_content_digest: str
    raw_byte_length: int
    source_character_length: int
    project_key: str
    source_locator: str
    input_kind: str
    content_format: str
    normalized_text: str
    source_time: str | None = None
    processed_time: str = "1970-01-01T00:00:00+00:00"
    effective_time: str | None = None
    time_provenance: str = "processed_time_fallback"
    time_parse_version: str = "source-time-window-v1"
    lineage_ref: str | None = None
    requested_downstream_targets: tuple[str, ...] = C7_DEFAULT_DOWNSTREAM_TARGETS
    normalization_profile_ref: str = C7_NORMALIZATION_PROFILE_REF
    normalization_loss: str = C7_NORMALIZATION_ONLY_LOSS
    envelope_digest: str = ""

    def __post_init__(self) -> None:
        snapshot_ref = _strip(
            self.snapshot_ref, "NormalizedIngestEnvelope.snapshot_ref"
        )
        require_hex64(
            self.snapshot_identity_digest,
            "NormalizedIngestEnvelope.snapshot_identity_digest",
        )
        require_hex64(
            self.raw_content_digest,
            "NormalizedIngestEnvelope.raw_content_digest",
        )
        raw_byte_length = int(self.raw_byte_length)
        if raw_byte_length < 0:
            raise ValueError("NormalizedIngestEnvelope.raw_byte_length must be >= 0")
        source_character_length = int(self.source_character_length)
        if source_character_length < 0:
            raise ValueError(
                "NormalizedIngestEnvelope.source_character_length must be >= 0"
            )
        project_key = _strip(self.project_key, "NormalizedIngestEnvelope.project_key")
        source_locator = _strip(
            self.source_locator, "NormalizedIngestEnvelope.source_locator"
        )
        input_kind = _strip(self.input_kind, "NormalizedIngestEnvelope.input_kind")
        if input_kind not in C7_INPUT_KINDS:
            raise ValueError(f"unsupported C7 input kind: {input_kind}")
        content_format = _strip(
            self.content_format,
            "NormalizedIngestEnvelope.content_format",
        )
        if content_format not in C7_CONTENT_FORMATS:
            raise ValueError(f"unsupported C7 content format: {content_format}")
        normalized_text = str(self.normalized_text or "")
        source_time = _normalize_iso_timestamp(
            self.source_time, "NormalizedIngestEnvelope.source_time"
        )
        processed_time = _normalize_iso_timestamp(
            self.processed_time or "1970-01-01T00:00:00+00:00",
            "NormalizedIngestEnvelope.processed_time",
            required=True,
        )
        source_datetime = (
            datetime.fromisoformat(source_time) if source_time is not None else None
        )
        processed_datetime = datetime.fromisoformat(processed_time)
        tolerance = timedelta(days=C7_SOURCE_TIME_FUTURE_TOLERANCE_DAYS)
        if source_datetime is None:
            derived_effective = processed_time
            derived_provenance = "processed_time_fallback"
        elif source_datetime <= processed_datetime + tolerance:
            derived_effective = source_time
            derived_provenance = "source_time"
        else:
            derived_effective = processed_time
            derived_provenance = "source_time_future_rejected"
        effective_raw = self.effective_time
        if effective_raw is None or not str(effective_raw).strip():
            effective_raw = derived_effective
        effective_time = _normalize_iso_timestamp(
            effective_raw,
            "NormalizedIngestEnvelope.effective_time",
            required=True,
        )
        if effective_time != derived_effective:
            raise ValueError(
                "NormalizedIngestEnvelope.effective_time must equal the derived "
                "legacy time value"
            )
        time_provenance = _strip(
            self.time_provenance or derived_provenance,
            "NormalizedIngestEnvelope.time_provenance",
        )
        if time_provenance != derived_provenance:
            raise ValueError(
                "NormalizedIngestEnvelope.time_provenance must equal the derived "
                "legacy provenance"
            )
        time_parse_version = _strip(
            self.time_parse_version or "source-time-window-v1",
            "NormalizedIngestEnvelope.time_parse_version",
        )
        lineage_ref = _optional_strip(self.lineage_ref)
        targets: list[str] = []
        seen: set[str] = set()
        for item in self.requested_downstream_targets or ():
            normalized = str(item or "").strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                targets.append(normalized)
        normalization_profile_ref = _strip(
            self.normalization_profile_ref or C7_NORMALIZATION_PROFILE_REF,
            "NormalizedIngestEnvelope.normalization_profile_ref",
        )
        normalization_loss = _strip(
            self.normalization_loss or C7_NORMALIZATION_ONLY_LOSS,
            "NormalizedIngestEnvelope.normalization_loss",
        )
        if normalization_loss != C7_NORMALIZATION_ONLY_LOSS:
            raise ValueError(
                "NormalizedIngestEnvelope.normalization_loss must be normalization_only"
            )
        object.__setattr__(self, "snapshot_ref", snapshot_ref)
        object.__setattr__(self, "raw_byte_length", raw_byte_length)
        object.__setattr__(self, "source_character_length", source_character_length)
        object.__setattr__(self, "project_key", project_key)
        object.__setattr__(self, "source_locator", source_locator)
        object.__setattr__(self, "input_kind", input_kind)
        object.__setattr__(self, "content_format", content_format)
        object.__setattr__(self, "normalized_text", normalized_text)
        object.__setattr__(self, "source_time", source_time)
        object.__setattr__(self, "processed_time", processed_time)
        object.__setattr__(self, "effective_time", effective_time)
        object.__setattr__(self, "time_provenance", time_provenance)
        object.__setattr__(self, "time_parse_version", time_parse_version)
        object.__setattr__(self, "lineage_ref", lineage_ref)
        object.__setattr__(self, "requested_downstream_targets", tuple(targets))
        object.__setattr__(self, "normalization_profile_ref", normalization_profile_ref)
        object.__setattr__(self, "normalization_loss", normalization_loss)
        digest = _object_digest(self, "envelope_digest")
        if self.envelope_digest and self.envelope_digest != digest:
            raise ValueError(
                "NormalizedIngestEnvelope.envelope_digest does not match fields"
            )
        object.__setattr__(self, "envelope_digest", digest)


def normalize_ingest_envelope(
    *,
    snapshot: RawSnapshot,
    input_kind: str,
    content_format: str,
    text: str | None = None,
    source_time: str | None = None,
    processed_time: str | None = None,
    effective_time: str | None = None,
    time_provenance: str | None = None,
    time_parse_version: str | None = None,
    lineage_ref: str | None = None,
    requested_downstream_targets: tuple[str, ...] | None = None,
) -> NormalizedIngestEnvelope:
    """Build one normalized envelope bound to the exact RawSnapshot identity."""

    if not isinstance(snapshot, RawSnapshot):
        raise TypeError("snapshot must be a RawSnapshot")
    try:
        decoded = snapshot.raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "RawSnapshot bytes must be UTF-8 decodable for envelope normalization"
        ) from exc
    if text is not None and str(text) != decoded:
        raise ValueError("text override must equal the exact raw UTF-8 decode")
    decoded = str(text) if text is not None else decoded
    if processed_time is None and source_time is not None:
        processed_time = source_time
    if content_format == "structured_json":
        normalized = decoded.strip()
    else:
        normalized = _collapse_whitespace(decoded)
    targets = (
        tuple(requested_downstream_targets)
        if requested_downstream_targets is not None
        else C7_DEFAULT_DOWNSTREAM_TARGETS
    )
    return NormalizedIngestEnvelope(
        snapshot_ref=snapshot.snapshot_ref,
        snapshot_identity_digest=snapshot.snapshot_identity_digest,
        raw_content_digest=snapshot.raw_content_digest,
        raw_byte_length=len(snapshot.raw_bytes),
        source_character_length=len(decoded),
        project_key=snapshot.project_key,
        source_locator=snapshot.source_locator,
        input_kind=input_kind,
        content_format=content_format,
        normalized_text=normalized,
        source_time=source_time,
        processed_time=processed_time,
        effective_time=effective_time,
        time_provenance=time_provenance,
        time_parse_version=time_parse_version,
        lineage_ref=lineage_ref,
        requested_downstream_targets=targets,
    )


@dataclass(frozen=True, slots=True)
class DigestionDecision:
    """Exactly one alternative bound to the envelope and legacy char length."""

    envelope_digest: str
    raw_byte_length: int
    source_character_length: int
    alternative: str
    reason: str
    branch_internal_structuring: tuple[str, ...] = ()
    profile_ref: str = C7_DECISION_PROFILE_REF
    decision_digest: str = ""

    def __post_init__(self) -> None:
        require_hex64(self.envelope_digest, "DigestionDecision.envelope_digest")
        raw_byte_length = int(self.raw_byte_length)
        if raw_byte_length < 0:
            raise ValueError("DigestionDecision.raw_byte_length must be >= 0")
        source_character_length = int(self.source_character_length)
        if source_character_length < 0:
            raise ValueError("DigestionDecision.source_character_length must be >= 0")
        alternative = _strip(self.alternative, "DigestionDecision.alternative")
        if alternative not in C7_ALTERNATIVES:
            raise ValueError(f"unsupported C7 alternative: {alternative}")
        reason = _strip(self.reason, "DigestionDecision.reason")
        structuring = tuple(self.branch_internal_structuring or ())
        if structuring not in ((), _BRANCH_INTERNAL_EXTRACT):
            raise ValueError(
                "DigestionDecision.branch_internal_structuring is out of scope"
            )
        if alternative not in {"CHUNK", "SUMMARIZE"} and structuring:
            raise ValueError(
                "branch-internal extract_required is only valid inside CHUNK/SUMMARIZE"
            )
        profile_ref = _strip(self.profile_ref, "DigestionDecision.profile_ref")
        object.__setattr__(self, "raw_byte_length", raw_byte_length)
        object.__setattr__(self, "source_character_length", source_character_length)
        object.__setattr__(self, "alternative", alternative)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "branch_internal_structuring", structuring)
        object.__setattr__(self, "profile_ref", profile_ref)
        digest = _object_digest(self, "decision_digest")
        if self.decision_digest and self.decision_digest != digest:
            raise ValueError("DigestionDecision.decision_digest does not match fields")
        object.__setattr__(self, "decision_digest", digest)


def _is_chunk_mode(envelope: NormalizedIngestEnvelope) -> bool:
    if envelope.input_kind == "report_shaped":
        return True
    return (
        envelope.source_character_length >= C7_LONG_REPORT_MIN_LENGTH
        and envelope.content_format in C7_LONG_CONTENT_FORMATS
    )


def _branch_internal_structuring(alternative: str) -> tuple[str, ...]:
    if alternative in {"CHUNK", "SUMMARIZE"}:
        return _BRANCH_INTERNAL_EXTRACT
    return ()


def _provider_enrichment_declared_loss_structure() -> dict[str, Any]:
    return {
        "extract_required": {
            "formation": "deterministic_branch_internal_structure_v1",
            "provider_model_enrichment": "DECLARED_LOSS",
            "loss_profile_ref": C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF,
            "provider_calls": 0,
        }
    }


def select_exactly_one_digestion_alternative(
    envelope: NormalizedIngestEnvelope,
) -> DigestionDecision:
    """Deterministically select exactly one branch, never a boolean mix."""

    if not isinstance(envelope, NormalizedIngestEnvelope):
        raise TypeError("envelope must be a NormalizedIngestEnvelope")
    if envelope.content_format == "structured_json":
        alternative = "EXTRACT"
        reason = "structured_json_prefers_direct_extraction"
    elif envelope.input_kind in _DERIVED_INPUT_KINDS:
        alternative = "SUMMARIZE"
        reason = (
            "derived_artifact_requires_summary_with_provider_enrichment_declared_loss"
        )
    elif _is_chunk_mode(envelope):
        alternative = "CHUNK"
        reason = "long_or_report_shaped_input_needs_chunking_with_provider_enrichment_declared_loss"
    else:
        alternative = "PASS_THROUGH"
        reason = "safe_default_no_forced_preprocessing"
    return DigestionDecision(
        envelope_digest=envelope.envelope_digest,
        raw_byte_length=envelope.raw_byte_length,
        source_character_length=envelope.source_character_length,
        alternative=alternative,
        reason=reason,
        branch_internal_structuring=_branch_internal_structuring(alternative),
    )


@dataclass(frozen=True, slots=True)
class StructuredMaterialCandidate:
    """One staged candidate bound to the complete input closure."""

    candidate_id: str
    project_key: str
    snapshot_ref: str
    snapshot_identity_digest: str
    raw_content_digest: str
    envelope_digest: str
    alternative: str
    decision_digest: str
    ordered_source_refs: tuple[str, ...]
    structured_payload: Mapping[str, Any]
    provenance_closure: tuple[str, ...]
    payload_content_digest: str = ""
    ordered_source_closure_digest: str = ""
    provenance_closure_digest: str = ""
    failure_loss_profile: str = "no_declared_loss"
    authority: StagingAuthority = StagingAuthority.STAGING_ONLY_NO_DOCUMENT_WRITE
    payload_ref: str = ""
    candidate_digest: str = ""

    def __post_init__(self) -> None:
        candidate_id = _strip(
            self.candidate_id, "StructuredMaterialCandidate.candidate_id"
        )
        project_key = _strip(
            self.project_key, "StructuredMaterialCandidate.project_key"
        )
        snapshot_ref = _strip(
            self.snapshot_ref, "StructuredMaterialCandidate.snapshot_ref"
        )
        require_hex64(
            self.snapshot_identity_digest,
            "StructuredMaterialCandidate.snapshot_identity_digest",
        )
        require_hex64(
            self.raw_content_digest,
            "StructuredMaterialCandidate.raw_content_digest",
        )
        require_hex64(
            self.envelope_digest,
            "StructuredMaterialCandidate.envelope_digest",
        )
        alternative = _strip(
            self.alternative, "StructuredMaterialCandidate.alternative"
        )
        if alternative not in C7_ALTERNATIVES:
            raise ValueError(f"unsupported C7 alternative: {alternative}")
        require_hex64(
            self.decision_digest,
            "StructuredMaterialCandidate.decision_digest",
        )
        ordered_source_refs = _normalize_required_refs(
            self.ordered_source_refs,
            "StructuredMaterialCandidate.ordered_source_refs",
        )
        if not isinstance(self.structured_payload, Mapping):
            raise TypeError(
                "StructuredMaterialCandidate.structured_payload must be a mapping"
            )
        structured_payload = dict(self.structured_payload)
        provenance_closure = _normalize_required_refs(
            self.provenance_closure,
            "StructuredMaterialCandidate.provenance_closure",
        )
        payload_content_digest = self.payload_content_digest or content_digest(
            structured_payload
        )
        require_hex64(
            payload_content_digest,
            "StructuredMaterialCandidate.payload_content_digest",
        )
        if payload_content_digest != content_digest(structured_payload):
            raise ValueError(
                "StructuredMaterialCandidate.payload_content_digest does not match "
                "the structured payload"
            )
        ordered_source_closure_digest = (
            self.ordered_source_closure_digest or content_digest(ordered_source_refs)
        )
        require_hex64(
            ordered_source_closure_digest,
            "StructuredMaterialCandidate.ordered_source_closure_digest",
        )
        if ordered_source_closure_digest != content_digest(ordered_source_refs):
            raise ValueError(
                "StructuredMaterialCandidate.ordered_source_closure_digest does not "
                "match ordered source refs"
            )
        provenance_closure_digest = self.provenance_closure_digest or content_digest(
            provenance_closure
        )
        require_hex64(
            provenance_closure_digest,
            "StructuredMaterialCandidate.provenance_closure_digest",
        )
        if provenance_closure_digest != content_digest(provenance_closure):
            raise ValueError(
                "StructuredMaterialCandidate.provenance_closure_digest does not "
                "match provenance closure"
            )
        failure_loss_profile = _strip(
            self.failure_loss_profile or "no_declared_loss",
            "StructuredMaterialCandidate.failure_loss_profile",
        )
        if not isinstance(self.authority, StagingAuthority):
            raise TypeError(
                "StructuredMaterialCandidate.authority must be the closed "
                "staging-only enum"
            )
        authority = self.authority
        payload_ref = self.payload_ref or f"payload:c7:{candidate_id}"
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "project_key", project_key)
        object.__setattr__(self, "snapshot_ref", snapshot_ref)
        object.__setattr__(self, "alternative", alternative)
        object.__setattr__(self, "ordered_source_refs", ordered_source_refs)
        object.__setattr__(self, "structured_payload", structured_payload)
        object.__setattr__(self, "provenance_closure", provenance_closure)
        object.__setattr__(self, "payload_content_digest", payload_content_digest)
        object.__setattr__(
            self,
            "ordered_source_closure_digest",
            ordered_source_closure_digest,
        )
        object.__setattr__(self, "provenance_closure_digest", provenance_closure_digest)
        object.__setattr__(self, "failure_loss_profile", failure_loss_profile)
        object.__setattr__(self, "authority", authority)
        object.__setattr__(self, "payload_ref", payload_ref)
        digest = _object_digest(self, "candidate_digest")
        if self.candidate_digest and self.candidate_digest != digest:
            raise ValueError(
                "StructuredMaterialCandidate.candidate_digest does not match fields"
            )
        object.__setattr__(self, "candidate_digest", digest)

    @property
    def normalized_envelope_digest(self) -> str:
        """Legacy alias for the bound envelope digest."""

        return self.envelope_digest


@dataclass(frozen=True, slots=True)
class C7Rejected:
    """Typed terminal rejection retaining source/candidate identity."""

    failure_code: str
    reason: str
    snapshot_ref: str
    candidate_ref: str | None = None
    provider_calls: int = 0
    canonical_write: bool = False
    external_delivery: bool = False
    cutover: bool = False
    authority_transfer: bool = False
    rejected_digest: str = ""

    def __post_init__(self) -> None:
        failure_code = _strip(self.failure_code, "C7Rejected.failure_code")
        reason = _strip(self.reason, "C7Rejected.reason")
        snapshot_ref = _strip(self.snapshot_ref, "C7Rejected.snapshot_ref")
        candidate_ref = _optional_strip(self.candidate_ref)
        _assert_pure_effect_flags(
            provider_calls=self.provider_calls,
            canonical_write=self.canonical_write,
            external_delivery=self.external_delivery,
            cutover=self.cutover,
            authority_transfer=self.authority_transfer,
        )
        object.__setattr__(self, "failure_code", failure_code)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "snapshot_ref", snapshot_ref)
        object.__setattr__(self, "candidate_ref", candidate_ref)
        object.__setattr__(self, "provider_calls", int(self.provider_calls))
        digest = _object_digest(self, "rejected_digest")
        if self.rejected_digest and self.rejected_digest != digest:
            raise ValueError("C7Rejected.rejected_digest does not match fields")
        object.__setattr__(self, "rejected_digest", digest)


@dataclass(frozen=True, slots=True)
class C7Deferred:
    """Typed terminal deferral retaining source/candidate identity."""

    failure_code: str
    reason: str
    snapshot_ref: str
    candidate_ref: str | None = None
    provider_calls: int = 0
    canonical_write: bool = False
    external_delivery: bool = False
    cutover: bool = False
    authority_transfer: bool = False
    deferred_digest: str = ""

    def __post_init__(self) -> None:
        failure_code = _strip(self.failure_code, "C7Deferred.failure_code")
        reason = _strip(self.reason, "C7Deferred.reason")
        snapshot_ref = _strip(self.snapshot_ref, "C7Deferred.snapshot_ref")
        candidate_ref = _optional_strip(self.candidate_ref)
        _assert_pure_effect_flags(
            provider_calls=self.provider_calls,
            canonical_write=self.canonical_write,
            external_delivery=self.external_delivery,
            cutover=self.cutover,
            authority_transfer=self.authority_transfer,
        )
        object.__setattr__(self, "failure_code", failure_code)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "snapshot_ref", snapshot_ref)
        object.__setattr__(self, "candidate_ref", candidate_ref)
        object.__setattr__(self, "provider_calls", int(self.provider_calls))
        digest = _object_digest(self, "deferred_digest")
        if self.deferred_digest and self.deferred_digest != digest:
            raise ValueError("C7Deferred.deferred_digest does not match fields")
        object.__setattr__(self, "deferred_digest", digest)


C7PortResult: TypeAlias = StructuredMaterialCandidate | C7Rejected | C7Deferred


@dataclass(frozen=True, slots=True)
class VerifiedMaterialCandidate:
    """Concrete verified candidate; no canonical write is ever authorized."""

    candidate_id: str
    candidate_digest: str
    envelope_digest: str
    snapshot_ref: str
    snapshot_identity_digest: str
    raw_content_digest: str
    payload_content_digest: str
    ordered_source_closure_digest: str
    provenance_closure_digest: str
    decision_digest: str
    alternative: str
    project_key: str
    canonical_object_id: str
    expected_base_revision: int
    expected_base_incarnation: str
    actor: str
    authority_digest: str
    authority_epoch: int
    verification_profile_ref: str
    verification_receipt: str = ""
    provider_calls: int = 0
    canonical_write_authorized: bool = False
    verification_digest: str = ""

    def __post_init__(self) -> None:
        candidate_id = _strip(
            self.candidate_id, "VerifiedMaterialCandidate.candidate_id"
        )
        require_hex64(
            self.candidate_digest, "VerifiedMaterialCandidate.candidate_digest"
        )
        require_hex64(self.envelope_digest, "VerifiedMaterialCandidate.envelope_digest")
        snapshot_ref = _strip(
            self.snapshot_ref, "VerifiedMaterialCandidate.snapshot_ref"
        )
        require_hex64(
            self.snapshot_identity_digest,
            "VerifiedMaterialCandidate.snapshot_identity_digest",
        )
        require_hex64(
            self.raw_content_digest,
            "VerifiedMaterialCandidate.raw_content_digest",
        )
        require_hex64(
            self.payload_content_digest,
            "VerifiedMaterialCandidate.payload_content_digest",
        )
        require_hex64(
            self.ordered_source_closure_digest,
            "VerifiedMaterialCandidate.ordered_source_closure_digest",
        )
        require_hex64(
            self.provenance_closure_digest,
            "VerifiedMaterialCandidate.provenance_closure_digest",
        )
        require_hex64(self.decision_digest, "VerifiedMaterialCandidate.decision_digest")
        alternative = _strip(self.alternative, "VerifiedMaterialCandidate.alternative")
        if alternative not in C7_ALTERNATIVES:
            raise ValueError(f"unsupported C7 alternative: {alternative}")
        project_key = _strip(self.project_key, "VerifiedMaterialCandidate.project_key")
        canonical_object_id = _strip(
            self.canonical_object_id, "VerifiedMaterialCandidate.canonical_object_id"
        )
        expected_base_revision = int(self.expected_base_revision)
        if expected_base_revision < 0:
            raise ValueError(
                "VerifiedMaterialCandidate.expected_base_revision must be >= 0"
            )
        expected_base_incarnation = _strip(
            self.expected_base_incarnation,
            "VerifiedMaterialCandidate.expected_base_incarnation",
        )
        actor = _strip(self.actor, "VerifiedMaterialCandidate.actor")
        require_hex64(
            self.authority_digest, "VerifiedMaterialCandidate.authority_digest"
        )
        authority_epoch = int(self.authority_epoch)
        if authority_epoch < 1:
            raise ValueError("VerifiedMaterialCandidate.authority_epoch must be >= 1")
        verification_profile_ref = _strip(
            self.verification_profile_ref,
            "VerifiedMaterialCandidate.verification_profile_ref",
        )
        verification_receipt = self.verification_receipt or (
            f"verify:c7:{candidate_id}:{authority_epoch}"
        )
        if self.provider_calls != 0:
            raise ValueError("pure C7 verification may not count provider calls")
        if self.canonical_write_authorized is not False:
            raise ValueError("C7 verification grants no canonical write")
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "snapshot_ref", snapshot_ref)
        object.__setattr__(self, "alternative", alternative)
        object.__setattr__(self, "project_key", project_key)
        object.__setattr__(self, "canonical_object_id", canonical_object_id)
        object.__setattr__(self, "expected_base_revision", expected_base_revision)
        object.__setattr__(self, "expected_base_incarnation", expected_base_incarnation)
        object.__setattr__(self, "actor", actor)
        object.__setattr__(self, "authority_epoch", authority_epoch)
        object.__setattr__(self, "verification_profile_ref", verification_profile_ref)
        object.__setattr__(self, "verification_receipt", verification_receipt)
        digest = _object_digest(self, "verification_digest")
        if self.verification_digest and self.verification_digest != digest:
            raise ValueError(
                "VerifiedMaterialCandidate.verification_digest does not match fields"
            )
        object.__setattr__(self, "verification_digest", digest)


C7VerifyResult: TypeAlias = VerifiedMaterialCandidate | C7Rejected | C7Deferred


def _require_snapshot_identity(snapshot: RawSnapshot) -> None:
    if snapshot.snapshot_identity_digest != content_digest(
        {
            "project_key": snapshot.project_key,
            "source_locator": snapshot.source_locator,
            "raw_content_digest": snapshot.raw_content_digest,
            "revision": snapshot.revision,
            "incarnation": snapshot.incarnation,
            "mime_type": snapshot.mime_type,
            "provenance_refs": snapshot.provenance_refs,
        }
    ):
        raise ValueError("RawSnapshot.snapshot_identity_digest is not current")
    if snapshot.raw_content_digest != sha256_hex(snapshot.raw_bytes):
        raise ValueError("RawSnapshot.raw_content_digest does not match raw bytes")


def _require_envelope_digest(envelope: NormalizedIngestEnvelope) -> None:
    if envelope.envelope_digest != _object_digest(envelope, "envelope_digest"):
        raise ValueError("envelope digest does not match its fields")


def _require_decision_digest(decision: DigestionDecision) -> None:
    if decision.decision_digest != _object_digest(decision, "decision_digest"):
        raise ValueError("decision digest does not match its fields")


def _require_exact_input_binding(
    *,
    snapshot: RawSnapshot,
    envelope: NormalizedIngestEnvelope,
    decision: DigestionDecision,
) -> None:
    if not isinstance(snapshot, RawSnapshot):
        raise TypeError("snapshot must be a RawSnapshot")
    if not isinstance(envelope, NormalizedIngestEnvelope):
        raise TypeError("envelope must be a NormalizedIngestEnvelope")
    if not isinstance(decision, DigestionDecision):
        raise TypeError("decision must be a DigestionDecision")
    _require_snapshot_identity(snapshot)
    _require_envelope_digest(envelope)
    _require_decision_digest(decision)
    if envelope.snapshot_ref != snapshot.snapshot_ref:
        raise ValueError("envelope snapshot ref does not match RawSnapshot")
    if envelope.snapshot_identity_digest != snapshot.snapshot_identity_digest:
        raise ValueError("envelope snapshot identity does not match RawSnapshot")
    if envelope.raw_content_digest != snapshot.raw_content_digest:
        raise ValueError("envelope raw content digest does not match RawSnapshot")
    if envelope.raw_byte_length != len(snapshot.raw_bytes):
        raise ValueError("envelope raw byte length does not match RawSnapshot")
    try:
        decoded = snapshot.raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "RawSnapshot bytes are not UTF-8 decodable for envelope binding"
        ) from exc
    expected_normalized = (
        decoded.strip()
        if envelope.content_format == "structured_json"
        else _collapse_whitespace(decoded)
    )
    if envelope.normalized_text != expected_normalized:
        raise ValueError("envelope normalized text does not match RawSnapshot decode")
    if envelope.source_character_length != len(decoded):
        raise ValueError(
            "envelope source character length does not match RawSnapshot decode"
        )
    if envelope.project_key != snapshot.project_key:
        raise ValueError("envelope project key does not match RawSnapshot")
    if envelope.source_locator != snapshot.source_locator:
        raise ValueError("envelope source locator does not match RawSnapshot")
    if decision.envelope_digest != envelope.envelope_digest:
        raise ValueError("decision does not bind the envelope digest")
    if decision.raw_byte_length != envelope.raw_byte_length:
        raise ValueError("decision raw byte length does not match the envelope")
    if decision.source_character_length != envelope.source_character_length:
        raise ValueError("decision source character length does not match the envelope")
    selector = select_exactly_one_digestion_alternative(envelope)
    if selector != decision:
        raise ValueError("decision does not match the exact envelope selector")


def _candidate_closure_failure(
    *,
    snapshot: RawSnapshot,
    envelope: NormalizedIngestEnvelope,
    decision: DigestionDecision,
    candidate: StructuredMaterialCandidate,
) -> str | None:
    if candidate.project_key != snapshot.project_key:
        return "project_key_mismatch"
    if candidate.snapshot_ref != envelope.snapshot_ref:
        return "snapshot_ref_mismatch"
    if candidate.snapshot_identity_digest != envelope.snapshot_identity_digest:
        return "snapshot_identity_mismatch"
    if candidate.raw_content_digest != envelope.raw_content_digest:
        return "raw_content_digest_mismatch"
    if candidate.envelope_digest != envelope.envelope_digest:
        return "envelope_digest_mismatch"
    if candidate.decision_digest != decision.decision_digest:
        return "decision_digest_mismatch"
    if candidate.alternative != decision.alternative:
        return "alternative_mismatch"
    if candidate.candidate_id != _branch_candidate_id(
        decision.alternative,
        snapshot.snapshot_ref,
        decision.decision_digest,
    ):
        return "candidate_id_mismatch"
    if candidate.payload_ref != f"payload:c7:{candidate.candidate_id}":
        return "payload_ref_mismatch"
    if candidate.ordered_source_refs != (snapshot.snapshot_ref,):
        return "ordered_source_mismatch"
    if candidate.ordered_source_closure_digest != content_digest(
        candidate.ordered_source_refs
    ):
        return "ordered_source_closure_mismatch"
    expected_provenance = (
        snapshot.snapshot_ref,
        envelope.envelope_digest,
        decision.decision_digest,
    )
    if candidate.provenance_closure != expected_provenance:
        return "provenance_mismatch"
    if candidate.provenance_closure_digest != content_digest(
        candidate.provenance_closure
    ):
        return "provenance_closure_mismatch"
    if candidate.payload_content_digest != content_digest(candidate.structured_payload):
        return "payload_content_digest_mismatch"
    if candidate.authority is not StagingAuthority.STAGING_ONLY_NO_DOCUMENT_WRITE:
        return "authority_mismatch"
    if candidate.candidate_digest != _object_digest(candidate, "candidate_digest"):
        return "candidate_digest_mismatch"
    return None


def verify_structured_candidate(
    *,
    snapshot: RawSnapshot,
    envelope: NormalizedIngestEnvelope,
    decision: DigestionDecision,
    candidate: StructuredMaterialCandidate,
    expected_candidate_digest: str,
    expected_project_key: str,
    actor: str,
    authority_digest: str,
    authority_epoch: int,
    canonical_base_revision: int,
    canonical_base_incarnation: str,
    canonical_object_id: str,
    verification_profile_ref: str = C7_VERIFICATION_PROFILE_REF,
    revoked_authority_epochs: frozenset[int] = frozenset(),
) -> C7VerifyResult:
    """Verify one exact candidate against the full input and server inputs."""

    def rejected(code: str, reason: str) -> C7Rejected:
        return C7Rejected(
            failure_code=code,
            reason=reason,
            snapshot_ref=candidate.snapshot_ref,
            candidate_ref=candidate.payload_ref,
        )

    if not isinstance(snapshot, RawSnapshot):
        raise TypeError("snapshot must be a RawSnapshot")
    if not isinstance(envelope, NormalizedIngestEnvelope):
        raise TypeError("envelope must be a NormalizedIngestEnvelope")
    if not isinstance(decision, DigestionDecision):
        raise TypeError("decision must be a DigestionDecision")
    if not isinstance(candidate, StructuredMaterialCandidate):
        raise TypeError("candidate must be a StructuredMaterialCandidate")
    try:
        require_hex64(
            expected_candidate_digest,
            "expected_candidate_digest",
        )
    except ValueError as exc:
        return rejected("expected_candidate_digest_invalid", str(exc))
    try:
        _require_exact_input_binding(
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
        )
    except ValueError as exc:
        return rejected("input_closure_mismatch", str(exc))
    if candidate.project_key != expected_project_key:
        return rejected(
            "project_key_mismatch", "server-resolved project scope mismatch"
        )
    closure_failure = _candidate_closure_failure(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
        candidate=candidate,
    )
    if closure_failure is not None:
        return rejected(
            closure_failure,
            f"candidate fails exact input closure: {closure_failure}",
        )
    if candidate.candidate_digest != expected_candidate_digest:
        return rejected(
            "expected_candidate_digest_mismatch",
            "candidate digest does not equal the server-resolved staged digest",
        )
    replay_kwargs: dict[str, Any] = {}
    if decision.alternative == "CHUNK":
        chunk_policy = candidate.structured_payload.get("chunk_policy")
        if not isinstance(chunk_policy, dict):
            return rejected(
                "chunk_policy_invalid",
                "digest-bound candidate has no valid chunk policy",
            )
        max_chunk_bytes = chunk_policy.get("max_chunk_bytes")
        max_chunk_count = chunk_policy.get("max_chunk_count")
        if (
            not isinstance(max_chunk_bytes, int)
            or not isinstance(max_chunk_count, int)
            or not 1 <= max_chunk_bytes <= C7_CHUNK_MAX_BYTES
            or not 1 <= max_chunk_count <= C7_CHUNK_MAX_COUNT
        ):
            return rejected(
                "chunk_policy_invalid",
                "digest-bound chunk policy exceeds bounded ceilings",
            )
        replay_kwargs = {
            "max_chunk_bytes": max_chunk_bytes,
            "max_chunk_count": max_chunk_count,
        }
    replay_port = _EXACT_PORT_CLASSES[decision.alternative](**replay_kwargs)
    replay_outcome = replay_port.execute(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
    )
    if not isinstance(replay_outcome, StructuredMaterialCandidate):
        return rejected(
            "replay_terminal",
            "independent built-in replay did not produce a candidate",
        )
    if replay_outcome != candidate:
        return rejected(
            "candidate_replay_mismatch",
            "candidate differs from the independent built-in replay",
        )
    payload_bytes = len(canonical_json(candidate.structured_payload).encode("utf-8"))
    if payload_bytes > C7_MAX_STRUCTURED_PAYLOAD_BYTES:
        return rejected(
            "structured_payload_limit_exceeded",
            "candidate structured payload exceeds bounded resource ceiling",
        )
    if len(snapshot.raw_bytes) > C7_MAX_STRUCTURED_PAYLOAD_BYTES:
        return rejected(
            "raw_snapshot_limit_exceeded",
            "raw snapshot exceeds bounded storage ceiling",
        )
    actor_name = _optional_strip(actor)
    object_id = _optional_strip(canonical_object_id)
    base_incarnation = _optional_strip(canonical_base_incarnation)
    base_revision = int(canonical_base_revision)
    if not actor_name or not object_id or not base_incarnation or base_revision < 0:
        return rejected(
            "server_identity_missing",
            "server-resolved actor/object/base identity is incomplete",
        )
    try:
        require_hex64(authority_digest, "authority_digest")
    except ValueError as exc:
        return rejected("authority_digest_invalid", str(exc))
    epoch = int(authority_epoch)
    if epoch < 1 or epoch in revoked_authority_epochs:
        return C7Deferred(
            failure_code="authority_epoch_revoked",
            reason="current verification authority epoch is revoked or stale",
            snapshot_ref=candidate.snapshot_ref,
            candidate_ref=candidate.payload_ref,
        )
    profile_ref = _strip(verification_profile_ref, "verification_profile_ref")
    return VerifiedMaterialCandidate(
        candidate_id=candidate.candidate_id,
        candidate_digest=candidate.candidate_digest,
        envelope_digest=candidate.envelope_digest,
        snapshot_ref=candidate.snapshot_ref,
        snapshot_identity_digest=candidate.snapshot_identity_digest,
        raw_content_digest=candidate.raw_content_digest,
        payload_content_digest=candidate.payload_content_digest,
        ordered_source_closure_digest=candidate.ordered_source_closure_digest,
        provenance_closure_digest=candidate.provenance_closure_digest,
        decision_digest=candidate.decision_digest,
        alternative=candidate.alternative,
        project_key=candidate.project_key,
        canonical_object_id=object_id,
        expected_base_revision=base_revision,
        expected_base_incarnation=base_incarnation,
        actor=actor_name,
        authority_digest=authority_digest,
        authority_epoch=epoch,
        verification_profile_ref=profile_ref,
    )


@dataclass(frozen=True, slots=True)
class C7ReverseReturn:
    """Reverse return binding full snapshot identity and exact retry policy."""

    snapshot_ref: str
    snapshot_identity_digest: str
    reason: str
    failure: str
    failure_digest: str
    cleanup_target: str = "cleanup_staged_candidate_or_snapshot"
    new_attempt_policy: str = C7_NEW_ATTEMPT_POLICY
    candidate_ref: str | None = None
    admission_disabled: bool = True
    projection_disabled: bool = True
    provider_calls: int = 0
    canonical_write: bool = False
    external_delivery: bool = False
    cutover: bool = False
    authority_transfer: bool = False
    reverse_return_digest: str = ""

    def __post_init__(self) -> None:
        snapshot_ref = _strip(self.snapshot_ref, "C7ReverseReturn.snapshot_ref")
        require_hex64(
            self.snapshot_identity_digest,
            "C7ReverseReturn.snapshot_identity_digest",
        )
        reason = _strip(self.reason, "C7ReverseReturn.reason")
        failure = _strip(self.failure, "C7ReverseReturn.failure")
        require_hex64(self.failure_digest, "C7ReverseReturn.failure_digest")
        cleanup_target = _strip(
            self.cleanup_target or "cleanup_staged_candidate_or_snapshot",
            "C7ReverseReturn.cleanup_target",
        )
        if self.new_attempt_policy != C7_NEW_ATTEMPT_POLICY:
            raise ValueError(
                "C7 reverse return must use the exact retry prohibition policy"
            )
        candidate_ref = _optional_strip(self.candidate_ref)
        if self.admission_disabled is not True:
            raise ValueError("C7 reverse return must disable admission")
        if self.projection_disabled is not True:
            raise ValueError("C7 reverse return must disable projection")
        _assert_pure_effect_flags(
            provider_calls=self.provider_calls,
            canonical_write=self.canonical_write,
            external_delivery=self.external_delivery,
            cutover=self.cutover,
            authority_transfer=self.authority_transfer,
        )
        object.__setattr__(self, "snapshot_ref", snapshot_ref)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "failure", failure)
        object.__setattr__(self, "cleanup_target", cleanup_target)
        object.__setattr__(self, "candidate_ref", candidate_ref)
        digest = _object_digest(self, "reverse_return_digest")
        if self.reverse_return_digest and self.reverse_return_digest != digest:
            raise ValueError(
                "C7ReverseReturn.reverse_return_digest does not match fields"
            )
        object.__setattr__(self, "reverse_return_digest", digest)


def return_for_cleanup(
    *,
    snapshot: RawSnapshot,
    reason: str,
    failure: str,
    candidate: StructuredMaterialCandidate | None = None,
    outcome: C7Rejected | C7Deferred | None = None,
    cleanup_target: str = "cleanup_staged_candidate_or_snapshot",
) -> C7ReverseReturn:
    """Emit a typed reverse return without extraction, admission or writes."""

    if not isinstance(snapshot, RawSnapshot):
        raise TypeError("snapshot must be a RawSnapshot")
    if outcome is not None and not isinstance(outcome, (C7Rejected, C7Deferred)):
        raise TypeError("outcome must be a typed C7Rejected or C7Deferred")
    if candidate is not None:
        if not isinstance(candidate, StructuredMaterialCandidate):
            raise TypeError("candidate must be a StructuredMaterialCandidate")
        if outcome is not None:
            raise ValueError("outcome and candidate are mutually exclusive")
        if (
            candidate.snapshot_ref != snapshot.snapshot_ref
            or candidate.snapshot_identity_digest != snapshot.snapshot_identity_digest
            or candidate.raw_content_digest != snapshot.raw_content_digest
        ):
            raise ValueError(
                "candidate is not bound to the returned full snapshot identity"
            )
    if outcome is not None:
        if outcome.snapshot_ref != snapshot.snapshot_ref:
            raise ValueError("outcome is not bound to the returned snapshot")
        failure_digest = (
            outcome.rejected_digest
            if isinstance(outcome, C7Rejected)
            else outcome.deferred_digest
        )
        candidate_ref = outcome.candidate_ref
    elif candidate is not None:
        failure_digest = content_digest(
            {
                "reason": reason,
                "failure": failure,
                "candidate_digest": candidate.candidate_digest,
            }
        )
        candidate_ref = candidate.payload_ref
    else:
        failure_digest = content_digest({"reason": reason, "failure": failure})
        candidate_ref = None
    return C7ReverseReturn(
        snapshot_ref=snapshot.snapshot_ref,
        snapshot_identity_digest=snapshot.snapshot_identity_digest,
        reason=reason,
        failure=failure,
        failure_digest=failure_digest,
        cleanup_target=cleanup_target,
        candidate_ref=candidate_ref,
    )


@dataclass(frozen=True, slots=True)
class C7MovementTrace:
    """One ordered movement trace with explicit false authority ceiling."""

    schema: str
    alternative: str
    decision_digest: str
    snapshot_ref: str
    outcome: C7PortResult
    branch_receipt: str
    provider_calls: int = 0
    authority: bool = False
    canonical_write: bool = False
    external_delivery: bool = False
    cutover: bool = False
    authority_transfer: bool = False
    trace_digest: str = ""

    def __post_init__(self) -> None:
        schema = _strip(self.schema or C7_PURE_SCHEMA, "C7MovementTrace.schema")
        alternative = _strip(self.alternative, "C7MovementTrace.alternative")
        if alternative not in C7_ALTERNATIVES:
            raise ValueError(f"unsupported C7 alternative: {alternative}")
        require_hex64(self.decision_digest, "C7MovementTrace.decision_digest")
        snapshot_ref = _strip(self.snapshot_ref, "C7MovementTrace.snapshot_ref")
        if not isinstance(
            self.outcome,
            (StructuredMaterialCandidate, C7Rejected, C7Deferred),
        ):
            raise TypeError("unsupported C7 movement outcome")
        if isinstance(self.outcome, StructuredMaterialCandidate):
            if self.outcome.alternative != alternative:
                raise ValueError("candidate branch does not match decision")
            if self.outcome.decision_digest != self.decision_digest:
                raise ValueError("candidate decision digest does not match")
            if self.outcome.snapshot_ref != snapshot_ref:
                raise ValueError("candidate snapshot ref does not match")
        else:
            if self.outcome.snapshot_ref != snapshot_ref:
                raise ValueError("terminal outcome snapshot ref does not match")
        branch_receipt = _strip(self.branch_receipt, "C7MovementTrace.branch_receipt")
        _assert_pure_effect_flags(
            provider_calls=self.provider_calls,
            canonical_write=self.canonical_write,
            external_delivery=self.external_delivery,
            cutover=self.cutover,
            authority_transfer=self.authority_transfer,
        )
        if self.authority is not False:
            raise ValueError("pure C7 movement may not claim authority")
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "alternative", alternative)
        object.__setattr__(self, "snapshot_ref", snapshot_ref)
        object.__setattr__(self, "branch_receipt", branch_receipt)
        object.__setattr__(self, "provider_calls", int(self.provider_calls))
        digest = _object_digest(self, "trace_digest")
        if self.trace_digest and self.trace_digest != digest:
            raise ValueError("C7MovementTrace.trace_digest does not match fields")
        object.__setattr__(self, "trace_digest", digest)


def _outcome_digest(outcome: C7PortResult) -> str:
    if isinstance(outcome, StructuredMaterialCandidate):
        return outcome.candidate_digest
    if isinstance(outcome, C7Rejected):
        return outcome.rejected_digest
    if isinstance(outcome, C7Deferred):
        return outcome.deferred_digest
    raise TypeError("unsupported C7 movement outcome")


class ExtractPort(Protocol):
    """Handwritten Extract branch port."""

    provider_calls: int
    receipts: list[str]

    def execute(
        self,
        *,
        snapshot: RawSnapshot,
        envelope: NormalizedIngestEnvelope,
        decision: DigestionDecision,
    ) -> C7PortResult: ...


class ChunkPort(Protocol):
    """Handwritten Chunk branch port."""

    provider_calls: int
    receipts: list[str]

    def execute(
        self,
        *,
        snapshot: RawSnapshot,
        envelope: NormalizedIngestEnvelope,
        decision: DigestionDecision,
    ) -> C7PortResult: ...


class SummarizePort(Protocol):
    """Handwritten Summarize branch port."""

    provider_calls: int
    receipts: list[str]

    def execute(
        self,
        *,
        snapshot: RawSnapshot,
        envelope: NormalizedIngestEnvelope,
        decision: DigestionDecision,
    ) -> C7PortResult: ...


class PassThroughPort(Protocol):
    """Handwritten PassThrough branch port."""

    provider_calls: int
    receipts: list[str]

    def execute(
        self,
        *,
        snapshot: RawSnapshot,
        envelope: NormalizedIngestEnvelope,
        decision: DigestionDecision,
    ) -> C7PortResult: ...


class _DeterministicPortBase:
    effect_profile = ""
    resource_profile = ""
    failure_profile = ""

    def __init__(self) -> None:
        self.calls = 0
        self.provider_calls = 0
        self.receipts: list[str] = []

    def _finish(self, outcome: C7PortResult) -> C7PortResult:
        self.calls += 1
        self.receipts.append(_outcome_digest(outcome))
        return outcome


def _branch_candidate_id(
    branch: str,
    snapshot_ref: str,
    decision_digest: str,
) -> str:
    digest = content_digest(
        {
            "branch": branch,
            "snapshot_ref": snapshot_ref,
            "decision_digest": decision_digest,
        }
    )
    return f"ingest-c7-{branch.lower()}-{digest[:16]}"


def _build_candidate(
    *,
    branch: str,
    snapshot: RawSnapshot,
    envelope: NormalizedIngestEnvelope,
    decision: DigestionDecision,
    structured_payload: Mapping[str, Any],
    failure_loss_profile: str = "no_declared_loss",
) -> StructuredMaterialCandidate:
    candidate_id = _branch_candidate_id(
        branch, envelope.snapshot_ref, decision.decision_digest
    )
    return StructuredMaterialCandidate(
        candidate_id=candidate_id,
        project_key=envelope.project_key,
        snapshot_ref=snapshot.snapshot_ref,
        snapshot_identity_digest=snapshot.snapshot_identity_digest,
        raw_content_digest=snapshot.raw_content_digest,
        envelope_digest=envelope.envelope_digest,
        alternative=branch,
        decision_digest=decision.decision_digest,
        ordered_source_refs=(snapshot.snapshot_ref,),
        structured_payload=structured_payload,
        provenance_closure=(
            snapshot.snapshot_ref,
            envelope.envelope_digest,
            decision.decision_digest,
        ),
        failure_loss_profile=failure_loss_profile,
        authority=StagingAuthority.STAGING_ONLY_NO_DOCUMENT_WRITE,
    )


class DeterministicExtractPort(_DeterministicPortBase, ExtractPort):
    """Provider-zero structured JSON extraction interpreter."""

    effect_profile = "pure_parse_no_provider"
    resource_profile = "cpu_light_bounded_parse"
    failure_profile = "malformed_or_empty_structured_json"

    @staticmethod
    def _reject_non_finite_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON constant: {value}")

    @classmethod
    def _require_finite_json_numbers(cls, value: Any) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        if isinstance(value, Mapping):
            for item in value.values():
                cls._require_finite_json_numbers(item)
        elif isinstance(value, list):
            for item in value:
                cls._require_finite_json_numbers(item)

    def execute(
        self,
        *,
        snapshot: RawSnapshot,
        envelope: NormalizedIngestEnvelope,
        decision: DigestionDecision,
    ) -> C7PortResult:
        if decision.alternative != "EXTRACT":
            return self._finish(
                C7Rejected(
                    failure_code="branch_mismatch",
                    reason="ExtractPort received a non-EXTRACT decision",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        if envelope.content_format != "structured_json":
            return self._finish(
                C7Rejected(
                    failure_code="format_mismatch",
                    reason="ExtractPort requires structured JSON content",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        try:
            parsed = json.loads(
                snapshot.raw_bytes.decode("utf-8"),
                parse_constant=self._reject_non_finite_constant,
            )
            self._require_finite_json_numbers(parsed)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            return self._finish(
                C7Rejected(
                    failure_code="malformed_structured_json",
                    reason=f"structured JSON could not be parsed: {exc}",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        if not isinstance(parsed, dict) or not parsed:
            return self._finish(
                C7Rejected(
                    failure_code="empty_structured_output",
                    reason="structured JSON produced no non-empty object",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        candidate = _build_candidate(
            branch="EXTRACT",
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
            structured_payload=parsed,
        )
        return self._finish(candidate)


def _ordered_chunks(text: str, max_chunk_bytes: int) -> list[str]:
    if int(max_chunk_bytes) <= 0:
        raise ValueError("max_chunk_bytes must be > 0")
    chunks: list[str] = []
    current = ""
    for char in text:
        if len(char.encode("utf-8")) > max_chunk_bytes:
            raise ValueError("single UTF-8 codepoint exceeds the chunk byte ceiling")
        candidate = current + char
        if len(candidate.encode("utf-8")) > max_chunk_bytes and current:
            chunks.append(current)
            current = char
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


class DeterministicChunkPort(_DeterministicPortBase, ChunkPort):
    """Provider-zero ordered chunking with aggregate single candidate."""

    effect_profile = "pure_split_no_provider"
    resource_profile = "bounded_chunk_count_bytes"
    failure_profile = "empty_or_resource_ceiling"

    def __init__(
        self,
        *,
        max_chunk_bytes: int = C7_CHUNK_MAX_BYTES,
        max_chunk_count: int = C7_CHUNK_MAX_COUNT,
    ) -> None:
        super().__init__()
        self.max_chunk_bytes = int(max_chunk_bytes)
        self.max_chunk_count = int(max_chunk_count)
        if not 1 <= self.max_chunk_bytes <= C7_CHUNK_MAX_BYTES:
            raise ValueError(
                "max_chunk_bytes must be within the global C7 chunk byte ceiling"
            )
        if not 1 <= self.max_chunk_count <= C7_CHUNK_MAX_COUNT:
            raise ValueError(
                "max_chunk_count must be within the global C7 chunk count ceiling"
            )

    def execute(
        self,
        *,
        snapshot: RawSnapshot,
        envelope: NormalizedIngestEnvelope,
        decision: DigestionDecision,
    ) -> C7PortResult:
        if decision.alternative != "CHUNK":
            return self._finish(
                C7Rejected(
                    failure_code="branch_mismatch",
                    reason="ChunkPort received a non-CHUNK decision",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        if not _is_chunk_mode(envelope):
            return self._finish(
                C7Rejected(
                    failure_code="chunk_mode_mismatch",
                    reason="envelope is not in long/report-shaped chunk mode",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        if not envelope.normalized_text.strip():
            return self._finish(
                C7Rejected(
                    failure_code="empty_chunk_input",
                    reason="chunk input is empty",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        try:
            policy_bytes = int(self.max_chunk_bytes)
            policy_count = int(self.max_chunk_count)
            policy_valid = (
                1 <= policy_bytes <= C7_CHUNK_MAX_BYTES
                and 1 <= policy_count <= C7_CHUNK_MAX_COUNT
            )
        except (OverflowError, TypeError, ValueError):
            policy_valid = False
        if not policy_valid:
            return self._finish(
                C7Rejected(
                    failure_code="chunk_policy_ceiling_exceeded",
                    reason="chunk policy exceeds bounded global ceilings",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        try:
            chunks = _ordered_chunks(envelope.normalized_text, policy_bytes)
        except ValueError as exc:
            return self._finish(
                C7Rejected(
                    failure_code="chunk_codepoint_exceeds_ceiling",
                    reason=str(exc),
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        if len(chunks) > policy_count:
            return self._finish(
                C7Rejected(
                    failure_code="chunk_count_ceiling_exceeded",
                    reason=(
                        f"resource ceiling exceeded: {len(chunks)} > {policy_count}"
                    ),
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        chunk_rows = [
            {
                "index": index,
                "ref": f"{envelope.snapshot_ref}:chunk:{index}",
                "text": chunk,
                "byte_size": len(chunk.encode("utf-8")),
            }
            for index, chunk in enumerate(chunks)
        ]
        payload = {
            "chunks": chunk_rows,
            "aggregate": {
                "chunk_count": len(chunk_rows),
                "total_bytes": len(envelope.normalized_text.encode("utf-8")),
            },
            "chunk_policy": {
                "max_chunk_bytes": policy_bytes,
                "max_chunk_count": policy_count,
            },
            "branch_internal_structuring": list(decision.branch_internal_structuring),
            "branch_internal_structure": _provider_enrichment_declared_loss_structure(),
            "raw_content_digest": snapshot.raw_content_digest,
            "raw_byte_length": envelope.raw_byte_length,
            "source_character_length": envelope.source_character_length,
        }
        candidate = _build_candidate(
            branch="CHUNK",
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
            structured_payload=payload,
            failure_loss_profile=C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF,
        )
        return self._finish(candidate)


class DeterministicSummarizePort(_DeterministicPortBase, SummarizePort):
    """Provider-zero summary-derived structural candidate interpreter."""

    effect_profile = "pure_summary_no_provider"
    resource_profile = "bounded_summary_text"
    failure_profile = "empty_or_insufficient_derived_artifact"

    def execute(
        self,
        *,
        snapshot: RawSnapshot,
        envelope: NormalizedIngestEnvelope,
        decision: DigestionDecision,
    ) -> C7PortResult:
        if decision.alternative != "SUMMARIZE":
            return self._finish(
                C7Rejected(
                    failure_code="branch_mismatch",
                    reason="SummarizePort received a non-SUMMARIZE decision",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        if envelope.input_kind not in _DERIVED_INPUT_KINDS:
            return self._finish(
                C7Rejected(
                    failure_code="derived_mode_mismatch",
                    reason="envelope is not a derived LLM/writing report",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        source_text = envelope.normalized_text
        summary = source_text[:C7_DEFAULT_SUMMARY_LENGTH].rstrip()
        if not summary or not any(char.isalnum() for char in summary):
            return self._finish(
                C7Rejected(
                    failure_code="empty_or_insufficient_derived_report",
                    reason="derived report produced no usable summary structure",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        payload = {
            "summary": summary,
            "summary_mode": "deterministic_truncate_v1",
            "summary_digest": content_digest(summary),
            "input_length": len(source_text),
            "raw_byte_length": envelope.raw_byte_length,
            "summary_length": len(summary),
            "branch_internal_structuring": list(decision.branch_internal_structuring),
            "branch_internal_structure": _provider_enrichment_declared_loss_structure(),
            "input_provenance": [
                envelope.snapshot_ref,
                envelope.envelope_digest,
            ],
            "raw_content_digest": snapshot.raw_content_digest,
            "source_character_length": envelope.source_character_length,
        }
        candidate = _build_candidate(
            branch="SUMMARIZE",
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
            structured_payload=payload,
            failure_loss_profile=C7_PROVIDER_ENRICHMENT_DECLARED_LOSS_REF,
        )
        return self._finish(candidate)


class DeterministicPassThroughPort(_DeterministicPortBase, PassThroughPort):
    """Provider-zero pass-through preserving content and provenance."""

    effect_profile = "pure_preserve_no_provider"
    resource_profile = "bounded_bytes"
    failure_profile = "empty_unsafe_or_resource_limit"

    def execute(
        self,
        *,
        snapshot: RawSnapshot,
        envelope: NormalizedIngestEnvelope,
        decision: DigestionDecision,
    ) -> C7PortResult:
        if decision.alternative != "PASS_THROUGH":
            return self._finish(
                C7Rejected(
                    failure_code="branch_mismatch",
                    reason="PassThroughPort received a non-PASS_THROUGH decision",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        text = envelope.normalized_text
        if not text.strip():
            return self._finish(
                C7Rejected(
                    failure_code="empty_pass_through_rejected",
                    reason="empty pass-through content is rejected without a candidate",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        if "\x00" in text:
            return self._finish(
                C7Deferred(
                    failure_code="unsafe_pass_through_deferred",
                    reason="unsafe pass-through content is deferred for repair",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        if len(text.encode("utf-8")) > C7_MAX_PASS_THROUGH_BYTES:
            return self._finish(
                C7Rejected(
                    failure_code="pass_through_resource_limit_exceeded",
                    reason="pass-through content exceeds bounded byte ceiling",
                    snapshot_ref=envelope.snapshot_ref,
                )
            )
        payload = {
            "content": text,
            "content_digest": content_digest(text),
            "content_format": envelope.content_format,
            "normalization_loss": envelope.normalization_loss,
            "normalization_profile_ref": envelope.normalization_profile_ref,
            "raw_snapshot_retained": True,
            "raw_content_digest": snapshot.raw_content_digest,
            "raw_byte_length": envelope.raw_byte_length,
            "provenance": [
                envelope.snapshot_ref,
                envelope.envelope_digest,
            ],
        }
        candidate = _build_candidate(
            branch="PASS_THROUGH",
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
            structured_payload=payload,
            failure_loss_profile=C7_NORMALIZATION_ONLY_LOSS,
        )
        return self._finish(candidate)


_EXACT_PORT_CLASSES: dict[str, type] = {
    "EXTRACT": DeterministicExtractPort,
    "CHUNK": DeterministicChunkPort,
    "SUMMARIZE": DeterministicSummarizePort,
    "PASS_THROUGH": DeterministicPassThroughPort,
}


def execute_c7_movement(
    *,
    snapshot: RawSnapshot,
    envelope: NormalizedIngestEnvelope,
    decision: DigestionDecision,
    extract: ExtractPort,
    chunk: ChunkPort,
    summarize: SummarizePort,
    pass_through: PassThroughPort,
) -> C7MovementTrace:
    """Run the ordered pure movement and execute exactly one branch."""

    _require_exact_input_binding(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
    )
    ports: dict[str, Any] = {
        "EXTRACT": extract,
        "CHUNK": chunk,
        "SUMMARIZE": summarize,
        "PASS_THROUGH": pass_through,
    }
    port = ports[decision.alternative]
    exact_class = _EXACT_PORT_CLASSES[decision.alternative]
    if type(port) is not exact_class:
        raise TypeError(
            "provider-zero evidence requires the exact built-in C7 port class"
        )
    if getattr(port, "calls", None) != 0 or getattr(port, "receipts", None) != []:
        raise ValueError("selected C7 port must be fresh with zero calls")
    execute_method = getattr(port, "execute", None)
    if getattr(execute_method, "__func__", None) is not exact_class.execute:
        raise TypeError("bound execute must be the exact built-in class implementation")
    finish_method = getattr(port, "_finish", None)
    if getattr(finish_method, "__func__", None) is not _DeterministicPortBase._finish:
        raise TypeError("bound _finish must be the exact built-in base implementation")
    allowed_state = {"calls", "provider_calls", "receipts"}
    if decision.alternative == "CHUNK":
        allowed_state = allowed_state | {"max_chunk_bytes", "max_chunk_count"}
    if set(vars(port).keys()) != allowed_state:
        raise ValueError("selected C7 port has forbidden instance state")
    outcome = port.execute(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
    )
    if not isinstance(outcome, (StructuredMaterialCandidate, C7Rejected, C7Deferred)):
        raise TypeError("branch port returned an unsupported outcome")
    if isinstance(outcome, StructuredMaterialCandidate):
        closure_failure = _candidate_closure_failure(
            snapshot=snapshot,
            envelope=envelope,
            decision=decision,
            candidate=outcome,
        )
        if closure_failure is not None:
            raise ValueError(
                f"branch port returned a candidate that fails input closure: "
                f"{closure_failure}"
            )
    if getattr(port, "calls", None) != 1:
        raise ValueError("selected C7 port must record exactly one call")
    receipts = getattr(port, "receipts", None)
    if (
        not isinstance(receipts, list)
        or len(receipts) != 1
        or receipts[0] != _outcome_digest(outcome)
    ):
        raise ValueError(
            "selected C7 port must record one receipt matching the outcome digest"
        )
    provider_calls = int(getattr(port, "provider_calls", 0))
    if provider_calls != 0:
        raise ValueError("branch port recorded provider calls")
    branch_receipt = receipts[0]
    return C7MovementTrace(
        schema=C7_PURE_SCHEMA,
        alternative=decision.alternative,
        decision_digest=decision.decision_digest,
        snapshot_ref=envelope.snapshot_ref,
        outcome=outcome,
        branch_receipt=branch_receipt,
        provider_calls=provider_calls,
    )
