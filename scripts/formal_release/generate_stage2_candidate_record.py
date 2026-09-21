#!/usr/bin/env python3
# ruff: noqa: E402, TRY003, TRY301
"""Bind a Stage 2 exact candidate to non-authoritative closure evidence."""

from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.formal_release.check_candidate_identity import evaluate_candidate_identity
from scripts.formal_release.model import (
    CreateOnlyWriteError,
    DirectoryIdentity,
    Finding,
    PreflightReport,
    StableFileReadError,
    directory_identity,
    read_stable_regular_bytes,
    write_create_only_bytes,
)
from scripts.formal_release.stage2_candidate_intake import (
    GIT_OID,
    Stage2IntakeError,
    assert_stage0_closure_projection,
    canonical_json,
    git_output,
    git_text,
    sha256_bytes,
    validate_stage0_and_stage1_bindings,
    validate_manifest_structure,
    validate_manifest,
)
from scripts.formal_release.stage2_git_batch import (
    BaseTreeIndex,
    GitBatchError,
    parse_raw_diff_tree_z,
)

SCHEMA_VERSION = "mrw.stage2.exact-candidate-record.v1"
RECORD_ID = "stage2-exact-candidate-v1"
STATUS = "EXACT_CANDIDATE_ESTABLISHED_NOT_AUTHORITY"
CHECKER = "stage2-exact-candidate-record"
CANDIDATE_STRATEGY = "REMEDIATION_INCLUSIVE_RELEASE"
AUTHORITY_KEYS = ("release", "push", "deploy", "candidate_promotion", "authority_transfer")
CEILING = "PRODUCTION_RELEASE_NOT_AUTHORIZED"
COMMIT_HEADER_KEY = re.compile(rb"^[A-Za-z][A-Za-z0-9-]*$")


class Stage2RecordError(RuntimeError):
    """Raised when Stage 2 candidate evidence cannot be bound."""


GenerationError = Stage2RecordError
ValidationError = Stage2RecordError


def _git(repo_root: Path, *args: str) -> str:
    try:
        return git_text(repo_root, *args)
    except Stage2IntakeError as exc:
        raise Stage2RecordError(str(exc)) from exc


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    try:
        return git_output(repo_root, *args)
    except Stage2IntakeError as exc:
        raise Stage2RecordError(str(exc)) from exc


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = read_stable_regular_bytes(path, label=label)
        value = json.loads(raw)
    except (StableFileReadError, json.JSONDecodeError) as exc:
        raise Stage2RecordError(f"{label} is missing or invalid JSON") from exc
    if not isinstance(value, dict):
        raise Stage2RecordError(f"{label} JSON root must be an object")
    return value, raw


def _candidate_git_common_dir(repo_root: Path) -> Path:
    raw = _git(repo_root, "rev-parse", "--git-common-dir")
    if not raw or "\x00" in raw or "\n" in raw or "\r" in raw:
        raise Stage2RecordError("candidate git common-dir is invalid")
    common_dir = Path(raw)
    if not common_dir.is_absolute():
        common_dir = repo_root / common_dir
    try:
        resolved = common_dir.resolve(strict=True)
    except OSError as exc:
        raise Stage2RecordError("candidate git common-dir is missing") from exc
    if not resolved.is_dir():
        raise Stage2RecordError("candidate git common-dir is not a directory")
    return resolved


def _assert_no_candidate_grafts(repo_root: Path) -> None:
    grafts = _candidate_git_common_dir(repo_root) / "info" / "grafts"
    try:
        grafts_stat = grafts.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise Stage2RecordError("candidate git common-dir info/grafts is unreadable") from exc

    if stat.S_ISREG(grafts_stat.st_mode):
        raise Stage2RecordError("candidate git common-dir info/grafts file is forbidden")
    if stat.S_ISLNK(grafts_stat.st_mode):
        raise Stage2RecordError("candidate git common-dir info/grafts symlink is forbidden")
    if stat.S_ISDIR(grafts_stat.st_mode):
        try:
            if any(grafts.iterdir()):
                raise Stage2RecordError(
                    "candidate git common-dir info/grafts non-empty directory is forbidden"
                )
        except Stage2RecordError:
            raise
        except OSError as exc:
            raise Stage2RecordError(
                "candidate git common-dir info/grafts directory is unreadable"
            ) from exc
        return
    raise Stage2RecordError("candidate git common-dir info/grafts special file is forbidden")


