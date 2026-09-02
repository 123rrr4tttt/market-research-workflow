"""Typed, content-addressed payload closure for the P0-C first specimen.

The shared Program AST only carries ``ValueRef`` objects.  This capability-owned
module constructs each submission-static DTO, round-trips it through that
operation's frozen codec, and persists its encoded bytes in the project value
store during the submission unit of work.  The delivery payload is dynamic:
its artifact ref does not exist until artifact admission.
"""

from __future__ import annotations

import hashlib
from dataclasses import MISSING, dataclass
from dataclasses import fields as dataclass_fields
from datetime import datetime
from typing import Any, Protocol

from app.successor_runtime.capabilities import (
    CanonicalReadInput,
    CaptureDocumentSnapshotInput,
    ClaimOrGapInput,
    EvidenceQualificationInput,
    InternalExportInput,
    MarkdownComposeInput,
    build_first_specimen_bundle,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.research.artifacts import DeliveryIntent
from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.research.object_types import ObjectType

from .checksum import content_digest
from .codecs import PayloadCodec

_OPERATION_KINDS = {
    "material.capture.source.a": "material.capture_document_snapshot.v1",
    "material.read.source.a": "material.read_canonical_ref.v1",
    "evidence.qualify.source.a": "evidence.qualify.v1",
    "material.capture.source.b": "material.capture_document_snapshot.v1",
    "material.read.source.b": "material.read_canonical_ref.v1",
    "evidence.qualify.source.b": "evidence.qualify.v1",
    "claim.form_or_open_gap": "claim.form_or_open_gap.v1",
    "artifact.compose_markdown": "artifact.compose_markdown.v1",
}


class TypedPayloadValuePort(Protocol):
    def put_exact(
        self,
        scope: object,
        *,
        value_id: str,
        object_type: str,
        codec_id: str,
        content: bytes,
        expected_digest: str,
        provenance_digest: str,
        expected_revision: int,
        expected_incarnation: str,
        source_ref: str | None = None,
        provenance: dict[str, object] | None = None,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class SourcePayloadContext:
    label: str
    source_ref: str
    document_id: int
    locator: str
    owner_id: str
    observed_at: datetime
    captured_content_digest: str
    captured_updated_at: datetime
    captured_byte_size: int
    material_ref: str

    def __post_init__(self) -> None:
        if self.label not in {"a", "b"}:
            raise ValueError("first-specimen source label must be a or b")
        if self.document_id <= 0 or self.captured_byte_size <= 0:
            raise ValueError("captured Document identity and size must be positive")
        if self.observed_at.tzinfo is None or self.captured_updated_at.tzinfo is None:
            raise ValueError("source and capture timestamps must be timezone-aware")
        if len(self.captured_content_digest) != 64:
            raise ValueError("captured content digest must be sha256 hex")


@dataclass(frozen=True, slots=True)
class FirstSpecimenPayloadContext:
    submission_id: str
    run_id: str
    project_key: str
    inquiry_ref: str
    sources: tuple[SourcePayloadContext, SourcePayloadContext]

    def __post_init__(self) -> None:
        required = (
            self.submission_id,
            self.run_id,
            self.project_key,
            self.inquiry_ref,
        )
        if any(not value for value in required):
            raise ValueError("typed payload context identities must be non-empty")
        if tuple(source.label for source in self.sources) != ("a", "b"):
            raise ValueError("typed payload sources must use ordered labels a then b")


@dataclass(frozen=True, slots=True)
class PersistedOperationPayloads:
    operations: tuple[tuple[str, ValueRef], ...]

    def __post_init__(self) -> None:
        if tuple(operation_id for operation_id, _ in self.operations) != tuple(
            _OPERATION_KINDS
        ):
            raise ValueError("typed payload closure must cover the eight static Atoms")

    def for_operation(self, operation_id: str) -> ValueRef:
        for candidate, value_ref in self.operations:
            if candidate == operation_id:
                return value_ref
        raise KeyError(operation_id)


@dataclass(frozen=True, slots=True)
class _PayloadSpec:
    operation_id: str
    source_label: str | None
    source_ref: str | None
    payload: Any


def _payload(dto_cls: type, **fields: Any) -> Any:
    complete = dict(fields)
    for field_def in dataclass_fields(dto_cls):
        if field_def.name in complete or field_def.name == "payload_digest":
            continue
        if field_def.default is not MISSING:
            complete[field_def.name] = field_def.default
        elif field_def.default_factory is not MISSING:
            complete[field_def.name] = field_def.default_factory()
    digest = content_digest(complete)
    return dto_cls(**complete, payload_digest=digest)


def _payload_specs(context: FirstSpecimenPayloadContext) -> tuple[_PayloadSpec, ...]:
    source_a, source_b = context.sources
    qualifications = {
        source.label: f"qualification:{context.run_id}:source:{source.label}"
        for source in context.sources
    }
    claim_ref = f"claim-or-gap:{context.run_id}"
    artifact_ref = f"artifact:{context.run_id}"

    source_specs: dict[str, tuple[_PayloadSpec, _PayloadSpec, _PayloadSpec]] = {}
    for source in context.sources:
        capture = _payload(
            CaptureDocumentSnapshotInput,
            source_ref=source.source_ref,
            document_id=source.document_id,
            content_sha256_hex=source.captured_content_digest,
            observed_updated_at=source.captured_updated_at.isoformat(),
            byte_size=source.captured_byte_size,
        )
        read = _payload(
            CanonicalReadInput,
            source_ref=source.source_ref,
            locator=source.locator,
            owner_id=source.owner_id,
            observed_at=source.observed_at.isoformat(),
        )
        qualify = _payload(
            EvidenceQualificationInput,
            qualification_id=qualifications[source.label],
            material_ref=source.material_ref,
            inquiry_ref=context.inquiry_ref,
            direction="SUPPORTS" if source.label == "a" else "CONTRADICTS",
            scope_statement_ref=(
                f"scope-statement:{context.run_id}:source:{source.label}"
            ),
            uncertainty_profile_ref="uncertainty:first-specimen:explicit",
            verifier_profile_ref="verifier:first-specimen:deterministic",
        )
        source_specs[source.label] = (
            _PayloadSpec(
                f"material.capture.source.{source.label}",
                source.label,
                source.source_ref,
                capture,
            ),
            _PayloadSpec(
                f"material.read.source.{source.label}",
                source.label,
                source.source_ref,
                read,
            ),
            _PayloadSpec(
                f"evidence.qualify.source.{source.label}",
                source.label,
                source.source_ref,
                qualify,
            ),
        )

    claim = _payload(
        ClaimOrGapInput,
        claim_or_gap_id=claim_ref,
        statement_ref=f"statement:{context.run_id}:two-captured-materials",
        inquiry_ref=context.inquiry_ref,
        support_relation_refs=(qualifications["a"],),
        contradiction_relation_refs=(qualifications["b"],),
        uncertainty_profile_ref="uncertainty:first-specimen:explicit",
    )
    markdown = _payload(
        MarkdownComposeInput,
        artifact_id=artifact_ref,
        claim_closure=(claim_ref,),
        evidence_relation_closure=(qualifications["a"], qualifications["b"]),
        citation_closure=(source_a.material_ref, source_b.material_ref),
    )
    return (
        *source_specs["a"],
        *source_specs["b"],
        _PayloadSpec("claim.form_or_open_gap", None, None, claim),
        _PayloadSpec("artifact.compose_markdown", None, None, markdown),
    )


def _payload_object_type(codec: PayloadCodec) -> ObjectType:
    return ObjectType(
        type_id=codec.payload_type_id,
        schema_version=codec.codec_version,
        codec_id=codec.codec_id,
        canonical_codec_version=codec.codec_version,
    )


def persist_first_specimen_payloads(
    port: TypedPayloadValuePort,
    scope: object,
    context: FirstSpecimenPayloadContext,
) -> PersistedOperationPayloads:
    """Persist the eight submission-static payloads inside the caller's UoW.

    ``InternalExportInput`` is deliberately excluded.  Its exact artifact ref
    binds the admitted artifact revision and content digest, so it can only be
    created by the post-artifact approval/admission gate.
    """

    bundle = build_first_specimen_bundle()
    persisted: list[tuple[str, ValueRef]] = []
    for spec in _payload_specs(context):
        kind = _OPERATION_KINDS[spec.operation_id]
        codec = bundle.codec_by_kind(kind)
        encoded = codec.encode_payload(spec.payload)
        if codec.decode_payload(encoded) != spec.payload:
            raise ValueError(f"{spec.operation_id} codec round-trip drift")
        exact = canonical_bytes(encoded)
        exact_digest = hashlib.sha256(exact).hexdigest()
        object_type = _payload_object_type(codec)
        value_id = f"{context.submission_id}:payload:{spec.operation_id}"
        provenance: dict[str, object] = {
            "submission_id": context.submission_id,
            "run_id": context.run_id,
            "operation_id": spec.operation_id,
            "operation_kind": kind,
            "source_label": spec.source_label,
            "payload_type_id": codec.payload_type_id,
            "codec_id": codec.codec_id,
            "codec_digest": codec.codec_digest,
        }
        provenance_digest = sha256_hex(provenance)
        ref = ValueRef(
            value_id=value_id,
            project_key=context.project_key,
            object_type=object_type,
            codec_id=codec.codec_id,
            content_digest=exact_digest,
            storage_kind="project_value_ref",
            store_id="successor_values",
            store_version="1",
            storage_ref=f"project-value:{value_id}",
            byte_size=len(exact),
            provenance_digest=provenance_digest,
        )
        port.put_exact(
            scope,
            value_id=value_id,
            object_type=object_type.type_id,
            codec_id=codec.codec_id,
            content=exact,
            expected_digest=exact_digest,
            provenance_digest=provenance_digest,
            expected_revision=0,
            expected_incarnation=f"p0c:{context.submission_id}:{value_id}",
            source_ref=spec.source_ref,
            provenance=provenance,
        )
        persisted.append((spec.operation_id, ref))
    return PersistedOperationPayloads(tuple(persisted))


def persist_internal_export_payload(
    port: TypedPayloadValuePort,
    scope: object,
    *,
    project_key: str,
    run_id: str,
    intent: DeliveryIntent,
    artifact_ref: str,
    expected_incarnation: str,
) -> ValueRef:
    """Persist the final export payload only after artifact admission/approval."""

    if intent.content_digest is None or intent.artifact_ref != artifact_ref:
        raise ValueError("delivery intent does not bind the exact admitted artifact")
    payload = _payload(
        InternalExportInput,
        delivery_intent_id=intent.delivery_intent_id,
        artifact_ref=artifact_ref,
        audience=intent.audience,
        approval_refs=intent.approval_refs,
        idempotency_key=intent.idempotency_key,
    )
    codec = build_first_specimen_bundle().codec_by_kind(
        "delivery.internal_export.v1"
    )
    encoded = codec.encode_payload(payload)
    if codec.decode_payload(encoded) != payload:
        raise ValueError("delivery.internal_export.v1 codec round-trip drift")
    exact = canonical_bytes(encoded)
    exact_digest = hashlib.sha256(exact).hexdigest()
    object_type = _payload_object_type(codec)
    value_id = f"{intent.delivery_intent_id}:payload:delivery.internal_export"
    provenance = {
        "submission_phase": "POST_ARTIFACT_APPROVAL",
        "run_id": run_id,
        "operation_id": "delivery.internal_export",
        "operation_kind": "delivery.internal_export.v1",
        "payload_type_id": codec.payload_type_id,
        "codec_id": codec.codec_id,
        "codec_digest": codec.codec_digest,
        "delivery_intent_id": intent.delivery_intent_id,
        "delivery_intent_digest": intent.content_digest,
        "artifact_ref": artifact_ref,
        "approval_refs": list(intent.approval_refs),
        "authority_digest": intent.authority_digest,
    }
    provenance_digest = sha256_hex(provenance)
    ref = ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=codec.codec_id,
        content_digest=exact_digest,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact),
        provenance_digest=provenance_digest,
    )
    port.put_exact(
        scope,
        value_id=value_id,
        object_type=object_type.type_id,
        codec_id=codec.codec_id,
        content=exact,
        expected_digest=exact_digest,
        provenance_digest=provenance_digest,
        expected_revision=0,
        expected_incarnation=expected_incarnation,
        source_ref=artifact_ref,
        provenance=provenance,
    )
    return ref


__all__ = [
    "FirstSpecimenPayloadContext",
    "PersistedOperationPayloads",
    "SourcePayloadContext",
    "persist_internal_export_payload",
    "persist_first_specimen_payloads",
]
