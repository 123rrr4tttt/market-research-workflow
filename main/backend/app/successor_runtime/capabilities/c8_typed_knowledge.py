"""Typed demand-read contracts for the C8 knowledge consumers.

P4 ahead-of-time family-local scaffold: this module owns the demand-read
operation and re-exports the family-local canonical contracts owned by
``c8_common``.  Production paths reject every nominal ``TestOnly*`` witness by
type; test-only entrypoints are explicitly named.
"""

from __future__ import annotations

import dataclasses
from types import MappingProxyType

from app.successor_runtime.capabilities.c8_common import (
    C8_CAPABILITY_OWNER,
    KNOWLEDGE_ITEM_SCHEMA,
    READ_HANDLE_SCHEMA,
    AmbiguousProjection,
    C8ProjectionError,
    CanonicalMaterialRead,
    CanonicalRef,
    HandleResolution,
    IssuedKnowledgeRead,
    KnowledgeItem,
    KnowledgeRead,
    KnowledgeReadHandle,
    Provenance,
    ReadHandle,
    ReadHandleRegistry,
    TestOnlySealedValue,
    TypedKnowledgeCandidate,
    UnavailableProjection,
    build_read_handle,
    c8_canonical_digest,
    candidate_fields_digest,
    canonical_identity_for,
    derived_canonical_ref,
    item_digest,
    validate_canonical_material,
    validate_canonical_ref,
    validate_typed_knowledge_candidate,
)

__all__ = [
    "C8_CAPABILITY_OWNER",
    "DEMAND_READ_OPERATION_KIND",
    "KNOWLEDGE_ITEM_SCHEMA",
    "READ_HANDLE_SCHEMA",
    "AmbiguousProjection",
    "C8ProjectionError",
    "CanonicalRef",
    "HandleResolution",
    "IssuedKnowledgeRead",
    "KnowledgeItem",
    "KnowledgeRead",
    "KnowledgeReadHandle",
    "Provenance",
    "ReadHandle",
    "ReadHandleRegistry",
    "StrictReadHandleRegistry",
    "TypedKnowledgeCandidate",
    "UnavailableProjection",
    "build_read_handle",
    "c8_canonical_digest",
    "canonical_identity_for",
    "demand_read",
    "item_digest",
    "strict_issued_demand_read",
    "strict_issued_demand_read_test_only",
    "validate_canonical_ref",
]

DEMAND_READ_OPERATION_KIND = "c8.demand_read.v1"

TYPED_KNOWLEDGE_DOMAIN = "typed_knowledge"
PROJECTION_DEMAND_READ = "demand_read.typed_knowledge"


def demand_read(
    items: tuple[KnowledgeItem, ...],
    *,
    item_key: str,
    fields: tuple[str, ...],
    project_key: str | None = None,
    registry: ReadHandleRegistry | None = None,
) -> KnowledgeRead:
    candidates = [item for item in items if item.key == item_key]
    if project_key is not None:
        candidates = [item for item in candidates if item.project_key == project_key]
    if not candidates:
        raise UnavailableProjection(f"typed knowledge item {item_key} is unavailable")
    if len(candidates) > 1:
        raise AmbiguousProjection(f"typed knowledge item {item_key} is ambiguous")
    item = candidates[0]
    ref = item.canonical_ref or derived_canonical_ref(item)
    handle = build_read_handle(
        domain=TYPED_KNOWLEDGE_DOMAIN,
        object_key=item.key,
        project_key=item.project_key,
        canonical_ref=ref,
        field_mask=tuple(fields),
    )
    active_registry = registry or ReadHandleRegistry()
    active_registry.register(handle)
    resolution = active_registry.resolve(handle, items=items)
    if not resolution.available:
        if resolution.ambiguous:
            raise AmbiguousProjection(resolution.reason)
        raise UnavailableProjection(resolution.reason)
    return KnowledgeRead(
        item=item,
        fields=dict(resolution.value),
        handle=handle,
        provenance=Provenance(
            projection_name=PROJECTION_DEMAND_READ,
            canonical_identity=ref.identity,
            canonical_digest=ref.content_digest,
            canonical_revision=ref.revision,
            canonical_incarnation=ref.incarnation,
        ),
    )


