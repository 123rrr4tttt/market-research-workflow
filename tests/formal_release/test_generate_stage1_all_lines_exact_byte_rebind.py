from __future__ import annotations

import hashlib
import json
import shlex
import sys
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/formal_release"))
import generate_stage1_all_lines_exact_byte_rebind as tool  # noqa: E402


def test_build_document_authority_metadata() -> None:
    return_hint = get_type_hints(tool.build_document, include_extras=True)["return"]
    assert get_origin(return_hint) is Annotated
    _, annotation = get_args(return_hint)
    tokens = shlex.split(annotation)
    assert tokens[0] == "kit:non-authoritative"
    assert dict(token.split("=", 1) for token in tokens[1:]) == {
        "derived_as": "generated_evidence",
        "fact_source": (
            "frozen_all_lines_predecessor+current_repo_bytes+stage0_candidate_bindings"
        ),
        "witness": "test:test_build_document_authority_metadata",
    }


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _blob(payload: bytes) -> str:
    header = b"blob " + str(len(payload)).encode("ascii") + b"\0"
    return hashlib.sha1(header + payload).hexdigest()


def _candidate_refs() -> list[dict[str, str]]:
    return [
        {
            "path": (
                tool.DEFAULT_STAGE_ROOT_REL / "candidates" / family / "candidate.v2.json"
            ).as_posix(),
            "sha256": str(index) * 64,
            "candidate_id": str(index + 1) * 64,
            "content_digest": str(index + 2) * 64,
            "family": family,
        }
        for index, family in enumerate(tool.FAMILIES, start=1)
    ]


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], dict[str, object]]:
    payloads = {"scope/a.txt": b"alpha\n", "scope/b.txt": b"beta"}
    for relative, payload in payloads.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    excluded = tmp_path / "scope/post.py"
    excluded.write_bytes(b"successor only\n")

    entries = []
    for index, (relative, _payload) in enumerate(sorted(payloads.items())):
        entries.append(
            {
                "path": relative,
                "kind": f"kind-{index}",
                "byte_hash_sha256": str(index + 7) * 64,
                "byte_hash_kind": "sha256_of_donor_working_tree_bytes",
                "git_blob_sha1_working_tree": str(index + 4) * 40,
                "bytes": index,
                "lines": index,
                "tracked_at_donor_head": index == 0,
                "reference_origins": [f"origin-{index}"],
            }
        )
    predecessor: dict[str, object] = {"entries": entries}
    legacy_gap: dict[str, object] = {"mapped": [{"donor_paths": ["scope"]}]}
    monkeypatch.setattr(tool, "_fixed_inputs", lambda root: (predecessor, legacy_gap))
    monkeypatch.setattr(tool, "EXPECTED_ENTRY_COUNT", 2)
    monkeypatch.setattr(
        tool,
        "KNOWN_SCOPE_EXCLUSIONS",
        {"scope/post.py": "successor-only implementation created after the frozen donor scope"},
    )
    monkeypatch.setattr(tool, "_check_stage_candidates", lambda root, stage: _candidate_refs())
    return predecessor, legacy_gap


def test_fixed_historical_inputs_match_repository_bytes() -> None:
    fixed = {
        tool.PREDECESSOR_REL: tool.PREDECESSOR_SHA256,
        tool.FREEZE_RECEIPT_REL: tool.FREEZE_RECEIPT_SHA256,
        **tool.SCOPE_INPUT_HASHES,
        tool.MOVEMENT_REL: tool.MOVEMENT_SHA256,
    }
    assert len(tool.SCOPE_INPUT_HASHES) == 3
    for relative, expected in fixed.items():
        assert _sha((ROOT / relative).read_bytes()) == expected


def test_frozen_predecessor_is_exactly_237_unique_sorted_paths() -> None:
    predecessor = json.loads((ROOT / tool.PREDECESSOR_REL).read_bytes())
    paths = [entry["path"] for entry in predecessor["entries"]]
    assert len(paths) == len(set(paths)) == 237
    assert paths == sorted(paths)


def test_build_rebinds_only_exact_bytes_and_records_scope_exclusion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor, _ = _fixture(tmp_path, monkeypatch)
    document = tool.build_document(tmp_path)

    assert document["schema"] == tool.SCHEMA
    assert document["status"] == tool.STATUS
    assert document["authoritative"] is False
    assert document["authority"] == tool.AUTHORITY
    assert all(value is False for value in document["authority"].values())
    assert document["limitations"] == list(tool.LIMITATIONS)
    assert document["entry_count"] == 2
    assert [item["family"] for item in document["stage0_candidates"]] == list(tool.FAMILIES)

    original = predecessor["entries"][0]  # type: ignore[index]
    rebound = document["entries"][0]
    payload = (tmp_path / "scope/a.txt").read_bytes()
    assert {key: rebound[key] for key in ("path", "kind", "reference_origins", "tracked_at_donor_head")} == {
        "path": original["path"],  # type: ignore[index]
        "kind": original["kind"],  # type: ignore[index]
        "reference_origins": original["reference_origins"],  # type: ignore[index]
        "tracked_at_donor_head": original["tracked_at_donor_head"],  # type: ignore[index]
    }
    assert rebound["predecessor_sha256"] == original["byte_hash_sha256"]  # type: ignore[index]
    assert rebound["current_sha256"] == _sha(payload)
    assert rebound["bytes"] == len(payload)
    assert rebound["lines"] == payload.count(b"\n")
    assert rebound["git_blob_oid"] == _blob(payload)
    assert document["exact_byte_method"]["git_object_format"] == "sha1"
    assert document["movement_inventory"] == {
        "path": tool.MOVEMENT_REL.as_posix(),
        "sha256": tool.MOVEMENT_SHA256,
        "semantic_fields_changed": False,
    }
    assert document["scope_exclusions"] == [
        {
            "path": "scope/post.py",
            "current_sha256": _sha(b"successor only\n"),
            "reason": "successor-only implementation created after the frozen donor scope",
        }
    ]
    assert document["content_digest"] == tool._content_digest(document)


