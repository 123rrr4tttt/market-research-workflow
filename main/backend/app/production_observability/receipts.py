from __future__ import annotations

# ruff: noqa: TRY003

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from collections.abc import Iterable, Mapping

from .errors import ObservabilityTypeError, ObservabilityValueError
from .contracts import RECEIPT_ARTIFACT_KINDS, RECEIPT_CONTRACT_VERSIONS, ReceiptScope
from .observations import Observation, observation_digest, parse_observed_at


class ReceiptValidationCode(StrEnum):
    VALID = "valid"
    WRONG_SCOPE = "wrong_scope"
    CONTRACT_VERSION_INVALID = "contract_version_invalid"
    ARTIFACT_KIND_INVALID = "artifact_kind_invalid"
    ISSUER_MISSING = "issuer_missing"
    SOURCE_REF_MISSING = "source_ref_missing"
    RELEASE_VERSION_MISSING = "release_version_missing"
    OBSERVATION_IDS_MISSING = "observation_ids_missing"
    OBSERVATION_DIGESTS_MISSING = "observation_digests_missing"
    OBSERVATION_ID_DUPLICATED = "observation_id_duplicated"
    OBSERVATION_DUPLICATED = "observation_duplicated"
    OBSERVATION_ID_NOT_BOUND = "observation_id_not_bound"
    OBSERVATION_DIGEST_INVALID = "observation_digest_invalid"
    OBSERVATION_RELEASE_MISMATCH = "observation_release_mismatch"
    OBSERVATION_TIME_AFTER_RECEIPT = "observation_time_after_receipt"
    RECEIPT_DIGEST_INVALID = "receipt_digest_invalid"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def receipt_digest(receipt: ObservationReceipt) -> str:
    payload = {
        "contract_version": receipt.contract_version,
        "artifact_kind": receipt.artifact_kind,
        "scope": receipt.scope.value,
        "receipt_id": receipt.receipt_id,
        "observed_at": receipt.observed_at.isoformat(),
        "domain": receipt.domain,
        "route": receipt.route,
        "release_version": receipt.release_version,
        "issuer": receipt.issuer,
        "source_ref": receipt.source_ref,
        "observation_ids": list(receipt.observation_ids),
        "observation_digests": dict(receipt.observation_digests),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ObservationReceipt:
    receipt_id: str
    observed_at: datetime
    scope: ReceiptScope
    contract_version: str
    artifact_kind: str
    domain: str
    route: str
    release_version: str
    issuer: str
    source_ref: str
    observation_ids: tuple[str, ...]
    observation_digests: Mapping[str, str]
    declared_digest: str | None = None

    def __post_init__(self) -> None:
        digests = {str(key).strip(): str(value).strip() for key, value in dict(self.observation_digests or {}).items()}
        ids = tuple(dict.fromkeys(str(item).strip() for item in self.observation_ids if str(item).strip()))
        declared = str(self.declared_digest or "").strip() or None
        object.__setattr__(self, "observation_ids", ids)
        object.__setattr__(self, "observation_digests", MappingProxyType(digests))
        object.__setattr__(self, "declared_digest", declared)
        object.__setattr__(self, "observed_at", parse_observed_at(self.observed_at))
        if not self.receipt_id.strip():
            raise ObservabilityValueError("receipt_id is required")
        if not isinstance(self.scope, ReceiptScope):
            raise ObservabilityTypeError("receipt scope is closed")
        if not self.domain.strip() or not self.route.strip() or not self.release_version.strip():
            raise ObservabilityValueError("receipt domain, route, and release_version are required")

    @property
    def digest(self) -> str:
        return receipt_digest(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "observed_at": self.observed_at.isoformat(),
            "scope": self.scope.value,
            "contract_version": self.contract_version,
            "artifact_kind": self.artifact_kind,
            "domain": self.domain,
            "route": self.route,
            "release_version": self.release_version,
            "issuer": self.issuer,
            "source_ref": self.source_ref,
            "observation_ids": list(self.observation_ids),
            "observation_digests": dict(self.observation_digests),
            "declared_digest": self.declared_digest,
        }


def make_observation_receipt(
    *,
    scope: ReceiptScope | str,
    receipt_id: str,
    observed_at: datetime | str,
    domain: str,
    route: str,
    release_version: str,
    issuer: str,
    source_ref: str,
    observations: Iterable[Observation],
) -> ObservationReceipt:
    receipt_scope = scope if isinstance(scope, ReceiptScope) else ReceiptScope(scope)
    ordered = tuple(observations)
    observation_ids = tuple(observation.observation_id for observation in ordered)
    observation_digests = {observation.observation_id: observation.digest for observation in ordered}
    if len(observation_ids) != len(set(observation_ids)):
        raise ObservabilityValueError("receipt observations must have unique observation_id")
    prototype = ObservationReceipt(
        receipt_id=receipt_id,
        observed_at=parse_observed_at(observed_at),
        scope=receipt_scope,
        contract_version=RECEIPT_CONTRACT_VERSIONS[receipt_scope],
        artifact_kind=RECEIPT_ARTIFACT_KINDS[receipt_scope],
        domain=domain,
        route=route,
        release_version=release_version,
        issuer=issuer,
        source_ref=source_ref,
        observation_ids=observation_ids,
        observation_digests=observation_digests,
    )
    return ObservationReceipt(
        receipt_id=receipt_id,
        observed_at=parse_observed_at(observed_at),
        scope=receipt_scope,
        contract_version=RECEIPT_CONTRACT_VERSIONS[receipt_scope],
        artifact_kind=RECEIPT_ARTIFACT_KINDS[receipt_scope],
        domain=domain,
        route=route,
        release_version=release_version,
        issuer=issuer,
        source_ref=source_ref,
        observation_ids=observation_ids,
        observation_digests=observation_digests,
        declared_digest=prototype.digest,
    )


def validate_production_receipt(
    receipt: ObservationReceipt | None,
    *,
    observations: Iterable[Observation],
) -> tuple[ReceiptValidationCode, ...]:
    if receipt is None:
        return (ReceiptValidationCode.CONTRACT_VERSION_INVALID,)
    failures: list[ReceiptValidationCode] = []
    if receipt.scope is not ReceiptScope.PRODUCTION:
        failures.append(ReceiptValidationCode.WRONG_SCOPE)
    if receipt.contract_version != RECEIPT_CONTRACT_VERSIONS[ReceiptScope.PRODUCTION]:
        failures.append(ReceiptValidationCode.CONTRACT_VERSION_INVALID)
    if receipt.artifact_kind != RECEIPT_ARTIFACT_KINDS[ReceiptScope.PRODUCTION]:
        failures.append(ReceiptValidationCode.ARTIFACT_KIND_INVALID)
    if not receipt.issuer.strip():
        failures.append(ReceiptValidationCode.ISSUER_MISSING)
    if not receipt.source_ref.strip():
        failures.append(ReceiptValidationCode.SOURCE_REF_MISSING)
    if not receipt.observation_ids:
        failures.append(ReceiptValidationCode.OBSERVATION_IDS_MISSING)
    if not receipt.observation_digests:
        failures.append(ReceiptValidationCode.OBSERVATION_DIGESTS_MISSING)
    if len(set(receipt.observation_ids)) != len(receipt.observation_ids):
        failures.append(ReceiptValidationCode.OBSERVATION_ID_DUPLICATED)

    indexed: dict[str, Observation] = {}
    duplicate_observation_ids = False
    for observation in observations:
        if observation.observation_id in indexed:
            duplicate_observation_ids = True
            continue
        indexed[observation.observation_id] = observation
    if duplicate_observation_ids:
        failures.append(ReceiptValidationCode.OBSERVATION_DUPLICATED)

    for observation_id in receipt.observation_ids:
        observation = indexed.get(observation_id)
        if observation is None:
            failures.append(ReceiptValidationCode.OBSERVATION_ID_NOT_BOUND)
            continue
        if receipt.observation_digests.get(observation_id) != observation_digest(observation):
            failures.append(ReceiptValidationCode.OBSERVATION_DIGEST_INVALID)
        if observation.release_version != receipt.release_version:
            failures.append(ReceiptValidationCode.OBSERVATION_RELEASE_MISMATCH)
        if observation.observed_at > receipt.observed_at:
            failures.append(ReceiptValidationCode.OBSERVATION_TIME_AFTER_RECEIPT)
    if receipt.declared_digest != receipt_digest(receipt):
        failures.append(ReceiptValidationCode.RECEIPT_DIGEST_INVALID)
    return tuple(dict.fromkeys(failures)) if failures else (ReceiptValidationCode.VALID,)


__all__ = [
    "ObservationReceipt",
    "ReceiptValidationCode",
    "make_observation_receipt",
    "receipt_digest",
    "validate_production_receipt",
]
