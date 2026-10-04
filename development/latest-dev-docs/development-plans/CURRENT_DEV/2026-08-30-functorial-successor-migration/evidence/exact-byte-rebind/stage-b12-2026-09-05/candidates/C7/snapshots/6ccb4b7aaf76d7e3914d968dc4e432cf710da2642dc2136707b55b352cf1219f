"""Pure C7 interpreter scaffolding for staged candidate and projections.

These interpreters are deterministic, side-effect-free rewrites of the ingest
staging/projection boundary.  They never call the legacy writer, never touch a
database, index, graph or provider, and never claim adoption authority.
``provider_calls`` and all authority flags stay zero/false by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from app.successor_runtime.capabilities.ingest_c7_common import (
    C7IngestSubmission,
    C7ReconciliationDecision,
    EffectOutcome,
    ProjectionDiff,
    stage_ingest_submission,
)

__all__ = [
    "C7_INTERPRETER_PROFILE_IDS",
    "IngestInterpreterOutcome",
    "IngestInterpreterSuccess",
    "InterpreterFailureC7",
    "interpret_commit_readback",
    "interpret_projection_diff",
    "interpret_reconciliation",
    "interpret_staged_candidate",
]


@dataclass(frozen=True, slots=True)
class IngestInterpreterSuccess:
    value: object
    disposition: Literal["SUCCEEDED"] = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class InterpreterFailureC7:
    code: str
    message: str
    disposition: Literal["FAILED"] = "FAILED"


IngestInterpreterOutcome: TypeAlias = IngestInterpreterSuccess | InterpreterFailureC7

C7_INTERPRETER_PROFILE_IDS = {
    "staged_candidate": "successor.ingest_index.stage_candidate.pure.v1",
    "commit_readback": "successor.ingest_index.commit_readback.interface.v1",
    "projection_diff": "successor.ingest_index.projection_diff.pure.v1",
    "reconciliation": "successor.ingest_index.reconcile.policy.v1",
}


def interpret_staged_candidate(
    submission: C7IngestSubmission,
) -> IngestInterpreterOutcome:
    """Stage one candidate; returns no admission/readback authority."""

    outcome: EffectOutcome = stage_ingest_submission(submission)
    if outcome.disposition != "SUCCEEDED":
        return InterpreterFailureC7(
            code="stage_failed",
            message="staged candidate interpreter did not succeed",
        )
    return IngestInterpreterSuccess(
        value={
            "receipt": dict(outcome.receipt),
            "provider_calls": 0,
            "authority": False,
        }
    )


def interpret_commit_readback(
    *,
    commit_intent_id: str,
    content_digest_hex: str,
    verification_binding_digest: str,
    state: str,
) -> IngestInterpreterOutcome:
    """Project typed C7.2 readback; never performs a canonical write."""

    return IngestInterpreterSuccess(
        value={
            "commit_intent_id": commit_intent_id,
            "content_digest": content_digest_hex,
            "verification_binding_digest": verification_binding_digest,
            "state": state,
            "document_write": False,
            "provider_calls": 0,
            "authority": False,
        }
    )


def interpret_projection_diff(diff: ProjectionDiff) -> IngestInterpreterOutcome:
    return IngestInterpreterSuccess(
        value={
            "projection_kind": diff.projection_kind,
            "source_digest": diff.source_digest,
            "projection_digest": diff.projection_digest,
            "declared_loss": list(diff.declared_loss),
            "provider_calls": 0,
            "authority": False,
        }
    )


def interpret_reconciliation(
    decision: C7ReconciliationDecision,
) -> IngestInterpreterOutcome:
    return IngestInterpreterSuccess(
        value={
            "new_attempt_allowed": decision.new_attempt_allowed,
            "requirement": decision.requirement,
            "reason": decision.reason,
            "provider_calls": 0,
            "authority": False,
        }
    )