def test_unknown_directory_expansion_extra_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    (tmp_path / "scope/unknown.py").write_text("unknown", encoding="utf-8")
    with pytest.raises(tool.ValidationError, match="unknown.py"):
        tool.build_document(tmp_path)


def test_missing_adjudicated_scope_exclusion_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    (tmp_path / "scope/post.py").unlink()
    with pytest.raises(tool.ValidationError, match="missing_known_exclusions"):
        tool.build_document(tmp_path)


def test_symlinked_frozen_source_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    (tmp_path / "scope/b.txt").unlink()
    (tmp_path / "scope/b.txt").symlink_to(tmp_path / "scope/a.txt")
    with pytest.raises(tool.ValidationError, match="symlink"):
        tool.build_document(tmp_path)


def test_live_candidate_checker_is_called_for_canonical_nine_family_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, Path, bool]] = []
    for family in tool.FAMILIES:
        path = tool.DEFAULT_STAGE_ROOT_REL / "candidates" / family / "candidate.v2.json"
        absolute = tmp_path / path
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_text(json.dumps({"content_digest": family.lower()}), encoding="utf-8")

    def fake_check(path: Path, *, repo_root: Path, history_only: bool) -> dict[str, str]:
        family = path.parts[-2]
        calls.append((path, repo_root, history_only))
        return {
            "candidate_id": family.lower() * 32,
            "family": family,
            "status": tool.CANDIDATE_LIVE_STATUS,
        }

    monkeypatch.setattr(tool, "check_candidate", fake_check)
    refs = tool._check_stage_candidates(tmp_path, tool.DEFAULT_STAGE_ROOT_REL)
    assert [item["family"] for item in refs] == list(tool.FAMILIES)
    assert [call[0].parts[-2] for call in calls] == list(tool.FAMILIES)
    assert all(call[1] == tmp_path and call[2] is False for call in calls)


def test_candidate_family_or_status_mismatch_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tool.DEFAULT_STAGE_ROOT_REL / "candidates/C2/candidate.v2.json"
    (tmp_path / first).parent.mkdir(parents=True)
    (tmp_path / first).write_text('{"content_digest":"x"}', encoding="utf-8")
    monkeypatch.setattr(
        tool,
        "check_candidate",
        lambda *args, **kwargs: {
            "candidate_id": "a" * 64,
            "family": "C3",
            "status": tool.CANDIDATE_LIVE_STATUS,
        },
    )
    with pytest.raises(tool.ValidationError, match="family/status mismatch"):
        tool._check_stage_candidates(tmp_path, tool.DEFAULT_STAGE_ROOT_REL)


def test_check_document_rejects_tamper_and_live_byte_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    document = tool.build_document(tmp_path)
    summary = tool.check_document(tmp_path, document)
    assert summary == {
        "schema": tool.SCHEMA,
        "status": tool.STATUS,
        "entry_count": 2,
        "candidate_count": 9,
        "content_digest": document["content_digest"],
    }

    tampered = json.loads(json.dumps(document))
    tampered["entries"][0]["kind"] = "changed"
    tampered["content_digest"] = tool._content_digest(tampered)
    with pytest.raises(tool.ValidationError, match="does not match"):
        tool.check_document(tmp_path, tampered)

    (tmp_path / "scope/a.txt").write_bytes(b"drift\n")
    with pytest.raises(tool.ValidationError, match="does not match"):
        tool.check_document(tmp_path, document)


def test_check_document_path_rejects_bad_digest_and_path_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    document = tool.build_document(tmp_path)
    relative = Path("out/aggregate.json")
    (tmp_path / relative).parent.mkdir()
    (tmp_path / relative).write_text(json.dumps(document), encoding="utf-8")
    assert tool.check_document(tmp_path, relative)["candidate_count"] == 9

    document["content_digest"] = "0" * 64
    (tmp_path / relative).write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(tool.ValidationError, match="content_digest"):
        tool.check_document(tmp_path, relative)
    with pytest.raises(tool.ValidationError, match="escapes repository root"):
        tool.check_document(tmp_path, "../aggregate.json")


def test_write_is_atomic_create_only_and_validates_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    document = tool.build_document(tmp_path)
    output = Path("artifacts/aggregate.json")
    target = tool.write_create_only(tmp_path, output, document)
    assert json.loads(target.read_bytes()) == document
    assert not list(target.parent.glob(f".{target.name}.*"))

    original = target.read_bytes()
    with pytest.raises(tool.ValidationError, match="already exists"):
        tool.write_create_only(tmp_path, output, document)
    assert target.read_bytes() == original

    bad = json.loads(json.dumps(document))
    bad["content_digest"] = "0" * 64
    with pytest.raises(tool.ValidationError, match="content_digest"):
        tool.write_create_only(tmp_path, "artifacts/bad.json", bad)
    assert not (tmp_path / "artifacts/bad.json").exists()


def test_write_rejects_symlink_parent_and_output_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    document = tool.build_document(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(tool.ValidationError, match="symlink|escapes"):
        tool.write_create_only(tmp_path, "linked/aggregate.json", document)
    with pytest.raises(tool.ValidationError, match="escapes repository root"):
        tool.write_create_only(tmp_path, "../aggregate.json", document)
    assert not (outside / "aggregate.json").exists()


def test_noncanonical_stage_root_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(tool.ValidationError, match="fresh canonical root"):
        tool._stage_relative(tmp_path, "other/stage-b23-2026-09-08")
