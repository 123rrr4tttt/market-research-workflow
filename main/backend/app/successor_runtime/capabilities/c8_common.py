"""Family-local canonical common contracts for the C8 knowledge consumers.

P4 ahead-of-time family-local scaffold: this module is the single owner of
the canonical identity surface shared by the TypedKnowledge, Writing, Report
and Graph capability modules (digests, knowledge item, provenance, read
handles and registry).  It contains no capability implementation logic and is
the only capability-layer import allowed for those sibling modules.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

__all__ = [
    "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED",
    "C8_3_ADMISSION_INTERFACE_CONTRACT",
    "C8_3_ADMISSION_INTERFACE_DIGEST",
    "C8_3_DELIVERY_INTERFACE_CONTRACT",
    "C8_3_DELIVERY_INTERFACE_DIGEST",
    "C8_CAPABILITY_OWNER",
    "C8_MATERIAL_ISSUER_KIND",
    "KNOWLEDGE_ITEM_FIELDS",
    "KNOWLEDGE_ITEM_SCHEMA",
    "READ_HANDLE_SCHEMA",
    "AmbiguousProjection",
    "C8FailureResult",
    "C8ProjectionError",
    "C8RecoveryResult",
    "C8ResearchArtifactCandidate",
    "C8RollbackResult",
    "C8SuccessResult",
    "CanonicalMaterialRead",
    "CanonicalRef",
    "CitationClosure",
    "CitationRef",
    "FormationProfile",
    "GraphConsumerResult",
    "GraphLossProfile",
    "GraphOccurrence",
    "GraphProjectionGeneration",
    "HandleResolution",
    "IssuedKnowledgeRead",
    "KnowledgeItem",
    "KnowledgeRead",
    "KnowledgeReadHandle",
    "Provenance",
    "ProvenanceClosureEntry",
    "ReadHandle",
    "ReadHandleRegistry",
    "ReportAdmissionIntent",
    "ReportAdmissionReadback",
    "ReportDeliveryIntent",
    "ReportExportPreparation",
    "ReportStage",
    "ReportVerification",
    "ResearchDraftArtifact",
    "SourceClosureEntry",
    "TestOnlySealedValue",
    "TypedKnowledgeCandidate",
    "UnavailableProjection",
    "WritingCompositionSpec",
    "build_read_handle",
    "c8_canonical_digest",
    "candidate_fields_digest",
    "canonical_identity_for",
    "canonical_material_digest",
    "collapse_duplicate_citations",
    "deep_freeze_json",
    "derived_canonical_ref",
    "form_typed_knowledge_candidate",
    "item_digest",
    "material_attestation_digest",
    "recover_unknown_outcome",
    "research_draft_artifact_digest",
    "rollback_transition",
    "source_closure_entry",
    "validate_canonical_material",
    "validate_canonical_ref",
    "validate_citation_closure",
    "validate_typed_knowledge_candidate",
]

C8_CAPABILITY_OWNER = "knowledge-consumers.c8.v1"
AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED = "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
KNOWLEDGE_ITEM_SCHEMA = "mrw.successor.c8.typed-knowledge-item.v1"
READ_HANDLE_SCHEMA = "mrw.successor.c8.read-handle.v1"
C8_3_ADMISSION_INTERFACE_CONTRACT = "c8.report.admission.v1"
C8_3_DELIVERY_INTERFACE_CONTRACT = "c8.report.delivery.v1"
KNOWLEDGE_ITEM_FIELDS: tuple[str, ...] = (
    "key",
    "project_key",
    "canonical_statement",
    "primary_type_node_key",
    "evidence_refs",
    "topic_cluster_keys",
    "booklet_keys",
    "review_state",
    "quality_grade",
    "locale",
    "visibility_scope",
)


class C8ProjectionError(ValueError):
    """Raised when a C8 projection cannot resolve without inventing facts."""


class UnavailableProjection(C8ProjectionError):
    """Raised when demanded canonical facts are unavailable."""


class AmbiguousProjection(C8ProjectionError):
    """Raised when a read handle binds more than one canonical fact."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _to_plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            item.name: _to_plain(getattr(value, item.name))
            for item in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON requires string mapping keys")
            normalized[key] = _to_plain(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    if isinstance(value, (bool, str)) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("canonical JSON requires finite numbers")
        return value
    raise TypeError(f"unsupported canonical JSON value type: {type(value).__name__}")


def deep_freeze_json(value: Any) -> Any:
    """Recursively freeze canonical JSON into immutable nested values."""

    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON requires string mapping keys")
            frozen[key] = deep_freeze_json(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze_json(item) for item in value)
    if isinstance(value, (bool, str)) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("canonical JSON requires finite numbers")
        return value
    raise TypeError(f"unsupported canonical JSON value type: {type(value).__name__}")


def c8_canonical_digest(value: Any) -> str:
    """SHA-256 over a stable canonical JSON encoding of a captured value."""

    normalized = _to_plain(value)
    return hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()


C8_3_ADMISSION_INTERFACE_DIGEST = c8_canonical_digest(
    {
        "contract": C8_3_ADMISSION_INTERFACE_CONTRACT,
        "interface_only": True,
    }
)
C8_3_DELIVERY_INTERFACE_DIGEST = c8_canonical_digest(
    {
        "contract": C8_3_DELIVERY_INTERFACE_CONTRACT,
        "interface_only": True,
    }
)
C8_MATERIAL_ISSUER_KIND = "postgres_c7_head_value_port.v1"


class TestOnlySealedValue:
    """Nominal marker for values that production paths must reject."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class CanonicalRef:
    identity: str
    content_digest: str
    revision: int = 1
    incarnation: str = "knowledge-generation-1"


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    key: str
    project_key: str
    canonical_statement: str
    primary_type_node_key: str
    evidence_refs: tuple[str, ...]
    topic_cluster_keys: tuple[str, ...] = ()
    booklet_keys: tuple[str, ...] = ()
    review_state: str = "draft_candidate"
    quality_grade: str | None = None
    locale: str | None = None
    visibility_scope: str = "internal_only"
    canonical_ref: CanonicalRef | None = None


def item_digest(item: KnowledgeItem) -> str:
    """Digest over the knowledge item body without its self-referential ref."""

    return c8_canonical_digest(dataclasses.replace(item, canonical_ref=None))


def canonical_identity_for(item: KnowledgeItem) -> str:
    """Derived canonical identity from the item's project scope and key."""

    return f"knowledge:{item.project_key}:{item.key}"


def derived_canonical_ref(item: KnowledgeItem) -> CanonicalRef:
    """Canonical ref derived from the item body when none is stored."""

    return CanonicalRef(
        identity=canonical_identity_for(item),
        content_digest=item_digest(item),
        revision=1,
        incarnation="knowledge-generation-1",
    )


def validate_canonical_ref(
    item: KnowledgeItem,
    *,
    project_key: str | None = None,
) -> CanonicalRef:
    """Fail-closed validation of derived identity, body digest and scope."""

    ref = item.canonical_ref
    if ref is None:
        raise C8ProjectionError("canonical_ref missing; validation requires one")
    expected_identity = canonical_identity_for(item)
    if ref.identity != expected_identity:
        raise C8ProjectionError(
            f"canonical identity mismatch: {ref.identity} != {expected_identity}"
        )
    if project_key is not None and item.project_key != project_key:
        raise C8ProjectionError(
            f"canonical project scope mismatch: {item.project_key} != {project_key}"
        )
    body_digest = item_digest(item)
    if ref.content_digest != body_digest:
        raise C8ProjectionError("canonical body digest mismatch")
    if ref.revision < 1:
        raise C8ProjectionError("canonical revision must be >= 1")
    if not str(ref.incarnation or "").strip():
        raise C8ProjectionError("canonical incarnation is required")
    return ref


@dataclass(frozen=True, slots=True)
class Provenance:
    projection_name: str
    canonical_identity: str
    canonical_digest: str
    canonical_revision: int = 1
    canonical_incarnation: str = "knowledge-generation-1"
    source_label: str = "canonical"
    declared_loss: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReadHandle:
    handle_id: str
    domain: str
    object_key: str
    project_key: str | None
    field_mask: tuple[str, ...]
    canonical_identity: str
    canonical_digest: str
    canonical_revision: int
    canonical_incarnation: str
    source_label: str = "canonical"
    declared_loss: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HandleResolution:
    available: bool
    ambiguous: bool
    value: Any
    reason: str


@dataclass(frozen=True, slots=True)
class KnowledgeRead:
    item: KnowledgeItem
    fields: Mapping[str, Any]
    handle: ReadHandle
    provenance: Provenance


@dataclass(frozen=True, slots=True)
class SourceClosureEntry:
    identity: str
    digest: str
    revision: int
    incarnation: str
    handle_id: str


def source_closure_entry(
    *,
    identity: str,
    digest: str,
    revision: int,
    incarnation: str,
    handle_id: str,
) -> SourceClosureEntry:
    return SourceClosureEntry(
        identity=identity,
        digest=digest,
        revision=revision,
        incarnation=incarnation,
        handle_id=handle_id,
    )


@dataclass(frozen=True, slots=True)
class C8SuccessResult:
    cell_id: str
    result_digest: str
    outcome: str = "SUCCEEDED"
    provider_calls: int = 0
    store_writes: int = 0
    export_calls: int = 0


@dataclass(frozen=True, slots=True)
class C8FailureResult:
    cell_id: str
    failure_kind: str
    reason: str
    provider_calls: int = 0
    store_writes: int = 0
    export_calls: int = 0


@dataclass(frozen=True, slots=True)
class C8RecoveryResult:
    cell_id: str
    recovery_kind: str = "readback_only"
    readback_required: bool = True
    new_attempt_allowed: bool = False
    binding_digest: str = ""
    attempt_digest: str = ""
    readback_profile_ref: str = ""
    outcome_digest: str = ""
    provider_calls: int = 0
    store_writes: int = 0
    export_calls: int = 0


@dataclass(frozen=True, slots=True)
class C8RollbackResult:
    cell_id: str
    rollback_kind: str = "staged_values_retained"
    retained_digests: tuple[str, ...] = ()
    admission_reverted: bool = False
    provider_calls: int = 0
    store_writes: int = 0
    export_calls: int = 0


def recover_unknown_outcome(
    *,
    cell_id: str,
    binding_digest: str,
    attempt_digest: str,
    readback_profile_ref: str,
    outcome_digest: str,
) -> C8RecoveryResult:
    """Production typed recovery result for an unknown-outcome attempt."""

    return C8RecoveryResult(
        cell_id=cell_id,
        recovery_kind="readback_only",
        readback_required=True,
        new_attempt_allowed=False,
        binding_digest=binding_digest,
        attempt_digest=attempt_digest,
        readback_profile_ref=readback_profile_ref,
        outcome_digest=outcome_digest,
    )


def rollback_transition(
    *,
    cell_id: str,
    retained_digests: tuple[str, ...],
    admission_reverted: bool = False,
    authority_reversed: bool = False,
) -> C8RollbackResult:
    """Production typed rollback transition over retained staged values."""

    if not retained_digests:
        raise C8ProjectionError("rollback requires non-empty retained staged digests")
    if authority_reversed:
        raise C8ProjectionError("rollback must not reverse canonical authority")
    return C8RollbackResult(
        cell_id=cell_id,
        rollback_kind="staged_values_retained",
        retained_digests=tuple(retained_digests),
        admission_reverted=admission_reverted,
    )


@dataclass(frozen=True, slots=True)
class FormationProfile:
    profile_id: str
    profile_version: str


@dataclass(frozen=True, slots=True)
class CanonicalMaterialRead:
    material_identity: str
    project_key: str
    candidate_id: str
    document_identity: str
    head_revision: int
    head_incarnation: str
    head_closure_digest: str
    value_revision: int
    value_incarnation: str
    value_digest: str
    snapshot_ref: str
    provenance_digest: str
    structured_payload: Mapping[str, Any]
    issuer_id: str = C8_MATERIAL_ISSUER_KIND
    read_epoch: int = 1
    attestation_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "structured_payload",
            deep_freeze_json(self.structured_payload),
        )
        if self.issuer_id != C8_MATERIAL_ISSUER_KIND:
            raise C8ProjectionError("canonical material issuer kind mismatch")
        if self.value_digest != canonical_material_digest(self):
            raise C8ProjectionError("canonical material value digest mismatch")
        if self.value_revision < 1 or self.head_revision < 1:
            raise C8ProjectionError("canonical material revision must be >= 1")
        if (
            not str(self.value_incarnation or "").strip()
            or not str(self.head_incarnation or "").strip()
        ):
            raise C8ProjectionError("canonical material incarnation is required")
        expected_attestation = material_attestation_digest(self)
        if self.attestation_digest == "":
            object.__setattr__(self, "attestation_digest", expected_attestation)
        elif self.attestation_digest != expected_attestation:
            raise C8ProjectionError("canonical material attestation digest mismatch")


