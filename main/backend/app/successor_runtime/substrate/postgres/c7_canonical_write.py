"""Successor-only C7.2 canonical commit-write port.

This slice is the narrow assembly boundary between the pure C7.2 rollback
route and the existing ``ingest_c7_movement_admission`` effect slice.  The
port admits one verified candidate through the exact
``admit_verified_candidate`` implementation and returns the typed
commit/readback result.  It never widens authority: the only durable writes
are the successor-owned canonical document table, the successor commit
intents table and the project ``successor_values`` table.  Legacy tables,
providers, exports, promotion and cutover remain closed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.ingest_c7_movements import (
    StructuredMaterialCandidate,
    VerifiedMaterialCandidate,
)
from app.successor_runtime.runtime.admission import VerificationBinding
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7AdmissionConfig,
    C7AdmissionResult,
    C7MovementAdmissionError,
    admit_verified_candidate,
)

__all__ = [
    "C7CanonicalWritePort",
    "C7MovementAdmissionError",
    "PostgresC7CanonicalWritePort",
]


@runtime_checkable
class C7CanonicalWritePort(Protocol):
    """Exact canonical commit-write boundary over successor tables only."""

    def admit(
        self,
        connection: Connection,
        structured_candidate: StructuredMaterialCandidate,
        verified_candidate: VerifiedMaterialCandidate,
        binding: VerificationBinding,
        ordered_event_payloads: Sequence[object],
        *,
        config: C7AdmissionConfig,
        scope: RuntimeScope,
    ) -> C7AdmissionResult: ...


class PostgresC7CanonicalWritePort:
    """Real PostgreSQL port; no authority widening over the admission slice."""

    def admit(
        self,
        connection: Connection,
        structured_candidate: StructuredMaterialCandidate,
        verified_candidate: VerifiedMaterialCandidate,
        binding: VerificationBinding,
        ordered_event_payloads: Sequence[object],
        *,
        config: C7AdmissionConfig,
        scope: RuntimeScope,
    ) -> C7AdmissionResult:
        return admit_verified_candidate(
            connection,
            structured_candidate,
            verified_candidate,
            binding,
            ordered_event_payloads,
            config=config,
            scope=scope,
        )
