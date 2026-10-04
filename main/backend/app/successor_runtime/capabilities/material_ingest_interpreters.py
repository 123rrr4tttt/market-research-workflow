"""Pure C7 interpreter scaffolding for staged candidate and projections.

These interpreters are deterministic, side-effect-free rewrites of the ingest
staging/projection boundary.  They never call the legacy writer, never touch a
database, index, graph or provider, and never claim adoption authority.
``provider_calls`` and all authority flags stay zero/false by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from app.successor_runtime.capabilities.material_ingest_common import (
    MaterialIngestSubmission,
    MaterialReconciliationDecision,
    EffectOutcome,
    ProjectionDiff,
    stage_ingest_submission,
)

__all__ = [
    "MATERIAL_INTERPRETER_PROFILE_IDS",
    "MaterialInterpreterOutcome",
    "MaterialInterpreterSuccess",
    "MaterialInterpreterFailure",
    "interpret_commit_readback",
    "interpret_projection_diff",
    "interpret_reconciliation",
    "interpret_staged_candidate",
]


@dataclass(frozen=True, slots=True)
class MaterialInterpreterSuccess:
    value: object
    disposition: Literal["SUCCEEDED"] = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class MaterialInterpreterFailure:
    code: str
    message: str
    disposition: Literal["FAILED"] = "FAILED"


MaterialInterpreterOutcome: TypeAlias = MaterialInterpreterSuccess | MaterialInterpreterFailure

MATERIAL_INTERPRETER_PROFILE_IDS = {
    "staged_candidate": "material.ingest.stage-candidate.pure.v2",
    "commit_readback": "material.ingest.commit-readback.interface.v2",
    "projection_diff": "material.ingest.projection-diff.pure.v2",
    "reconciliation": "material.ingest.reconcile.policy.v2",
}


def interpret_staged_candidate(
    submission: MaterialIngestSubmission,
) -> MaterialInterpreterOutcome:
    """Stage one candidate; returns no admission/readback authority."""

    outcome: EffectOutcome = stage_ingest_submission(submission)
    if outcome.disposition != "SUCCEEDED":
        return MaterialInterpreterFailure(
            code="stage_failed",
            message="staged candidate interpreter did not succeed",
        )
    return MaterialInterpreterSuccess(
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
) -> MaterialInterpreterOutcome:
    """Project typed C7.2 readback; never performs a canonical write."""

    return MaterialInterpreterSuccess(
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


def interpret_projection_diff(diff: ProjectionDiff) -> MaterialInterpreterOutcome:
    return MaterialInterpreterSuccess(
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
    decision: MaterialReconciliationDecision,
) -> MaterialInterpreterOutcome:
    return MaterialInterpreterSuccess(
        value={
            "new_attempt_allowed": decision.new_attempt_allowed,
            "requirement": decision.requirement,
            "reason": decision.reason,
            "provider_calls": 0,
            "authority": False,
        }
    )
