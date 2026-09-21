from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FAILURE_MAP = ROOT / "docs/governance/failure-family-map.v1.json"
AUTHORITY_MAP = ROOT / "docs/governance/derived-authority-map.v1.json"
EXACT_REBIND = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind"
)

B13_FAMILIES = ("C2", "C3", "C4", "C5", "C6", "C8", "C9")
EXPECTED_FAMILIES = set(B13_FAMILIES) | {"C7", "I1"}
EXPECTED_STAGE = {family: "stage-b19-2026-09-05" for family in B13_FAMILIES}
EXPECTED_STAGE["C7"] = "stage-b19-2026-09-05"
EXPECTED_STAGE["I1"] = "stage-b22-2026-09-05"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _canonical_without_digest(value: dict[str, Any]) -> bytes:
    return json.dumps(
        {key: item for key, item in value.items() if key != "content_digest"},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _assert_candidate_binding(row: dict[str, Any], *, family: str) -> dict[str, Any]:
    path_text = row.get("candidate_path", row.get("path"))
    assert isinstance(path_text, str)
    path = ROOT / path_text
    assert path.is_file(), path_text
    candidate = _load(path)
    raw = path.read_bytes()
    assert candidate["family"] == family
    assert candidate["schema"] == "mrw.family_fragment_rebind.candidate.v2"
    assert candidate["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    assert re.fullmatch(r"[0-9a-f]{64}", candidate["candidate_id"])
    assert row["candidate_id"] == candidate["candidate_id"]
    assert row.get("candidate_content_digest", row.get("content_digest")) == candidate["content_digest"]
    assert row.get("candidate_file_sha256", row.get("file_sha256")) == hashlib.sha256(raw).hexdigest()
    assert hashlib.sha256(_canonical_without_digest(candidate)).hexdigest() == candidate[
        "content_digest"
    ]
    assert row.get("status", row.get("candidate_status")) == candidate["status"]
    assert row.get("stage", row.get("candidate")) == EXPECTED_STAGE[family]
    assert Path(path_text).parts[-3:] == ("candidates", family, "candidate.v2.json")
    return candidate


def _walk(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def test_JSON__stage0_governance_maps_are_parseable_and_mutable() -> None:
    failure = _load(FAILURE_MAP)
    authority = _load(AUTHORITY_MAP)
    assert failure["schema"] == "mrw.functorial.failure_family_map.v1"
    assert authority["schema"] == "mrw.functorial.derived_authority_map.v1"
    assert failure["status"] == authority["status"] == "ACTIVE_MUTABLE_MAP"


def test_INVARIANT__b13_failure_and_authority_candidate_bindings_are_live() -> None:
    failure = _load(FAILURE_MAP)
    authority = _load(AUTHORITY_MAP)
    failure_entries = failure["priority_order"]
    authority_entries = authority["priority_order"]

    c2 = next(entry for entry in failure_entries if entry["surface"] == "C2 shared contract")
    assert c2["candidate"] == "stage-b19-2026-09-05"
    _assert_candidate_binding(c2, family="C2")

    crawler = next(entry for entry in failure_entries if entry["surface"] == "Crawler/Scrapyd effect family")
    assert crawler["registered_family"] == "crawler.runtime.failure"
    assert crawler["typed_port"].endswith("scrapyd_runtime.py::ScrapydTransportPort")
    assert crawler["durable_bridge"].endswith("durable_effect_bridge.py::DurableCrawlerEffectBridge")
    assert "not_configured" in crawler["not_configured_semantics"]
    assert "queued/accepted/scheduled/running" in crawler["durable_c2_3_closure"]
    _assert_candidate_binding(crawler, family="C2")

    c9 = next(entry for entry in authority_entries if entry["surface"] == "C9 semantic source and projection payloads")
    _assert_candidate_binding(c9["successor_candidate"] | {"stage": "stage-b19-2026-09-05"}, family="C9")
    sidecar_ref = c9["authority_sidecar"]
    sidecar_path = ROOT / sidecar_ref["path"]
    sidecar = _load(sidecar_path)
    assert sidecar["schema"] == "mrw.governance.generated_evidence_authority_sidecar.c9.v7"
    assert sidecar["sidecar_id"] == "c9.generated-evidence-authority-sidecar.v7"
    assert sidecar_ref["content_digest"] == sidecar["content_digest"]
    assert sidecar_ref["file_sha256"] == hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
    assert hashlib.sha256(_canonical_without_digest(sidecar)).hexdigest() == sidecar["content_digest"]
    authority_values = (
        value.values()
        for _, value in _walk(sidecar)
        if _ == "authority" and isinstance(value, dict)
    )
    assert all(item is False for values in authority_values for item in values)


def test_INVARIANT__shared_family_projection_preserves_mixed_lineage_rows() -> None:
    authority = _load(AUTHORITY_MAP)
    entry = next(
        item
        for item in authority["priority_order"]
        if item["surface"]
        == "shared successor family fragment registration projection"
    )
    projection = entry["shared_family_projection"]
    assert "stage" not in projection
    assert projection["kind"] == "CURRENT_CANDIDATE_ROWS"
    assert projection["lineage"] == "MIXED_STAGE_LINEAGE"
    rows = projection["rows"]
    assert {row["family"] for row in rows} == EXPECTED_FAMILIES - {"I1"}
    assert len(rows) == len(EXPECTED_FAMILIES) - 1
    for row in rows:
        _assert_candidate_binding(row, family=row["family"])
        assert (ROOT / row["fragment_path"]).is_file()
        assert (ROOT / row["manifest_path"]).is_file()


def test_INVARIANT__stage0_projection_covers_nine_families_with_mixed_lineage() -> None:
    authority = _load(AUTHORITY_MAP)
    projection = next(
        item["shared_family_projection"]
        for item in authority["priority_order"]
        if item["surface"] == "shared successor family fragment registration projection"
    )
    i1 = next(
        item
        for item in authority["priority_order"]
        if item["surface"] == "I1 exact-binding drift projection"
    )
    stages = {row["family"]: row["stage"] for row in projection["rows"]}
    stages["I1"] = i1["successor_candidate"]["stage"]
    assert set(stages) == EXPECTED_FAMILIES
    assert {stage for stage in stages.values()} == {
        "stage-b19-2026-09-05",
        "stage-b22-2026-09-05",
    }
    assert stages["I1"] == "stage-b22-2026-09-05"


def test_INVARIANT__all_authority_flags_are_false_and_no_deferred_status_remains() -> None:
    for path in (FAILURE_MAP, AUTHORITY_MAP):
        payload = _load(path)
        for key, value in _walk(payload):
            if key == "authority" and isinstance(value, dict):
                assert all(item is False for item in value.values())
            if key == "status" and isinstance(value, str):
                assert value not in {"DEFERRED", "OPEN", "IMPLEMENTATION_REQUIRED"}


def test_INVARIANT__i1_uses_the_live_b22_candidate_and_stage0_generator() -> None:
    authority = _load(AUTHORITY_MAP)
    i1 = next(entry for entry in authority["priority_order"] if entry["surface"] == "I1 exact-binding drift projection")
    assert i1["path"] == "scripts/generate_stage0_i1_exact_binding_rebind.py"
    assert i1["state"] == "STAGE_B22_CANDIDATE_NOT_AUTHORITY"
    candidate = i1["successor_candidate"]
    assert "stage-b22-2026-09-05/candidates/I1/candidate.v2.json" in candidate["path"]
    assert candidate["candidate_id"] == "ab3f9b96856d3c8e41b30d96ac8c1291dad5a71abe7d68d95d40d2f83ff07e66"
    assert candidate["amendment"] == "STAGE_B22_I1_EXACT_BINDING_REBIND_CANDIDATE_NOT_AUTHORITY"
    _assert_candidate_binding(candidate, family="I1")
    assert candidate["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"


def test_INVARIANT__historical_i1_candidates_are_history_only() -> None:
    authority = _load(AUTHORITY_MAP)
    i1 = next(entry for entry in authority["priority_order"] if entry["surface"] == "I1 exact-binding drift projection")
    successor = i1["successor_candidate"]
    assert "stage-b18-2026-09-05" not in successor["path"]
    assert "stage-b19-2026-09-05" not in successor["path"]
    assert "stage-b20-2026-09-05" not in successor["path"]
    assert "stage-b21-2026-09-05" not in successor["path"]

    history = {item["stage"]: item for item in i1["predecessor_candidates"]}
    assert set(history) == {
        "stage-b9-2026-09-05",
        "stage-b18-2026-09-05",
        "stage-b19-2026-09-05",
        "stage-b20-2026-09-05",
        "stage-b21-2026-09-05",
    }
    assert history["stage-b20-2026-09-05"]["status"] == "SUPERSEDED_BY_STAGE_B21_NOT_AUTHORITY"
    assert history["stage-b21-2026-09-05"]["status"] == "SUPERSEDED_BY_STAGE_B22_NOT_AUTHORITY"
    assert history["stage-b18-2026-09-05"]["status"] == "SUPERSEDED_HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY"
    assert history["stage-b19-2026-09-05"]["status"] == "SUPERSEDED_HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY"
    for stage, item in history.items():
        assert "AUTHORITY" in item["status"]
        assert f"/{stage}/candidates/I1/candidate.v2.json" in item["path"]
        assert (ROOT / item["path"]).is_file()
