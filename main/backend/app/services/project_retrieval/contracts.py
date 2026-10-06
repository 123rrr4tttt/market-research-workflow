"""Static wire contracts for the project retrieval authority.

The runtime continues to use the existing JSON mappings.  These declarations
give those mappings one package-owned type vocabulary; they do not add a
second parser, schema, persistence model, or execution facade.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypeAlias, TypedDict, Union


RetrievalJsonAtom: TypeAlias = str | int | float | bool | None
RetrievalJsonArray: TypeAlias = list["RetrievalJsonValue"]
RetrievalJsonValue: TypeAlias = Union[
    RetrievalJsonAtom,
    RetrievalJsonArray,
    "RetrievalJsonObject",
]  # noqa: UP007
RetrievalJsonObject: TypeAlias = dict[str, RetrievalJsonValue]


class RetrievalFailureWire(TypedDict, total=False):
    family: str
    code: str
    message: str
    context: RetrievalJsonObject
    path: str


class FormalizationFailed(TypedDict):
    status: Literal["failed"]
    error: RetrievalFailureWire


class FormalizationNoClaim(TypedDict):
    status: Literal["no_claim"]
    gaps: list[str]


class FormalizationProposed(TypedDict):
    status: Literal["proposed"]
    proposal: RetrievalJsonObject
    gaps: list[str]


FormalizationResult: TypeAlias = FormalizationFailed | FormalizationNoClaim | FormalizationProposed


class RetrievalRunFailure(TypedDict):
    status: Literal["failed"]
    error: RetrievalFailureWire
    attempts: list[RetrievalJsonObject]
    candidates: list[RetrievalJsonObject]
    materials: list[RetrievalJsonObject]
    graph: None
    session_id: NotRequired[str]
    failures: NotRequired[list[RetrievalJsonObject]]
    gaps: NotRequired[list[RetrievalJsonObject]]
    report: NotRequired[RetrievalJsonObject]


class RetrievalRunCompleted(TypedDict):
    status: Literal["completed", "partial", "blocked"]
    session_id: str
    plan_id: str
    attempts: list[RetrievalJsonObject]
    candidates: list[RetrievalJsonObject]
    materials: list[RetrievalJsonObject]
    graph: RetrievalJsonObject | None
    discovery: RetrievalJsonObject
    topology_write: RetrievalJsonObject
    failures: list[RetrievalJsonObject]
    gaps: list[RetrievalJsonObject]
    report: RetrievalJsonObject
    followup_rounds: int
    mode_id: NotRequired[RetrievalJsonValue]
    mode_version: NotRequired[RetrievalJsonValue]


RetrievalRunResult: TypeAlias = RetrievalRunFailure | RetrievalRunCompleted
