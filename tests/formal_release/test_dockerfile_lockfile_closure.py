from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DOCKERFILE = ROOT / "main/backend/Dockerfile"
FRONTEND_DOCKERFILE = ROOT / "main/frontend-modern/Dockerfile"
EXPECTED_BASES = {
    "python:3.11-slim": (
        "9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534"
    ),
    "node:22-alpine": (
        "c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32"
    ),
    "nginx:1.30.4-alpine3.24": (
        "dc5069ad14f19660b141b21236140b91656bf89bbc3e2417c70ae650cd66104c"
    ),
}


def assert_release_dockerfile_contract(backend: str, frontend: str) -> None:
    from_lines = [
        line.strip()
        for text in (backend, frontend)
        for line in text.splitlines()
        if line.startswith("FROM ")
    ]
    external_from_lines = [
        line
        for line in from_lines
        if line.startswith("FROM python:")
        or line.startswith("FROM node:")
        or line.startswith("FROM nginx:")
    ]
    expected_from_lines = [
        f"FROM python:3.11-slim@sha256:{EXPECTED_BASES['python:3.11-slim']} AS backend-shared-base",
        f"FROM node:22-alpine@sha256:{EXPECTED_BASES['node:22-alpine']} AS builder",
        f"FROM nginx:1.30.4-alpine3.24@sha256:{EXPECTED_BASES['nginx:1.30.4-alpine3.24']} AS frontend-runtime",
    ]
    if external_from_lines != expected_from_lines:
        raise ValueError("RELEASE_BASE_DIGEST_DRIFT")
    if "FROM backend-shared-base AS migration-runner" not in from_lines:
        raise ValueError("BACKEND_INTERNAL_STAGE_DRIFT")
    if "FROM backend-shared-base AS backend-runtime" not in from_lines:
        raise ValueError("BACKEND_INTERNAL_STAGE_DRIFT")
    if not re.search(r"^FROM\s+\S+@sha256:[0-9a-f]{64}(?:\s|$)", backend, re.MULTILINE):
        raise ValueError("BACKEND_FLOATING_BASE")
    if not re.search(r"^FROM\s+\S+@sha256:[0-9a-f]{64}(?:\s|$)", frontend, re.MULTILINE):
        raise ValueError("FRONTEND_FLOATING_BASE")
    if (
        "RUN corepack enable && corepack prepare pnpm@11.22.0 --activate"
        not in frontend
    ):
        raise ValueError("COREPACK_PNPM_PIN_DRIFT")
    if "package-lock.json" in frontend or "npm ci" in frontend:
        raise ValueError("NPM_DEPENDENCY_GRAPH_FORBIDDEN")
    if "COPY package*.json" in frontend:
        raise ValueError("AMBIGUOUS_PACKAGE_MANIFEST_FORBIDDEN")
    if "COPY package.json pnpm-lock.yaml ./" not in frontend:
        raise ValueError("PNPM_MANIFEST_GRAPH_DRIFT")
    if "RUN pnpm install --frozen-lockfile" not in frontend:
        raise ValueError("PNPM_FROZEN_INSTALL_DRIFT")
    policy_copy = "COPY pnpm-workspace.yaml ./"
    if policy_copy not in frontend or frontend.index(policy_copy) > frontend.index(
        "RUN pnpm install --frozen-lockfile"
    ):
        raise ValueError("PNPM_WORKSPACE_BUILD_POLICY_MISSING_BEFORE_INSTALL")


def test_release_base_images_are_bound_to_frozen_index_digests() -> None:
    backend = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    frontend = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert_release_dockerfile_contract(backend, frontend)


def test_frontend_builder_uses_ci_pnpm_frozen_lockfile_graph() -> None:
    frontend = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")

    assert "RUN corepack enable && corepack prepare pnpm@11.22.0 --activate" in frontend
    assert "COPY package.json pnpm-lock.yaml ./" in frontend
    assert "RUN pnpm install --frozen-lockfile" in frontend
    assert "package-lock.json" not in frontend
    assert "npm ci" not in frontend
    assert "COPY package*.json" not in frontend


def test_frontend_runtime_binds_fixed_libuuid_version() -> None:
    frontend = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    runtime = frontend.split(" AS frontend-runtime\n", 1)[1]
    assert "RUN apk add --no-cache libuuid=2.42.3-r1 && rm -f /var/log/apk.log\n" in runtime


def test_backend_roles_share_hash_locked_psutil_wheel() -> None:
    backend = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    shared = backend.split("FROM backend-shared-base AS migration-runner", 1)[0]
    requirements = (ROOT / "main/backend/requirements.txt").read_text(encoding="utf-8")
    wheels = (ROOT / "main/backend/requirements-psutil-wheels.txt").read_text(encoding="utf-8")
    assert "psutil==6.0.0\n" in requirements
    assert "psutil==6.0.0 \\" in wheels
    assert set(re.findall(r"--hash=sha256:([0-9a-f]{64})", wheels)) == {
        "e2e8d0054fc88153ca0544f5c4d554d42e33df2e009c4ff42284ac9ebdef4132",
        "5fd9a97c8e94059b0ef54a7d4baf13b405011176c3b6ff257c247cae0d560ecd",
    }
    assert "--require-hashes --only-binary=:all: --no-deps" in shared
    wheel_install = "python -m pip install --no-index --no-deps /opt/mrw-wheels/psutil-6.0.0-*.whl"
    assert wheel_install in shared
    assert shared.index(wheel_install) < shared.index("RUN pip install -r /app/requirements.txt")


def test_backend_build_time_bytecode_and_install_logs_are_deterministic() -> None:
    backend = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG SOURCE_DATE_EPOCH=0\n" in backend
    assert "ENV SOURCE_DATE_EPOCH" not in backend
    assert "rm -f /var/log/alternatives.log /var/log/apt/history.log" in backend
    assert "/var/log/apt/term.log /var/log/dpkg.log" in backend
    assert "&& rm -f /var/cache/ldconfig/aux-cache" in backend
    assert "rm -f /etc/ld.so.cache" not in backend
    assert "rm -rf /var/lib/dpkg" not in backend


@pytest.mark.parametrize(
    ("old", "new", "failure"),
    (
        (EXPECTED_BASES["node:22-alpine"], "0" * 64, "RELEASE_BASE_DIGEST_DRIFT"),
        ("pnpm install --frozen-lockfile", "npm ci", "NPM_DEPENDENCY_GRAPH_FORBIDDEN"),
        ("COPY package.json pnpm-lock.yaml ./", "COPY package*.json ./", "AMBIGUOUS_PACKAGE_MANIFEST_FORBIDDEN"),
        (
            "COPY pnpm-workspace.yaml ./", "# omitted workspace build policy",
            "PNPM_WORKSPACE_BUILD_POLICY_MISSING_BEFORE_INSTALL",
        ),
    ),
)
def test_frontend_dependency_and_base_mutations_fail_closed(
    old: str, new: str, failure: str
) -> None:
    payload = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    mutated = payload.replace(old, new, 1)

    assert mutated != payload
    with pytest.raises(ValueError, match=failure):
        assert_release_dockerfile_contract(BACKEND_DOCKERFILE.read_text(encoding="utf-8"), mutated)
