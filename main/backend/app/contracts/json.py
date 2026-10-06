"""Shared JSON value types used by agent calls and persisted session records."""

from collections.abc import Mapping, Sequence
from typing import TypeAlias

JSONValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | None
    | Sequence["JSONValue"]
    | Mapping[str, "JSONValue"]
)
JSONObject: TypeAlias = dict[str, JSONValue]