def _raw_commit_tree_and_parents(repo_root: Path, commit_oid: str) -> tuple[str, list[str]]:
    raw = _git_bytes(repo_root, "cat-file", "commit", commit_oid)
    if b"\x00" in raw:
        raise Stage2RecordError("candidate raw commit header contains NUL")
    header, separator, _message = raw.partition(b"\n\n")
    if not separator or not header:
        raise Stage2RecordError("candidate raw commit header is malformed")

    fields: list[tuple[bytes, bytes]] = []
    previous_key: bytes | None = None
    for line in header.split(b"\n"):
        if line.startswith(b" "):
            if previous_key is None:
                raise Stage2RecordError("candidate raw commit header continuation is malformed")
            continue
        key, space, value = line.partition(b" ")
        if not space or not value or COMMIT_HEADER_KEY.fullmatch(key) is None:
            raise Stage2RecordError("candidate raw commit header field is malformed")
        fields.append((key, value))
        previous_key = key

    if fields[0][0] != b"tree":
        raise Stage2RecordError("candidate raw commit tree header is not first")
    trees = [value for key, value in fields if key == b"tree"]
    parents = [value for key, value in fields if key == b"parent"]

    def decode_oid(value: bytes, label: str) -> str:
        try:
            decoded = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise Stage2RecordError(f"candidate raw commit {label} header is invalid") from exc
        if GIT_OID.fullmatch(decoded) is None:
            raise Stage2RecordError(f"candidate raw commit {label} header is invalid")
        return decoded

    if len(trees) != 1:
        raise Stage2RecordError("candidate raw commit tree header is invalid")
    tree = decode_oid(trees[0], "tree")
    decoded_parents = [decode_oid(parent, "parent") for parent in parents]
    return tree, decoded_parents


def _assert_candidate_history(
    repo_root: Path,
    *,
    commit_oid: str,
    tree_oid: str,
    base_oid: str,
) -> None:
    raw_tree, raw_parents = _raw_commit_tree_and_parents(repo_root, commit_oid)
    if raw_tree != tree_oid:
        raise Stage2RecordError("candidate raw commit tree is not the bound candidate tree")
    if raw_parents != [base_oid]:
        raise Stage2RecordError("candidate raw commit parent is not exactly the manifest base")
    if _git(repo_root, "rev-list", "--count", f"{base_oid}..{commit_oid}") != "1":
        raise Stage2RecordError("candidate history is not exactly one remediation commit")


def _build_base_tree_index(
    source_root: Path,
    base_oid: str,
) -> Annotated[
    BaseTreeIndex,
    "kit:non-authoritative derived_as=view "
    "fact_source=git.base_tree "
    "witness=test:record_base_tree_index_is_constructed_once",
]:
    try:
        return BaseTreeIndex.from_repo(source_root, base_oid, runner=git_output)
    except GitBatchError as exc:
        raise Stage2RecordError(str(exc)) from exc


def _candidate_root_identity(repo_root: Path) -> tuple[Path, DirectoryIdentity]:
    requested_root = repo_root.resolve(strict=True)
    top_level = Path(_git(requested_root, "rev-parse", "--show-toplevel")).resolve(strict=True)
    if top_level != requested_root:
        raise Stage2RecordError(
            f"repo root must be the git checkout top-level: {top_level}"
        )
    return top_level, directory_identity(top_level)


def _assert_r1(repo_root: Path, commit: str, tree: str, r1_path: Path) -> dict[str, Any]:
    try:
        resolved_r1 = r1_path.resolve(strict=True)
    except OSError as exc:
        raise Stage2RecordError("R1 report is missing") from exc
    if not resolved_r1.is_file():
        raise Stage2RecordError("R1 report path is not a regular file")
    r1, raw = _read_json(resolved_r1, "R1 report")
    live = evaluate_candidate_identity(
        repo_root=repo_root,
        expected_commit=commit,
        expected_tree=tree,
        candidate_strategy=CANDIDATE_STRATEGY,
    )
    if live.status != "PASS":
        raise Stage2RecordError(f"live R1 candidate identity status is {live.status}")
    if live.to_dict() != r1 or r1.get("status") != "PASS":
        raise Stage2RecordError("R1 report bytes do not match live candidate identity")
    return {
        "path": str(resolved_r1),
        "sha256": sha256_bytes(raw),
        "status": "PASS",
        "schema_version": r1.get("schema_version"),
        "checker": r1.get("checker"),
    }


