"""Canonical contract vocabulary consumed by capability packages.

Capability packages publish operation contracts, but they do not own parallel
Python identities for the shared language.  The definitions re-exported here
are the canonical research/language definitions used by the AST, compiler and
runtime assignment boundary.
"""

from __future__ import annotations

from typing import Literal

from app.successor_runtime.language.algebra import OperationSpec
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.object_contracts import (
    OperationContract,
    OperationContractRef,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "ExecutionClass",
    "ObjectType",
    "OperationContract",
    "OperationContractCatalogSnapshot",
    "OperationContractRef",
    "OperationSpec",
]

ExecutionClass = Literal["PURE_TRANSFORM", "EFFECTFUL", "ADMISSION", "PROJECTION"]