def canonical_material_digest(material: CanonicalMaterialRead) -> str:
    """Exact digest of the decoded structured payload bytes."""

    return c8_canonical_digest(material.structured_payload)


def material_attestation_digest(material: CanonicalMaterialRead) -> str:
    """Exact attestation over the issued head/value/scope fields."""

    return c8_canonical_digest(
        {
            "project_key": material.project_key,
            "material_identity": material.material_identity,
            "candidate_id": material.candidate_id,
            "document_identity": material.document_identity,
            "head_revision": material.head_revision,
            "head_incarnation": material.head_incarnation,
            "head_closure_digest": material.head_closure_digest,
            "value_revision": material.value_revision,
            "value_incarnation": material.value_incarnation,
            "value_digest": material.value_digest,
            "snapshot_ref": material.snapshot_ref,
            "provenance_digest": material.provenance_digest,
            "read_epoch": material.read_epoch,
        }
    )


def candidate_fields_digest(
    candidate: TypedKnowledgeCandidate,
    field_mask: tuple[str, ...],
) -> str:
    return c8_canonical_digest(
        {
            "candidate_id": candidate.candidate_id,
            "fields": [(name, getattr(candidate, name)) for name in sorted(field_mask)],
        }
    )


def validate_canonical_material(
    material: CanonicalMaterialRead,
    *,
    project_key: str | None = None,
) -> CanonicalMaterialRead:
    if project_key is not None and material.project_key != project_key:
        raise C8ProjectionError("canonical material project scope mismatch")
    if material.issuer_id != C8_MATERIAL_ISSUER_KIND:
        raise C8ProjectionError("canonical material issuer kind mismatch")
    if material.attestation_digest != material_attestation_digest(material):
        raise C8ProjectionError("canonical material attestation digest mismatch")
    if material.value_digest != canonical_material_digest(material):
        raise C8ProjectionError("canonical material value digest mismatch")
    return material