def _candidate_delta(
    repo_root: Path,
    base_oid: str,
    tree_oid: str,
) -> dict[str, dict[str, str]]:
    """Return the complete NUL-delimited raw tree delta."""
    try:
        parsed = parse_raw_diff_tree_z(
            _git_bytes(
                repo_root,
                "diff-tree",
                "-r",
                "--no-renames",
                "--raw",
                "--no-commit-id",
                "-z",
                base_oid,
                tree_oid,
            )
        )
    except GitBatchError as exc:
        raise Stage2RecordError(f"candidate raw delta is invalid: {exc}") from exc
    return {
        path: {
            "base_mode": row.base_mode,
            "base_blob": row.base_blob,
            "mode": row.mode,
            "blob": row.blob,
        }
        for path, row in parsed.items()
    }


def _assert_manifest_delta(
    repo_root: Path,
    base_oid: str,
    tree_oid: str,
    entries: list[dict[str, Any]],
) -> None:
    expected: dict[str, dict[str, str]] = {}
    expected_rows: list[dict[str, str]] = []
    for row in entries:
        path = row["path"]
        if row["operation"] == "DELETE":
            delta_row = {
                "base_mode": row["base_mode"],
                "base_blob": row["base_blob"],
                "mode": "000000",
                "blob": "",
            }
        else:
            delta_row = {
                "base_mode": row["base_mode"],
                "base_blob": row["base_blob"],
                "mode": row["mode"],
                "blob": row["blob"],
            }
            if (row["base_mode"], row["base_blob"]) == (row["mode"], row["blob"]):
                continue
        if path in expected:
            raise Stage2RecordError(f"manifest delta contains duplicate path: {path}")
        expected[path] = delta_row
        expected_rows.append({"path": path, **delta_row})

    observed = _candidate_delta(repo_root, base_oid, tree_oid)
    observed_rows = [{"path": path, **observed[path]} for path in sorted(observed)]
    expected_rows.sort(key=lambda row: row["path"])
    if observed != expected or observed_rows != expected_rows:
        raise Stage2RecordError("candidate raw delta is not exactly equal to manifest entries")


def _assert_source_identity(
    source: dict[str, Any],
    *,
    verify_cleanliness: bool = True,
) -> tuple[Path, DirectoryIdentity]:
    checkout = source.get("checkout")
    if not isinstance(checkout, str) or not checkout:
        raise Stage2RecordError("manifest source checkout is invalid")
    source_root = Path(checkout)
    if not source_root.is_absolute():
        raise Stage2RecordError("manifest source checkout must be absolute")
    try:
        source_identity = directory_identity(source_root)
    except OSError as exc:
        raise Stage2RecordError("manifest source checkout is missing") from exc
    if source_root.as_posix() != checkout:
        raise Stage2RecordError("manifest source checkout path is not canonical")
    expected_identity = (int(source.get("dev", -1)), int(source.get("ino", -1)))
    if source_identity != expected_identity:
        raise Stage2RecordError("manifest source checkout root identity drift")
    source_head = _git(source_root, "rev-parse", "HEAD")
    source_base = _git(source_root, "rev-parse", "--verify", source["base_ref"])
    source_remote = _git(source_root, "remote", "get-url", source["remote_name"])
    if (
        source_head != source["head"]
        or source_base != source["base_oid"]
        or source_remote != source["remote"]
    ):
        raise Stage2RecordError("manifest source git identity drift")
    if verify_cleanliness and "source_clean" in source and "porcelain_sha256" in source:
        porcelain = git_output(source_root, "status", "--porcelain=v1", "--untracked-files=all", "-z")
        if source["source_clean"] is not (porcelain == b"") or sha256_bytes(porcelain) != source["porcelain_sha256"]:
            raise Stage2RecordError("manifest source cleanliness drift")
    return source_root, source_identity


