from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from app.successor_runtime.capabilities import source_library_c2_1 as c2_1
from app.successor_runtime.substrate.postgres.source_library_c2_1_canary import (
    AUTHORITY_EVENT_SCHEMA,
)

from . import test_p2_c2_1_canary_postgres as canary

pytestmark = pytest.mark.unit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_PACKET_V1 = (
    _REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/"
    "P2C21CapabilityPacket.v1.json"
)
_PACKET_V2 = _PACKET_V1.with_name("P2C21CapabilityPacket.v2.json")
_PACKET_V3 = _PACKET_V1.with_name("P2C21CapabilityPacket.v3.json")
_PACKET_V4 = _PACKET_V1.with_name("P2C21CapabilityPacket.v4.json")
_PACKET = _PACKET_V1.with_name("P2C21CapabilityPacket.v5.json")


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def test_packet_content_and_source_bindings_are_exact() -> None:
    packet = json.loads(_PACKET.read_bytes())
    claimed = packet.pop("content_digest")
    assert claimed == _canonical_digest(packet)
    assert packet["status"] == "FROZEN_LOCAL_ONLY_PROMOTED_NOT_LIVE_V5"

    for binding in packet["source_bindings"]:
        data = (_REPOSITORY_ROOT / binding["path"]).read_bytes()
        assert binding == {
            "path": binding["path"],
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "lines": len(data.splitlines()),
        }


def test_v2_additively_supersedes_immutable_v1_packet() -> None:
    v1_bytes = _PACKET_V1.read_bytes()
    v1 = json.loads(v1_bytes)
    v2 = json.loads(_PACKET_V2.read_bytes())
    v1_body = dict(v1)
    v1_claimed = v1_body.pop("content_digest")
    assert v1_claimed == _canonical_digest(v1_body)
    assert v2["supersedes"] == {
        "path": (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "P2C21CapabilityPacket.v1.json"
        ),
        "file_sha256": hashlib.sha256(v1_bytes).hexdigest(),
        "content_digest": v1_claimed,
        "disposition": "INVALIDATED_FOR_CURRENT_BYTES",
        "reason": (
            "shared plan digest now binds CompiledStep.transform_ref; exact "
            "Plan/assignment identities changed"
        ),
    }


def test_v4_additively_supersedes_v3_after_canonical_identity_consolidation() -> None:
    v3_bytes = _PACKET_V3.read_bytes()
    v3 = json.loads(v3_bytes)
    v4 = json.loads(_PACKET_V4.read_bytes())
    assert v4["supersedes"] == {
        "path": (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "P2C21CapabilityPacket.v3.json"
        ),
        "file_sha256": hashlib.sha256(v3_bytes).hexdigest(),
        "content_digest": v3["content_digest"],
        "disposition": "INVALIDATED_FOR_CURRENT_BYTES",
        "reason": (
            "C2.1 duplicate schema classes consolidated into one canonical "
            "shared identity"
        ),
    }


def test_v5_additively_supersedes_immutable_v4_packet() -> None:
    v4_bytes = _PACKET_V4.read_bytes()
    v4 = json.loads(v4_bytes)
    v5 = json.loads(_PACKET.read_bytes())
    assert v5["supersedes"] == {
        "path": (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "P2C21CapabilityPacket.v4.json"
        ),
        "file_sha256": hashlib.sha256(v4_bytes).hexdigest(),
        "content_digest": v4["content_digest"],
        "disposition": "INVALIDATED_FOR_CURRENT_BYTES",
        "reason": (
            "P2 contract shared-root locality baseline corrected to current "
            "reviewed roots"
        ),
    }


def test_packet_matches_current_contract_schemas_and_exact_fixture() -> None:
    packet = json.loads(_PACKET.read_bytes())
    bundle = c2_1.build_source_library_c2_1_bundle()
    fixture = canary._c2_1()
    transition = canary._canary_packet(fixture)

    contract = packet["operation_contract"]
    assert contract["kind"] == bundle.operation.ref.kind
    assert contract["contract_digest"] == bundle.operation.ref.contract_digest
    assert contract["owner_capability_id"] == bundle.operation.owner_capability_id
    assert contract["operation_catalog_digest"] == fixture.catalog.catalog_digest
    assert contract["deployment_catalog_digest"] == c2_1.deployment_catalog_digest()
    assert contract["operation_catalog_digest"] != contract["deployment_catalog_digest"]
    assert contract["payload_codec_digest"] == bundle.payload_codec().codec_digest
    assert contract["profile_digests"] == {
        name: profile.profile_digest for name, profile in bundle.profiles.items()
    }

    expected_schemas = []
    for name in (
        "SOURCE_ITEM_DEFINITION_SCHEMA",
        "SOURCE_TAXONOMY_SCHEMA",
        "SOURCE_MODE_SCHEMA",
        "SOURCE_EXECUTION_REQUEST_SCHEMA",
        "SOURCE_WARNING_SCHEMA",
        "SOURCE_REJECTION_SCHEMA",
        "SOURCE_RESOLUTION_OBSERVATION_SCHEMA",
    ):
        schema = getattr(c2_1, name)
        expected_schemas.append(
            {
                "name": name,
                "schema_ref": schema.schema_ref,
                "schema_digest": schema.schema_digest,
                "field_requiredness": [
                    [field, required] for field, required in schema.field_requiredness
                ],
            }
        )
    assert packet["schema_contracts"] == expected_schemas
    assert packet["resource_ceiling"] == dataclasses.asdict(c2_1.RESOURCE_CEILING)

    assert packet["interpreters"]["same_program_digest"] == (
        fixture.program.program_digest
    )
    assert packet["interpreters"]["same_plan_digest"] == fixture.plan.plan_digest
    assert packet["canary_fixture"]["runtime_assignment_digest"] == (
        fixture.assignment.assignment_digest
    )
    assert packet["canary_fixture"]["transition_packet_digest"] == (
        transition.transition_packet_digest
    )
    assert packet["canary_fixture"]["event_schema"] == AUTHORITY_EVENT_SCHEMA
    assert packet["canary_fixture"]["runtime_node_claim_executed"] is True
    assert packet["canary_fixture"]["provider_calls"] == 0


def test_packet_preserves_review_and_authority_ceiling() -> None:
    packet = json.loads(_PACKET.read_bytes())
    reviews = packet["independent_reviews"]
    assert reviews["p2_local_promotion"] == ("ALLOW P2 C2.1 LOCAL-ONLY PROMOTION")
    assert reviews["shared_traversal"] == "ALLOW_LOCALITY_REBIND"
    assert reviews["store_rehydration"] == "ALLOW"
    assert reviews["packet_v5"] == "PENDING"
    assert packet["open_findings"]["p0"] == []
    assert packet["open_findings"]["p1"] == ["P2C21_REVIEW_SURFACE_NOT_GIT_IDENTIFIED"]
    assert packet["rehydration"]["independent_review"] == "ALLOW"

    authority = packet["authority"]
    assert authority["local_disposable_runtime_node_canary_rehearsed"] is True
    assert authority["project_store_rehydration_rehearsed"] is True
    for key in (
        "production_canonical_write",
        "live_provider",
        "external_delivery",
        "production_cutover",
        "production_authority_transfer",
        "legacy_retired",
    ):
        assert authority[key] is False
