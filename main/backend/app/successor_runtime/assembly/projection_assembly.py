"""Closed local projection ports used by the mounted successor facade."""

from __future__ import annotations

from typing import Annotated

from app.successor_runtime.assembly.base import sha256_hex
from app.successor_runtime.runtime.projection_native_contribution import (
    PROJECTION_CLIENT_CONTRACT_CELL_ID,
    PROJECTION_COMMAND_QUERY_CELL_ID,
    PROJECTION_READ_MODEL_CELL_ID,
)
from app.successor_runtime.runtime.facade import SuccessorRuntimeFacade
from app.successor_runtime.runtime.facade_contracts import (
    MATERIAL_PROJECTION_CLOSURE_ID,
    MATERIAL_PROJECTION_PROJECTOR_ID,
    MATERIAL_PROJECTION_PROJECTOR_VERSION,
    MATERIAL_PROJECTION_SOURCE_KIND,
    CommandReceipt,
    CommandSubmissionPort,
    FacadeCommandV2,
    FacadeQueryV2,
    ProjectionResponseMetaV2,
    QueryReadPort,
    QueryResult,
)


class _MemoryQueryReadPort(QueryReadPort):
    """Minimal deterministic QueryReadPort; no PostgreSQL or other sink."""

    def read(self, query: FacadeQueryV2) -> QueryResult:
        meta = ProjectionResponseMetaV2(
            project_key=query.meta.project_key,
            trace_id=query.meta.trace_id,
            projection_id=MATERIAL_PROJECTION_CLOSURE_ID,
            project_scope_ref=query.meta.project_scope_ref,
            projector_id=MATERIAL_PROJECTION_PROJECTOR_ID,
            projector_version=MATERIAL_PROJECTION_PROJECTOR_VERSION,
            source_kind=MATERIAL_PROJECTION_SOURCE_KIND,
            source_ref="projection:material-projection-local:source",
            source_incarnation="local-offline:material-projection-inc-2",
            projection_generation=0,
            offset_revision=0,
            projection_revision=1,
            source_digest=sha256_hex("mrw.projection.local-offline.source.v2"),
            cursor=0,
        )
        return QueryResult(
            data={
                "project_key": query.meta.project_key,
                "projection_id": MATERIAL_PROJECTION_CLOSURE_ID,
                "query_kind": query.query_kind,
                "cells": {
                    PROJECTION_COMMAND_QUERY_CELL_ID: "INSTALLED",
                    PROJECTION_CLIENT_CONTRACT_CELL_ID: "INSTALLED",
                    PROJECTION_READ_MODEL_CELL_ID: "INSTALLED",
                },
                "no_postgres_write": True,
            },
            meta=meta,
        )


class _MemoryCommandSubmissionPort(CommandSubmissionPort):
    """Minimal deterministic CommandSubmissionPort; never reached by the route."""

    def submit(self, command: FacadeCommandV2) -> CommandReceipt:
        return CommandReceipt(
            receipt_ref="material-projection-receipt:local-offline-validation",
            command_id=command.command_id,
            request_digest=sha256_hex("mrw.projection.local-offline.command.v2"),
            state="TERMINAL",
            idempotency_id=command.idempotency_key,
            logical_request_id="logical:local-offline:material-projection-validation",
            observed_at="2026-09-02T00:00:00+00:00",
        )


def build_deterministic_facade_closure() -> Annotated[
    SuccessorRuntimeFacade,
    "kit:prepared-command "
    "effect_boundary=successor_runtime.projection_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """LOCAL_OFFLINE facade bound only to minimal in-memory ports."""

    return SuccessorRuntimeFacade(
        submission_port=_MemoryCommandSubmissionPort(),
        query_port=_MemoryQueryReadPort(),
    )


def build_deterministic_command_submission_port() -> Annotated[
    CommandSubmissionPort,
    "kit:prepared-command "
    "effect_boundary=successor_runtime.projection_assembly "
    "witness=test:test_w08a_remaining_assembly_bindings_are_prepared_commands",
]:
    """Return the deterministic no-write command submission port.

    The registry-backed HTTP facade reuses this port so commands stay
    validation-only and never perform a write while the read facade is being
    wired to real PostgreSQL reads.
    """

    return _MemoryCommandSubmissionPort()


__all__ = [
    "build_deterministic_command_submission_port",
    "build_deterministic_facade_closure",
]