def build_record(
    *,
    repo_root: Path,
    source_root: Path,
    manifest_path: Path,
    r1_path: Path,
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=exact_candidate_record "
    "fact_source=candidate_intake_manifest+r1_report+git_tree "
    "witness=test:test_builds_create_only_record_outside_candidate",
]:
    repo_root = repo_root.resolve(strict=True)
    _assert_no_candidate_grafts(repo_root)
    requested_source_root = source_root
    manifest_path = manifest_path.resolve()
    manifest, manifest_raw = _read_json(manifest_path, "candidate intake manifest")
    try:
        validate_manifest_structure(manifest)
        source_root, source_identity = _assert_source_identity(
            manifest["source"],
            verify_cleanliness=False,
        )
        if requested_source_root.as_posix() != source_root.as_posix():
            raise Stage2RecordError("manifest source checkout binding drift")
        base_index = _build_base_tree_index(source_root, manifest["source"]["base_oid"])
        validate_manifest(manifest, base_index=base_index)
        validate_stage0_and_stage1_bindings(
            manifest,
            source_root,
            expected_identity=source_identity,
            base_index=base_index,
        )
    except Stage2IntakeError as exc:
        raise Stage2RecordError(str(exc)) from exc
    _assert_source_identity(manifest["source"], verify_cleanliness=True)
    source = manifest["source"]
    if source_root.as_posix() != source["checkout"]:
        raise Stage2RecordError("manifest source checkout binding drift")
    try:
        assert_stage0_closure_projection(
            manifest,
            source_root,
            expected_identity=source_identity,
            base_index=base_index,
        )
    except Stage2IntakeError as exc:
        raise Stage2RecordError(str(exc)) from exc
    source_head = _git(source_root, "rev-parse", "HEAD")
    source_base = _git(source_root, "rev-parse", "--verify", source["base_ref"])
    if source_head != source["head"] or source_base != source["base_oid"]:
        raise Stage2RecordError("manifest source git identity drift")
    source_remote = _git(source_root, "remote", "get-url", source["remote_name"])
    if source_remote != source["remote"]:
        raise Stage2RecordError("manifest source remote identity drift")

    commit = _git(repo_root, "rev-parse", "HEAD")
    tree = _git(repo_root, "rev-parse", "HEAD^{tree}")
    if GIT_OID.fullmatch(commit) is None or GIT_OID.fullmatch(tree) is None:
        raise Stage2RecordError("candidate oid is invalid")
    _assert_candidate_history(
        repo_root,
        commit_oid=commit,
        tree_oid=tree,
        base_oid=source["base_oid"],
    )
    _assert_manifest_delta(repo_root, source["base_oid"], tree, manifest["entries"])
    r1 = _assert_r1(repo_root, commit, tree, r1_path)
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "record_id": RECORD_ID,
        "status": STATUS,
        "authoritative": False,
        "authority": {key: False for key in AUTHORITY_KEYS},
        "authority_ceiling": CEILING,
        "bindings": {
            "candidate": {
                "commit": commit,
                "tree": tree,
                "parent": source["base_oid"],
                "strategy": CANDIDATE_STRATEGY,
            },
            "source": source,
            "intake": {
                "path": manifest_path.as_posix(),
                "sha256": sha256_bytes(manifest_raw),
            },
            "stage0_b23": manifest["stage0_b23"],
            "stage1": manifest["stage1"],
            "r1": r1,
        },
    }
    validate_record(repo_root, record, base_index=base_index)
    return record


