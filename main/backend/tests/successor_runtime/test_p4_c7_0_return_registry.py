"""Deterministic frozen-base/additive-C7 return-registry invariant tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.successor_runtime.capabilities import build_first_specimen_bundle
from app.successor_runtime.language.object_contracts import (
    CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF,
    CLAIM_OR_GAP_RETURN_CONTRACT_REF,
    DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
    DOCUMENT_ADMISSION_RETURN_CONTRACT_REF,
    EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF,
    FROZEN_BASE_RETURN_CONTRACT_REFS,
    READ_CANONICAL_REF_RETURN_CONTRACT_REF,
    RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    build_c7_document_admission_return_contract_extension,
    build_first_specimen_return_contract_registry,
    build_frozen_base_return_contract_registry,
)

_EXPECTED_BASE_REFS = (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    "mrw.functorial-successor.return.single-typed-output.v1",
    CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF,
    READ_CANONICAL_REF_RETURN_CONTRACT_REF,
    EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF,
    CLAIM_OR_GAP_RETURN_CONTRACT_REF,
    RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
    DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
)

_EXPECTED_ADMISSION_REQUIRED = {
    RUNTIME_VALUE_RETURN_CONTRACT_REF: False,
    "mrw.functorial-successor.return.single-typed-output.v1": False,
    CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF: False,
    READ_CANONICAL_REF_RETURN_CONTRACT_REF: False,
    EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF: True,
    CLAIM_OR_GAP_RETURN_CONTRACT_REF: True,
    RESEARCH_ARTIFACT_RETURN_CONTRACT_REF: True,
    DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF: True,
}

_EXPECTED_FIRST_SPECIMEN_OPERATION_DIGESTS = {
    "material.capture_document_snapshot.v1": (
        "399fbac80b9bdd1840d790a8e373b43426e7b51d206cb877784a9d0c242e196e"
    ),
    "material.read_canonical_ref.v1": (
        "30083862b60066f923758d8ce3c8181a228b30f897ae5ea9a10f97a273044f89"
    ),
    "evidence.qualify.v1": "b65724e56b77767fe895d7b05d2d8854cf01a38826911b3aa484a0b28d5d8e5c",
    "claim.form_or_open_gap.v1": (
        "7660dc4764cb735af41e8ca06b0e64d1b52b07d86fb5a2bbfbf2ed8bfb1e04c3"
    ),
    "artifact.compose_markdown.v1": (
        "e60a2bb72f0837fd644ab4f4522ef378769fb609ad9a9e272bb35056619a6ddc"
    ),
    "delivery.internal_export.v1": (
        "ae17472f5a7f0317e29ad2074c2620be8f0d7f8715293cadafa822bf9fb06262"
    ),
}

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EVIDENCE_ROOT = (
    _REPO_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)

_P2_PACKET_V5_SHA256 = (
    "81051ed22585b72e07f0e773ceebe70cccad7cbeee08aa7b2106c454517b0b09"
)
_P3_C4_FRAGMENT_SHA256 = (
    "058b02345b9d67c1e7ff51006afb4c28e2c8ce4dadf7a505fac6bbac781bd188"
)


def test_frozen_base_refs_order_and_contracts_are_unchanged() -> None:
    base = build_frozen_base_return_contract_registry()
    refs = tuple(ref for ref, _contract in base.entries)
    assert refs == _EXPECTED_BASE_REFS
    assert FROZEN_BASE_RETURN_CONTRACT_REFS == _EXPECTED_BASE_REFS
    for ref, contract in base.entries:
        assert contract.admission_required == _EXPECTED_ADMISSION_REQUIRED[ref]
        assert contract.success_modes == ("SUCCEEDED",)
        assert contract.failure_modes == ("FAILED",)
        assert contract.wait_modes == ("WAIT",)
        assert contract.cancel_modes == ("CANCELED",)


def test_combined_registry_is_base_plus_single_c7_extension() -> None:
    base = build_frozen_base_return_contract_registry()
    extension = build_c7_document_admission_return_contract_extension()
    combined = build_first_specimen_return_contract_registry()
    assert len(extension) == 1
    assert extension[0][0] == DOCUMENT_ADMISSION_RETURN_CONTRACT_REF
    assert extension[0][1].admission_required is True
    combined_refs = tuple(ref for ref, _contract in combined.entries)
    assert combined_refs == _EXPECTED_BASE_REFS + (
        DOCUMENT_ADMISSION_RETURN_CONTRACT_REF,
    )
    assert len(combined.entries) == len(base.entries) + 1


def test_existing_operation_contract_digests_and_frozen_bytes_unchanged() -> None:
    bundle = build_first_specimen_bundle()
    observed = {
        operation.ref.kind: operation.ref.contract_digest
        for operation in bundle.operations
    }
    assert observed == _EXPECTED_FIRST_SPECIMEN_OPERATION_DIGESTS
    assert (
        hashlib.sha256(
            (_EVIDENCE_ROOT / "P2C21CapabilityPacket.v5.json").read_bytes()
        ).hexdigest()
        == _P2_PACKET_V5_SHA256
    )
    assert (
        hashlib.sha256(
            (_EVIDENCE_ROOT / "p3-fragments" / "C4.json").read_bytes()
        ).hexdigest()
        == _P3_C4_FRAGMENT_SHA256
    )


def test_registry_builder_docstring_records_frozen_base_plus_extension() -> None:
    doc = build_first_specimen_return_contract_registry.__doc__ or ""
    assert "Frozen base return vocabulary" in doc
    assert "single additive C7 extension" in doc
