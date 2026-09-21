from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from app.release_identity import (
    RELEASE_BUILD_COMMIT_ENV,
    RELEASE_BUILD_DIGEST_ENV,
    RELEASE_BUILD_TREE_ENV,
    RELEASE_VERSION,
    read_build_identity,
)


pytestmark = pytest.mark.unit

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent.parent


def test_canonical_release_version_is_stable() -> None:
    assert RELEASE_VERSION == "1.0.0"


def test_reader_preserves_explicit_build_coordinates() -> None:
    identity = read_build_identity(
        {
            RELEASE_BUILD_COMMIT_ENV: "0123456789abcdef",
            RELEASE_BUILD_TREE_ENV: "fedcba9876543210",
            RELEASE_BUILD_DIGEST_ENV: "sha256:00112233445566778899aabbccddeeff",
        }
    )

    assert identity.version == RELEASE_VERSION
    assert identity.commit == "0123456789abcdef"
    assert identity.tree == "fedcba9876543210"
    assert identity.digest == "sha256:00112233445566778899aabbccddeeff"
    assert identity.fully_bound


@pytest.mark.parametrize(
    ("commit", "tree", "digest"),
    [
        (None, None, None),
        ("", None, None),
        ("commit", "  ", "digest"),
    ],
)
def test_reader_does_not_invent_missing_build_coordinates(
    commit: str | None,
    tree: str | None,
    digest: str | None,
) -> None:
    env = {
        RELEASE_BUILD_COMMIT_ENV: commit,
        RELEASE_BUILD_TREE_ENV: tree,
        RELEASE_BUILD_DIGEST_ENV: digest,
    }
    def normalized(value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    identity = read_build_identity(env)

    assert identity.version == RELEASE_VERSION
    assert identity.commit == normalized(commit)
    assert identity.tree == normalized(tree)
    assert identity.digest == normalized(digest)
    assert not identity.fully_bound


def test_release_files_use_canonical_version() -> None:
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text())
    package = json.loads(
        (REPOSITORY_ROOT / "main/frontend-modern/package.json").read_text()
    )

    assert pyproject["project"]["version"] == RELEASE_VERSION
    assert package["version"] == RELEASE_VERSION


def test_lock_importers_match_frontend_dependency_contract() -> None:
    ruby = shutil.which("ruby")
    if ruby is None:
        pytest.skip("Ruby YAML parser is unavailable")

    result = subprocess.run(
        [
            ruby,
            "-ryaml",
            "-rjson",
            "-e",
            'print JSON.generate(YAML.safe_load(File.read(ARGV.fetch(0)), aliases: true))',
            str(REPOSITORY_ROOT / "main/frontend-modern/pnpm-lock.yaml"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    lock = json.loads(result.stdout)
    package = json.loads(
        (REPOSITORY_ROOT / "main/frontend-modern/package.json").read_text()
    )
    importer = lock["importers"]["."]

    assert lock["lockfileVersion"] == "9.0"
    assert package["version"] == RELEASE_VERSION
    for dependency_kind in ("dependencies", "devDependencies"):
        for name, requirement in package[dependency_kind].items():
            assert importer[dependency_kind][name]["specifier"] == requirement
