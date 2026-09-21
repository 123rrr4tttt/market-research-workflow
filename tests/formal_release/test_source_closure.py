from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.formal_release.source_closure import (  # noqa: E402
    BACKEND_MIGRATION_VERSIONS_ROOT,
    CORE_ROOT,
    CURRENT_BYTE_BUNDLE_ROOT_FILES,
    CURRENT_BYTE_BUNDLE_ROOTS,
    CURRENT_BYTE_BUNDLE_SNAPSHOT_ROOTS,
    FRONTEND_SELECTOR_ROOT,
    FRONTEND_SELECTOR_ROOT_FILES,
    FRONTEND_SELECTOR_SUBTREES,
    REQUIRED_CONSUMERS,
    REQUIRED_CORE_MODULES,
    STAGE3_REMEDIATION_CONTRACT_PATH,
    STAGE3_REMEDIATION_CONTRACT_ROOT,
    STAGE3_REMEDIATION_HISTORICAL_RECORD_PATH,
    STAGE3_REMEDIATION_HISTORICAL_RECORD_ROOT,
    STAGE3_REMEDIATION_TEST_FIXTURE_PATHS,
    STAGE3_REMEDIATION_TEST_FIXTURE_ROOT,
    STAGE1_PRODUCTION_BINDING_BUNDLE_FILES,
    STAGE1_PRODUCTION_BINDING_BUNDLE_ROOT,
    WORKFLOW_SELECTOR_JSON_ROOTS,
    WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS,
    WORKFLOW_SELECTOR_EXACT_PATHS,
    WORKFLOW_SELECTOR_LOG_ROOTS,
    WORKFLOW_SELECTOR_MARKDOWN_ROOTS,
    WORKFLOW_SELECTOR_PYTHON_ROOTS,
    WORKFLOW_SELECTOR_ROOTS,
    WORKFLOW_SELECTOR_SHELL_ROOTS,
    WORKFLOW_SELECTOR_STATIC_EXACT_PATHS,
    WORKFLOW_SELECTOR_SUCCESSOR_PROJECTION_PATHS,
    WORKFLOW_SELECTOR_TEST_EVIDENCE_EXACT_PATHS,
    SourceClosureError,
    check_workflow_selector_manifest_closure,
    check_frontend_selector_manifest_closure,
    check_source_closure,
    check_source_closure_if_present,
    compute_workflow_selector_delta,
    compute_frontend_selector_delta,
    is_mrw_projected_candidate,
)
from scripts.formal_release.stage2_git_batch import BaseTreeIndex, git_blob_oid  # noqa: E402


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "candidate"
    relatives = [
        path.relative_to(ROOT)
        for path in (ROOT / CORE_ROOT).glob("*.py")
    ]
    relatives.extend(Path(path) for path in REQUIRED_CONSUMERS)
    for relative in relatives:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _manifest(*paths: str) -> dict[str, object]:
    return {
        "entries": [
            {"path": path, "operation": "UPSERT"}
            for path in paths
        ]
    }


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(("git", "-C", str(root), *args), text=True).strip()


def _commit_base(root: Path) -> tuple[str, BaseTreeIndex]:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "source@example.test")
    _git(root, "config", "user.name", "Source")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    return base, BaseTreeIndex.from_repo(root, base)


def _projected_manifest(
    root: Path,
    base: str,
    index: BaseTreeIndex,
    *,
    upserts: tuple[str, ...] = REQUIRED_CORE_MODULES,
    deletes: tuple[str, ...] = (),
) -> dict[str, object]:
    entries: list[dict[str, str]] = []
    for relative in (*upserts, *deletes):
        base_entry = index.lookup(relative)
        base_mode = base_entry.mode if base_entry is not None else "000000"
        base_blob = base_entry.oid if base_entry is not None else ""
        if relative in deletes:
            entries.append(
                {
                    "path": relative,
                    "operation": "DELETE",
                    "mode": "000000",
                    "sha256": "",
                    "blob": "",
                    "base_mode": base_mode,
                    "base_blob": base_blob,
                }
            )
            continue
        payload = (root / relative).read_bytes()
        mode = "100755" if (root / relative).stat().st_mode & 0o111 else "100644"
        entries.append(
            {
                "path": relative,
                "operation": "UPSERT",
                "mode": mode,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "blob": git_blob_oid(payload),
                "base_mode": base_mode,
                "base_blob": base_blob,
            }
        )
    return {"source": {"base_oid": base}, "entries": entries}


