"""Versioned exact-byte readback for retired workflow slice acceptances.

The former A/B/C qualification surface no longer participates in workflow
execution. This module retains only historical artifact interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, NoReturn

from functorial_kit import Failure

from app.successor_runtime.capabilities.workflow_common import (
    HISTORICAL_C1_ACCEPTANCE_SCHEMA,
    WORKFLOW_ACCEPTANCE_DIGEST_INVALID,
    WORKFLOW_ACCEPTANCE_INPUT_INVALID,
    WORKFLOW_ACCEPTANCE_SCHEMA,
    WORKFLOW_DEFINITION_FAILURES,
)

__all__ = [
    "HISTORICAL_C1_ACCEPTANCE_SCHEMA",
    "WORKFLOW_ACCEPTANCE_SCHEMA",
    "WorkflowAcceptanceArtifactRead",
    "WorkflowAcceptanceError",
    "WorkflowAcceptanceSchemaIdentity",
    "decode_workflow_acceptance_schema",
    "read_workflow_acceptance_artifact",
    "replay_workflow_acceptance_artifact",
]

WORKFLOW_FAILURE_OWNER = "workflow.runtime.observe.v2"
WORKFLOW_FAILURE_WITNESS = "test:test_w06_retained_failure_lifts_preserve_public_abi"


class WorkflowAcceptanceError(ValueError):
    """A versioned workflow acceptance artifact is invalid."""

    def __init__(self, message: str, failure: Failure | None = None) -> None:
        super().__init__(message)
        self.failure = failure


@dataclass(frozen=True, slots=True)
class WorkflowAcceptanceSchemaIdentity:
    """Explicit identity for current or historical workflow acceptance bytes."""

    schema: str
    era: Literal["current", "historical_c1"]


@dataclass(frozen=True, slots=True)
class WorkflowAcceptanceArtifactRead:
    """Exact workflow acceptance bytes retained across versioned readback."""

    identity: WorkflowAcceptanceSchemaIdentity
    raw_bytes: bytes
    sha256: str


def decode_workflow_acceptance_schema(
    schema: str,
) -> WorkflowAcceptanceSchemaIdentity:
    if schema == WORKFLOW_ACCEPTANCE_SCHEMA:
        return WorkflowAcceptanceSchemaIdentity(schema=schema, era="current")
    if schema == HISTORICAL_C1_ACCEPTANCE_SCHEMA:
        return WorkflowAcceptanceSchemaIdentity(schema=schema, era="historical_c1")
    _raise_acceptance_failure(
        _acceptance_failure(
            WORKFLOW_ACCEPTANCE_INPUT_INVALID,
            f"unsupported workflow acceptance schema: {schema}",
            site="schema",
        )
    )


def read_workflow_acceptance_artifact(
    *,
    schema: str,
    raw_bytes: bytes,
) -> WorkflowAcceptanceArtifactRead:
    """Read acceptance bytes without normalizing or re-encoding them."""

    if not isinstance(raw_bytes, bytes):
        _raise_acceptance_failure(
            _acceptance_failure(
                WORKFLOW_ACCEPTANCE_INPUT_INVALID,
                "workflow acceptance artifact raw_bytes must be bytes",
                site="raw_bytes",
            )
        )
    return WorkflowAcceptanceArtifactRead(
        identity=decode_workflow_acceptance_schema(schema),
        raw_bytes=raw_bytes,
        sha256=sha256(raw_bytes).hexdigest(),
    )


def replay_workflow_acceptance_artifact(
    artifact: WorkflowAcceptanceArtifactRead,
) -> bytes:
    """Replay exact acceptance bytes after verifying their retained hash."""

    if sha256(artifact.raw_bytes).hexdigest() != artifact.sha256:
        _raise_acceptance_failure(
            _acceptance_failure(
                WORKFLOW_ACCEPTANCE_DIGEST_INVALID,
                "workflow acceptance artifact hash mismatch",
                site="sha256",
            )
        )
    return artifact.raw_bytes


def _acceptance_failure(code: str, message: str, *, site: str) -> Failure:
    return WORKFLOW_DEFINITION_FAILURES.fail(
        code,
        message,
        {
            "owner": WORKFLOW_FAILURE_OWNER,
            "operation": "accept_workflow_slice",
            "site": site,
            "public_exception": "WorkflowAcceptanceError",
            "public_message": message,
            "witness": WORKFLOW_FAILURE_WITNESS,
        },
    )


def _raise_acceptance_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    if (
        failure.family != WORKFLOW_DEFINITION_FAILURES.name
        or context.get("public_exception") != WorkflowAcceptanceError.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=workflow_slice_acceptance.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_retained_failure_lifts_preserve_public_abi
        raise TypeError("workflow acceptance lift context is incomplete")
    # kit:boundary owner=workflow_slice_acceptance.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=workflow.definition.failure witness=test:test_historical_acceptance_readback_preserves_bytes_and_rejects_unknown_schema
    raise WorkflowAcceptanceError(str(context["public_message"]), failure)