@dataclass(frozen=True, slots=True)
class TypedKnowledgeCandidate:
    candidate_id: str
    project_key: str
    material_identity: str
    material_value_digest: str
    formation_profile: FormationProfile
    canonical_statement: str
    primary_type_node_key: str
    evidence_refs: tuple[str, ...]
    topic_cluster_keys: tuple[str, ...] = ()
    booklet_keys: tuple[str, ...] = ()
    revision: int = 1
    incarnation: str = "knowledge-generation-1"
    candidate_digest: str = ""


def typed_knowledge_candidate_digest(
    candidate: TypedKnowledgeCandidate,
) -> str:
    body = {
        name: value
        for name, value in dataclasses.asdict(candidate).items()
        if name != "candidate_digest"
    }
    return c8_canonical_digest(body)


def form_typed_knowledge_candidate(
    material: CanonicalMaterialRead,
    *,
    formation_profile: FormationProfile,
    candidate_id: str,
    canonical_statement: str,
    primary_type_node_key: str,
    evidence_refs: tuple[str, ...],
) -> TypedKnowledgeCandidate:
    validate_canonical_material(material)
    if not canonical_statement.strip() or not primary_type_node_key.strip():
        raise C8ProjectionError("knowledge candidate requires statement and type")
    if not evidence_refs:
        raise C8ProjectionError("knowledge candidate requires evidence refs")
    candidate = TypedKnowledgeCandidate(
        candidate_id=candidate_id,
        project_key=material.project_key,
        material_identity=material.material_identity,
        material_value_digest=material.value_digest,
        formation_profile=formation_profile,
        canonical_statement=canonical_statement.strip(),
        primary_type_node_key=primary_type_node_key.strip(),
        evidence_refs=tuple(evidence_refs),
        revision=material.value_revision,
        incarnation=material.value_incarnation,
    )
    return dataclasses.replace(
        candidate,
        candidate_digest=typed_knowledge_candidate_digest(candidate),
    )


