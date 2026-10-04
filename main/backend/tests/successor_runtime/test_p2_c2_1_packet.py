from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


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
_EXACT_REBIND_ROOT = (
    _REPOSITORY_ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind"
)
_TEMP_B18_STAGE = "stage-b18-2099-01-01"


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

    from .historical_fixture import historical_bytes

    for binding in packet["source_bindings"]:
        data = historical_bytes(binding["path"], binding["sha256"])
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


def test_packet_matches_current_contract_schemas_and_exact_fixture(tmp_path: Path) -> None:
    """Replay the packet's exact historical contract; current v2 has separate selectors."""
    import os
    import subprocess
    import sys

    from .historical_fixture import historical_bytes, materialize_revision

    # This revision contains the original assertion and its dependency closure.
    revision = "9fa8aefaae8f30a080f3d2dcac6dfb6ff9f773e0"
    root = materialize_revision(tmp_path / "packet-history", revision)
    packet = json.loads(_PACKET.read_bytes())
    for binding in packet["source_bindings"]:
        relative = Path(binding["path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        data = historical_bytes(binding["path"], binding["sha256"])
        assert hashlib.sha256(data).hexdigest() == binding["sha256"]
        assert len(data) == binding["bytes"]
        assert len(data.decode("utf-8").splitlines()) == binding["lines"]
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    packet_path = root / _PACKET.relative_to(_REPOSITORY_ROOT)
    packet_path.write_bytes(_PACKET.read_bytes())
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        str(root / relative) for relative in ("", "src", "main/backend")
    )
    environment["DATABASE_URL"] = "postgresql+psycopg2://postgres:postgres@127.0.0.1:1/postgres"
    environment["REDIS_URL"] = "redis://127.0.0.1:1/0"
    environment["ES_URL"] = "http://127.0.0.1:1"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q",
         "main/backend/tests/successor_runtime/test_p2_c2_1_packet.py::"
         "test_packet_matches_current_contract_schemas_and_exact_fixture"],
        cwd=root, env=environment, capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


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
