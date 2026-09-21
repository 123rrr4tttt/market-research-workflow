from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from scripts.formal_release import stage2_git_batch as tool
from scripts.formal_release.stage2_git_batch import (
    BaseTreeIndex,
    BoundedReadOnlyCache,
    GitBatchError,
    parse_raw_diff_tree_z,
    make_intake_cache_key,
    git_blob_oid,
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ("git", "-C", str(repo), *args),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def initialized_repo(repo: Path) -> tuple[Path, str]:
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Stage 2 Test")
    git(repo, "config", "user.email", "stage2-test@localhost")
    (repo / "tracked.txt").write_text("original\n", encoding="utf-8")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-m", "original")
    return repo, git(repo, "rev-parse", "HEAD")


def test_blob_oid_matches_git_hash_object(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(("git", "-C", str(repo), "init"), check=True, capture_output=True)
    payload = b"hello\x00world\n"
    expected = subprocess.run(
        ("git", "-C", str(repo), "hash-object", "--stdin"),
        input=payload,
        check=True,
        capture_output=True,
    ).stdout.decode().strip()
    assert git_blob_oid(payload) == expected
    assert git_blob_oid(payload) == hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def test_base_tree_index_parses_once_and_rejects_selected_tree(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []
    output = (
        b"100644 blob " + b"a" * 40 + b"\tfile.txt\0"
        b"040000 tree " + b"b" * 40 + b"\tdir\0"
    )

    def runner(_root: Path, *args: str) -> bytes:
        calls.append(args)
        if args == ("rev-parse", "--show-object-format"):
            return b"sha1\n"
        assert args == ("ls-tree", "-r", "-z", "--full-tree", "a" * 40)
        return output

    index = BaseTreeIndex(tmp_path, "a" * 40, runner=runner)
    assert index.lookup("file.txt").oid == "a" * 40
    with pytest.raises(GitBatchError, match="unsupported base tree entry"):
        index.lookup("dir")
    assert sum(command[0] == "ls-tree" for command in calls) == 1


def test_default_base_tree_runner_closes_git_configuration_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def fake_run(
        command: tuple[str, ...],
        *,
        check: bool,
        capture_output: bool,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[bytes]:
        assert check is False
        assert capture_output is True
        calls.append((command, env))
        stdout = b"sha1\n" if command[-2:] == ("rev-parse", "--show-object-format") else b""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "other.git"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "poison.config"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "url.https://safe.test/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "https://evil.test/")
    monkeypatch.setattr(tool.subprocess, "run", fake_run)

    index = BaseTreeIndex(tmp_path, "a" * 40)

    assert len(index) == 0
    assert len(calls) == 2
    for command, environment in calls:
        assert command[:6] == (
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-C",
        )
        assert {
            key for key in environment if key.startswith("GIT_")
        } == {
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_NO_REPLACE_OBJECTS",
        }
        assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
        assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
        assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"


def test_default_runner_blocks_home_xdg_and_local_fsmonitor_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo, base = initialized_repo(tmp_path / "repo")
    git(repo, "remote", "add", "origin", "https://safe.test/source.git")
    (repo / ".gitattributes").write_text("tracked.txt filter=poison\n", encoding="utf-8")
    git(repo, "add", ".gitattributes")
    git(repo, "commit", "-m", "attributes")
    base = git(repo, "rev-parse", "HEAD")

    marker = tmp_path / "git-config-side-effect"
    fsmonitor = tmp_path / "fsmonitor"
    fsmonitor.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n", encoding="utf-8")
    fsmonitor.chmod(0o755)
    filter_driver = tmp_path / "filter-driver"
    filter_driver.write_text(f"#!/bin/sh\ntouch '{marker}'\ncat\n", encoding="utf-8")
    filter_driver.chmod(0o755)
    git(repo, "config", "core.fsmonitor", str(fsmonitor))

    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    hooks = tmp_path / "hooks"
    home.mkdir()
    (xdg / "git").mkdir(parents=True)
    hooks.mkdir()
    (home / ".gitconfig").write_text(
        '[url "https://evil.test/"]\n'
        "\tinsteadOf = https://safe.test/\n"
        "[core]\n"
        f"\thooksPath = {hooks}\n",
        encoding="utf-8",
    )
    (xdg / "git/config").write_text(
        '[filter "poison"]\n'
        f"\tsmudge = {filter_driver}\n"
        "\trequired = true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

    index = BaseTreeIndex(repo, base)
    status = tool._run_git(repo, "status", "--porcelain=v1")
    filtered = tool._run_git(repo, "cat-file", "--filters", f"{base}:tracked.txt")
    remote = tool._run_git(repo, "remote", "get-url", "origin")

    assert index.lookup("tracked.txt") is not None
    assert status == b""
    assert filtered == b"original\n"
    assert remote == b"https://safe.test/source.git\n"
    assert not marker.exists()


def test_default_base_tree_runner_ignores_replace_refs(tmp_path: Path) -> None:
    repo, original = initialized_repo(tmp_path / "repo")
    (repo / "tracked.txt").unlink()
    (repo / "replacement.txt").write_text("replacement\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "replacement")
    replacement = git(repo, "rev-parse", "HEAD")
    git(repo, "replace", original, replacement)

    index = BaseTreeIndex(repo, original)

    assert index.lookup("tracked.txt") is not None
    assert index.lookup("replacement.txt") is None


@pytest.mark.parametrize(
    "payload",
    [b"100644 blob nope\tfile\0", b"100644 blob " + b"a" * 40 + b" file\0", b"100644 blob " + b"a" * 40 + b"\tfile"],
)
def test_base_tree_parser_fails_closed(payload: bytes) -> None:
    with pytest.raises(GitBatchError):
        BaseTreeIndex.parse(payload)


def test_raw_diff_tree_parser_is_canonical() -> None:
    oid = "a" * 40
    payload = (
            f":000000 100644 0000000000000000000000000000000000000000 {oid} A\0x.txt\0"
            f":100755 100755 {oid} {oid} M\0y.txt\0"
            f":100644 120000 {oid} {oid} T\0z.txt\0"
            f":100644 000000 {oid} 0000000000000000000000000000000000000000 D\0gone.txt\0"
    ).encode()
    parsed = parse_raw_diff_tree_z(payload)
    assert set(parsed) == {"x.txt", "y.txt", "z.txt", "gone.txt"}
    assert parsed["x.txt"].base_blob == ""
    assert parsed["gone.txt"].blob == ""
    assert parse_raw_diff_tree_z(b"") == {}


@pytest.mark.parametrize(
    "payload",
    [
        b":100644 100644 " + b"a" * 40 + b" " + b"a" * 40 + b" M\tx",
        b":100644 100644 " + b"a" * 40 + b" " + b"a" * 40 + b" M\tx\0y\0",
        b":100644 100644 " + b"a" * 40 + b" " + b"a" * 40 + b" M\tx\0x.txt\0"
        b":100644 100644 " + b"a" * 40 + b" " + b"a" * 40 + b" M\tx\0x.txt\0",
        b":100644 100644 " + b"a" * 40 + b" " + b"a" * 40 + b" M\tx.txt\0x.txt\0",
        b":100644 100644 " + b"a" * 40 + b" " + b"a" * 40 + b" R\tx\0y\0",
        b":100644 000000 " + b"a" * 40 + b" " + b"a" * 40 + b" D\tx.txt\0",
        b":100644 000000 " + b"a" * 40 + b" " + b"a" * 40 + b" D\tx.txt\0",
        b":000000 100644 0000000000000000000000000000000000000000 " + b"a" * 40 + b" A\tx.txt\0"
        b":000000 100644 0000000000000000000000000000000000000000 " + b"a" * 40 + b" A\tx.txt\0",
    ],
)
def test_raw_diff_tree_parser_fails_closed(payload: bytes) -> None:
    with pytest.raises(GitBatchError):
        parse_raw_diff_tree_z(payload)


def test_cache_is_bounded_and_key_dimensions_drift() -> None:
    key_fields = dict(
        schema="schema",
        resolved_source="/repo",
        dev=1,
        ino=2,
        head="h",
        porcelain_sha256="p",
        canonical_manifest_sha256="m",
        base_oid="b",
        object_format="sha1",
    )
    key = make_intake_cache_key(**key_fields)
    cache = BoundedReadOnlyCache(max_entries=1)
    cache.put(key, "value")
    assert cache.get(key) == "value"
    assert make_intake_cache_key(**{**key_fields, "head": "other"}) != key
    assert len(cache) == 1