def validate_typed_knowledge_candidate(
    candidate: TypedKnowledgeCandidate,
    *,
    material: CanonicalMaterialRead | None = None,
    project_key: str | None = None,
) -> TypedKnowledgeCandidate:
    if project_key is not None and candidate.project_key != project_key:
        raise C8ProjectionError("knowledge candidate project scope mismatch")
    if candidate.candidate_digest != typed_knowledge_candidate_digest(candidate):
        raise C8ProjectionError("knowledge candidate digest mismatch")
    if material is not None:
        validate_canonical_material(material, project_key=candidate.project_key)
        if (
            candidate.material_identity != material.material_identity
            or candidate.material_value_digest != material.value_digest
            or candidate.revision != material.value_revision
            or candidate.incarnation != material.value_incarnation
        ):
            raise C8ProjectionError(
                "knowledge candidate is not closed under issued material"
            )
    return candidate


@dataclass(frozen=True, slots=True)
class KnowledgeReadHandle:
    handle_id: str
    domain: str
    object_key: str
    project_key: str
    field_mask: tuple[str, ...]
    canonical_identity: str
    canonical_digest: str
    revision: int
    incarnation: str
    head_revision: int
    head_incarnation: str
    head_closure_digest: str
    snapshot_ref: str
    read_epoch: int
    attestation_digest: str
    provenance_digest: str
    fields_digest: str
    authority_kind: str
    authority_digest: str
    issuer_registry_id: str
    issuer_registry_digest: str
    issuer_id: str = "c8.strict-read-handle-registry.v1"

    def __post_init__(self) -> None:
        expected = c8_canonical_digest(
            {
                "domain": self.domain,
                "object_key": self.object_key,
                "project_key": self.project_key,
                "field_mask": list(self.field_mask),
                "canonical_identity": self.canonical_identity,
                "canonical_digest": self.canonical_digest,
                "revision": self.revision,
                "incarnation": self.incarnation,
                "head_revision": self.head_revision,
                "head_incarnation": self.head_incarnation,
                "head_closure_digest": self.head_closure_digest,
                "snapshot_ref": self.snapshot_ref,
                "read_epoch": self.read_epoch,
                "attestation_digest": self.attestation_digest,
                "provenance_digest": self.provenance_digest,
                "fields_digest": self.fields_digest,
                "authority_kind": self.authority_kind,
                "authority_digest": self.authority_digest,
                "issuer_registry_id": self.issuer_registry_id,
                "issuer_registry_digest": self.issuer_registry_digest,
                "issuer_id": self.issuer_id,
            }
        )
        if self.handle_id != expected:
            raise C8ProjectionError("read handle digest mismatch (tamper detected)")


@dataclass(frozen=True, slots=True)
class IssuedKnowledgeRead:
    handle: KnowledgeReadHandle
    candidate: TypedKnowledgeCandidate
    fields: Mapping[str, Any]
    read_digest: str = ""
    witness_marker: object | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))
        expected = c8_canonical_digest(
            {
                "handle_id": self.handle.handle_id,
                "candidate_digest": self.candidate.candidate_digest,
                "fields": [(name, self.fields[name]) for name in sorted(self.fields)],
            }
        )
        if self.read_digest == "":
            object.__setattr__(self, "read_digest", expected)
        elif self.read_digest != expected:
            raise C8ProjectionError("issued read digest mismatch (tamper detected)")


