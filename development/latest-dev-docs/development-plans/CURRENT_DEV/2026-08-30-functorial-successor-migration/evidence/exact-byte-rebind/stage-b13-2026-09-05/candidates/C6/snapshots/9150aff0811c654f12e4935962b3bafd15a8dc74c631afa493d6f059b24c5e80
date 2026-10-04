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
from typing import Annotated, Any, Literal, NoReturn, TypeAlias

from functorial_kit import Failure
from mrw_functorial_kit.core import (
    successor_capability_contract_failures,
)


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
REDACTION_RESOURCE_CEILING_SCHEMA_REF = "mrw.successor.agent-core.c6-3.resource-ceiling.v1"
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
_C6_3_CONTRACT_WITNESS = "test:test_w05_n4_c63_typed_contract_failures"


def _contract_failure(
    code: str,
    message: str,
    *,
    boundary_class: str = "PURE_CONTRACT_FAILURE",
    **details: Any,
) -> Failure:
    """Build the canonical kit value before any legacy public exception lift."""

    return successor_capability_contract_failures.fail(
        code,
        message,
        {
            "owner": AGENT_CORE_C6_3_OWNER,
            "effect_boundary": "agent_core.c6_3.contract_core",
            "boundary_class": boundary_class,
            "failure_family": successor_capability_contract_failures.name,
            "witness": _C6_3_CONTRACT_WITNESS,
            **details,
        },
    )


def _raise_contract_failure(
    failure: Failure,
    exception_type: type[ValueError] = ValueError,
) -> NoReturn:
    # kit:boundary owner=agent_core_c6_3.py class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.capability.contract_failure witness=test:test_w05_n4_c63_typed_contract_failures
    raise exception_type(failure.message)


def _hex64_failure(value: Any, field_name: str) -> Failure | None:
    if not isinstance(value, str) or len(value) != 64:
        return _contract_failure(
            "digest_contract_invalid",
            f"{field_name} must be a 64-char lowercase hex digest",
            field=field_name,
        )
    if any(char not in "0123456789abcdef" for char in value):
        return _contract_failure(
            "digest_contract_invalid",
            f"{field_name} must be a 64-char lowercase hex digest",
            field=field_name,
        )
    return None


def _validated_fingerprint_entry(
    path: Any,
    digest: Any,
) -> tuple[str, str] | Failure:
    normalized_path = str(path)
    digest_failure = _hex64_failure(digest, "fingerprint digest")
    if digest_failure is not None:
        return digest_failure
    return normalized_path, digest