def test_source_closure_passes_with_two_modules_and_seven_consumers(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    result = check_source_closure(root, manifest=_manifest(*REQUIRED_CORE_MODULES))
    assert result.required_modules == REQUIRED_CORE_MODULES
    assert result.consumers == tuple(REQUIRED_CONSUMERS)
    assert result.manifest_paths == tuple(sorted(REQUIRED_CORE_MODULES))


@pytest.mark.parametrize("missing", REQUIRED_CORE_MODULES)
def test_source_closure_rejects_missing_required_module(tmp_path: Path, missing: str) -> None:
    root = _fixture(tmp_path)
    (root / missing).unlink()
    with pytest.raises(SourceClosureError, match="required source module is missing"):
        check_source_closure(root)


def test_source_closure_rejects_unknown_package_export(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    init = root / CORE_ROOT / "__init__.py"
    text = init.read_text(encoding="utf-8")
    init.write_text(
        text.replace('    "writing_request_contract_failures",\n', '    "unknown_export",\n'),
        encoding="utf-8",
    )
    with pytest.raises(SourceClosureError, match="unknown exported name"):
        check_source_closure(root)


def test_source_closure_resolves_relative_package_imports(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    init = root / CORE_ROOT / "__init__.py"
    text = init.read_text(encoding="utf-8")
    init.write_text(
        text.replace(
            "from mrw_functorial_kit.core.w07_semantics import (",
            "from .w07_semantics import (",
        ),
        encoding="utf-8",
    )
    check_source_closure(root, manifest=_manifest(*REQUIRED_CORE_MODULES))


def test_source_closure_rejects_source_manifest_omission(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    with pytest.raises(SourceClosureError, match="source/manifest omission"):
        check_source_closure(root, manifest=_manifest(REQUIRED_CORE_MODULES[0]))


def test_source_closure_optional_probe_skips_unrelated_repository(tmp_path: Path) -> None:
    assert check_source_closure_if_present(tmp_path) is None


def test_projected_source_closure_uses_base_consumer_not_checkout_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    base, index = _commit_base(root)
    consumer = root / next(iter(REQUIRED_CONSUMERS))
    consumer.write_text("from nowhere import drift\n", encoding="utf-8")

    result = check_source_closure(
        root,
        manifest=_projected_manifest(root, base, index),
        base_index=index,
    )

    assert result.required_modules == REQUIRED_CORE_MODULES


def test_base_only_mrw_package_is_detected_and_checked_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "candidate"
    write_path = root / CORE_ROOT / "__init__.py"
    write_path.parent.mkdir(parents=True)
    write_path.write_text("__all__ = []\n", encoding="utf-8")
    base, index = _commit_base(root)
    shutil.rmtree(root / "src")
    manifest = {"source": {"base_oid": base}, "entries": []}

    assert is_mrw_projected_candidate(root, manifest, base_index=index) is True
    with pytest.raises(SourceClosureError, match="required source module is missing"):
        check_source_closure(root, manifest=manifest, base_index=index)


def test_projected_mrw_detection_ignores_undeclared_checkout_only_package(
    tmp_path: Path,
) -> None:
    root = tmp_path / "candidate"
    root.mkdir()
    (root / "generic.txt").write_text("generic\n", encoding="utf-8")
    base, index = _commit_base(root)
    _fixture(tmp_path)
    manifest = {"source": {"base_oid": base}, "entries": []}

    assert (root / CORE_ROOT).is_dir()
    assert is_mrw_projected_candidate(root, manifest, base_index=index) is False


def test_projected_source_closure_reads_base_blob_from_index_repository(tmp_path: Path) -> None:
    source = _fixture(tmp_path / "source")
    base, _ = _commit_base(source)
    clone = tmp_path / "clone"
    subprocess.run(
        ("git", "clone", "--quiet", "--no-checkout", str(source), str(clone)),
        check=True,
    )
    index = BaseTreeIndex.from_repo(clone, base)

    assert check_source_closure(
        source,
        manifest=_projected_manifest(source, base, index),
        base_index=index,
    ).consumers


def test_projected_source_closure_rejects_base_missing_init_despite_checkout_file(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    init = root / CORE_ROOT / "__init__.py"
    payload = init.read_bytes()
    init.unlink()
    base, index = _commit_base(root)
    init.write_bytes(payload)

    with pytest.raises(SourceClosureError, match="core package is missing"):
        check_source_closure(
            root,
            manifest=_projected_manifest(root, base, index),
            base_index=index,
        )


def test_projected_source_closure_allows_base_missing_package_when_fully_upserted(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    init = root / CORE_ROOT / "__init__.py"
    payload = init.read_bytes()
    init.unlink()
    base, index = _commit_base(root)
    init.write_bytes(payload)
    manifest = _projected_manifest(
        root,
        base,
        index,
        upserts=(
            *REQUIRED_CORE_MODULES,
            (CORE_ROOT / "__init__.py").as_posix(),
            *REQUIRED_CONSUMERS,
        ),
    )

    assert check_source_closure(root, manifest=manifest, base_index=index).consumers


@pytest.mark.parametrize(
    ("deleted", "message"),
    (
        pytest.param(REQUIRED_CORE_MODULES[0], "required source module is missing", id="module"),
        pytest.param((CORE_ROOT / "__init__.py").as_posix(), "core package is missing", id="init"),
        pytest.param(next(iter(REQUIRED_CONSUMERS)), "required consumer is missing", id="consumer"),
    ),
)
def test_projected_source_closure_treats_delete_as_missing(
    tmp_path: Path, deleted: str, message: str
) -> None:
    root = _fixture(tmp_path)
    base, index = _commit_base(root)
    upserts = tuple(path for path in REQUIRED_CORE_MODULES if path != deleted)
    manifest = _projected_manifest(root, base, index, upserts=upserts, deletes=(deleted,))

    with pytest.raises(SourceClosureError, match=message):
        check_source_closure(root, manifest=manifest, base_index=index)


def test_projected_source_closure_rejects_wrong_base_index_binding(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    base, index = _commit_base(root)
    manifest = _projected_manifest(root, base, index)
    manifest["source"] = {"base_oid": "0" * 40}

    with pytest.raises(SourceClosureError, match="index oid does not match"):
        check_source_closure(root, manifest=manifest, base_index=index)


@pytest.mark.parametrize("field", ("sha256", "blob", "mode"))
def test_projected_source_closure_rejects_upsert_metadata_or_bytes_drift(
    tmp_path: Path, field: str
) -> None:
    root = _fixture(tmp_path)
    base, index = _commit_base(root)
    manifest = _projected_manifest(root, base, index)
    manifest["entries"][0][field] = "0" * 64  # type: ignore[index]

    with pytest.raises(SourceClosureError, match="projected UPSERT bytes, mode, sha256, or blob drift"):
        check_source_closure(root, manifest=manifest, base_index=index)


def test_projected_source_closure_rejects_upsert_source_bytes_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    base, index = _commit_base(root)
    manifest = _projected_manifest(root, base, index)
    (root / REQUIRED_CORE_MODULES[0]).write_text("changed = True\n", encoding="utf-8")

    with pytest.raises(SourceClosureError, match="projected UPSERT bytes, mode, sha256, or blob drift"):
        check_source_closure(root, manifest=manifest, base_index=index)


def _workflow_selector_base(tmp_path: Path) -> tuple[Path, str, BaseTreeIndex]:
    root = tmp_path / "workflow-source"
    relatives = (
        "main/backend/app/base.py",
        "main/backend/app/legacy.py",
        "main/backend/app/successor_runtime/runtime/allowed.py",
        "main/backend/pytest.ini",
        "main/backend/requirements.txt",
        "main/backend/.env.production.example",
        "main/ops/base.py",
        "main/ops/docker-compose.production.yml",
        "ops/base.py",
        "scripts/base.py",
        "scripts/base.sh",
        "src/mrw_functorial_kit/base.py",
        "docs/governance/base.json",
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
        "stage-b13-2026-09-05/sidecar-inputs/base.json",
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/stage0-evidence/base.json",
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/stage0-evidence/"
        "stage0-v2-frontend-npm-lint.log",
        "development/latest-dev-docs/backend-docs/B_API/"
        "API_SCHEMA_INVENTORY_2026-05-22.md",
        "pyproject.toml",
    )
    for relative in relatives:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")
    base, index = _commit_base(root)
    return root, base, index


def _selector_manifest(base: str, *rows: tuple[str, str]) -> dict[str, object]:
    return {
        "source": {"base_oid": base},
        "entries": [
            {"path": path, "operation": operation}
            for operation, path in rows
        ],
    }


def test_workflow_selector_delta_completeness(tmp_path: Path) -> None:
    root, _base, index = _workflow_selector_base(tmp_path)
    (root / "main/backend/app/base.py").write_text("# changed\n", encoding="utf-8")
    (root / "main/backend/app/new.py").write_text("# untracked\n", encoding="utf-8")
    (root / "main/backend/app/successor_runtime/runtime/new.py").write_text(
        "# source runtime\n", encoding="utf-8"
    )
    (root / "main/backend/pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (root / "main/backend/requirements-extra.txt").write_text("pytest\n", encoding="utf-8")
    (root / "main/ops/base.py").write_text("# changed\n", encoding="utf-8")
    (root / "ops/new.py").write_text("# new\n", encoding="utf-8")
    (root / "scripts/new.py").write_text("# new\n", encoding="utf-8")
    (root / "scripts/new.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (root / "src/mrw_functorial_kit/new.py").write_text("# new\n", encoding="utf-8")
    (root / "docs/governance/new.json").write_text("{}\n", encoding="utf-8")
    exact_rebind_json = (
        root
        / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
        "stage-b13-2099-01-01/sidecar-inputs/new.json"
    )
    exact_rebind_json.parent.mkdir(parents=True, exist_ok=True)
    exact_rebind_json.write_text("{}\n", encoding="utf-8")
    stage0_json = (
        root
        / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/stage0-evidence/new.json"
    )
    stage0_json.write_text("{}\n", encoding="utf-8")
    stage0_log = stage0_json.with_name("stage0-v2-frontend-npm-lint.log")
    api_markdown = (
        root
        / "development/latest-dev-docs/backend-docs/B_API/"
        "API_SCHEMA_INVENTORY_2026-05-22.md"
    )
    api_markdown.parent.mkdir(parents=True, exist_ok=True)
    api_markdown.write_text("# changed inventory\n", encoding="utf-8")
    stage0_log.write_text("frontend lint passed\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests/test_new_law.py").write_text("# law witness\n", encoding="utf-8")
    (root / "main/backend/app/legacy.py").unlink()
    (root / "notes.md").write_text("unrelated\n", encoding="utf-8")
    (root / "main/backend/app/data.json").write_text("{}\n", encoding="utf-8")

    expected = (
        ("DELETE", "main/backend/app/legacy.py"),
        (
            "UPSERT",
            "development/latest-dev-docs/backend-docs/B_API/"
            "API_SCHEMA_INVENTORY_2026-05-22.md",
        ),
        (
            "UPSERT",
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
            "stage-b13-2099-01-01/sidecar-inputs/new.json",
        ),
        (
            "UPSERT",
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-09-04-formal-production-release/stage0-evidence/new.json",
        ),
        (
            "UPSERT",
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-09-04-formal-production-release/stage0-evidence/"
            "stage0-v2-frontend-npm-lint.log",
        ),
        ("UPSERT", "docs/governance/new.json"),
        ("UPSERT", "main/backend/app/base.py"),
        ("UPSERT", "main/backend/app/new.py"),
        ("UPSERT", "main/backend/app/successor_runtime/runtime/new.py"),
        ("UPSERT", "main/backend/pytest.ini"),
        ("UPSERT", "main/backend/requirements-extra.txt"),
        ("UPSERT", "main/ops/base.py"),
        ("UPSERT", "ops/new.py"),
        ("UPSERT", "scripts/new.py"),
        ("UPSERT", "scripts/new.sh"),
        ("UPSERT", "src/mrw_functorial_kit/new.py"),
        ("UPSERT", "tests/test_new_law.py"),
    )
    assert compute_workflow_selector_delta(root, base_index=index) == expected


def test_workflow_selector_delta_exclusions(tmp_path: Path) -> None:
    root, _base, index = _workflow_selector_base(tmp_path)
    for relative in (
        "cache/excluded.py",
        "main/backend/.venv/excluded.py",
        "main/backend/runtime/excluded.py",
        "main/backend/secrets/excluded.py",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# ignored\n", encoding="utf-8")
    assert compute_workflow_selector_delta(root, base_index=index) == ()


def test_workflow_selector_delta_excludes_backup_virtualenvs(tmp_path: Path) -> None:
    root, _base, index = _workflow_selector_base(tmp_path)
    for relative in (
        "main/backend/.venv311/excluded.py",
        "main/backend/.venv311.bak-20260906/excluded.py",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# ignored\n", encoding="utf-8")

    assert compute_workflow_selector_delta(root, base_index=index) == ()


def test_workflow_selector_delta_includes_backend_api_contract_documents(
    tmp_path: Path,
) -> None:
    root, _base, index = _workflow_selector_base(tmp_path)
    relative = (
        "development/latest-dev-docs/backend-docs/B_API/"
        "API_SCHEMA_INVENTORY_2026-05-22.md"
    )
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# changed inventory\\n", encoding="utf-8")

    assert compute_workflow_selector_delta(root, base_index=index) == (
        ("UPSERT", relative),
    )


def test_workflow_selector_delta_includes_production_route_bindings(
    tmp_path: Path,
) -> None:
    root, _base, index = _workflow_selector_base(tmp_path)
    relative = "main/backend/app/composition/production_route_bindings.json"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema":"mrw.production-route-bindings.v1"}\n', encoding="utf-8")

    assert compute_workflow_selector_delta(root, base_index=index) == (
        ("UPSERT", relative),
    )


def test_workflow_selector_delta_rejects_included_symlink_and_fifo(
    tmp_path: Path,
) -> None:
    root, _base, index = _workflow_selector_base(tmp_path)
    target = root / "main/backend/notes.md"
    target.write_text("# target\n", encoding="utf-8")
    symlink = root / "main/backend/app/symlinked.py"
    symlink.symlink_to(target)
    fifo = root / "main/backend/app/fifo.py"
    os.mkfifo(fifo)

    with pytest.raises(SourceClosureError, match="not a regular file"):
        compute_workflow_selector_delta(root, base_index=index)

    symlink.unlink()
    fifo.unlink()
    assert compute_workflow_selector_delta(root, base_index=index) == ()


def test_workflow_selector_manifest_allows_irrelevant_extra(tmp_path: Path) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    manifest = _selector_manifest(base, ("UPSERT", "notes.md"))
    assert check_workflow_selector_manifest_closure(root, manifest, base_index=index) == ()

    excluded = _selector_manifest(
        base,
        ("UPSERT", "main/backend/.venv311/excluded.py"),
    )
    with pytest.raises(SourceClosureError, match="excluded"):
        check_workflow_selector_manifest_closure(root, excluded, base_index=index)


def test_workflow_selector_roots_are_closed() -> None:
    assert WORKFLOW_SELECTOR_PYTHON_ROOTS == (
        "main/backend",
        "main/ops",
        "src/mrw_functorial_kit",
        "ops",
        "scripts",
        "tests",
    )
    assert WORKFLOW_SELECTOR_SHELL_ROOTS == ("main/ops", "ops", "scripts")
    assert WORKFLOW_SELECTOR_JSON_ROOTS == (
        "docs/governance",
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/stage0-evidence",
    )
    assert WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS == (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind",
    )
    assert WORKFLOW_SELECTOR_LOG_ROOTS == (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/stage0-evidence",
    )
    assert WORKFLOW_SELECTOR_MARKDOWN_ROOTS == (
        "development/latest-dev-docs/backend-docs/B_API",
    )
    assert WORKFLOW_SELECTOR_STATIC_EXACT_PATHS == frozenset(
        {
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-09-04-formal-production-release/04_production-deployment-stage-plan.v1.md",
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-09-04-formal-production-release/05_production-deployment-stage-plan.freeze.v1.json",
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-09-04-formal-production-release/10_stage1-stage2-source-and-static-closure-return-contract.v1.md",
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-09-04-formal-production-release/16_stage-convergence-execution-amendment.v1.md",
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-09-04-formal-production-release/stage1-evidence/independent-review.v1.md",
            "functorial-kit.json",
            "main/backend/.env.production.example",
            "main/backend/app/composition/production_route_bindings.json",
            "main/ops/docker-compose.yml",
            "main/ops/docker-compose.production.yml",
            "pyproject.toml",
            "sketches.json",
            "tools/functorial-kit/consumer-gate.manifest.json",
            "tools/functorial-kit/consumer-gate.patch",
        }
    )
    assert WORKFLOW_SELECTOR_EXACT_PATHS == (
        WORKFLOW_SELECTOR_STATIC_EXACT_PATHS
        | WORKFLOW_SELECTOR_TEST_EVIDENCE_EXACT_PATHS
        | WORKFLOW_SELECTOR_SUCCESSOR_PROJECTION_PATHS
    )
    assert WORKFLOW_SELECTOR_ROOTS == (
        *WORKFLOW_SELECTOR_PYTHON_ROOTS,
        *WORKFLOW_SELECTOR_JSON_ROOTS,
        *WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS,
        *WORKFLOW_SELECTOR_MARKDOWN_ROOTS,
        *WORKFLOW_SELECTOR_LOG_ROOTS,
        *CURRENT_BYTE_BUNDLE_ROOTS,
        STAGE1_PRODUCTION_BINDING_BUNDLE_ROOT,
        STAGE3_REMEDIATION_TEST_FIXTURE_ROOT,
        STAGE3_REMEDIATION_CONTRACT_ROOT,
        STAGE3_REMEDIATION_HISTORICAL_RECORD_ROOT,
    )


def _declared_current_byte_bundle_paths() -> tuple[Path, ...]:
    paths: set[Path] = set()
    for root in CURRENT_BYTE_BUNDLE_ROOTS:
        manifests = sorted((ROOT / root).glob("artifact-manifest.v*.json"))
        assert len(manifests) == 1, root
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        assert isinstance(manifest, dict)
        assert manifest["member_count"] == len(manifest["members"])
        paths.add(manifests[0].relative_to(ROOT))
        paths.update(Path(row["path"]) for row in manifest["members"])
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def test_workflow_selector_includes_complete_current_byte_consumer_bundles(
    tmp_path: Path,
) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    paths = _declared_current_byte_bundle_paths()
    assert len(paths) == 48
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    expected = tuple(("UPSERT", path.as_posix()) for path in paths)
    assert compute_workflow_selector_delta(root, base_index=index) == expected
    assert check_workflow_selector_manifest_closure(
        root,
        _selector_manifest(base, *expected),
        base_index=index,
    ) == expected

    missing = Path(
        "stage1-successor-evidence/current-byte-remediation-v1/bindings/"
        "artifact-manifest.v1.json"
    )
    incomplete = tuple(row for row in expected if row[1] != missing.as_posix())
    with pytest.raises(
        SourceClosureError,
        match=f"workflow selector manifest closure gap: {missing.as_posix()}",
    ):
        check_workflow_selector_manifest_closure(
            root,
            _selector_manifest(base, *incomplete),
            base_index=index,
        )


def test_workflow_selector_current_byte_roots_remain_exact_and_exclude_runtime(
    tmp_path: Path,
) -> None:
    root, _base, index = _workflow_selector_base(tmp_path)
    excluded_suffixes = (
        "__pycache__/generated.pyc",
        "startup/generated.py",
        "local/generated.py",
        "raw/generated.json",
        "runtime/generated.py",
        "generated.log",
        "snapshots/not-a-lowercase-sha256",
    )
    for bundle_root in CURRENT_BYTE_BUNDLE_ROOTS:
        for suffix in excluded_suffixes:
            path = root / bundle_root / suffix
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("excluded\n", encoding="utf-8")
    assert compute_workflow_selector_delta(root, base_index=index) == ()

    assert len(CURRENT_BYTE_BUNDLE_ROOT_FILES) == 5
    assert len(CURRENT_BYTE_BUNDLE_SNAPSHOT_ROOTS) == 4


def test_workflow_selector_current_byte_bundle_delete_is_projected(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workflow-source"
    relative = Path(
        "stage1-successor-evidence/current-byte-remediation-v2/bindings/"
        "check_current_byte_binding_successors_v2.py"
    )
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# predecessor checker\n", encoding="utf-8")
    _base, index = _commit_base(root)
    target.unlink()
    assert compute_workflow_selector_delta(root, base_index=index) == (
        ("DELETE", relative.as_posix()),
    )


def test_workflow_selector_includes_closed_stage3_remediation_test_fixtures(
    tmp_path: Path,
) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    assert len(STAGE3_REMEDIATION_TEST_FIXTURE_PATHS) == 31
    expected = tuple(
        (
            "UPSERT",
            f"{STAGE3_REMEDIATION_TEST_FIXTURE_ROOT}/{relative}",
        )
        for relative in sorted(STAGE3_REMEDIATION_TEST_FIXTURE_PATHS)
    )
    for _operation, relative in expected:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    assert compute_workflow_selector_delta(root, base_index=index) == expected
    missing = (
        f"{STAGE3_REMEDIATION_TEST_FIXTURE_ROOT}/raw/source-selector.json"
    )
    with pytest.raises(
        SourceClosureError,
        match=f"workflow selector manifest closure gap: {missing}",
    ):
        check_workflow_selector_manifest_closure(
            root,
            _selector_manifest(
                base,
                *(row for row in expected if row[1] != missing),
            ),
            base_index=index,
        )

    unrelated = root / STAGE3_REMEDIATION_TEST_FIXTURE_ROOT / "raw/startup.log"
    unrelated.write_text("excluded\n", encoding="utf-8")
    assert compute_workflow_selector_delta(root, base_index=index) == expected


def test_workflow_selector_includes_only_the_bound_stage3_contract(
    tmp_path: Path,
) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    contract = root / STAGE3_REMEDIATION_CONTRACT_PATH
    contract.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / STAGE3_REMEDIATION_CONTRACT_PATH, contract)
    unrelated = contract.with_name("16_unbound-contract.md")
    unrelated.write_text("# not selected\n", encoding="utf-8")
    expected = (("UPSERT", STAGE3_REMEDIATION_CONTRACT_PATH),)
    assert compute_workflow_selector_delta(root, base_index=index) == expected
    with pytest.raises(
        SourceClosureError,
        match=f"workflow selector manifest closure gap: {STAGE3_REMEDIATION_CONTRACT_PATH}",
    ):
        check_workflow_selector_manifest_closure(
            root,
            _selector_manifest(base),
            base_index=index,
        )


def test_workflow_selector_includes_only_the_bound_stage3_historical_record(
    tmp_path: Path,
) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    record = root / STAGE3_REMEDIATION_HISTORICAL_RECORD_PATH
    record.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / STAGE3_REMEDIATION_HISTORICAL_RECORD_PATH, record)
    unrelated = record.with_name("stage2-v6-intake-remediation-record.v4.json")
    unrelated.write_text("{}\n", encoding="utf-8")
    expected = (("UPSERT", STAGE3_REMEDIATION_HISTORICAL_RECORD_PATH),)

    assert compute_workflow_selector_delta(root, base_index=index) == expected
    with pytest.raises(
        SourceClosureError,
        match=(
            "workflow selector manifest closure gap: "
            f"{STAGE3_REMEDIATION_HISTORICAL_RECORD_PATH}"
        ),
    ):
        check_workflow_selector_manifest_closure(
            root,
            _selector_manifest(base),
            base_index=index,
        )


def test_workflow_selector_includes_only_static_production_contract_inputs(
    tmp_path: Path,
) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    expected = tuple(
        ("UPSERT", relative)
        for relative in sorted(WORKFLOW_SELECTOR_STATIC_EXACT_PATHS)
    )
    for _operation, relative in expected:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"changed {relative}\n", encoding="utf-8")

    for relative in (
        "main/backend/.env.production.local",
        "main/ops/docker-compose.development.yml",
        "pyproject.backup.toml",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("excluded\n", encoding="utf-8")

    assert compute_workflow_selector_delta(root, base_index=index) == expected
    with pytest.raises(
        SourceClosureError,
        match=(
            "workflow selector manifest closure gap: "
            "main/ops/docker-compose.production.yml"
        ),
    ):
        check_workflow_selector_manifest_closure(
            root,
            _selector_manifest(
                base,
                *(
                    row
                    for row in expected
                    if row[1] != "main/ops/docker-compose.production.yml"
                ),
            ),
            base_index=index,
        )


def test_workflow_selector_projects_exact_backend_test_evidence_deletes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workflow-source"
    for relative in WORKFLOW_SELECTOR_TEST_EVIDENCE_EXACT_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"historical evidence: {relative}\n", encoding="utf-8")
    _base, index = _commit_base(root)
    for relative in WORKFLOW_SELECTOR_TEST_EVIDENCE_EXACT_PATHS:
        (root / relative).unlink()

    assert len(WORKFLOW_SELECTOR_TEST_EVIDENCE_EXACT_PATHS) == 42
    assert compute_workflow_selector_delta(root, base_index=index) == tuple(
        ("DELETE", relative)
        for relative in sorted(WORKFLOW_SELECTOR_TEST_EVIDENCE_EXACT_PATHS)
    )


def test_successor_current_projections_are_selected_and_omissions_fail_closed(
    tmp_path: Path,
) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    assert len(WORKFLOW_SELECTOR_SUCCESSOR_PROJECTION_PATHS) == 13
    for relative in WORKFLOW_SELECTOR_SUCCESSOR_PROJECTION_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    assert compute_workflow_selector_delta(root, base_index=index) == tuple(
        ("UPSERT", relative)
        for relative in sorted(WORKFLOW_SELECTOR_SUCCESSOR_PROJECTION_PATHS)
    )
    with pytest.raises(SourceClosureError, match="workflow selector manifest closure gap"):
        check_workflow_selector_manifest_closure(
            root, _selector_manifest(base), base_index=index
        )
    assert not any("GeneratedHandwrittenOwnership" in path for path in WORKFLOW_SELECTOR_SUCCESSOR_PROJECTION_PATHS)


def test_exact_rebind_selector_excludes_non_sidecar_historical_outputs(
    tmp_path: Path,
) -> None:
    root, _base, index = _workflow_selector_base(tmp_path)
    candidate = (
        root
        / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
        "stage-b13-2099-01-01/candidates/C9/candidate.v2.json"
    )
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("{}\n", encoding="utf-8")
    assert compute_workflow_selector_delta(root, base_index=index) == ()


@pytest.mark.parametrize(
    "relative",
    (
        "scripts/base.sh",
        "docs/governance/base.json",
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
        "stage-b13-2026-09-05/sidecar-inputs/base.json",
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/stage0-evidence/base.json",
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/stage0-evidence/"
        "stage0-v2-frontend-npm-lint.log",
    ),
)
def test_root_support_selector_rejects_changed_or_deleted_omission(
    tmp_path: Path, relative: str
) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    path = root / relative
    path.write_text("changed\n", encoding="utf-8")
    with pytest.raises(SourceClosureError, match="workflow selector manifest closure gap"):
        check_workflow_selector_manifest_closure(
            root, _selector_manifest(base), base_index=index
        )

    path.unlink()
    with pytest.raises(SourceClosureError, match="workflow selector manifest closure gap"):
        check_workflow_selector_manifest_closure(
            root, _selector_manifest(base), base_index=index
        )


def test_root_law_witness_omission_is_rejected(tmp_path: Path) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    (root / "tests").mkdir()
    (root / "tests/test_counter_laws.py").write_text(
        "def test_counter_law():\n    assert True\n", encoding="utf-8"
    )
    with pytest.raises(SourceClosureError, match="workflow selector manifest closure gap"):
        check_workflow_selector_manifest_closure(
            root, _selector_manifest(base), base_index=index
        )


def test_workflow_selector_manifest_coverage_and_unchanged_base(tmp_path: Path) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    manifest = _selector_manifest(base)
    assert compute_workflow_selector_delta(root, base_index=index) == ()
    assert check_workflow_selector_manifest_closure(root, manifest, base_index=index) == ()

    (root / "main/backend/app/base.py").write_text("# changed\n", encoding="utf-8")
    (root / "main/backend/app/new.py").write_text("# untracked\n", encoding="utf-8")
    (root / "main/backend/app/legacy.py").unlink()
    expected = (
        ("DELETE", "main/backend/app/legacy.py"),
        ("UPSERT", "main/backend/app/base.py"),
        ("UPSERT", "main/backend/app/new.py"),
    )
    assert compute_workflow_selector_delta(root, base_index=index) == expected
    full = _selector_manifest(base, *expected, ("UPSERT", "ops/base.py"))
    assert check_workflow_selector_manifest_closure(root, full, base_index=index) == expected


def test_workflow_selector_requires_base_migration_delete_when_source_is_absent(
    tmp_path: Path,
) -> None:
    root, _base, _index = _workflow_selector_base(tmp_path)
    migration = BACKEND_MIGRATION_VERSIONS_ROOT / "20260524_000001_bridge.py"
    path = root / migration
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('revision = "20260524_000001"\n', encoding="utf-8")
    base, index = _commit_base(root)
    path.unlink()

    manifest = _selector_manifest(base)
    with pytest.raises(
        SourceClosureError,
        match="backend migration manifest projection has unexpected paths",
    ):
        check_workflow_selector_manifest_closure(root, manifest, base_index=index)

    manifest = _selector_manifest(base, ("DELETE", migration.as_posix()))
    assert check_workflow_selector_manifest_closure(
        root, manifest, base_index=index
    ) == (("DELETE", migration.as_posix()),)


def test_workflow_selector_rejects_deleting_referenced_migration_parent(
    tmp_path: Path,
) -> None:
    root, _base, _index = _workflow_selector_base(tmp_path)
    parent = BACKEND_MIGRATION_VERSIONS_ROOT / "20260525_000001_parent.py"
    child = BACKEND_MIGRATION_VERSIONS_ROOT / "20260905_000001_merge.py"
    for path, source in (
        (parent, 'revision = "20260525_000001"\ndown_revision = None\n'),
        (
            child,
            'revision = "20260905_000001"\n'
            'down_revision = "20260525_000001"\n',
        ),
    ):
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")
    base, index = _commit_base(root)
    (root / parent).unlink()

    manifest = _selector_manifest(base, ("DELETE", parent.as_posix()))
    with pytest.raises(
        SourceClosureError,
        match=(
            "backend migration 20260905_000001 references missing "
            "down_revision 20260525_000001"
        ),
    ):
        check_workflow_selector_manifest_closure(root, manifest, base_index=index)


def test_workflow_selector_rejects_base_migration_delete_projection(
    tmp_path: Path,
) -> None:
    root, _base, _index = _workflow_selector_base(tmp_path)
    migration = BACKEND_MIGRATION_VERSIONS_ROOT / "20260524_000001_bridge.py"
    path = root / migration
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('revision = "20260524_000001"\n', encoding="utf-8")
    base, index = _commit_base(root)

    manifest = _selector_manifest(base, ("DELETE", migration.as_posix()))
    with pytest.raises(
        SourceClosureError,
        match="backend migration manifest projection is incomplete",
    ):
        check_workflow_selector_manifest_closure(root, manifest, base_index=index)


@pytest.mark.parametrize(
    ("omit", "label"),
    (
        ("main/backend/app/base.py", "changed"),
        ("main/backend/app/new.py", "untracked"),
        ("main/backend/app/legacy.py", "delete"),
    ),
)
def test_workflow_selector_manifest_rejects_omissions(
    tmp_path: Path, omit: str, label: str
) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    (root / "main/backend/app/base.py").write_text("# changed\n", encoding="utf-8")
    (root / "main/backend/app/new.py").write_text("# untracked\n", encoding="utf-8")
    (root / "main/backend/app/legacy.py").unlink()
    rows = (
        ("DELETE", "main/backend/app/legacy.py"),
        ("UPSERT", "main/backend/app/base.py"),
        ("UPSERT", "main/backend/app/new.py"),
    )
    manifest = _selector_manifest(base, *(row for row in rows if row[1] != omit))
    with pytest.raises(SourceClosureError, match="closure gap"):
        check_workflow_selector_manifest_closure(root, manifest, base_index=index)


def test_workflow_selector_manifest_rejects_stale_operation(tmp_path: Path) -> None:
    root, base, index = _workflow_selector_base(tmp_path)
    (root / "main/backend/app/legacy.py").unlink()
    manifest = _selector_manifest(base, ("UPSERT", "main/backend/app/legacy.py"))
    with pytest.raises(SourceClosureError, match="operation mismatch"):
        check_workflow_selector_manifest_closure(root, manifest, base_index=index)


def _frontend_selector_base(tmp_path: Path) -> tuple[Path, str, BaseTreeIndex]:
    root = tmp_path / "frontend-source"
    root_files = (
        "package.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "tsconfig.json",
        "vite.config.ts",
        "package-lock.json",
    )
    for name in root_files:
        path = root / FRONTEND_SELECTOR_ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")
    for relative in (
        "src/legacy.tsx",
        "tests/legacy.ts",
        "scripts/legacy.mjs",
        "src/base.css",
    ):
        path = root / FRONTEND_SELECTOR_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"/* {relative} */\n", encoding="utf-8")
    base, index = _commit_base(root)
    return root, base, index


def test_frontend_selector_delta_covers_files_bytes_and_modes(
    tmp_path: Path,
) -> None:
    root, _base, index = _frontend_selector_base(tmp_path)
    prefix = FRONTEND_SELECTOR_ROOT / "src/base.css"
    (root / prefix).write_text("/* changed */\n", encoding="utf-8")
    (root / prefix).chmod(0o755)
    expected = (("UPSERT", prefix.as_posix()),)

    assert compute_frontend_selector_delta(root, base_index=index) == expected


def test_frontend_selector_includes_storybook_execution_config(tmp_path: Path) -> None:
    root, base, index = _frontend_selector_base(tmp_path)
    relative = FRONTEND_SELECTOR_ROOT / "playwright.storybook.config.ts"
    (root / relative).write_text("export default {};\n", encoding="utf-8")
    assert compute_frontend_selector_delta(root, base_index=index) == (("UPSERT", relative.as_posix()),)
    with pytest.raises(SourceClosureError, match="frontend selector manifest closure gap"):
        check_frontend_selector_manifest_closure(root, _selector_manifest(base), base_index=index)


def test_frontend_selector_delta_covers_fifty_nine_upserts_and_three_deletes(
    tmp_path: Path,
) -> None:
    root, _base, index = _frontend_selector_base(tmp_path)
    frontend = root / FRONTEND_SELECTOR_ROOT
    (frontend / "package.json").write_text("{\"changed\": true}\n", encoding="utf-8")
    (frontend / "pnpm-lock.yaml").write_text("changed: true\n", encoding="utf-8")
    (frontend / "src/base.css").write_text("/* changed */\n", encoding="utf-8")
    for name in ("src/legacy.tsx", "tests/legacy.ts", "scripts/legacy.mjs"):
        (root / FRONTEND_SELECTOR_ROOT / name).unlink()
    subtrees = ("src", "tests", "scripts", ".storybook", "public")
    for number in range(56):
        subtree = subtrees[number % len(subtrees)]
        suffix = (".tsx", ".ts", ".mjs", ".ts", ".svg")[number % 5]
        relative = frontend / subtree / f"generated-{number}{suffix}"
        relative.parent.mkdir(parents=True, exist_ok=True)
        relative.write_text(f"export const value = {number};\n", encoding="utf-8")

    delta = compute_frontend_selector_delta(root, base_index=index)
    upserts = tuple(row for row in delta if row[0] == "UPSERT")
    deletes = tuple(row for row in delta if row[0] == "DELETE")

    assert len(upserts) == 59
    assert len(deletes) == 3
    assert [path for operation, path in delta if operation == "DELETE"] == [
        (FRONTEND_SELECTOR_ROOT / "scripts/legacy.mjs").as_posix(),
        (FRONTEND_SELECTOR_ROOT / "src/legacy.tsx").as_posix(),
        (FRONTEND_SELECTOR_ROOT / "tests/legacy.ts").as_posix(),
    ]
    assert ("UPSERT", (FRONTEND_SELECTOR_ROOT / "package.json").as_posix()) in delta
    assert ("UPSERT", (FRONTEND_SELECTOR_ROOT / "src/base.css").as_posix()) in delta
    assert ("UPSERT", (FRONTEND_SELECTOR_ROOT / "public/generated-54.svg").as_posix()) in delta
    for _operation, path in delta:
        assert isinstance(path, str)


def test_frontend_selector_excludes_generated_runtime_and_legacy_lock(
    tmp_path: Path,
) -> None:
    root, _base, index = _frontend_selector_base(tmp_path)
    frontend = root / FRONTEND_SELECTOR_ROOT
    excluded = (
        "node_modules/generated.js",
        "dist/generated.js",
        "storybook-static/generated.js",
        "test-results/generated.json",
        "playwright-report/generated.html",
        "coverage/generated.js",
        ".cache/generated.js",
        "src/generated.tsbuildinfo",
        "src/.DS_Store",
        "src/__pycache__/generated.py",
        "log/generated.log",
        "env/generated.js",
        "secrets/generated.js",
    )
    for relative in excluded:
        path = frontend / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated\n", encoding="utf-8")
    (frontend / "package-lock.json").write_text(
        "{\"legacy\":\"changed\"}\n", encoding="utf-8"
    )

    assert compute_frontend_selector_delta(root, base_index=index) == ()


def test_frontend_selector_rejects_eligible_symlink_and_fifo(
    tmp_path: Path,
) -> None:
    root, _base, index = _frontend_selector_base(tmp_path)
    symlink = root / FRONTEND_SELECTOR_ROOT / "package.json"
    target = root / FRONTEND_SELECTOR_ROOT / "package-lock.json"
    symlink.unlink()
    symlink.symlink_to(target)

    with pytest.raises(SourceClosureError, match="not a regular file"):
        compute_frontend_selector_delta(root, base_index=index)

    symlink.unlink()
    (root / FRONTEND_SELECTOR_ROOT / "package.json").write_text(
        "# restored\n", encoding="utf-8"
    )
    fifo = root / FRONTEND_SELECTOR_ROOT / "src/fifo.ts"
    os.mkfifo(fifo)

    with pytest.raises(SourceClosureError, match="not a regular file"):
        compute_frontend_selector_delta(root, base_index=index)


def test_frontend_selector_manifest_unchanged_and_extra_entries(
    tmp_path: Path,
) -> None:
    root, base, index = _frontend_selector_base(tmp_path)
    manifest = {
        "source": {"base_oid": base},
        "entries": [{"path": "README.md", "operation": "UPSERT"}],
    }

    assert compute_frontend_selector_delta(root, base_index=index) == ()
    assert check_frontend_selector_manifest_closure(root, manifest, base_index=index) == ()


@pytest.mark.parametrize(
    ("omit", "label"),
    (
        ("src/base.css", "changed upsert"),
        ("src/legacy.tsx", "delete"),
    ),
)
def test_frontend_selector_manifest_rejects_missing_row(
    tmp_path: Path, omit: str, label: str
) -> None:
    root, base, index = _frontend_selector_base(tmp_path)
    (root / FRONTEND_SELECTOR_ROOT / "src/base.css").write_text(
        "/* changed */\n", encoding="utf-8"
    )
    (root / FRONTEND_SELECTOR_ROOT / "src/legacy.tsx").unlink()
    rows = (
        ("UPSERT", "src/base.css"),
        ("DELETE", "src/legacy.tsx"),
    )
    manifest = {
        "source": {"base_oid": base},
        "entries": [
            {"path": f"main/frontend-modern/{path}", "operation": operation}
            for operation, path in rows
            if path != omit
        ],
    }

    with pytest.raises(SourceClosureError, match="closure gap"):
        check_frontend_selector_manifest_closure(root, manifest, base_index=index)


def test_frontend_selector_manifest_rejects_wrong_operation(tmp_path: Path) -> None:
    root, base, index = _frontend_selector_base(tmp_path)
    (root / FRONTEND_SELECTOR_ROOT / "src/legacy.tsx").unlink()
    manifest = {
        "source": {"base_oid": base},
        "entries": [
            {
                "path": "main/frontend-modern/src/legacy.tsx",
                "operation": "UPSERT",
            }
        ],
    }

    with pytest.raises(SourceClosureError, match="operation mismatch"):
        check_frontend_selector_manifest_closure(root, manifest, base_index=index)


def test_frontend_selector_policy_is_closed() -> None:
    assert FRONTEND_SELECTOR_ROOT == Path("main/frontend-modern")
    assert FRONTEND_SELECTOR_SUBTREES == (
        "src",
        "tests",
        "scripts",
        ".storybook",
        "public",
    )
    assert "package-lock.json" not in FRONTEND_SELECTOR_ROOT_FILES


def test_stage1_production_binding_successor_bundle_policy_is_closed() -> None:
    root = STAGE1_PRODUCTION_BINDING_BUNDLE_ROOT
    assert STAGE1_PRODUCTION_BINDING_BUNDLE_FILES == frozenset(
        {
            "artifact-manifest.v1.json",
            "stage1-production-contract-binding-successor.v1.json",
        }
    )
    assert root in WORKFLOW_SELECTOR_ROOTS
    assert root not in CURRENT_BYTE_BUNDLE_ROOTS


def test_stage1_production_binding_successor_bundle_is_selected_exactly(
    tmp_path: Path,
) -> None:
    root, _base, index = _workflow_selector_base(tmp_path)
    bundle = root / STAGE1_PRODUCTION_BINDING_BUNDLE_ROOT
    bundle.mkdir(parents=True, exist_ok=True)
    for name in STAGE1_PRODUCTION_BINDING_BUNDLE_FILES:
        (bundle / name).write_text("selected\n", encoding="utf-8")
    (bundle / "unexpected.json").write_text("excluded\n", encoding="utf-8")
    (bundle / "snapshots").mkdir()
    (bundle / "snapshots" / ("a" * 64)).write_text("excluded\n", encoding="utf-8")

    assert compute_workflow_selector_delta(root, base_index=index) == tuple(
        ("UPSERT", f"{STAGE1_PRODUCTION_BINDING_BUNDLE_ROOT}/{name}")
        for name in sorted(STAGE1_PRODUCTION_BINDING_BUNDLE_FILES)
    )
