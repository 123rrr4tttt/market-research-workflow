"""Shared closed declarations for the existing C8 semantic vocabulary.

These declarations are the shared source for kit registry projection.  Native
runtime ownership and executable profiles remain in the C8 capability modules;
in particular, the C8.4 contribution references ``c8_graph_failures.codes``
directly.  This module does not execute a C8 movement or delivery operation.
"""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family, define_vocabulary

C8OperationKind = Literal[
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

C8TypedKnowledgeFailureCode = Literal[
    "DEMAND_READ_UNAVAILABLE",
    "DEMAND_READ_AMBIGUOUS",
    "CANONICAL_REF_VALIDATION_FAILED",
]
C8WritingFailureCode = Literal[
    "WRITING_SYNTHESIS_INCOMPLETE",
    "WRITING_STAGE_INVALID",
]
C8GraphFailureCode = Literal[
    "GRAPH_PROJECTION_DECLARED_LOSS",
    "GRAPH_ITEM_CANONICAL_REF_INVALID",
]
C8ReportDeliveryFailureCode = Literal[
    "REPORT_LOCATOR_READ_ONLY_UNAVAILABLE",
    "REPORT_ADMISSION_INTERFACE_ONLY",
    "REPORT_EXPORT_NOT_EXECUTED",
]

c8_operation_kinds = define_vocabulary("c8.operation.kind", get_args(C8OperationKind))
c8_typed_knowledge_failures = define_failure_family(
    "c8.typed_knowledge.failure", get_args(C8TypedKnowledgeFailureCode)
)
c8_writing_failures = define_failure_family(
    "c8.writing.failure", get_args(C8WritingFailureCode)
)
c8_graph_failures = define_failure_family(
    "c8.graph.failure", get_args(C8GraphFailureCode)
)
c8_report_delivery_failures = define_failure_family(
    "c8.report_delivery.failure", get_args(C8ReportDeliveryFailureCode)
)

__all__ = [
    "c8_graph_failures",
    "c8_operation_kinds",
    "c8_report_delivery_failures",
    "c8_typed_knowledge_failures",
    "c8_writing_failures",
]