def _validated_provenance_entry(
    name: Any,
    digest: Any,
) -> tuple[str, str] | Failure:
    normalized_name = str(name)
    digest_failure = _hex64_failure(digest, "provenance digest")
    if digest_failure is not None:
        return digest_failure
    return normalized_name, digest


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
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "RedactionPolicyRef.schema_version is not frozen",
                    field="RedactionPolicyRef.schema_version",
                )
            )
        for name in ("policy_id", "policy_version"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                _raise_contract_failure(
                    _contract_failure(
                        "schema_contract_invalid",
                        f"RedactionPolicyRef.{name} is required",
                        field=f"RedactionPolicyRef.{name}",
                    )
                )
        digest_failure = _hex64_failure(self.policy_digest, "RedactionPolicyRef.policy_digest")
        if digest_failure is not None:
            _raise_contract_failure(digest_failure)

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
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    f"unsupported payload schema {self.schema_version!r}",
                    field="RedactionEvidencePayload.schema_version",
                )
            )
        if self.operation_kind != AGENT_CORE_C6_3_KIND:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    f"unsupported operation kind {self.operation_kind!r}",
                    field="RedactionEvidencePayload.operation_kind",
                )
            )
        for name in (
            "source_observation_ref",
            "source_kind",
            "trace_id",
            "request_id",
            "call_id",
            "interpreter_profile_ref",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                _raise_contract_failure(
                    _contract_failure(
                        "schema_contract_invalid",
                        f"RedactionEvidencePayload.{name} is required",
                        field=f"RedactionEvidencePayload.{name}",
                    )
                )
        source_digest_failure = _hex64_failure(
            self.source_observation_digest,
            "RedactionEvidencePayload.source_observation_digest",
        )
        if source_digest_failure is not None:
            _raise_contract_failure(source_digest_failure)
        object.__setattr__(
            self,
            "field_classifications",
            freeze_c6_json_object(dict(self.field_classifications)),
        )
        for path, classification in self.field_classifications:
            if not isinstance(path, str) or not path:
                _raise_contract_failure(
                    _contract_failure(
                        "schema_contract_invalid",
                        "field classification path must be a non-empty string",
                        field="RedactionEvidencePayload.field_classifications",
                    )
                )
            if classification not in _ALLOWED_CLASSES:
                _raise_contract_failure(
                    _contract_failure(
                        "schema_contract_invalid",
                        f"unsupported classification {classification!r}",
                        field="RedactionEvidencePayload.field_classifications",
                    )
                )
        if (
            not isinstance(self.max_input_bytes, int)
            or isinstance(self.max_input_bytes, bool)
            or self.max_input_bytes <= 0
        ):
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "max_input_bytes must be a positive int",
                    field="RedactionEvidencePayload.max_input_bytes",
                )
            )
        if (
            not isinstance(self.max_event_batch, int)
            or isinstance(self.max_event_batch, bool)
            or self.max_event_batch <= 0
        ):
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "max_event_batch must be a positive int",
                    field="RedactionEvidencePayload.max_event_batch",
                )
            )
        expected = content_digest(self, omit_fields=("payload_digest",))
        if self.payload_digest == "":
            object.__setattr__(self, "payload_digest", expected)
        else:
            digest_failure = _hex64_failure(self.payload_digest, "RedactionEvidencePayload.payload_digest")
            if digest_failure is not None:
                _raise_contract_failure(digest_failure)
            if self.payload_digest != expected:
                _raise_contract_failure(
                    _contract_failure(
                        "digest_contract_invalid",
                        "RedactionEvidencePayload.payload_digest does not match content",
                        field="RedactionEvidencePayload.payload_digest",
                    )
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
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "RedactedEvidence.schema_version is not frozen",
                    field="RedactedEvidence.schema_version",
                )
            )
        if self.raw_value_persisted is not False:
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "RedactedEvidence.raw_value_persisted must be false",
                    field="RedactedEvidence.raw_value_persisted",
                )
            )
        source_digest_failure = _hex64_failure(
            self.source_observation_digest,
            "RedactedEvidence.source_observation_digest",
        )
        if source_digest_failure is not None:
            _raise_contract_failure(source_digest_failure)
        object.__setattr__(self, "redacted_value", freeze_c6_json_object(dict(self.redacted_value)))
        object.__setattr__(self, "redacted_field_paths", tuple(self.redacted_field_paths))
        object.__setattr__(self, "omitted_field_paths", tuple(self.omitted_field_paths))
        fingerprint_entries: list[tuple[str, str]] = []
        for path, digest in self.fingerprint_entries:
            entry = _validated_fingerprint_entry(path, digest)
            if isinstance(entry, Failure):
                _raise_contract_failure(entry)
            fingerprint_entries.append(entry)
        object.__setattr__(self, "fingerprint_entries", tuple(fingerprint_entries))
        expected_redacted = content_digest(
            {
                "schema": REDACTED_EVIDENCE_SCHEMA_REF,
                "redacted_value": thaw_json_value(self.redacted_value),
            }
        )
        if self.redacted_digest == "":
            object.__setattr__(self, "redacted_digest", expected_redacted)
        else:
            digest_failure = _hex64_failure(self.redacted_digest, "RedactedEvidence.redacted_digest")
            if digest_failure is not None:
                _raise_contract_failure(digest_failure)
            if self.redacted_digest != expected_redacted:
                _raise_contract_failure(
                    _contract_failure(
                        "digest_contract_invalid",
                        "RedactedEvidence.redacted_digest does not match redacted value",
                        field="RedactedEvidence.redacted_digest",
                    )
                )
        expected_evidence = content_digest(self, omit_fields=("evidence_digest",))
        if self.evidence_digest == "":
            object.__setattr__(self, "evidence_digest", expected_evidence)
        else:
            digest_failure = _hex64_failure(self.evidence_digest, "RedactedEvidence.evidence_digest")
            if digest_failure is not None:
                _raise_contract_failure(digest_failure)
            if self.evidence_digest != expected_evidence:
                _raise_contract_failure(
                    _contract_failure(
                        "digest_contract_invalid",
                        "RedactedEvidence.evidence_digest does not match content",
                        field="RedactedEvidence.evidence_digest",
                    )
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
            "fingerprint_entries": [[path, digest] for path, digest in self.fingerprint_entries],
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
            _raise_contract_failure(
                _contract_failure(
                    "schema_contract_invalid",
                    "RedactionReceipt.schema_version is not frozen",
                    field="RedactionReceipt.schema_version",
                )
            )
        provenance_entries: list[tuple[str, str]] = []
        for name, value in self.source_to_redacted_provenance:
            entry = _validated_provenance_entry(name, value)
            if isinstance(entry, Failure):
                _raise_contract_failure(entry)
            provenance_entries.append(entry)
        object.__setattr__(
            self,
            "source_to_redacted_provenance",
            tuple(provenance_entries),
        )
        object.__setattr__(
            self,
            "policy_application_receipt",
            freeze_c6_json_object(dict(self.policy_application_receipt)),
        )
        expected = content_digest({key: value for key, value in self.to_plain().items() if key != "receipt_digest"})
        if self.receipt_digest == "":
            object.__setattr__(self, "receipt_digest", expected)
        else:
            digest_failure = _hex64_failure(self.receipt_digest, "RedactionReceipt.receipt_digest")
            if digest_failure is not None:
                _raise_contract_failure(digest_failure)
            if self.receipt_digest != expected:
                _raise_contract_failure(
                    _contract_failure(
                        "digest_contract_invalid",
                        "RedactionReceipt.receipt_digest does not match content",
                        field="RedactionReceipt.receipt_digest",
                    )
                )

    def to_plain(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence": self.evidence.to_plain(),
            "source_to_redacted_provenance": [[name, digest] for name, digest in self.source_to_redacted_provenance],
            "policy_application_receipt": thaw_json_value(self.policy_application_receipt),
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
                _raise_contract_failure(
                    _contract_failure(
                        "schema_contract_invalid",
                        f"RedactionResourceCeiling.{name} must be positive",
                        field=f"RedactionResourceCeiling.{name}",
                    )
                )
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
            digest_failure = _hex64_failure(self.ceiling_digest, "RedactionResourceCeiling.ceiling_digest")
            if digest_failure is not None:
                _raise_contract_failure(digest_failure)
            if self.ceiling_digest != expected:
                _raise_contract_failure(
                    _contract_failure(
                        "digest_contract_invalid",
                        "RedactionResourceCeiling.ceiling_digest does not match content",
                        field="RedactionResourceCeiling.ceiling_digest",
                    )
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


def _redaction_failure_from_contract(
    contract_failure: Failure,
    code: str,
) -> RedactionFailure:
    return RedactionFailure(code, contract_failure.message)


def _redaction_failure(
    code: str,
    message: str,
    *,
    contract_code: str,
    boundary_class: str = "PURE_CONTRACT_FAILURE",
    **details: Any,
) -> RedactionFailure:
    return _redaction_failure_from_contract(
        _contract_failure(
            contract_code,
            message,
            boundary_class=boundary_class,
            redaction_code=code,
            **details,
        ),
        code,
    )


def _apply_classification(
    value: Any,
    *,
    path: str,
    classifications: dict[str, str],
    redacted_paths: list[str],
    omitted_paths: list[str],
    fingerprints: list[tuple[str, str]],
    suppressed_values: list[Any],
) -> tuple[Any, bool] | RedactionFailure:
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
                fingerprints.append((child_path, sha256_hex(canonical_json(item).encode("utf-8"))))
                out[key] = {"fingerprint": fingerprints[-1][1]}
                redacted_paths.append(child_path)
                suppressed_values.extend(_leaf_scalars(item))
                continue
            if any(token in str(key).lower() for token in _SENSITIVE_PATH_TOKENS):
                return _redaction_failure_from_contract(
                    _contract_failure(
                        "program_binding_invalid",
                        (f"sensitive field is not classified by the bound policy: {child_path}"),
                        boundary_class="DOMAIN_REJECTION",
                        redaction_code="SensitiveFieldUnclassified",
                        field_path=child_path,
                    ),
                    "SensitiveFieldUnclassified",
                )
            classified = _apply_classification(
                item,
                path=child_path,
                classifications=classifications,
                redacted_paths=redacted_paths,
                omitted_paths=omitted_paths,
                fingerprints=fingerprints,
                suppressed_values=suppressed_values,
            )
            if isinstance(classified, RedactionFailure):
                return classified
            transformed, removed = classified
            if not removed:
                out[key] = transformed
        return out, False
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            classified = _apply_classification(
                item,
                path=path,
                classifications=classifications,
                redacted_paths=redacted_paths,
                omitted_paths=omitted_paths,
                fingerprints=fingerprints,
                suppressed_values=suppressed_values,
            )
            if isinstance(classified, RedactionFailure):
                return classified
            transformed, _removed = classified
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
        return _redaction_failure(
            code="RedactionPolicyMissing",
            message="payload operation kind is not the frozen C6.3 redaction atom",
            contract_code="schema_contract_invalid",
        )
    try:
        source_bytes = canonical_json(raw_observation).encode("utf-8")
    except (TypeError, ValueError) as exc:
        return _redaction_failure(
            code="SerializationFailed",
            message=f"source observation cannot be serialized: {exc}",
            contract_code="codec_contract_invalid",
            serialization_error=type(exc).__name__,
        )
    if len(source_bytes) > min(payload.max_input_bytes, REDACTION_RESOURCE_CEILING.max_input_bytes):
        return _redaction_failure(
            code="ResourceCeilingExceeded",
            message=(
                f"source observation bytes {len(source_bytes)} exceed ceiling "
                f"{min(payload.max_input_bytes, REDACTION_RESOURCE_CEILING.max_input_bytes)}"
            ),
            contract_code="program_binding_invalid",
            observed_bytes=len(source_bytes),
        )
    expected_source_digest = source_observation_digest(raw_observation)
    if expected_source_digest != payload.source_observation_digest:
        return _redaction_failure(
            code="SourceDigestMismatch",
            message="source observation digest does not match the exact payload binding",
            contract_code="digest_contract_invalid",
        )
    if len(payload.field_classifications) > REDACTION_RESOURCE_CEILING.max_classification_paths:
        return _redaction_failure(
            code="ResourceCeilingExceeded",
            message="field classification path count exceeds the redaction ceiling",
            contract_code="program_binding_invalid",
            observed_paths=len(payload.field_classifications),
        )
    classifications = dict(payload.field_classifications)
    expected_policy_digest = redaction_policy_digest(
        payload.policy.policy_id,
        payload.policy.policy_version,
        classifications,
    )
    if expected_policy_digest != payload.policy.policy_digest:
        return _redaction_failure(
            code="RedactionPolicyUnsupported",
            message="policy digest does not match the field classification map",
            contract_code="digest_contract_invalid",
        )

    redacted_paths: list[str] = []
    omitted_paths: list[str] = []
    fingerprints: list[tuple[str, str]] = []
    suppressed_values: list[Any] = []
    classified = _apply_classification(
        raw_observation,
        path="",
        classifications=classifications,
        redacted_paths=redacted_paths,
        omitted_paths=omitted_paths,
        fingerprints=fingerprints,
        suppressed_values=suppressed_values,
    )
    if isinstance(classified, RedactionFailure):
        return classified
    redacted_value, _removed = classified

    for raw_leaf in suppressed_values:
        if _raw_string_present(redacted_value, raw_leaf):
            return _redaction_failure(
                code="ForbiddenRawValueDetected",
                message="raw source value survived the redacted evidence output",
                contract_code="codec_contract_invalid",
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
    plain_body = {key: value for key, value in receipt.to_plain().items() if key != "receipt_digest"}
    if receipt.receipt_digest != content_digest(plain_body):
        return _redaction_failure(
            code="RedactedDigestMismatch",
            message="redaction receipt digest does not match its content",
            contract_code="digest_contract_invalid",
        )
    return receipt


def _profile_ref(profile_id: str, profile_version: str, digest: str) -> ContractProfileRef:
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
        "budget_ref": ("mrw.successor.agent-core.c6-3.budget.v1:" + REDACTION_RESOURCE_CEILING.ceiling_digest),
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


def build_agent_core_c6_3_bundle() -> Annotated[
    AgentCoreC6_3CapabilityBundle,
    "kit:non-authoritative derived_as=view "
    "fact_source=AGENT_CORE_C6_3_OWNER+capability_contract_constants "
    "witness=test:test_w05_agent_core_authority_metadata",
]:
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
) -> Annotated[
    OperationContractCatalogSnapshot,
    "kit:non-authoritative derived_as=view "
    "fact_source=AgentCoreC6_3CapabilityBundle.operations "
    "witness=test:test_w05_agent_core_authority_metadata",
]:
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
) -> Annotated[
    OperationContractRegistry,
    "kit:non-authoritative derived_as=view "
    "fact_source=AgentCoreC6_3CapabilityBundle+catalog_snapshot "
    "witness=test:test_w05_agent_core_authority_metadata",
]:
    return OperationContractRegistry(
        build_agent_core_c6_3_catalog(bundle),
        (bundle.operation,),
    )
