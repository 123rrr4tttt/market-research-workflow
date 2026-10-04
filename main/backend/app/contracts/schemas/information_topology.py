"""HTTP schemas for the information-topology structural API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ElementRefSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_key: str = Field(min_length=1, max_length=128)
    module_id: str = Field(min_length=1, max_length=128)
    namespace: str = Field(min_length=1, max_length=255)
    type_id: str = Field(min_length=1, max_length=255)
    local_id: str = Field(min_length=1, max_length=255)


class BoundRefSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: ElementRefSchema
    observed_revision: str = Field(min_length=1, max_length=255)
    content_digest: str | None = Field(default=None, max_length=128)


class EndpointSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=255)
    target: BoundRefSchema
    position: int | None = Field(default=None, ge=0)


class ElementSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: BoundRefSchema
    attributes: dict[str, Any] = Field(default_factory=dict)
    endpoints: list[EndpointSchema] = Field(default_factory=list)


class TopologyStateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=255)
    profile_version: str = Field(min_length=1, max_length=128)
    elements: list[ElementSchema]


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refs: list[ElementRefSchema] = Field(min_length=1, max_length=500)


class TopologyRefSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str = Field(min_length=1, max_length=128)
    namespace: str = Field(min_length=1, max_length=255)
    state_id: str = Field(min_length=1, max_length=255)
    revision: int | None = Field(default=None, ge=1)


class TopologyReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topology_ref: TopologyRefSchema
    filters: dict[str, Any] = Field(default_factory=dict)


class RelationsFindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: BoundRefSchema
    relation_types: list[str] = Field(default_factory=list, max_length=500)
    direction: Literal["incoming", "outgoing", "both"] = "both"


class MappingPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mapping_ref: str = Field(min_length=1, max_length=512)
    input_refs: list[TopologyRefSchema] = Field(min_length=1, max_length=100)


class PatchOperationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["add", "replace", "remove"]
    ref: BoundRefSchema
    element: ElementSchema | None = None


class StatePatchSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: TopologyRefSchema
    base_revision: int | None = Field(ge=1)
    initial_state: TopologyStateSchema | None = None
    patch: list[PatchOperationSchema] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_create_or_update(self) -> "StatePatchSchema":
        if self.base_revision is None and self.initial_state is None:
            # kit:boundary owner=app.contracts.schemas.information_topology.StatePatchSchema.validate_create_or_update class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_patch_api_explicitly_creates_initial_state_and_link_together
            raise ValueError("initial_state is required when base_revision is null")
        if self.base_revision is not None and self.initial_state is not None:
            # kit:boundary owner=app.contracts.schemas.information_topology.StatePatchSchema.validate_create_or_update class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_patch_api_explicitly_creates_initial_state_and_link_together
            raise ValueError("initial_state is only allowed when base_revision is null")
        if self.base_revision is not None and not self.patch:
            # kit:boundary owner=app.contracts.schemas.information_topology.StatePatchSchema.validate_create_or_update class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_patch_api_accepts_explicit_multi_target_batch_shape
            raise ValueError("patch is required when base_revision is supplied")
        if self.target.revision is not None and self.target.revision != self.base_revision:
            # kit:boundary owner=app.contracts.schemas.information_topology.StatePatchSchema.validate_create_or_update class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_patch_api_accepts_explicit_multi_target_batch_shape
            raise ValueError("target.revision must equal base_revision when supplied")
        return self


class LinkWriteSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str = Field(min_length=1, max_length=255)
    record_kind: Literal["relation", "mapping"]
    type_or_rule_ref: str = Field(min_length=1, max_length=512)
    endpoints: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    payload: dict[str, Any] = Field(default_factory=dict)
    base_revision: int | None = Field(default=None, ge=1)
    provenance: dict[str, Any] = Field(default_factory=dict)


class StateReadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: TopologyRefSchema
    base_revision: int = Field(ge=1)

    @model_validator(mode="after")
    def target_revision_matches_base(self) -> "StateReadSchema":
        if self.target.revision is not None and self.target.revision != self.base_revision:
            # kit:boundary owner=app.contracts.schemas.information_topology.StateReadSchema.target_revision_matches_base class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_link_read_set_conflict_leaves_state_and_link_unchanged
            raise ValueError("target.revision must equal base_revision when supplied")
        return self


class LinkReadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_id: str = Field(min_length=1, max_length=255)
    base_revision: int = Field(ge=1)


class PatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The first three fields retain the original single-state request. They may
    # not be combined with state_patches, which is the explicit batch form.
    target: TopologyRefSchema | None = None
    base_revision: int | None = Field(default=None, ge=1)
    patch: list[PatchOperationSchema] | None = Field(default=None, min_length=1, max_length=1000)
    state_patches: list[StatePatchSchema] = Field(default_factory=list, max_length=500)
    link_writes: list[LinkWriteSchema] = Field(default_factory=list, max_length=500)
    read_set: list[StateReadSchema] = Field(default_factory=list, max_length=1000)
    link_read_set: list[LinkReadSchema] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_write_shape(self) -> "PatchRequest":
        legacy_fields_present = any(value is not None for value in (self.target, self.base_revision, self.patch))
        if legacy_fields_present and any(value is None for value in (self.target, self.base_revision, self.patch)):
            # kit:boundary owner=app.contracts.schemas.information_topology.PatchRequest.validate_write_shape class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_patch_api_accepts_explicit_multi_target_batch_shape
            raise ValueError("target, base_revision, and patch must be supplied together")
        if legacy_fields_present and self.state_patches:
            # kit:boundary owner=app.contracts.schemas.information_topology.PatchRequest.validate_write_shape class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_patch_api_accepts_explicit_multi_target_batch_shape
            raise ValueError("legacy target/patch fields cannot be combined with state_patches")
        if (legacy_fields_present and self.target is not None and self.target.revision is not None
                and self.target.revision != self.base_revision):
            # kit:boundary owner=app.contracts.schemas.information_topology.PatchRequest.validate_write_shape class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_patch_api_accepts_explicit_multi_target_batch_shape
            raise ValueError("target.revision must equal base_revision when supplied")
        state_write_count = len(self.state_patches) + (1 if legacy_fields_present else 0)
        if state_write_count + len(self.link_writes) == 0:
            # kit:boundary owner=app.contracts.schemas.information_topology.PatchRequest.validate_write_shape class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_patch_api_accepts_explicit_multi_target_batch_shape
            raise ValueError("at least one state patch or link write is required")
        if len(self.state_patches) > 1 and legacy_fields_present:
            # kit:boundary owner=app.contracts.schemas.information_topology.PatchRequest.validate_write_shape class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_patch_api_accepts_explicit_multi_target_batch_shape
            raise ValueError("ambiguous state patch request")
        return self


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str = Field(min_length=1, max_length=128)
    source: dict[str, Any]


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: TopologyRefSchema
    format: str = Field(min_length=1, max_length=128)


__all__ = [
    "BoundRefSchema", "ElementRefSchema", "ElementSchema", "EndpointSchema",
    "ExportRequest", "ImportRequest", "LinkReadSchema", "LinkWriteSchema", "MappingPreviewRequest", "PatchOperationSchema",
    "PatchRequest", "RelationsFindRequest", "ResolveRequest", "TopologyReadRequest",
    "StatePatchSchema", "StateReadSchema", "TopologyRefSchema", "TopologyStateSchema",
]
