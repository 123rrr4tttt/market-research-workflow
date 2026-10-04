"""Canonical current-version business-line vocabulary.

This module intentionally depends only on the standard library so backend
code and root automation scripts can read the same declarations without
loading application services.
"""

from __future__ import annotations

from typing import Literal, get_args

__all__ = [
    "BUSINESS_LINE_KEYS",
    "BUSINESS_LINE_VOCABULARY_VERSION",
    "BusinessLineKey",
    "WORKER_REQUIRED_BUSINESS_LINE_KEYS",
    "WorkerRequiredBusinessLineKey",
    "is_business_line_key",
    "is_worker_required_business_line_key",
    "normalize_business_line_key",
]

BUSINESS_LINE_VOCABULARY_VERSION = "business_line.vocabulary.current.v1"

BusinessLineKey = Literal[
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "projects_config_workflow",
    "dashboard_admin_governance",
    "writing_knowledge_graph_agent",
    "runtime_ops",
]

WorkerRequiredBusinessLineKey = Literal[
    "ingest",
    "search_discovery_index",
    "resource_source_library",
    "writing_knowledge_graph_agent",
]

BUSINESS_LINE_KEYS: tuple[BusinessLineKey, ...] = get_args(BusinessLineKey)
WORKER_REQUIRED_BUSINESS_LINE_KEYS: tuple[WorkerRequiredBusinessLineKey, ...] = get_args(WorkerRequiredBusinessLineKey)


def normalize_business_line_key(value: object) -> str:
    """Normalize an external line-key representation."""

    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def is_business_line_key(value: object) -> bool:
    """Return whether a normalized value is a current-version line key."""

    return normalize_business_line_key(value) in BUSINESS_LINE_KEYS


def is_worker_required_business_line_key(value: object) -> bool:
    """Return whether a normalized value is in the worker-required subset."""

    return normalize_business_line_key(value) in WORKER_REQUIRED_BUSINESS_LINE_KEYS