@dataclass(frozen=True, slots=True)
class ProvenanceClosureEntry:
    identity: str
    digest: str
    revision: int
    incarnation: str
    handle_id: str
    fields_digest: str


@dataclass(frozen=True, slots=True)
class CitationRef:
    citation_id: str
    source_identity: str
    source_digest: str
    position: int
    source_revision: int = 1
    source_incarnation: str = ""
    handle_id: str = ""
    fields_digest: str = ""


@dataclass(frozen=True, slots=True)
class CitationClosure:
    refs: tuple[CitationRef, ...]


def validate_citation_closure(
    closure: CitationClosure,
    *,
    duplicate_policy: str = "reject",
    ceiling: int | None = None,
) -> CitationClosure:
    if ceiling is not None and len(closure.refs) > ceiling:
        raise C8ProjectionError("citation closure exceeds ceiling")
    for index, ref in enumerate(closure.refs, start=1):
        if ref.position != index:
            raise C8ProjectionError("citation order is not contiguous")
    seen: dict[str, tuple[str, str]] = {}
    for ref in closure.refs:
        bound = (
            ref.source_identity,
            ref.source_digest,
            ref.source_revision,
            ref.source_incarnation,
            ref.handle_id,
            ref.fields_digest,
        )
        prior = seen.get(ref.citation_id)
        if prior is not None:
            if prior != bound:
                raise C8ProjectionError(
                    f"conflicting citation identity: {ref.citation_id}"
                )
            if duplicate_policy == "reject":
                raise C8ProjectionError(
                    f"duplicate citation rejected: {ref.citation_id}"
                )
            raise C8ProjectionError(
                "duplicate citation policy must be reject or collapse"
            )
        seen[ref.citation_id] = bound
    return closure


def collapse_duplicate_citations(
    closure: CitationClosure,
) -> tuple[CitationClosure, tuple[str, ...]]:
    seen: set[str] = set()
    kept: list[CitationRef] = []
    dropped: list[str] = []
    for index, ref in enumerate(closure.refs, start=1):
        if ref.citation_id in seen:
            dropped.append(ref.citation_id)
            continue
        seen.add(ref.citation_id)
        kept.append(
            CitationRef(
                citation_id=ref.citation_id,
                source_identity=ref.source_identity,
                source_digest=ref.source_digest,
                position=len(kept) + 1,
                source_revision=ref.source_revision,
                source_incarnation=ref.source_incarnation,
                handle_id=ref.handle_id,
                fields_digest=ref.fields_digest,
            )
        )
    return CitationClosure(tuple(kept)), tuple(dropped)


@dataclass(frozen=True, slots=True)
class WritingCompositionSpec:
    project_key: str
    base_revision: int
    base_incarnation: str
    byte_ceiling: int
    citation_ceiling: int
    duplicate_policy: str = "reject"


@dataclass(frozen=True, slots=True)
class ResearchDraftArtifact:
    artifact_id: str
    project_key: str
    markdown_bytes: bytes
    base_revision: int
    base_incarnation: str
    provenance_closure: tuple[ProvenanceClosureEntry, ...]
    citation_closure: CitationClosure
    declared_legacy_metadata_loss: tuple[str, ...]
    artifact_digest: str = ""


@dataclass(frozen=True, slots=True)
class C8ResearchArtifactCandidate:
    candidate_id: str
    project_key: str
    canonical_metadata_bytes: bytes
    canonical_metadata_digest: str
    markdown_ref: str
    markdown_digest: str
    source_draft_digest: str
    verification_digest: str
    provenance_digest: str
    claim_closure: tuple[str, ...]
    evidence_relation_closure: tuple[str, ...]
    citation_closure: tuple[str, ...]
    source_base_revision: int
    source_base_incarnation: str
    canonical_revision: int = 1
    canonical_incarnation: str = "research-artifact-1"
    lifecycle_state: str = "DRAFT"
    payload_digest: str = ""
    object_digest: str = ""

    def __post_init__(self) -> None:
        body = {
            name: value
            for name, value in dataclasses.asdict(self).items()
            if name not in ("payload_digest", "object_digest")
        }
        body["canonical_metadata_bytes"] = body["canonical_metadata_bytes"].decode(
            "utf-8"
        )
        expected_payload = c8_canonical_digest(body)
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected_payload)
        elif self.payload_digest != expected_payload:
            raise C8ProjectionError(
                "research artifact candidate payload digest mismatch"
            )
        object_body = {
            name: value
            for name, value in dataclasses.asdict(self).items()
            if name != "object_digest"
        }
        object_body["canonical_metadata_bytes"] = object_body[
            "canonical_metadata_bytes"
        ].decode("utf-8")
        expected_object = c8_canonical_digest(object_body)
        if self.object_digest == "":
            object.__setattr__(self, "object_digest", expected_object)
        elif self.object_digest != expected_object:
            raise C8ProjectionError(
                "research artifact candidate object digest mismatch"
            )


