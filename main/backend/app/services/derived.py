"""Compatibility-preserving marker for non-authoritative dictionary projections."""

from __future__ import annotations

from typing import Any, Literal


DerivedKind = Literal[
    "view",
    "plan",
    "preflight",
    "simulation",
    "external_claim",
    "generated_evidence",
]


class NonAuthoritativeDict(dict[str, Any]):
    """A dict-compatible derived projection that cannot claim fact authority."""

    authoritative: Literal[False] = False
    reverse_write: Literal[False] = False

    def __init__(
        self,
        value: dict[str, Any],
        *,
        derived_as: DerivedKind,
        fact_source: str,
    ) -> None:
        super().__init__(value)
        self.derived_as = derived_as
        self.fact_source = fact_source
