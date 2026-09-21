from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from scripts.formal_release.model import (
    CreateOnlyWriteError,
    StableFileReadError,
    Finding,
    PreflightReport,
    aggregate_status,
    directory_identity,
    read_stable_regular_bytes,
    write_create_only_bytes,
)


def test_INVARIANT__preflight_report_is_non_authoritative() -> None:
    report = PreflightReport(
        checker="candidate-identity",
        findings=(Finding("candidate.commit", "PASS", "commit matches"),),
    )

    payload = report.to_dict()

    assert payload["authoritative"] is False
    assert payload["derived_as"] == "preflight"
    assert payload["status"] == "PASS"


def test_DETERMINISM__same_report_has_same_json_bytes() -> None:
    report = PreflightReport(
        checker="release-evidence",
        findings=(
            Finding("manifest.schema", "PASS", "schema matches", ("manifest.json",)),
            Finding("manifest.authority", "BLOCKED", "authority is absent"),
        ),
    )

    assert report.to_json().encode("utf-8") == report.to_json().encode("utf-8")


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (("PASS", "PASS"), "PASS"),
        (("PASS", "UNEXECUTED"), "UNEXECUTED"),
        (("UNEXECUTED", "BLOCKED"), "BLOCKED"),
        (("BLOCKED", "FAIL"), "FAIL"),
    ],
)
def test_INVARIANT__aggregate_preserves_highest_severity(
    statuses: tuple[str, ...], expected: str
) -> None:
    findings = tuple(
        Finding(f"check.{index}", status, f"status {status}")  # type: ignore[arg-type]
        for index, status in enumerate(statuses)
    )

    assert aggregate_status(findings) == expected


def test_INVARIANT__empty_report_is_unexecuted() -> None:
    assert PreflightReport(checker="empty", findings=()).status == "UNEXECUTED"


def test_INVARIANT__status_vocabulary_is_closed() -> None:
    with pytest.raises(ValueError, match="unknown preflight status"):
        Finding("bad.status", "UNKNOWN", "invalid")  # type: ignore[arg-type]


def test_INVARIANT__finding_ids_are_unique() -> None:
    with pytest.raises(ValueError, match="must be unique"):
        PreflightReport(
            checker="duplicates",
            findings=(
                Finding("same", "PASS", "first"),
                Finding("same", "FAIL", "second"),
            ),
        )


def test_INVARIANT__report_is_immutable() -> None:
    report = PreflightReport(checker="immutable", findings=())

    with pytest.raises(FrozenInstanceError):
        report.checker = "changed"  # type: ignore[misc]


def test_create_only_writer_detects_parent_replacement_after_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    parent = tmp_path / "receipt"
    parent.mkdir()
    moved = tmp_path / "receipt-original"
    destination = parent / "result.json"
    original_open = os.open
    swapped = False

    def swap_after_create(
        path: os.PathLike[str] | str,
        flags: int,
        *args: object,
        **kwargs: object,
    ) -> int:
        nonlocal swapped
        descriptor = original_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
        if flags & os.O_CREAT and Path(path).name == destination.name and not swapped:
            swapped = True
            parent.rename(moved)
            parent.mkdir()
        return descriptor

    monkeypatch.setattr(os, "open", swap_after_create)
    with pytest.raises(CreateOnlyWriteError, match="unsafe|changed"):
        write_create_only_bytes(destination, b"payload\n")

    assert not destination.exists()
    assert not (moved / destination.name).exists()


def test_create_only_writer_rejects_forbidden_ancestor_before_creation(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    output_parent = tmp_path / "receipt"
    output_parent.mkdir()
    destination = output_parent / "result.json"
    forbidden = directory_identity(checkout)

    checkout.rename(output_parent)

    with pytest.raises(
        CreateOnlyWriteError,
        match="ancestor entered a forbidden checkout",
    ):
        write_create_only_bytes(destination, b"payload\n", (forbidden,))

    assert not destination.exists()


def test_create_only_writer_cleans_forbidden_ancestor_after_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    output_parent = tmp_path / "receipt"
    output_parent.mkdir()
    destination = output_parent / "result.json"
    moved_parent = checkout / "receipt"
    forbidden = directory_identity(checkout)
    original_write = os.write

    def move_parent_during_write(fd: int, payload: bytes) -> int:
        result = original_write(fd, payload)
        if not moved_parent.exists():
            output_parent.rename(moved_parent)
        return result

    monkeypatch.setattr(os, "write", move_parent_during_write)
    with pytest.raises(
        CreateOnlyWriteError,
        match="ancestor entered a forbidden checkout",
    ):
        write_create_only_bytes(destination, b"payload\n", (forbidden,))

    assert not destination.exists()
    assert not (moved_parent / destination.name).exists()


def test_stable_reader_fails_fast_on_fifo(tmp_path: Path) -> None:
    destination = tmp_path / "input"
    os.mkfifo(destination)

    with pytest.raises(StableFileReadError, match="regular file \\(FIFO\\)"):
        read_stable_regular_bytes(destination, label="stable input")


def test_stable_reader_rejects_final_symlink(tmp_path: Path) -> None:
    regular = tmp_path / "regular"
    regular.write_bytes(b"payload\n")
    destination = tmp_path / "link"
    destination.symlink_to(regular)

    with pytest.raises(StableFileReadError, match="cannot be read safely"):
        read_stable_regular_bytes(destination, label="stable input")


def test_stable_reader_detects_parent_replacement_during_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    destination = parent / "input"
    destination.write_bytes(b"payload\n")
    moved = tmp_path / "parent-original"
    replacement = tmp_path / "parent-replacement"
    replacement.mkdir()
    original_read = os.read
    replaced = False

    def replace_parent_after_first_read(fd: int, size: int) -> bytes:
        nonlocal replaced
        chunk = original_read(fd, size)
        if not replaced:
            replaced = True
            parent.rename(moved)
            replacement.rename(parent)
        return chunk

    monkeypatch.setattr(os, "read", replace_parent_after_first_read)
    with pytest.raises(StableFileReadError, match="changed during read|cannot be read safely"):
        read_stable_regular_bytes(destination, label="stable input")