def research_draft_artifact_digest(artifact: ResearchDraftArtifact) -> str:
    body = {
        "artifact_id": artifact.artifact_id,
        "project_key": artifact.project_key,
        "markdown_bytes": artifact.markdown_bytes.decode("utf-8"),
        "base_revision": artifact.base_revision,
        "base_incarnation": artifact.base_incarnation,
        "provenance_closure": [
            {
                "identity": entry.identity,
                "digest": entry.digest,
                "revision": entry.revision,
                "incarnation": entry.incarnation,
                "handle_id": entry.handle_id,
                "fields_digest": entry.fields_digest,
            }
            for entry in artifact.provenance_closure
        ],
        "citation_closure": [
            {
                "citation_id": ref.citation_id,
                "source_identity": ref.source_identity,
                "source_digest": ref.source_digest,
                "position": ref.position,
            }
            for ref in artifact.citation_closure.refs
        ],
        "declared_legacy_metadata_loss": list(artifact.declared_legacy_metadata_loss),
    }
    return c8_canonical_digest(body)


@dataclass(frozen=True, slots=True)
class ReportStage:
    stage_id: str
    project_key: str
    artifact_id: str
    artifact_digest: str
    source_identities: tuple[str, ...]
    citation_closure: CitationClosure
    provenance_closure: tuple[ProvenanceClosureEntry, ...] = ()
    authority: str = "stage_no_admission"
    object_digest: str = ""

    def __post_init__(self) -> None:
        expected = c8_canonical_digest(
            {
                "stage_id": self.stage_id,
                "project_key": self.project_key,
                "artifact_id": self.artifact_id,
                "artifact_digest": self.artifact_digest,
                "source_identities": list(self.source_identities),
                "citation_ids": [ref.citation_id for ref in self.citation_closure.refs],
                "citations": [
                    {
                        "citation_id": ref.citation_id,
                        "source_identity": ref.source_identity,
                        "source_digest": ref.source_digest,
                        "position": ref.position,
                        "source_revision": ref.source_revision,
                        "source_incarnation": ref.source_incarnation,
                        "handle_id": ref.handle_id,
                        "fields_digest": ref.fields_digest,
                    }
                    for ref in self.citation_closure.refs
                ],
                "provenance_closure": [
                    {
                        "identity": entry.identity,
                        "digest": entry.digest,
                        "revision": entry.revision,
                        "incarnation": entry.incarnation,
                        "handle_id": entry.handle_id,
                        "fields_digest": entry.fields_digest,
                    }
                    for entry in self.provenance_closure
                ],
                "authority": self.authority,
            }
        )
        if self.object_digest == "":
            object.__setattr__(self, "object_digest", expected)
        elif self.object_digest != expected:
            raise C8ProjectionError("report stage digest mismatch (tamper detected)")


@dataclass(frozen=True, slots=True)
class ReportVerification:
    verification_id: str
    stage_id: str
    project_key: str
    artifact_digest: str
    citation_closure_digest: str
    state: str = "UNVERIFIED"
    failure_reason: str | None = None
    authority_kind: str = ""
    authority_digest: str = ""
    verifier_registry_id: str = ""
    verifier_registry_digest: str = ""
    object_digest: str = ""

    def __post_init__(self) -> None:
        expected = c8_canonical_digest(
            {
                "verification_id": self.verification_id,
                "stage_id": self.stage_id,
                "project_key": self.project_key,
                "artifact_digest": self.artifact_digest,
                "citation_closure_digest": self.citation_closure_digest,
                "state": self.state,
                "failure_reason": self.failure_reason,
                "authority_kind": self.authority_kind,
                "authority_digest": self.authority_digest,
                "verifier_registry_id": self.verifier_registry_id,
                "verifier_registry_digest": self.verifier_registry_digest,
            }
        )
        if self.object_digest == "":
            object.__setattr__(self, "object_digest", expected)
        elif self.object_digest != expected:
            raise C8ProjectionError(
                "report verification digest mismatch (tamper detected)"
            )


@dataclass(frozen=True, slots=True)
class ReportAdmissionIntent:
    intent_id: str
    verification_id: str
    project_key: str
    artifact_digest: str
    state: str = "PENDING"
    authority: str = "admission_intent_only"
    object_digest: str = ""

    def __post_init__(self) -> None:
        expected = c8_canonical_digest(
            {
                "intent_id": self.intent_id,
                "verification_id": self.verification_id,
                "project_key": self.project_key,
                "artifact_digest": self.artifact_digest,
                "state": self.state,
                "authority": self.authority,
            }
        )
        if self.object_digest == "":
            object.__setattr__(self, "object_digest", expected)
        elif self.object_digest != expected:
            raise C8ProjectionError(
                "report admission intent digest mismatch (tamper detected)"
            )


