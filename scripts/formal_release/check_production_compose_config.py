#!/usr/bin/env python3
"""Render-only production Compose config preflight."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.formal_release.model import Finding, PreflightReport


CHECKER = "production-compose-config-render"
COMPOSE_PATH = Path("main/ops/docker-compose.production.yml")
CONFIG_TIMEOUT_SECONDS = 30

SYNTHETIC_ENV = {
    "DB_IMAGE_DIGEST": "ghcr.io/example/postgres@sha256:"
    + "1" * 64,
    "ES_IMAGE_DIGEST": "ghcr.io/example/elasticsearch@sha256:"
    + "2" * 64,
    "REDIS_IMAGE_DIGEST": "ghcr.io/example/redis@sha256:"
    + "3" * 64,
    "BACKEND_IMAGE_DIGEST": "ghcr.io/example/backend@sha256:"
    + "4" * 64,
    "FRONTEND_IMAGE_DIGEST": "ghcr.io/example/frontend@sha256:"
    + "5" * 64,
    "POSTGRES_USER": "synthetic_db_user",
    "POSTGRES_PASSWORD": "synthetic_db_password",
    "POSTGRES_DB": "synthetic_db",
    "DATABASE_URL": (
        "postgresql+psycopg2://synthetic_db_user:"
        "synthetic_db_password@db:5432/synthetic_db"
    ),
    "REDIS_PASSWORD": "synthetic_redis_password",
    "ELASTIC_PASSWORD": "synthetic_elastic_password",
    "ES_URL": "https://elastic:synthetic_elastic_password@es:9200",
    "REDIS_URL": "redis://:synthetic_redis_password@redis:6379/0",
    "FRONTEND_PUBLIC_PORT": "18080",
    "RELEASE_BUILD_COMMIT": "synthetic_commit",
    "RELEASE_BUILD_TREE": "synthetic_tree",
    "RELEASE_BUILD_DIGEST": "sha256:"
    + "6" * 64,
    "RUN_MIGRATIONS_BACKEND": "false",
    "RUN_MIGRATIONS_WORKER": "false",
    "CODEX_OAUTH_COOKIE_SECURE": "true",
    "PRODUCTION_ALLOWED_HOSTS": "synthetic-host",
    "PRODUCTION_ALLOWED_ORIGINS": "https://synthetic.example",
    "PRODUCTION_TRUSTED_ACTOR_SOURCES": "synthetic_actor_source",
    "PRODUCTION_TRUSTED_AUTH_MODES": "synthetic_auth_mode",
    "PRODUCTION_REQUIRE_TLS": "true",
    "PRODUCTION_ALLOWED_METHODS": "GET,POST",
    "PRODUCTION_ALLOWED_CONTENT_TYPES": "application/json",
    "PRODUCTION_MAX_BODY_BYTES": "1048576",
    "PRODUCTION_HTTP_RATE_MAX_REQUESTS": "100",
    "PRODUCTION_HTTP_RATE_WINDOW_SECONDS": "60",
    "PRODUCTION_PROVIDER_IDS": "synthetic_provider",
    "PRODUCTION_PROVIDER_RATE_MAX_REQUESTS": "50",
    "PRODUCTION_PROVIDER_RATE_WINDOW_SECONDS": "60",
    "PRODUCTION_PROVIDER_MAX_PAYLOAD_BYTES": "1048576",
    "PRODUCTION_PROVIDER_CATALOG_BINDING": "synthetic_provider_catalog",
    "PRODUCTION_RATE_AUTHORITY_BINDING": "synthetic_rate_authority",
    "PRODUCTION_CANONICAL_WRITER_BINDING": "synthetic_canonical_writer",
    "PRODUCTION_CANONICAL_WRITER_OWNER": "synthetic_canonical_owner",
    "PRODUCTION_PROJECT_KEYS": "synthetic_project",
    "PRODUCTION_METRICS_TOKEN": "synthetic_metrics_token",
    "PRODUCTION_OBSERVABILITY_RUNTIME_ID": "synthetic-r7",
    "PRODUCTION_CANARY_ROUTE_ENABLED": "false",
    "PRODUCTION_DOMAIN_REJECTION_TRIGGER_RATIO": "0.10",
    "PRODUCTION_DOMAIN_REJECTION_RECOVER_RATIO": "0.05",
    "PRODUCTION_ROUTE_ERROR_TRIGGER_RATIO": "0.05",
    "PRODUCTION_ROUTE_ERROR_RECOVER_RATIO": "0.01",
    "PRODUCTION_RELEASE_ERROR_TRIGGER_RATIO": "0.05",
    "PRODUCTION_RELEASE_ERROR_RECOVER_RATIO": "0.01",
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def resolve_root(root: Path | None = None) -> Path:
    return (root or Path(__file__).resolve().parents[2]).resolve()


def _subprocess_environment(
    synthetic: Mapping[str, str],
    *,
    missing_keys: Sequence[str],
) -> dict[str, str]:
    values = dict(synthetic)
    for key in missing_keys:
        values.pop(key, None)

    inherited = {
        key: os.environ[key]
        for key in ("PATH", "DOCKER_HOST", "DOCKER_CONFIG")
        if key in os.environ
    }
    inherited.update(values)
    return inherited


def _write_synthetic_env(
    directory: Path,
    synthetic: Mapping[str, str],
    *,
    missing_keys: Sequence[str],
) -> Path:
    values = dict(synthetic)
    for key in missing_keys:
        values.pop(key, None)

    path = directory / "synthetic-production.env"
    path.write_text(
        "".join(f"{key}={values[key]}\n" for key in sorted(values)),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def evaluate_production_compose_config(
    *,
    repo_root: Path | None = None,
    synthetic_overrides: Mapping[str, str | None] | None = None,
    missing_keys: Sequence[str] = (),
) -> PreflightReport:
    root = resolve_root(repo_root)
    synthetic = dict(SYNTHETIC_ENV)
    for key, value in (synthetic_overrides or {}).items():
        if value is None:
            synthetic.pop(key, None)
        else:
            synthetic[key] = value

    try:
        with tempfile.TemporaryDirectory(prefix="production-compose-config-") as directory:
            env_path = _write_synthetic_env(
                Path(directory),
                synthetic,
                missing_keys=missing_keys,
            )
            environment = _subprocess_environment(
                synthetic,
                missing_keys=missing_keys,
            )
            completed = subprocess.run(
                (
                    "docker",
                    "compose",
                    "-f",
                    str(root / COMPOSE_PATH),
                    "--env-file",
                    str(env_path),
                    "config",
                    "--quiet",
                ),
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                timeout=CONFIG_TIMEOUT_SECONDS,
                check=False,
            )
    except Exception as exc:  # noqa: BLE001 - preflight boundary converts effects to findings
        return PreflightReport(
            checker=CHECKER,
            findings=(
                Finding(
                    "production.compose_config",
                    "FAIL",
                    "production compose config rendering failed",
                    (
                        f"error_class={type(exc).__name__}",
                        f"error_sha256={hashlib.sha256(str(exc).encode()).hexdigest()}",
                    ),
                ),
            ),
        )

    if completed.returncode != 0:
        return PreflightReport(
            checker=CHECKER,
            findings=(
                Finding(
                    "production.compose_config",
                    "FAIL",
                    "production compose config rendering failed",
                    (
                        f"returncode={completed.returncode}",
                        f"stderr_sha256={hashlib.sha256(completed.stderr.encode()).hexdigest()}",
                    ),
                ),
            ),
        )

    return PreflightReport(
        checker=CHECKER,
        findings=(
            Finding(
                "production.compose_config",
                "PASS",
                "production compose config rendered successfully",
                (
                    "mode=config_render_only",
                    "synthetic_inputs=true",
                    "service_start=false",
                    "temp_env_cleanup=true",
                ),
            ),
        ),
    )


def write_report(path: Path, report: PreflightReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json(), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = evaluate_production_compose_config(repo_root=args.repo_root)
    if args.output is not None:
        write_report(args.output, report)
    sys.stdout.write(report.to_json())
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
