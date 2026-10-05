"""Read-only validation contract for the frozen C5/P3 evidence fragment.

The historical session, attempt and process observations are frozen in the
fragment and its adjudication.  This module validates exact bytes and closed
fields; it does not reconstruct or re-execute legacy behavior.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.specification.shared_family_generator import (
    BindingsByKind,
    BindingTarget,
    FamilyFragmentConfig,
)

PROJECT_KEY = "p3-c5-fragment"
RESOLVED_SCHEMA = "mrw_p3_c5_fragment"
REGISTRY_REVISION = 1

FRAGMENT_ID = "p3-c5-family-local-implementation"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p3_fragment.v1"
FRAGMENT_PHASE = "P3"
FRAGMENT_FAMILY = "C5"
FRAGMENT_STATUS = "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
FRAGMENT_CONTENT_DIGEST = (
    "1dedd393e46037ed8cfb66aa43ef32255963da63d98c7f908a2ddee6db0e4c7d"
)
FRAGMENT_FILE_SHA256 = (
    "0e1da888f13adf637774612be90ae367633f565774585b6ad18ace045cdf5231"
)

_EVIDENCE_ROOT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
FRAGMENT_OUTPUT_REL = f"{_EVIDENCE_ROOT}/p3-fragments/C5.json"
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
EVIDENCE_ROOT = REPOSITORY_ROOT / _EVIDENCE_ROOT
FRAGMENT_PATH = REPOSITORY_ROOT / FRAGMENT_OUTPUT_REL

ADJUDICATION_PATH = EVIDENCE_ROOT / "C5_4LocatorAdjudication.v1.json"
ADJUDICATION_RELATIVE = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/"
    "C5_4LocatorAdjudication.v1.json"
)
ADJUDICATION_CONTENT_DIGEST = (
    "1b2209a7cc55be719a4470575579a66b744171aadea52eae9e30e075e81b9b0d"
)
ADJUDICATION_FILE_SHA256 = (
    "81a64ec01988d7dd02034f689d8c70e0d7d58dbc6c39eb6306fe029a14b34f77"
)
NORMATIVE_DONOR_LOCATORS = (
    "main/backend/app/services/tasks.py",
    "main/backend/app/services/agent_sessions",
    "main/backend/app/celery_app.py",
)
SUPPLEMENTARY_READ_ONLY_EVIDENCE = (
    "main/backend/app/api/process.py",
    "main/backend/app/api/agent_batch.py",
)
PROHIBITED_DIRTY_SOURCE = "main/backend/app/services/task_readback_metadata.py"
PROHIBITED_DIRTY_SOURCE_SHA256 = (
    "981c970ea1610450f681a1dfe1a6a22288c33363b38d827ca7f39052072072e9"
)

AUTHORITY = {
    "production_canonical_write": False,
    "live_provider": False,
    "external_delivery": False,
    "live_credential": False,
    "network": False,
    "cutover": False,
    "authority_transfer": False,
    "legacy_retired": False,
    "p3_promotion": False,
}

_SOURCE_BINDINGS = (
    BindingTarget(
        f"{_EVIDENCE_ROOT}/P1FunctorizationEligibility.v1.json",
        "p1_eligibility",
    ),
    BindingTarget(f"{_EVIDENCE_ROOT}/p1-fragments/C5.json", "p1_fragment"),
    BindingTarget(
        f"{_EVIDENCE_ROOT}/C5_4LocatorAdjudication.v1.json",
        "c5_4_locator_adjudication",
    ),
)
_IMPLEMENTATION_BINDINGS = (
    BindingTarget(
        "main/backend/app/successor_runtime/specification/c5_p3.py",
        "frozen_c5_fragment_validator",
    ),
)
_TEST_BINDINGS = (
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c5_0_evidence_generator.py",
        "frozen_c5_fragment_validator",
    ),
)

_REQUIRED_ROOTS = {
    "schema",
    "phase",
    "family",
    "fragment_id",
    "status",
    "cells",
    "source_bindings",
    "implementation_bindings",
    "test_bindings",
    "authority",
    "resolved_findings",
    "open_findings",
    "content_digest",
}
_REQUIRED_CELL_FIELDS = {
    "cell_id",
    "p1_cell_digest",
    "operation_bindings",
    "owner_capability_id",
    "program_digest",
    "plan_digest",
    "legacy_observation",
    "successor_observation",
    "rollback_observation",
    "provider_calls",
    "postgres_requirement",
}


def _validate_adjudication() -> None:
    data = ADJUDICATION_PATH.read_bytes()
    if hashlib.sha256(data).hexdigest() != ADJUDICATION_FILE_SHA256:
        raise ValueError("C5 adjudication file sha256 drift")
    artifact = json.loads(data)
    body = {key: value for key, value in artifact.items() if key != "content_digest"}
    if artifact.get("content_digest") != ADJUDICATION_CONTENT_DIGEST:
        raise ValueError("C5 adjudication content digest drift")
    if content_digest(body) != ADJUDICATION_CONTENT_DIGEST:
        raise ValueError("C5 adjudication canonical digest mismatch")
    if artifact.get("normative_donor_locators") != list(NORMATIVE_DONOR_LOCATORS):
        raise ValueError("C5 adjudication donor locators drift")
    if artifact.get("supplementary_read_only_evidence") != list(
        SUPPLEMENTARY_READ_ONLY_EVIDENCE
    ):
        raise ValueError("C5 adjudication supplementary locators drift")
    dirty = artifact.get("path_observations", {}).get("source_checkout_dirty", {})
    if dirty != {
        "path": PROHIBITED_DIRTY_SOURCE,
        "git_status": "UNTRACKED_EXCLUDED",
        "sha256": PROHIBITED_DIRTY_SOURCE_SHA256,
        "adopted": False,
    }:
        raise ValueError("C5 adjudication dirty-source disposition drift")


def _load_frozen_fragment(root: Path, _bindings: BindingsByKind) -> dict[str, Any]:
    _validate_adjudication()
    data = (root / FRAGMENT_OUTPUT_REL).read_bytes()
    if hashlib.sha256(data).hexdigest() != FRAGMENT_FILE_SHA256:
        raise ValueError("frozen C5 fragment file sha256 drift")
    fragment = json.loads(data)
    body = {key: value for key, value in fragment.items() if key != "content_digest"}
    if fragment.get("content_digest") != FRAGMENT_CONTENT_DIGEST:
        raise ValueError("frozen C5 fragment content digest drift")
    if content_digest(body) != FRAGMENT_CONTENT_DIGEST:
        raise ValueError("frozen C5 fragment canonical digest mismatch")
    return fragment


def _self_check(fragment: Mapping[str, Any]) -> None:
    identity = {
        "schema": FRAGMENT_SCHEMA,
        "phase": FRAGMENT_PHASE,
        "family": FRAGMENT_FAMILY,
        "fragment_id": FRAGMENT_ID,
        "status": FRAGMENT_STATUS,
    }
    if {key: fragment.get(key) for key in identity} != identity:
        raise ValueError("frozen C5 fragment identity drift")
    if set(fragment) != _REQUIRED_ROOTS:
        raise ValueError("frozen C5 fragment root field drift")
    body = {key: value for key, value in fragment.items() if key != "content_digest"}
    if content_digest(body) != FRAGMENT_CONTENT_DIGEST:
        raise ValueError("frozen C5 fragment digest mismatch")
    if [cell.get("cell_id") for cell in fragment["cells"]] != [
        "C5.1",
        "C5.2",
        "C5.3",
        "C5.4",
    ]:
        raise ValueError("frozen C5 cell identity drift")
    for cell in fragment["cells"]:
        if set(cell) != _REQUIRED_CELL_FIELDS:
            raise ValueError("frozen C5 cell field drift")
        if cell["provider_calls"] != 0:
            raise ValueError("frozen C5 provider calls must remain zero")
    if any(AUTHORITY.values()) or set(fragment["authority"]) != set(AUTHORITY):
        raise ValueError("frozen C5 authority ceiling drift")
    resolved = {item.get("id"): item for item in fragment["resolved_findings"]}
    blocker = resolved.get("C5_4_FROZEN_LOCATOR_CLARIFICATION_REQUIRED")
    if blocker is None:
        raise ValueError("frozen C5 adjudicated blocker missing")
    if blocker.get("state") != "RESOLVED_BY_EXISTING_FREEZE_PRECEDENCE":
        raise ValueError("frozen C5 adjudication state drift")


CONFIG = FamilyFragmentConfig(
    family_id=FRAGMENT_FAMILY,
    phase=FRAGMENT_PHASE,
    schema=FRAGMENT_SCHEMA,
    fragment_id=FRAGMENT_ID,
    status=FRAGMENT_STATUS,
    fragment_output_rel=FRAGMENT_OUTPUT_REL,
    source_bindings=_SOURCE_BINDINGS,
    implementation_bindings=_IMPLEMENTATION_BINDINGS,
    test_bindings=_TEST_BINDINGS,
    authority=AUTHORITY,
    open_findings=(
        {"id": "FROZEN_C5_EVIDENCE", "description": "read-only frozen evidence"},
    ),
    body_builder=_load_frozen_fragment,
    self_check=_self_check,
)