@dataclass(frozen=True, slots=True)
class ReportAdmissionReadback:
    readback_id: str
    intent_id: str
    project_key: str
    artifact_digest: str
    state: str = "UNADMITTED"
    authority_epoch: int = 1
    verification_id: str = ""
    authority_kind: str = ""
    authority_digest: str = ""
    verifier_registry_id: str = ""
    verifier_registry_digest: str = ""
    object_digest: str = ""

    def __post_init__(self) -> None:
        expected = c8_canonical_digest(
            {
                "readback_id": self.readback_id,
                "intent_id": self.intent_id,
                "project_key": self.project_key,
                "artifact_digest": self.artifact_digest,
                "state": self.state,
                "authority_epoch": self.authority_epoch,
                "verification_id": self.verification_id,
                "authority_kind": self.authority_kind,
                "authority_digest": self.authority_digest,
                "verifier_registry_id": self.verifier_registry_id,
                "verifier_registry_digest": self.verifier_registry_digest,
            }
        )
        if self.object_digest == "":
            object.__setattr__(self, "object_digest", expected)
        elif self.object_digest != expected:
            raise C8ProjectionError(
                "report admission readback digest mismatch (tamper detected)"
            )


@dataclass(frozen=True, slots=True)
class ReportExportPreparation:
    preparation_id: str
    project_key: str
    artifact_digest: str
    export_format: str
    state: str = "NOT_PREPARED"
    internal_only: bool = True
    object_digest: str = ""

    def __post_init__(self) -> None:
        expected = c8_canonical_digest(
            {
                "preparation_id": self.preparation_id,
                "project_key": self.project_key,
                "artifact_digest": self.artifact_digest,
                "export_format": self.export_format,
                "state": self.state,
                "internal_only": self.internal_only,
            }
        )
        if self.object_digest == "":
            object.__setattr__(self, "object_digest", expected)
        elif self.object_digest != expected:
            raise C8ProjectionError(
                "report export preparation digest mismatch (tamper detected)"
            )


@dataclass(frozen=True, slots=True)
class ReportDeliveryIntent:
    intent_id: str
    project_key: str
    preparation_id: str
    artifact_digest: str
    external_delivery: bool = False
    state: str = "PENDING"
    approval_digest: str = ""
    approval_epoch: int = 0
    object_digest: str = ""

    def __post_init__(self) -> None:
        expected = c8_canonical_digest(
            {
                "intent_id": self.intent_id,
                "project_key": self.project_key,
                "preparation_id": self.preparation_id,
                "artifact_digest": self.artifact_digest,
                "external_delivery": self.external_delivery,
                "state": self.state,
                "approval_digest": self.approval_digest,
                "approval_epoch": self.approval_epoch,
            }
        )
        if self.object_digest == "":
            object.__setattr__(self, "object_digest", expected)
        elif self.object_digest != expected:
            raise C8ProjectionError(
                "report delivery intent digest mismatch (tamper detected)"
            )


@dataclass(frozen=True, slots=True)
class GraphOccurrence:
    occurrence_id: str
    edge_type: str
    source_identity: str
    target_identity: str
    position: int
    occurrence_digest: str = ""


def graph_occurrence_digest(occurrence: GraphOccurrence) -> str:
    body = {
        "occurrence_id": occurrence.occurrence_id,
        "edge_type": occurrence.edge_type,
        "source_identity": occurrence.source_identity,
        "target_identity": occurrence.target_identity,
        "position": occurrence.position,
    }
    return c8_canonical_digest(body)


@dataclass(frozen=True, slots=True)
class GraphLossProfile:
    profile_id: str
    filter: tuple[str, ...] = ()
    truncation: tuple[str, ...] = ()
    redaction: tuple[str, ...] = ()
    casefold: bool = False
    duplicate_collapse: bool = False
    omitted_fields: tuple[str, ...] = ()
    profile_digest: str = ""

    def __post_init__(self) -> None:
        expected = c8_canonical_digest(
            {
                "profile_id": self.profile_id,
                "filter": list(self.filter),
                "truncation": list(self.truncation),
                "redaction": list(self.redaction),
                "casefold": self.casefold,
                "duplicate_collapse": self.duplicate_collapse,
                "omitted_fields": list(self.omitted_fields),
            }
        )
        if self.profile_digest == "":
            object.__setattr__(self, "profile_digest", expected)
        elif self.profile_digest != expected:
            raise C8ProjectionError("graph loss profile digest mismatch")


def graph_projection_generation_digest(
    generation: GraphProjectionGeneration,
) -> str:
    return c8_canonical_digest(
        {
            "generation_id": generation.generation_id,
            "project_key": generation.project_key,
            "occurrences": [
                {
                    "occurrence_id": occurrence.occurrence_id,
                    "edge_type": occurrence.edge_type,
                    "source_identity": occurrence.source_identity,
                    "target_identity": occurrence.target_identity,
                    "position": occurrence.position,
                    "occurrence_digest": occurrence.occurrence_digest,
                }
                for occurrence in generation.occurrences
            ],
            "declared_loss": list(generation.declared_loss),
            "provenance_digest": generation.provenance_digest,
            "offset": generation.offset,
            "authority_kind": generation.authority_kind,
            "authority_digest": generation.authority_digest,
            "loss_profile_registry_id": generation.loss_profile_registry_id,
            "loss_profile_registry_digest": generation.loss_profile_registry_digest,
        }
    )


