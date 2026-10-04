"""Shared closed declarations for the current knowledge semantic vocabulary.

These declarations are the shared source for kit registry projection.  Native
runtime ownership and executable profiles remain in the C8 capability modules;
in particular, the C8.4 contribution references ``c8_graph_failures.codes``
directly.  This module does not execute a C8 movement or delivery operation.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Literal, get_args

from functorial_kit import define_failure_family, define_vocabulary

LegacyKnowledgeOperationKind = Literal[
    "c8.typed_knowledge.demand_read.v1",
    "c8.writing.compose.v1",
    "c8.writing.stage.v1",
    "c8.report.stage.v1",
    "c8.graph.project.v1",
    "c8.report.verify.v1",
    "c8.report.admission.v1",
    "c8.delivery_intent_prepare.v1",
    "delivery.internal_export.v1",
]

KnowledgeOperationKind = Literal[
    "knowledge.read.demand.v2",
    "knowledge.writing.compose.v2",
    "knowledge.writing.stage.v2",
    "knowledge.report.stage.v2",
    "knowledge.graph.project.v2",
    "knowledge.report.verify.v2",
    "knowledge.report.admission.v2",
    "knowledge.report.prepare_delivery_intent.v2",
    "delivery.internal_export.v1",
]

KnowledgeTypedKnowledgeFailureCode = Literal[
    "DEMAND_READ_UNAVAILABLE",
    "DEMAND_READ_AMBIGUOUS",
    "CANONICAL_REF_VALIDATION_FAILED",
]
KnowledgeWritingFailureCode = Literal[
    "WRITING_SYNTHESIS_INCOMPLETE",
    "WRITING_STAGE_INVALID",
]
KnowledgeGraphFailureCode = Literal[
    "GRAPH_PROJECTION_DECLARED_LOSS",
    "GRAPH_ITEM_CANONICAL_REF_INVALID",
]
KnowledgeReportDeliveryFailureCode = Literal[
    "REPORT_LOCATOR_READ_ONLY_UNAVAILABLE",
    "REPORT_ADMISSION_INTERFACE_ONLY",
    "REPORT_EXPORT_NOT_EXECUTED",
]

KnowledgeReportExportContractFailureCode = Literal[
    "authority_contract_invalid",
    "canonical_json_invalid",
    "digest_binding_invalid",
    "evidence_surface_invalid",
    "input_contract_invalid",
    "lookup_not_found",
    "operation_contract_invalid",
    "payload_codec_invalid",
    "program_binding_invalid",
]
KnowledgeReportExportTokenFailureCode = Literal[
    "export_token_actor_mismatch",
    "export_token_already_used",
    "export_token_expired",
    "export_token_markdown_hash_mismatch",
    "export_token_missing_expiry",
    "export_token_revoked",
    "invalid_export_token_format",
    "invalid_export_token_payload",
    "invalid_export_token_signature",
    "unsupported_export_token_contract",
]
KnowledgeReportExportTokenStateFailureCode = Literal[
    "backend_unavailable",
    "conflict",
    "credential_rejected",
    "input_contract_invalid",
    "not_found",
]

# Historical identifiers remain raw readback metadata. They are deliberately
# not live vocabulary/failure declarations, so current registry projection has
# one representation per member set while exact v1 records retain their family
# and code strings.
_LEGACY_C8_OPERATION_KIND_MEMBERS = get_args(LegacyKnowledgeOperationKind)
_LEGACY_C8_FAILURE_CODES = MappingProxyType(
    {
        "c8.typed_knowledge.failure": get_args(KnowledgeTypedKnowledgeFailureCode),
        "c8.writing.failure": get_args(KnowledgeWritingFailureCode),
        "c8.graph.failure": get_args(KnowledgeGraphFailureCode),
        "c8.report_delivery.failure": get_args(KnowledgeReportDeliveryFailureCode),
        "c8.contract.failure": get_args(KnowledgeReportExportContractFailureCode),
        "c8.report_export_token.failure": get_args(
            KnowledgeReportExportTokenFailureCode
        ),
        "c8.report_export_token_state.failure": get_args(
            KnowledgeReportExportTokenStateFailureCode
        ),
    }
)


def read_legacy_c8_operation_kind_members() -> tuple[str, ...]:
    """Return exact historical operation strings without declaring them live."""

    return _LEGACY_C8_OPERATION_KIND_MEMBERS


def read_legacy_c8_failure_codes(family_id: str) -> tuple[str, ...] | None:
    """Read an exact historical family/code set without registry authority."""

    return _LEGACY_C8_FAILURE_CODES.get(family_id)

knowledge_operation_kinds = define_vocabulary("knowledge.operation.kind", get_args(KnowledgeOperationKind))
knowledge_typed_knowledge_failures = define_failure_family(
    "knowledge.read.failure", get_args(KnowledgeTypedKnowledgeFailureCode)
)
knowledge_writing_failures = define_failure_family(
    "knowledge.writing.failure", get_args(KnowledgeWritingFailureCode)
)
knowledge_graph_failures = define_failure_family(
    "knowledge.graph.failure", get_args(KnowledgeGraphFailureCode)
)
knowledge_report_delivery_failures = define_failure_family(
    "knowledge.report-delivery.failure", get_args(KnowledgeReportDeliveryFailureCode)
)
knowledge_report_export_token_failures = define_failure_family(
    "knowledge.report.export-token.failure",
    get_args(KnowledgeReportExportTokenFailureCode),
)
knowledge_report_export_contract_failures = define_failure_family(
    "knowledge.report.export-contract.failure",
    get_args(KnowledgeReportExportContractFailureCode),
)
knowledge_report_export_token_state_failures = define_failure_family(
    "knowledge.report.export-token-state.failure",
    get_args(KnowledgeReportExportTokenStateFailureCode),
)

__all__ = [
    "knowledge_graph_failures",
    "knowledge_operation_kinds",
    "knowledge_report_delivery_failures",
    "knowledge_typed_knowledge_failures",
    "knowledge_writing_failures",
    "knowledge_report_export_token_failures",
    "knowledge_report_export_token_state_failures",
    "knowledge_report_export_contract_failures",
    "read_legacy_c8_failure_codes",
    "read_legacy_c8_operation_kind_members",
]
