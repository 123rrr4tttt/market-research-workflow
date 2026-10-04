"""Registered material-ingest vocabularies, failures, and token codecs.

The declarations in this module are the current semantic authority shared by
the ingest runtime and its native contribution. Explicit historical readers
retain the retired ``c7.*`` wire metadata without declaring a second live
registry representation or changing historical bytes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal, get_args

from functorial_kit import Failure, define_codec, define_failure_family, define_vocabulary
from functorial_kit.core.codec import Codec
from functorial_kit.core.failure import FailureFamily
from functorial_kit.core.vocab import Vocabulary


MaterialDigestionAlternative = Literal["EXTRACT", "CHUNK", "SUMMARIZE", "PASS_THROUGH"]
MaterialIngestInputKind = Literal[
    "url_driven_external",
    "raw_import",
    "report_shaped",
    "derived_llm_report",
    "derived_writing_markdown",
    "unknown",
]
MaterialIngestContentFormat = Literal[
    "plain_text", "markdown", "html", "pdf", "structured_json", "other"
]
MaterialIngestMovementDisposition = Literal[
    "PRESERVED_AS",
    "MOVED_TO",
    "REIMPLEMENTED_AS",
    "DECLARED_LOSS",
    "EXPLICITLY_REJECTED",
    "UNASSIGNED_BLOCKER",
]
MaterialIngestTerminalOutcome = Literal[
    "STRUCTURED_MATERIAL_CANDIDATE", "REJECTED", "DEFERRED"
]
MaterialIngestTerminalFailureCode = Literal[
    "alternative_mismatch",
    "authority_digest_invalid",
    "authority_epoch_revoked",
    "authority_mismatch",
    "branch_mismatch",
    "candidate_digest_mismatch",
    "candidate_id_mismatch",
    "candidate_replay_mismatch",
    "chunk_codepoint_exceeds_ceiling",
    "chunk_count_ceiling_exceeded",
    "chunk_mode_mismatch",
    "chunk_policy_ceiling_exceeded",
    "chunk_policy_invalid",
    "decision_digest_mismatch",
    "derived_mode_mismatch",
    "empty_chunk_input",
    "empty_or_insufficient_derived_report",
    "empty_pass_through_rejected",
    "empty_structured_output",
    "envelope_digest_mismatch",
    "expected_candidate_digest_invalid",
    "expected_candidate_digest_mismatch",
    "format_mismatch",
    "input_closure_mismatch",
    "malformed_structured_json",
    "ordered_source_closure_mismatch",
    "ordered_source_mismatch",
    "pass_through_resource_limit_exceeded",
    "payload_content_digest_mismatch",
    "payload_ref_mismatch",
    "project_key_mismatch",
    "provenance_closure_mismatch",
    "provenance_mismatch",
    "raw_content_digest_mismatch",
    "raw_snapshot_limit_exceeded",
    "replay_terminal",
    "server_identity_missing",
    "snapshot_identity_mismatch",
    "snapshot_ref_mismatch",
    "structured_payload_limit_exceeded",
    "unsafe_pass_through_deferred",
]
MaterialIngestFailureCode = Literal[
    "INGEST_SUBMISSION_INVALID",
    "STAGED_CANDIDATE_FAILED",
    "COMMIT_INTENT_READBACK_UNAVAILABLE",
    "PROJECTION_OFFSET_DRIFT",
    "RECONCILIATION_TERMINAL_READBACK_REQUIRED",
    "RECONCILIATION_AUTHORITY_MISMATCH",
    "alternative_mismatch",
    "authority_digest_invalid",
    "authority_epoch_revoked",
    "authority_mismatch",
    "branch_mismatch",
    "candidate_digest_mismatch",
    "candidate_id_mismatch",
    "candidate_replay_mismatch",
    "chunk_codepoint_exceeds_ceiling",
    "chunk_count_ceiling_exceeded",
    "chunk_mode_mismatch",
    "chunk_policy_ceiling_exceeded",
    "chunk_policy_invalid",
    "decision_digest_mismatch",
    "derived_mode_mismatch",
    "empty_chunk_input",
    "empty_or_insufficient_derived_report",
    "empty_pass_through_rejected",
    "empty_structured_output",
    "envelope_digest_mismatch",
    "expected_candidate_digest_invalid",
    "expected_candidate_digest_mismatch",
    "format_mismatch",
    "input_closure_mismatch",
    "malformed_structured_json",
    "ordered_source_closure_mismatch",
    "ordered_source_mismatch",
    "pass_through_resource_limit_exceeded",
    "payload_content_digest_mismatch",
    "payload_ref_mismatch",
    "project_key_mismatch",
    "provenance_closure_mismatch",
    "provenance_mismatch",
    "raw_content_digest_mismatch",
    "raw_snapshot_limit_exceeded",
    "replay_terminal",
    "server_identity_missing",
    "snapshot_identity_mismatch",
    "snapshot_ref_mismatch",
    "structured_payload_limit_exceeded",
    "unsafe_pass_through_deferred",
]

MATERIAL_INGEST_FAILURE_CODES = get_args(MaterialIngestFailureCode)
MATERIAL_INGEST_TERMINAL_FAILURE_CODES = get_args(MaterialIngestTerminalFailureCode)
MATERIAL_INGEST_STAGE_FAILURE_CODES = MATERIAL_INGEST_FAILURE_CODES[
    : -len(MATERIAL_INGEST_TERMINAL_FAILURE_CODES)
]

material_digestion_alternatives = define_vocabulary(
    "material.digestion.alternatives", get_args(MaterialDigestionAlternative)
)
material_ingest_input_kinds = define_vocabulary(
    "material.ingest.input_kind", get_args(MaterialIngestInputKind)
)
material_ingest_content_formats = define_vocabulary(
    "material.ingest.content_format", get_args(MaterialIngestContentFormat)
)
material_ingest_movement_dispositions = define_vocabulary(
    "material.ingest.movement_disposition", get_args(MaterialIngestMovementDisposition)
)
material_ingest_terminal_outcomes = define_vocabulary(
    "material.ingest.terminal_outcome", get_args(MaterialIngestTerminalOutcome)
)
material_ingest_failures = define_failure_family(
    "material.ingest.failure", get_args(MaterialIngestFailureCode)
)


def _invalid_member(field: str, value: object) -> Failure:
    return Failure(
        family="kit.codec",
        code="CODEC_INVALID_FIELD",
        message="member is outside the closed vocabulary",
        context={"field": field, "value": value},
    )


def _parse_member(value: Mapping[str, Any], vocabulary: Vocabulary) -> str | Failure:
    member = value.get("member")
    if isinstance(member, str) and vocabulary.has(member):
        return member
    return _invalid_member("member", member)


def _parse_alternative(value: Mapping[str, Any]) -> str | Failure:
    return _parse_member(value, material_digestion_alternatives)


def _parse_input_kind(value: Mapping[str, Any]) -> str | Failure:
    return _parse_member(value, material_ingest_input_kinds)


def _parse_content_format(value: Mapping[str, Any]) -> str | Failure:
    return _parse_member(value, material_ingest_content_formats)


def _parse_disposition(value: Mapping[str, Any]) -> str | Failure:
    return _parse_member(value, material_ingest_movement_dispositions)


def _parse_terminal_outcome(value: Mapping[str, Any]) -> str | Failure:
    return _parse_member(value, material_ingest_terminal_outcomes)


material_digestion_alternative_codec = define_codec(
    name="material.digestion.alternative",
    discriminant="material.digestion.alternative.v2",
    keys=("kind", "member"),
    parse=_parse_alternative,
    to_wire=lambda member: {
        "kind": "material.digestion.alternative.v2",
        "member": member,
    },
)
material_ingest_input_kind_codec = define_codec(
    name="material.ingest.input_kind",
    discriminant="material.ingest.input_kind.v2",
    keys=("kind", "member"),
    parse=_parse_input_kind,
    to_wire=lambda member: {"kind": "material.ingest.input_kind.v2", "member": member},
)
material_ingest_content_format_codec = define_codec(
    name="material.ingest.content_format",
    discriminant="material.ingest.content_format.v2",
    keys=("kind", "member"),
    parse=_parse_content_format,
    to_wire=lambda member: {
        "kind": "material.ingest.content_format.v2",
        "member": member,
    },
)
material_ingest_movement_disposition_codec = define_codec(
    name="material.ingest.movement_disposition",
    discriminant="material.ingest.movement_disposition.v2",
    keys=("kind", "member"),
    parse=_parse_disposition,
    to_wire=lambda member: {
        "kind": "material.ingest.movement_disposition.v2",
        "member": member,
    },
)
material_ingest_terminal_outcome_codec = define_codec(
    name="material.ingest.terminal_outcome",
    discriminant="material.ingest.terminal_outcome.v2",
    keys=("kind", "member"),
    parse=_parse_terminal_outcome,
    to_wire=lambda member: {
        "kind": "material.ingest.terminal_outcome.v2",
        "member": member,
    },
)


def _historical_codec(
    *,
    name: str,
    discriminant: str,
    parse: Callable[[Mapping[str, Any]], str | Failure],
) -> Codec[str]:
    """Construct read-only metadata for an exact retired C7 token encoding."""

    return Codec(
        name=name,
        discriminant=discriminant,
        discriminant_key="kind",
        keys=("kind", "member"),
        _parse=parse,
        _to_wire=lambda member: {"kind": discriminant, "member": member},
    )


def read_historical_c7_alternative_codec() -> Codec[str]:
    return _historical_codec(
        name="c7.digestion.alternative",
        discriminant="c7.digestion.alternative.v1",
        parse=_parse_alternative,
    )


def read_historical_c7_input_kind_codec() -> Codec[str]:
    return _historical_codec(
        name="c7.ingest.input_kind",
        discriminant="c7.ingest.input_kind.v1",
        parse=_parse_input_kind,
    )


def read_historical_c7_content_format_codec() -> Codec[str]:
    return _historical_codec(
        name="c7.ingest.content_format",
        discriminant="c7.ingest.content_format.v1",
        parse=_parse_content_format,
    )


def read_historical_c7_movement_disposition_codec() -> Codec[str]:
    return _historical_codec(
        name="c7.movement.disposition",
        discriminant="c7.movement.disposition.v1",
        parse=_parse_disposition,
    )


def read_historical_c7_terminal_outcome_codec() -> Codec[str]:
    return _historical_codec(
        name="c7.movement.terminal_outcome",
        discriminant="c7.movement.terminal_outcome.v1",
        parse=_parse_terminal_outcome,
    )


def read_historical_c7_terminal_failure_family() -> FailureFamily:
    return FailureFamily(
        "c7.movement.terminal_failure", get_args(MaterialIngestTerminalFailureCode)
    )


# Source-compatible type spellings; current values are material-domain values.
MaterialDigestionAlternative = MaterialDigestionAlternative
MaterialIngestInputKind = MaterialIngestInputKind
MaterialIngestContentFormat = MaterialIngestContentFormat
MaterialMovementDisposition = MaterialIngestMovementDisposition
MaterialTerminalOutcome = MaterialIngestTerminalOutcome
MaterialIngestTerminalFailureCode = MaterialIngestTerminalFailureCode


__all__ = [
    "MaterialDigestionAlternative",
    "MaterialIngestContentFormat",
    "MaterialIngestInputKind",
    "MaterialMovementDisposition",
    "MaterialIngestTerminalFailureCode",
    "MaterialTerminalOutcome",
    "MATERIAL_INGEST_FAILURE_CODES",
    "MATERIAL_INGEST_STAGE_FAILURE_CODES",
    "MATERIAL_INGEST_TERMINAL_FAILURE_CODES",
    "MaterialDigestionAlternative",
    "MaterialIngestContentFormat",
    "MaterialIngestFailureCode",
    "MaterialIngestInputKind",
    "MaterialIngestMovementDisposition",
    "MaterialIngestTerminalFailureCode",
    "MaterialIngestTerminalOutcome",
    "material_digestion_alternative_codec",
    "material_digestion_alternatives",
    "material_ingest_content_format_codec",
    "material_ingest_content_formats",
    "material_ingest_failures",
    "material_ingest_input_kind_codec",
    "material_ingest_input_kinds",
    "material_ingest_movement_disposition_codec",
    "material_ingest_movement_dispositions",
    "material_ingest_terminal_outcome_codec",
    "material_ingest_terminal_outcomes",
    "read_historical_c7_alternative_codec",
    "read_historical_c7_content_format_codec",
    "read_historical_c7_input_kind_codec",
    "read_historical_c7_movement_disposition_codec",
    "read_historical_c7_terminal_failure_family",
    "read_historical_c7_terminal_outcome_codec",
]
