"""Research relation contracts and the generic relation record."""

from __future__ import annotations

from dataclasses import dataclass

from .codec import finalize_digest
from .evidence import QUALIFICATION_DIRECTIONS
from .identities import ResearchObjectRef

__all__ = [
    "RELATION_CONTRACT_BY_ID",
    "RELATION_CONTRACT_REFS",
    "RELATION_CONTRACTS",
    "RELATION_KINDS",
    "RelationContract",
    "ResearchRelation",
]

RELATION_KINDS: tuple[str, ...] = (
    "derived_from",
    "answers",
    "opens",
    "cites",
    "supersedes",
    "delivered_as",
)


@dataclass(frozen=True, slots=True)
class RelationContract:
    type_id: str
    storage: str = "research_relations_only"
    directions: tuple[str, ...] = ()
    requires_authoritative_receipt: bool = False


RELATION_CONTRACTS: tuple[RelationContract, ...] = (
    RelationContract("EvidenceQualification.v1", directions=QUALIFICATION_DIRECTIONS),
    RelationContract("derived_from.v1"),
    RelationContract("answers.v1"),
    RelationContract("opens.v1"),
    RelationContract("cites.v1"),
    RelationContract("supersedes.v1"),
    RelationContract("delivered_as.v1", requires_authoritative_receipt=True),
)

RELATION_CONTRACT_REFS: tuple[str, ...] = tuple(
    contract.type_id for contract in RELATION_CONTRACTS
)

RELATION_CONTRACT_BY_ID: dict[str, RelationContract] = {
    contract.type_id: contract for contract in RELATION_CONTRACTS
}


@dataclass(frozen=True, slots=True)
class ResearchRelation:
    relation_id: str
    relation_type: str
    project_key: str
    source_ref: ResearchObjectRef
    target_ref: ResearchObjectRef
    provenance_closure_digest: str
    direction: str | None = None
    scope_ref: str | None = None
    uncertainty_profile_ref: str | None = None
    validity: str = "VALID"
    revision: int = 1
    incarnation: str = "inc-1"
    state: str = "ACTIVE"
    relation_digest: str | None = None

    def __post_init__(self) -> None:
        if self.relation_type not in RELATION_KINDS:
            raise ValueError(f"invalid relation type: {self.relation_type}")
        finalize_digest(self, "relation_digest")