def validate_record(
    repo_root: Path,
    record: Any,
    *,
    base_index: BaseTreeIndex | None = None,
) -> None:
    repo_root = repo_root.resolve(strict=True)
    _assert_no_candidate_grafts(repo_root)
    if not isinstance(record, dict):
        raise Stage2RecordError("record JSON root must be an object")
    expected_fields = {
        "schema_version",
        "record_id",
        "status",
        "authoritative",
        "authority",
        "authority_ceiling",
        "bindings",
    }
    if set(record) != expected_fields:
        raise Stage2RecordError("record field set drift")
    if (
        record["schema_version"] != SCHEMA_VERSION
        or record["record_id"] != RECORD_ID
        or record["status"] != STATUS
        or record["authoritative"] is not False
        or record["authority_ceiling"] != CEILING
    ):
        raise Stage2RecordError("record identity, status, or ceiling drift")
    authority = record["authority"]
    if not isinstance(authority, dict) or set(authority) != set(AUTHORITY_KEYS):
        raise Stage2RecordError("record authority key set drift")
    if any(authority[key] is not False for key in AUTHORITY_KEYS):
        raise Stage2RecordError("all Stage2 authority flags must be false")
    bindings = record["bindings"]
    if not isinstance(bindings, dict) or set(bindings) != {
        "candidate",
        "source",
        "intake",
        "stage0_b23",
        "stage1",
        "r1",
    }:
        raise Stage2RecordError("record binding field set drift")
    candidate = bindings["candidate"]
    source = bindings["source"]
    if not isinstance(source, dict):
        raise Stage2RecordError("record source binding is invalid")
    if (
        not isinstance(candidate, dict)
        or candidate.get("strategy") != CANDIDATE_STRATEGY
        or candidate.get("parent") != source.get("base_oid")
    ):
        raise Stage2RecordError("candidate strategy or parent binding drift")
    if any(
        not isinstance(candidate.get(key), str) or GIT_OID.fullmatch(candidate[key]) is None
        for key in ("commit", "tree", "parent")
    ):
        raise Stage2RecordError("candidate oid binding drift")
    if candidate.get("commit") != _git(repo_root, "rev-parse", "HEAD"):
        raise Stage2RecordError("candidate commit binding drift")
    if candidate.get("tree") != _git(repo_root, "rev-parse", "HEAD^{tree}"):
        raise Stage2RecordError("candidate tree binding drift")
    _assert_candidate_history(
        repo_root,
        commit_oid=candidate["commit"],
        tree_oid=candidate["tree"],
        base_oid=source["base_oid"],
    )
    r1 = bindings["r1"]
    if not isinstance(r1, dict) or set(r1) != {
        "path",
        "sha256",
        "status",
        "schema_version",
        "checker",
    }:
        raise Stage2RecordError("R1 binding field set drift")
    if r1.get("status") != "PASS":
        raise Stage2RecordError("R1 binding is not PASS")
    r1_path_raw = r1.get("path")
    if not isinstance(r1_path_raw, str) or not Path(r1_path_raw).is_absolute():
        raise Stage2RecordError("R1 binding path must be absolute")
    try:
        r1_path = Path(r1_path_raw).resolve(strict=True)
    except OSError as exc:
        raise Stage2RecordError("R1 report is missing") from exc
    if r1_path.as_posix() != r1_path_raw or not r1_path.is_file():
        raise Stage2RecordError("R1 binding path is not canonical")
    live_r1_binding = _assert_r1(
        repo_root,
        candidate["commit"],
        candidate["tree"],
        r1_path,
    )
    if live_r1_binding != r1:
        raise Stage2RecordError("R1 binding does not match receipt and live evaluation")
    intake_binding = bindings["intake"]
    if not isinstance(intake_binding, dict) or set(intake_binding) != {"path", "sha256"}:
        raise Stage2RecordError("candidate intake binding field set drift")
    intake_path_raw = intake_binding.get("path")
    if not isinstance(intake_path_raw, str) or not Path(intake_path_raw).is_absolute():
        raise Stage2RecordError("candidate intake path must be absolute")
    try:
        intake_path = Path(intake_path_raw)
        if intake_path.as_posix() != intake_path_raw:
            raise Stage2RecordError("candidate intake path is not canonical")
        intake_raw = read_stable_regular_bytes(
            intake_path,
            label="candidate intake manifest",
        )
    except (OSError, StableFileReadError) as exc:
        raise Stage2RecordError("candidate intake manifest is missing") from exc
    if sha256_bytes(intake_raw) != intake_binding.get("sha256"):
        raise Stage2RecordError("candidate intake digest drift")
    try:
        intake = json.loads(intake_raw)
    except json.JSONDecodeError as exc:
        raise Stage2RecordError("candidate intake manifest is invalid JSON") from exc
    try:
        validate_manifest_structure(intake)
    except Stage2IntakeError as exc:
        raise Stage2RecordError(str(exc)) from exc
    intake_source = intake["source"]
    if not isinstance(intake_source, dict) or not isinstance(intake_source.get("checkout"), str):
        raise Stage2RecordError("manifest source checkout is invalid")
    try:
        checkout_root = Path(intake_source["checkout"]).resolve(strict=True)
    except OSError as exc:
        raise Stage2RecordError("manifest source checkout is missing") from exc
    if checkout_root.as_posix() != intake_source["checkout"]:
        raise Stage2RecordError("manifest source checkout path is not canonical")
    try:
        if base_index is None:
            base_index = _build_base_tree_index(checkout_root, intake["source"]["base_oid"])
        validate_manifest(intake, base_index=base_index)
        validate_stage0_and_stage1_bindings(
            intake,
            checkout_root,
            base_index=base_index,
        )
    except Stage2IntakeError as exc:
        raise Stage2RecordError(str(exc)) from exc
    source_root, intake_source_identity = _assert_source_identity(
        intake["source"],
        verify_cleanliness=False,
    )
    try:
        assert_stage0_closure_projection(
            intake,
            source_root,
            expected_identity=intake_source_identity,
            base_index=base_index,
        )
        record_projection = {
            **intake,
            "stage0_b23": bindings["stage0_b23"],
            "stage1": bindings["stage1"],
        }
        validate_manifest(record_projection, base_index=base_index)
        assert_stage0_closure_projection(
            record_projection,
            source_root,
            expected_identity=intake_source_identity,
            base_index=base_index,
        )
    except Stage2IntakeError as exc:
        raise Stage2RecordError(str(exc)) from exc
    if source_root == repo_root:
        raise Stage2RecordError("manifest source checkout must differ from candidate")
    if source != intake["source"]:
        raise Stage2RecordError("record source binding does not match intake")
    if bindings["stage0_b23"] != intake["stage0_b23"] or bindings["stage1"] != intake["stage1"]:
        raise Stage2RecordError("record Stage0 or Stage1 binding does not match intake")
    _assert_manifest_delta(repo_root, source["base_oid"], candidate["tree"], intake["entries"])


