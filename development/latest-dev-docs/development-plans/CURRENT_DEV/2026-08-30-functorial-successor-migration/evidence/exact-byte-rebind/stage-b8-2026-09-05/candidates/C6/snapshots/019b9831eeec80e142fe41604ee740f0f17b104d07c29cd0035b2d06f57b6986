"""Frozen typed contracts for the C6.3 pre-persistence redaction atom.

The atom redacts a source observation before any event, transcript, approval,
receipt or evidence persistence.  The Program payload carries only opaque
source refs, digests and the versioned policy; raw values are supplied to the
pure interpreter at call time and never enter the Program, Plan, payload,
receipt or digest namespace.  All failures are fail-closed and no raw value
survives in the redacted output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from app.successor_runtime.capabilities.agent_core_c6_common import (
    ProjectScope,
    SchemaSpec,
    build_payload_codec,
    freeze_c6_json_object,
    thaw_json_value,
)
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
    sha256_hex,
)
from app.successor_runtime.capabilities.contracts import (
    OperationContract,
    OperationContractCatalogSnapshot,
)
from app.successor_runtime.capabilities.profiles import (
    AuthorityProfile,
    ContractProfileRef,
    EffectProfile,
    FailureProfile,
    InterpreterProfile,
    ObservationProfile,
    ResourceProfile,
    SemanticProfile,
)
from app.successor_runtime.language.algebra import (
    FrozenJsonObject,
)
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    make_operation_contract,
)
from app.successor_runtime.research.object_types import ObjectType

__all__ = [
    "AGENT_CORE_C6_3_CATALOG_ID",
    "AGENT_CORE_C6_3_CATALOG_VERSION",
    "AGENT_CORE_C6_3_KIND",
    "AGENT_CORE_C6_3_OPERATION_ID",
    "AGENT_CORE_C6_3_OWNER",
    "AGENT_CORE_C6_3_PAYLOAD_CODEC_ID",
    "AGENT_CORE_C6_3_PAYLOAD_SCHEMA",
    "AGENT_CORE_C6_3_RESULT_TYPE",
    "AGENT_CORE_C6_3_SEMANTIC_IDENTITY",
    "REDACTED_EVIDENCE_SCHEMA",
    "REDACTION_POLICY_SCHEMA",
    "REDACTION_RECEIPT_SCHEMA",
    "REDACTION_RESOURCE_CEILING",
    "REDACTION_SOURCE_SCHEMA",
    "AgentCoreC6_3CapabilityBundle",
    "RedactedEvidence",
    "RedactionEvidencePayload",
    "RedactionFailure",
    "RedactionPolicyRef",
    "RedactionReceipt",
    "RedactionResourceCeiling",
    "build_agent_core_c6_3_bundle",
    "build_agent_core_c6_3_catalog",
    "build_agent_core_c6_3_registry",
    "redact_observation",
    "redaction_policy_digest",
    "source_observation_digest",
]


AGENT_CORE_C6_3_KIND = "observability.redact_evidence.v1"
AGENT_CORE_C6_3_OWNER = "agent_core.c6_3.v1"
AGENT_CORE_C6_3_OPERATION_ID = "observability.redact_evidence"
AGENT_CORE_C6_3_PAYLOAD_SCHEMA = "mrw.successor.agent-core.c6-3.payload.v1"
AGENT_CORE_C6_3_PAYLOAD_CODEC_ID = "mrw.successor.agent-core.c6-3.payload.codec.v1"
AGENT_CORE_C6_3_CATALOG_ID = "mrw.successor.agent-core.c6-3.operations"
AGENT_CORE_C6_3_CATALOG_VERSION = "1.0.0"
AGENT_CORE_C6_3_OBSERVATION_PROFILE = "mrw.successor.agent-core.c6-3.observation.v1"
AGENT_CORE_C6_3_SEMANTIC_IDENTITY = "observability.redact-evidence"
REDACTION_POLICY_SCHEMA_REF = "mrw.successor.agent-core.c6-3.redaction-policy.v1"
REDACTION_SOURCE_SCHEMA_REF = "mrw.successor.agent-core.c6-3.source.v1"
REDACTED_EVIDENCE_SCHEMA_REF = "mrw.successor.agent-core.c6-3.evidence.v1"
REDACTION_RECEIPT_SCHEMA_REF = "mrw.successor.agent-core.c6-3.receipt.v1"
REDACTION_RESOURCE_CEILING_SCHEMA_REF = (
    "mrw.successor.agent-core.c6-3.resource-ceiling.v1"
)
_REDACTED_MARKER = "[REDACTED]"

REDACTION_POLICY_TYPE = ObjectType("RedactionPolicyRef.v1")
REDACTION_SOURCE_TYPE = ObjectType("RedactionSourceObservation.v1")
REDACTED_EVIDENCE_TYPE = ObjectType("RedactedEvidence.v1")
REDACTION_RECEIPT_TYPE = ObjectType("RedactionReceipt.v1")
AGENT_CORE_C6_3_PAYLOAD_TYPE = ObjectType("RedactionEvidencePayload.v1")
AGENT_CORE_C6_3_RESULT_TYPE = REDACTION_RECEIPT_TYPE

REDACTION_POLICY_SCHEMA = SchemaSpec(
    schema_ref=REDACTION_POLICY_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("policy_id", True),
        ("policy_version", True),
        ("policy_digest", True),
    ),
)
REDACTION_SOURCE_SCHEMA = SchemaSpec(
    schema_ref=REDACTION_SOURCE_SCHEMA_REF,
    field_requiredness=(
        ("source_observation_ref", True),
        ("source_observation_digest", True),
        ("source_kind", True),
        ("trace_id", True),
        ("request_id", True),
        ("call_id", True),
        ("interpreter_profile_ref", True),
    ),
)
REDACTED_EVIDENCE_SCHEMA = SchemaSpec(
    schema_ref=REDACTED_EVIDENCE_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("source_observation_ref", True),
        ("source_observation_digest", True),
        ("source_kind", True),
        ("trace_id", True),
        ("request_id", True),
        ("call_id", True),
        ("interpreter_profile_ref", True),
        ("policy", True),
        ("redacted_value", True),
        ("redacted_digest", True),
        ("redacted_field_paths", True),
        ("omitted_field_paths", True),
        ("fingerprint_entries", True),
        ("declared_loss_profile_ref", True),
        ("raw_value_persisted", True),
        ("evidence_digest", True),
    ),
)
REDACTION_RECEIPT_SCHEMA = SchemaSpec(
    schema_ref=REDACTION_RECEIPT_SCHEMA_REF,
    field_requiredness=(
        ("schema_version", True),
        ("evidence", True),
        ("source_to_redacted_provenance", True),
        ("policy_application_receipt", True),
        ("receipt_digest", True),
    ),
)

REDACTION_FAILURE_CODES: frozenset[str] = frozenset(
    {
        "RedactionPolicyMissing",
        "RedactionPolicyUnsupported",
        "SensitiveFieldUnclassified",
        "SerializationFailed",
        "SourceDigestMismatch",
        "RedactedDigestMismatch",
        "ForbiddenRawValueDetected",
        "ResourceCeilingExceeded",
    }
)
_SENSITIVE_PATH_TOKENS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "authorization",
        "cookie",
        "credential",
        "private_key",
        "access_key",
    }
)
_ALLOWED_CLASSES: frozenset[str] = frozenset({"REDACT", "OMIT", "FINGERPRINT"})


def redaction_policy_digest(
    policy_id: str,
    policy_version: str,
    field_classifications: FrozenJsonObject | dict[str, Any],
) -> str:
    """Content digest binding one versioned policy to its classification map."""

    return content_digest(
        {
            "schema": REDACTION_POLICY_SCHEMA_REF,
            "policy_id": policy_id,
            "policy_version": policy_version,
            "field_classifications": dict(field_classifications),
        }
    )


def source_observation_digest(value: Any) -> str:
    """Canonical digest of one ephemeral source observation value."""

    return content_digest({"schema": REDACTION_SOURCE_SCHEMA_REF, "value": value})


@dataclass(frozen=True, slots=True)
class RedactionPolicyRef:
    policy_id: str
    policy_version: str
    policy_digest: str
    schema_version: str = REDACTION_POLICY_SCHEMA_REF

    def __post_init__(self) -> None:
        if self.schema_version != REDACTION_POLICY_SCHEMA_REF:
            raise ValueError("RedactionPolicyRef.schema_version is not frozen")
        for name in ("policy_id", "policy_version"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"RedactionPolicyRef.{name} is required")
        require_hex64(self.policy_digest, "RedactionPolicyRef.policy_digest")

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
        }


@dataclass(frozen=True, slots=True)
class RedactionEvidencePayload:
    """Exact-bound Atom payload; raw source bytes stay at the call boundary."""

    schema_version: Literal["mrw.successor.agent-core.c6-3.payload.v1"]
    operation_kind: Literal["observability.redact_evidence.v1"]
    project_scope: ProjectScope
    source_observation_ref: str
    source_observation_digest: str
    source_kind: str
    trace_id: str
    request_id: str
    call_id: str
    interpreter_profile_ref: str
    policy: RedactionPolicyRef
    field_classifications: FrozenJsonObject
    max_input_bytes: int
    max_event_batch: int
    payload_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_CORE_C6_3_PAYLOAD_SCHEMA:
            raise ValueError(f"unsupported payload schema {self.schema_version!r}")
        if self.operation_kind != AGENT_CORE_C6_3_KIND:
            raise ValueError(f"unsupported operation kind {self.operation_kind!r}")
        for name in (
            "source_observation_ref",
            "source_kind",
            "trace_id",
            "request_id",
            "call_id",
            "interpreter_profile_ref",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"RedactionEvidencePayload.{name} is required")
        require_hex64(
            self.source_observation_digest,
            "RedactionEvidencePayload.source_observation_digest",
        )
        object.__setattr__(
            self,
            "field_classifications",
            freeze_c6_json_object(dict(self.field_classifications)),
        )
        for path, classification in self.field_classifications:
            if not isinstance(path, str) or not path:
                raise ValueError("field classification path must be a non-empty string")
            if classification not in _ALLOWED_CLASSES:
                raise ValueError(f"unsupported classification {classification!r}")
        if (
            not isinstance(self.max_input_bytes, int)
            or isinstance(self.max_input_bytes, bool)
            or self.max_input_bytes <= 0
        ):
            raise ValueError("max_input_bytes must be a positive int")
        if (
            not isinstance(self.max_event_batch, int)
            or isinstance(self.max_event_batch, bool)
            or self.max_event_batch <= 0
        ):
            raise ValueError("max_event_batch must be a positive int")
        expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            require_hex64(
                self.payload_digest, "RedactionEvidencePayload.payload_digest"
            )
            if self.payload_digest != expected:
                raise ValueError(
                    "RedactionEvidencePayload.payload_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_kind": self.operation_kind,
            "project_scope": self.project_scope.to_plain(),
            "source_observation_ref": self.source_observation_ref,
            "source_observation_digest": self.source_observation_digest,
            "source_kind": self.source_kind,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "call_id": self.call_id,
            "interpreter_profile_ref": self.interpreter_profile_ref,
            "policy": self.policy.to_plain(),
            "field_classifications": dict(self.field_classifications),
            "max_input_bytes": self.max_input_bytes,
            "max_event_batch": self.max_event_batch,
            "payload_digest": self.payload_digest,
        }


@dataclass(frozen=True, slots=True)
class RedactedEvidence:
    """Redacted derivative bound to source/policy digests and declared loss."""

    schema_version: Literal["mrw.successor.agent-core.c6-3.evidence.v1"]
    source_observation_ref: str
    source_observation_digest: str
    source_kind: str
    trace_id: str
    request_id: str
    call_id: str
    interpreter_profile_ref: str
    policy: RedactionPolicyRef
    redacted_value: FrozenJsonObject
    redacted_field_paths: tuple[str, ...]
    omitted_field_paths: tuple[str, ...]
    fingerprint_entries: tuple[tuple[str, str], ...]
    declared_loss_profile_ref: str
    raw_value_persisted: Literal[False] = False
    redacted_digest: str = ""
    evidence_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != REDACTED_EVIDENCE_SCHEMA_REF:
            raise ValueError("RedactedEvidence.schema_version is not frozen")
        if self.raw_value_persisted is not False:
            raise ValueError("RedactedEvidence.raw_value_persisted must be false")
        require_hex64(
            self.source_observation_digest,
            "RedactedEvidence.source_observation_digest",
        )
        object.__setattr__(
            self, "redacted_value", freeze_c6_json_object(dict(self.redacted_value))
        )
        object.__setattr__(
            self, "redacted_field_paths", tuple(self.redacted_field_paths)
        )
        object.__setattr__(self, "omitted_field_paths", tuple(self.omitted_field_paths))
        object.__setattr__(
            self,
            "fingerprint_entries",
            tuple(
                (str(path), require_hex64(digest, "fingerprint digest"))
                for path, digest in self.fingerprint_entries
            ),
        )
        expected_redacted = content_digest(
            {
                "schema": REDACTED_EVIDENCE_SCHEMA_REF,
                "redacted_value": thaw_json_value(self.redacted_value),
            }
        )
        if self.redacted_digest == "":
            object.__setattr__(self, "redacted_digest", expected_redacted)
        else:
            require_hex64(self.redacted_digest, "RedactedEvidence.redacted_digest")
            if self.redacted_digest != expected_redacted:
                raise ValueError(
                    "RedactedEvidence.redacted_digest does not match redacted value"
                )
        expected_evidence = content_digest(self, omit_fields=("evidence_digest",))
        if self.evidence_digest == "":
            object.__setattr__(self, "evidence_digest", expected_evidence)
        else:
            require_hex64(self.evidence_digest, "RedactedEvidence.evidence_digest")
            if self.evidence_digest != expected_evidence:
                raise ValueError(
                    "RedactedEvidence.evidence_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_observation_ref": self.source_observation_ref,
            "source_observation_digest": self.source_observation_digest,
            "source_kind": self.source_kind,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "call_id": self.call_id,
            "interpreter_profile_ref": self.interpreter_profile_ref,
            "policy": self.policy.to_plain(),
            "redacted_value": thaw_json_value(self.redacted_value),
            "redacted_field_paths": list(self.redacted_field_paths),
            "omitted_field_paths": list(self.omitted_field_paths),
            "fingerprint_entries": [
                [path, digest] for path, digest in self.fingerprint_entries
            ],
            "declared_loss_profile_ref": self.declared_loss_profile_ref,
            "raw_value_persisted": self.raw_value_persisted,
            "redacted_digest": self.redacted_digest,
            "evidence_digest": self.evidence_digest,
        }


@dataclass(frozen=True, slots=True)
class RedactionReceipt:
    """Pre-persistence receipt binding source, policy and redacted evidence."""

    schema_version: Literal["mrw.successor.agent-core.c6-3.receipt.v1"]
    evidence: RedactedEvidence
    source_to_redacted_provenance: tuple[tuple[str, str], ...]
    policy_application_receipt: FrozenJsonObject
    receipt_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != REDACTION_RECEIPT_SCHEMA_REF:
            raise ValueError("RedactionReceipt.schema_version is not frozen")
        object.__setattr__(
            self,
            "source_to_redacted_provenance",
            tuple(
                (str(name), require_hex64(value, "provenance digest"))
                for name, value in self.source_to_redacted_provenance
            ),
        )
        object.__setattr__(
            self,
            "policy_application_receipt",
            freeze_c6_json_object(dict(self.policy_application_receipt)),
        )
        expected = content_digest(
            {
                key: value
                for key, value in self.to_plain().items()
                if key != "receipt_digest"
            }
        )
        if self.receipt_digest == "":
            object.__setattr__(self, "receipt_digest", expected)
        else:
            require_hex64(self.receipt_digest, "RedactionReceipt.receipt_digest")
            if self.receipt_digest != expected:
                raise ValueError(
                    "RedactionReceipt.receipt_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence": self.evidence.to_plain(),
            "source_to_redacted_provenance": [
                [name, digest] for name, digest in self.source_to_redacted_provenance
            ],
            "policy_application_receipt": thaw_json_value(
                self.policy_application_receipt
            ),
            "receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True, slots=True)
class RedactionFailure:
    code: Literal[
        "RedactionPolicyMissing",
        "RedactionPolicyUnsupported",
        "SensitiveFieldUnclassified",
        "SerializationFailed",
        "SourceDigestMismatch",
        "RedactedDigestMismatch",
        "ForbiddenRawValueDetected",
        "ResourceCeilingExceeded",
    ]
    message: str
    retryable: bool = False
    disposition: Literal["FAILED"] = "FAILED"


RedactionReceiptOrFailure: TypeAlias = RedactionReceipt | RedactionFailure


@dataclass(frozen=True, slots=True)
class RedactionResourceCeiling:
    """Bounded pure-CPU redaction envelope."""

    schema_ref: str
    max_input_bytes: int
    max_event_batch: int
    max_classification_paths: int
    ceiling_digest: str = ""

    def __post_init__(self) -> None:
        for name in (
            "max_input_bytes",
            "max_event_batch",
            "max_classification_paths",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"RedactionResourceCeiling.{name} must be positive")
        expected = content_digest(
            {
                "schema": REDACTION_RESOURCE_CEILING_SCHEMA_REF,
                "max_input_bytes": self.max_input_bytes,
                "max_event_batch": self.max_event_batch,
                "max_classification_paths": self.max_classification_paths,
            }
        )
        if self.ceiling_digest == "":
            object.__setattr__(self, "ceiling_digest", expected)
        else:
            require_hex64(
                self.ceiling_digest, "RedactionResourceCeiling.ceiling_digest"
            )
            if self.ceiling_digest != expected:
                raise ValueError(
                    "RedactionResourceCeiling.ceiling_digest does not match content"
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            "max_input_bytes": self.max_input_bytes,
            "max_event_batch": self.max_event_batch,
            "max_classification_paths": self.max_classification_paths,
            "ceiling_digest": self.ceiling_digest,
        }


REDACTION_RESOURCE_CEILING = RedactionResourceCeiling(
    schema_ref=REDACTION_RESOURCE_CEILING_SCHEMA_REF,
    max_input_bytes=65536,
    max_event_batch=1000,
    max_classification_paths=256,
)


def _leaf_scalars(value: Any) -> list[Any]:
    if isinstance(value, dict):
        out: list[Any] = []
        for item in value.values():
            out.extend(_leaf_scalars(item))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            out.extend(_leaf_scalars(item))
        return out
    return [value]


def _raw_string_present(redacted_plain: Any, raw_leaf: Any) -> bool:
    if isinstance(raw_leaf, str) and len(raw_leaf) >= 3:
        return raw_leaf in canonical_json(redacted_plain)
    return False


def _apply_classification(
    value: Any,
    *,
    path: str,
    classifications: dict[str, str],
    redacted_paths: list[str],
    omitted_paths: list[str],
    fingerprints: list[tuple[str, str]],
    suppressed_values: list[Any],
) -> tuple[Any, bool]:
    """Return ``(transformed, removed)``; sensitive leaves fail closed."""

    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            classification = classifications.get(child_path)
            if classification == "OMIT":
                omitted_paths.append(child_path)
                suppressed_values.extend(_leaf_scalars(item))
                continue
            if classification == "REDACT":
                out[key] = _REDACTED_MARKER
                redacted_paths.append(child_path)
                suppressed_values.extend(_leaf_scalars(item))
                continue
            if classification == "FINGERPRINT":
                fingerprints.append(
                    (child_path, sha256_hex(canonical_json(item).encode("utf-8")))
                )
                out[key] = {"fingerprint": fingerprints[-1][1]}
                redacted_paths.append(child_path)
                suppressed_values.extend(_leaf_scalars(item))
                continue
            if any(token in str(key).lower() for token in _SENSITIVE_PATH_TOKENS):
                raise SensitiveFieldUnclassified(child_path)
            transformed, removed = _apply_classification(
                item,
                path=child_path,
                classifications=classifications,
                redacted_paths=redacted_paths,
                omitted_paths=omitted_paths,
                fingerprints=fingerprints,
                suppressed_values=suppressed_values,
            )
            if not removed:
                out[key] = transformed
        return out, False
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            transformed, _removed = _apply_classification(
                item,
                path=path,
                classifications=classifications,
                redacted_paths=redacted_paths,
                omitted_paths=omitted_paths,
                fingerprints=fingerprints,
                suppressed_values=suppressed_values,
            )
            out.append(transformed)
        return out, False
    return value, False


class SensitiveFieldUnclassified(ValueError):
    """Fail-closed marker for unclassified sensitive field paths."""


def redact_observation(
    payload: RedactionEvidencePayload,
    raw_observation: Any,
) -> RedactionReceiptOrFailure:
    """Deterministic pre-persistence redaction; failures never yield a receipt."""

    if payload.operation_kind != AGENT_CORE_C6_3_KIND:
        return RedactionFailure(
            code="RedactionPolicyMissing",
            message="payload operation kind is not the frozen C6.3 redaction atom",
        )
    try:
        source_bytes = canonical_json(raw_observation).encode("utf-8")
    except (TypeError, ValueError) as exc:
        return RedactionFailure(
            code="SerializationFailed",
            message=f"source observation cannot be serialized: {exc}",
        )
    if len(source_bytes) > min(
        payload.max_input_bytes, REDACTION_RESOURCE_CEILING.max_input_bytes
    ):
        return RedactionFailure(
            code="ResourceCeilingExceeded",
            message=(
                f"source observation bytes {len(source_bytes)} exceed ceiling "
                f"{min(payload.max_input_bytes, REDACTION_RESOURCE_CEILING.max_input_bytes)}"
            ),
        )
    expected_source_digest = source_observation_digest(raw_observation)
    if expected_source_digest != payload.source_observation_digest:
        return RedactionFailure(
            code="SourceDigestMismatch",
            message="source observation digest does not match the exact payload binding",
        )
    if (
        len(payload.field_classifications)
        > REDACTION_RESOURCE_CEILING.max_classification_paths
    ):
        return RedactionFailure(
            code="ResourceCeilingExceeded",
            message="field classification path count exceeds the redaction ceiling",
        )
    classifications = dict(payload.field_classifications)
    expected_policy_digest = redaction_policy_digest(
        payload.policy.policy_id,
        payload.policy.policy_version,
        classifications,
    )
    if expected_policy_digest != payload.policy.policy_digest:
        return RedactionFailure(
            code="RedactionPolicyUnsupported",
            message="policy digest does not match the field classification map",
        )

    redacted_paths: list[str] = []
    omitted_paths: list[str] = []
    fingerprints: list[tuple[str, str]] = []
    suppressed_values: list[Any] = []
    try:
        redacted_value, _removed = _apply_classification(
            raw_observation,
            path="",
            classifications=classifications,
            redacted_paths=redacted_paths,
            omitted_paths=omitted_paths,
            fingerprints=fingerprints,
            suppressed_values=suppressed_values,
        )
    except SensitiveFieldUnclassified as exc:
        return RedactionFailure(
            code="SensitiveFieldUnclassified",
            message=f"sensitive field is not classified by the bound policy: {exc}",
        )

    for raw_leaf in suppressed_values:
        if _raw_string_present(redacted_value, raw_leaf):
            return RedactionFailure(
                code="ForbiddenRawValueDetected",
                message="raw source value survived the redacted evidence output",
            )

    policy_receipt = freeze_c6_json_object(
        {
            "policy_id": payload.policy.policy_id,
            "policy_version": payload.policy.policy_version,
            "policy_digest": payload.policy.policy_digest,
            "applied_before_persistence": True,
            "redacted_field_count": len(redacted_paths),
            "omitted_field_count": len(omitted_paths),
            "fingerprint_count": len(fingerprints),
            "raw_value_persisted": False,
        }
    )
    evidence = RedactedEvidence(
        schema_version=REDACTED_EVIDENCE_SCHEMA_REF,
        source_observation_ref=payload.source_observation_ref,
        source_observation_digest=payload.source_observation_digest,
        source_kind=payload.source_kind,
        trace_id=payload.trace_id,
        request_id=payload.request_id,
        call_id=payload.call_id,
        interpreter_profile_ref=payload.interpreter_profile_ref,
        policy=payload.policy,
        redacted_value=freeze_c6_json_object(redacted_value),
        redacted_field_paths=tuple(sorted(set(redacted_paths))),
        omitted_field_paths=tuple(sorted(set(omitted_paths))),
        fingerprint_entries=tuple(sorted(fingerprints)),
        declared_loss_profile_ref=("mrw.successor.agent-core.c6-3.declared-loss.v1"),
        raw_value_persisted=False,
    )
    receipt = RedactionReceipt(
        schema_version=REDACTION_RECEIPT_SCHEMA_REF,
        evidence=evidence,
        source_to_redacted_provenance=(
            ("source_observation_digest", payload.source_observation_digest),
            ("redacted_digest", evidence.redacted_digest),
            ("evidence_digest", evidence.evidence_digest),
        ),
        policy_application_receipt=policy_receipt,
    )
    plain_body = {
        key: value
        for key, value in receipt.to_plain().items()
        if key != "receipt_digest"
    }
    if receipt.receipt_digest != content_digest(plain_body):
        return RedactionFailure(
            code="RedactedDigestMismatch",
            message="redaction receipt digest does not match its content",
        )
    return receipt


def _profile_ref(
    profile_id: str, profile_version: str, digest: str
) -> ContractProfileRef:
    return ContractProfileRef(
        profile_id=profile_id,
        profile_version=profile_version,
        profile_digest=digest,
    )


def _semantic_profile() -> SemanticProfile:
    values = {
        "semantic_profile_id": "observability.redact_evidence.v1.semantic",
        "semantic_profile_version": "1.0.0",
        "reads": ("RedactionSourceObservation.v1", "RedactionPolicyRef.v1"),
        "creates": ("RedactedEvidence.v1", "RedactionReceipt.v1"),
        "creates_relations": (),
        "declared_loss": (
            "REDACTED_FIELD",
            "OMITTED_FIELD",
            "FINGERPRINTED_FIELD",
        ),
        "observation_profile_ref": AGENT_CORE_C6_3_OBSERVATION_PROFILE,
    }
    return SemanticProfile(**values, profile_digest=content_digest(values))


def _effect_profile() -> EffectProfile:
    values = {
        "effect_profile_id": "observability.redact_evidence.v1.effect",
        "effect_profile_version": "1.0.0",
        "execution_class": "PURE_TRANSFORM",
        "external_visibility": "NONE",
        "network_required": False,
        "irreversible": False,
        "cancellation_points": ("step_boundary",),
        "internal_export_only": False,
        "human_approval_required": False,
        "external_acquisition": False,
        "idempotency_profile_ref": "logical_request_id",
    }
    return EffectProfile(**values, profile_digest=content_digest(values))


def _resource_profile() -> ResourceProfile:
    values = {
        "resource_profile_id": "observability.redact_evidence.v1.resource",
        "resource_profile_version": "1.0.0",
        "resource_classes": ("cpu",),
        "concurrency_key": "project",
        "budget_units": "bytes+events",
        "default_soft_limit_seconds": 30,
        "default_hard_limit_seconds": 60,
        "node_profile_selector": "any",
        "budget_ref": (
            "mrw.successor.agent-core.c6-3.budget.v1:"
            + REDACTION_RESOURCE_CEILING.ceiling_digest
        ),
        "deadline_policy_ref": "mrw.successor.agent-core.c6-3.deadline.v1",
        "node_profile_requirements": ("any",),
        "units": 1,
    }
    return ResourceProfile(**values, profile_digest=content_digest(values))


def _failure_profile() -> FailureProfile:
    values = {
        "failure_profile_id": "observability.redact_evidence.v1.failure",
        "failure_profile_version": "1.0.0",
        "typed_failures": tuple(sorted(REDACTION_FAILURE_CODES)),
        "retryable": False,
        "degraded_acceptable": False,
        "unknown_outcome_supported": False,
        "readback_or_compensation": "none",
        "failure_union_ref": "mrw.successor.agent-core.c6-3.failures.v1",
        "retryable_failure_kinds": (),
        "readback_profile_ref": None,
        "compensation_profile_ref": None,
    }
    return FailureProfile(**values, profile_digest=content_digest(values))


def _authority_profile() -> AuthorityProfile:
    values = {
        "authority_profile_id": "observability.redact_evidence.v1.authority",
        "authority_profile_version": "1.0.0",
        "grant_scopes": ("project",),
        "approval_required": False,
        "approval_kinds": (),
        "credential_refs": (),
        "canonical_owner": "observability.redaction-policy.v1",
        "revalidation_points": ("claim_time",),
        "authority_epoch": 1,
    }
    return AuthorityProfile(**values, profile_digest=content_digest(values))


def _interpreter_profile() -> InterpreterProfile:
    values = {
        "interpreter_profile_id": "successor.agent_core.c6_3.redaction.v1",
        "interpreter_profile_version": "1.0.0",
        "supported_contract_kinds": (AGENT_CORE_C6_3_KIND,),
        "supported_contract_refs": (),
        "dependency_digest": content_digest(
            {
                "interpreter": "successor-native.agent_core.c6_3.redaction",
                "version": "1.0.0",
                "donor": "provider_trace._redacted_*_snapshot",
            }
        ),
        "security_profile_ref": "mrw.functorial-successor.security.redaction.v1",
        "resource_profile_ref": "observability.redact_evidence.v1.resource",
        "credential_requirements_ref": None,
        "cancellation_profile_ref": "step_boundary",
        "idempotency_profile_ref": "logical_request_id",
        "authoritative_readback_profile_ref": None,
        "receipt_codec_ref": REDACTION_RECEIPT_SCHEMA_REF,
    }
    return InterpreterProfile(**values, profile_digest=content_digest(values))


def _observation_profile() -> ObservationProfile:
    values = {
        "observation_profile_id": AGENT_CORE_C6_3_OBSERVATION_PROFILE,
        "observation_profile_version": "1.0.0",
        "dimensions": (
            "schema_version",
            "source_observation_ref",
            "source_observation_digest",
            "source_kind",
            "trace_id",
            "request_id",
            "call_id",
            "interpreter_profile_ref",
            "redaction_policy_id",
            "redaction_policy_version",
            "redaction_policy_digest",
            "redacted_digest",
            "redacted_field_paths",
            "omitted_field_paths",
            "fingerprints",
            "raw_value_persisted",
            "declared_loss",
        ),
        "compatible_with_legacy": True,
        "observation_schema_ref": REDACTION_RECEIPT_SCHEMA_REF,
    }
    return ObservationProfile(**values, profile_digest=content_digest(values))


@dataclass(frozen=True, slots=True)
class AgentCoreC6_3CapabilityBundle:
    bundle_id: str
    operation: OperationContract
    codecs: tuple[Any, ...]
    profiles: dict[str, object]

    def payload_codec(self) -> Any:
        return self.codecs[0]


def build_agent_core_c6_3_bundle() -> AgentCoreC6_3CapabilityBundle:
    semantic = _semantic_profile()
    effect = _effect_profile()
    resource = _resource_profile()
    failure = _failure_profile()
    authority = _authority_profile()
    interpreter = _interpreter_profile()
    observation = _observation_profile()
    operation = make_operation_contract(
        kind=AGENT_CORE_C6_3_KIND,
        contract_version="1.0.0",
        input_type=AGENT_CORE_C6_3_PAYLOAD_TYPE,
        output_type=AGENT_CORE_C6_3_RESULT_TYPE,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        semantic_profile_ref=_profile_ref(
            semantic.semantic_profile_id,
            semantic.semantic_profile_version,
            semantic.profile_digest,
        ),
        effect_profile_ref=_profile_ref(
            effect.effect_profile_id,
            effect.effect_profile_version,
            effect.profile_digest,
        ),
        resource_profile_ref=_profile_ref(
            resource.resource_profile_id,
            resource.resource_profile_version,
            resource.profile_digest,
        ),
        failure_profile_ref=_profile_ref(
            failure.failure_profile_id,
            failure.failure_profile_version,
            failure.profile_digest,
        ),
        authority_profile_ref=_profile_ref(
            authority.authority_profile_id,
            authority.authority_profile_version,
            authority.profile_digest,
        ),
        interpreter_compatibility_ref=_profile_ref(
            interpreter.interpreter_profile_id,
            interpreter.interpreter_profile_version,
            interpreter.profile_digest,
        ),
        observation_profile_ref=_profile_ref(
            observation.observation_profile_id,
            observation.observation_profile_version,
            observation.profile_digest,
        ),
        allowed_override_schema_ref="mrw.functorial-successor.override.none.v1",
        owner_capability_id=AGENT_CORE_C6_3_OWNER,
    )
    codec = build_payload_codec(
        codec_id=AGENT_CORE_C6_3_PAYLOAD_CODEC_ID,
        codec_version="1",
        contract_ref=operation.ref,
        payload_type_id=AGENT_CORE_C6_3_PAYLOAD_TYPE.type_id,
        dto_cls=RedactionEvidencePayload,
    )
    return AgentCoreC6_3CapabilityBundle(
        bundle_id="mrw.successor.agent-core.c6-3",
        operation=operation,
        codecs=(codec,),
        profiles={
            "semantic": semantic,
            "effect": effect,
            "resource": resource,
            "failure": failure,
            "authority": authority,
            "interpreter": interpreter,
            "observation": observation,
        },
    )


def build_agent_core_c6_3_catalog(
    bundle: AgentCoreC6_3CapabilityBundle,
) -> OperationContractCatalogSnapshot:
    return OperationContractCatalogSnapshot(
        catalog_id=AGENT_CORE_C6_3_CATALOG_ID,
        catalog_version=AGENT_CORE_C6_3_CATALOG_VERSION,
        entries=(
            (
                bundle.operation.ref.kind,
                bundle.operation.ref.contract_version,
                bundle.operation.ref.contract_digest,
                bundle.operation.owner_capability_id,
            ),
        ),
    )


def build_agent_core_c6_3_registry(
    bundle: AgentCoreC6_3CapabilityBundle,
) -> OperationContractRegistry:
    return OperationContractRegistry(
        build_agent_core_c6_3_catalog(bundle),
        (bundle.operation,),
    )
