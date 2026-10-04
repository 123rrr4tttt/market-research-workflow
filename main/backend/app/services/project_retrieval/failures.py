"""Compatibility re-export of the canonical project-retrieval failure family.

The authoritative family and failure constructor now live in the pure
capability shared-contract module; the service retains its existing HTTP/skill
error envelope and public callers lift these failures as before.
"""

from app.successor_runtime.capabilities.retrieval_common import (
    ProjectRetrievalFailureCode,
    project_retrieval_failures,
    retrieval_failure,
)

__all__ = ["ProjectRetrievalFailureCode", "project_retrieval_failures", "retrieval_failure"]
