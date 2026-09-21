"""Canonical research object references shared by objects and relations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .codec import _failure, _raise_failure, is_sha256_hex
from .object_types import ObjectType

__all__ = ["LIFECYCLE_STATES", "LifecycleState", "ResearchObjectRef"]

LifecycleState = Literal["DRAFT", "ADMITTED", "SUPERSEDED", "RETRACTED"]
LIFECYCLE_STATES: tuple[str, ...] = (
    "DRAFT",
    "ADMITTED",
    "SUPERSEDED",
    "RETRACTED",
)
_INCARNATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


@dataclass(frozen=True, slots=True)
class ResearchObjectRef:
    object_id: str
    object_type: ObjectType
    project_key: str
    revision: int = 1
    incarnation: str = "inc-1"
    owner_binding_ref: str = ""
    content_ref: str = ""
    content_digest: str = ""
    provenance_closure_digest: str = ""
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    lifecycle_state: str = "DRAFT"

    def __post_init__(self) -> None:
        required_strings = {
            "object_id": self.object_id,
            "project_key": self.project_key,
            "owner_binding_ref": self.owner_binding_ref,
            "content_ref": self.content_ref,
        }
        for field_name, value in required_strings.items():
            if not isinstance(value, str) or not value.strip():
                _raise_failure(
                    _failure(
                        "RESEARCH_OBJECT_REF_INVALID",
                        f"ResearchObjectRef {field_name} must be non-empty",
                        ValueError,
                        site=f"ResearchObjectRef.{field_name}",
                    ),
                    ValueError,
                )
        if not isinstance(self.object_type, ObjectType):
            _raise_failure(
                _failure(
                    "RESEARCH_OBJECT_REF_INVALID",
                    "ResearchObjectRef object_type must be an ObjectType",
                    TypeError,
                    site="ResearchObjectRef.object_type",
                ),
                TypeError,
            )
        for field_name in (
            "type_id",
            "schema_version",
            "codec_id",
            "canonical_codec_version",
        ):
            value = getattr(self.object_type, field_name)
            if not isinstance(value, str) or not value.strip():
                _raise_failure(
                    _failure(
                        "RESEARCH_OBJECT_REF_INVALID",
                        f"ResearchObjectRef object_type.{field_name} must be non-empty",
                        ValueError,
                        site=f"ResearchObjectRef.object_type.{field_name}",
                    ),
                    ValueError,
                )
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 1
        ):
            _raise_failure(
                _failure(
                    "RESEARCH_OBJECT_REF_INVALID",
                    "ResearchObjectRef revision must be an integer >= 1",
                    ValueError,
                    site="ResearchObjectRef.revision",
                ),
                ValueError,
            )
        if not isinstance(self.incarnation, str) or not _INCARNATION_PATTERN.fullmatch(
            self.incarnation
        ):
            _raise_failure(
                _failure(
                    "RESEARCH_OBJECT_REF_INVALID",
                    "ResearchObjectRef incarnation is invalid",
                    ValueError,
                    site="ResearchObjectRef.incarnation",
                ),
                ValueError,
            )
        for field_name in ("content_digest", "provenance_closure_digest"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not is_sha256_hex(value):
                _raise_failure(
                    _failure(
                        "RESEARCH_OBJECT_REF_INVALID",
                        f"ResearchObjectRef {field_name} must be lowercase 64-hex",
                        ValueError,
                        site=f"ResearchObjectRef.{field_name}",
                    ),
                    ValueError,
                )
        if self.lifecycle_state not in LIFECYCLE_STATES:
            _raise_failure(
                _failure(
                    "RESEARCH_OBJECT_REF_INVALID",
                    f"invalid ResearchObjectRef lifecycle state: {self.lifecycle_state}",
                    ValueError,
                    site="ResearchObjectRef.lifecycle_state",
                ),
                ValueError,
            )
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from > self.valid_to
        ):
            _raise_failure(
                _failure(
                    "RESEARCH_OBJECT_REF_INVALID",
                    "ResearchObjectRef valid_from must not be after valid_to",
                    ValueError,
                    site="ResearchObjectRef.validity",
                ),
                ValueError,
            )
