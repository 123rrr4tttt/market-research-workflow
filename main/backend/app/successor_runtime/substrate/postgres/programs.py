"""Exact immutable ProgramSpec repository on a caller-owned connection."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from app.successor_runtime.language.program import ProgramSpec, decode_program_spec
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope

from .research_ledger import (
    ExactContentConflict,
    ProjectRecordNotFound,
    ProjectScopeMismatch,
    assert_table_scope,
    one_mapping,
    project_table,
    scope_actor,
    utcnow,
)


def _canonical_program_bytes(program: ProgramSpec) -> bytes:
    return program.canonical_json()


class ProgramRepository:
    """Immutable absent-or-exact CAS for canonical ProgramSpec bytes."""

    def __init__(self, connection: Connection, tables: Any) -> None:
        self.connection = connection
        self.tables = tables

    def put_exact(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        program: ProgramSpec,
        expected_digest: str,
    ) -> ProgramSpec:
        table = project_table(self.tables, "research_program_specs")
        project_key = assert_table_scope(table, scope)
        if program.project_key != project_key:
            raise ProjectScopeMismatch("ProgramSpec project_key does not match scope")
        resolved = scope.project_scope if isinstance(scope, RuntimeScope) else scope
        if (
            program.project_registry_revision != resolved.project_registry_revision
            or program.project_scope_digest != resolved.scope_digest
        ):
            raise ProjectScopeMismatch("ProgramSpec carries a stale project scope binding")
        canonical = _canonical_program_bytes(program)
        actual = program.digest()
        if expected_digest != actual or program.program_digest != actual:
            raise ExactContentConflict("ProgramSpec digest does not bind canonical bytes")
        payload = json.loads(canonical.decode("utf-8"))
        by_id = one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == project_key,
                    table.c.program_id == program.program_id,
                )
            )
        )
        by_digest = one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == project_key,
                    table.c.program_digest == expected_digest,
                )
            )
        )
        for existing in (by_id, by_digest):
            if existing is None:
                continue
            stored_bytes = json.dumps(
                existing["spec_json"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            if existing["program_id"] != program.program_id or stored_bytes != canonical:
                raise ExactContentConflict("same Program identity/digest has different canonical bytes")
        if by_id is not None:
            return program
        now = utcnow()
        self.connection.execute(
            insert(table).values(
                project_key=project_key,
                program_id=program.program_id,
                contract_version=program.contract_version,
                program_digest=expected_digest,
                spec_json=payload,
                created_by=scope_actor(scope),
                created_at=now,
                updated_at=now,
            )
        )
        return program

    def get(
        self,
        scope: RuntimeScope | ProjectScopeRef,
        program_id: str,
        *,
        expected_digest: str,
    ) -> ProgramSpec:
        table = project_table(self.tables, "research_program_specs")
        project_key = assert_table_scope(table, scope)
        row = one_mapping(
            self.connection.execute(
                select(table).where(
                    table.c.project_key == project_key,
                    table.c.program_id == program_id,
                    table.c.program_digest == expected_digest,
                )
            )
        )
        if row is None:
            raise ProjectRecordNotFound(f"exact ProgramSpec not found: {program_id}")
        spec = decode_program_spec(
            {
                "schema": "mrw.functorial_successor.program_spec.v1",
                "program": row["spec_json"],
                "program_digest": row["program_digest"],
            }
        )
        if spec.digest() != expected_digest:
            raise ExactContentConflict("stored ProgramSpec bytes fail digest readback")
        return spec


__all__ = ["ProgramRepository"]
