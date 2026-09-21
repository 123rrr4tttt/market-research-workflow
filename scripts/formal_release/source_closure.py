#!/usr/bin/env python3
# ruff: noqa: TRY003
"""Fail-closed validation of the candidate-local functorial source closure.

The checker deliberately operates on source files and a candidate manifest.  It
does not import the package: importing would allow the checkout's ambient
``PYTHONPATH`` to conceal a missing candidate file, which is the failure this
gate is intended to prevent.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import stat
import subprocess
import unicodedata
from dataclasses import dataclass
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from scripts.formal_release.stage2_git_batch import BaseTreeIndex, GitBatchError, git_blob_oid


CORE_ROOT = Path("src/mrw_functorial_kit/core")
BACKEND_MIGRATION_VERSIONS_ROOT = Path("main/backend/migrations/versions")
WORKFLOW_SELECTOR_PYTHON_ROOTS: tuple[str, ...] = (
    "main/backend",
    "main/ops",
    "src/mrw_functorial_kit",
    "ops",
    "scripts",
    "tests",
)
WORKFLOW_SELECTOR_SHELL_ROOTS: tuple[str, ...] = (
    "main/ops",
    "ops",
    "scripts",
)
WORKFLOW_SELECTOR_JSON_ROOTS: tuple[str, ...] = (
    "docs/governance",
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage0-evidence",
)
WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS: tuple[str, ...] = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind",
)
WORKFLOW_SELECTOR_MARKDOWN_ROOTS: tuple[str, ...] = (
    "development/latest-dev-docs/backend-docs/B_API",
)
WORKFLOW_SELECTOR_LOG_ROOTS: tuple[str, ...] = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage0-evidence",
)
WORKFLOW_SELECTOR_STATIC_EXACT_PATHS: frozenset[str] = frozenset(
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
WORKFLOW_SELECTOR_TEST_EVIDENCE_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "development/latest-dev-docs/automation-runs/"
        "crawler-public-replay-gate/2026-05-22/README.md",
        "development/latest-dev-docs/automation-runs/"
        "crawler-public-replay-gate/2026-05-22/crawler_public_replay_gate_check.json",
        "development/latest-dev-docs/automation-runs/"
        "crawler-public-replay-gate/2026-05-22/manifest.json",
        "development/latest-dev-docs/automation-runs/"
        "crawler-public-replay-shards/2026-05-22/output.public.shard-01.json",
        "development/latest-dev-docs/automation-runs/"
        "crawler-public-replay-shards/2026-05-22/output.public.shard-02.json",
        "development/latest-dev-docs/automation-runs/"
        "crawler-public-replay-shards/2026-05-22/output.public.shard-03.json",
        "development/latest-dev-docs/automation-runs/"
        "crawler-public-replay-shards/2026-05-22/output.public.shard-04.json",
        "development/latest-dev-docs/automation-runs/"
        "crawler-public-replay-shards/2026-05-22/output.public.shard-05.json",
        "development/latest-dev-docs/automation-runs/"
        "crawler-public-replay-shards/2026-05-22/shard_manifest.json",
        "development/latest-dev-docs/automation-runs/"
        "crawler-public-replay-shards/2026-05-22/shard_readback.json",
        "development/latest-dev-docs/automation-runs/"
        "crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/README.md",
        "development/latest-dev-docs/automation-runs/"
        "crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/"
        "a5_public_replay_gate_check.json",
        "development/latest-dev-docs/automation-runs/"
        "crawler-source-expansion-wave8-a7-validation-pack/2026-05-22/"
        "crawler_source_expansion_closure_check.json",
        "development/latest-dev-docs/automation-runs/"
        "deisolation-project-coherence/2026-05-14/"
        "local_index_lancedb_project_prototype.jsonl",
        "development/latest-dev-docs/automation-runs/"
        "frontend-coherence-and-searxng-gate/2026-05-14/"
        "local_index_lancedb_project_prototype.jsonl",
        "development/latest-dev-docs/automation-runs/"
        "llm-crawler-browser-replay-fixture/2026-05-22/replay.fixture.json",
        "development/latest-dev-docs/automation-runs/"
        "llm-crawler-high-js-public-replay/2026-05-22/manifest.json",
        "development/latest-dev-docs/automation-runs/"
        "local-index-lancedb-benchmark/2026-05-22/README.md",
        "development/latest-dev-docs/automation-runs/"
        "local-index-lancedb-benchmark/2026-05-22/benchmark_quality_results.json",
        "development/latest-dev-docs/automation-runs/"
        "local-index-lancedb-runtime-smoke/2026-05-22/runtime_smoke_results.json",
        "development/latest-dev-docs/automation-runs/"
        "search-provider-container-replay/2026-05-22/provider_trace_replay_summary.json",
        "development/latest-dev-docs/automation-runs/"
        "search-provider-trace-artifacts/2026-05-22/search_provider_trace_contract.json",
        "development/latest-dev-docs/automation-runs/"
        "source-library-live-probes/2026-05-22/output.json",
        "development/latest-dev-docs/automation-runs/"
        "source-library-replay-scaleout/2026-05-22/input.json",
        "development/latest-dev-docs/automation-runs/"
        "source-library-replay-scaleout/2026-05-22/output.json",
        "development/latest-dev-docs/automation-runs/"
        "source-library-replay-scaleout/2026-05-22/output.public.json",
        "development/latest-dev-docs/automation-runs/"
        "source-library-review-closure-batch/2026-05-22/review_batch.json",
        "development/latest-dev-docs/automation-runs/"
        "source-library-review-closure-batch2/2026-05-22/review_batch2.json",
        "development/latest-dev-docs/automation-runs/"
        "source-library-review-closure-batch3/2026-05-22/review_batch3.json",
        "development/latest-dev-docs/automation-runs/"
        "source-library-review-closure-batch4/2026-05-22/review_batch4.json",
        "development/latest-dev-docs/automation-runs/"
        "wave10-vectorization-quality-gate/2026-05-22/contract_summary.json",
        "development/latest-dev-docs/automation-runs/"
        "wave12-provider-readiness/2026-05-22/provider_readiness_summary.json",
        "development/latest-dev-docs/automation-runs/"
        "wave14-vectorization-provider-capability/2026-05-22/"
        "provider_capability_summary.json",
        "development/latest-dev-docs/automation-runs/"
        "wave18-vectorization-hybrid-readback/2026-05-22/hybrid_readback_contract.json",
        "development/latest-dev-docs/automation-runs/"
        "wave19-vectorization-provider-manifest/2026-05-22/provider_manifest_readback.json",
        "development/latest-dev-docs/automation-runs/"
        "wave30-vector-closure-gate/2026-05-23/README.md",
        "development/latest-dev-docs/automation-runs/"
        "wave55-live-embedding-provider/2026-05-23/README.md",
        "development/latest-dev-docs/automation-runs/"
        "wave55-live-embedding-provider/2026-05-23/live_embedding_provider_gate.json",
        "development/latest-dev-docs/automation-runs/"
        "wave55-oss-node-search-quality-gate/2026-05-23/oss_node_search_quality_gate.json",
        "development/latest-dev-docs/automation-runs/"
        "wave56-semantic-vector-quality-gate/2026-05-23/README.md",
        "development/latest-dev-docs/automation-runs/"
        "wave56-semantic-vector-quality-gate/2026-05-23/semantic_vector_quality_gate.json",
        "development/latest-dev-docs/automation-runs/"
        "wave8-search-vectorization-contract/2026-05-22/contract_summary.json",
    }
)
_SUCCESSOR_EVIDENCE_ROOT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
# Current generator projections read by successor_runtime; historical ownership
# and candidate snapshots remain governed by their existing recursive bindings.
WORKFLOW_SELECTOR_SUCCESSOR_PROJECTION_PATHS: frozenset[str] = frozenset(
    {
        f"{_SUCCESSOR_EVIDENCE_ROOT}/CapabilitySpecCompilationAndVerticalSlicesDecision.v1.json",
        *(
            f"{_SUCCESSOR_EVIDENCE_ROOT}/semantic-movement/fragments/{family}.v1.json"
            for family in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9")
        ),
        *(
            f"{_SUCCESSOR_EVIDENCE_ROOT}/semantic-movement/{name}.v1.json"
            for name in (
                "P1P3LegacyDonorSemanticMovementInventory",
                "P1P3SuccessorMovementMatrix",
                "P1P3SemanticMovementGate",
            )
        ),
    }
)
WORKFLOW_SELECTOR_EXACT_PATHS: frozenset[str] = (
    WORKFLOW_SELECTOR_STATIC_EXACT_PATHS
    | WORKFLOW_SELECTOR_TEST_EVIDENCE_EXACT_PATHS
    | WORKFLOW_SELECTOR_SUCCESSOR_PROJECTION_PATHS
)
STAGE1_PRODUCTION_BINDING_BUNDLE_ROOT = (
    "stage1-successor-evidence/stage1-production-contract-binding-successor-v1-r12"
)
STAGE1_PRODUCTION_BINDING_BUNDLE_FILES = frozenset(
    {
        "artifact-manifest.v1.json",
        "stage1-production-contract-binding-successor.v1.json",
    }
)
CURRENT_BYTE_BUNDLE_ROOT_FILES: Mapping[str, frozenset[str]] = {
    "stage1-successor-evidence/current-byte-remediation-v1/bindings": frozenset(
        {
            "artifact-manifest.v1.json",
            "build_current_byte_binding_successors.py",
            "check_current_byte_binding_successors.py",
            "current-byte-all-lines-closure.v2.json",
            "current-byte-binding-successors.v1.json",
            "test_current_byte_binding_successors.py",
        }
    ),
    "stage1-successor-evidence/current-byte-remediation-v2/bindings": frozenset(
        {
            "artifact-manifest.v2.json",
            "build_current_byte_binding_successors_v2.py",
            "check_current_byte_binding_successors_v2.py",
            "current-byte-binding-successors.v2.json",
            "test_current_byte_binding_successors_v2.py",
        }
    ),
    "stage1-successor-evidence/current-byte-remediation-v3/bindings": frozenset(
        {
            "artifact-manifest.v3.json",
            "build_current_byte_binding_successors_v3.py",
            "check_current_byte_binding_successors_v3.py",
            "current-byte-binding-successors.v3.json",
            "test_current_byte_binding_successors_v3.py",
        }
    ),
    "stage1-successor-evidence/current-byte-remediation-v4/bindings": frozenset(
        {
            "artifact-manifest.v4.json",
            "build_current_byte_binding_successors_v4.py",
            "check_current_byte_binding_successors_v4.py",
            "current-byte-binding-successors.v4.json",
            "test_current_byte_binding_successors_v4.py",
        }
    ),
    "stage1-successor-evidence/current-byte-remediation-v3/semantic-bindings": frozenset(
        {
            "artifact-manifest.v3.json",
            "build_semantic_binding_successors_v3.py",
            "check_semantic_binding_successors_v3.py",
            "semantic-binding-successors.v3.json",
            "test_semantic_binding_successors_v3.py",
        }
    ),
}
CURRENT_BYTE_BUNDLE_ROOTS: tuple[str, ...] = tuple(
    CURRENT_BYTE_BUNDLE_ROOT_FILES
)
CURRENT_BYTE_BUNDLE_SNAPSHOT_ROOTS: frozenset[str] = frozenset(
    root
    for root in CURRENT_BYTE_BUNDLE_ROOTS
    if "current-byte-remediation-v4" not in root
)
_LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
STAGE3_REMEDIATION_TEST_FIXTURE_ROOT = (
    "stage1-successor-evidence/stage3-v6-artifact-remediation-v1"
)
_STAGE3_REMEDIATION_PYTEST_RECEIPT_STEMS = (
    "focused-final",
    "package-focused-create-final",
    "package-focused-final",
    "source-selector-bound-final",
    "source-selector",
)
_STAGE3_REMEDIATION_FRONTEND_RECEIPT_STEMS = (
    "frontend-build",
    "frontend-frozen-install",
    "frontend-lint",
    "frontend-storybook",
    "frontend-typecheck",
)
STAGE3_REMEDIATION_TEST_FIXTURE_PATHS: frozenset[str] = frozenset(
    {
        "artifact-manifest.v1.json",
        "build_stage3_v6_artifact_remediation_v1.py",
        "check_stage3_v6_artifact_remediation_v1.py",
        "input-observation.v1.json",
        "stage3-v6-artifact-remediation-record.v1.json",
        "test_stage3_v6_artifact_remediation_v1.py",
        *(
            f"raw/{stem}.{suffix}"
            for stem in _STAGE3_REMEDIATION_PYTEST_RECEIPT_STEMS
            for suffix in ("json", "log", "xml")
        ),
        *(
            f"raw/{stem}.{suffix}"
            for stem in _STAGE3_REMEDIATION_FRONTEND_RECEIPT_STEMS
            for suffix in ("json", "log")
        ),
    }
)
STAGE3_REMEDIATION_CONTRACT_ROOT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release"
)
STAGE3_REMEDIATION_CONTRACT_PATH = (
    f"{STAGE3_REMEDIATION_CONTRACT_ROOT}/"
    "15_production-deployment-stage3-v6-contract.v1.md"
)
STAGE3_REMEDIATION_HISTORICAL_RECORD_ROOT = (
    "stage1-successor-evidence/stage2-v6-intake-remediation-v5"
)
STAGE3_REMEDIATION_HISTORICAL_RECORD_PATH = (
    f"{STAGE3_REMEDIATION_HISTORICAL_RECORD_ROOT}/"
    "stage2-v6-intake-remediation-record.v5.json"
)
WORKFLOW_SELECTOR_ROOTS: tuple[str, ...] = (
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
WORKFLOW_SELECTOR_CONFIG_ROOT = Path("main/backend")
FRONTEND_SELECTOR_ROOT = Path("main/frontend-modern")
FRONTEND_SELECTOR_SUBTREES: tuple[str, ...] = (
    "src",
    "tests",
    "scripts",
    ".storybook",
    "public",
)
FRONTEND_SELECTOR_ROOT_FILES: frozenset[str] = frozenset(
    {
        "Dockerfile",
        "eslint.config.js",
        "index.html",
        "nginx.conf",
        "package.json",
        "playwright.config.ts",
        "playwright.storybook.config.ts",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "tsconfig.app.json",
        "tsconfig.json",
        "tsconfig.node.json",
        "vite.config.ts",
    }
)
_WORKFLOW_SELECTOR_SOURCE_RUNTIME_PREFIX = Path(
    "main/backend/app/successor_runtime/runtime"
).parts
_WORKFLOW_SELECTOR_FORBIDDEN_COMPONENTS = frozenset(
    {
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".runtime",
        ".tmp",
        ".venv",
        ".virtualenv",
        "__pypackages__",
        "__pycache__",
        "cache",
        "caches",
        "node_modules",
        "runtime",
        "runtime-cache",
        "temp",
        "tmp",
        "venv",
        "virtualenv",
    }
)
_WORKFLOW_SELECTOR_SECRET_DIRECTORIES = frozenset(
    {".credentials", ".secrets", "credentials", "secrets"}
)
_WORKFLOW_SELECTOR_SECRET_FILES = frozenset(
    {
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".token",
        "credential",
        "credentials.json",
        "credentials.yaml",
        "credentials.yml",
        "id_ed25519",
        "id_rsa",
        "password",
        "password.txt",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "token.json",
        "token.yaml",
        "token.yml",
        "tokens.json",
    }
)
_WORKFLOW_SELECTOR_SECRET_SUFFIXES = (".key", ".p12", ".pem", ".pfx", ".token")
_FRONTEND_SELECTOR_EXCLUDED_COMPONENTS = frozenset(
    {
        ".cache",
        ".credentials",
        ".env",
        ".secrets",
        "__pycache__",
        "coverage",
        "credential",
        "credentials",
        "dist",
        "env",
        "environment",
        "environments",
        "log",
        "logs",
        "node_modules",
        "playwright-report",
        "secret",
        "secrets",
        "storybook-static",
        "test-results",
    }
)
_FRONTEND_SELECTOR_EXCLUDED_NAMES = frozenset({".ds_store"})
_FRONTEND_SELECTOR_EXCLUDED_SUFFIXES = (".tsbuildinfo",)
REQUIRED_CORE_MODULES: tuple[str, ...] = (
    "src/mrw_functorial_kit/core/w07_semantics.py",
    "src/mrw_functorial_kit/core/agent_service_semantics.py",
)

# These are the seven v4 consumers bound to the two missing modules.  Keeping
# the map closed prevents a silently reduced selector from turning a partial
# check into a PASS.
REQUIRED_CONSUMERS: Mapping[str, tuple[tuple[str, str], ...]] = {
    "main/backend/app/services/codex_oauth.py": (
        ("mrw_functorial_kit.core.agent_service_semantics", "codex_oauth_failures"),
    ),
    "main/backend/app/successor_runtime/language/compile.py": (
        ("mrw_functorial_kit.core.w07_semantics", "language_failures"),
    ),
    "main/backend/app/successor_runtime/language/object_contracts.py": (
        ("mrw_functorial_kit.core.w07_semantics", "language_failures"),
    ),
    "main/backend/app/services/agent_batch/task_contract.py": (
        ("mrw_functorial_kit.core.agent_service_semantics", "agent_batch_failures"),
    ),
    "main/backend/app/services/agent_batch/agent_loop.py": (
        ("mrw_functorial_kit.core.agent_service_semantics", "agent_batch_failures"),
    ),
    "main/backend/app/services/agent_sessions/service.py": (
        ("mrw_functorial_kit.core.agent_service_semantics", "agent_session_failures"),
    ),
    "main/backend/app/services/agent_sessions/store.py": (
        ("mrw_functorial_kit.core.agent_service_semantics", "agent_session_failures"),
    ),
}


class SourceClosureError(ValueError):
    """Raised when source, package exports, imports, or manifest are incomplete."""


@dataclass(frozen=True)
class SourceClosureResult:
    """Deterministic, non-authoritative witness returned by the checker."""

    required_modules: tuple[str, ...]
    consumers: tuple[str, ...]
    manifest_paths: tuple[str, ...]


@dataclass(frozen=True)
class _SelectorSpec:
    """Closed path policy shared by deterministic selector implementations."""

    roots: tuple[str, ...]
    label: str
    accepts_path: Callable[[str], bool]
    is_excluded_path: Callable[[str], bool]
    exact_paths: frozenset[str] = frozenset()
    reject_directory_symlink: bool = False
    reject_base_symlink_entry: bool = False
    reject_special_base_source: bool = False

    def in_scope(self, relative: str) -> bool:
        return relative in self.exact_paths or any(
            relative == scope or relative.startswith(scope + "/")
            for scope in self.roots
        )


class _DirectSourceReader:
    """Generic, checkout-local reader used only by the optional probe API."""

    def __init__(self, source_root: Path) -> None:
        self.root = source_root.resolve()

    def read(self, relative: str, *, label: str) -> bytes:
        path = self.root / relative
        try:
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise SourceClosureError(f"{label} must be a regular file: {relative}")
            payload = path.read_bytes()
            after = path.lstat()
        except OSError as exc:
            raise SourceClosureError(f"{label} is missing: {relative}") from exc
        if (
            not stat.S_ISREG(after.st_mode)
            or (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise SourceClosureError(f"{label} changed during read: {relative}")
        return payload


class _ProjectedCandidateReader:
    """Read exactly ``base tree + ordered manifest overlay``.

    The working checkout supplies bytes only for an explicit UPSERT.  An
    omitted path is read solely from the immutable ``BaseTreeIndex`` blob, and
    DELETE is represented as absent even if a checkout file happens to exist.
    """

    def __init__(
        self,
        source_root: Path,
        manifest: Mapping[str, Any],
        base_index: BaseTreeIndex,
    ) -> None:
        self.root = source_root.resolve()
        self.base_index = base_index
        source = manifest.get("source")
        if not isinstance(source, Mapping):
            raise SourceClosureError("manifest source is required for projected source closure")
        if source.get("base_oid") != base_index.base_oid:
            raise SourceClosureError("base tree index oid does not match manifest base_oid")
        if base_index.object_format != "sha1":
            raise SourceClosureError("base tree index object format is unsupported")
        try:
            index_root = Path(base_index.repo_root).resolve()
        except OSError as exc:
            raise SourceClosureError("base tree index repository root is invalid") from exc
        self.base_root = index_root

        rows = manifest.get("entries")
        if not isinstance(rows, list):
            raise SourceClosureError("manifest entries are required for projected source closure")
        self._overlay: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise SourceClosureError("manifest entry is invalid")
            path = row.get("path")
            operation = row.get("operation")
            if not isinstance(path, str) or not isinstance(operation, str):
                raise SourceClosureError("manifest entry path or operation is invalid")
            _validate_relative(path)
            if operation not in {"UPSERT", "DELETE"}:
                raise SourceClosureError(f"manifest entry operation is invalid: {path}")
            if path in self._overlay:
                raise SourceClosureError(f"manifest entry path is duplicated: {path}")
            # Keep the manifest order explicit even though the v2 structure
            # currently forbids duplicate paths.
            self._overlay[path] = row

    def read(self, relative: str, *, label: str) -> bytes:
        _validate_relative(relative)
        row = self._overlay.get(relative)
        if row is not None:
            if row["operation"] == "DELETE":
                raise SourceClosureError(f"{label} is missing: {relative}")
            return self._read_upsert(relative, row, label=label)
        return self._read_base(relative, label=label)

    def _read_upsert(self, relative: str, row: Mapping[str, Any], *, label: str) -> bytes:
        path = self.root / relative
        try:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise SourceClosureError(f"{label} must be a regular file: {relative}")
            payload = path.read_bytes()
            after = path.lstat()
        except OSError as exc:
            raise SourceClosureError(f"{label} is missing: {relative}") from exc
        if (
            not stat.S_ISREG(after.st_mode)
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise SourceClosureError(f"{label} changed during read: {relative}")
        mode = "100755" if after.st_mode & 0o111 else "100644"
        digest = hashlib.sha256(payload).hexdigest()
        try:
            blob = git_blob_oid(payload, object_format=self.base_index.object_format)
        except GitBatchError as exc:
            raise SourceClosureError(f"cannot hash projected UPSERT: {relative}") from exc
        if (row.get("mode"), row.get("sha256"), row.get("blob")) != (mode, digest, blob):
            raise SourceClosureError(
                f"projected UPSERT bytes, mode, sha256, or blob drift: {relative}"
            )
        return payload

    def _read_base(self, relative: str, *, label: str) -> bytes:
        try:
            entry = self.base_index.lookup(relative)
        except GitBatchError as exc:
            raise SourceClosureError(f"cannot read base tree entry: {relative}") from exc
        if entry is None:
            raise SourceClosureError(f"{label} is missing: {relative}")
        if entry.mode not in {"100644", "100755"}:
            raise SourceClosureError(f"{label} must be a regular file: {relative}")
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_NO_REPLACE_OBJECTS": "1",
            }
        )
        completed = subprocess.run(
            ("git", "-C", str(self.base_root), "cat-file", "blob", entry.oid),
            check=False,
            capture_output=True,
            env=env,
        )
        if completed.returncode:
            raise SourceClosureError(f"cannot read base tree blob: {relative}")
        payload = completed.stdout
        try:
            actual = git_blob_oid(payload, object_format=self.base_index.object_format)
        except GitBatchError as exc:
            raise SourceClosureError(f"cannot hash base tree blob: {relative}") from exc
        if actual != entry.oid:
            raise SourceClosureError(f"base tree blob mismatch: {relative}")
        return payload


def _validate_relative(relative: str) -> None:
    candidate = Path(relative)
    if (
        not relative
        or candidate.is_absolute()
        or candidate.as_posix() != relative
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or "\\" in relative
        or "\x00" in relative
    ):
        raise SourceClosureError(f"projected source path is invalid: {relative!r}")


def _is_workflow_selector_path(relative: str) -> bool:
    path = Path(relative)
    if relative in WORKFLOW_SELECTOR_EXACT_PATHS:
        return True
    if _is_current_byte_bundle_path(relative):
        return True
    if _is_stage1_production_binding_bundle_path(relative):
        return True
    if _is_stage3_remediation_test_fixture_path(relative):
        return True
    if relative == STAGE3_REMEDIATION_CONTRACT_PATH:
        return True
    if relative == STAGE3_REMEDIATION_HISTORICAL_RECORD_PATH:
        return True
    if path.suffix == ".py" and any(
        relative == root or relative.startswith(root + "/")
        for root in WORKFLOW_SELECTOR_PYTHON_ROOTS
    ):
        return True
    if path.suffix == ".sh" and any(
        relative == root or relative.startswith(root + "/")
        for root in WORKFLOW_SELECTOR_SHELL_ROOTS
    ):
        return True
    if path.suffix == ".json":
        if any(
            relative == root or relative.startswith(root + "/")
            for root in WORKFLOW_SELECTOR_JSON_ROOTS
        ):
            return True
        if any(
            relative.startswith(root + "/")
            and "sidecar-inputs" in Path(relative).relative_to(root).parts[:-1]
            for root in WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS
        ):
            return True
    if path.suffix == ".log" and any(
        relative.startswith(root + "/") for root in WORKFLOW_SELECTOR_LOG_ROOTS
    ):
        return True
    if path.suffix == ".md" and any(
        relative == root or relative.startswith(root + "/")
        for root in WORKFLOW_SELECTOR_MARKDOWN_ROOTS
    ):
        return True
    return (
        path.parent == WORKFLOW_SELECTOR_CONFIG_ROOT
        and (
            path.name == "pytest.ini"
            or (
                path.name.startswith("requirements")
                and path.suffix in {".in", ".txt"}
            )
        )
    )


def _is_current_byte_bundle_path(relative: str) -> bool:
    for root, root_files in CURRENT_BYTE_BUNDLE_ROOT_FILES.items():
        prefix = root + "/"
        if not relative.startswith(prefix):
            continue
        below = Path(relative[len(prefix) :]).parts
        if len(below) == 1:
            return below[0] in root_files
        return (
            root in CURRENT_BYTE_BUNDLE_SNAPSHOT_ROOTS
            and len(below) == 2
            and below[0] == "snapshots"
            and _LOWER_SHA256.fullmatch(below[1]) is not None
        )
    return False


def _is_stage1_production_binding_bundle_path(relative: str) -> bool:
    prefix = STAGE1_PRODUCTION_BINDING_BUNDLE_ROOT + "/"
    return (
        relative.startswith(prefix)
        and relative[len(prefix) :] in STAGE1_PRODUCTION_BINDING_BUNDLE_FILES
    )


def _is_stage3_remediation_test_fixture_path(relative: str) -> bool:
    prefix = STAGE3_REMEDIATION_TEST_FIXTURE_ROOT + "/"
    return (
        relative.startswith(prefix)
        and relative[len(prefix) :] in STAGE3_REMEDIATION_TEST_FIXTURE_PATHS
    )


def _is_backend_migration_version_path(relative: str) -> bool:
    path = Path(relative)
    return path.parent == BACKEND_MIGRATION_VERSIONS_ROOT and path.suffix == ".py"


def _is_excluded_workflow_selector_path(relative: str) -> bool:
    path = Path(relative)
    lowered_parts = tuple(part.casefold() for part in path.parts)
    source_runtime = (
        lowered_parts[: len(_WORKFLOW_SELECTOR_SOURCE_RUNTIME_PREFIX)]
        == _WORKFLOW_SELECTOR_SOURCE_RUNTIME_PREFIX
    )
    if any(
        (
            part in _WORKFLOW_SELECTOR_FORBIDDEN_COMPONENTS
            or part.startswith(".venv")
            or part.startswith("venv-")
            or part.startswith("virtualenv-")
        )
        and not (part == "runtime" and source_runtime)
        for part in lowered_parts
    ):
        return True
    if any(part in _WORKFLOW_SELECTOR_SECRET_DIRECTORIES for part in lowered_parts[:-1]):
        return True
    filename = path.name.casefold()
    return filename in _WORKFLOW_SELECTOR_SECRET_FILES or filename.endswith(
        _WORKFLOW_SELECTOR_SECRET_SUFFIXES
    )


def _validate_workflow_selector_relative(relative: str) -> None:
    _validate_relative(relative)
    if unicodedata.normalize("NFC", relative) != relative:
        raise SourceClosureError(f"workflow selector path is not NFC-normalized: {relative!r}")
    if not _is_workflow_selector_path(relative):
        raise SourceClosureError(f"workflow selector path is out of closure: {relative!r}")
    if _is_excluded_workflow_selector_path(relative):
        raise SourceClosureError(f"workflow selector path is excluded: {relative!r}")


def _is_frontend_selector_path(relative: str) -> bool:
    prefix = FRONTEND_SELECTOR_ROOT.as_posix() + "/"
    if not relative.startswith(prefix):
        return False
    relative_parts = Path(relative[len(prefix) :]).parts
    if len(relative_parts) == 1:
        return relative_parts[0] in FRONTEND_SELECTOR_ROOT_FILES
    return len(relative_parts) > 1 and relative_parts[0] in FRONTEND_SELECTOR_SUBTREES


def _is_excluded_frontend_selector_path(relative: str) -> bool:
    path = Path(relative)
    if any(part.casefold() in _FRONTEND_SELECTOR_EXCLUDED_COMPONENTS for part in path.parts):
        return True
    filename = path.name.casefold()
    return filename in _FRONTEND_SELECTOR_EXCLUDED_NAMES or filename.endswith(
        _FRONTEND_SELECTOR_EXCLUDED_SUFFIXES
    )


def _validate_frontend_selector_relative(relative: str) -> None:
    _validate_relative(relative)
    if unicodedata.normalize("NFC", relative) != relative:
        raise SourceClosureError(f"frontend selector path is not NFC-normalized: {relative!r}")
    if not _is_frontend_selector_path(relative):
        raise SourceClosureError(f"frontend selector path is out of closure: {relative!r}")
    if _is_excluded_frontend_selector_path(relative):
        raise SourceClosureError(f"frontend selector path is excluded: {relative!r}")


def _read_selector_file(
    source_root: Path,
    relative: str,
    *,
    label: str = "workflow",
) -> tuple[bytes, str]:
    path = source_root / relative
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise SourceClosureError(f"{label} selector source is not a regular file: {relative}")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise SourceClosureError(f"{label} selector source is unreadable: {relative}") from exc
    if (
        not stat.S_ISREG(after.st_mode)
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise SourceClosureError(f"workflow selector source changed during read: {relative}")
    return payload, "100755" if after.st_mode & 0o111 else "100644"


def _selector_checkout_paths(source_root: Path, *, spec: _SelectorSpec) -> tuple[str, ...]:
    found: set[str] = set()
    for relative in sorted(spec.exact_paths):
        path = source_root / relative
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.lstat().st_mode):
            raise SourceClosureError(
                f"{spec.label} selector source is not a regular file: {relative}"
            )
        if spec.accepts_path(relative) and not spec.is_excluded_path(relative):
            found.add(relative)
    for scope in spec.roots:
        scope_path = source_root / scope
        if not scope_path.exists():
            continue
        if not scope_path.is_dir() or scope_path.is_symlink():
            raise SourceClosureError(f"{spec.label} selector scope is not a directory: {scope}")
        for directory, directory_names, file_names in os.walk(scope_path, followlinks=False):
            directory_path = Path(directory)
            for name in directory_names:
                child = directory_path / name
                if child.is_symlink():
                    if spec.reject_directory_symlink:
                        probe = (child / "__probe__").relative_to(source_root).as_posix()
                        if spec.accepts_path(probe):
                            raise SourceClosureError(
                                f"{spec.label} selector directory is a symlink: "
                                f"{child.relative_to(source_root).as_posix()}"
                            )
                    probe = (child / "__probe__").relative_to(source_root).as_posix()
            directory_names[:] = sorted(
                name
                for name in directory_names
                if not (directory_path / name).is_symlink()
                and not spec.is_excluded_path(
                    (directory_path / name / "__probe__.py")
                    .relative_to(source_root)
                    .as_posix()
                )
            )
            for name in sorted(file_names):
                path = directory_path / name
                relative = path.relative_to(source_root).as_posix()
                if not spec.accepts_path(relative):
                    continue
                if spec.is_excluded_path(relative):
                    continue
                _validate_relative(relative)
                if unicodedata.normalize("NFC", relative) != relative:
                    raise SourceClosureError(
                        f"{spec.label} selector path is not NFC-normalized: {relative!r}"
                    )
                metadata = path.lstat()
                if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                    raise SourceClosureError(
                        f"{spec.label} selector source is not a regular file: {relative}"
                    )
                found.add(relative)
    return tuple(sorted(found))


def _base_selector_paths(
    base_index: BaseTreeIndex,
    *,
    spec: _SelectorSpec,
) -> tuple[str, ...]:
    found: list[str] = []
    for relative, entry in base_index.items():
        if not spec.in_scope(relative) or not spec.accepts_path(relative):
            continue
        try:
            looked_up = base_index.lookup(relative)
        except GitBatchError as exc:
            raise SourceClosureError(f"cannot read base tree entry: {relative}") from exc
        if looked_up is None:
            continue
        if entry.mode == "120000" and spec.reject_base_symlink_entry:
            raise SourceClosureError(f"{spec.label} selector base source is a symlink: {relative}")
        if (
            entry.kind != "blob"
            or entry.mode not in {"100644", "100755"}
            or spec.is_excluded_path(relative)
        ):
            continue
        _validate_relative(relative)
        if unicodedata.normalize("NFC", relative) != relative:
            raise SourceClosureError(
                f"{spec.label} selector path is not NFC-normalized: {relative!r}"
            )
        found.append(relative)
    return tuple(found)


def _selector_delta(
    source_root: Path,
    *,
    base_index: BaseTreeIndex,
    spec: _SelectorSpec,
) -> tuple[tuple[str, str], ...]:
    try:
        resolved_root = source_root.resolve(strict=True)
    except OSError as exc:
        raise SourceClosureError(f"{spec.label} selector source root is missing") from exc
    if not resolved_root.is_dir() or resolved_root.is_symlink():
        raise SourceClosureError(f"{spec.label} selector source root must be a directory")

    checkout_paths = _selector_checkout_paths(resolved_root, spec=spec)
    operations: dict[str, str] = {}
    for relative in checkout_paths:
        try:
            payload, mode = _read_selector_file(resolved_root, relative, label=spec.label)
            blob = git_blob_oid(payload, object_format=base_index.object_format)
        except GitBatchError as exc:
            raise SourceClosureError(f"cannot hash {spec.label} selector source: {relative}") from exc
        entry = base_index.lookup(relative)
        if entry is None or entry.mode != mode or entry.oid != blob:
            operations[relative] = "UPSERT"

    for relative in _base_selector_paths(base_index, spec=spec):
        path = resolved_root / relative
        try:
            metadata = path.lstat()
        except OSError:
            operations[relative] = "DELETE"
            continue
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            if spec.reject_special_base_source:
                raise SourceClosureError(
                    f"{spec.label} selector source is not a regular file: {relative}"
                )
            operations[relative] = "DELETE"
            continue
        if not path.is_symlink() and path.is_file() and stat.S_ISREG(path.lstat().st_mode):
            continue
        operations[relative] = "DELETE"

    return tuple(
        (operation, relative)
        for relative, operation in sorted(operations.items(), key=lambda item: item[1])
    )


def _workflow_selector_delta(
    source_root: Path,
    *,
    base_index: BaseTreeIndex,
) -> tuple[tuple[str, str], ...]:
    spec = _SelectorSpec(
        roots=WORKFLOW_SELECTOR_ROOTS,
        label="workflow",
        accepts_path=_is_workflow_selector_path,
        is_excluded_path=_is_excluded_workflow_selector_path,
        exact_paths=WORKFLOW_SELECTOR_EXACT_PATHS,
    )
    return _selector_delta(source_root, base_index=base_index, spec=spec)


def _frontend_selector_delta(
    source_root: Path,
    *,
    base_index: BaseTreeIndex,
) -> tuple[tuple[str, str], ...]:
    spec = _SelectorSpec(
        roots=(FRONTEND_SELECTOR_ROOT.as_posix(),),
        label="frontend",
        accepts_path=_is_frontend_selector_path,
        is_excluded_path=_is_excluded_frontend_selector_path,
        reject_directory_symlink=True,
        reject_base_symlink_entry=True,
        reject_special_base_source=True,
    )
    return _selector_delta(source_root, base_index=base_index, spec=spec)


def _selector_manifest_rows(
    manifest: Mapping[str, Any],
    *,
    spec: _SelectorSpec,
) -> dict[str, str]:
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise SourceClosureError(f"{spec.label} selector manifest entries are required")
    rows: dict[str, str] = {}
    for raw_row in cast(list[Any], entries):
        if not isinstance(raw_row, Mapping):
            raise SourceClosureError(f"{spec.label} selector manifest entry is invalid")
        row = cast(Mapping[str, Any], raw_row)
        relative = row.get("path")
        operation = row.get("operation")
        if not isinstance(relative, str) or not isinstance(operation, str):
            raise SourceClosureError(f"{spec.label} selector manifest path or operation is invalid")
        _validate_relative(relative)
        if not spec.in_scope(relative) or not spec.accepts_path(relative):
            continue
        if unicodedata.normalize("NFC", relative) != relative:
            raise SourceClosureError(
                f"{spec.label} selector path is not NFC-normalized: {relative!r}"
            )
        if spec.is_excluded_path(relative):
            raise SourceClosureError(f"{spec.label} selector path is excluded: {relative!r}")
        if operation not in {"UPSERT", "DELETE"}:
            raise SourceClosureError(f"{spec.label} selector manifest operation is invalid: {relative}")
        if relative in rows:
            raise SourceClosureError(f"{spec.label} selector manifest path is duplicated: {relative}")
        rows[relative] = operation
    return rows


def _backend_migration_version_paths(
    source_root: Path,
    *,
    base_index: BaseTreeIndex,
) -> tuple[set[str], set[str]]:
    """Return checkout-expected and immutable-base migration path sets."""

    base_paths = {
        relative
        for relative, entry in base_index.items()
        if _is_backend_migration_version_path(relative)
        and entry.kind == "blob"
        and entry.mode in {"100644", "100755"}
    }
    checkout_paths: set[str] = set()
    resolved_root = source_root.resolve()
    root = resolved_root / BACKEND_MIGRATION_VERSIONS_ROOT
    if root.exists():
        if not root.is_dir() or root.is_symlink():
            raise SourceClosureError(
                "backend migration versions root must be a directory"
            )
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            relative = path.relative_to(resolved_root).as_posix()
            if not _is_backend_migration_version_path(relative):
                continue
            metadata = path.lstat()
            if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                raise SourceClosureError(
                    f"backend migration version is not a regular file: {relative}"
                )
            checkout_paths.add(relative)
    return checkout_paths, base_paths


def _check_backend_migration_manifest_projection(
    source_root: Path,
    manifest: Mapping[str, Any],
    rows: Mapping[str, str],
    *,
    base_index: BaseTreeIndex,
) -> None:
    """Compare migration paths and validate the exact projected revision graph."""

    expected, base_paths = _backend_migration_version_paths(
        source_root,
        base_index=base_index,
    )
    projected = set(base_paths)
    for relative, operation in rows.items():
        if not _is_backend_migration_version_path(relative):
            continue
        if operation == "UPSERT":
            projected.add(relative)
        else:
            projected.discard(relative)

    missing = sorted(expected - projected)
    extra = sorted(projected - expected)
    if missing:
        raise SourceClosureError(
            "backend migration manifest projection is incomplete: " + ", ".join(missing)
        )
    if extra:
        raise SourceClosureError(
            "backend migration manifest projection has unexpected paths: "
            + ", ".join(extra)
        )

    reader = _ProjectedCandidateReader(source_root, manifest, base_index)
    revisions: dict[str, tuple[str, ...]] = {}
    revision_paths: dict[str, str] = {}
    for relative in sorted(projected):
        tree = _read_ast(reader, relative, label="backend migration")
        revision = _literal_assignment(tree, "revision", relative)
        down_revision = _literal_assignment(tree, "down_revision", relative)
        if not isinstance(revision, str) or not revision.strip():
            raise SourceClosureError(
                f"backend migration revision must be a non-empty string literal: {relative}"
            )
        parents = _normalize_down_revisions(down_revision, relative)
        if revision in revisions:
            raise SourceClosureError(
                "backend migration revision is duplicated: "
                f"{revision}: {revision_paths[revision]}, {relative}"
            )
        revisions[revision] = parents
        revision_paths[revision] = relative

    known = set(revisions)
    for revision, parents in revisions.items():
        for parent in parents:
            if parent not in known:
                raise SourceClosureError(
                    f"backend migration {revision} references missing down_revision {parent}"
                )


def _literal_assignment(tree: ast.Module, name: str, relative: str) -> Any:
    for node in tree.body:
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            value = node.value
        if value is None:
            continue
        try:
            return ast.literal_eval(value)
        except (ValueError, TypeError) as exc:
            raise SourceClosureError(
                f"backend migration {name} must be literal: {relative}"
            ) from exc
    raise SourceClosureError(f"backend migration {name} is missing: {relative}")


def _normalize_down_revisions(value: Any, relative: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parents = (value,)
    elif isinstance(value, (tuple, list)):
        parents = tuple(value)
    else:
        raise SourceClosureError(
            f"backend migration down_revision must be a literal string, sequence, or None: {relative}"
        )
    if any(not isinstance(parent, str) or not parent.strip() for parent in parents):
        raise SourceClosureError(
            f"backend migration down_revision contains an invalid parent: {relative}"
        )
    return cast(tuple[str, ...], parents)


def _read_ast(reader: _DirectSourceReader | _ProjectedCandidateReader, path: str, *, label: str) -> ast.Module:
    payload = reader.read(path, label=label)
    try:
        return ast.parse(payload.decode("utf-8"), filename=path)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise SourceClosureError(f"{label} is not valid UTF-8 Python: {path}") from exc


def _defined_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _literal_exports(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        value = node.value
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            result: set[str] = set()
            for item in value.elts:
                if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                    raise SourceClosureError("core package __all__ must contain string literals")
                result.add(item.value)
            return result
        raise SourceClosureError("core package __all__ must be a literal sequence")
    raise SourceClosureError("core package __all__ is missing")


def _module_path(dotted: str) -> str:
    prefix = "mrw_functorial_kit.core."
    if dotted.startswith(prefix):
        return (CORE_ROOT / (dotted[len(prefix) :] + ".py")).as_posix()
    if dotted == "mrw_functorial_kit.core":
        return (CORE_ROOT / "__init__.py").as_posix()
    raise SourceClosureError(f"unsupported internal import: {dotted}")


def _package_import_dotted(node: ast.ImportFrom, package_parts: tuple[str, ...]) -> str | None:
    """Resolve an absolute or relative import against a Python package."""

    if node.module is None:
        return None
    if node.level == 0:
        return node.module
    if node.level > len(package_parts) + 1:
        return None
    anchor = package_parts[: len(package_parts) - (node.level - 1)]
    return ".".join((*anchor, node.module))


def _manifest_paths(manifest: Mapping[str, Any] | None) -> tuple[str, ...]:
    if manifest is None:
        return ()
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise SourceClosureError("manifest entries are required for source closure")
    entries = cast(list[Any], entries)
    paths: list[str] = []
    for raw_row in entries:
        if not isinstance(raw_row, Mapping):
            raise SourceClosureError("manifest entry path is invalid")
        row = cast(Mapping[str, Any], raw_row)
        if not isinstance(row.get("path"), str):
            raise SourceClosureError("manifest entry path is invalid")
        if row.get("operation") != "UPSERT":
            continue
        paths.append(row["path"])
    return tuple(sorted(set(paths)))


def check_source_closure(
    source_root: Path,
    *,
    manifest: Mapping[str, Any] | None = None,
    required_modules: Sequence[str] = REQUIRED_CORE_MODULES,
    base_index: BaseTreeIndex | None = None,
) -> SourceClosureResult:
    """Validate candidate-local files, exports, direct consumers, and intake paths.

    The function is strict once an MRW functorial package is present.  Callers
    may use :func:`check_source_closure_if_present` for generic temporary
    repositories that do not contain this package.
    """

    if base_index is None:
        reader: _DirectSourceReader | _ProjectedCandidateReader = _DirectSourceReader(source_root)
    else:
        if manifest is None:
            raise SourceClosureError("manifest is required for projected source closure")
        reader = _ProjectedCandidateReader(source_root, manifest, base_index)
    package_init = (CORE_ROOT / "__init__.py").as_posix()

    required = tuple(dict.fromkeys(path.replace("\\", "/") for path in required_modules))
    if set(required) != set(REQUIRED_CORE_MODULES):
        raise SourceClosureError("required source list must contain the two Stage 1 core modules")
    for relative in required:
        _read_ast(reader, relative, label="required source module")

    package_tree = _read_ast(reader, package_init, label="core package")
    defined = _defined_names(package_tree)
    declared = _literal_exports(package_tree)
    unknown_declared = sorted(declared - defined)
    if unknown_declared:
        raise SourceClosureError(
            "unknown exported name(s): " + ", ".join(unknown_declared)
        )

    # Every package-level relative import must resolve to a local module and a
    # symbol defined by that module.  This catches both missing files and typoed
    # exports without importing anything from the ambient environment.
    for node in ast.walk(package_tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        dotted = _package_import_dotted(node, ("mrw_functorial_kit", "core"))
        if dotted is None or dotted != "mrw_functorial_kit.core" and not dotted.startswith(
            "mrw_functorial_kit.core."
        ):
            continue
        if dotted == "mrw_functorial_kit.core":
            target_names = defined
        else:
            target = _module_path(dotted)
            target_tree = _read_ast(reader, target, label="declared core module")
            target_names = _defined_names(target_tree)
        for alias in node.names:
            if alias.name == "*":
                raise SourceClosureError("star imports are not allowed in core package exports")
            if alias.name not in target_names:
                raise SourceClosureError(
                    f"unknown exported name: {dotted}.{alias.name}"
                )

    for consumer, imports in REQUIRED_CONSUMERS.items():
        tree = _read_ast(reader, consumer, label="required consumer")
        observed: set[tuple[str, str]] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level != 0 or node.module is None:
                continue
            if not node.module.startswith("mrw_functorial_kit.core"):
                continue
            target = _module_path(node.module)
            target_tree = _read_ast(reader, target, label="consumer import module")
            target_names = _defined_names(target_tree)
            for alias in node.names:
                if alias.name == "*":
                    raise SourceClosureError(f"star import in required consumer: {consumer}")
                if alias.name not in target_names:
                    raise SourceClosureError(
                        f"consumer import export is unknown: {consumer}: {node.module}.{alias.name}"
                    )
                observed.add((node.module, alias.name))
        missing = sorted(set(imports) - observed)
        if missing:
            raise SourceClosureError(
                f"required consumer import missing: {consumer}: {missing[0][0]}.{missing[0][1]}"
            )

    manifest_paths = _manifest_paths(manifest)
    if manifest is not None:
        omitted = sorted(set(required) - set(manifest_paths))
        if omitted:
            raise SourceClosureError("source/manifest omission: " + ", ".join(omitted))
    return SourceClosureResult(required, tuple(REQUIRED_CONSUMERS), manifest_paths)


def check_source_closure_if_present(
    source_root: Path,
) -> SourceClosureResult | None:
    """Run the strict checker only for repositories containing the package."""

    if not (source_root / CORE_ROOT / "__init__.py").is_file():
        return None
    return check_source_closure(source_root)


def is_mrw_projected_candidate(
    source_root: Path,
    manifest: Mapping[str, Any],
    *,
    base_index: BaseTreeIndex | None = None,
) -> bool:
    """Identify an MRW candidate without consulting a projected file fallback.

    This is intentionally not an optional projected checker.  With a base
    index, detection is derived only from ``base tree + ordered overlay``;
    checkout-only files are not candidate files.  Once that projection claims
    the MRW core namespace, Stage 2 must run :func:`check_source_closure` and a
    missing projected package is an error rather than an absent-probe result.
    """

    prefix = CORE_ROOT.as_posix() + "/"
    rows = manifest.get("entries")
    if base_index is not None:
        # Projected detection must observe the same path set as the projected
        # reader.  The live checkout is only the byte source for declared
        # UPSERTs; an undeclared checkout-only package is not in the candidate.
        projected = {
            path for path, _entry in base_index.items() if path.startswith(prefix)
        }
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                path = row.get("path")
                operation = row.get("operation")
                if not isinstance(path, str) or not path.startswith(prefix):
                    continue
                if operation == "UPSERT":
                    projected.add(path)
                elif operation == "DELETE":
                    projected.discard(path)
        return bool(projected)

    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping) and isinstance(row.get("path"), str):
                if row["path"].startswith(prefix):
                    return True
    return (source_root / CORE_ROOT).exists()


def compute_workflow_selector_delta(
    source_root: Path,
    *,
    base_index: BaseTreeIndex,
) -> tuple[tuple[str, str], ...]:
    """Compute the current checkout's complete workflow selector delta.

    The result contains one path-major ordered ``(operation, path)`` row for
    every changed Python source and workflow test configuration.  Unchanged
    base files do not require UPSERT rows; a later projected reader can obtain
    them from ``base_index``.
    """

    return _workflow_selector_delta(source_root, base_index=base_index)


def check_workflow_selector_manifest_closure(
    source_root: Path,
    manifest: Mapping[str, Any],
    *,
    base_index: BaseTreeIndex,
) -> tuple[tuple[str, str], ...]:
    """Verify that manifest entries cover the complete workflow selector delta.

    Extra safe manifest paths are allowed for callers that combine selectors.
    Every expected path must occur exactly once with the same operation, and a
    manifest carrying a base binding must match ``base_index.base_oid``.  On
    success this returns the complete expected delta unchanged.
    """

    expected = _workflow_selector_delta(source_root, base_index=base_index)
    source = manifest.get("source")
    if source is not None:
        if not isinstance(source, Mapping) or source.get("base_oid") != base_index.base_oid:
            raise SourceClosureError("workflow selector manifest base oid does not match base tree index")
    workflow_spec = _SelectorSpec(
        roots=WORKFLOW_SELECTOR_ROOTS,
        label="workflow",
        accepts_path=_is_workflow_selector_path,
        is_excluded_path=_is_excluded_workflow_selector_path,
        exact_paths=WORKFLOW_SELECTOR_EXACT_PATHS,
    )
    rows = _selector_manifest_rows(manifest, spec=workflow_spec)
    _check_backend_migration_manifest_projection(
        source_root,
        manifest,
        rows,
        base_index=base_index,
    )
    for operation, relative in expected:
        observed = rows.get(relative)
        if observed is None:
            raise SourceClosureError(f"workflow selector manifest closure gap: {relative}")
        if observed != operation:
            raise SourceClosureError(
                f"workflow selector manifest operation mismatch: {relative}: expected {operation}"
            )
    return expected


def compute_frontend_selector_delta(
    source_root: Path,
    *,
    base_index: BaseTreeIndex,
) -> tuple[tuple[str, str], ...]:
    """Compute the complete deterministic frontend selector delta.

    The selector covers regular source resources below the five declared
    frontend subtrees plus the closed root-file list.  Output rows use the same
    path-major ``(operation, POSIX path string)`` shape as workflow selectors.
    """

    return _frontend_selector_delta(source_root, base_index=base_index)


def check_frontend_selector_manifest_closure(
    source_root: Path,
    manifest: Mapping[str, Any],
    *,
    base_index: BaseTreeIndex,
) -> tuple[tuple[str, str], ...]:
    """Verify exact operation coverage of the complete frontend selector delta.

    Out-of-selector entries are ignored so combined candidate manifests remain
    valid.  An in-selector excluded path, duplicate path, missing delta row, or
    stale operation is rejected.
    """

    expected = _frontend_selector_delta(source_root, base_index=base_index)
    source = manifest.get("source")
    if source is not None:
        if not isinstance(source, Mapping) or source.get("base_oid") != base_index.base_oid:
            raise SourceClosureError("frontend selector manifest base oid does not match base tree index")
    spec = _SelectorSpec(
        roots=(FRONTEND_SELECTOR_ROOT.as_posix(),),
        label="frontend",
        accepts_path=_is_frontend_selector_path,
        is_excluded_path=_is_excluded_frontend_selector_path,
    )
    rows = _selector_manifest_rows(manifest, spec=spec)
    for operation, relative in expected:
        observed = rows.get(relative)
        if observed is None:
            raise SourceClosureError(f"frontend selector manifest closure gap: {relative}")
        if observed != operation:
            raise SourceClosureError(
                f"frontend selector manifest operation mismatch: {relative}: expected {operation}"
            )
    return expected


# Explicit aliases make the contract convenient for shell/checker callers and
# preserve one implementation rather than creating parallel gate logic.
validate_source_closure = check_source_closure
assert_source_closure = check_source_closure


__all__ = [
    "BACKEND_MIGRATION_VERSIONS_ROOT",
    "CORE_ROOT",
    "CURRENT_BYTE_BUNDLE_ROOT_FILES",
    "CURRENT_BYTE_BUNDLE_ROOTS",
    "CURRENT_BYTE_BUNDLE_SNAPSHOT_ROOTS",
    "STAGE3_REMEDIATION_TEST_FIXTURE_PATHS",
    "STAGE3_REMEDIATION_TEST_FIXTURE_ROOT",
    "STAGE3_REMEDIATION_CONTRACT_PATH",
    "STAGE3_REMEDIATION_CONTRACT_ROOT",
    "STAGE3_REMEDIATION_HISTORICAL_RECORD_PATH",
    "STAGE3_REMEDIATION_HISTORICAL_RECORD_ROOT",
    "REQUIRED_CORE_MODULES",
    "REQUIRED_CONSUMERS",
    "SourceClosureError",
    "SourceClosureResult",
    "WORKFLOW_SELECTOR_ROOTS",
    "WORKFLOW_SELECTOR_EXACT_PATHS",
    "WORKFLOW_SELECTOR_STATIC_EXACT_PATHS",
    "WORKFLOW_SELECTOR_TEST_EVIDENCE_EXACT_PATHS",
    "WORKFLOW_SELECTOR_PYTHON_ROOTS",
    "WORKFLOW_SELECTOR_SHELL_ROOTS",
    "WORKFLOW_SELECTOR_JSON_ROOTS",
    "WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS",
    "WORKFLOW_SELECTOR_LOG_ROOTS",
    "assert_source_closure",
    "check_source_closure",
    "check_source_closure_if_present",
    "check_workflow_selector_manifest_closure",
    "check_frontend_selector_manifest_closure",
    "compute_workflow_selector_delta",
    "compute_frontend_selector_delta",
    "validate_source_closure",
]
