"""Kit registration projection for the existing C7 semantic vocabulary.

The authoritative runtime definitions remain in
``main/backend/app/successor_runtime/capabilities/ingest_c7_movements.py``.
This module only gives those closed vocabularies a kit registry owner; it does
not execute C7 movements or authorize a canonical write.
"""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import Failure, define_codec, define_failure_family, define_vocabulary

C7Alternative = Literal["EXTRACT", "CHUNK", "SUMMARIZE", "PASS_THROUGH"]
C7InputKind = Literal[
    "url_driven_external",
    "raw_import",
    "report_shaped",
    "derived_llm_report",
    "derived_writing_markdown",
    "unknown",
]
C7ContentFormat = Literal[
    "plain_text",
    "markdown",
    "html",
    "pdf",
    "structured_json",
    "other",
]
C7MovementDisposition = Literal[
    "PRESERVED_AS",
    "MOVED_TO",
    "REIMPLEMENTED_AS",
    "DECLARED_LOSS",
    "EXPLICITLY_REJECTED",
    "UNASSIGNED_BLOCKER",
]
C7TerminalOutcome = Literal[
    "STRUCTURED_MATERIAL_CANDIDATE",
    "REJECTED",
    "DEFERRED",
]
C7TerminalFailureCode = Literal[
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

c7_alternatives = define_vocabulary("c7.digestion.alternatives", get_args(C7Alternative))
c7_input_kinds = define_vocabulary("c7.ingest.input_kind", get_args(C7InputKind))
c7_content_formats = define_vocabulary("c7.ingest.content_format", get_args(C7ContentFormat))
c7_movement_dispositions = define_vocabulary(
    "c7.movement.disposition", get_args(C7MovementDisposition)
)
c7_terminal_outcomes = define_vocabulary(
    "c7.movement.terminal_outcome", get_args(C7TerminalOutcome)
)
c7_terminal_failures = define_failure_family(
    "c7.movement.terminal_failure", get_args(C7TerminalFailureCode)
)


def _invalid_member(field: str, value: object) -> Failure:
    return Failure(
        family="kit.codec",
        code="CODEC_INVALID_FIELD",
        message="member is outside the closed vocabulary",
        context={"field": field, "value": value},
    )


def _parse_alternative(value: dict[str, object]) -> str | Failure:
    member = value.get("member")
    return member if c7_alternatives.has(member) else _invalid_member("member", member)


def _parse_input_kind(value: dict[str, object]) -> str | Failure:
    member = value.get("member")
    return member if c7_input_kinds.has(member) else _invalid_member("member", member)


def _parse_content_format(value: dict[str, object]) -> str | Failure:
    member = value.get("member")
    return member if c7_content_formats.has(member) else _invalid_member("member", member)


def _parse_disposition(value: dict[str, object]) -> str | Failure:
    member = value.get("member")
    return (
        member
        if c7_movement_dispositions.has(member)
        else _invalid_member("member", member)
    )


def _parse_terminal_outcome(value: dict[str, object]) -> str | Failure:
    member = value.get("member")
    return member if c7_terminal_outcomes.has(member) else _invalid_member("member", member)


c7_alternative_codec = define_codec(
    name="c7.digestion.alternative",
    discriminant="c7.digestion.alternative.v1",
    keys=("kind", "member"),
    parse=_parse_alternative,
    to_wire=lambda member: {"kind": "c7.digestion.alternative.v1", "member": member},
)
c7_input_kind_codec = define_codec(
    name="c7.ingest.input_kind",
    discriminant="c7.ingest.input_kind.v1",
    keys=("kind", "member"),
    parse=_parse_input_kind,
    to_wire=lambda member: {"kind": "c7.ingest.input_kind.v1", "member": member},
)
c7_content_format_codec = define_codec(
    name="c7.ingest.content_format",
    discriminant="c7.ingest.content_format.v1",
    keys=("kind", "member"),
    parse=_parse_content_format,
    to_wire=lambda member: {"kind": "c7.ingest.content_format.v1", "member": member},
)
c7_movement_disposition_codec = define_codec(
    name="c7.movement.disposition",
    discriminant="c7.movement.disposition.v1",
    keys=("kind", "member"),
    parse=_parse_disposition,
    to_wire=lambda member: {"kind": "c7.movement.disposition.v1", "member": member},
)
c7_terminal_outcome_codec = define_codec(
    name="c7.movement.terminal_outcome",
    discriminant="c7.movement.terminal_outcome.v1",
    keys=("kind", "member"),
    parse=_parse_terminal_outcome,
    to_wire=lambda member: {"kind": "c7.movement.terminal_outcome.v1", "member": member},
)

__all__ = [
    "c7_alternatives",
    "c7_alternative_codec",
    "c7_content_formats",
    "c7_content_format_codec",
    "c7_input_kinds",
    "c7_input_kind_codec",
    "c7_movement_dispositions",
    "c7_movement_disposition_codec",
    "c7_terminal_failures",
    "c7_terminal_outcomes",
    "c7_terminal_outcome_codec",
]
