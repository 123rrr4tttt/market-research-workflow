#!/usr/bin/env python3
"""Focused production CI and immutable artifact contract tests."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.formal_release import check_static_production_contract as checker

if TYPE_CHECKING:
    from app.contracts.json import JSONValue


ROOT = Path(__file__).resolve().parents[2]


def _array(value: JSONValue) -> list[JSONValue]:
    assert isinstance(value, list)
    return value


def _object(value: JSONValue) -> dict[str, JSONValue]:
    assert isinstance(value, dict)
    return value


def _text(value: JSONValue) -> str:
    assert isinstance(value, str)
    return value


def named_steps(steps: list[JSONValue]) -> dict[str, dict[str, JSONValue]]:
    named: dict[str, dict[str, JSONValue]] = {}
    for value in steps:
        step = _object(value)
        if "name" in step:
            named[_text(step["name"])] = step
    return named


class S1WorkflowContractTestCase(unittest.TestCase):
    branch: dict[str, JSONValue]
    workflow: dict[str, JSONValue]
    jobs: dict[str, JSONValue]
    contracts: dict[str, checker.CheckContract]
    parsed: dict[str, tuple[object, str | None]]

    def setUp(self) -> None:
        branch_value: JSONValue = json.loads(
            (ROOT / ".github/branch-protection-required-checks.json").read_text(encoding="utf-8")
        )
        self.branch = _object(branch_value)
        workflow_value: JSONValue
        workflow_value, workflow_error = checker.parse_yaml(ROOT / ".github/workflows/backend-tests.yml")
        self.assertIsNone(workflow_error)
        self.workflow = _object(workflow_value)
        self.contracts, self.parsed = checker.parse_contracts_and_jobs(ROOT, self.branch)
        jobs_value: JSONValue = checker.as_mapping(self.workflow["jobs"], "workflow_jobs")
        self.jobs = _object(jobs_value)

    def test_required_check_contract_covers_every_category_exactly(self) -> None:
        required = {_text(item) for item in _array(self.branch["required_checks"])}
        expected = {contract.required_check for contract in self.contracts.values()}
        self.assertEqual(len(required), len(set(required)))
        self.assertEqual(set(required), expected)
        self.assertEqual(set(self.contracts), set(checker.REQUIRED_CHECK_CATEGORIES))
        required_check_contracts = _object(self.branch["required_check_contracts"])
        self.assertEqual(
            {name: _text(_object(item)["source"]) for name, item in required_check_contracts.items()},
            {category: ".github/workflows/backend-tests.yml" for category in checker.REQUIRED_CHECK_CATEGORIES},
        )
        convergence = _object(self.jobs["required-convergence-check"])
        self.assertEqual(
            _array(convergence["needs"]),
            _array(self.branch["required_checks"]),
        )

    def test_every_required_category_has_an_unconditional_concrete_job(self) -> None:
        concurrency = _object(self.workflow["concurrency"])
        self.assertEqual(concurrency["cancel-in-progress"], False)
        for contract in self.contracts.values():
            job = _object(self.jobs[contract.required_check])
            self.assertNotIn("if", job)
            self.assertFalse(job.get("continue-on-error"))
            self.assertIsInstance(job["steps"], list)
            self.assertTrue(job["steps"])
            for step in _array(job["steps"]):
                self.assertFalse(_object(step).get("continue-on-error"))

    def test_convergence_is_not_promoted_to_a_required_check(self) -> None:
        self.assertNotIn(
            "required-convergence-check",
            {_text(item) for item in _array(self.branch["required_checks"])},
        )
        self.assertNotIn(
            "required-convergence-check",
            _object(self.branch["required_check_contracts"]),
        )

    def test_backend_unit_lane_installs_declared_async_test_dependencies(self) -> None:
        expected_test_dependencies = {"pytest==9.0.3", "pytest-asyncio==1.3.0"}
        pyproject_value: JSONValue = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        pyproject = _object(pyproject_value)
        project = _object(pyproject["project"])
        optional_dependencies = _object(project["optional-dependencies"])
        dev_dependencies = [_text(dependency) for dependency in _array(optional_dependencies["dev"])]
        declared_test_dependencies = {
            dependency for dependency in dev_dependencies if dependency.startswith(("pytest==", "pytest-asyncio=="))
        }
        self.assertEqual(expected_test_dependencies, declared_test_dependencies)

        requirements = (ROOT / "main/backend/requirements.txt").read_text(encoding="utf-8")
        self.assertNotRegex(requirements, r"(?im)^\s*pytest[-_]asyncio(?:\s|[<>=!~;@\[])")

        backend_job = _object(self.jobs["backend-unit-check"])
        steps = named_steps(_array(backend_job["steps"]))
        install_tokens = set(shlex.split(_text(steps["Install dependencies"]["run"])))
        installed_test_dependencies = {
            token for token in install_tokens if token.startswith(("pytest==", "pytest-asyncio=="))
        }
        self.assertEqual(expected_test_dependencies, installed_test_dependencies)

        unit_step = steps["Run pytest (unit, deterministic lane)"]
        self.assertNotIn("working-directory", unit_step)
        unit_env = _object(unit_step["env"])
        self.assertEqual("1", unit_env["MRW_PYTEST_EXCLUDE_FLAKY"])
        self.assertIn("bash scripts/test-standardize.sh unit -q", _text(unit_step["run"]))

        dockerfile_test = (ROOT / "main/backend/Dockerfile.test").read_text(encoding="utf-8")
        self.assertIn("COPY ./pyproject.toml /opt/mrw/pyproject.toml", dockerfile_test)
        self.assertIn('["optional-dependencies"]["dev"]', dockerfile_test)

    def test_runtime_refreshes_setuptools_vendor_bundle_in_shared_base(self) -> None:
        dockerfile = (ROOT / "main/backend/Dockerfile").read_text(encoding="utf-8")
        runtime_install = dockerfile.index("RUN pip install -r /app/requirements.txt")
        optional_install = dockerfile.index('RUN if [ "$INSTALL_OPTIONAL_ENHANCEMENTS" = "true" ]; then')
        optional_install_end = dockerfile.index("\n    fi", optional_install)
        vendor_refresh = dockerfile.index('RUN python -m pip install --no-deps "setuptools==80.10.2"')
        source_copy = dockerfile.index("COPY ./src /opt/mrw/src")
        migration_role = dockerfile.index("FROM backend-shared-base AS migration-runner")
        backend_role = dockerfile.index("FROM backend-shared-base AS backend-runtime")

        self.assertLess(runtime_install, vendor_refresh)
        self.assertLess(optional_install_end, vendor_refresh)
        self.assertLess(vendor_refresh, source_copy)
        self.assertLess(vendor_refresh, migration_role)
        self.assertLess(vendor_refresh, backend_role)
        self.assertEqual(1, dockerfile.count("setuptools==80.10.2"))

        requirements = (ROOT / "main/backend/requirements.txt").read_text(encoding="utf-8")
        requirement_names: set[str] = set()
        for raw_line in requirements.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            name = re.split(r"[<>=!~@\[\s]", line, maxsplit=1)[0]
            requirement_names.add(re.sub(r"[-_.]+", "-", name).lower())
        self.assertTrue({"jaraco-context", "wheel"}.isdisjoint(requirement_names))

    def test_docker_job_keeps_static_production_and_development_compose_separate(self) -> None:
        job = _object(self.jobs["docker-config-check"])
        steps = named_steps(_array(job["steps"]))

        production = steps["Validate production compose configuration"]
        self.assertNotIn("env", production)
        self.assertEqual(
            "python3 scripts/formal_release/check_production_compose_config.py",
            _text(production["run"]),
        )
        self.assertNotIn(
            "docker-compose.production.yml",
            _text(steps["Run backend tests in docker compose"]["run"]),
        )
        self.assertIn(
            "docker compose -f main/ops/docker-compose.yml --profile",
            _text(steps["Run backend tests in docker compose"]["run"]),
        )

    def test_docker_job_collects_diagnostics_only_after_failure_and_always_tears_down(self) -> None:
        job = _object(self.jobs["docker-config-check"])
        steps = named_steps(_array(job["steps"]))
        self.assertEqual(steps["Collect docker compose diagnostics on failure"]["if"], "failure()")
        self.assertEqual(steps["Upload docker compose diagnostics"]["if"], "failure()")
        self.assertEqual(steps["Teardown"]["if"], "always()")
        self.assertIn("--remove-orphans", _text(steps["Teardown"]["run"]))

    def test_convergence_job_is_fail_closed_for_success_cancel_and_skip(self) -> None:
        job = _object(self.jobs["required-convergence-check"])
        self.assertEqual(job["if"], "always()")
        run = _text(_object(_array(job["steps"])[0])["run"])
        for category in checker.REQUIRED_CHECK_CATEGORIES:
            required_job = self.contracts[category].required_check
            self.assertIn(f'"{required_job}"', run)
        self.assertIn('result != "success"', run)
        self.assertIn("sys.exit(1)", run)

    def test_security_contract_has_three_real_scan_families(self) -> None:
        finding = checker.check_workflow_security(self.contracts, self.parsed)
        self.assertEqual("PASS", finding.status)

    def test_metadata_contract_passes_with_clean_compose_digests(self) -> None:
        compose = {
            "services": {
                "db": {"image": "${DB_IMAGE_DIGEST:?required production sha256 digest}"},
                "es": {"image": "${ES_IMAGE_DIGEST:?required production sha256 digest}"},
                "redis": {"image": "${REDIS_IMAGE_DIGEST:?required production sha256 digest}"},
                "backend": {
                    "image": "${BACKEND_IMAGE_DIGEST:?required production sha256 digest}",
                    "environment": {"SERVICE_VERSION": "1.2.3"},
                },
                "celery-worker": {
                    "image": "${BACKEND_IMAGE_DIGEST:?required production sha256 digest}",
                    "environment": {"SERVICE_VERSION": "1.2.3"},
                },
                "frontend": {
                    "image": "${FRONTEND_IMAGE_DIGEST:?required production sha256 digest}",
                },
            }
        }
        inputs = checker.ContractInputs(
            compose=compose,
            compose_error=None,
            env=(),
            env_error=None,
        )
        finding = checker.check_artifact_metadata(inputs, self.contracts, self.parsed)
        self.assertEqual("PASS", finding.status)
        self.assertIn("canonical_artifact_chain_contract=complete", finding.evidence)
        self.assertIn(
            "artifact_bytes_not_built_or_verified_current_run",
            finding.evidence,
        )

    def test_metadata_job_has_canonical_oci_predicates_independent_rebuild_and_upload(self) -> None:
        job_text = self.job_text("artifact-metadata-check")
        self.assertEqual(2, job_text.count("docker/setup-buildx-action@v3"))
        self.assertEqual(6, job_text.count("docker/build-push-action@v6"))
        self.assertIn("id: canonical-builder", job_text)
        self.assertIn("id: rebuild-builder", job_text)
        self.assertIn("builder: ${{ steps.canonical-builder.outputs.name }}", job_text)
        self.assertIn("builder: ${{ steps.rebuild-builder.outputs.name }}", job_text)
        self.assertIn("provenance: true", job_text)
        self.assertIn("sbom: true", job_text)
        self.assertIn("outputs: type=oci,dest=immutable-release-metadata/backend/image.oci.tar", job_text)
        for output in (
            "immutable-release-metadata/backend/image.oci.tar",
            "immutable-release-metadata/frontend/image.oci.tar",
            "immutable-release-metadata/migration-runner/image.oci.tar",
            "rebuild-output/backend.oci.tar",
            "rebuild-output/frontend.oci.tar",
            "rebuild-output/migration-runner.oci.tar",
        ):
            self.assertIn(f"outputs: type=oci,dest={output},rewrite-timestamp=true", job_text)
        self.assertIn("https://slsa.dev/provenance/", job_text)
        self.assertIn("https://spdx.dev/Document", job_text)
        self.assertIn("subject_matches", job_text)
        self.assertIn("OCI blob digest mismatch", job_text)
        self.assertIn("linux/amd64-image-manifest-digest", job_text)
        self.assertIn("non-reproducible clean build", job_text)
        self.assertIn("actions/upload-artifact@v4", job_text)
        self.assertIn("name: immutable-release-metadata", job_text)
        self.assertIn("if-no-files-found: error", job_text)
        self.assertIn("sha256:[0-9a-f]{64}", job_text)

    def test_required_chain_has_no_registry_signing_or_tlog_authority(self) -> None:
        job_text = self.job_text("artifact-metadata-check")
        self.assertNotIn("secrets.", job_text)
        self.assertNotIn("ghcr.io", job_text)
        self.assertNotIn("cosign sign", job_text)
        self.assertNotIn("docker/login-action", job_text)
        self.assertNotIn("rekor", job_text.lower())
        self.assertNotIn("push: true", job_text)
        self.assertIn("UNEXECUTED_AUTHORITY_REQUIRED", job_text)
        self.assertIn("PRODUCTION_RELEASE_NOT_AUTHORIZED", job_text)
        scan_text = self.job_text("image-vulnerability-scan-check")
        self.assertIn("actions/download-artifact@v4", scan_text)
        self.assertNotIn("docker/build-push-action", scan_text)
        for role in ("backend", "frontend", "migration-runner"):
            self.assertIn(f"immutable-release-metadata/{role}/image.oci.tar", scan_text)

    def test_embedded_trivy_report_validator_rejects_empty_or_high_severity_evidence(self) -> None:
        scan_job = _object(self.jobs["image-vulnerability-scan-check"])
        step = named_steps(_array(scan_job["steps"]))["Validate and index vulnerability reports"]
        run = _text(step["run"])
        script = run.split("python3 - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
        roles = ("backend", "frontend", "migration-runner")
        with tempfile.TemporaryDirectory(prefix="mrw-trivy-validator-") as temp:
            root = Path(temp)
            metadata_root = root / "immutable-release-metadata"
            output_root = root / "vulnerability-scan-evidence"
            metadata_root.mkdir()
            output_root.mkdir()
            (metadata_root / "index.json").write_text(
                json.dumps(
                    {
                        "roles": {
                            role: {"artifact_digest": "sha256:" + str(position) * 64}
                            for position, role in enumerate(roles, start=1)
                        }
                    }
                ),
                encoding="utf-8",
            )

            def write_report(role: str, vulnerabilities: list[dict[str, str]] | None = None) -> None:
                (output_root / f"{role}.json").write_text(
                    json.dumps(
                        {
                            "SchemaVersion": 2,
                            "ArtifactName": f"/work/immutable-release-metadata/{role}/image.oci.tar",
                            "ArtifactType": "container_image",
                            "Results": [
                                {
                                    "Target": role,
                                    "Vulnerabilities": vulnerabilities or [],
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )

            for role in roles:
                write_report(role)
            completed = subprocess.run(
                [sys.executable, "-c", script], cwd=root, text=True, capture_output=True, check=False
            )
            self.assertEqual(0, completed.returncode, completed.stderr)

            (output_root / "backend.json").write_text("{}", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-c", script], cwd=root, text=True, capture_output=True, check=False
            )
            self.assertNotEqual(0, completed.returncode)
            self.assertIn("Trivy report identity or schema mismatch for backend", completed.stderr)

            write_report("backend", [{"Severity": "CRITICAL"}])
            completed = subprocess.run(
                [sys.executable, "-c", script], cwd=root, text=True, capture_output=True, check=False
            )
            self.assertNotEqual(0, completed.returncode)
            self.assertIn("HIGH/CRITICAL vulnerabilities persisted for backend", completed.stderr)

    def job_text(self, job_name: str) -> str:
        text = (ROOT / ".github/workflows/backend-tests.yml").read_text(encoding="utf-8")
        match = re.search(
            rf"(?ms)^  {re.escape(job_name)}:\n.*?(?=^  [A-Za-z0-9_-]+:\n|\Z)",
            text,
        )
        assert match is not None
        return match.group(0)


if __name__ == "__main__":
    unittest.main()