class StrictReadHandleRegistry:
    """Source-issued read handles; resolution never derives a ref.

    The ``issuance`` argument is an opaque test-only or future production
    issuance registry.  Production entrypoints reject ``TestOnly*`` witnesses
    by nominal type before dispatch.
    """

    def __init__(self, issuance: object) -> None:
        self._issuance = issuance
        self._handles: dict[str, KnowledgeReadHandle] = {}

    def issue(
        self,
        *,
        material: CanonicalMaterialRead,
        witness: object,
        candidate: TypedKnowledgeCandidate,
        domain: str,
        object_key: str,
        fields: tuple[str, ...],
    ) -> KnowledgeReadHandle:
        registered = self._issuance.resolve(material.material_identity)
        if registered is None or registered != material:
            raise UnavailableProjection(
                "material is not an issued exact registry entry"
            )
        if witness._secret is not self._issuance._authority._secret:
            raise UnavailableProjection("material issuance witness is not authentic")
        if (
            witness.material_identity != material.material_identity
            or witness.attestation_digest != material.attestation_digest
        ):
            raise UnavailableProjection("material issuance witness mismatch")
        validate_typed_knowledge_candidate(
            candidate,
            material=material,
            project_key=candidate.project_key,
        )
        normalized_fields = tuple(sorted(set(fields)))
        fields_digest = candidate_fields_digest(candidate, normalized_fields)
        payload = {
            "domain": domain,
            "object_key": object_key,
            "project_key": candidate.project_key,
            "field_mask": normalized_fields,
            "canonical_identity": material.material_identity,
            "canonical_digest": material.value_digest,
            "revision": material.value_revision,
            "incarnation": material.value_incarnation,
            "head_revision": material.head_revision,
            "head_incarnation": material.head_incarnation,
            "head_closure_digest": material.head_closure_digest,
            "snapshot_ref": material.snapshot_ref,
            "read_epoch": material.read_epoch,
            "attestation_digest": material.attestation_digest,
            "provenance_digest": material.provenance_digest,
            "fields_digest": fields_digest,
            "authority_kind": self._issuance.authority_id,
            "authority_digest": self._issuance.authority_digest,
            "issuer_registry_id": self._issuance.registry_id,
            "issuer_registry_digest": self._issuance.registry_digest,
            "issuer_id": "c8.strict-read-handle-registry.v1",
        }
        handle = KnowledgeReadHandle(
            handle_id=c8_canonical_digest(payload),
            domain=domain,
            object_key=object_key,
            project_key=candidate.project_key,
            field_mask=normalized_fields,
            canonical_identity=material.material_identity,
            canonical_digest=material.value_digest,
            revision=material.value_revision,
            incarnation=material.value_incarnation,
            head_revision=material.head_revision,
            head_incarnation=material.head_incarnation,
            head_closure_digest=material.head_closure_digest,
            snapshot_ref=material.snapshot_ref,
            read_epoch=material.read_epoch,
            attestation_digest=material.attestation_digest,
            provenance_digest=material.provenance_digest,
            fields_digest=fields_digest,
            authority_kind=self._issuance.authority_id,
            authority_digest=self._issuance.authority_digest,
            issuer_registry_id=self._issuance.registry_id,
            issuer_registry_digest=self._issuance.registry_digest,
        )
        self._handles[handle.handle_id] = handle
        return handle

    def resolve(
        self,
        handle: KnowledgeReadHandle,
        *,
        material: CanonicalMaterialRead,
        candidate: TypedKnowledgeCandidate,
    ) -> IssuedKnowledgeRead:
        issued = self._handles.get(handle.handle_id)
        if issued is None:
            raise UnavailableProjection("forged read handle was never issued")
        if issued != handle:
            raise UnavailableProjection(
                "read handle does not match the issued entry byte-for-byte"
            )
        registered = self._issuance.resolve(handle.canonical_identity)
        if registered is None or registered != material:
            raise UnavailableProjection(
                "material drifted from the registered issuance entry"
            )
        validate_canonical_material(material, project_key=handle.project_key)
        validate_typed_knowledge_candidate(
            candidate,
            material=material,
            project_key=handle.project_key,
        )
        if handle.fields_digest != candidate_fields_digest(
            candidate, handle.field_mask
        ):
            raise UnavailableProjection("issued handle fields digest is stale")
        selected: dict[str, object] = {}
        for name in handle.field_mask:
            if not hasattr(candidate, name):
                raise UnavailableProjection(f"demanded field unavailable: {name}")
            selected[name] = getattr(candidate, name)
        return IssuedKnowledgeRead(
            handle=handle,
            candidate=candidate,
            fields=MappingProxyType(selected),
        )


def strict_issued_demand_read(
    material: CanonicalMaterialRead,
    witness: object,
    candidate: TypedKnowledgeCandidate,
    registry: StrictReadHandleRegistry,
    *,
    fields: tuple[str, ...],
    domain: str = TYPED_KNOWLEDGE_DOMAIN,
    object_key: str | None = None,
) -> IssuedKnowledgeRead:
    if isinstance(witness, TestOnlySealedValue):
        raise UnavailableProjection("production demand-read rejects TEST_ONLY witness")
    return strict_issued_demand_read_test_only(
        material,
        witness,
        candidate,
        registry,
        fields=fields,
        domain=domain,
        object_key=object_key,
    )


def strict_issued_demand_read_test_only(
    material: CanonicalMaterialRead,
    witness: object,
    candidate: TypedKnowledgeCandidate,
    registry: StrictReadHandleRegistry,
    *,
    fields: tuple[str, ...],
    domain: str = TYPED_KNOWLEDGE_DOMAIN,
    object_key: str | None = None,
) -> IssuedKnowledgeRead:
    handle = registry.issue(
        material=material,
        witness=witness,
        candidate=candidate,
        domain=domain,
        object_key=object_key or candidate.candidate_id,
        fields=fields,
    )
    read = registry.resolve(handle, material=material, candidate=candidate)
    return dataclasses.replace(read, witness_marker=witness)
