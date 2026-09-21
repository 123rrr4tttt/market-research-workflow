#!/usr/bin/env python3
"""Focused tests for the single functorial-kit dependency audit adapter."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "formal_release" / "check_functorial_kit_dependency_audit.py"
SPEC = importlib.util.spec_from_file_location("check_functorial_kit_dependency_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def pyproject(requirement: str = audit.EXPECTED_REQUIREMENT, *, extra: str = "") -> bytes:
    suffix = f', "{extra}"' if extra else ""
    return f'[project]\ndependencies = ["{requirement}"{suffix}]\n'.encode()


class FakeDistribution:
    def __init__(
        self,
        root: Path,
        *,
        direct_url: dict[str, object] | None = None,
        version: str = audit.EXPECTED_VERSION,
        requirements: list[str] | None = None,
    ) -> None:
        self.metadata = {"Name": audit.EXPECTED_NAME}
        self.version = version
        self.requires = requirements
        self._root = root
        self._direct_url = direct_url or {
            "url": audit.EXPECTED_GIT_URL,
            "vcs_info": {
                "vcs": "git",
                "commit_id": audit.EXPECTED_COMMIT,
                "requested_revision": audit.EXPECTED_COMMIT,
            },
            "subdirectory": audit.EXPECTED_SUBDIRECTORY,
        }
        (root / "functorial_kit").mkdir(parents=True)

    def read_text(self, filename: str) -> str | None:
        if filename != "direct_url.json":
            return None
        return json.dumps(self._direct_url)

    def locate_file(self, filename: str) -> Path:
        return self._root / filename


def test_classification_emits_only_public_pypi_requirements() -> None:
    source = f"fastapi==0.133.0\n{audit.EXPECTED_REQUIREMENT}\nrequests==2.33.0\n"
    assert audit.classify_declarations(source, pyproject()) == "fastapi==0.133.0\nrequests==2.33.0\n"


def test_classification_rejects_requirement_declaration_mismatch() -> None:
    source = f"fastapi==0.133.0\n{audit.EXPECTED_REQUIREMENT.replace('functorial-kit', 'other-kit', 1)}\n"
    with pytest.raises(audit.AuditContractError, match="exactly one direct URL"):
        audit.classify_declarations(source, pyproject())


def test_classification_rejects_commit_mismatch() -> None:
    changed = audit.EXPECTED_REQUIREMENT.replace(audit.EXPECTED_COMMIT, "0" * 40)
    with pytest.raises(audit.AuditContractError, match="exactly one direct URL"):
        audit.classify_declarations(f"fastapi==0.133.0\n{changed}\n", pyproject(changed))


def test_classification_rejects_additional_vcs_dependency() -> None:
    extra = "other-kit @ git+https://example.invalid/other-kit.git@" + "1" * 40
    source = f"fastapi==0.133.0\n{audit.EXPECTED_REQUIREMENT}\n{extra}\n"
    with pytest.raises(audit.AuditContractError, match="exactly one direct URL"):
        audit.classify_declarations(source, pyproject())


@pytest.mark.parametrize(
    "extra",
    (
        "other-kit @ https://example.invalid/other.whl",
        "other-kit @ file:///private/tmp/other.whl",
        "https://example.invalid/other.whl",
        "../other-package",
        "git+https://example.invalid/other.git#egg=other-kit",
        "-r other-requirements.txt",
        "-c constraints.txt",
        "-e ../other-package",
        "--index-url https://example.invalid/simple",
        "--find-links https://example.invalid/wheels",
    ),
)
def test_classification_rejects_every_unapproved_requirement_source(extra: str) -> None:
    source = f"fastapi==0.133.0\n{audit.EXPECTED_REQUIREMENT}\n{extra}\n"
    with pytest.raises(audit.AuditContractError):
        audit.classify_declarations(source, pyproject())


def test_pyproject_public_dependency_enters_projection() -> None:
    source = f"fastapi==0.133.0\n{audit.EXPECTED_REQUIREMENT}\n"
    assert audit.classify_declarations(
        source, pyproject(extra="requests==2.33.0")
    ) == "fastapi==0.133.0\nrequests==2.33.0\n"


def test_pyproject_public_dependency_already_in_backend_is_not_duplicated() -> None:
    source = f"requests==2.33.0\n{audit.EXPECTED_REQUIREMENT}\n"
    assert audit.classify_declarations(
        source, pyproject(extra="requests==2.33.0")
    ) == "requests==2.33.0\n"


@pytest.mark.parametrize(
    "extra",
    (
        "other-kit @ https://example.invalid/other.whl",
        "other-kit @ file:///private/tmp/other.whl",
        "../other-package",
    ),
)
def test_pyproject_rejects_every_unapproved_requirement_source(extra: str) -> None:
    source = f"fastapi==0.133.0\n{audit.EXPECTED_REQUIREMENT}\n"
    with pytest.raises(audit.AuditContractError):
        audit.classify_declarations(source, pyproject(extra=extra))


def test_installed_identity_accepts_exact_direct_url_and_optional_only_dependencies(tmp_path: Path) -> None:
    distribution = FakeDistribution(
        tmp_path,
        requirements=['hypothesis>=6; extra == "laws"', 'pytest>=8; extra == "dev"'],
    )
    installed = audit.inspect_installed_dependency(distribution)
    assert installed.package_root == (tmp_path / "functorial_kit").resolve()
    assert installed.active_runtime_requirements == ()
    assert installed.direct_url["vcs_info"]["commit_id"] == audit.EXPECTED_COMMIT


def test_installed_identity_rejects_direct_url_commit_mismatch(tmp_path: Path) -> None:
    direct_url = {
        "url": audit.EXPECTED_GIT_URL,
        "vcs_info": {
            "vcs": "git",
            "commit_id": "0" * 40,
            "requested_revision": audit.EXPECTED_COMMIT,
        },
        "subdirectory": audit.EXPECTED_SUBDIRECTORY,
    }
    with pytest.raises(audit.AuditContractError, match="VCS identity mismatch"):
        audit.inspect_installed_dependency(FakeDistribution(tmp_path, direct_url=direct_url))


def test_installed_public_runtime_dependency_enters_strict_projection(tmp_path: Path) -> None:
    installed = audit.inspect_installed_dependency(
        FakeDistribution(tmp_path, requirements=["requests>=2", 'pytest>=8; extra == "dev"'])
    )
    projection, additions = audit.extend_public_projection(
        "fastapi==0.133.0\n", installed.active_runtime_requirements
    )
    assert additions == ("requests>=2",)
    assert projection == "fastapi==0.133.0\nrequests>=2\n"


def test_installed_public_runtime_dependency_already_present_is_not_duplicated(tmp_path: Path) -> None:
    installed = audit.inspect_installed_dependency(
        FakeDistribution(tmp_path, requirements=["requests>=2"])
    )
    projection, additions = audit.extend_public_projection(
        "fastapi==0.133.0\nrequests>=2\n", installed.active_runtime_requirements
    )
    assert additions == ()
    assert projection == "fastapi==0.133.0\nrequests>=2\n"


def test_installed_runtime_direct_url_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(audit.AuditContractError, match="active runtime direct URL"):
        audit.inspect_installed_dependency(
            FakeDistribution(
                tmp_path,
                requirements=["other-kit @ https://example.invalid/other.whl"],
            )
        )


def test_installed_direct_url_root_must_be_an_object(tmp_path: Path) -> None:
    distribution = FakeDistribution(tmp_path)
    distribution._direct_url = [audit.EXPECTED_GIT_URL]  # type: ignore[assignment]
    with pytest.raises(audit.AuditContractError, match="root must be an object") as raised:
        audit.inspect_installed_dependency(distribution)
    assert raised.value.evidence == {"installed_direct_url": [audit.EXPECTED_GIT_URL]}


def test_manifest_identity_accepts_exact_values_and_rejects_drift(tmp_path: Path) -> None:
    path = tmp_path / "consumer-gate.manifest.json"
    payload = {
        "base": {
            "git_commit": audit.EXPECTED_COMMIT,
            "git_tree": audit.EXPECTED_REPOSITORY_TREE,
        },
        "runtime_identity": {
            "pyproject_runtime_dependency": audit.EXPECTED_REQUIREMENT,
            "pyproject_runtime_pin_modified": False,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert audit.inspect_consumer_gate_manifest(path).repository_tree == audit.EXPECTED_REPOSITORY_TREE
    payload["base"]["git_tree"] = "0" * 40
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(audit.AuditContractError, match="repository tree mismatch"):
        audit.inspect_consumer_gate_manifest(path)


@pytest.mark.parametrize(
    ("section", "key", "changed", "message"),
    (
        ("base", "git_commit", "0" * 40, "commit mismatch"),
        (
            "runtime_identity",
            "pyproject_runtime_dependency",
            "other-kit==1",
            "runtime requirement mismatch",
        ),
        (
            "runtime_identity",
            "pyproject_runtime_pin_modified",
            True,
            "pyproject_runtime_pin_modified=false",
        ),
    ),
)
def test_manifest_identity_rejects_commit_and_runtime_drift(
    tmp_path: Path, section: str, key: str, changed: object, message: str
) -> None:
    path = tmp_path / "consumer-gate.manifest.json"
    payload = {
        "base": {
            "git_commit": audit.EXPECTED_COMMIT,
            "git_tree": audit.EXPECTED_REPOSITORY_TREE,
        },
        "runtime_identity": {
            "pyproject_runtime_dependency": audit.EXPECTED_REQUIREMENT,
            "pyproject_runtime_pin_modified": False,
        },
    }
    payload[section][key] = changed
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(audit.AuditContractError, match=message):
        audit.inspect_consumer_gate_manifest(path)


def test_source_identity_reads_fixed_git_objects_not_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob_id = "1" * 40

    def fake_git(_checkout: Path, *arguments: str) -> bytes:
        replies = {
            ("remote", "get-url", "origin"): audit.EXPECTED_GIT_URL.removesuffix(".git").encode(),
            ("rev-parse", "HEAD"): audit.EXPECTED_COMMIT.encode(),
            ("rev-parse", "HEAD^{tree}"): audit.EXPECTED_REPOSITORY_TREE.encode(),
            ("rev-parse", "HEAD:python"): audit.EXPECTED_PYTHON_SUBTREE.encode(),
            ("ls-tree", "-r", "-z", "HEAD", "--", "python/functorial_kit"): (
                f"100644 blob {blob_id}\tpython/functorial_kit/__init__.py\0".encode()
            ),
            ("cat-file", "blob", blob_id): b"fixed object bytes\n",
        }
        return replies[arguments]

    monkeypatch.setattr(audit, "_run_git", fake_git)
    source = audit.inspect_source_checkout(tmp_path)
    assert source.commit == audit.EXPECTED_COMMIT
    assert source.package_files[0]["path"] == "functorial_kit/__init__.py"


def test_source_identity_rejects_python_subtree_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_git(_checkout: Path, *arguments: str) -> bytes:
        replies = {
            ("remote", "get-url", "origin"): audit.EXPECTED_GIT_URL.encode(),
            ("rev-parse", "HEAD"): audit.EXPECTED_COMMIT.encode(),
            ("rev-parse", "HEAD^{tree}"): audit.EXPECTED_REPOSITORY_TREE.encode(),
            ("rev-parse", "HEAD:python"): b"0" * 40,
        }
        return replies[arguments]

    monkeypatch.setattr(audit, "_run_git", fake_git)
    with pytest.raises(audit.AuditContractError, match="python subtree mismatch"):
        audit.inspect_source_checkout(tmp_path)


def test_installed_manifest_rejects_extra_or_changed_files(tmp_path: Path) -> None:
    package_root = tmp_path / "functorial_kit"
    package_root.mkdir()
    (package_root / "__init__.py").write_bytes(b"installed\n")
    installed_files, _ = audit.inspect_installed_package_files(package_root)
    source_files, _ = audit._package_file_manifest(
        {"functorial_kit/__init__.py": b"source\n"}
    )
    with pytest.raises(audit.AuditContractError, match="do not byte-match") as raised:
        audit.compare_installed_to_source(installed_files, source_files)
    assert raised.value.evidence["artifact_comparison"]["changed_paths"] == [
        "functorial_kit/__init__.py"
    ]

    (package_root / "extra.py").write_bytes(b"extra\n")
    installed_files, _ = audit.inspect_installed_package_files(package_root)
    with pytest.raises(audit.AuditContractError) as raised:
        audit.compare_installed_to_source(installed_files, source_files)
    assert raised.value.evidence["artifact_comparison"]["extra_installed_paths"] == [
        "functorial_kit/extra.py"
    ]


def test_source_bandit_is_fail_closed_for_findings(tmp_path: Path) -> None:
    native = {"errors": [], "results": [{"test_id": "B999"}]}

    def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 1, json.dumps(native), "")

    with pytest.raises(audit.AuditContractError, match="Bandit high/high scan failed"):
        audit.run_installed_source_bandit(tmp_path, "bandit", runner=runner)


def test_source_bandit_rejects_non_object_report_with_structured_evidence(tmp_path: Path) -> None:
    def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, "[]", "")

    with pytest.raises(audit.AuditContractError, match="root must be an object") as raised:
        audit.run_installed_source_bandit(tmp_path, "bandit", runner=runner)
    assert raised.value.evidence["bandit"]["native_report"] == []


def test_source_bandit_accepts_zero_findings(tmp_path: Path) -> None:
    native = {"errors": [], "results": [], "metrics": {"_totals": {"loc": 42}}}

    def runner(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, json.dumps(native), "")

    result = audit.run_installed_source_bandit(tmp_path, "bandit", runner=runner)
    assert result["exit_code"] == 0
    assert result["native_report"] == native
