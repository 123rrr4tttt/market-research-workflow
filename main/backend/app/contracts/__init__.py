"""Standardized API and task contracts."""

from .api import error_response, success_response
from .errors import ErrorCode, map_exception_to_error
from .ingest_digestion import (
    ContentFormat,
    DigestionDecision,
    DigestionStage,
    IngestInputKind,
    IngestTimeSemantics,
    LongCycleAutomationStatus,
    LongCycleTaskObject,
    LongCycleTaskSnapshot,
    LongCycleTaskStatus,
    NormalizedIngestEnvelope,
)
from .responses import ApiEnvelope, ApiErrorModel, ApiMetaModel, PaginationMetaModel, TaskResultData, fail, ok, ok_page
from .tasks import task_result_response

__all__ = [
    "ApiEnvelope",
    "ApiErrorModel",
    "ApiMetaModel",
    "ContentFormat",
    "DigestionDecision",
    "DigestionStage",
    "ErrorCode",
    "IngestInputKind",
    "IngestTimeSemantics",
    "LongCycleAutomationStatus",
    "LongCycleTaskObject",
    "LongCycleTaskSnapshot",
    "LongCycleTaskStatus",
    "NormalizedIngestEnvelope",
    "PaginationMetaModel",
    "TaskResultData",
    "error_response",
    "fail",
    "map_exception_to_error",
    "ok",
    "ok_page",
    "success_response",
    "task_result_response",
]
