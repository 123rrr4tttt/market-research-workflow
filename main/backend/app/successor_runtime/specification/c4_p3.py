"""Read-only validation contract for the frozen C4/P3 evidence fragment.

The historical legacy/successor observations are already frozen in the
fragment.  This module never re-executes either implementation; it verifies the
exact artifact bytes, canonical content digest, family identity and closed
field surface expected by the shared fragment checker.
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

PROJECT_KEY = "p3-c4-fragment"
REGISTRY_REVISION = 3
RESOLVED_SCHEMA = "mrw_p3_c4_fragment"

FRAGMENT_ID = "p3-c4-family-local-implementation"
FRAGMENT_SCHEMA = "mrw.functorial_successor.p3_fragment.v1"
FRAGMENT_PHASE = "P3"
FRAGMENT_FAMILY = "C4"
FRAGMENT_STATUS = "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
FRAGMENT_CONTENT_DIGEST = (
    "a8c6ecaf1a3cada4729036b7ff12ee84fbf0353291f85f82f3b5e50dad0160ad"
)
FRAGMENT_FILE_SHA256 = (
    "058b02345b9d67c1e7ff51006afb4c28e2c8ce4dadf7a505fac6bbac781bd188"
)

_EVIDENCE_ROOT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
FRAGMENT_OUTPUT_REL = f"{_EVIDENCE_ROOT}/p3-fragments/C4.json"
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
FRAGMENT_PATH = REPOSITORY_ROOT / FRAGMENT_OUTPUT_REL

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
    BindingTarget(f"{_EVIDENCE_ROOT}/p1-fragments/C4.json", "p1_fragment"),
    BindingTarget(
        "main/backend/app/services/agent_batch/task_contract.py",
        "frozen_legacy_donor_c4_1_c4_2_c4_3",
    ),
    BindingTarget(
        "main/backend/app/api/agent_batch.py",
        "frozen_legacy_donor_c4_3",
    ),
)
_IMPLEMENTATION_BINDINGS = (
    BindingTarget(
        "main/backend/app/successor_runtime/specification/c4_p3.py",
        "frozen_c4_fragment_validator",
    ),
)
_TEST_BINDINGS = (
    BindingTarget(
        "main/backend/tests/successor_runtime/test_p3_c4_evidence_generator.py",
        "frozen_c4_fragment_validator",
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


def _load_frozen_fragment(root: Path, _bindings: BindingsByKind) -> dict[str, Any]:
    data = (root / FRAGMENT_OUTPUT_REL).read_bytes()
    if hashlib.sha256(data).hexdigest() != FRAGMENT_FILE_SHA256:
        raise ValueError("frozen C4 fragment file sha256 drift")
    fragment = json.loads(data)
    body = {key: value for key, value in fragment.items() if key != "content_digest"}
    if fragment.get("content_digest") != FRAGMENT_CONTENT_DIGEST:
        raise ValueError("frozen C4 fragment content digest drift")
    if content_digest(body) != FRAGMENT_CONTENT_DIGEST:
        raise ValueError("frozen C4 fragment canonical digest mismatch")
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
        raise ValueError("frozen C4 fragment identity drift")
    if set(fragment) != _REQUIRED_ROOTS:
        raise ValueError("frozen C4 fragment root field drift")
    body = {key: value for key, value in fragment.items() if key != "content_digest"}
    if content_digest(body) != FRAGMENT_CONTENT_DIGEST:
        raise ValueError("frozen C4 fragment digest mismatch")
    if [cell.get("cell_id") for cell in fragment["cells"]] != ["C4.1", "C4.2", "C4.3"]:
        raise ValueError("frozen C4 cell identity drift")
    for cell in fragment["cells"]:
        if set(cell) != _REQUIRED_CELL_FIELDS:
            raise ValueError("frozen C4 cell field drift")
        if cell["provider_calls"] != 0:
            raise ValueError("frozen C4 provider calls must remain zero")
    if any(AUTHORITY.values()) or set(fragment["authority"]) != set(AUTHORITY):
        raise ValueError("frozen C4 authority ceiling drift")
    if not fragment["open_findings"]:
        raise ValueError("frozen C4 open findings must be preserved")


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
        {"id": "FROZEN_C4_EVIDENCE", "description": "read-only frozen evidence"},
    ),
    body_builder=_load_frozen_fragment,
    self_check=_self_check,
)
