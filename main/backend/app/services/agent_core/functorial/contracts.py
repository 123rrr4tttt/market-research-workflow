"""Closed contracts for the lightweight functorial development projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

OperatorRisk = Literal["read_only", "write_shared", "write_external"]
FunctorialFailureCode = Literal[
    "WORKFLOW_NOT_FOUND",
    "OPERATOR_NOT_REGISTERED",
    "OPERATOR_FAILED",
    "OPERATOR_CANCELED",
    "OPERATOR_NEEDS_APPROVAL",
    "OPERATOR_DEFERRED",
]

OPERATOR_RISKS: tuple[OperatorRisk, ...] = (
    "read_only",
    "write_shared",
    "write_external",
)
FUNCTORIAL_FAILURE_CODES: tuple[FunctorialFailureCode, ...] = (
    "WORKFLOW_NOT_FOUND",
    "OPERATOR_NOT_REGISTERED",
    "OPERATOR_FAILED",
    "OPERATOR_CANCELED",
    "OPERATOR_NEEDS_APPROVAL",
    "OPERATOR_DEFERRED",
)


class OperatorValidationError(ValueError):
    """Raised when an operator projection violates the closed risk vocabulary."""


@dataclass(frozen=True, slots=True)
class FunctorialFailure:
    code: FunctorialFailureCode
    message: str
    context: dict[str, Any] | None = None

    @property
    def failure(self) -> bool:
        return True


def failure(
    code: FunctorialFailureCode,
    message: str,
    *,
    context: dict[str, Any] | None = None,
) -> FunctorialFailure:
    if code not in FUNCTORIAL_FAILURE_CODES:
        # kit:boundary — projection-shell programming error, not a domain failure.
        raise ValueError(f"unknown functorial failure code: {code}")
    return FunctorialFailure(code=code, message=message, context=context)
