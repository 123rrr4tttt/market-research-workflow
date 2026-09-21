"""Focused production Compose isolation and development compatibility tests."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEV_COMPOSE_PATH = ROOT / "main" / "ops" / "docker-compose.yml"
PROD_COMPOSE_PATH = ROOT / "main" / "ops" / "docker-compose.production.yml"
PROD_EXAMPLE_PATH = ROOT / "main" / "backend" / ".env.production.example"
CHECKER_PATH = ROOT / "scripts" / "formal_release" / "check_static_production_contract.py"

CHECKER_ID = "s1_static_production_contract"
IMAGE_VARIABLES = {
    "db": "DB_IMAGE_DIGEST",
    "es": "ES_IMAGE_DIGEST",
    "redis": "REDIS_IMAGE_DIGEST",
    "backend": "BACKEND_IMAGE_DIGEST",
    "celery-worker": "BACKEND_IMAGE_DIGEST",
    "frontend": "FRONTEND_IMAGE_DIGEST",
}
PRODUCTION_SERVICES = set(IMAGE_VARIABLES)
PRODUCTION_CONTROL_VARIABLES = (
    "PRODUCTION_ALLOWED_HOSTS",
    "PRODUCTION_ALLOWED_ORIGINS",
    "PRODUCTION_TRUSTED_ACTOR_SOURCES",
    "PRODUCTION_TRUSTED_AUTH_MODES",
    "PRODUCTION_REQUIRE_TLS",
    "PRODUCTION_ALLOWED_METHODS",
    "PRODUCTION_ALLOWED_CONTENT_TYPES",
    "PRODUCTION_MAX_BODY_BYTES",
    "PRODUCTION_HTTP_RATE_MAX_REQUESTS",
    "PRODUCTION_HTTP_RATE_WINDOW_SECONDS",
    "PRODUCTION_PROVIDER_IDS",
    "PRODUCTION_PROVIDER_RATE_MAX_REQUESTS",
    "PRODUCTION_PROVIDER_RATE_WINDOW_SECONDS",
    "PRODUCTION_PROVIDER_MAX_PAYLOAD_BYTES",
    "PRODUCTION_PROVIDER_CATALOG_BINDING",
    "PRODUCTION_RATE_AUTHORITY_BINDING",
    "PRODUCTION_CANONICAL_WRITER_BINDING",
    "PRODUCTION_CANONICAL_WRITER_OWNER",
    "PRODUCTION_PROJECT_KEYS",
    "PRODUCTION_METRICS_TOKEN",
    "PRODUCTION_OBSERVABILITY_RUNTIME_ID",
    "PRODUCTION_CANARY_ROUTE_ENABLED",
    "PRODUCTION_DOMAIN_REJECTION_TRIGGER_RATIO",
    "PRODUCTION_DOMAIN_REJECTION_RECOVER_RATIO",
    "PRODUCTION_ROUTE_ERROR_TRIGGER_RATIO",
    "PRODUCTION_ROUTE_ERROR_RECOVER_RATIO",
    "PRODUCTION_RELEASE_ERROR_TRIGGER_RATIO",
    "PRODUCTION_RELEASE_ERROR_RECOVER_RATIO",
)
REQUIRED_ENV = [
    *dict.fromkeys(IMAGE_VARIABLES.values()),
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "DATABASE_URL",
    "REDIS_PASSWORD",
    "ELASTIC_PASSWORD",
    "ES_URL",
    "REDIS_URL",
    "FRONTEND_PUBLIC_PORT",
    "RELEASE_BUILD_COMMIT",
    "RELEASE_BUILD_TREE",
    "RELEASE_BUILD_DIGEST",
    "RUN_MIGRATIONS_BACKEND",
    "RUN_MIGRATIONS_WORKER",
    "CODEX_OAUTH_COOKIE_SECURE",
    *PRODUCTION_CONTROL_VARIABLES,
]


def _load_checker() -> Any:
    spec = importlib.util.spec_from_file_location(CHECKER_ID, CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def fixture_values() -> dict[str, str]:
    return {
        "DB_IMAGE_DIGEST": "ghcr.io/example/postgres@sha256:" + "1" * 64,
        "ES_IMAGE_DIGEST": "ghcr.io/example/elasticsearch@sha256:" + "2" * 64,
        "REDIS_IMAGE_DIGEST": "ghcr.io/example/redis@sha256:" + "3" * 64,
        "BACKEND_IMAGE_DIGEST": "ghcr.io/example/backend@sha256:" + "4" * 64,
        "FRONTEND_IMAGE_DIGEST": "ghcr.io/example/frontend@sha256:" + "5" * 64,
        "POSTGRES_USER": "fixture_owner",
        "POSTGRES_PASSWORD": "fixture_password",
        "POSTGRES_DB": "fixture_db",
        "DATABASE_URL": "postgresql+psycopg2://fixture_owner:fixture_password@db:5432/fixture_db",
        "REDIS_PASSWORD": "fixture_redis_password",
        "ELASTIC_PASSWORD": "fixture_elastic_password",
        "ES_URL": "https://elastic:fixture_elastic_password@es:9200",
        "REDIS_URL": "redis://:fixture_redis_password@redis:6379/0",
        "ES_JAVA_OPTS": "-Xms1g -Xmx1g",
        "FRONTEND_PUBLIC_PORT": "18080",
        "RELEASE_BUILD_COMMIT": "0123456789abcdef0123456789abcdef01234567",
        "RELEASE_BUILD_TREE": "0123456789abcdef0123456789abcdef01234567",
        "RELEASE_BUILD_DIGEST": "sha256:" + "6" * 64,
        "RUN_MIGRATIONS_BACKEND": "true",
        "RUN_MIGRATIONS_WORKER": "false",
        "CODEX_OAUTH_COOKIE_SECURE": "true",
        "PRODUCTION_ALLOWED_HOSTS": "api.internal",
        "PRODUCTION_ALLOWED_ORIGINS": "https://app.example",
        "PRODUCTION_TRUSTED_ACTOR_SOURCES": "authenticated_request_state",
        "PRODUCTION_TRUSTED_AUTH_MODES": "oidc_claims",
        "PRODUCTION_REQUIRE_TLS": "true",
        "PRODUCTION_ALLOWED_METHODS": "GET,POST,PUT,PATCH,DELETE",
        "PRODUCTION_ALLOWED_CONTENT_TYPES": "application/json",
        "PRODUCTION_MAX_BODY_BYTES": "1048576",
        "PRODUCTION_HTTP_RATE_MAX_REQUESTS": "100",
        "PRODUCTION_HTTP_RATE_WINDOW_SECONDS": "60",
        "PRODUCTION_PROVIDER_IDS": "ollama",
        "PRODUCTION_PROVIDER_RATE_MAX_REQUESTS": "50",
        "PRODUCTION_PROVIDER_RATE_WINDOW_SECONDS": "60",
        "PRODUCTION_PROVIDER_MAX_PAYLOAD_BYTES": "1048576",
        "PRODUCTION_PROVIDER_CATALOG_BINDING": "provider-catalog-v1",
        "PRODUCTION_RATE_AUTHORITY_BINDING": "rate-authority-v1",
        "PRODUCTION_CANONICAL_WRITER_BINDING": "canonical-writer-v1",
        "PRODUCTION_CANONICAL_WRITER_OWNER": "canonical-writer-owner",
        "PRODUCTION_PROJECT_KEYS": "fixture_project",
        "PRODUCTION_METRICS_TOKEN": "fixture_metrics_token",
        "PRODUCTION_OBSERVABILITY_RUNTIME_ID": "fixture-runtime",
        "PRODUCTION_CANARY_ROUTE_ENABLED": "false",
        "PRODUCTION_DOMAIN_REJECTION_TRIGGER_RATIO": "0.10",
        "PRODUCTION_DOMAIN_REJECTION_RECOVER_RATIO": "0.05",
        "PRODUCTION_ROUTE_ERROR_TRIGGER_RATIO": "0.05",
        "PRODUCTION_ROUTE_ERROR_RECOVER_RATIO": "0.01",
        "PRODUCTION_RELEASE_ERROR_TRIGGER_RATIO": "0.05",
        "PRODUCTION_RELEASE_ERROR_RECOVER_RATIO": "0.01",
    }


def compose_environment(fixture: dict[str, str]) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "COMPOSE_PROJECT_NAME"}
    }
    environment.update(fixture)
    return environment


def compose_config(path: Path, env_file: Path, environment: dict[str, str]) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(path),
            "--env-file",
            str(env_file),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(completed.stdout)


def write_env(path: Path, fixture: dict[str, str]) -> None:
    path.write_text("".join(f"{key}={value}\n" for key, value in fixture.items()), encoding="utf-8")


def materialize_development_compose_fixture(directory: Path, fixture: dict[str, str]) -> Path:
    compose_path = directory / "main" / "ops" / "docker-compose.yml"
    compose_path.parent.mkdir(parents=True)
    compose_path.write_bytes(DEV_COMPOSE_PATH.read_bytes())

    backend_env = directory / "main" / "backend" / ".env"
    backend_env.parent.mkdir(parents=True)
    write_env(backend_env, fixture)
    return compose_path


def settings_production_variable_names() -> set[str]:
    settings_path = ROOT / "main" / "backend" / "app" / "settings" / "config.py"
    tree = ast.parse(settings_path.read_text(encoding="utf-8"), filename=str(settings_path))
    settings_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Settings"
    )
    return {
        node.target.id
        for node in settings_class.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id.startswith("production_")
    }


def compose_environment_values(compose_text: str, service_name: str) -> dict[str, str]:
    parsed = checker.StrictYamlParser(compose_text).parse()
    environment = parsed["services"][service_name].get("environment", {})
    assert all(isinstance(value, str) for value in environment.values())
    return environment


def test_r3_static_compose_family_passes_for_repository_contract() -> None:
    report = checker.evaluate_static_production_contract(ROOT)
    family = {
        "compose.production_profile",
        "compose.image_digest_pinning",
        "compose.production_policy",
        "compose.public_ports",
        "compose.source_bind_mounts",
        "database.default_credentials",
        "compose.elasticsearch_security",
    }
    failures = {
        finding.check_id: (finding.status, finding.summary, finding.evidence)
        for finding in report.findings
        if finding.check_id in family and finding.status != "PASS"
    }
    assert failures == {}


def test_production_source_binds_exact_images_and_policy_env() -> None:
    compose_text = PROD_COMPOSE_PATH.read_text(encoding="utf-8")
    image_lines = re.findall(r'^    image: "([^"]+)"$', compose_text, flags=re.MULTILINE)
    assert len(image_lines) == len(IMAGE_VARIABLES)
    required_image = "${%s:?required production sha256 digest}"
    for line in image_lines:
        assert any(line == required_image % variable for variable in set(IMAGE_VARIABLES.values()))

    parsed = checker.StrictYamlParser(compose_text).parse()
    assert set(parsed["services"]) == PRODUCTION_SERVICES
    assert all("profiles" not in service for service in parsed["services"].values())
    for service_name, variable in IMAGE_VARIABLES.items():
        assert f"${{{variable}:?" in parsed["services"][service_name]["image"]

    example = PROD_EXAMPLE_PATH.read_text(encoding="utf-8")
    for variable in dict.fromkeys(IMAGE_VARIABLES.values()):
        assert re.search(rf"^{variable}=\s*$", example, flags=re.MULTILINE)
    assert re.search(r"^POSTGRES_PASSWORD=\s*$", example, flags=re.MULTILINE)
    assert re.search(r"^REDIS_PASSWORD=\s*$", example, flags=re.MULTILINE)
    for variable in ("RELEASE_BUILD_COMMIT", "RELEASE_BUILD_TREE", "RELEASE_BUILD_DIGEST"):
        assert re.search(rf"^{variable}=\s*$", example, flags=re.MULTILINE)
    assert re.search(r"^CODEX_OAUTH_COOKIE_SECURE=true$", example, flags=re.MULTILINE)


def test_production_control_inputs_match_settings_and_are_fail_fast() -> None:
    assert set(PRODUCTION_CONTROL_VARIABLES) == {
        name.upper() for name in settings_production_variable_names()
    }

    compose_text = PROD_COMPOSE_PATH.read_text(encoding="utf-8")
    for variable in PRODUCTION_CONTROL_VARIABLES:
        required_ref = "${" + variable + ":?required production "
        assert compose_text.count(required_ref) == 2, variable

    example = PROD_EXAMPLE_PATH.read_text(encoding="utf-8")
    for variable in PRODUCTION_CONTROL_VARIABLES:
        if variable == "PRODUCTION_CANARY_ROUTE_ENABLED":
            pattern = rf"^{variable}=(?:\s*|false)$"
        else:
            pattern = rf"^{variable}=\s*$"
        assert re.search(pattern, example, flags=re.MULTILINE), variable


def test_development_backend_healthcheck_uses_exec_argv() -> None:
    parsed = checker.StrictYamlParser(DEV_COMPOSE_PATH.read_text(encoding="utf-8")).parse()
    healthcheck = parsed["services"]["backend"]["healthcheck"]
    assert healthcheck["test"] == ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
    assert healthcheck["interval"] == "30s"
    assert healthcheck["timeout"] == "10s"
    assert healthcheck["retries"] == 3
    assert healthcheck["start_period"] == "40s"


def test_production_backend_and_worker_activate_policy_without_tokenized_health_probe() -> None:
    compose_text = PROD_COMPOSE_PATH.read_text(encoding="utf-8")
    parsed = checker.StrictYamlParser(compose_text).parse()
    for service_name in ("backend", "celery-worker"):
        environment = compose_environment_values(compose_text, service_name)
        assert environment["ENV"] == "production"
        for variable in PRODUCTION_CONTROL_VARIABLES:
            assert variable in environment
            assert environment[variable].startswith("${" + variable + ":?")

    backend_environment = compose_environment_values(compose_text, "backend")
    assert backend_environment["CODEX_OAUTH_COOKIE_SECURE"].startswith(
        "${CODEX_OAUTH_COOKIE_SECURE:?"
    )

    health_test = "\n".join(parsed["services"]["backend"]["healthcheck"]["test"])
    assert "curl --config -" in health_test
    assert "Authorization: Bearer $${PRODUCTION_METRICS_TOKEN}" in health_test
    assert "?token=" not in health_test
    assert parsed["services"]["celery-worker"].get("healthcheck") is not None


def test_production_renders_immutable_services_without_infrastructure_ports_or_binds() -> None:
    fixture = fixture_values()
    with tempfile.TemporaryDirectory(prefix="s1-r3-render-", dir="/private/tmp") as temp_dir:
        env_file = Path(temp_dir) / "production.env"
        write_env(env_file, fixture)
        config = compose_config(PROD_COMPOSE_PATH, env_file, compose_environment(fixture))

    assert set(config["services"]) == PRODUCTION_SERVICES
    for name in PRODUCTION_SERVICES:
        service = config["services"][name]
        assert re.search(r"@sha256:[0-9a-f]{64}$", service["image"])
        assert service.get("build") is None
        assert all(volume["type"] == "volume" for volume in service.get("volumes", []))

    unpublished = ("db", "es", "redis", "backend", "celery-worker")
    assert all(config["services"][name].get("ports") is None for name in unpublished)
    assert config["services"]["frontend"]["ports"][0]["target"] == 80
    assert config["services"]["es"]["environment"]["xpack.security.enabled"] == "true"
    assert config["services"]["backend"]["image"] == config["services"]["celery-worker"]["image"]
    for name in ("backend", "celery-worker"):
        environment = config["services"][name]["environment"]
        for key in ("RELEASE_BUILD_COMMIT", "RELEASE_BUILD_TREE", "RELEASE_BUILD_DIGEST"):
            assert environment[key] == fixture[key]
        migration = fixture["RUN_MIGRATIONS_BACKEND" if name == "backend" else "RUN_MIGRATIONS_WORKER"]
        assert environment["RUN_MIGRATIONS"] == migration


def test_production_required_values_fail_fast_without_host_defaults() -> None:
    fixture = fixture_values()
    for missing in REQUIRED_ENV:
        with tempfile.TemporaryDirectory(prefix="s1-r3-missing-", dir="/private/tmp") as temp_dir:
            env_file = Path(temp_dir) / "production.env"
            partial = dict(fixture)
            partial.pop(missing)
            write_env(env_file, partial)
            completed = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(PROD_COMPOSE_PATH),
                    "--env-file",
                    str(env_file),
                    "config",
                    "--quiet",
                ],
                cwd=ROOT,
                env=compose_environment(partial),
                text=True,
                capture_output=True,
                check=False,
            )
        assert completed.returncode != 0, missing
        assert missing in completed.stderr, (missing, completed.stderr)


def test_development_compose_remains_renderable_with_current_service_names() -> None:
    fixture = {
        "DATABASE_URL": "postgresql+psycopg2://postgres:postgres@db:5432/postgres",
    }
    with tempfile.TemporaryDirectory(prefix="s1-r3-development-", dir="/private/tmp") as temp_dir:
        fixture_root = Path(temp_dir)
        compose_path = materialize_development_compose_fixture(fixture_root, fixture)
        env_file = fixture_root / "development.env"
        write_env(env_file, fixture)
        config = compose_config(compose_path, env_file, compose_environment(fixture))

    services = config["services"]
    for name in ("db", "es", "redis", "backend", "celery-worker"):
        assert name in services
    for name in ("db", "es", "redis"):
        assert services[name]["ports"][0]["host_ip"] == "127.0.0.1"
    assert services["backend"]["build"]["dockerfile"] == "./main/backend/Dockerfile"
    assert services["backend"]["environment"]["DATABASE_URL"] == fixture["DATABASE_URL"]
    assert all(volume["type"] == "bind" or volume["type"] == "volume" for volume in services["backend"]["volumes"])


def test_production_compose_is_isolated_from_development_contract() -> None:
    dev_text = DEV_COMPOSE_PATH.read_text(encoding="utf-8")
    production_text = PROD_COMPOSE_PATH.read_text(encoding="utf-8")
    assert "docker-compose.production.yml" not in dev_text
    assert "backend-dev" not in production_text
    assert "db-dev" not in production_text
    parsed_dev = checker.StrictYamlParser(dev_text).parse()
    assert "docker-compose.production.yml" not in parsed_dev
    production_services = checker.StrictYamlParser(production_text).parse()["services"]
    assert set(production_services) == PRODUCTION_SERVICES
    assert all("profiles" not in service for service in production_services.values())