@dataclass(frozen=True, slots=True)
class GraphProjectionGeneration:
    generation_id: str
    project_key: str
    occurrences: tuple[GraphOccurrence, ...]
    declared_loss: tuple[str, ...]
    provenance_digest: str
    offset: str = "0"
    authority_kind: str = ""
    authority_digest: str = ""
    loss_profile_registry_id: str = ""
    loss_profile_registry_digest: str = ""
    projection_digest: str = ""

    def __post_init__(self) -> None:
        for occurrence in self.occurrences:
            if occurrence.occurrence_digest != graph_occurrence_digest(occurrence):
                raise C8ProjectionError("graph occurrence digest mismatch")
        expected = graph_projection_generation_digest(self)
        if self.projection_digest == "":
            object.__setattr__(self, "projection_digest", expected)
        elif self.projection_digest != expected:
            raise C8ProjectionError(
                "graph projection digest mismatch (tamper detected)"
            )


@dataclass(frozen=True, slots=True)
class GraphConsumerResult:
    consumer_id: str
    generation_id: str
    project_key: str
    items: tuple[Mapping[str, Any], ...] = ()
    declared_loss: tuple[str, ...] = ()
    state: str = "UNAVAILABLE"
    provider_calls: int = 0
    store_writes: int = 0
    export_calls: int = 0


def build_read_handle(
    *,
    domain: str,
    object_key: str,
    project_key: str | None,
    canonical_ref: CanonicalRef,
    field_mask: tuple[str, ...],
    declared_loss: tuple[str, ...] = (),
    source_label: str = "canonical",
) -> ReadHandle:
    normalized_fields = tuple(sorted(set(field_mask)))
    payload = {
        "domain": domain,
        "object_key": object_key,
        "project_key": project_key,
        "canonical_identity": canonical_ref.identity,
        "canonical_digest": canonical_ref.content_digest,
        "canonical_revision": canonical_ref.revision,
        "canonical_incarnation": canonical_ref.incarnation,
        "field_mask": normalized_fields,
        "source_label": source_label,
    }
    handle_id = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return ReadHandle(
        handle_id=handle_id,
        domain=domain,
        object_key=object_key,
        project_key=project_key,
        field_mask=normalized_fields,
        canonical_identity=canonical_ref.identity,
        canonical_digest=canonical_ref.content_digest,
        canonical_revision=canonical_ref.revision,
        canonical_incarnation=canonical_ref.incarnation,
        source_label=source_label,
        declared_loss=tuple(declared_loss),
    )


class ReadHandleRegistry:
    """Maps read handles to bounded field slices; never manufactures facts."""

    def __init__(self) -> None:
        self._handles: dict[str, ReadHandle] = {}

    def register(self, handle: ReadHandle) -> ReadHandle:
        self._handles[handle.handle_id] = handle
        return handle

    def resolve(
        self,
        handle: ReadHandle,
        *,
        items: tuple[KnowledgeItem, ...],
    ) -> HandleResolution:
        candidates = [item for item in items if item.key == handle.object_key]
        if handle.project_key is not None:
            candidates = [
                item for item in candidates if item.project_key == handle.project_key
            ]
        if not candidates:
            return HandleResolution(
                available=False,
                ambiguous=False,
                value=None,
                reason="typed knowledge fact unavailable for read handle",
            )
        if len(candidates) > 1:
            return HandleResolution(
                available=False,
                ambiguous=True,
                value=[item.key for item in candidates],
                reason="read handle binds multiple typed knowledge facts",
            )
        item = candidates[0]
        if item.canonical_ref is not None:
            validate_canonical_ref(item, project_key=handle.project_key)
            ref = item.canonical_ref
        else:
            ref = derived_canonical_ref(item)
            if (
                handle.project_key is not None
                and item.project_key != handle.project_key
            ):
                return HandleResolution(
                    available=False,
                    ambiguous=False,
                    value=None,
                    reason="canonical project scope mismatch",
                )
        if (
            handle.canonical_identity != ref.identity
            or handle.canonical_digest != ref.content_digest
            or handle.canonical_revision != ref.revision
            or handle.canonical_incarnation != ref.incarnation
        ):
            return HandleResolution(
                available=False,
                ambiguous=False,
                value=None,
                reason=(
                    "canonical content, revision or incarnation changed since "
                    "handle issuance"
                ),
            )
        selected: dict[str, Any] = {}
        for name in handle.field_mask:
            if not hasattr(item, name):
                return HandleResolution(
                    available=False,
                    ambiguous=False,
                    value=None,
                    reason=f"demanded field unavailable: {name}",
                )
            selected[name] = getattr(item, name)
        return HandleResolution(
            available=True,
            ambiguous=False,
            value=selected,
            reason="ok",
        )
