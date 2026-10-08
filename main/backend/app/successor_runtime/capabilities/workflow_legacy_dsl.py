"""Versioned readback for retired workflow compile artifacts.

The active workflow graph compiler is owned by ``app.services.workflow_graph``.
This module keeps only exact-byte interpretation of records written by the
retired static workflow lowering. It never compiles a workflow or constructs a
Program, plan, catalog, or registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, NoReturn

from functorial_kit import Failure

from app.successor_runtime.capabilities.workflow_common import (
    HISTORICAL_C1_DSL_RECEIPT_SCHEMA,
    HISTORICAL_WORKFLOW_V2_RECEIPT_SCHEMA,
    WORKFLOW_DEFINITION_FAILURES,
    WORKFLOW_DSL_PROGRAM_METADATA_SCHEMA,
    WORKFLOW_DSL_PROGRAM_SCHEMA,
    WORKFLOW_DSL_PROJECT_SCOPE_SCHEMA,
    WORKFLOW_DSL_RECEIPT_SCHEMA,
    WORKFLOW_RECEIPT_CONTRACT_INVALID,
    WorkflowJsonValue,
)

__all__ = [
    "HISTORICAL_C1_DSL_FAILURE_CODES",
    "HISTORICAL_C1_DSL_RECEIPT_SCHEMA",
    "HISTORICAL_C1_OPERATION_CATALOG_ID",
    "HISTORICAL_WORKFLOW_V2_RECEIPT_SCHEMA",
    "WORKFLOW_DEFINITION_FAILURES",
    "WORKFLOW_DSL_PROGRAM_METADATA_SCHEMA",
    "WORKFLOW_DSL_PROGRAM_SCHEMA",
    "WORKFLOW_DSL_PROJECT_SCOPE_SCHEMA",
    "WORKFLOW_DSL_RECEIPT_SCHEMA",
    "WorkflowCompileArtifactRead",
    "WorkflowCompileSchemaIdentity",
    "decode_workflow_compile_schema",
    "read_workflow_compile_artifact",
    "replay_workflow_compile_artifact",
]

HISTORICAL_C1_DSL_FAILURE_CODES = (
    "C1_DSL_MALFORMED_PAYLOAD",
    "C1_DSL_DUPLICATE_NODE_ID",
    "C1_DSL_UNSUPPORTED_NODE_TYPE",
    "C1_DSL_MISSING_ENDPOINT",
    "C1_DSL_CYCLE",
    "C1_DSL_COMPILE_FAILURE",
)
HISTORICAL_C1_OPERATION_CATALOG_ID = "mrw.functorial-successor.c1.operations"
WORKFLOW_FAILURE_OWNER = "workflow.definition.compile.v2"
WORKFLOW_FAILURE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"


@dataclass(frozen=True, slots=True)
class WorkflowCompileSchemaIdentity:
    """Explicit read identity for current or historical compile artifacts."""

    schema: str
    era: Literal["current", "historical_v2", "historical_c1"]
    program_schema: str
    project_scope_schema: str
    program_metadata_schema: str


@dataclass(frozen=True, slots=True)
class WorkflowCompileArtifactRead:
    """Exact current or historical artifact bytes with their original hash."""

    identity: WorkflowCompileSchemaIdentity
    raw_bytes: bytes
    sha256: str


def decode_workflow_compile_schema(schema: str) -> WorkflowCompileSchemaIdentity:
    """Decode compile identities without rehashing historical bytes."""

    if schema == WORKFLOW_DSL_RECEIPT_SCHEMA:
        return WorkflowCompileSchemaIdentity(
            schema=schema,
            era="current",
            program_schema=WORKFLOW_DSL_PROGRAM_SCHEMA,
            project_scope_schema=WORKFLOW_DSL_PROJECT_SCOPE_SCHEMA,
            program_metadata_schema=WORKFLOW_DSL_PROGRAM_METADATA_SCHEMA,
        )
    if schema == HISTORICAL_WORKFLOW_V2_RECEIPT_SCHEMA:
        return WorkflowCompileSchemaIdentity(
            schema=schema,
            era="historical_v2",
            program_schema="mrw.workflow.definition.compile.program.v2",
            project_scope_schema="mrw.workflow.definition.compile.project-scope.v2",
            program_metadata_schema="mrw.workflow.definition.compile.program-metadata.v2",
        )
    if schema == HISTORICAL_C1_DSL_RECEIPT_SCHEMA:
        return WorkflowCompileSchemaIdentity(
            schema=schema,
            era="historical_c1",
            program_schema="mrw.successor.c1.legacy-dsl.v1",
            project_scope_schema="mrw.successor.c1.legacy-dsl.project-scope.v1",
            program_metadata_schema="mrw.successor.c1.legacy-dsl.program-metadata.v1",
        )
    _raise_contract_failure(
        _contract_failure(
            WORKFLOW_RECEIPT_CONTRACT_INVALID,
            f"unsupported workflow compile receipt schema: {schema}",
            operation="workflow.definition.decode_historical_schema",
            site="schema",
        )
    )


def read_workflow_compile_artifact(
    *,
    schema: str,
    raw_bytes: object,
) -> WorkflowCompileArtifactRead:
    """Read versioned workflow bytes without normalizing or re-encoding them."""

    if not isinstance(raw_bytes, bytes):
        _raise_contract_failure(
            _contract_failure(
                WORKFLOW_RECEIPT_CONTRACT_INVALID,
                "workflow compile artifact raw_bytes must be bytes",
                operation="workflow.definition.read_historical_artifact",
                site="raw_bytes",
                exception_type=TypeError,
            ),
            TypeError,
        )
    return WorkflowCompileArtifactRead(
        identity=decode_workflow_compile_schema(schema),
        raw_bytes=raw_bytes,
        sha256=sha256(raw_bytes).hexdigest(),
    )


def replay_workflow_compile_artifact(artifact: WorkflowCompileArtifactRead) -> bytes:
    """Replay exact stored bytes after verifying their historical hash."""

    if sha256(artifact.raw_bytes).hexdigest() != artifact.sha256:
        _raise_contract_failure(
            _contract_failure(
                WORKFLOW_RECEIPT_CONTRACT_INVALID,
                "workflow compile artifact hash mismatch",
                operation="workflow.definition.replay_historical_artifact",
                site="sha256",
            )
        )
    return artifact.raw_bytes


def _contract_failure(
    code: str,
    message: str,
    *,
    operation: str,
    site: str,
    exception_type: type[Exception] = ValueError,
    **details: WorkflowJsonValue,
) -> Failure:
    return WORKFLOW_DEFINITION_FAILURES.fail(
        code,
        message,
        {
            "owner": WORKFLOW_FAILURE_OWNER,
            "operation": operation,
            "site": site,
            "public_exception": exception_type.__name__,
            "public_message": message,
            "witness": WORKFLOW_FAILURE_WITNESS,
            **details,
        },
    )


def _raise_contract_failure(
    failure: Failure,
    exception_type: type[Exception] = ValueError,
) -> NoReturn:
    context = failure.context or {}
    if (
        failure.family != WORKFLOW_DEFINITION_FAILURES.name
        or context.get("public_exception") != exception_type.__name__
        or not context.get("public_message")
    ):
        # kit:boundary owner=workflow_legacy_dsl.py class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w06_c2_total_core_failure_lifts
        raise TypeError("workflow compile contract lift context is incomplete")
    # kit:boundary owner=workflow_legacy_dsl.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=workflow.definition.failure witness=test:test_current_compile_reader_and_unknown_versions_are_explicit
    raise exception_type(str(context["public_message"]))
