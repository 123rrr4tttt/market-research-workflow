"""Persist the C8 internal-export payload at its approval boundary."""

from __future__ import annotations

import hashlib
from dataclasses import MISSING, fields as dataclass_fields
from typing import Any, Protocol

from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.research.artifacts import DeliveryIntent
from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.research.object_types import ObjectType

from .checksum import content_digest
from .codecs import PayloadCodec
from .first_specimen import (
    InternalExportInput,
    _capability_failure,
    _raise_capability_failure,
    build_first_specimen_bundle,
)


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


def _payload(dto_cls: type, **fields: Any) -> Any:
    complete = dict(fields)
    for field_def in dataclass_fields(dto_cls):
        if field_def.name in complete or field_def.name == "payload_digest":
            continue
        if field_def.default is not MISSING:
            complete[field_def.name] = field_def.default
        elif field_def.default_factory is not MISSING:
            complete[field_def.name] = field_def.default_factory()
    return dto_cls(**complete, payload_digest=content_digest(complete))


def _payload_object_type(codec: PayloadCodec) -> ObjectType:
    return ObjectType(
        type_id=codec.payload_type_id,
        schema_version=codec.codec_version,
        codec_id=codec.codec_id,
        canonical_codec_version=codec.codec_version,
    )


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
        _raise_capability_failure(
            _capability_failure(
                "INVALID_ARTIFACT_CLOSURE",
                "delivery intent does not bind the exact admitted artifact",
            )
        )
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
        _raise_capability_failure(
            _capability_failure(
                "CAPABILITY_CONTRACT_INVALID",
                "delivery.internal_export.v1 codec round-trip drift",
            )
        )
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


__all__ = ["persist_internal_export_payload"]