def _assert_no_symlink_ancestors(path: Path) -> None:
    current = path.absolute()
    candidate = Path(current.anchor)
    for part in current.parts[1:]:
        candidate /= part
        try:
            mode = candidate.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise Stage2RecordError("record output parent contains a symlink")


def write_create_only(repo_root: Path, record: dict[str, Any], output: Path) -> Path:
    repo_root, candidate_identity = _candidate_root_identity(repo_root)
    destination = output.absolute()
    try:
        source = record["bindings"]["source"]
        source_checkout_raw = source["checkout"]
        if not isinstance(source_checkout_raw, str) or not Path(source_checkout_raw).is_absolute():
            raise ValueError("source checkout must be absolute")
        source_checkout = Path(source_checkout_raw)
        if source_checkout.as_posix() != source_checkout_raw:
            raise ValueError("source checkout path is not canonical")
        source_identity = (int(source["dev"]), int(source["ino"]))
        if directory_identity(source_checkout) != source_identity:
            raise ValueError("source checkout root identity drift")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise Stage2RecordError("record source checkout is invalid") from exc
    _assert_no_symlink_ancestors(destination.parent)
    resolved_destination = destination.resolve(strict=False)
    if resolved_destination.is_relative_to(repo_root) or resolved_destination.is_relative_to(source_checkout):
        raise Stage2RecordError("Stage2 record must be created outside the candidate")
    if destination.exists() or destination.is_symlink():
        raise Stage2RecordError(f"create-only target already exists: {resolved_destination}")
    try:
        return write_create_only_bytes(
            destination,
            canonical_json(record) + b"\n",
            (candidate_identity, source_identity),
        )
    except CreateOnlyWriteError as exc:
        raise Stage2RecordError(str(exc)) from exc


def _failure_report(message: str) -> PreflightReport:
    return PreflightReport(CHECKER, (Finding("stage2_exact_candidate_record", "FAIL", message),))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--r1", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        record = build_record(
            repo_root=args.repo_root,
            source_root=args.source_root,
            manifest_path=args.manifest,
            r1_path=args.r1,
        )
        write_create_only(args.repo_root, record, args.output)
    except (Stage2RecordError, Stage2IntakeError, OSError) as exc:
        print(_failure_report(str(exc)).to_json(), end="")
        return 1
    print(json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
